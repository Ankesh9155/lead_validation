#config.py




# Excel Configuration


FILE_NAME = r"C:\Users\Ankesh\Downloads\CallingSheet - TEC - 6321 27Q2_iProspect_Comms_ABCS (2).xlsx"
SHEET_NAME = "Patna NightShift"

# ==========================================
# Output Configuration
# ==========================================

# Final validated output file
OUTPUT_FILE = r"C:\Users\Ankesh\Downloads\Validated_Output.xlsx"


# ==========================================
# Browser Configuration
# ==========================================

# Run browser in background
HEADLESS = False

# Browser window size
VIEWPORT = {
    "width": 1400,
    "height": 900
}

# Slow browser actions for LinkedIn loading
SLOW_MO = 300

# Default timeout in milliseconds
TIMEOUT = 60000


# ==========================================
# LinkedIn Session
# (Only used by the old Playwright scraper -
# kept here in case you ever need to fall back)
# ==========================================

# Saved LinkedIn login cookies
COOKIE_FILE = "cookies.json"


# ==========================================
# LinkedIn Credentials (auto-login)
#
# If cookies.json is missing or the session has expired, the
# script will log in automatically using these credentials and
# save a fresh cookies.json for the rest of the run.
# Leave blank ("") to skip auto-login and rely on cookies.json.
# ==========================================

LINKEDIN_EMAIL = ""

LINKEDIN_PASSWORD = ""


# ==========================================
# Daily LinkedIn Lead Limit
# ==========================================

# Max number of leads to validate per LinkedIn account, per day
# (only applies when SCRAPER_MODE = "playwright" - Apify has no
# login/ban risk so this doesn't apply there). Once this many
# leads have been checked today on the current account, the
# script logs out of LinkedIn and asks for another account's
# cookies file to keep going.
DAILY_LEAD_LIMIT = 90

# File used to remember how many leads were already checked
# today per LinkedIn account (cookies file), so the limit is
# respected even across multiple re-runs of main.py on the same
# day.
USAGE_TRACK_FILE = "linkedin_usage.json"


# ==========================================
# Scraper Mode
# ==========================================

# Which scraper main.py uses to pull LinkedIn profile data:
#   "playwright" - FREE. Uses your own logged-in LinkedIn session
#                   (cookies.json) and a real browser. Slower
#                   (one profile at a time, ~10-20s each) and
#                   carries LinkedIn ToS/rate-limit risk if run on
#                   too many profiles too fast.
#   "apify"       - PAID after the free trial runs out. Faster,
#                   batched, no LinkedIn login needed.
SCRAPER_MODE = "playwright"


# How many LinkedIn profiles to scrape AT THE SAME TIME using
# separate browser tabs (only applies when SCRAPER_MODE is
# "playwright"). 1 = old behavior, one profile at a time.
# Higher = faster, but also a higher chance LinkedIn flags/
# restricts the account for unusually fast browsing. 3 is a
# balanced choice - not as risky as 4+, noticeably faster than 1.
PLAYWRIGHT_WORKERS = 2


# ==========================================
# Apify Configuration
# (Used only when SCRAPER_MODE = "apify")
# ==========================================

import os
from dotenv import load_dotenv

load_dotenv()

APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")

APIFY_ACTOR_ID = "harvestapi/linkedin-profile-scraper"

APIFY_PROFILE_MODE = "Profile details no email ($4 per 1k)"

APIFY_BATCH_SIZE = 10


# ==========================================
# Scraper Configuration
# ==========================================

# Number of times to scroll LinkedIn profile
SCROLL_COUNT = 15

# Delay between scrolls (milliseconds)
SCROLL_DELAY = 1000


# ==========================================
# Auto Save Configuration
# ==========================================

# Save progress after every X contacts
AUTO_SAVE_COUNT = 25


# ==========================================
# Country List
# Used for location validation
# ==========================================

COUNTRIES = [
    "United States",
    "India",
    "Canada",
    "United Kingdom",
    "Australia",
    "New Zealand",
    "Singapore",
    "Germany",
    "France",
    "Netherlands",
    "Japan",
    "China",
    "Italy",
    "Spain",
    "South Korea",
    "Brazil",
    "Mexico",
    "Ireland",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Switzerland",
    "Belgium",
    "Austria",
    "United Arab Emirates",
    "Malaysia",
    "Philippines",
    "Indonesia",
    "Thailand",
    "Vietnam",
    "South Africa",
    "Nigeria",
    "Kenya",
    "Egypt",
    "Israel",
    "Turkey",
    "Poland",
    "Portugal",
    "Greece",
    "Czech Republic",
    "Romania",
    "Hungary",
    "Pakistan",
    "Bangladesh",
    "Sri Lanka",
    "Nepal",
    "Argentina",
    "Chile",
    "Colombia",
    "Peru",
]


# ==========================================
# Experience Ignore Words
# These are NOT company or job titles
# ==========================================

IGNORE_EXPERIENCE_WORDS = [
    "full-time",
    "part-time",
    "contract",
    "freelance",
    "internship",
    "temporary",
    "remote",
    "hybrid",
    "on-site",
    "self-employed"
]


# ==========================================
# Non-Standard Employment Flags
# If the LATEST LinkedIn experience entry shows
# any of these tags, the lead is marked INVALID
# with that reason added (e.g. "INVALID - REMOTE").
# "Full-time", "On-site" and "Hybrid" are left out
# since those are normal/expected, not a red flag.
# ==========================================

NON_STANDARD_EMPLOYMENT_WORDS = [
    "retired",
    "remote",
    "contract",
    "part-time",
    "freelance",
    "internship",
    "temporary",
    "self-employed"
]


# ==========================================
# Experience Filter
# Maximum years allowed in the latest job title.
# Leads whose current role exceeds this are marked
# INVALID - EXPERIENCE. Can be overridden at runtime
# by ask_experience_years() in main.py (press ENTER
# there to keep this default).
# None = no filter applied.
# ==========================================

# 10 years 6 months
MAX_EXPERIENCE_YEARS = 10.5


