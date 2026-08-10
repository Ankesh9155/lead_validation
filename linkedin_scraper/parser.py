# linkedin_scraper/parser.py

import re
import datetime

from config import NON_STANDARD_EMPLOYMENT_WORDS


# ==========================================
# Supported Countries
# ==========================================

COUNTRIES = [
    "United States",
    "India",
    "Canada",
    "United Kingdom",
    "Australia",
    "Germany",
    "France",
    "Japan",
    "Singapore",
    "Netherlands",
    "Italy",
    "Spain",
    "New Zealand",
    "Ireland",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Switzerland",
    "Belgium",
    "Austria",
    "Brazil",
    "Mexico",
    "South Korea",
    "China",
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
# State / City / Region -> Country
# ==========================================
# LinkedIn often shows only a city, state, or
# "X Metropolitan Area" with no country word at
# all (e.g. "New York City Metropolitan Area",
# "Wisconsin/Illinois"). This table lets us infer
# the country from those regions.
# Only full names are used (no 2-letter codes)
# to avoid false matches on common English words.

LOCATION_TO_COUNTRY = {

    # ---- United States ----
    "alabama": "United States", "alaska": "United States",
    "arizona": "United States", "arkansas": "United States",
    "california": "United States", "colorado": "United States",
    "connecticut": "United States", "delaware": "United States",
    "florida": "United States", "georgia": "United States",
    "hawaii": "United States", "idaho": "United States",
    "illinois": "United States", "indiana": "United States",
    "iowa": "United States", "kansas": "United States",
    "kentucky": "United States", "louisiana": "United States",
    "maine": "United States", "maryland": "United States",
    "massachusetts": "United States", "michigan": "United States",
    "minnesota": "United States", "mississippi": "United States",
    "missouri": "United States", "montana": "United States",
    "nebraska": "United States", "nevada": "United States",
    "new hampshire": "United States", "new jersey": "United States",
    "new mexico": "United States", "new york": "United States",
    "north carolina": "United States", "north dakota": "United States",
    "ohio": "United States", "oklahoma": "United States",
    "oregon": "United States", "pennsylvania": "United States",
    "rhode island": "United States", "south carolina": "United States",
    "south dakota": "United States", "tennessee": "United States",
    "texas": "United States", "utah": "United States",
    "vermont": "United States", "virginia": "United States",
    "washington": "United States", "west virginia": "United States",
    "wisconsin": "United States", "wyoming": "United States",
    "washington dc": "United States", "district of columbia": "United States",
    "los angeles": "United States", "san francisco": "United States",
    "chicago": "United States", "boston": "United States",
    "seattle": "United States", "austin": "United States",
    "dallas": "United States", "houston": "United States",
    "atlanta": "United States", "denver": "United States",
    "phoenix": "United States", "miami": "United States",
    "santa monica": "United States", "milwaukee": "United States",
    "el segundo": "United States",
    # Additional major US metro-area names - LinkedIn frequently
    # shows ONLY "<City> Metropolitan Area" / "Greater <City> Area"
    # as someone's location with no state/country alongside it
    # (extract_country()'s case-3 fallback handles that format), but
    # it can only resolve to a country if the bare city name is in
    # this table. Confirmed missing from a real profile (Jason
    # Loope, "Detroit Metropolitan Area") whose country came back
    # blank and then got backfilled from an unrelated older job's
    # location instead of resolving straight from the header.
    "detroit": "United States", "philadelphia": "United States",
    "baltimore": "United States", "charlotte": "United States",
    "nashville": "United States", "portland": "United States",
    "sacramento": "United States", "san diego": "United States",
    "san jose": "United States", "san antonio": "United States",
    "jacksonville": "United States", "columbus": "United States",
    "indianapolis": "United States", "fort worth": "United States",
    "memphis": "United States", "oklahoma city": "United States",
    "louisville": "United States", "tucson": "United States",
    "fresno": "United States", "mesa": "United States",
    "kansas city": "United States", "omaha": "United States",
    "raleigh": "United States", "virginia beach": "United States",
    "colorado springs": "United States", "tulsa": "United States",
    "wichita": "United States", "arlington": "United States",
    "new orleans": "United States", "cleveland": "United States",
    "tampa": "United States", "honolulu": "United States",
    "anchorage": "United States", "pittsburgh": "United States",
    "cincinnati": "United States", "st louis": "United States",
    "saint louis": "United States", "orlando": "United States",
    "richmond": "United States", "buffalo": "United States",
    "rochester": "United States", "hartford": "United States",
    "providence": "United States", "salt lake city": "United States",
    "las vegas": "United States", "st petersburg": "United States",
    "raleigh-durham": "United States", "greensboro": "United States",
    "knoxville": "United States", "albuquerque": "United States",
    "baton rouge": "United States", "birmingham": "United States",
    "chattanooga": "United States", "des moines": "United States",
    "durham": "United States", "grand rapids": "United States",
    "kalamazoo": "United States", "lansing": "United States",
    "flint": "United States", "ann arbor": "United States",
    "greenville": "United States", "little rock": "United States",
    "madison": "United States", "spokane": "United States",
    "syracuse": "United States", "toledo": "United States",
    "akron": "United States", "dayton": "United States",
    "el paso": "United States", "long beach": "United States",
    "minneapolis": "United States", "st paul": "United States",
    "saint paul": "United States", "boise": "United States",
    "reno": "United States", "bakersfield": "United States",
    "fort lauderdale": "United States", "west palm beach": "United States",

    # ---- Canada ----
    "ontario": "Canada", "quebec": "Canada",
    "british columbia": "Canada", "alberta": "Canada",
    "manitoba": "Canada", "saskatchewan": "Canada",
    "nova scotia": "Canada", "new brunswick": "Canada",
    "newfoundland": "Canada", "prince edward island": "Canada",
    "toronto": "Canada", "vancouver": "Canada",
    "montreal": "Canada", "ottawa": "Canada",
    "calgary": "Canada", "edmonton": "Canada",
    "winnipeg": "Canada",

    # ---- United Kingdom ----
    "london": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom",

    # ---- India ----
    "maharashtra": "India", "karnataka": "India",
    "tamil nadu": "India", "delhi": "India",
    "mumbai": "India", "bangalore": "India",
    "bengaluru": "India", "hyderabad": "India",
    "pune": "India", "chennai": "India",

    # ---- Australia ----
    "new south wales": "Australia", "victoria": "Australia",
    "queensland": "Australia", "south australia": "Australia",
    "western australia": "Australia", "tasmania": "Australia",
    "sydney": "Australia", "melbourne": "Australia",
    "brisbane": "Australia", "perth": "Australia",
    "adelaide": "Australia", "canberra": "Australia",

    # ---- New Zealand ----
    "new zealand": "New Zealand",
    "auckland": "New Zealand", "wellington": "New Zealand",
    "christchurch": "New Zealand", "hamilton": "New Zealand",
    "tauranga": "New Zealand", "dunedin": "New Zealand",

    # ---- Germany ----
    "berlin": "Germany", "munich": "Germany", "hamburg": "Germany",
    "frankfurt": "Germany", "cologne": "Germany", "stuttgart": "Germany",
    "bavaria": "Germany", "north rhine-westphalia": "Germany",

    # ---- France ----
    "paris": "France", "lyon": "France", "marseille": "France",
    "toulouse": "France", "bordeaux": "France", "ile-de-france": "France",

    # ---- Netherlands ----
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "the hague": "Netherlands", "utrecht": "Netherlands",

    # ---- Ireland ----
    "ireland": "Ireland", "dublin": "Ireland", "cork": "Ireland",
    "galway": "Ireland", "limerick": "Ireland",

    # ---- Sweden ----
    "sweden": "Sweden", "stockholm": "Sweden", "gothenburg": "Sweden",
    "malmo": "Sweden",

    # ---- Norway ----
    "norway": "Norway", "oslo": "Norway", "bergen": "Norway",

    # ---- Denmark ----
    "denmark": "Denmark", "copenhagen": "Denmark",

    # ---- Finland ----
    "finland": "Finland", "helsinki": "Finland",

    # ---- Switzerland ----
    "switzerland": "Switzerland", "zurich": "Switzerland",
    "geneva": "Switzerland", "bern": "Switzerland",

    # ---- Belgium ----
    "belgium": "Belgium", "brussels": "Belgium", "antwerp": "Belgium",

    # ---- Austria ----
    "austria": "Austria", "vienna": "Austria",

    # ---- Spain ----
    "madrid": "Spain", "barcelona": "Spain",
    "catalonia": "Spain", "andalusia": "Spain",

    # ---- Italy ----
    "rome": "Italy", "milan": "Italy", "naples": "Italy",
    "turin": "Italy", "lombardy": "Italy",

    # ---- Japan ----
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan",
    "yokohama": "Japan",

    # ---- Singapore ----
    "singapore": "Singapore",

    # ---- China ----
    "beijing": "China", "shanghai": "China", "guangzhou": "China",
    "shenzhen": "China",

    # ---- South Korea ----
    "seoul": "South Korea", "busan": "South Korea",

    # ---- United Arab Emirates ----
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",

    # ---- Malaysia ----
    "kuala lumpur": "Malaysia",

    # ---- Brazil ----
    "sao paulo": "Brazil", "rio de janeiro": "Brazil",
    "brasilia": "Brazil",

    # ---- Mexico ----
    "mexico city": "Mexico", "guadalajara": "Mexico",
    "monterrey": "Mexico",

    # ---- South Africa ----
    "johannesburg": "South Africa", "cape town": "South Africa",
    "durban": "South Africa",

    # ---- Israel ----
    "tel aviv": "Israel", "jerusalem": "Israel",

    # ---- Turkey ----
    "istanbul": "Turkey", "ankara": "Turkey",

    # ---- Poland ----
    "warsaw": "Poland", "krakow": "Poland",

    # ---- Portugal ----
    "lisbon": "Portugal", "porto": "Portugal",
}


# ==========================================
# Clean Single Line
# ==========================================

# Invisible/zero-width Unicode characters. Some LinkedIn profile
# names carry one of these embedded right at the start (visible in
# the URL as "%E2%80%8Bcody-johannessen..." - the encoded form of a
# zero-width space, confirmed from a real profile URL) - likely a
# deliberate anti-scraping/anti-search-match trick some users add to
# their name. The character is invisible on screen but present in the
# scraped text, so "Cody Johannessen" actually arrives as
# "​Cody Johannessen" - one token starting with a non-letter,
# non-word character, which looks_like_name_word()'s "first char must
# be a real letter" check then rejects outright, taking the whole
# name line down with it. Strip these out of every line before
# anything else touches it.
_INVISIBLE_CHARS_PATTERN = re.compile(
    "["
    "​"  # zero width space
    "‌"  # zero width non-joiner
    "‍"  # zero width joiner
    "‎"  # left-to-right mark
    "‏"  # right-to-left mark
    "⁠"  # word joiner
    "﻿"  # zero width no-break space / BOM
    "­"  # soft hyphen
    "]"
)


def clean_line(text):

    if not text:
        return ""

    text = _INVISIBLE_CHARS_PATTERN.sub("", str(text))

    return " ".join(
        text.split()
    ).strip()


# ==========================================
# Check Location Line
# ==========================================

US_STATE_ABBREVIATIONS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc",
}


def is_location(line):

    line = line.lower()

    # Government/municipal entity NAMES ("The City of Miramar,
    # Florida", "City of Austin, Texas", "County of Los Angeles")
    # legitimately end in a real state name, which made the
    # piece-based check further down misclassify the whole line as
    # a LOCATION and strip it out as noise - even though it's
    # actually the COMPANY name for that experience entry.
    # Confirmed on a real profile (Ann Marie M., whose employer line
    # "The City of Miramar, Florida - Full-time" got dropped
    # entirely, leaving company_name blank) even though the person
    # is a City employee, not just located there. A line that
    # STARTS with "city of"/"county of"/etc. is naming an
    # organization, not describing where someone lives - never
    # treat it as a location.
    if re.match(
        r"^(the\s+)?(city|county|state|town|village|township|borough)\s+of\s+",
        line
    ):
        return False

    # "Area"/"Metropolitan"/"Metroplex"/"London" wrapper words are
    # safe to match anywhere in the line via word-boundary - they
    # never show up as part of an ordinary job title/headline.
    wrapper_words = [
        "area",
        "metropolitan",
        "metroplex",
        "london"
    ]

    if any(
        re.search(r"\b" + re.escape(word) + r"\b", line)
        for word in wrapper_words
    ):
        return True

    country_names = [
        "united states",
        "india",
        "canada",
        "japan",
        "australia",
        "new zealand",
        "singapore",
        "ireland",
        "germany",
        "france",
        "netherlands",
        "sweden",
        "norway",
        "denmark",
        "finland",
        "switzerland",
        "belgium",
        "austria",
        "brazil",
        "mexico",
        "south korea",
        "china",
        "united arab emirates",
        "united kingdom",
        "south africa",
        "israel",
        "turkey",
        "poland",
        "portugal",
    ]

    # Full country names, and state/city/region names (e.g.
    # "Denver", "Houston"), are only treated as a location if they
    # appear as their OWN comma-separated piece, e.g. "Denver,
    # Colorado, United States" or "Sandy, Utah, United States". A
    # plain word-boundary check (the old approach for country
    # names) let a country name match anywhere a job title/headline
    # happened to mention geography - e.g. "Vice President of
    # Marketing and Sales, US, Canada and Caribbean" or "Senior
    # Vice President of Sales and General Manager of the US,
    # Canada, Caribbean" - which wrongly stripped the ENTIRE job
    # title line out as a "location" (confirmed from real profiles,
    # Laura Bernier and Daniel Taylor, both at 4Life Research, whose
    # job title vanished this way and also got misread as the
    # header's location line, wrongly setting Country to "Canada").
    # It also let city/state names match inside organization names
    # that happen to contain them, e.g. "University of Denver" or
    # "Houston Methodist Hospital", wrongly stripping the company
    # name out as if it were a location/noise line.
    pieces = [p.strip() for p in line.split(",")]

    # 2-letter US state abbreviations ("Brentwood, TN") weren't
    # recognized at all, only full state names ("Tennessee") -
    # confirmed on a real profile (Noah Stanley) whose experience
    # entry has a "City, ST" location line ("Brentwood, TN") sitting
    # BEFORE the job title/date, which - unrecognized - counted as
    # real content instead of noise, tripping the "crossed into a
    # different entry" boundary before the actual date line was
    # ever reached and wrongly marking a current, dated role
    # NO LONGER.
    if any(piece in US_STATE_ABBREVIATIONS for piece in pieces):
        return True

    return any(
        piece in country_names or piece in LOCATION_TO_COUNTRY
        for piece in pieces
    )


# ==========================================
# Extract Country
# ==========================================

def extract_country(text):

    if not text:
        return ""


    text = text.lower()


    # 1. Direct country name match
    # (word boundaries - same "india" inside "indian" issue
    # as is_location() above)

    for country in COUNTRIES:

        if re.search(
            r"\b" + re.escape(country.lower()) + r"\b",
            text
        ):

            return country


    # 2. State / city / region fallback.
    # Only match if the region name appears as its OWN
    # comma-separated piece (e.g. "Denver, Colorado, United
    # States"), not merely as a word-boundary substring anywhere
    # in the text - otherwise org names like "University of
    # Denver" or "Houston Methodist Hospital" wrongly resolve to
    # a country via the city name buried inside them.

    pieces = [p.strip() for p in text.split(",")]

    for region, country in LOCATION_TO_COUNTRY.items():

        if region in pieces:

            return country


    # 3. "Greater X Area" / "X Metropolitan Area" wrapper phrases.
    # LinkedIn frequently shows ONLY this (e.g. "Greater Chicago
    # Area") with no comma and no separate country/state piece at
    # all - confirmed from a real profile (Chantrice Martin) whose
    # location was "Greater Chicago Area", which never matched
    # case 2 above because there's no comma to split on, so
    # "greater chicago area" as a whole is never equal to the bare
    # city key "chicago" in LOCATION_TO_COUNTRY. Strip the
    # "Greater"/"Metropolitan"/"Area" wrapper words off and look
    # up whatever city name is left in the middle.

    metro_match = re.search(
        r"(?:greater\s+)?([a-z][a-z\s\.\-]*?)(?:\s+metropolitan)?\s+area\b",
        text
    )

    if metro_match:

        city = re.sub(
            r"\bcity\b", "", metro_match.group(1)
        ).strip(" .-")

        if city in LOCATION_TO_COUNTRY:

            return LOCATION_TO_COUNTRY[city]

        # Compound/hyphenated metro names (e.g. "Minneapolis-St.
        # Paul", "Dallas-Fort Worth") - confirmed from a real profile
        # (Michele Gorden, "Greater Minneapolis-St. Paul Area") whose
        # country came back blank because the combined string
        # "minneapolis-st. paul" is never itself a dict key. Check
        # each dash/period-separated piece individually instead.
        for part in re.split(r"[\-\.]", city):

            part = part.strip()

            if part and part in LOCATION_TO_COUNTRY:

                return LOCATION_TO_COUNTRY[part]


    # 4. "X Metroplex" (e.g. "Dallas-Fort Worth Metroplex") - confirmed
    # from a real profile (Nanette Lyttaker) whose header location was
    # exactly this, with no comma and no "Area"/"Metropolitan" wrapper
    # for case 3 above to catch. "Metroplex" is a US-only term (no
    # other country uses it for a metro region), so any line
    # containing it can be resolved straight to United States.

    if re.search(r"\bmetroplex\b", text):

        return "United States"


    return ""


# ==========================================
# Remove LinkedIn Navigation Text
# ==========================================

_NOISE_WORDS = [
    "notifications",
    "skip to",
    "home",
    "my network",
    "jobs",
    "messaging",
    "for business",
    "try premium",
    "message",
    "follow",
    "connect",
    "contact info",
    "me",
    "sales nav",            # Sales Navigator header/button text
    "visit my website",     # Sales Navigator profile button
    "connections",          # connection count line
    "· 1st",               # connection degree badges
    "· 2nd",
    "· 3rd",
    "· 3rd+",
]

# Word-boundary patterns for single words so that e.g. \bme\b matches
# the standalone LinkedIn nav button but NOT the "me" inside "James",
# "Cameron", "Ahmed", "Megan", "Palmer", "Romero" etc. Multi-word
# phrases use plain substring matching (they can't appear in a name).
_NOISE_PATTERNS = [
    re.compile(r"\b" + re.escape(w) + r"\b" if " " not in w else re.escape(w))
    for w in _NOISE_WORDS
]


def remove_noise(lines):

    cleaned = []


    for line in lines:

        line = clean_line(line)

        if not line:
            continue


        lower = line.lower()


        # Remove menu text (word-boundary match - see _NOISE_PATTERNS)
        if any(
            p.search(lower)
            for p in _NOISE_PATTERNS
        ):
            continue


        # Remove only numbers like 25, 500+
        if re.fullmatch(
            r"[\d+]+",
            line
        ):
            continue


        cleaned.append(line)


    return cleaned


# ==========================================
# Extract Header Information
# ==========================================

# ==========================================
# Check "Open To" Badges
# LinkedIn shows an "Open to work" / "Open to
# volunteer" / "Hiring" card right under the
# profile photo. Any of these on a contact's
# profile should mark the lead INVALID.
# ==========================================

OPEN_TO_PHRASES = [
    "open to work",
    "open to volunteer"
]

# The "Hiring" badge on LinkedIn is its own short line right next
# to the name/photo - it is NOT a sentence. Matching "hiring"
# anywhere in the first lines of the page caught unrelated text
# (e.g. a headline that just happens to mention hiring) and threw
# false positives. Only count it when the line is short and is
# basically just that one word/badge.
HIRING_PHRASE = "hiring"


def find_open_to_flags(lines):

    flags = []

    window = lines[:20]

    for line in window:

        lower = line.lower().strip()

        for phrase in OPEN_TO_PHRASES:

            if phrase in lower and phrase not in flags:
                flags.append(phrase)

        # The profile-photo ring badge for "Open to work" sometimes
        # renders as a hashtag with no spaces - "#OPENTOWORK" - not
        # the spaced phrase "open to work". Confirmed from a real
        # profile (Zane Vela) where that badge was on the page but
        # never got flagged, because "opentowork" has no spaces and
        # therefore never contains the substring "open to work".
        no_space = lower.replace(" ", "").replace("#", "")

        if (
            no_space in ("opentowork", "opentovolunteer")
            and "open to work" not in flags
            and "open to volunteer" not in flags
        ):
            flags.append(
                "open to work"
                if no_space == "opentowork"
                else "open to volunteer"
            )

        if (
            HIRING_PHRASE in lower
            and len(lower.split()) <= 3
            and HIRING_PHRASE not in flags
        ):
            flags.append(HIRING_PHRASE)

        # All three of LinkedIn's "card" badges (Hiring / Open to
        # work / Open to volunteer) can render as either the short
        # one-word/one-phrase ring badge (already caught above by
        # the plain substring + word-count checks) OR a longer card
        # with its own title line followed by extra detail text -
        # e.g. "Hiring: Global Account Manager", "Open to: Providing
        # mentorship, Career advice" - confirmed from a real profile
        # (Robert Membreno's "Hiring: Global Account Manager" card)
        # that never got flagged because it's way more than 3 words.
        # The colon right after the keyword is what makes these
        # unambiguous - it's the card's own title, never a sentence
        # that just happens to mention hiring/open to.
        if (
            lower.startswith("hiring:")
            and HIRING_PHRASE not in flags
        ):
            flags.append(HIRING_PHRASE)

        if lower.startswith("open to:"):

            rest = lower.split(":", 1)[1]

            if "volunteer" in rest:

                if "open to volunteer" not in flags:
                    flags.append("open to volunteer")

            elif "open to work" not in flags:

                flags.append("open to work")

    return flags


# ==========================================
# Words that mean a line is a JOB TITLE / HEADLINE,
# not a person's name. Used to stop the name-finder
# from accidentally grabbing the headline line
# instead of the real name above it.
# ==========================================

JOB_TITLE_WORDS = [
    "director", "manager", "head", "vp", "president",
    "officer", "engineer", "lead", "analyst", "consultant",
    "chief", "ceo", "cfo", "coo", "cto", "founder", "owner",
    "partner", "specialist", "coordinator", "administrator",
    "supervisor", "executive", "associate", "senior",
    "principal", "architect", "advisor", "strategist"
]


COMMON_INITIAL_NAMES = {
    "aj", "tj", "cj", "dj", "pj", "bj", "rj", "jj", "kj", "mj",
    "jc", "jt", "bg", "cd",
}


def looks_like_name_word(word):

    core = word.rstrip(".")

    if not core:
        return False

    # Single letter initial - "H" or "H." - always OK
    if len(core) == 1:
        return core.isalpha()

    # Multi-letter ALL-CAPS token (IT, CEO, VP, HR, US...) is
    # almost always a job-title/location abbreviation, not part
    # of a person's name - reject SHORT ones. But some LinkedIn
    # users style their entire real name in all caps (e.g. "KAREN
    # CABRERA ROSALES" - confirmed from a real profile that was
    # coming back "INVALID - NAME" because this line rejected all
    # three of her real name words outright, and the header search
    # then fell through to a later line - "Las Vegas, Nevada,
    # United States" - and wrongly grabbed "Las Vegas" as the name
    # instead). Real name words are essentially never <= 3 letters
    # long in all caps, while every actual abbreviation this check
    # exists to catch (IT, HR, VP, US, CEO, CFO, COO, CTO, LLC...)
    # is - so only reject short all-caps tokens, not long ones.
    # Short 2-3 letter initials-style first names ("AJ", "TJ", "CJ",
    # "DJ", "PJ", "BJ", "RJ", "JR" as a first name rather than a
    # suffix, "JJ", "KJ", "MJ") are real, common names - confirmed
    # on a real profile (AJ Scarpaci) where "AJ" got rejected here,
    # which then rejected the whole "AJ Scarpaci" name line and let
    # a later, unrelated line ("Pittsburgh Post-Gazette" - his
    # employer, not his name) get picked up as full_name instead.
    if core.lower() in COMMON_INITIAL_NAMES:
        return True

    if core.isupper():
        return len(core) > 3 and bool(re.match(r"^[A-Z]+$", core))

    # Requiring the first letter to be uppercase was meant to reject
    # stray lowercase sentence fragments from matching as a name, but
    # it also rejects real names some LinkedIn users deliberately
    # style all-lowercase (e.g. "sonny kwan" - confirmed from a real
    # profile that came back "INVALID - NAME" even though the name
    # itself matched, because the header search never even accepted
    # "sonny"/"kwan" as name words in the first place). The
    # surrounding checks in extract_header() (2-4 word count, no
    # JOB_TITLE_WORDS present) already guard against matching a
    # random lowercase sentence, so drop the case requirement here.
    # Accented/international letters (e.g. "André", "François",
    # "Müller") were being rejected because this only matched
    # plain A-Z ASCII letters - confirmed from a real profile
    # ("André Lebel") where "André" failed this check, rejecting
    # the whole name line, and the header search fell through to
    # a later line ("Nova Scotia, Canada") that got wrongly
    # grabbed as the person's name instead. `\W`/`\w` in Python 3
    # are Unicode-aware, so negating `\W` (and digits/underscore)
    # accepts any letter in any script, not just ASCII.
    return bool(
        re.match(r"^[^\W\d_](?:[^\W\d_]|['’\-])*$", core)
    )


def extract_header(profile_text):

    result = {
        "full_name": "",
        "location": "",
        "country": "",
        "open_to_flags": []
    }


    lines = profile_text.split("\n")


    lines = remove_noise(lines)


    print("\n========== CLEAN HEADER ==========")

    for item in lines[:20]:
        print(item)

    print("==================================")


    # --------------------------------
    # Find Full Name
    # --------------------------------
    #
    # LinkedIn sometimes shows the connection-limited
    # name format, e.g. "James H." instead of
    # "James Hall". The regex below still accepts
    # this (trailing single-letter + period), and
    # also allows apostrophes/hyphens (O'Brien,
    # Smith-Jones).

    for line in lines[:10]:

        # LinkedIn sometimes packs credential suffixes after a
        # comma, e.g. "Tyler McMahon, J.D., M.S." or
        # "Brian Floyd, SET, GROL". Only the part before the
        # first comma is the actual name - match against that.

        candidate = line.split(",")[0].strip()

        # LinkedIn often appends a pronoun tag right after the name,
        # e.g. "Jane Donnelly Bastian (she/her)". The slash inside
        # the parentheses made looks_like_name_word() reject that
        # whole word, which rejected the entire candidate line as a
        # name - confirmed from a real profile where this pushed the
        # name match to fail even though "Jane Donnelly Bastian" is
        # exactly right. Strip a trailing "(...)" tag before the
        # word-by-word validation below.
        candidate = re.sub(r"\s*\([^)]*\)\s*$", "", candidate).strip()

        # Name should contain alphabets
        # and should not be a sentence

        words = candidate.split()


        # LinkedIn also sometimes packs a credential suffix
        # right after the name with no comma at all, e.g.
        # "Diane Whalen MBA". These credentials are always
        # multi-letter ALL-CAPS tokens, same as what
        # looks_like_name_word() already rejects - so strip them
        # off the END of the line instead of rejecting the whole
        # candidate. Without this, the real name line got
        # rejected outright and the loop fell through to a later,
        # unrelated line (e.g. a company name shown in a side
        # panel) and mistook it for the person's name.
        #
        # BUT: some LinkedIn users style their ENTIRE real name in
        # all caps (e.g. "KAREN CABRERA ROSALES"). In that case
        # every single word is an all-caps token, and this loop
        # kept stripping the real surname off as if it were a
        # credential - confirmed from a real profile where "KAREN
        # CABRERA ROSALES" got reduced to just "KAREN CABRERA",
        # dropping the surname and causing "INVALID - NAME" even
        # though the full name matched. Only run this stripping
        # when the line is a MIX of cases (a normal name plus one
        # trailing credential) - never when the whole candidate is
        # uniformly all caps, which signals a stylized full name
        # instead.

        all_caps_line = all(
            w.rstrip(".").isupper()
            for w in words
            if w.rstrip(".")
        )

        while (
            not all_caps_line
            and len(words) > 2
            and len(words[-1].rstrip(".")) > 1
            and words[-1].rstrip(".").isupper()
        ):

            words = words[:-1]

        candidate = " ".join(words)

        candidate_lower = candidate.lower()


        if (
            len(words) >= 2
            and len(words) <= 4
            and all(
                looks_like_name_word(word)
                for word in words
            )
            # Reject if this line is actually the headline/job title
            # (e.g. "Associate Director- IT Infrastructure").
            # Word-boundary match prevents surnames like "Whitehead"
            # from being rejected because "head" is a substring.
            and not any(
                re.search(r"\b" + re.escape(jw) + r"\b", candidate_lower)
                for jw in JOB_TITLE_WORDS
            )
        ):

            result["full_name"] = candidate
            break


    # --------------------------------
    # Find Location
    # --------------------------------

    for line in lines:

        if is_location(line):

            result["location"] = line

            result["country"] = extract_country(
                line
            )

            break


    # --------------------------------
    # Find "Open To" Badges
    # --------------------------------

    result["open_to_flags"] = find_open_to_flags(
        lines
    )


    print("\n===== HEADER RESULT =====")

    print(
        "Name:",
        result["full_name"]
    )

    print(
        "Location:",
        result["location"]
    )

    print(
        "Country:",
        result["country"]
    )

    print(
        "Open To Flags:",
        result["open_to_flags"]
    )

    print("=========================")


    return result

# ==========================================
# Check Duration Line
# ==========================================

def is_duration(line):

    line = line.lower()

    patterns = [
        "yrs",
        "yr",
        "mos",
        "mo",
        "years",
        "months"
    ]

    # Plain substring matching used to false-positive on ordinary
    # words that happen to contain one of these short patterns -
    # confirmed on a real profile (Keith Ripley) where his company
    # line "Diamond Products Limited" was thrown away entirely
    # because "mo" is a substring of "diaMOnd", making
    # strip_noise_segments() treat the whole company name as a
    # duration ("5 mo") and leaving company_name blank. Require the
    # pattern to be its own word/token instead.
    return any(
        re.search(r"\b" + re.escape(word) + r"\b", line)
        for word in patterns
    )


# ==========================================
# Check Employment Type
# ==========================================

def is_employment_type(line):

    line = line.lower()

    words = [
        "full-time",
        "part-time",
        "contract",
        "internship",
        "freelance",
        "temporary",
        "self-employed",
        "remote",
        "hybrid",
        "on-site",
        "onsite",
        "retired"
    ]

    # Same word-boundary fix as is_duration() above - substring
    # matching here could just as easily eat a company/job line that
    # merely contains one of these words as part of a longer word
    # (e.g. "Contractor", "Freelancer.com", "Remotasks").
    return any(
        re.search(r"\b" + re.escape(word) + r"\b", line)
        for word in words
    )


# ==========================================
# Check Skills Summary Line
# LinkedIn appends auto-generated skill chips
# under the latest role, e.g.
# "Software as a Service (SaaS), Quotas and +51 skills"
# These are noise, not a company/job line.
# ==========================================

def is_skills_line(line):

    return bool(
        re.search(
            r"\+\s*\d+\s*skills",
            line.lower()
        )
    )


# ==========================================
# Check Date / Duration Segment
# Catches things like "Jan 2026 - Present",
# "Nov 2023 - Jan 2026" (a date range with no
# "yrs/mos" word, so is_duration() alone misses
# it) and bare "Present".
# ==========================================

MONTH_YEAR_PATTERN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"[a-z]*\.?\s+\d{4}\b",
    re.IGNORECASE
)


# Non-capturing group on purpose - extract_start_date() below calls
# YEAR_PATTERN.findall() and expects the FULL matched year string
# back (e.g. "2024"). With a capturing group here, re.findall()
# returns only the captured group instead of the whole match - i.e.
# just "20" - which made extract_start_date() build datetime.date(20,
# 1, 1) for any bare "YYYY - Present" line with no month name (no
# match in MONTH_YEAR_PATTERN). That phantom "year 20" then made
# every such role look ~2000 years long, wrongly tripping the
# MAX_EXPERIENCE_YEARS filter - confirmed as the cause of a real
# profile (John Peirano, "2024 - Present" at AdvoCare, actually only
# ~2.5 years) being wrongly marked INVALID - EXPERIENCE.
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")


_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12
}


def extract_start_date(date_line):
    """Parse the START date from a LinkedIn date-range line.

    Handles: 'Jan 2026 - Present · 6 mos', '2018 - Present · 8 yrs', etc.
    Returns a datetime.date set to the 1st of the start month/year, or None.
    """
    # Try Month+Year first (most precise)
    m = MONTH_YEAR_PATTERN.search(date_line)
    if m:
        parts = m.group(0).split()
        month = _MONTH_ABBR.get(parts[0][:3].lower(), 1)
        year = int(parts[-1])
        return datetime.date(year, month, 1)

    # Fall back to bare year (e.g. "2018 - Present")
    years = YEAR_PATTERN.findall(date_line)
    if years:
        return datetime.date(int(years[0]), 1, 1)

    return None


_PRESENT_WORD_PATTERN = re.compile(r"\bpresent\b", re.IGNORECASE)


def is_date_segment(segment):

    if not segment:
        return False

    # Word-boundary match - a plain substring check let ordinary
    # English words containing "present" as a substring (e.g.
    # "presenter", "representative", "presentation") false-positive
    # as a date line. Confirmed from a real profile (Michele Gorden)
    # whose About paragraph mentions "Knowledgeable presenter" - that
    # got mistaken for a "... - Present" date line, which sent the
    # Present-date fallback (used when the Experience heading never
    # renders) off into her About/Featured text instead of the real
    # Experience section, producing garbage company/job title values.
    if _PRESENT_WORD_PATTERN.search(segment):
        return True

    if MONTH_YEAR_PATTERN.search(segment):
        return True

    # A bare year range like "2022 - 2024"
    if YEAR_PATTERN.search(segment) and "-" in segment:
        return True

    return False


# ==========================================
# Strip Noise From One Experience Line
#
# LinkedIn often packs noise onto the SAME line as
# real content, separated by "·", e.g.:
#   "3S Services LLC · Full-time"
#   "Jan 2026 - Present · 6 mos"
#   "Corpus Christi, Texas, United States · On-site"
#
# Checking the whole line for a noise keyword (the
# old approach) throws away real content like the
# company name whenever it shares a line with a
# noise segment. Instead, split on "·" and drop only
# the noise segments, keeping whatever real content
# remains.
# ==========================================

def strip_noise_segments(line):

    segments = [s.strip() for s in line.split("·")]

    kept = [
        s for s in segments
        if s and not (
            is_duration(s)
            or is_employment_type(s)
            or is_location(s)
            or is_skills_line(s)
            or is_date_segment(s)
        )
    ]

    return " ".join(kept).strip()


# ==========================================
# Detect Non-Standard Employment Flags
#
# strip_noise_segments() throws away words like
# "Remote" / "Contract" / "Part-time" since they
# aren't part of the company/job-title text. But
# the validator needs to know if the LATEST role
# carried one of these tags, so scan for them
# separately on the raw (pre-strip) lines, limited
# to the first few lines of the block (the latest
# role's own metadata) so an older role's tag
# doesn't get attributed to the current one.
# ==========================================

def find_employment_flags(exp_lines):

    flags = []

    window = exp_lines[:10]

    for line in window:

        stripped = line.strip()

        # Same false-positive risk as the company-name scan:
        # words like "remote", "contract", "retired", "temporary"
        # are ordinary English words that show up constantly
        # inside bullet/description sentences ("coordinated with
        # remote sales reps", "contract negotiations", "retired
        # equipment from service"...) without meaning the PERSON's
        # employment is non-standard. Only trust these words on
        # short, non-bullet structural lines (job title, date
        # line, location/workplace-type line) - this normally
        # only matters when the date line wasn't detected and the
        # whole experience block got used as a fallback, since the
        # bounded latest_block stops before the bullets start.
        if (
            stripped.startswith(("▪", "•", "-", "*"))
            or len(stripped) > 60
        ):
            continue

        for segment in line.split("·"):

            segment_lower = segment.strip().lower()

            for word in NON_STANDARD_EMPLOYMENT_WORDS:

                if word in segment_lower and word not in flags:

                    flags.append(word)

    return flags


# ==========================================
# Extract Experience Section
# ==========================================

# Sidebar/suggestion widgets ("People you may know", "Explore
# Premium profiles", suggested-profile cards, etc.) get pulled into
# the same body.inner_text() dump as the real profile content,
# especially on Sales Navigator / Premium layouts. Those widgets
# contain OTHER people's headlines and job titles, formatted just
# like a real experience entry (e.g. "National Sales Manager |
# Multiple Salesperson of the Year ... / Follow / Derek Travers") -
# confirmed from real runs where this exact text got mistaken for
# the actual contact's job title/company. Once one of these markers
# shows up, everything after it is sidebar noise, not the contact's
# own profile content, so both the "Experience" heading search and
# the Present-date fallback below must never look past it.

_SIDEBAR_MARKERS = [
    "people you may know",
    "explore premium profiles",
    "more profiles for you",
    "people also viewed",
    "show all comments",
    "people you follow",
    "ads you may be interested in",
    # Activity/feed section headers - real Experience entries never
    # appear after these. Confirmed from real runs (Zane Vela,
    # Robert Membreno) where the "Experience" heading never rendered
    # in the captured text at all, and the Present-date fallback
    # below then wandered into the Activity feed - matching a date
    # buried inside someone else's repost, a job-ad post, or an
    # Indeed.com listing, and grabbing bullet-point ad copy as the
    # "job title"/"company" (e.g. "Robert Membreno reposted this" /
    # "Cohu, Inc." came out as company/job title for a contact whose
    # real Experience section simply never loaded into the text).
    "activity",
    "key signals",
    "sales insights",
    "people who can introduce you",
    "top qualities",
    "show all posts",
]

# Same idea as _SIDEBAR_MARKERS, but these only ever appear as part
# of a longer line (a repost attribution, a job-ad call-to-action, a
# job-board listing), never as the whole line by itself - so they
# need substring matching instead of exact-line matching.
_SIDEBAR_MARKERS_CONTAINS = [
    "reposted this",
    "apply now",
    "show job",
    "indeed.com",
]

# LinkedIn timestamps its feed posts with short lines like "1yr •",
# "2mo •", "3d •" right under each reposter's name/headline. These
# sit exactly where a real date-range line ("Jan 2025 - Present")
# would, so without excluding them, a post's timestamp can itself
# get mistaken for a date line further down the noise-removal/
# fallback logic. They never carry real Experience content, so
# treat them as a cutoff marker too, same as the others above.
_FEED_TIMESTAMP_PATTERN = re.compile(
    r"^\d+\s*(yr|yrs|mo|mos|d|w)\s*•?\s*$",
    re.IGNORECASE
)


def get_experience_lines(profile_text):

    lines = [
        clean_line(x)
        for x in profile_text.split("\n")
        if clean_line(x)
    ]


    # Strip the same button/nav noise (Message, Follow, Connect,
    # "Save in Sales Navigator", "· 3rd" connection badges, etc.)
    # that extract_header() already strips for the same reason:
    # confirmed from real runs where the Present-date fallback below
    # stepped back from a date line and landed on "Message" or
    # "Save in Sales Navigator" instead of a real job title, because
    # those noise lines were sitting in between.
    lines = remove_noise(lines)


    # IMPORTANT: search for the real "Experience" heading on the
    # FULL, untruncated line list first - not the marker-truncated
    # one. Confirmed via real screenshots (Sarah Davis, Wesley Hall,
    # Nicole Gregait) that LinkedIn's normal profile layout puts an
    # Activity/"Show all posts" preview block ABOVE the real
    # Experience section, not after it. Cutting the lines off at
    # "Activity"/"Show all posts" before this search (the previous
    # version of this function) deleted the genuine Experience
    # section along with the activity feed, turning correct profiles
    # into blank results. The feed/sidebar marker cutoff below is
    # only safe to apply to the Present-date FALLBACK search, which
    # is the one that actually wandered into feed/sidebar noise.

    start = -1
    heading_found = False


    for i, line in enumerate(lines):

        if line.lower() in ("experience", "work experience"):

            start = i + 1
            heading_found = True
            break


    if start == -1:

        # Heading genuinely not found anywhere in the profile text -
        # only now build a feed/sidebar-truncated copy and run the
        # Present-date fallback against THAT, so it can never wander
        # into another person's headline, a repost, or a job-ad post
        # looking for a date to latch onto.

        fallback_lines = lines

        for i, line in enumerate(lines):

            lower = line.lower().strip()

            if (
                lower in _SIDEBAR_MARKERS
                or any(m in lower for m in _SIDEBAR_MARKERS_CONTAINS)
                or _FEED_TIMESTAMP_PATTERN.match(lower)
            ):

                fallback_lines = lines[:i]
                break

        lines = fallback_lines

        # Fallback: Sales Navigator profiles sometimes don't render
        # the "Experience" heading as a standalone line. Scan for the
        # first date line that contains "Present" and step back up to
        # 5 lines to capture the job title and company above it.
        for i, line in enumerate(lines):

            if is_date_segment(line) and _PRESENT_WORD_PATTERN.search(line):

                start = max(0, i - 5)

                print(
                    "\n[Experience heading not found - "
                    "falling back to first Present date at line",
                    i, "]"
                )

                break


    if start == -1:

        return [], False


    # Read only latest experience block
    exp = lines[start:start + 40]


    print("\n========== EXPERIENCE ==========")

    for x in exp:
        print(x)

    print("================================")


    return exp, heading_found


# ==========================================
# Extract Current Experience
# ==========================================

def extract_current_experience(profile_text):

    result = {
        "company_name": "",
        "job_title": "",
        "current_employee": False,
        "employment_flags": [],
        "additional_job_titles": [],
        "job_start_date": None,
        "heading_found": False
    }


    exp, heading_found = get_experience_lines(profile_text)

    result["heading_found"] = heading_found


    if not exp:
        return result


    # ----------------------------------
    # Company name suffixes
    # Used to detect the company line even
    # when the job title is non-English
    # ----------------------------------
    # (Defined up front, rather than after latest_block is chosen,
    # so the lookahead-candidate check below can reuse the exact
    # same "does this pair of lines confidently resolve into a job
    # title/company" logic as the main Pattern 1/2 code further
    # down.)

    COMPANY_SUFFIXES = [
        "inc", "inc.", "llc", "ltd", "ltd.",
        "co.", "co., ltd", "corp", "corp.",
        "group", "gmbh", "pte", "pte.", "pvt",
        "pvt.", "limited", "plc", "company",
        "technologies", "solutions", "services",
        "industries", "holdings"
    ]


    def looks_like_company(line):

        lower = line.lower()

        return any(
            suffix in lower
            for suffix in COMPANY_SUFFIXES
        )


    # If first line looks like company
    # and second line has job words

    job_words = [
        "director",
        "manager",
        "head",
        "vp",
        "president",
        "officer",
        "engineer",
        "lead",
        "analyst",
        "consultant",
        "secretary",
        "counsel",
        "attorney",
        "specialist",
        "representative",
        "supervisor",
        "administrator",
        "coordinator",
        "executive",
        "associate",
        "assistant",
        "controller",
        "accountant",
        "recruiter",
        "designer",
        "architect",
        "developer",
        "scientist",
        "strategist",
        "planner",
        "advisor",
        "auditor",
        "agent",
        "technician",
        "teller",
        "clerk"
    ]


    def block_meaningful_lines(block):

        lines = []

        for line in block:

            cleaned_line = strip_noise_segments(line)

            if not cleaned_line:
                continue

            if lines and cleaned_line == lines[-1]:
                continue

            lines.append(cleaned_line)

        return lines


    def is_confident_split(meaningful_lines, block):

        # Mirrors the Pattern 1 / Pattern 2 conditions further down -
        # True only when the first two lines confidently resolve
        # into a job title + company pair, as opposed to the
        # ambiguous "guess job-title-first" fallback.

        if len(meaningful_lines) < 2:
            return False

        first, second = meaningful_lines[0], meaningful_lines[1]

        first_is_company = looks_like_company(first)
        second_is_company = looks_like_company(second)

        second_is_job = any(w in second.lower() for w in job_words)
        first_is_job = any(w in first.lower() for w in job_words)

        raw_second_line = block[1] if len(block) > 1 else ""

        second_raw_is_pure_noise = (
            bool(raw_second_line)
            and not strip_noise_segments(raw_second_line)
        )

        return (
            second_raw_is_pure_noise
            or (first_is_company and not first_is_job)
            or (second_is_job and not first_is_job)
            or second_is_company
            or first_is_job
        )


    # ----------------------------------
    # Bound everything to the TOPMOST/latest experience
    # entry only.
    #
    # Each role/position on LinkedIn has exactly one date
    # line (e.g. "Jan 2025 - Present", "May 2024 - Dec
    # 2024 - 8 mos", or a bare "2018 - 2022"). The FIRST
    # date line in the experience block marks the end of
    # the latest entry - anything below it (a second
    # grouped position at the same company, an older job,
    # etc.) must not affect job title, company, employment
    # flags ("contract"/"internship"/"remote"/"retired"...),
    # or whether the person currently works there. Without
    # this boundary, an older grouped position (e.g. an
    # "Internship" listed right below the current role)
    # was bleeding into the result.
    # ----------------------------------

    date_idx = None

    end_idx = None

    block_start = 0

    # Some profiles list a current/topmost role with NO date line
    # under it at all (confirmed on a real profile - Joseph Russo's
    # "VP Sales / Strategic Content Imaging" entry has no date
    # shown, followed by an unrelated older entry "sales /
    # McGraw-Hill / 2007 - Present"). Scanning the whole block for
    # the first date line anywhere used to grab THAT LATER entry's
    # date/"Present" status and wrongly stamp it onto the current
    # entry. To stop that: once more than 2 real (non-noise) lines
    # have gone by without hitting a date, treat that as having
    # crossed into a different, later entry and stop looking -
    # `boundary_idx` remembers where that happened so latest_block
    # can be cut there instead of scanning the whole profile (which
    # also stops sidebar "More profiles for you" content from
    # bleeding into job title/company when there's no date at all).
    boundary_idx = None

    real_content_count = 0

    for idx, line in enumerate(exp):

        if is_date_segment(line):

            date_idx = idx
            break

        if strip_noise_segments(line):

            real_content_count += 1

            if real_content_count > 2:

                boundary_idx = idx
                break


    # NOTE: this used to look ahead past the topmost entry for a
    # later entry with its own explicit "Present" date, and adopt
    # THAT instead (added for Jerneshia Johnson's profile, where the
    # topmost entry "Head Teller / b1BANK" has no date but the next
    # entry "Human Resources Director / Walmart, Apr 2024 - Present"
    # is clearly her real current job). Per explicit instruction,
    # that's been removed again: only the very first/topmost entry's
    # own date counts, full stop - if IT has no date, the lead is
    # NO LONGER regardless of what a later entry shows. (Confirmed
    # on Yamila Herrera's profile: topmost entry "Human Resources
    # Director / Hialeah Hospital-Tenet Healthcare" has no date, and
    # this should be NO LONGER even though a second entry below it,
    # "HR Director / Tenet Healthcare", does have "2006 - Present".)

    if date_idx is not None:

        if end_idx is None:

            end_idx = date_idx

            # LinkedIn usually puts the location + workplace type
            # (e.g. "United States · Remote") on the line right
            # after the date/duration line, still as part of the
            # SAME entry. Cutting off exactly at the date line
            # excluded that line entirely, so a "Remote"/"Hybrid"/
            # "On-site" tag sitting there was silently dropped from
            # employment_flags. Include it when present.

            if (
                date_idx + 1 < len(exp)
                and (
                    is_location(exp[date_idx + 1])
                    or is_employment_type(exp[date_idx + 1])
                )
            ):
                end_idx = date_idx + 1

        latest_block = exp[block_start:end_idx + 1]

    else:

        # No date line found for this entry - either it genuinely
        # has none, or we stopped early above because the search
        # had wandered into a later, unrelated entry (and no
        # confident, nearby Present-dated entry was found either).
        # Bound latest_block at that point (boundary_idx) instead of
        # the whole profile, so that later entry's/sidebar's content
        # can never bleed into this entry's job title or company.
        latest_block = exp[:boundary_idx] if boundary_idx is not None else exp


    # Current employee check - ONLY the latest entry's own
    # date line decides this, not the rest of the profile.
    if date_idx is not None:

        result["current_employee"] = bool(
            _PRESENT_WORD_PATTERN.search(exp[date_idx])
        )

        result["job_start_date"] = extract_start_date(exp[date_idx])

    else:

        # No date line for the topmost/latest entry, AND (from the
        # lookahead above) no nearby entry with an explicit
        # "Present" date either. Per explicit instruction: without a
        # real date/"Present" to point to, treat this as NOT
        # confirmed current rather than presuming it is - mark it
        # NO LONGER instead of guessing VALID. (This was briefly set
        # to presume True/current for one specific evidenced case -
        # Joseph Russo, whose header headline matched his undated
        # top entry - but the general policy going forward is: no
        # date/Present found anywhere reasonable = NO LONGER, full
        # stop. A lead like that should get flagged for manual
        # review, not auto-passed.)
        result["current_employee"] = False


    meaningful = block_meaningful_lines(latest_block)


    print("\nMeaningful Experience Lines:")

    for x in meaningful[:10]:
        print(x)


    # ----------------------------------
    # Non-standard employment flags (Remote, Contract,
    # Part-time, Self-employed, Retired, etc.) - scanned
    # only within the latest entry's own block, bounded
    # above.
    # ----------------------------------

    result["employment_flags"] = find_employment_flags(
        latest_block
    )


    if len(meaningful) >= 2:

        first = meaningful[0]
        second = meaningful[1]


        first_is_company = looks_like_company(first)
        second_is_company = looks_like_company(second)

        second_is_job = any(
            word in second.lower()
            for word in job_words
        )

        first_is_job = any(
            word in first.lower()
            for word in job_words
        )


        # ----------------------------------
        # Grouped-position header detection.
        #
        # When LinkedIn groups multiple roles under one
        # company (e.g. someone promoted within the same
        # company), the RAW layout is:
        #
        #   Newfoundland Power          <- company header
        #   14 yrs 6 mos                <- total duration only
        #   Corporate Secretary         <- job title
        #   2018 - Present · 8 yrs 6 mos
        #
        # The line right after the company header is PURE
        # noise (just a duration, or "Full-time · X yrs Y
        # mos") - strip_noise_segments() reduces it to an
        # empty string, which is why it never survives into
        # `meaningful`. Neither the company name
        # ("Newfoundland Power") nor the job title
        # ("Corporate Secretary") necessarily contains a
        # recognizable suffix or job word, so the heuristics
        # below can't tell them apart and the old fallback
        # ("job title first") got it backwards. Detecting
        # this raw-layout signature lets us resolve the
        # order correctly without guessing.
        # ----------------------------------

        raw_second_line = (
            latest_block[1] if len(latest_block) > 1 else ""
        )

        second_raw_is_pure_noise = (
            bool(raw_second_line)
            and not strip_noise_segments(raw_second_line)
        )


        # ----------------------------------
        # Pattern 1:
        # Company First
        #
        # Activision Blizzard
        # Director, Global Digital Commerce
        #
        # AP Communications Co., Ltd.
        # 資料工程師   (non-English job title)
        # ----------------------------------

        # first_is_company is a substring check against generic
        # words like "solutions"/"services"/"group"/"company" - but
        # those same generic words show up constantly INSIDE real
        # job titles too (e.g. "Vice President, Pre-Sales &
        # Solutions", "Director of Client Services"), not just in
        # company names. Confirmed from a real profile (Chuck
        # Phelps) where "Vice President, Pre-Sales & Solutions" got
        # misread as the company name and "Access Healthcare" as the
        # job title, purely because of the word "Solutions" in his
        # title. A line can't simultaneously be a real company name
        # AND contain a strong job-title word ("vice president",
        # "director", etc.), so if first_is_job already fired, don't
        # let first_is_company override it.
        if (
            second_raw_is_pure_noise
            or (first_is_company and not first_is_job)
            or (second_is_job and not first_is_job)
        ):

            result["company_name"] = first
            result["job_title"] = second


        # --------------------------------
        # Pattern 2:
        # Job First
        #
        # Chief Executive Officer
        # Advance Local
        # --------------------------------

        elif second_is_company or first_is_job:

            result["job_title"] = first
            result["company_name"] = second


        else:

            # Fallback: keep original assumption
            # (job title first, company second)

            result["job_title"] = first
            result["company_name"] = second


    elif len(meaningful) == 1:

        # Only one usable line found - safer to treat
        # it as the job title than to leave both blank
        # or guess a company name

        result["job_title"] = meaningful[0]


    # ----------------------------------
    # LinkedIn sometimes packs the company name into
    # the job title line itself, e.g.
    # "Operations Manager | Gulf Coast Construction".
    # Keep only the part before "|".
    # ----------------------------------

    if "|" in result["job_title"]:

        result["job_title"] = (
            result["job_title"].split("|")[0].strip()
        )


    # ----------------------------------
    # Additional concurrent ("Present") roles grouped under
    # the SAME company.
    #
    # LinkedIn sometimes lists more than one role someone
    # currently holds at the same employer (a person wearing
    # multiple hats, e.g. "Risk & Insurance Specialist" AND
    # "Assistant Corporate Secretary" both marked Present at
    # the same company). The topmost-entry bounding above only
    # captures the FIRST of these as job_title, which made the
    # calling sheet's job title look like a mismatch when it
    # actually matched one of the person's other current roles.
    #
    # Scan forward from where the topmost entry ended, picking
    # up any other role whose own date line says "Present",
    # and stop as soon as a line that looks like a genuinely
    # different company (has a company-suffix word) shows up -
    # that marks the start of an unrelated, separate employer.
    # ----------------------------------

    additional_job_titles = []

    if date_idx is not None and end_idx is not None:

        i = end_idx + 1

        while i < len(exp):

            line = exp[i]

            stripped = line.strip()

            # looks_like_company() does a plain substring check
            # for words like "company"/"group", which also shows
            # up constantly mid-sentence inside bullet/description
            # text (e.g. "...strategies for the company's
            # insurance program..."). Only trust it as a real
            # "new employer started" signal on short, non-bullet
            # lines - actual company names aren't 60+ character
            # sentences and don't start with bullet markers.
            is_description_line = (
                stripped.startswith(("▪", "•", "-", "*"))
                or len(stripped) > 60
            )

            if (
                not is_description_line
                and looks_like_company(line)
            ):
                break

            if (
                is_date_segment(line)
                and _PRESENT_WORD_PATTERN.search(line)
            ):

                for back in range(i - 1, max(i - 4, -1), -1):

                    candidate = strip_noise_segments(
                        exp[back]
                    )

                    if candidate:

                        if candidate not in additional_job_titles:
                            additional_job_titles.append(
                                candidate
                            )

                        break

            i += 1

    result["additional_job_titles"] = additional_job_titles


    print(
        "\nCompany Found:",
        result["company_name"]
    )

    print(
        "Job Title Found:",
        result["job_title"]
    )

    print(
        "Employment Flags:",
        result["employment_flags"]
    )


    return result

# ==========================================
# Main LinkedIn Parser
# ==========================================

def parse_linkedin_data(profile_text):

    result = {
        "full_name": "",
        "job_title": "",
        "company_name": "",
        "country": "",
        "current_employee": False,
        "employment_flags": [],
        "open_to_flags": [],
        "additional_job_titles": [],
        "job_start_date": None,
        "heading_found": False
    }


    # ------------------------------------------
    # Extract Header
    # ------------------------------------------

    header = extract_header(
        profile_text
    )


    result["full_name"] = (
        header["full_name"]
    )


    result["country"] = (
        header["country"]
    )


    result["open_to_flags"] = (
        header["open_to_flags"]
    )


    # ------------------------------------------
    # Extract Latest Experience
    # ------------------------------------------

    experience = extract_current_experience(
        profile_text
    )


    result["job_title"] = (
        experience["job_title"]
    )


    result["company_name"] = (
        experience["company_name"]
    )


    result["current_employee"] = (
        experience["current_employee"]
    )


    result["employment_flags"] = (
        experience["employment_flags"]
    )


    result["additional_job_titles"] = (
        experience["additional_job_titles"]
    )

    result["job_start_date"] = (
        experience["job_start_date"]
    )


    result["heading_found"] = (
        experience.get("heading_found", False)
    )


    # ------------------------------------------
    # Country fallback from Experience
    # ------------------------------------------

    if not result["country"]:

        exp_lines, _ = get_experience_lines(
            profile_text
        )


        for line in exp_lines:

            country = extract_country(
                line
            )


            if country:

                result["country"] = country
                break


    # ------------------------------------------
    # Final Debug
    # ------------------------------------------

    print(
        "\n========== PARSED LINKEDIN DATA =========="
    )


    print(
        "Full Name:",
        result["full_name"]
    )


    print(
        "Job Title:",
        result["job_title"]
    )


    print(
        "Company:",
        result["company_name"]
    )


    print(
        "Country:",
        result["country"]
    )


    print(
        "Current Employee:",
        "YES"
        if result["current_employee"]
        else "NO"
    )


    print(
        "Employment Flags:",
        result["employment_flags"]
    )


    print(
        "Open To Flags:",
        result["open_to_flags"]
    )


    print(
        "=========================================="
    )


    return result
