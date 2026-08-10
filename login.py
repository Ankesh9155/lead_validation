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

    browser.close()