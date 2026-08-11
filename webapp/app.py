# webapp/app.py
#
# Web GUI for the existing lead-validation pipeline, so it can run
# as a hosted FastAPI service (deployed via Docker on Kubernetes /
# Rancher) instead of a local terminal script.
#
# IMPORTANT: this file does NOT reimplement any scraping or
# validation logic. It only replaces main.py's interactive
# input()-driven CLI loop with an equivalent web form / button
# driven loop, calling the exact same functions main.py itself
# calls (lookup_linkedin_data, load_usage, save_usage,
# read_excel/save_excel, start_browser/close_browser, ...) which
# all live untouched in the project root.
#
# Why a request runs only a small BATCH of leads at a time instead
# of the whole sheet:
# A reverse proxy / ingress in front of this service will kill HTTP
# requests that run too long, and each LinkedIn profile takes
# ~15-30s with the real-browser scraper. So one click processes
# `batch_size` leads, saves progress into the working Excel file,
# and the "Validation 2" column (already how main.py tracks resume
# state) is what the dashboard's auto-run JS (webapp/templates/
# dashboard.html) uses to keep resubmitting "Start Validation" on
# its own after every batch, so a single click drives the whole
# sheet instead of making you click "Run next batch" by hand each
# time - or you can close the tab and come back later, and pick up
# where the last completed batch left off.

import os
import sys
import json
import asyncio
import datetime
import threading
from typing import Optional

# Windows + `uvicorn --reload` (WatchFiles) resets the asyncio
# event-loop policy to one that can't spawn subprocesses. Playwright
# needs to spawn its own driver subprocess even for the *sync* API,
# so without this, every /run-batch and /login-linkedin/start call
# fails with a bare `NotImplementedError` the moment it tries to
# launch a browser - only under --reload; a plain `uvicorn
# webapp.app:app` (no --reload) is unaffected. Must run before
# anything else touches asyncio, so it's here at the top of the
# module, ahead of the FastAPI/Starlette imports below.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Make the project root (parent of webapp/) importable regardless
# of the working directory uvicorn is launched from.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from playwright.sync_api import sync_playwright

import config

from excel_handler import read_excel, save_excel, list_sheet_names
from validator import normalize_text, expand_country_alias

from linkedin_scraper.browser import (
    start_browser,
    close_browser,
    get_page,
    SessionExpiredError,
)

# Reused as-is from main.py: the per-row lookup/validate/enrich
# helper and the daily-usage-tracking helpers. main.py itself is
# never executed here (its `if __name__ == "__main__"` guard keeps
# main() from running on import) - only these functions are used.
from main import (
    lookup_linkedin_data,
    load_usage,
    save_usage,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CURRENT_XLSX = os.path.join(DATA_DIR, "current.xlsx")
COOKIES_PATH = os.path.join(DATA_DIR, "cookies.json")
JOB_META_PATH = os.path.join(DATA_DIR, "job_meta.json")

WORKING_SHEET_NAME = "Sheet1"  # pandas' default to_excel() sheet name


app = FastAPI(title="Lead Validator")

# Signs the session cookie (Flask's `app.secret_key` equivalent).
# Set SECRET_KEY in the environment/Kubernetes Secret in production
# - a random one is generated per-process otherwise, which just
# means everyone gets logged out on every restart.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY") or os.urandom(24).hex(),
    same_site="lax",
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Guards every route that drives a real Playwright browser
# (/run-batch and the /login-linkedin/* trio below). Under
# Flask+gunicorn (--workers 1, no --threads) requests were
# naturally serialized; FastAPI runs sync `def` path operations in
# a threadpool, so two overlapping clicks could otherwise drive two
# browsers from two threads at once. This makes the second click
# fail fast instead. Acquired non-blocking in one request and (for
# the login flow, which spans multiple requests - see below)
# released from a later one; that's fine, threading.Lock doesn't
# care which thread/request releases it.
_batch_lock = threading.Lock()

# Set by /stop-validation, checked by _run_batch between rows.
# /run-batch runs synchronously for the whole batch (up to 15 leads,
# ~15-30s each), so a "Stop Validation" click has to reach the batch
# already in flight via shared state like this rather than just
# withholding the next request - there's no way to cancel a lead
# that's already mid-scrape, but this stops before the NEXT one
# starts, and whatever finished already is already saved (see the
# save_excel() call after the batch loop in _run_batch).
_stop_event = threading.Event()

# State for the "Log in to LinkedIn" button - runs the same flow as
# login.py (a real, visible browser window you log into by hand),
# just started/finished from the dashboard instead of a terminal's
# input() prompts. LOCAL USE ONLY: the browser window opens on
# whatever machine is running this server process, so on a hosted
# deployment (Render/Rancher) nobody could see or click it - use
# the cookies.json file upload there instead.
_login_state = {"active": False}
_login_playwright = None
_login_browser = None
_login_context = None


# ==================================================
# Flask-style flash messages, backed by the signed
# session cookie (SessionMiddleware) instead of Flask's
# server-side session dict.
# ==================================================

def flash(request: Request, message: str):
    request.session.setdefault("_flashes", []).append(message)


def render(request: Request, name: str, **context):

    context.setdefault("session", request.session)
    context.setdefault(
        "get_flashed_messages",
        lambda: request.session.pop("_flashes", []),
    )
    context.setdefault(
        "url_for",
        lambda route_name, **params: str(request.url_for(route_name, **params)),
    )

    return templates.TemplateResponse(request, name, context)


def redirect_to(request: Request, route_name: str, **params):
    # 303 (not FastAPI's default 307) so browsers turn the POST
    # that triggered this into a GET, matching Flask's redirect()
    # behaviour after a form submit.
    return RedirectResponse(
        url=request.url_for(route_name, **params),
        status_code=303,
    )


# ==================================================
# Auth (single shared password via APP_PASSWORD env var)
# ==================================================

class NotAuthenticated(Exception):
    pass


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return redirect_to(request, "login")


def login_required(request: Request):

    if not request.session.get("authed"):
        raise NotAuthenticated()


@app.get("/login", name="login")
async def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login", name="login")
async def login_submit(request: Request, password: str = Form("")):

    expected = os.environ.get("APP_PASSWORD", "")

    if not expected:
        # No password configured. Allowed so local testing isn't
        # blocked, but this should never be the case on a public
        # deploy - see README.
        request.session["authed"] = True
        flash(
            request,
            "APP_PASSWORD is not set on this server - running "
            "with NO login protection. Set it in your Kubernetes "
            "Secret / environment variables.",
        )
        return redirect_to(request, "dashboard")

    if password == expected:
        request.session["authed"] = True
        return redirect_to(request, "dashboard")

    flash(request, "Incorrect password.")
    return render(request, "login.html")


@app.post("/logout", name="logout")
async def logout(request: Request):
    request.session.clear()
    return redirect_to(request, "login")


# ==================================================
# Job state helpers (single job at a time, on disk so
# it survives across requests/worker restarts)
# ==================================================

def load_job_meta():

    if not os.path.exists(JOB_META_PATH):
        return None

    try:
        with open(JOB_META_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_job_meta(meta):

    with open(JOB_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ==================================================
# Re-implementations of main.py's ask_country_filter() /
# pending-row logic, minus the input() prompt - same
# normalize_text/expand_country_alias rules, just sourced
# from a form field instead of stdin.
# ==================================================

def compute_country_filter(country_input):

    country_input = (country_input or "").strip()

    if not country_input:
        return None

    wanted = {
        expand_country_alias(normalize_text(c))
        for c in country_input.split(",")
        if c.strip()
    }

    wanted.discard("")

    if not wanted:
        return None

    return sorted(wanted)


def _country_row_matches(value, wanted_countries):

    normalized = expand_country_alias(normalize_text(str(value)))

    if not normalized:
        return True

    return normalized in wanted_countries


def compute_pending_mask(data, filter_countries):

    pending = (
        data["Validation 2"].isna()
        | (data["Validation 2"].astype(str).str.strip() == "")
    )

    if filter_countries:
        wanted = set(filter_countries)
        country_mask = data.get("Country", "").apply(
            lambda v: _country_row_matches(v, wanted)
        )
        pending = pending & country_mask

    return pending


# ==================================================
# Routes
# ==================================================

def enrichment_labels(enrichment_fields):

    labels = {"industry": "industry", "emp_size": "company size", "revenue": "revenue"}
    chosen = [labels[k] for k in labels if (enrichment_fields or {}).get(k)]

    return ", ".join(chosen) if chosen else "none"


@app.get("/", name="dashboard")
async def dashboard(request: Request, _auth: None = Depends(login_required)):

    meta = load_job_meta()

    return render(
        request,
        "dashboard.html",
        meta=meta,
        has_cookies=os.path.exists(COOKIES_PATH),
        login_pending=_login_state["active"],
        max_experience_years=getattr(config, "MAX_EXPERIENCE_YEARS", None),
        daily_lead_limit=getattr(config, "DAILY_LEAD_LIMIT", 90),
        enrichment_labels=enrichment_labels,
    )


@app.post("/start", name="start_job")
async def start_job(
    request: Request,
    excel_file: UploadFile = File(...),
    sheet_name: str = Form(""),
    cookies_file: Optional[UploadFile] = File(None),
    max_experience_years: str = Form(""),
    daily_limit: str = Form(""),
    country_filter: str = Form(""),
    batch_size: str = Form("3"),
    enrich_industry: Optional[str] = Form(None),
    enrich_emp_size: Optional[str] = Form(None),
    enrich_revenue: Optional[str] = Form(None),
    _auth: None = Depends(login_required),
):

    sheet_name = sheet_name.strip()
    max_exp_input = max_experience_years.strip()
    daily_limit_input = daily_limit.strip()
    country_input = country_filter.strip()
    batch_size_input = batch_size.strip()

    enrichment_fields = {
        "industry": bool(enrich_industry),
        "emp_size": bool(enrich_emp_size),
        "revenue": bool(enrich_revenue),
    }

    if not excel_file or not excel_file.filename:
        flash(request, "Please choose an Excel file to upload.")
        return redirect_to(request, "dashboard")

    if cookies_file and cookies_file.filename:
        with open(COOKIES_PATH, "wb") as f:
            f.write(await cookies_file.read())
    elif not os.path.exists(COOKIES_PATH):
        flash(
            request,
            "Please upload your LinkedIn cookies.json - no saved "
            "session was found on the server yet.",
        )
        return redirect_to(request, "dashboard")

    upload_ext = os.path.splitext(excel_file.filename)[1] or ".xlsx"
    upload_path = os.path.join(DATA_DIR, "upload_original" + upload_ext)
    with open(upload_path, "wb") as f:
        f.write(await excel_file.read())

    # Sheet name only needs to come from the form when the file
    # actually HAS more than one tab - most calling sheets are a
    # single tab, and making everyone type the exact tab name for
    # those was pure friction. Single-tab files are auto-detected;
    # only a genuinely multi-tab upload (with no sheet_name typed,
    # or one that doesn't match any tab in THIS file) stops here to
    # ask which one to use.
    try:
        available_sheets = list_sheet_names(upload_path)
    except Exception as e:
        flash(request, f"Excel read error: {e}")
        return redirect_to(request, "dashboard")

    if sheet_name:
        if sheet_name not in available_sheets:
            case_insensitive_match = next(
                (s for s in available_sheets if s.lower() == sheet_name.lower()),
                None,
            )
            if case_insensitive_match:
                sheet_name = case_insensitive_match
            else:
                flash(
                    request,
                    f"No sheet named \"{sheet_name}\" in this file. "
                    f"Available sheets: {', '.join(available_sheets)}",
                )
                return redirect_to(request, "dashboard")
    elif len(available_sheets) == 1:
        sheet_name = available_sheets[0]
    else:
        flash(
            request,
            "This file has more than one sheet - enter which one to "
            f"use. Available sheets: {', '.join(available_sheets)}",
        )
        return redirect_to(request, "dashboard")

    try:
        data = read_excel(upload_path, sheet_name)
    except Exception as e:
        flash(request, f"Excel read error: {e}")
        return redirect_to(request, "dashboard")

    if "Validation 2" not in data.columns:
        data["Validation 2"] = ""

    for col in ("Industry", "Company Size", "Company Members", "Company LinkedIn URL", "Revenue"):
        if col not in data.columns:
            data[col] = ""

    # Same semantics as ask_experience_years(): blank = keep
    # config's current default, "0" = disable, else override.
    if max_exp_input:
        try:
            years = float(max_exp_input)
            config.MAX_EXPERIENCE_YEARS = None if years == 0 else years
        except ValueError:
            pass

    # Same semantics as ask_linkedin_limit().
    if daily_limit_input:
        try:
            limit = int(daily_limit_input)
            if limit > 0:
                config.DAILY_LEAD_LIMIT = limit
        except ValueError:
            pass

    filter_countries = compute_country_filter(country_input)

    try:
        batch_size_val = max(1, min(int(batch_size_input), 15))
    except ValueError:
        batch_size_val = 3

    save_excel(data, CURRENT_XLSX)

    meta = {
        "original_filename": excel_file.filename,
        "sheet_name": WORKING_SHEET_NAME,
        "total_contacts": len(data),
        "filter_countries": filter_countries,
        "enrichment_fields": enrichment_fields,
        "batch_size": batch_size_val,
        "cookie_label": (
            cookies_file.filename
            if (cookies_file and cookies_file.filename)
            else "(reused previously uploaded cookies)"
        ),
        "used_today": load_usage(COOKIES_PATH),
        "daily_limit": getattr(config, "DAILY_LEAD_LIMIT", 90),
        "max_experience_years": getattr(config, "MAX_EXPERIENCE_YEARS", None),
        "status": "in_progress",
        "total_processed": 0,
        "last_batch_summary": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    save_job_meta(meta)

    flash(request, "Job started. Click \"Start Validation\" once - it will keep going on its own.")
    return redirect_to(request, "dashboard")


# Plain `def` (not `async def`): this handler drives the real
# Playwright browser synchronously for the whole batch (tens of
# seconds), so FastAPI runs it in its worker threadpool instead of
# blocking the single asyncio event loop other requests share.
@app.post("/run-batch", name="run_batch")
def run_batch(request: Request, _auth: None = Depends(login_required)):

    if not _batch_lock.acquire(blocking=False):
        flash(request, "A batch or LinkedIn login is already running - wait for it to finish.")
        return redirect_to(request, "dashboard")

    try:
        return _run_batch(request)
    finally:
        _batch_lock.release()


def _run_batch(request: Request):

    meta = load_job_meta()

    if not meta:
        flash(request, "No job in progress - start a new one first.")
        return redirect_to(request, "dashboard")

    if meta.get("status") == "completed":
        flash(request, "This job is already complete - download it below, or start a new one.")
        return redirect_to(request, "dashboard")

    if not os.path.exists(COOKIES_PATH):
        flash(request, "No cookies.json on file - upload one to continue.")
        return redirect_to(request, "dashboard")

    try:
        data = read_excel(CURRENT_XLSX, meta["sheet_name"])
    except Exception as e:
        flash(request, f"Could not reload the working file: {e}")
        return redirect_to(request, "dashboard")

    pending_mask = compute_pending_mask(data, meta.get("filter_countries"))
    pending_indices = list(data.index[pending_mask])

    if not pending_indices:
        meta["status"] = "completed"
        meta["updated_at"] = now_iso()
        save_job_meta(meta)
        flash(request, "All contacts processed! Download your file below.")
        return redirect_to(request, "dashboard")

    batch_indices = pending_indices[: meta["batch_size"]]

    # A stop request left over from a click with no batch actually
    # running (e.g. between auto-run reloads) would otherwise abort
    # this brand-new batch before it processes a single row. Any
    # stop meant for a batch that's already running gets set AFTER
    # this point instead, once that batch's loop below is underway,
    # so clearing here can't swallow a genuine in-flight stop.
    _stop_event.clear()

    used_today = meta.get("used_today", 0)
    daily_limit = meta.get("daily_limit")
    enrichment_fields = meta.get("enrichment_fields")
    filter_countries = meta.get("filter_countries")

    company_cache = {}
    batch_log = []
    stop_reason = None

    try:
        start_browser(cookie_file=COOKIES_PATH)
    except Exception as e:
        flash(request, f"Browser start error: {e}")
        return redirect_to(request, "dashboard")

    try:

        for index in batch_indices:

            if _stop_event.is_set():
                _stop_event.clear()
                stop_reason = "stopped_by_user"
                break

            row = data.loc[index]

            url = str(row.get("Linkedin URL", "")).strip()
            excel_job = str(row.get("Job Title", "")).strip()
            excel_country = str(row.get("Country", "")).strip()
            excel_name = (
                str(row.get("First Name", "")) + " " + str(row.get("Last Name", ""))
            ).strip()

            # Same daily-limit gate as main.py's sequential loop.
            if (
                url and url.lower() != "nan"
                and daily_limit
                and used_today >= daily_limit
            ):
                stop_reason = "daily_limit"
                break

            try:
                result, linkedin_data = lookup_linkedin_data(
                    row,
                    url,
                    excel_job,
                    scraped_results=None,
                    page=get_page(),
                    threaded=False,
                    company_cache=company_cache,
                    filter_countries=filter_countries,
                    enrichment_fields=enrichment_fields,
                )
            except SessionExpiredError:
                stop_reason = "session_expired"
                break

            used_today += 1
            save_usage(COOKIES_PATH, used_today)

            # ---- Same column writes as main.py's sequential loop ----

            data.at[index, "Validation 2"] = result

            if not excel_country and linkedin_data.get("country"):
                data.at[index, "Country"] = linkedin_data["country"]

            if "JOB TITLE" not in result and linkedin_data.get("job_title"):
                data.at[index, "Job Title"] = linkedin_data["job_title"]

            final_url = linkedin_data.get("final_url", "")
            if result == "VALID" and final_url and final_url != url:
                data.at[index, "Linkedin URL"] = final_url

            if result == "VALID":

                ef = enrichment_fields or {
                    "industry": True, "emp_size": True, "revenue": True
                }

                if ef.get("industry", True):
                    data.at[index, "Industry"] = linkedin_data.get("industry", "")

                if ef.get("emp_size", True):
                    data.at[index, "Company Size"] = linkedin_data.get("company_size_range", "")
                    data.at[index, "Company Members"] = linkedin_data.get("company_size_members", "")

                if ef.get("industry", True) or ef.get("emp_size", True):
                    data.at[index, "Company LinkedIn URL"] = linkedin_data.get("company_linkedin_url", "")

                if ef.get("revenue", True):
                    data.at[index, "Revenue"] = linkedin_data.get("revenue", "")

            batch_log.append({
                "row": int(index) + 1,
                "name": excel_name or linkedin_data.get("full_name", ""),
                "result": result,
            })

    finally:

        try:
            close_browser()
        except Exception:
            pass

    save_excel(data, CURRENT_XLSX)

    processed_mask = ~(
        data["Validation 2"].isna()
        | (data["Validation 2"].astype(str).str.strip() == "")
    )

    meta["used_today"] = used_today
    meta["last_batch_summary"] = batch_log
    meta["total_processed"] = int(processed_mask.sum())
    meta["updated_at"] = now_iso()

    if stop_reason == "daily_limit":
        meta["status"] = "daily_limit_reached"
        flash(
            request,
            f"Daily LinkedIn limit ({daily_limit}) reached for this "
            f"account. Upload another account's cookies.json below "
            f"to keep going.",
        )
    elif stop_reason == "session_expired":
        meta["status"] = "session_expired"
        flash(
            request,
            "LinkedIn session expired (hit the login wall). Upload "
            "a fresh cookies.json below to keep going.",
        )
    elif stop_reason == "stopped_by_user":
        meta["status"] = "stopped"
        flash(
            request,
            f"Validation stopped. {len(batch_log)} contact(s) in this "
            f"batch were already validated and saved - download below, "
            f"or click \"Start Validation\" to continue with the rest.",
        )
    else:
        meta["status"] = "in_progress"
        flash(request, f"Processed {len(batch_log)} contact(s) this batch.")

    save_job_meta(meta)
    return redirect_to(request, "dashboard")


@app.post("/stop-validation", name="stop_validation")
async def stop_validation(request: Request, _auth: None = Depends(login_required)):
    # `async def`, deliberately not `def` (threadpool) - this must be
    # handled immediately even while /run-batch is occupying the
    # threadpool with a running batch. It only sets a flag; the
    # actual stop happens in _run_batch's loop, between rows.
    _stop_event.set()
    flash(
        request,
        "Stop requested - finishing the lead currently in progress, "
        "then saving and stopping.",
    )
    return redirect_to(request, "dashboard")


def _mark_cookies_refreshed(cookie_label):
    # Shared by /update-cookies and /login-linkedin/finish - both
    # end with a fresh cookies.json already written to COOKIES_PATH.

    meta = load_job_meta()

    if meta:
        meta["cookie_label"] = cookie_label
        meta["used_today"] = load_usage(COOKIES_PATH)

        if meta.get("status") in ("daily_limit_reached", "session_expired"):
            meta["status"] = "in_progress"

        meta["updated_at"] = now_iso()
        save_job_meta(meta)


@app.post("/update-cookies", name="update_cookies")
async def update_cookies(
    request: Request,
    cookies_file: Optional[UploadFile] = File(None),
    _auth: None = Depends(login_required),
):

    if not cookies_file or not cookies_file.filename:
        flash(request, "Choose a cookies.json file to upload.")
        return redirect_to(request, "dashboard")

    with open(COOKIES_PATH, "wb") as f:
        f.write(await cookies_file.read())

    _mark_cookies_refreshed(cookies_file.filename)

    flash(request, "Cookies updated. Click \"Start Validation\" to resume.")
    return redirect_to(request, "dashboard")


# ==================================================
# "Log in to LinkedIn" button - runs the same flow as login.py (a
# real, visible browser window you log into by hand) from the
# dashboard instead of a terminal. LOCAL USE ONLY - see the
# _login_state comment near the top of this file.
# ==================================================

@app.post("/login-linkedin/start", name="login_linkedin_start")
def login_linkedin_start(request: Request, _auth: None = Depends(login_required)):

    global _login_playwright, _login_browser, _login_context

    if _login_state["active"]:
        flash(request, "A LinkedIn login window is already open - finish or cancel it below.")
        return redirect_to(request, "dashboard")

    if not _batch_lock.acquire(blocking=False):
        flash(request, "A batch is currently running - wait for it to finish first.")
        return redirect_to(request, "dashboard")

    try:
        _login_playwright = sync_playwright().start()
        _login_browser = _login_playwright.chromium.launch(headless=False)
        _login_context = _login_browser.new_context()
        page = _login_context.new_page()
        page.goto("https://www.linkedin.com/login")
    except Exception as e:
        _close_login_browser()
        _batch_lock.release()
        print("login-linkedin/start failed:", repr(e))
        flash(request, f"Could not open the LinkedIn login window: {type(e).__name__}: {e}")
        return redirect_to(request, "dashboard")

    # Lock stays held until /login-linkedin/finish or /cancel - see
    # the _batch_lock comment near the top of this file.
    _login_state["active"] = True

    flash(
        request,
        "A LinkedIn login window opened on this machine. Log in "
        "there, then come back and click \"I've logged in - save "
        "cookies\" below.",
    )
    return redirect_to(request, "dashboard")


def _close_login_browser():

    global _login_playwright, _login_browser, _login_context

    for obj, label in (
        (_login_context, "context"),
        (_login_browser, "browser"),
        (_login_playwright, "playwright"),
    ):
        try:
            if obj:
                (obj.stop if label == "playwright" else obj.close)()
        except Exception:
            pass

    _login_playwright = None
    _login_browser = None
    _login_context = None


@app.post("/login-linkedin/finish", name="login_linkedin_finish")
def login_linkedin_finish(request: Request, _auth: None = Depends(login_required)):

    if not _login_state["active"]:
        flash(request, "No LinkedIn login is in progress.")
        return redirect_to(request, "dashboard")

    try:
        _login_context.storage_state(path=COOKIES_PATH)
        flash(request, "cookies.json saved. Click \"Start Validation\" to resume.")
        _mark_cookies_refreshed("(saved via Log in to LinkedIn)")
    except Exception as e:
        flash(request, f"Could not save cookies - the login window may have been closed already: {e}")
    finally:
        _close_login_browser()
        _login_state["active"] = False
        _batch_lock.release()

    return redirect_to(request, "dashboard")


@app.post("/login-linkedin/cancel", name="login_linkedin_cancel")
def login_linkedin_cancel(request: Request, _auth: None = Depends(login_required)):

    if not _login_state["active"]:
        return redirect_to(request, "dashboard")

    _close_login_browser()
    _login_state["active"] = False
    _batch_lock.release()

    flash(request, "LinkedIn login cancelled.")
    return redirect_to(request, "dashboard")


@app.get("/download", name="download")
async def download(request: Request, _auth: None = Depends(login_required)):

    if not os.path.exists(CURRENT_XLSX):
        flash(request, "No output file yet - start a job first.")
        return redirect_to(request, "dashboard")

    meta = load_job_meta() or {}
    base = os.path.splitext(meta.get("original_filename", "output.xlsx"))[0]

    return FileResponse(
        CURRENT_XLSX,
        filename=f"{base}_validated.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/reset", name="reset_job")
async def reset_job(request: Request, _auth: None = Depends(login_required)):

    for path in (JOB_META_PATH, CURRENT_XLSX):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    flash(request, "Job cleared - start a new one whenever you're ready.")
    return redirect_to(request, "dashboard")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    # Liveness/readiness probe target for Kubernetes/Rancher - see
    # k8s/deployment.yaml. Doesn't touch auth or job state.
    return {"status": "ok"}


if __name__ == "__main__":
    # Local dev only - the container runs this via uvicorn (see
    # Dockerfile).
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )
