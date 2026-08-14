from playwright.sync_api import sync_playwright


save_path = input(
    "Enter filename to save cookies "
    "(press ENTER for default 'cookies.json'): "
).strip()

if not save_path:
    save_path = "cookies.json"

if not save_path.endswith(".json"):
    save_path += ".json"


with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    context = browser.new_context()

    page = context.new_page()

    page.goto(
        "https://www.linkedin.com/login"
    )

    print("Login using your LinkedIn username and password.")

    input(
        "After the LinkedIn home page loads, press ENTER: "
    )

    context.storage_state(
        path=save_path
    )

    print(
        f"{save_path} saved successfully"
    )

    print(
        f"\nReminder: {save_path} is your live LinkedIn session - "
        f"never commit it to git (it's gitignored via the "
        f"'cookies*.json' pattern already, but double-check "
        f"`git status` if you ever rename/move it)."
    )
    print(
        "Next: `python verify_session.py "
        f"{save_path}` to confirm it works, then see README.md's "
        "\"Deploying to Render\" section to put it in a Render "
        "Secret File."
    )

    browser.close()