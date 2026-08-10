"""
debug_profile.py
=================
Debug ONE or a few LinkedIn profile URLs directly, without running the
whole batch in main.py. Reuses the exact same scraping/parsing code
main.py uses, so whatever it prints here (CLEAN HEADER, EXPERIENCE,
Meaningful Experience Lines, FINAL LINKEDIN DATA, etc.) is exactly
what main.py would have seen for that contact.

Use this whenever a specific lead comes back with an unexpected
INVALID result and you want to see exactly what got scraped/parsed
for that one profile, instead of scrolling through a 25-contact log.

RUN
    python debug_profile.py "<linkedin-url>" ["<linkedin-url-2>" ...]

Example
    python debug_profile.py "https://www.linkedin.com/in/mariamilliken/" "https://www.linkedin.com/in/caroline-grasso-aism%C2%AE-381a8329/"

A visible browser window will open using your saved cookies.json
(same login as main.py) - no need to log in again if it's already
saved.
"""

import sys

import config
from linkedin_scraper.browser import start_browser, close_browser
from linkedin_scraper.scraper import get_linkedin_details


def main():

    if len(sys.argv) < 2:
        print(__doc__)
        return

    urls = sys.argv[1:]

    start_browser(cookie_file=config.COOKIE_FILE)

    try:

        for url in urls:

            print("\n" + "#" * 70)
            print("DEBUGGING:", url)
            print("#" * 70)

            data = get_linkedin_details(url, excel_job="")

            print("\n>>> SUMMARY (excluding raw profile_text)")

            for key, value in data.items():

                if key == "profile_text":
                    continue

                print(f"{key}: {value}")

    finally:

        close_browser()


if __name__ == "__main__":
    main()
