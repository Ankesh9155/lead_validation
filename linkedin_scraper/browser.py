# linkedin_scraper/browser.py

from playwright.sync_api import sync_playwright
import os
import shutil
import base64
import json


# Global browser objects
playwright = None
browser = None
context = None
page = None


# ==========================================
# Hosted-Deployment Detection
#
# Single source of truth for "is this process running on a hosted
# platform (Render/Kubernetes) with nobody able to see a browser
# window, vs. someone's own machine". webapp/app.py imports this
# instead of keeping its own copy, since headless mode (below) needs
# the exact same check.
#
# RENDER is set automatically by Render on every service
# (https://render.com/docs/environment-variables#all-runtimes) - no
# config needed. There's no Kubernetes/Rancher equivalent, so
# k8s/deployment.yaml sets HOSTED_DEPLOYMENT=true explicitly.
# ==========================================

def is_hosted_deployment() -> bool:

    return bool(
        os.environ.get("RENDER")
        or os.environ.get("HOSTED_DEPLOYMENT", "").strip().lower()
        in ("1", "true", "yes")
    )


# ==========================================
# Headless Mode
#
# Local runs (main.py, login.py, debug_profile.py, the "Log in to
# LinkedIn" dashboard button) keep the original real/visible browser
# window - unchanged. On a hosted deployment (Render/Rancher) there
# is nobody to see that window, and Render's free tier has only
# 512MB RAM, so a real headless=True Chromium (no Xvfb virtual
# display needed) is both the only usable option and far lighter.
#
# PLAYWRIGHT_HEADLESS is an explicit escape hatch (e.g. to force
# headless=True while testing locally) - set it to "1"/"true" or
# "0"/"false" to override the automatic hosted-deployment detection.
# ==========================================

def _headless_mode() -> bool:

    override = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()

    if override in ("1", "true", "yes"):
        return True

    if override in ("0", "false", "no"):
        return False

    return is_hosted_deployment()


# ==========================================
# Bootstrap Session From Render Secret File / Env Var
#
# Render's free web services have an EPHEMERAL filesystem - anything
# written to disk (including a cookies.json uploaded through the
# dashboard) is wiped on every restart / idle spin-down. Render
# Secret Files are the free, persistent exception: a file you paste
# into the Render dashboard (Environment -> Secret Files), never
# committed to git, that Render re-mounts at a fixed path on every
# boot, including after a restart.
#
# This copies that Secret File's contents into `cookie_file` (e.g.
# webapp/data/cookies.json) once at process startup, so a freshly
# booted container starts already authenticated with no manual
# re-upload needed. If no Secret File is present, falls back to a
# base64-encoded LINKEDIN_STORAGE_STATE_B64 env var (only suitable
# for very small storage_state files - see README).
#
# Never logs cookie/session content - only filenames and outcomes.
# ==========================================

DEFAULT_SECRET_FILE_PATH = "/etc/secrets/linkedin_storage_state.json"


def bootstrap_session_from_secret(cookie_file) -> bool:

    secret_path = os.environ.get(
        "LINKEDIN_STORAGE_STATE_PATH", ""
    ).strip() or DEFAULT_SECRET_FILE_PATH

    if os.path.exists(secret_path):

        try:

            os.makedirs(os.path.dirname(cookie_file) or ".", exist_ok=True)
            shutil.copyfile(secret_path, cookie_file)

            print(
                f"Loaded LinkedIn session from Secret File "
                f"({os.path.basename(secret_path)})."
            )

            return True

        except Exception as e:

            print(
                "Could not load LinkedIn session from Secret File:",
                type(e).__name__,
            )

    b64 = os.environ.get("LINKEDIN_STORAGE_STATE_B64", "").strip()

    if b64:

        try:

            raw = base64.b64decode(b64)

            # Validate it's real storage_state JSON before writing -
            # a bad/partial env var value should never silently
            # produce a corrupt cookies.json.
            json.loads(raw)

            os.makedirs(os.path.dirname(cookie_file) or ".", exist_ok=True)

            with open(cookie_file, "wb") as f:
                f.write(raw)

            print("Loaded LinkedIn session from LINKEDIN_STORAGE_STATE_B64.")

            return True

        except Exception as e:

            print(
                "Could not decode LINKEDIN_STORAGE_STATE_B64:",
                type(e).__name__,
            )

    return False


# ==========================================
# Raised when a profile load lands on
# LinkedIn's authwall ("Join LinkedIn" / sign
# in page) instead of the real profile - this
# means the session's cookies are no longer
# logged in (expired, or LinkedIn force-logged
# it out for suspicious/too-fast activity).
#
# This is NOT the same as "profile not found"
# or "page loaded slowly" - retrying or
# recreating the browser tab does nothing here,
# because the cookies themselves are dead. Every
# subsequent profile on this same session will
# hit the same authwall and come back blank,
# which is what was happening across many
# contacts in a row before this was added.
# Callers should stop using this session and
# rotate to a different LinkedIn account instead
# of retrying.
# ==========================================

class SessionExpiredError(Exception):
    pass


# ==========================================
# Auto Login with Credentials
#
# Called when cookies.json is missing or the session has expired.
# Navigates to the LinkedIn login page, fills in email/password,
# and waits until the home feed is loaded. The caller is
# responsible for saving cookies afterwards via
# context.storage_state(path=cookie_file).
# ==========================================

def login_linkedin_with_credentials(pg, email, password):

    print("\nLogging into LinkedIn with provided credentials...")

    pg.goto(
        "https://www.linkedin.com/login",
        wait_until="domcontentloaded",
        timeout=60000
    )

    pg.wait_for_timeout(2000)

    pg.fill("#username", email)
    pg.fill("#password", password)

    pg.click("button[type='submit']")

    # Wait until redirected away from the login page
    pg.wait_for_url(
        lambda url: "linkedin.com/login" not in url,
        timeout=60000
    )

    pg.wait_for_timeout(3000)

    # ------------------------------------------
    # 2FA / checkpoint handling
    #
    # LinkedIn sometimes interrupts a fresh login with a
    # "checkpoint" page - a verification code emailed/texted to
    # you, a "is this you?" photo puzzle, or similar. This is NOT
    # a login failure (wrong email/password) - it's an extra step
    # LinkedIn is asking a real human to complete. Since the
    # browser runs with headless=False, the window is visible on
    # screen, so instead of giving up immediately we wait here and
    # let you complete it by hand, then keep going automatically
    # once you're past it.
    # ------------------------------------------

    if "checkpoint" in pg.url:

        print(
            "\nLinkedIn is asking for extra verification "
            "(checkpoint) - this usually means a code was sent to "
            "your email/phone, or a security puzzle needs solving."
        )
        print(
            "Switch to the browser window and complete it now. "
            "Waiting up to 3 minutes for you to finish..."
        )

        try:

            pg.wait_for_url(
                lambda url: (
                    "checkpoint" not in url
                    and "linkedin.com/login" not in url
                ),
                timeout=180000
            )

        except Exception:

            raise RuntimeError(
                "LinkedIn checkpoint/verification was not completed "
                "in time (waited 3 minutes). Re-run and complete it "
                "faster, or check your email/phone for the code."
            )

        pg.wait_for_timeout(2000)

    if "linkedin.com/login" in pg.url or "checkpoint" in pg.url:
        raise RuntimeError(
            "LinkedIn login failed or requires verification. "
            "Check your credentials or complete the CAPTCHA manually."
        )

    print("LinkedIn login successful.")


# ==========================================
# Ensure LinkedIn Session
#
# Checks whether the current page is actually logged into
# LinkedIn. If not (missing cookies or expired session) and
# credentials are configured, logs in automatically and saves
# fresh cookies to cookie_file.
# ==========================================

def _ensure_linkedin_session(pg, ctx, cookie_file):

    import config as _cfg

    email = getattr(_cfg, "LINKEDIN_EMAIL", "").strip()
    password = getattr(_cfg, "LINKEDIN_PASSWORD", "").strip()

    if not email or not password:
        return

    # Quick check: navigate to LinkedIn feed; if redirected to
    # login page the session is gone and we need to log in.
    try:

        pg.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=30000
        )

        pg.wait_for_timeout(2000)

    except Exception:
        pass

    if "linkedin.com/login" not in pg.url and "checkpoint" not in pg.url:
        # Already logged in — nothing to do
        return

    login_linkedin_with_credentials(pg, email, password)

    ctx.storage_state(path=cookie_file)

    print(f"Session saved to {cookie_file}")


# ==========================================
# Start Browser
# ==========================================

def start_browser(cookie_file="cookies.json"):

    global playwright, browser, context, page

    print("\nStarting Browser...")

    playwright = sync_playwright().start()


    browser = playwright.chromium.launch(
        headless=_headless_mode(),
        slow_mo=0
    )


    options = {
        "viewport": {
            "width": 1400,
            "height": 900
        }
    }


    # Load LinkedIn saved session
    if cookie_file and os.path.exists(cookie_file):

        print(f"Loading saved LinkedIn session ({cookie_file})...")

        options["storage_state"] = cookie_file

    else:

        print(f"{cookie_file} not found - will attempt auto-login.")


    context = browser.new_context(**options)

    page = context.new_page()

    page.set_default_timeout(60000)


    # Auto-login if cookies are missing or the session expired
    _ensure_linkedin_session(page, context, cookie_file)


    print("Browser Started Successfully")


# ==========================================
# Get Current Page
# ==========================================

def get_page():

    global page

    return page


# ==========================================
# Create New Page
# ==========================================

def create_new_page():

    global context, page


    if page and not page.is_closed():

        page.close()


    page = context.new_page()

    page.set_default_timeout(
        60000
    )


    return page


# ==========================================
# Launch Worker Browser (for parallel scraping)
#
# IMPORTANT: Playwright's sync API is NOT safe to share
# across threads. A single sync_playwright().start() call
# spins up a background dispatcher thread plus a greenlet
# tied to whichever thread called .start() - every
# page.goto()/etc. for objects created from that call must
# be driven from THAT SAME thread, or you get errors like
# "greenlet.error: cannot switch to a different thread" and
# basically every navigation aborting (net::ERR_ABORTED).
# That mismatch (pages created on the main thread, driven
# from worker threads) was the actual cause of the
# all-leads-invalid run.
#
# Fix: each worker thread gets its OWN fully independent
# Playwright instance, browser, context, and page - all
# created on (and only ever used from) that worker's own
# thread. They each load the same cookies.json, so every
# worker still reuses the same logged-in LinkedIn session,
# just via separate browser processes/contexts.
# ==========================================

def launch_worker_browser(cookie_file="cookies.json"):

    pw = sync_playwright().start()

    br = pw.chromium.launch(
        headless=_headless_mode(),
        slow_mo=0
    )

    options = {
        "viewport": {
            "width": 1400,
            "height": 900
        }
    }

    if cookie_file and os.path.exists(cookie_file):

        options["storage_state"] = cookie_file

    ctx = br.new_context(**options)

    pg = ctx.new_page()

    pg.set_default_timeout(60000)

    _ensure_linkedin_session(pg, ctx, cookie_file)

    return pw, br, ctx, pg


# ==========================================
# Close Worker Browser
#
# Tears down everything created by launch_worker_browser()
# for one worker thread. Must be called from that same
# worker thread, for the same reason described above.
# ==========================================

def close_worker_browser(pw, br, ctx, pg):

    try:

        if pg and not pg.is_closed():

            pg.close()

    except Exception as e:

        print("Worker page close error:", e)

    try:

        if ctx:

            ctx.close()

    except Exception as e:

        print("Worker context close error:", e)

    try:

        if br:

            br.close()

    except Exception as e:

        print("Worker browser close error:", e)

    try:

        if pw:

            pw.stop()

    except Exception as e:

        print("Worker playwright stop error:", e)


# ==========================================
# Logout Of LinkedIn
#
# Called when the daily lead limit is hit for the account
# currently logged in via cookies.json, so the session is
# properly ended on LinkedIn's side (not just the browser
# window closed) before asking for another account.
# ==========================================

def logout_linkedin(pg):

    try:

        print("\nLogging out of LinkedIn...")

        pg.goto(
            "https://www.linkedin.com/m/logout/",
            timeout=30000
        )

        pg.wait_for_timeout(2000)

        print("Logged out of LinkedIn")

    except Exception as e:

        print("LinkedIn logout error (continuing anyway):", e)


# ==========================================
# Close Browser
# ==========================================

def close_browser():

    global page, context, browser, playwright


    print("\nClosing Browser...")


    try:

        if page and not page.is_closed():

            page.close()

            print("Page closed")

    except Exception as e:

        print(
            "Page close error:",
            e
        )


    try:

        if context:

            context.close()

            print("Context closed")

    except Exception as e:

        print(
            "Context close error:",
            e
        )


    try:

        if browser:

            browser.close()

            print("Browser closed")

    except Exception as e:

        print(
            "Browser close error:",
            e
        )


    try:

        if playwright:

            playwright.stop()

            print("Playwright stopped")

    except Exception as e:

        print(
            "Playwright stop error:",
            e
        )


    print("Browser Closed Successfully")