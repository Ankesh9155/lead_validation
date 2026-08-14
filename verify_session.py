"""
verify_session.py
==================
Checks whether a saved Playwright storage_state file (cookies.json,
or any second/third-account cookie file from main.py's account
rotation) is still a valid, logged-in LinkedIn session - WITHOUT ever
printing its contents (no cookies/tokens are logged).

Run this:
  - Right after `python login.py`, to confirm the session it saved
    actually works before you upload it anywhere.
  - Before pasting a file's contents into a Render Secret File, to
    avoid configuring Render with a session that's already dead.
  - Any time a job on the dashboard reports "session expired" and you
    want to confirm a fix before re-uploading/redeploying.

Always runs headless (no visible window) and never types a
username/password - if the session is dead, the fix is to log in
again locally with `python login.py`, not to automate a login here.

RUN
    python verify_session.py [path-to-cookies.json]

    (defaults to "cookies.json" in the current directory if omitted)
"""

import sys
import os

from playwright.sync_api import sync_playwright


def verify_session(storage_state_path: str) -> bool:

    if not os.path.exists(storage_state_path):
        print(f"File not found: {storage_state_path}")
        return False

    print(f"Checking session in: {storage_state_path} (headless)...")

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage_state_path)
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Navigation error: {type(e).__name__}: {e}")
            browser.close()
            return False

        final_url = page.url
        browser.close()

    dead_markers = ("/login", "authwall", "checkpoint")

    if any(marker in final_url.lower() for marker in dead_markers):
        print("RESULT: Session is EXPIRED / not logged in.")
        print("Fix: run `python login.py` again to create a fresh session.")
        return False

    print("RESULT: Session is VALID (reached the LinkedIn feed while logged in).")
    return True


if __name__ == "__main__":

    path = sys.argv[1] if len(sys.argv) > 1 else "cookies.json"

    ok = verify_session(path)

    sys.exit(0 if ok else 1)
