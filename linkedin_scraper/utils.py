# linkedin_scraper/utils.py

import re
from config import COUNTRIES


# ==========================================
# Clean Text
# ==========================================

def clean_text(text):

    if not text:
        return ""

    lines = []

    for line in str(text).split("\n"):

        line = " ".join(
            line.split()
        )

        if line:
            lines.append(line)

    return "\n".join(lines)


# ==========================================
# Scroll LinkedIn Profile
# Loads Experience, About, Education
# ==========================================

def scroll_profile(page):

    print("Scrolling profile...")

    previous_height = 0

    # Profiles with a long About section and/or a big Activity/Posts
    # feed push the actual "Experience" heading much further down the
    # page than usual. Stopping the scroll loop as soon as
    # scrollHeight looks unchanged ONCE (the old behavior) breaks out
    # too early on these pages - confirmed from real runs where
    # profile_text came back 12,000-14,000+ characters long (huge
    # About/Posts content) but the literal word "Experience" never
    # appeared anywhere in it at all, even though it's plainly
    # visible further down the live page. Requiring the height to be
    # unchanged on TWO checks in a row (not just one) avoids treating
    # a slow-loading feed section as "fully loaded" prematurely.

    stable_count = 0

    for _ in range(10):

        page.mouse.wheel(
            0,
            2500
        )

        # mouse.wheel() dispatches a wheel event at the current
        # cursor position - if that happens to sit over a fixed
        # element (e.g. LinkedIn's top nav bar) the event can be
        # consumed there instead of scrolling the page. Pairing it
        # with a direct window.scrollBy() call means the scroll
        # doesn't depend on where the cursor happens to be.
        try:
            page.evaluate("window.scrollBy(0, 2500)")
        except Exception:
            pass

        page.wait_for_timeout(500)


        current_height = page.evaluate(
            "document.body.scrollHeight"
        )

        if current_height == previous_height:

            stable_count += 1

            if stable_count >= 2:
                break

        else:

            stable_count = 0

        previous_height = current_height


    # Extra targeted pass: keep scrolling specifically until the
    # word "Experience" actually shows up in the rendered page text,
    # instead of trusting scrollHeight alone. Capped so profiles that
    # genuinely have no Experience section (or a renamed/hidden one)
    # don't scroll forever.
    #
    # IMPORTANT: must match on a standalone heading LINE ("Experience"
    # or "Work experience" by itself), not a substring match anywhere
    # in the page. A plain .includes('experience') matches constantly
    # inside totally unrelated text - headlines like "Experienced
    # Solutions Account Manager" or About text like "12+ Years of
    # sales experience" - which made this loop exit on the very FIRST
    # check, before ever scrolling far enough to lazy-load the real
    # Experience section. Confirmed against real runs (Sarah Davis,
    # Wesley Hall, Nicole Gregait, Chantrice Martin) where every one
    # of them had "experience" somewhere in their headline/About text
    # and every one of them came back with a blank job title/company
    # because the section never actually got scrolled into view.
    # This must use the same exact-line standard as
    # parser.get_experience_lines(), or the two can disagree about
    # whether the section "loaded".

    for _ in range(15):

        has_experience = page.evaluate(
            """
            () => document.body.innerText
                .split('\\n')
                .some(line => {
                    const t = line.trim().toLowerCase();
                    return t === 'experience' || t === 'work experience';
                })
            """
        )

        if has_experience:
            break

        page.mouse.wheel(
            0,
            2500
        )

        try:
            page.evaluate("window.scrollBy(0, 2500)")
        except Exception:
            pass

        page.wait_for_timeout(600)


    # Back to top
    page.evaluate(
        "window.scrollTo(0, 0)"
    )

    page.wait_for_timeout(
        800
    )

    print("Scrolling completed")


# ==========================================
# Extract Country From Location
# IMPORTANT:
# Do NOT search whole profile
# ==========================================

def extract_country(location):

    if not location:
        return ""

    location_lower = location.lower()


    for country in COUNTRIES:

        if country.lower() in location_lower:

            print(
                "Country Found:",
                country
            )

            return country


    return ""


# ==========================================
# Remove LinkedIn Header Noise
# Fix:
# Name = Me
# Job = Message
# ==========================================

def is_invalid_header_line(text):

    if not text:
        return True


    text = text.lower().strip()


    invalid_words = [
        "me",
        "home",
        "jobs",
        "messaging",
        "notifications",
        "my network",
        "for business",
        "try premium",
        "message",
        "follow",
        "connect",
        "contact info",
        "open to",
        "skip to",
        "visit my website",
        "people also viewed",
        "show all",
        "see all"
    ]


    for word in invalid_words:

        if text == word or text.startswith(word):
            return True


    return False


# ==========================================
# Detect Date Lines
# Examples:
# Jan 2025 - Present
# 2020 - 2024
# ==========================================

def is_date_line(text):

    if not text:
        return False


    patterns = [
        r"\b\d{4}\s*-\s*\d{4}\b",
        r"\b\d{4}\s*-\s*present\b",
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    ]


    text = text.lower()


    for pattern in patterns:

        if re.search(
            pattern,
            text
        ):
            return True


    return False


# ==========================================
# Detect Duration
# Examples:
# 10 yrs 3 mos
# 2 yrs
# 6 mos
# ==========================================

def is_duration_line(text):

    if not text:
        return False


    pattern = (
        r"\b\d+\s*(yr|yrs|year|years|"
        r"mo|mos|month|months)\b"
    )


    return bool(
        re.search(
            pattern,
            text.lower()
        )
    )


# ==========================================
# Employment Type / Work Mode
# Ignore these in Experience
# ==========================================

def is_ignore_experience(text):

    if not text:
        return False


    ignore_words = [
        "full-time",
        "part-time",
        "contract",
        "freelance",
        "internship",
        "temporary",
        "self-employed",
        "remote",
        "hybrid",
        "on-site"
    ]


    text = text.lower()


    for word in ignore_words:

        if word in text:
            return True


    return False


# ==========================================
# Normalize Text For Comparison
# Used in validator.py
#
# Handles:
# & == and
# comma difference
# uppercase/lowercase
# ==========================================

def normalize_text(text):

    if not text:
        return ""


    text = text.lower()


    # Replace symbols
    text = text.replace("&", "and")


    # Remove special characters
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )


    # Remove extra spaces
    text = " ".join(
        text.split()
    )


    return text