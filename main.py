import threading
import queue
import os
import json
import datetime

from config import (
    FILE_NAME,
    SHEET_NAME,
    OUTPUT_FILE,
    SCRAPER_MODE
)

import config

from excel_handler import (
    read_excel,
    save_excel
)

from validator import (
    validate_lead,
    normalize_text,
    expand_country_alias
)


# ==================================================
# Scraper backend (chosen via config.SCRAPER_MODE)
# ==================================================

if SCRAPER_MODE == "apify":

    from linkedin_scraper.apify_scraper import (
        get_linkedin_details_batch,
        lookup_result
    )

else:

    from linkedin_scraper.browser import (
        start_browser,
        close_browser,
        launch_worker_browser,
        close_worker_browser,
        logout_linkedin,
        get_page,
        SessionExpiredError
    )

    from linkedin_scraper.scraper import (
        get_linkedin_details,
        get_company_details
    )


# ==================================================
# Daily LinkedIn Lead Limit
#
# Only relevant for SCRAPER_MODE = "playwright" (a real logged-in
# LinkedIn session, real rate-limit/ban risk). Tracks how many
# leads have been checked TODAY per LinkedIn account (cookies
# file) in a small JSON file, so the limit holds even across
# separate re-runs of main.py on the same day. Once an account
# hits the limit, it gets logged out of LinkedIn and the user is
# asked for another account's cookies file to keep going.
# ==================================================

def usage_file_path():

    return getattr(
        config,
        "USAGE_TRACK_FILE",
        "linkedin_usage.json"
    )


def load_usage(cookie_file):

    path = usage_file_path()

    if not os.path.exists(path):
        return 0

    try:

        with open(path, "r") as f:
            data = json.load(f)

    except Exception:

        return 0

    today = str(datetime.date.today())

    entry = data.get(cookie_file, {})

    if entry.get("date") != today:
        return 0

    return entry.get("count", 0)


def save_usage(cookie_file, count):

    path = usage_file_path()

    data = {}

    if os.path.exists(path):

        try:

            with open(path, "r") as f:
                data = json.load(f)

        except Exception:

            data = {}

    data[cookie_file] = {
        "date": str(datetime.date.today()),
        "count": count
    }

    try:

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:

        print("Usage tracking save error:", e)


def ask_next_linkedin_account(current_cookie_file):

    limit = getattr(config, "DAILY_LEAD_LIMIT", 90)

    print(
        f"\nDaily limit of {limit} leads reached for this LinkedIn "
        f"account ({current_cookie_file})."
    )

    next_file = input(
        "Enter the path to ANOTHER LinkedIn account's cookies file "
        "to keep going today (or press ENTER to stop here): "
    ).strip()

    if not next_file:

        print("\nStopping for today - daily limit reached.")
        return None

    if not os.path.exists(next_file):

        print(
            f"\nFile not found: {next_file}. Stopping for today."
        )
        return None

    return next_file


def logout_account(cookie_file):

    """
    Logs an account out of LinkedIn by opening a quick throwaway
    browser with that account's saved cookies, hitting the logout
    URL, then closing it. Used whenever the daily lead limit is
    hit for that account.
    """

    print(f"\nLogging out LinkedIn account: {cookie_file}")

    try:

        pw, br, ctx, pg = launch_worker_browser(cookie_file)

        logout_linkedin(pg)

        close_worker_browser(pw, br, ctx, pg)

    except Exception as e:

        print("Account logout error (continuing anyway):", e)


# ==================================================
# Helpers shared by the sequential and threaded paths
# ==================================================

def empty_linkedin_data():

    return {
        "full_name": "",
        "job_title": "",
        "company_name": "",
        "country": "",
        "current_employee": False,
        "employment_flags": [],
        "open_to_flags": [],
        "final_url": "",
        "company_linkedin_url": "",
        "industry": "",
        "company_size_range": "",
        "company_size_members": "",
        "revenue": "",
        "job_start_date": None
    }


def lookup_linkedin_data(row, url, excel_job, scraped_results, page, threaded, company_cache=None, company_cache_lock=None, filter_countries=None, enrichment_fields=None):

    """
    Fetches + validates LinkedIn data for one row.
    Returns (result_string, linkedin_data).
    `page` is only used in playwright mode; ignored for apify.
    `threaded` controls whether scraper errors are raised back
    to the caller (True, multi-tab mode - caller owns page
    recovery) or swallowed internally (False, old single-tab
    behavior).
    `enrichment_fields` is a dict {"industry":bool, "emp_size":bool,
    "revenue":bool} controlling which of those get fetched/written
    for VALID leads - defaults to all True if not given.
    """

    if enrichment_fields is None:
        enrichment_fields = {"industry": True, "emp_size": True, "revenue": True}

    if not url or url.lower() == "nan":

        return "NO LINKEDIN", empty_linkedin_data()

    try:

        if SCRAPER_MODE == "apify":

            linkedin_data = lookup_result(
                scraped_results,
                url
            )

        else:

            linkedin_data = get_linkedin_details(
                url,
                excel_job,
                page=page,
                raise_errors=threaded
            )

        result = validate_lead(
            row,
            linkedin_data,
            filter_countries
        )

        # For VALID leads in playwright mode, open the company
        # About page and pull industry + company size details.
        # If multiple leads share the same company URL, reuse
        # the cached result instead of re-opening the page.
        want_industry = enrichment_fields.get("industry", True)
        want_emp_size = enrichment_fields.get("emp_size", True)
        want_revenue = enrichment_fields.get("revenue", True)

        if (
            result == "VALID"
            and SCRAPER_MODE != "apify"
            and page is not None
            and (want_industry or want_emp_size or want_revenue)
        ):
            company_url = linkedin_data.get("company_linkedin_url", "")
            company_name_for_lookup = linkedin_data.get("company_name", "")

            # Revenue (via ZoomInfo/Google) only needs a company
            # NAME, not a LinkedIn company URL - so still run this
            # block when the URL is missing but a name was parsed
            # (e.g. Travis Neal-style profiles with an unlinked
            # company logo). Cache key falls back to the name in
            # that case so different no-URL companies don't collide.
            need_something = (
                ((want_industry or want_emp_size) and company_url)
                or (want_revenue and company_name_for_lookup)
            )

            if need_something:

                cache_key = company_url or ("name:" + company_name_for_lookup.lower())

                cached_details = None

                if company_cache is not None:
                    if company_cache_lock is not None:
                        with company_cache_lock:
                            cached_details = company_cache.get(cache_key)
                    else:
                        cached_details = company_cache.get(cache_key)

                if cached_details is not None:
                    print(f"\nUsing cached company details for: {cache_key}")
                    linkedin_data.update(cached_details)

                else:

                    try:

                        company_details = get_company_details(
                            company_url,
                            page,
                            company_name=company_name_for_lookup,
                            want_industry=want_industry,
                            want_emp_size=want_emp_size,
                            want_revenue=want_revenue
                        )

                        linkedin_data.update(company_details)

                        if company_cache is not None:
                            if company_cache_lock is not None:
                                with company_cache_lock:
                                    company_cache[cache_key] = company_details
                            else:
                                company_cache[cache_key] = company_details

                    except Exception as ce:

                        print("Company details error (continuing):", ce)

        return result, linkedin_data

    except SessionExpiredError:

        # Don't swallow this into a generic "SCRAPING ERROR" -
        # the caller needs to know the session itself died (not
        # just this one lead) so it can stop reusing these dead
        # cookies instead of producing the same blank result for
        # every remaining contact.
        raise

    except Exception as e:

        print("LinkedIn Lookup Error:", e)

        return "SCRAPING ERROR", empty_linkedin_data()


# ==================================================
# Threaded Playwright Path (multiple parallel tabs)
#
# Each worker thread creates and owns its OWN Playwright
# instance/browser/context/page for its entire lifetime and
# pulls rows from a shared queue. This is required because
# Playwright's sync API is tied to whichever thread called
# sync_playwright().start() - a page created on one thread
# cannot be safely driven (goto, etc.) from another thread.
# Sharing one browser/context across threads (the old
# approach) caused "greenlet.error: cannot switch to a
# different thread" and almost every navigation failing with
# net::ERR_ABORTED, which is what produced the all-invalid
# run.
# ==================================================

def run_threaded_batch(data, batch_indices, cookie_file, usage_state, filter_countries=None, enrichment_fields=None):

    """
    Runs the multi-tab worker pool over exactly `batch_indices`
    (already sized to not exceed this account's remaining daily
    capacity), using `cookie_file` for every worker's browser.
    `usage_state` is a shared {"count": N} dict that gets bumped
    and persisted to disk after every contact, so the daily count
    survives even if the run is interrupted.
    """

    worker_count = config.PLAYWRIGHT_WORKERS

    print(
        f"\nUsing {worker_count} parallel browser tabs "
        f"(LinkedIn account: {cookie_file})..."
    )

    work_queue = queue.Queue()

    for index in batch_indices:
        work_queue.put((index, data.loc[index]))

    total_pending = work_queue.qsize()

    lock = threading.Lock()
    progress = {"done": 0}
    save_lock_failed = {"flag": False}

    # Set as soon as ANY worker discovers this LinkedIn account's
    # session has died (hit the authwall). Once set, every worker
    # stops pulling new rows from the queue instead of continuing
    # to scrape with dead cookies - that's what previously produced
    # long runs of identical blank "Join LinkedIn" results across
    # many different contacts after the session expired partway
    # through a batch.
    session_dead = threading.Event()

    # Shared cache: company LinkedIn URL → company details dict.
    # Prevents re-opening the same company About page when multiple
    # leads belong to the same company.
    company_cache = {}
    company_cache_lock = threading.Lock()


    def worker(worker_id):

        # Each worker thread gets its own independent browser
        # stack - created here, on this thread, and never
        # touched by any other thread.

        try:
            pw, br, ctx, page = launch_worker_browser(cookie_file)
        except Exception as e:
            print(f"[Worker {worker_id}] failed to launch browser:", e)
            return

        try:

            while True:

                if session_dead.is_set():
                    # Another worker already found this account's
                    # session is dead - stop immediately and leave
                    # whatever's still in the queue for the next
                    # account to pick up.
                    return

                try:
                    index, row = work_queue.get_nowait()
                except queue.Empty:
                    return

                excel_job = str(
                    row.get("Job Title", "")
                ).strip()

                url = str(
                    row.get("Linkedin URL", "")
                ).strip()

                try:

                    result, linkedin_data = lookup_linkedin_data(
                        row,
                        url,
                        excel_job,
                        None,
                        page,
                        True,
                        company_cache,
                        company_cache_lock,
                        filter_countries,
                        enrichment_fields
                    )

                except SessionExpiredError as e:

                    # The session itself is dead, not just this
                    # one row. Put this row back so a future
                    # account/run still picks it up, signal every
                    # other worker to stop, and end this worker
                    # without writing any (garbage) result for it.

                    print(
                        f"[Worker {worker_id}] LinkedIn session "
                        f"expired - stopping this batch and "
                        f"requeueing remaining work:",
                        e
                    )

                    work_queue.put((index, row))
                    session_dead.set()
                    work_queue.task_done()
                    return

                except Exception as e:

                    # This worker's page likely crashed/closed.
                    # Recreate a fresh page on THIS SAME thread
                    # and mark this row as a scraping error so
                    # the run keeps going.

                    print(
                        f"[Worker {worker_id}] page error, recreating tab:",
                        e
                    )

                    try:
                        page.close()
                    except Exception:
                        pass

                    try:
                        page = ctx.new_page()
                        page.set_default_timeout(60000)
                    except Exception as recreate_err:
                        print(
                            f"[Worker {worker_id}] tab recreation failed:",
                            recreate_err
                        )

                    result, linkedin_data = "SCRAPING ERROR", empty_linkedin_data()

                with lock:

                    data.at[index, "Validation 2"] = result

                    # Calling sheet didn't supply a country for
                    # this row - backfill it from whatever
                    # LinkedIn showed instead of leaving it blank
                    # in the output (validator.py already treats
                    # a blank sheet country as "nothing to
                    # compare", not a mismatch, so this is purely
                    # filling in missing data).
                    if (
                        not str(row.get("Country", "")).strip()
                        and linkedin_data.get("country")
                    ):
                        data.at[index, "Country"] = (
                            linkedin_data["country"]
                        )

                    # Job title matched (after symbol/stopword
                    # cleanup) between the calling sheet and
                    # LinkedIn - rewrite the sheet's short/older
                    # wording with LinkedIn's actual current title
                    # so the output shows the up-to-date version,
                    # per request.
                    if (
                        "JOB TITLE" not in result
                        and linkedin_data.get("job_title")
                    ):
                        data.at[index, "Job Title"] = (
                            linkedin_data["job_title"]
                        )

                    # Update LinkedIn URL with the final canonical
                    # URL (after any redirects) for valid leads.
                    final_url = linkedin_data.get("final_url", "")
                    if (
                        result == "VALID"
                        and final_url
                        and final_url != url
                    ):
                        data.at[index, "Linkedin URL"] = final_url

                    # Write company About page data for valid leads -
                    # only the columns actually asked for via
                    # ask_enrichment_fields(). "Company LinkedIn URL"
                    # is written whenever either industry or emp size
                    # was requested, since it's how that data was
                    # found in the first place.
                    if result == "VALID":

                        ef = enrichment_fields or {
                            "industry": True, "emp_size": True, "revenue": True
                        }

                        if ef.get("industry", True):
                            data.at[index, "Industry"] = (
                                linkedin_data.get("industry", "")
                            )

                        if ef.get("emp_size", True):
                            data.at[index, "Company Size"] = (
                                linkedin_data.get("company_size_range", "")
                            )
                            data.at[index, "Company Members"] = (
                                linkedin_data.get("company_size_members", "")
                            )

                        if ef.get("industry", True) or ef.get("emp_size", True):
                            data.at[index, "Company LinkedIn URL"] = (
                                linkedin_data.get("company_linkedin_url", "")
                            )

                        if ef.get("revenue", True):
                            data.at[index, "Revenue"] = (
                                linkedin_data.get("revenue", "")
                            )

                    progress["done"] += 1

                    # Only count rows that actually consumed a
                    # LinkedIn pageview against today's limit (a
                    # missing URL never touched LinkedIn at all).
                    if url and url.lower() != "nan":

                        usage_state["count"] += 1
                        save_usage(cookie_file, usage_state["count"])

                    print(
                        f"[{progress['done']}/{total_pending}] "
                        f"Contact {index + 1}: {result} "
                        f"(today: {usage_state['count']})"
                    )

                    if progress["done"] % 25 == 0 and not save_lock_failed["flag"]:

                        print("\nSaving Progress...")

                        try:

                            save_excel(data, OUTPUT_FILE)

                            print("Progress Saved Successfully")

                        except PermissionError:

                            print(
                                "\nOutput file is open - skipping this "
                                "autosave. Close Excel to allow autosave."
                            )

                            save_lock_failed["flag"] = True

                work_queue.task_done()

        finally:

            close_worker_browser(pw, br, ctx, page)


    threads = []

    for i in range(worker_count):

        t = threading.Thread(
            target=worker,
            args=(i,),
            daemon=True
        )

        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # Anything still sitting in the queue means the session died
    # before all of `batch_indices` got processed (or, in the
    # ordinary case, the queue is simply empty). Hand the leftover
    # indices back to the caller so they can be retried under a
    # different account instead of being silently dropped.
    leftover_indices = []

    while True:
        try:
            index, _row = work_queue.get_nowait()
            leftover_indices.append(index)
        except queue.Empty:
            break

    return session_dead.is_set(), leftover_indices


def run_threaded_playwright(data, total_contacts, pending_mask, filter_countries=None, enrichment_fields=None):

    cookie_file = config.COOKIE_FILE

    daily_limit = getattr(config, "DAILY_LEAD_LIMIT", None)

    remaining_indices = list(data[pending_mask].index)

    stopped_early = False

    while remaining_indices:

        used_today = load_usage(cookie_file)

        if daily_limit and used_today >= daily_limit:

            # Already at/over the limit before doing any work
            # with this account this round (e.g. re-running
            # main.py later the same day) - log it out and ask
            # for another account straight away.

            logout_account(cookie_file)

            next_file = ask_next_linkedin_account(cookie_file)

            if not next_file:
                stopped_early = True
                break

            cookie_file = next_file
            continue

        capacity = (
            (daily_limit - used_today)
            if daily_limit
            else len(remaining_indices)
        )

        batch_indices = remaining_indices[:capacity]
        remaining_indices = remaining_indices[len(batch_indices):]

        usage_state = {"count": used_today}

        session_died, leftover_indices = run_threaded_batch(
            data,
            batch_indices,
            cookie_file,
            usage_state,
            filter_countries,
            enrichment_fields
        )

        # Anything left in the queue (normally only happens when
        # the session died mid-batch) needs to be retried under
        # whichever account we end up using next - put it back at
        # the front of the line.
        if leftover_indices:
            remaining_indices = leftover_indices + remaining_indices

        if session_died:

            print(
                f"\nLinkedIn account ({cookie_file}) got logged out "
                f"mid-run (hit the authwall) - rotating to a "
                f"different account instead of continuing with a "
                f"dead session."
            )

            logout_account(cookie_file)

            next_file = ask_next_linkedin_account(cookie_file)

            if not next_file:
                stopped_early = True
                break

            cookie_file = next_file
            continue

        if remaining_indices:

            # This account's batch is exhausted but more contacts
            # are still pending - the daily limit was hit. Log out
            # of LinkedIn and ask for another account.

            logout_account(cookie_file)

            next_file = ask_next_linkedin_account(cookie_file)

            if not next_file:
                stopped_early = True
                break

            cookie_file = next_file


    print("\nFinal Saving...")

    while True:

        try:

            save_excel(data, OUTPUT_FILE)
            break

        except PermissionError:

            input(
                "\nOutput file is open in Excel.\n"
                "Please close the Excel file and press ENTER to retry..."
            )

    print("\n" + "=" * 70)

    if stopped_early:
        print("Lead Validation Stopped - daily LinkedIn limit reached.")
    else:
        print("Lead Validation Completed Successfully!")

    print("Output File:", OUTPUT_FILE)
    print("=" * 70)


# ==================================================
# Country Filter
#
# Asks which country/countries to validate this run.
# Accepts full names ("United States", "India") or
# short/alternate forms ("US", "UK", "in") and any
# number of them, comma-separated. Rows whose Country
# column doesn't match are left untouched this run
# (not marked invalid - just skipped, so a later run
# with a different filter can still pick them up).
# ==================================================

def ask_linkedin_limit():

    current = getattr(config, "DAILY_LEAD_LIMIT", 90)

    user_input = input(
        f"\nEnter daily LinkedIn lead limit per account "
        f"(press ENTER to keep current: {current}): "
    ).strip()

    if not user_input:
        return

    try:
        new_limit = int(user_input)
        if new_limit <= 0:
            raise ValueError
        config.DAILY_LEAD_LIMIT = new_limit
        print(f"Daily lead limit set to {new_limit}.")
    except ValueError:
        print(f"Invalid input - keeping current limit of {current}.")


def ask_experience_years():

    current = getattr(config, "MAX_EXPERIENCE_YEARS", None)

    current_label = (
        f"{current} year(s)" if current is not None else "no filter"
    )

    user_input = input(
        f"\nMax years allowed in latest job title "
        f"(leads OVER this are marked INVALID). "
        f"Press ENTER to keep current ({current_label}), "
        f"or type 0 to disable: "
    ).strip()

    if not user_input:

        if current is not None:
            print(f"Experience filter kept at {current} year(s).")
        else:
            print("No experience filter - all tenures accepted.")

        return

    try:
        years = float(user_input)

        if years == 0:
            config.MAX_EXPERIENCE_YEARS = None
            print("Experience filter disabled - all tenures accepted.")
            return

        if years < 0:
            raise ValueError

        config.MAX_EXPERIENCE_YEARS = years
        print(
            f"Experience filter set: latest job title must be "
            f"<= {years} year(s) (more than that = INVALID)."
        )
    except ValueError:
        print("Invalid input - experience filter not applied.")


def ask_enrichment_fields():
    """
    Ask which extra data to fetch/write for VALID leads: LinkedIn
    Industry, LinkedIn Company/Emp Size, and/or ZoomInfo Revenue.
    Per request: if the user only says yes to Revenue, only the
    Revenue column gets touched - Industry/Company Size stay blank
    rather than being fetched and written anyway. This also skips
    the actual page fetches for anything not selected, so a
    "revenue only" run doesn't waste time opening LinkedIn's About
    page if industry/emp size weren't asked for (and vice versa -
    skips the Google/ZoomInfo lookup entirely if revenue wasn't
    asked for).
    """

    print(
        "\nFor VALID leads, which extra data should be fetched?"
    )
    print(
        "  Options: industry, empsize, revenue "
        "(comma-separated, e.g. \"industry, revenue\")"
    )

    user_input = input(
        "Press ENTER for all three, or type 'none' to skip all: "
    ).strip().lower()

    fields = {
        "industry": True,
        "emp_size": True,
        "revenue": True
    }

    if not user_input:

        print("Fetching Industry, Company/Emp Size, and Revenue for VALID leads.")
        return fields

    if user_input == "none":

        fields = {
            "industry": False,
            "emp_size": False,
            "revenue": False
        }
        print("Skipping Industry/Company Size/Revenue enrichment entirely.")
        return fields

    wanted = {part.strip() for part in user_input.split(",") if part.strip()}

    fields = {
        "industry": "industry" in wanted,
        "emp_size": (
            "empsize" in wanted
            or "emp size" in wanted
            or "emp_size" in wanted
            or "company size" in wanted
        ),
        "revenue": "revenue" in wanted
    }

    chosen = [k for k, v in fields.items() if v] or ["none"]
    print(f"Fetching for VALID leads: {', '.join(chosen)}")

    return fields


def ask_country_filter(data, pending_mask):

    """
    Returns (pending_mask, filter_countries).

    filter_countries is the set of normalized country name(s) the
    user typed here, or None if they left it blank. main.py hangs
    onto this and passes it into validate_lead() as a fallback
    expected country - per the user's request: when the calling
    sheet's own Country cell IS filled in, that value is what gets
    checked against LinkedIn (unchanged). Only when the sheet's
    Country cell is BLANK does the country typed here at the start
    of the run become the expected value, instead of silently
    accepting whatever LinkedIn shows with no check at all.
    """

    country_input = input(
        "\nEnter country name(s) to validate (comma-separated, "
        "full or short name - e.g. 'India, USA, UK').\n"
        "Leave blank to process all countries: "
    ).strip()

    if not country_input:

        print("\nNo country filter - processing all countries.")
        return pending_mask, None

    wanted_countries = {
        expand_country_alias(normalize_text(c))
        for c in country_input.split(",")
        if c.strip()
    }

    wanted_countries.discard("")

    if not wanted_countries:

        print("\nNo valid country given - processing all countries.")
        return pending_mask, None

    def row_country_matches(value):

        normalized = expand_country_alias(
            normalize_text(str(value))
        )

        # The sheet's Country column is blank/unknown for a lot
        # of rows - that's not the same as "wrong country", it's
        # just no data yet. Filtering those out here means they'd
        # NEVER get checked against LinkedIn at all (this filter
        # runs before any scraping happens, so there's no LinkedIn
        # country to compare against yet). Let them through; the
        # real country gets resolved from LinkedIn during
        # scraping and checked properly by the validator
        # afterwards.
        if not normalized:
            return True

        return normalized in wanted_countries

    country_mask = data.get(
        "Country",
        ""
    ).apply(row_country_matches)

    skipped_country = len(
        data[pending_mask & ~country_mask]
    )

    print(
        "\nFiltering to country/countries: "
        + ", ".join(sorted(wanted_countries))
    )

    if skipped_country:

        print(
            f"Skipping {skipped_country} contact(s) not in the "
            f"selected country list this run."
        )

    return pending_mask & country_mask, wanted_countries


# ==================================================
# Main Function
# ==================================================

def main():

    print("\nReading Excel File...")

    try:
        data = read_excel(
            FILE_NAME,
            SHEET_NAME
        )

    except Exception as e:
        print("Excel Read Error:", e)
        return


    # Create output columns if not present
    if "Validation 2" not in data.columns:
        data["Validation 2"] = ""

    for col in ("Industry", "Company Size", "Company Members", "Company LinkedIn URL", "Revenue"):
        if col not in data.columns:
            data[col] = ""


    total_contacts = len(data)

    print(
        f"Total Contacts Found: {total_contacts}"
    )


    # ----------------------------------------------
    # Rows that already have a "Validation 2" result from a
    # previous run are skipped, so you can re-run main.py and it
    # picks up where it left off.
    # ----------------------------------------------

    pending_mask = (
        data["Validation 2"].isna()
        | (data["Validation 2"].astype(str).str.strip() == "")
    )

    already_done = total_contacts - len(data[pending_mask])

    if already_done:
        print(
            f"Skipping {already_done} contact(s) already validated "
            f"in a previous run."
        )


    if SCRAPER_MODE != "apify":
        ask_linkedin_limit()

    ask_experience_years()

    enrichment_fields = ask_enrichment_fields()

    pending_mask, filter_countries = ask_country_filter(data, pending_mask)


    scraped_results = None

    if SCRAPER_MODE == "apify":

        # ----------------------------------------------
        # Apify scrapes everything in one (or a few) batched
        # runs up front. Free plan only returns up to 10
        # profiles per run, so this only covers the next batch
        # of pending rows each time you re-run main.py.
        # ----------------------------------------------

        pending_rows = data[pending_mask]

        all_urls = [
            str(u).strip()
            for u in pending_rows.get("Linkedin URL", [])
            if str(u).strip() and str(u).strip().lower() != "nan"
        ]

        print(
            f"\nScraping {len(all_urls)} LinkedIn profiles via Apify..."
        )

        try:

            scraped_results = get_linkedin_details_batch(all_urls)

        except Exception as e:

            print("Apify Scraping Error:", e)
            return

    use_threaded_playwright = (
        SCRAPER_MODE != "apify"
        and getattr(config, "PLAYWRIGHT_WORKERS", 1) > 1
    )


    # ----------------------------------------------
    # LinkedIn account / daily lead limit tracking (single-tab
    # path only - the threaded path manages this itself inside
    # run_threaded_playwright).
    # ----------------------------------------------

    cookie_file = config.COOKIE_FILE
    daily_limit = getattr(config, "DAILY_LEAD_LIMIT", None)
    used_today = (
        load_usage(cookie_file)
        if SCRAPER_MODE != "apify"
        else 0
    )


    if SCRAPER_MODE != "apify":

        # ----------------------------------------------
        # Playwright scrapes profiles using your own logged-in
        # LinkedIn session (cookies.json). Free, no run limits.
        # If config.PLAYWRIGHT_WORKERS > 1, multiple browser tabs
        # run in parallel (faster, but higher LinkedIn rate-limit
        # risk - see config.py). In that case each worker thread
        # launches its own browser later on, so we deliberately
        # do NOT start the single global browser here.
        # ----------------------------------------------

        print("\nUsing free Playwright scraper (your LinkedIn session)...")

        if not use_threaded_playwright:

            try:

                start_browser(cookie_file=cookie_file)

            except Exception as e:

                print("Browser Start Error:", e)
                return


    if use_threaded_playwright:

        try:

            run_threaded_playwright(
                data,
                total_contacts,
                pending_mask,
                filter_countries,
                enrichment_fields
            )

        except Exception as e:

            print("\nUnexpected error during threaded validation:", e)
            raise

        finally:

            try:

                close_browser()

            except Exception as e:

                print("Browser Close Error:", e)

        return


    stopped_early = False

    # Shared cache for the sequential path: company LinkedIn URL →
    # company details. Same company won't be re-fetched if it
    # appears more than once in the sheet.
    company_cache = {}

    try:

        for index, row in data.iterrows():

            existing_result = str(row.get("Validation 2", "")).strip()

            if existing_result and existing_result.lower() != "nan":
                # Already validated in a previous run - leave as is
                continue

            if not pending_mask.loc[index]:
                # Not in the selected country filter this run - leave as is
                continue

            print("\n" + "=" * 70)
            print(
                f"Processing Contact {index + 1} of {total_contacts}"
            )
            print("=" * 70)


            # ------------------------------------------
            # Excel Data
            # ------------------------------------------

            excel_name = (
                str(row.get("First Name", "")) + " " +
                str(row.get("Last Name", ""))
            ).strip()


            excel_job = str(
                row.get("Job Title", "")
            ).strip()


            excel_country = str(
                row.get("Country", "")
            ).strip()


            print("\nEXCEL DATA")
            print("-" * 30)

            print("Name     :", excel_name)
            print("Job Title:", excel_job)
            print("Country  :", excel_country)


            # ------------------------------------------
            # LinkedIn URL
            # ------------------------------------------

            url = str(
                row.get("Linkedin URL", "")
            ).strip()


            # ------------------------------------------
            # Daily LinkedIn Lead Limit
            #
            # Only matters when this contact actually needs a
            # LinkedIn pageview (a missing URL never touches
            # LinkedIn). Once the current account hits its daily
            # cap, log it out and ask for another account's
            # cookies file to keep going.
            # ------------------------------------------

            if (
                SCRAPER_MODE != "apify"
                and url and url.lower() != "nan"
                and daily_limit
                and used_today >= daily_limit
            ):

                print(
                    f"\nDaily limit of {daily_limit} leads reached for "
                    f"this LinkedIn account ({cookie_file})."
                )

                try:
                    close_browser()
                except Exception as e:
                    print("Browser Close Error:", e)

                logout_account(cookie_file)

                next_file = ask_next_linkedin_account(cookie_file)

                if not next_file:

                    print("\nStopping for today - saving progress...")

                    stopped_early = True
                    break

                cookie_file = next_file
                used_today = load_usage(cookie_file)

                try:

                    start_browser(cookie_file=cookie_file)

                except Exception as e:

                    print("Browser Start Error:", e)

                    stopped_early = True
                    break


            if not url or url.lower() == "nan":

                print("No LinkedIn URL Found")


                linkedin_data = {
                    "full_name": "",
                    "job_title": "",
                    "company_name": "",
                    "country": "",
                    "current_employee": False,
                    "employment_flags": [],
                    "open_to_flags": []
                }


                result = "NO LINKEDIN"


            else:

                try:

                    if SCRAPER_MODE == "apify":

                        linkedin_data = lookup_result(
                            scraped_results,
                            url
                        )

                    else:

                        linkedin_data = get_linkedin_details(
                            url,
                            excel_job
                        )


                    result = validate_lead(
                        row,
                        linkedin_data,
                        filter_countries
                    )

                    # Fetch company About page details for valid leads.
                    # Reuse cached result if the same company was
                    # already fetched for an earlier lead.
                    want_industry = enrichment_fields.get("industry", True)
                    want_emp_size = enrichment_fields.get("emp_size", True)
                    want_revenue = enrichment_fields.get("revenue", True)

                    if (
                        result == "VALID"
                        and SCRAPER_MODE != "apify"
                        and (want_industry or want_emp_size or want_revenue)
                    ):
                        company_url = linkedin_data.get(
                            "company_linkedin_url", ""
                        )
                        company_name_for_lookup = linkedin_data.get(
                            "company_name", ""
                        )
                        # Revenue (via ZoomInfo/Google) only needs a
                        # company NAME, not a LinkedIn URL - still
                        # run this for no-URL companies, with the
                        # cache falling back to the name as its key.
                        need_something = (
                            ((want_industry or want_emp_size) and company_url)
                            or (want_revenue and company_name_for_lookup)
                        )
                        if need_something:
                            cache_key = company_url or (
                                "name:" + company_name_for_lookup.lower()
                            )
                            if cache_key in company_cache:
                                print(
                                    f"\nUsing cached company details "
                                    f"for: {cache_key}"
                                )
                                linkedin_data.update(
                                    company_cache[cache_key]
                                )
                            else:
                                try:
                                    company_details = get_company_details(
                                        company_url,
                                        get_page(),
                                        company_name=company_name_for_lookup,
                                        want_industry=want_industry,
                                        want_emp_size=want_emp_size,
                                        want_revenue=want_revenue
                                    )
                                    linkedin_data.update(company_details)
                                    company_cache[cache_key] = (
                                        company_details
                                    )
                                except Exception as ce:
                                    print(
                                        "Company details error "
                                        "(continuing):", ce
                                    )


                except SessionExpiredError as e:

                    # The session is dead, not just this one
                    # contact - every remaining contact would hit
                    # the same authwall if we kept going with
                    # these cookies. Rotate to a different account
                    # (same flow as the daily-limit handling above)
                    # and retry THIS contact once with the fresh
                    # session before moving on.

                    print("\nLinkedIn session expired:", e)

                    try:
                        close_browser()
                    except Exception as ce:
                        print("Browser Close Error:", ce)

                    logout_account(cookie_file)

                    next_file = ask_next_linkedin_account(cookie_file)

                    if not next_file:

                        print("\nStopping for today - saving progress...")

                        stopped_early = True
                        break

                    cookie_file = next_file
                    used_today = load_usage(cookie_file)

                    try:
                        start_browser(cookie_file=cookie_file)
                    except Exception as be:
                        print("Browser Start Error:", be)
                        stopped_early = True
                        break

                    try:
                        linkedin_data = get_linkedin_details(
                            url,
                            excel_job
                        )
                        result = validate_lead(row, linkedin_data, filter_countries)
                    except Exception as e2:
                        print(
                            "LinkedIn Lookup Error after account "
                            "rotation:", e2
                        )
                        linkedin_data = {
                            "full_name": "",
                            "job_title": "",
                            "company_name": "",
                            "country": "",
                            "current_employee": False
                        }
                        result = "SCRAPING ERROR"

                except Exception as e:

                    print(
                        "LinkedIn Lookup Error:",
                        e
                    )


                    linkedin_data = {
                        "full_name": "",
                        "job_title": "",
                        "company_name": "",
                        "country": "",
                        "current_employee": False
                    }


                    result = "SCRAPING ERROR"


                if SCRAPER_MODE != "apify":

                    used_today += 1
                    save_usage(cookie_file, used_today)

                    print(f"\nLinkedIn leads used today ({cookie_file}): {used_today}")


            # ------------------------------------------
            # LinkedIn Data
            # ------------------------------------------

            print("\nLINKEDIN DATA")
            print("-" * 30)


            print(
                "Name     :",
                linkedin_data.get(
                    "full_name",
                    ""
                )
            )


            print(
                "Job Title:",
                linkedin_data.get(
                    "job_title",
                    ""
                )
            )


            print(
                "Company  :",
                linkedin_data.get(
                    "company_name",
                    ""
                )
            )


            print(
                "Country  :",
                linkedin_data.get(
                    "country",
                    ""
                )
            )


            print(
                "Current Employee:",
                "YES"
                if linkedin_data.get(
                    "current_employee",
                    False
                )
                else "NO"
            )


            print(
                "Employment Flags:",
                linkedin_data.get(
                    "employment_flags",
                    []
                )
            )


            print(
                "Open To Flags:",
                linkedin_data.get(
                    "open_to_flags",
                    []
                )
            )


            # ------------------------------------------
            # Validation Result
            # ------------------------------------------

            print("\nRESULT")
            print("-" * 30)

            print(result)


            # Save result in dataframe

            data.at[
                index,
                "Validation 2"
            ] = result


            # Calling sheet didn't supply a country for this row -
            # backfill it from whatever LinkedIn showed instead of
            # leaving it blank in the output (validator.py already
            # treats a blank sheet country as "nothing to compare",
            # not a mismatch, so this is purely filling in missing
            # data).
            if (
                not excel_country
                and linkedin_data.get("country")
            ):
                data.at[
                    index,
                    "Country"
                ] = linkedin_data["country"]


            # Job title matched (after symbol/stopword cleanup)
            # between the calling sheet and LinkedIn - rewrite the
            # sheet's short/older wording with LinkedIn's actual
            # current title so the output shows the up-to-date
            # version, per request.
            if (
                "JOB TITLE" not in result
                and linkedin_data.get("job_title")
            ):
                data.at[
                    index,
                    "Job Title"
                ] = linkedin_data["job_title"]


            # Update LinkedIn URL with the final canonical URL
            # (after any redirects) for valid leads.
            final_url = linkedin_data.get("final_url", "")
            if (
                result == "VALID"
                and final_url
                and final_url != url
            ):
                data.at[index, "Linkedin URL"] = final_url


            # Write company About page data for valid leads - only
            # the columns actually asked for via
            # ask_enrichment_fields().
            if result == "VALID":

                ef = enrichment_fields or {
                    "industry": True, "emp_size": True, "revenue": True
                }

                if ef.get("industry", True):
                    data.at[index, "Industry"] = (
                        linkedin_data.get("industry", "")
                    )

                if ef.get("emp_size", True):
                    data.at[index, "Company Size"] = (
                        linkedin_data.get("company_size_range", "")
                    )
                    data.at[index, "Company Members"] = (
                        linkedin_data.get("company_size_members", "")
                    )

                if ef.get("industry", True) or ef.get("emp_size", True):
                    data.at[index, "Company LinkedIn URL"] = (
                        linkedin_data.get("company_linkedin_url", "")
                    )

                if ef.get("revenue", True):
                    data.at[index, "Revenue"] = (
                        linkedin_data.get("revenue", "")
                    )


            # ------------------------------------------
            # Auto save every 25 contacts
            # ------------------------------------------

            if (index + 1) % 25 == 0:

                print(
                    "\nSaving Progress..."
                )

                try:

                    save_excel(
                        data,
                        OUTPUT_FILE
                    )

                    print(
                        "Progress Saved Successfully"
                    )


                except PermissionError:

                    print(
                        "\nOutput file is open."
                    )

                    print(
                        "Please close Excel and try again."
                    )

                    return



        # ==================================================
        # Final Save
        # ==================================================

        print("\nFinal Saving...")


        while True:

            try:

                save_excel(
                    data,
                    OUTPUT_FILE
                )

                break


            except PermissionError:

                input(
                    "\nOutput file is open in Excel.\n"
                    "Please close the Excel file and press ENTER to retry..."
                )


        print("\n" + "=" * 70)

        if stopped_early:

            print(
                "Lead Validation Stopped - daily LinkedIn limit reached."
            )

        else:

            print(
                "Lead Validation Completed Successfully!"
            )

        print(
            "Output File:",
            OUTPUT_FILE
        )

        print("=" * 70)


    except Exception as e:

        print("\nUnexpected error during validation loop:", e)
        raise

    finally:

        if SCRAPER_MODE != "apify":

            try:

                close_browser()

            except Exception as e:

                print("Browser Close Error:", e)




# ==================================================
# Run Application
# ==================================================

if __name__ == "__main__":

    main()