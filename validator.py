# validator.py

import re
import datetime
import unicodedata

import config


# ==========================================
# Normalize Text
# ==========================================

def normalize_text(text):

    if not text:
        return ""

    text = text.lower()

    # Fold accented characters to their plain ASCII equivalent
    # BEFORE stripping special characters below - e.g. "seán" needs
    # to become "sean", not "se n". Without this, the special-char
    # regex (which only keeps a-z0-9) just deletes the accented
    # letter outright since it's not ASCII, splitting one name into
    # two words and breaking the first-name comparison - confirmed
    # from a real profile (Seán Brady) that LinkedIn shows correctly
    # but kept being marked INVALID - NAME against "Sean Brady" on
    # the calling sheet.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text if not unicodedata.combining(ch)
    )

    # & and and are same
    text = text.replace("&", "and")

    # Hyphens joining two halves of one name/word need to disappear
    # entirely (not become a space) so "Wal-Mart" normalizes to
    # "walmart", matching the calling sheet's "Walmart" - confirmed
    # from a real profile (Keitha Keene) where the general
    # special-char-to-space rule below turned "Wal-Mart" into "wal
    # mart" (two words), which then failed every company_match()
    # check against "walmart" (one word) even though it's the same
    # company. Same fix helps "T-Mobile"/"7-Eleven" style names.
    text = text.replace("-", "")

    # remove special characters
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    # remove extra spaces
    return " ".join(text.split())


# ==========================================
# Name Matching
# Peter Briscoe = Peter B.
# Jerry Lucas = Jerry Lucas
# ==========================================

# LinkedIn names sometimes carry a credential
# suffix the calling sheet never has (e.g.
# "Brian Floyd, PMP", "John Smith Jr"). Without
# stripping these, the suffix becomes the "last
# name" and breaks the last-initial check.
NAME_SUFFIXES = {
    "jr", "sr", "ii", "iii", "iv",
    "phd", "md", "mba", "pmp", "cpa",
    "esq", "cfa", "cissp", "cpa", "rn"
}


def strip_name_suffixes(parts):

    while len(parts) > 2 and parts[-1] in NAME_SUFFIXES:

        parts = parts[:-1]

    return parts


# The calling sheet and LinkedIn frequently use different forms of
# the same first name (calling sheet has the formal/legal name,
# LinkedIn has the nickname people actually go by, or vice versa)
# e.g. "Timothy Cumings" (excel) vs "Tim Cumings" (LinkedIn), or
# "Jeffrey Barlow" (excel) vs "Jeff Barlow" (LinkedIn). Map common
# nicknames to a canonical form so both sides normalize to the same
# thing before comparing.
NICKNAME_TO_CANONICAL = {
    # Male
    "tim": "timothy", "timmy": "timothy",
    "jeff": "jeffrey", "geoff": "jeffrey",
    "bob": "robert", "rob": "robert", "robbie": "robert", "bobby": "robert",
    "bill": "william", "will": "william", "willy": "william",
    "billy": "william", "liam": "william",
    "dave": "david", "davy": "david",
    "mike": "michael", "mick": "michael", "mickey": "michael",
    "steve": "steven", "stevie": "steven",
    "chris": "christopher",
    "rick": "richard", "rich": "richard", "ricky": "richard", "dick": "richard",
    "dan": "daniel", "danny": "daniel",
    "tom": "thomas", "tommy": "thomas",
    "jim": "james", "jimmy": "james", "jamie": "james",
    "joe": "joseph", "joey": "joseph",
    "ken": "kenneth", "kenny": "kenneth",
    "nick": "nicholas", "nicky": "nicholas",
    "andy": "andrew", "drew": "andrew",
    "alex": "alexander",
    "sam": "samuel", "sammy": "samuel",
    "matt": "matthew",
    "greg": "gregory",
    "ron": "ronald", "ronnie": "ronald",
    "ed": "edward", "eddie": "edward", "ted": "edward", "teddy": "edward",
    "frank": "francis", "fran": "francis",
    "larry": "lawrence",
    "gabe": "gabriel",
    "ben": "benjamin", "benny": "benjamin",
    "nate": "nathaniel", "nathan": "nathaniel",
    "tony": "anthony",
    "vince": "vincent",
    "pat": "patrick",
    "phil": "philip",
    "stan": "stanley",
    "walt": "walter",
    "fred": "frederick", "freddie": "frederick",
    "charlie": "charles", "chuck": "charles", "chas": "charles",
    "harry": "harold", "hal": "harold",
    "lou": "louis", "louie": "louis",
    "marty": "martin",
    "ray": "raymond",
    "russ": "russell",
    "stu": "stuart",
    "zack": "zachary", "zach": "zachary",

    # Female
    "beth": "elizabeth", "liz": "elizabeth", "lizzie": "elizabeth",
    "betty": "elizabeth", "eliza": "elizabeth", "betsy": "elizabeth",
    "kate": "katherine", "katie": "katherine", "kathy": "katherine",
    "sue": "susan", "susie": "susan",
    "peggy": "margaret", "maggie": "margaret", "meg": "margaret",
    "marge": "margaret",
    "jen": "jennifer", "jenny": "jennifer",
    "cathy": "catherine",
    "cindy": "cynthia",
    "debbie": "deborah", "deb": "deborah",
    "patty": "patricia", "trish": "patricia", "tricia": "patricia",
    "sandy": "sandra",
    "becky": "rebecca",
    "abby": "abigail",
    "jess": "jessica", "jessie": "jessica",
    "vicky": "victoria", "vicki": "victoria",
    "carol": "caroline",
    "barb": "barbara", "barbie": "barbara",
}


def canonical_first_name(name):

    return NICKNAME_TO_CANONICAL.get(
        name,
        name
    )


def name_match(excel_name, linkedin_name):

    excel_name = normalize_text(excel_name)
    linkedin_name = normalize_text(linkedin_name)


    if not excel_name or not linkedin_name:
        return False


    excel_parts = strip_name_suffixes(
        excel_name.split()
    )

    linkedin_parts = strip_name_suffixes(
        linkedin_name.split()
    )


    # First name must match (allowing for nickname/formal-name
    # equivalents like Tim/Timothy, Jeff/Jeffrey, Beth/Elizabeth)
    if (
        excel_parts[0] != linkedin_parts[0]
        and canonical_first_name(excel_parts[0])
        != canonical_first_name(linkedin_parts[0])
    ):
        return False


    # Exact name match
    if excel_name == linkedin_name:
        return True


    # Peter Briscoe = Peter B
    if len(excel_parts) >= 2 and len(linkedin_parts) >= 2:

        excel_last = excel_parts[-1][0]
        linkedin_last = linkedin_parts[-1][0]


        if excel_last == linkedin_last:
            return True


    return False


# ==========================================
# Company Name Matching
# ==========================================

# Legal-entity suffixes that commonly differ between the calling
# sheet (often just the plain brand name) and LinkedIn (which may
# show the full registered entity name, e.g. excel "Acme" vs
# LinkedIn "Acme LLC", or excel "Acme Pvt Ltd" vs LinkedIn "Acme").
# Stripped from BOTH sides (as a trailing run of one or more of
# these words) before the substring/word-overlap checks, so the
# suffix alone never causes a false mismatch. Periods/commas are
# already gone by the time this runs (normalize_text strips them),
# so "L.L.C." and "LLC" both normalize down to "llc" first.
COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "llp", "pllc", "lp", "ltd",
    "limited", "corp", "corporation", "co", "company", "group",
    "plc", "gmbh", "srl", "sa", "sas", "bv", "nv", "ag", "kg",
    "pvt", "private", "pty", "holdings", "enterprises",
}


def strip_company_suffix(text):

    words = text.split()

    while words and words[-1] in COMPANY_SUFFIXES:
        words = words[:-1]

    return " ".join(words)


def company_match(excel_company, linkedin_company):

    excel_company = normalize_text(excel_company)
    linkedin_company = normalize_text(linkedin_company)


    if not excel_company or not linkedin_company:
        return False


    # Exact match
    if excel_company == linkedin_company:
        return True


    # Partial matching (handles suffixes like
    # "Inc", "LLC", "Ltd", "Co., Ltd" etc.)
    if excel_company in linkedin_company:
        return True


    if linkedin_company in excel_company:
        return True


    # Same as above, but with legal-entity suffixes stripped off
    # both sides first - catches cases where the suffix is the
    # ONLY difference and the substring checks above didn't already
    # match (e.g. excel "Acme Group" vs LinkedIn "Acme Inc" - no
    # substring relationship, but both reduce to "acme").
    excel_stripped = strip_company_suffix(excel_company)
    linkedin_stripped = strip_company_suffix(linkedin_company)

    if excel_stripped and linkedin_stripped:

        if excel_stripped == linkedin_stripped:
            return True

        if excel_stripped in linkedin_stripped:
            return True

        if linkedin_stripped in excel_stripped:
            return True


    # Word similarity (same approach as job title)
    excel_words = set(excel_company.split())
    linkedin_words = set(linkedin_company.split())


    common = excel_words.intersection(
        linkedin_words
    )


    similarity = (
        len(common)
        /
        max(len(excel_words), len(linkedin_words))
    )


    if similarity >= 0.70:
        return True


    # Regional/divisional LinkedIn company pages. Builders, retail
    # chains, and franchises often run a SEPARATE LinkedIn company
    # page per region/division (e.g. LinkedIn experience shows
    # "Lennar San Diego" while the calling sheet just has the brand
    # name "Lennar Homes") - confirmed from a real run where this
    # was flagged as a mismatch even though it's the same employer.
    # Word-overlap alone misses this because the only shared word
    # ("lennar") is one out of two-to-three total words, well under
    # the 70% bar. Treat it as a match when the FIRST word of both
    # names is identical and is distinctive enough to be a real
    # brand name rather than a generic word lots of unrelated
    # companies happen to start with.
    GENERIC_FIRST_WORDS = {
        "the", "national", "global", "american", "international",
        "united", "first", "city", "metro", "central", "western",
        "eastern", "northern", "southern", "general", "premier",
        "advanced", "pacific", "atlantic",
    }

    excel_first = excel_company.split()[0] if excel_company else ""
    linkedin_first = linkedin_company.split()[0] if linkedin_company else ""

    if (
        excel_first
        and excel_first == linkedin_first
        and len(excel_first) >= 4
        and excel_first not in GENERIC_FIRST_WORDS
    ):
        return True


    return False


# ==========================================
# Job Title Matching
# Match latest experience title
# ==========================================

# The calling sheet and LinkedIn often spell the same title
# differently - one side abbreviates, the other writes it out
# in full (e.g. excel says "VP, Engineering", LinkedIn says
# "Vice President, Engineering"; excel says "Sr. Manager",
# LinkedIn says "Senior Manager"). Expanding every known
# abbreviation to its full word on BOTH sides before comparing
# means these no longer count as a mismatch.
JOB_TITLE_ABBREVIATIONS = {
    "vp": "vice president",
    "svp": "senior vice president",
    "evp": "executive vice president",
    "avp": "assistant vice president",
    "sr": "senior",
    "jr": "junior",
    "mgr": "manager",
    "mgmt": "management",
    "dir": "director",
    "asst": "assistant",
    "coord": "coordinator",
    "exec": "executive",
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "coo": "chief operating officer",
    "cto": "chief technology officer",
    "cio": "chief information officer",
    "cmo": "chief marketing officer",
    "chro": "chief human resources officer",
    "ciso": "chief information security officer",
    "gc": "general counsel",
    "hr": "human resources",
    "dept": "department",
    "admin": "administrator",
    "rep": "representative",
    "spec": "specialist",
    "eng": "engineer",
    "tech": "technical",
    "it": "information technology",
    "ops": "operations",
    "biz dev": "business development",
    "bd": "business development",
    "pm": "project manager",
    "qa": "quality assurance",
}


def expand_job_title_abbreviations(text):

    if not text:
        return text

    words = text.split()

    expanded_words = [
        JOB_TITLE_ABBREVIATIONS.get(word, word)
        for word in words
    ]

    return " ".join(expanded_words)


# Dotted abbreviations like "V.P." or "C.E.O." lose their dots in
# normalize_text() (it strips all punctuation), which splits them
# into separate single-letter tokens - "v p", "c e o" - instead of
# the single token ("vp", "ceo") that JOB_TITLE_ABBREVIATIONS
# actually recognizes. That broke a real match: LinkedIn "V.P. of
# Sales and Business Development" vs calling-sheet "Vice President,
# Sales & Business Development" got marked INVALID because "v p"
# never expanded to "vice president" the way "vp" would have. Re-glue
# runs of standalone single-letter tokens back into one word before
# abbreviation expansion so dotted forms behave the same as
# undotted ones.
def merge_single_letter_runs(text):

    if not text:
        return text

    return re.sub(
        r"\b(?:[a-z]\s+){1,}[a-z]\b",
        lambda m: m.group(0).replace(" ", ""),
        text
    )


# Small filler/connector words that don't carry any actual title
# meaning ("is", "am", "are", "of", "the"...). normalize_text()
# already strips symbols like ",./@#$" - this strips these leftover
# filler words too, on BOTH the calling-sheet title and the
# LinkedIn title, before they're compared - per request, so titles
# that are worded slightly differently around the same filler words
# ("VP of Sales" vs "VP Sales") aren't wrongly flagged as INVALID.
JOB_TITLE_STOPWORDS = {
    "is", "am", "are", "was", "were", "be", "been",
    "the", "a", "an", "of", "and", "to", "for", "in", "at", "on"
}


def strip_job_title_stopwords(text):

    if not text:
        return text

    return " ".join(
        word for word in text.split()
        if word not in JOB_TITLE_STOPWORDS
    )


def job_title_match(excel_job, linkedin_job):

    excel_job = strip_job_title_stopwords(
        expand_job_title_abbreviations(
            merge_single_letter_runs(
                normalize_text(excel_job)
            )
        )
    )

    linkedin_job = strip_job_title_stopwords(
        expand_job_title_abbreviations(
            merge_single_letter_runs(
                normalize_text(linkedin_job)
            )
        )
    )


    if not excel_job or not linkedin_job:
        return False


    # Words that change the actual seniority/scope of a role, not
    # just its wording. "Vice President" and "Senior Vice
    # President" are genuinely different titles (one's a
    # promotion from the other), so a calling-sheet title that's
    # missing/adding one of these relative to LinkedIn must NOT
    # be waved through by the substring or word-overlap checks
    # below, even though those checks are deliberately lenient
    # about abbreviations and word reordering.
    RANK_MODIFIER_WORDS = {
        "senior", "junior", "chief", "deputy", "assistant",
        "associate", "lead", "principal", "interim", "acting",
        "executive"
    }

    excel_words = set(excel_job.split())
    linkedin_words = set(linkedin_job.split())

    rank_conflict = (
        excel_words ^ linkedin_words
    ) & RANK_MODIFIER_WORDS

    if rank_conflict:
        return False


    # Exact match
    if excel_job == linkedin_job:
        return True


    # Partial matching
    if excel_job in linkedin_job:
        return True


    if linkedin_job in excel_job:
        return True


    # Word similarity
    common = excel_words.intersection(
        linkedin_words
    )


    similarity = (
        len(common)
        /
        max(len(excel_words), len(linkedin_words))
    )


    # Raised from 0.70 to 0.90 at the user's request - 70% word
    # overlap was letting job titles through as "matching" when they
    # actually shared only a couple of common words (e.g. "Sales" /
    # "Manager") while describing meaningfully different roles. 90%
    # requires titles to be almost identical (differing by at most
    # one word out of ten, roughly) before being accepted as a match.
    return similarity >= 0.90


# ==========================================
# Country Matching
# ==========================================

# Common abbreviations / alternate spellings
# found in calling sheets that won't match the
# full country name LinkedIn shows
COUNTRY_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "u s": "united states",
    "u s a": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "u k": "united kingdom",
    "britain": "united kingdom",
    "great britain": "united kingdom",
    "uae": "united arab emirates",
    "south korea": "south korea",
    "korea": "south korea",

    # ISO-style 2-letter codes seen in calling sheets, mapped to
    # the full country names LinkedIn shows
    "ca": "canada",
    "au": "australia",
    "sg": "singapore",
    "de": "germany",
    "fr": "france",
    "nl": "netherlands",
    "jp": "japan",
    "cn": "china",
    "it": "italy",
    "es": "spain",
    "kr": "south korea",
    "br": "brazil",
    "mx": "mexico",
    "ie": "ireland",
    "se": "sweden",
    "no": "norway",
    "dk": "denmark",
    "fi": "finland",
    "ch": "switzerland",
    "be": "belgium",
    "at": "austria",
    "in": "india",
}


def expand_country_alias(text):

    return COUNTRY_ALIASES.get(text, text)


def country_match(excel_country, linkedin_country):

    excel_country = expand_country_alias(
        normalize_text(excel_country)
    )

    linkedin_country = expand_country_alias(
        normalize_text(linkedin_country)
    )


    return (
        excel_country == linkedin_country
    )


# ==========================================
# Main Validation Function
# ==========================================

def validate_lead(row, linkedin_data, filter_countries=None):

    """
    `filter_countries`: the normalized set of country name(s) the
    user typed at the "Enter country name(s) to validate" prompt at
    the start of the run (None if they left it blank / no filter).
    Per the user's request: when the calling sheet's OWN Country
    cell for this row is filled in, that value is always what gets
    checked against LinkedIn - filter_countries is never consulted
    in that case. filter_countries only comes into play as a
    fallback EXPECTED country when the sheet's Country cell is
    blank, so a blank cell isn't silently waved through with no
    check at all.
    """

    # ------------------------------
    # "Open To Work" badge
    # If LinkedIn shows the person as open to work, that
    # alone makes the lead invalid - skip every other check
    # and return this directly, nothing else appended.
    # ------------------------------

    open_to_flags_lower = [
        str(f).lower()
        for f in linkedin_data.get("open_to_flags", [])
    ]

    if "open to work" in open_to_flags_lower:
        return "OPEN TO WORK"


    errors = []


    # ------------------------------
    # Excel Data
    # ------------------------------

    excel_name = (
        str(
            row.get(
                "First Name",
                ""
            )
        )
        + " "
        +
        str(
            row.get(
                "Last Name",
                ""
            )
        )
    ).strip()


    excel_company = str(
        row.get(
            "Company Name",
            ""
        )
    )


    excel_job = str(
        row.get(
            "Job Title",
            ""
        )
    )


    excel_country = str(
        row.get(
            "Country",
            ""
        )
    )


    # ------------------------------
    # Name Validation
    # (checked first)
    # ------------------------------

    if not name_match(
        excel_name,
        linkedin_data.get(
            "full_name",
            ""
        )
    ):
        errors.append(
            "NAME"
        )


    # ------------------------------
    # Company Name Validation
    # (checked second)
    # ------------------------------

    company_ok = company_match(
        excel_company,
        linkedin_data.get(
            "company_name",
            ""
        )
    )

    # Fallback for companies whose LinkedIn experience entry is
    # written in a non-Latin script (e.g. "美的集团" for a company
    # the calling sheet lists as "Midea Group" / "Midea Building
    # Tech.") - confirmed from a real profile (Eric SHI, Sales
    # Director at Midea) where the scraped company_name is Chinese
    # and can never match an English calling-sheet value via
    # company_match()'s substring/word-overlap logic no matter how
    # the words are arranged. Rather than running actual translation
    # (extra dependency, network call, cost), use the LinkedIn
    # company page's own URL slug as a proxy - LinkedIn slugs are
    # almost always in Latin script/English even when the display
    # name on the profile is localized (e.g.
    # linkedin.com/company/midea-group), so try matching against
    # that before giving up.
    if not company_ok:

        company_url = linkedin_data.get("company_linkedin_url", "")

        if company_url:

            slug = company_url.rstrip("/").split("/")[-1]
            slug_name = slug.replace("-", " ").replace("_", " ").strip()

            if (
                slug_name
                and slug_name.lower() != linkedin_data.get(
                    "company_name", ""
                ).lower()
                and company_match(excel_company, slug_name)
            ):
                company_ok = True

    if not company_ok:
        errors.append(
            "COMPANY"
        )


    # ------------------------------
    # Job Title Validation
    # (checked third)
    #
    # LinkedIn sometimes lists more than one role someone
    # currently holds at the same company (e.g. "Risk &
    # Insurance Specialist" AND "Assistant Corporate
    # Secretary" both marked Present). The calling sheet's
    # job title only needs to match ONE of these, not
    # specifically whichever one happened to be the topmost
    # entry on the page.
    # ------------------------------

    job_title_candidates = [
        linkedin_data.get(
            "job_title",
            ""
        )
    ] + linkedin_data.get(
        "additional_job_titles",
        []
    )

    if not any(
        job_title_match(excel_job, candidate)
        for candidate in job_title_candidates
    ):
        errors.append(
            "JOB TITLE"
        )


    # ------------------------------
    # Country Validation
    #
    # LinkedIn sometimes just doesn't render a location line at
    # all for a profile (privacy settings, connection-degree
    # restrictions, etc.) - that's missing data, not a confirmed
    # mismatch. Flagging it the same as "COUNTRY" (which means we
    # found a DIFFERENT country than the calling sheet says)
    # caused genuinely valid leads to read as flat-out invalid.
    # Use a distinct "COUNTRY UNKNOWN" label so these can be
    # manually reviewed instead of treated as a confirmed bad
    # lead.
    # ------------------------------

    linkedin_country = linkedin_data.get(
        "country",
        ""
    )

    if not excel_country.strip():

        # Excel has no country at all. If the user typed one or
        # more expected countries at the start of the run (the
        # "Enter country name(s) to validate" prompt), use THAT as
        # the expected value instead of silently accepting whatever
        # LinkedIn shows with no check - per the user's request.
        if filter_countries:

            if not linkedin_country:
                errors.append("COUNTRY UNKNOWN")

            else:
                normalized_linkedin = expand_country_alias(
                    normalize_text(linkedin_country)
                )

                if normalized_linkedin not in filter_countries:
                    errors.append("COUNTRY")

        elif not linkedin_country:
            # No sheet country AND no run-level country filter -
            # neither side has data, genuinely unknown.
            errors.append("COUNTRY UNKNOWN")
        # else: LinkedIn has a country, main.py will backfill it
        # into the output - nothing to flag.

    elif not linkedin_country:

        # Excel has a country but LinkedIn didn't show one.
        # LinkedIn often hides location for privacy/connection
        # reasons - that's not proof the person is in the wrong
        # country. Trust the Excel value and skip this check.
        pass

    elif not country_match(
        excel_country,
        linkedin_country
    ):

        errors.append(
            "COUNTRY"
        )


    # ------------------------------
    # Current Employee Validation
    # ------------------------------

    if not linkedin_data.get(
        "current_employee",
        False
    ):
        errors.append(
            "NO LONGER"
        )


    # ------------------------------
    # Non-Standard Employment Validation
    # (Remote, Contract, Part-time, Retired, etc. on
    # the latest/topmost role only -> marked INVALID)
    # ------------------------------

    employment_flags = linkedin_data.get(
        "employment_flags",
        []
    )

    for flag in employment_flags:
        errors.append(
            flag.upper()
        )


    # ------------------------------
    # "Open To Volunteer / Hiring" Badge Validation
    # ("Open to work" is handled above with an early
    # return, so it never reaches here.)
    # ------------------------------

    for flag in open_to_flags_lower:

        if flag == "open to work":
            continue

        errors.append(
            flag.upper()
        )


    # ------------------------------
    # Experience Years Check
    #
    # Only runs when the user set MAX_EXPERIENCE_YEARS
    # at the start of the run. If the person has been
    # in their latest job title for MORE than that many
    # years, the lead is marked INVALID - EXPERIENCE.
    # If LinkedIn didn't expose a start date, the check
    # is skipped (not a failure).
    # ------------------------------

    max_years = getattr(config, "MAX_EXPERIENCE_YEARS", None)

    if max_years is not None:

        job_start = linkedin_data.get("job_start_date")

        if job_start:

            today = datetime.date.today()
            years_in_role = (today - job_start).days / 365.25

            print(
                f"Experience check: {years_in_role:.1f} yrs in role "
                f"(max allowed: {max_years})"
            )

            if years_in_role > max_years:
                errors.append(
                    f"EXPERIENCE MORE THAN {max_years} YEARS"
                )


    # ------------------------------
    # Final Result
    # ------------------------------

    if not errors:

        return "VALID"


    return (
        "INVALID - "
        + ", ".join(errors)
    )