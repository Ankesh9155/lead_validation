# linkedin_scraper/apify_scraper.py
#
# Replaces the Playwright-based scraper with the Apify
# "harvestapi/linkedin-profile-scraper" actor.
#
# - No LinkedIn cookies / login required (no account ban risk)
# - Scrapes all profiles in one batched Actor run instead of
#   opening a real browser per profile
# - Output is mapped into the same shape the rest of the
#   pipeline (validator.py) already expects:
#       {
#           "full_name": "",
#           "job_title": "",
#           "company_name": "",
#           "country": "",
#           "current_employee": False
#       }

import re

from apify_client import ApifyClient

import config


# ==========================================
# Safe field getter
#
# Depending on the installed apify-client version, the object
# returned by client.actor(...).call(...) (and sometimes dataset
# items) can be a plain dict OR a typed object (e.g. a "Run"
# model) that doesn't support .get(). This helper works with
# either shape, and tries multiple possible key names (Apify
# mixes camelCase and snake_case across versions/endpoints).
# ==========================================

def _get(obj, *keys):

    if obj is None:
        return None

    for key in keys:

        if isinstance(obj, dict):
            value = obj.get(key)
        else:
            value = getattr(obj, key, None)

        if value is not None:
            return value

    return None


# ==========================================
# Extract LinkedIn public identifier from URL
# e.g. https://www.linkedin.com/in/williamhgates/ -> williamhgates
# ==========================================

def extract_public_identifier(url):

    if not url:
        return ""

    match = re.search(r"linkedin\.com/in/([^/?]+)", url, re.IGNORECASE)

    if not match:
        return ""

    return match.group(1).strip().lower()


# ==========================================
# Normalize a raw LinkedIn URL for use as a
# lookup key (case/slash/query-string only -
# doesn't try to resolve redirects).
# ==========================================

def normalize_url(url):

    if not url:
        return ""

    return url.strip().lower().rstrip("/")


# Some calling sheets contain LinkedIn's internal URN-style
# profile URL instead of the normal vanity one, e.g.
# "https://linkedin.com/in/ACwAAAC_VkQBZFNgkAL9SUCrtT0TpgyXiskI6l4"
# instead of "https://www.linkedin.com/in/siarhei-vasilevich-
# b86113115/". LinkedIn redirects the URN form to the real
# profile, so Apify still scrapes the right person - but the
# *identifier* it reports back (publicIdentifier) is the real
# vanity slug, not the URN string from the sheet. Looking results
# up purely by re-deriving an identifier from the input URL (the
# old approach) breaks for exactly this case. Matching on the
# literal submitted URL instead (which Apify echoes back via the
# "query" field) sidesteps the whole problem regardless of which
# URL format the sheet uses.


# ==========================================
# Build empty result shape
# ==========================================

def _empty_result():

    return {
        "full_name": "",
        "job_title": "",
        "company_name": "",
        "country": "",
        "current_employee": False,
        "employment_flags": [],
        "open_to_flags": [],
        "profile_text": ""
    }


# ==========================================
# Parse one Apify dataset item into our schema
# ==========================================

def parse_apify_item(item):

    result = _empty_result()

    if not item:
        return result


    # --------------------------------
    # Full Name
    # --------------------------------

    first_name = _get(item, "firstName", "first_name") or ""
    last_name = _get(item, "lastName", "last_name") or ""

    full_name = (
        first_name + " " + last_name
    ).strip()

    # LinkedIn sometimes packs credential suffixes into the name
    # after a comma, e.g. "Brian Floyd, SET, GROL". Only the part
    # before the first comma is the actual name.
    if "," in full_name:
        full_name = full_name.split(",")[0].strip()

    result["full_name"] = full_name


    # --------------------------------
    # Latest / Current Experience
    # --------------------------------

    experience = _get(item, "experience") or []

    if experience:

        latest = experience[0]

        position = _get(latest, "position", "title") or ""

        # Position text is sometimes
        # "Job Title | extra detail, more detail"
        # Keep only the title portion before "|"
        if "|" in position:
            position = position.split("|")[0].strip()

        result["job_title"] = position

        result["company_name"] = (
            _get(latest, "companyName", "company_name") or ""
        )

        end_date = _get(latest, "endDate", "end_date") or {}

        end_date_text = _get(end_date, "text") or ""

        result["current_employee"] = (
            end_date_text.strip().lower() == "present"
        )

        # --------------------------------
        # Non-Standard Employment Flags
        # (Remote, Contract, Part-time, etc.)
        # --------------------------------

        employment_type = (
            _get(latest, "employmentType", "employment_type") or ""
        )

        workplace_type = (
            _get(latest, "workplaceType", "workplace_type") or ""
        )

        combined = (
            employment_type + " " + workplace_type
        ).strip().lower().replace(" ", "-")

        flags = []

        for word in config.NON_STANDARD_EMPLOYMENT_WORDS:

            if word in combined and word not in flags:
                flags.append(word)

        result["employment_flags"] = flags

    else:

        # Fall back to currentPosition block
        # (usually just has companyName)
        current_position = _get(item, "currentPosition", "current_position") or []

        if current_position:

            result["company_name"] = (
                _get(current_position[0], "companyName", "company_name") or ""
            )


    # --------------------------------
    # "Open To Work / Volunteer / Hiring" badge
    # (best-effort - field names not confirmed
    # against the live harvestapi schema since this
    # path isn't the active scraper right now)
    # --------------------------------

    open_to_work = _get(item, "openToWork", "open_to_work")
    headline = (_get(item, "headline") or "")

    open_to_flags = []

    if open_to_work:
        open_to_flags.append("open to work")

    for phrase in ["open to work", "open to volunteer", "hiring"]:
        if phrase in headline.lower() and phrase not in open_to_flags:
            open_to_flags.append(phrase)

    result["open_to_flags"] = open_to_flags


    # --------------------------------
    # Country
    # --------------------------------

    location = _get(item, "location") or {}
    parsed_location = _get(location, "parsed") or {}

    country = (
        _get(parsed_location, "country")
        or _get(parsed_location, "countryFull", "country_full")
        or ""
    )

    result["country"] = country


    return result


# ==========================================
# Batch-scrape all LinkedIn profile URLs
# Returns: { public_identifier: parsed_result }
# ==========================================

def get_linkedin_details_batch(urls):

    results = {}

    urls = [u for u in urls if u]

    if not urls:
        return results


    if not config.APIFY_API_TOKEN:

        raise RuntimeError(
            "APIFY_API_TOKEN is not set. "
            "Set it as an environment variable before running "
            "(see config.py for instructions)."
        )


    client = ApifyClient(config.APIFY_API_TOKEN)


    # Apify actors handle large input lists fine in one run,
    # but we batch anyway to keep memory/debug output manageable
    # and to allow partial progress visibility.

    batch_size = config.APIFY_BATCH_SIZE

    for start in range(0, len(urls), batch_size):

        batch = urls[start:start + batch_size]

        print(
            f"\nScraping LinkedIn batch {start + 1}-{start + len(batch)} "
            f"of {len(urls)} via Apify..."
        )

        run_input = {
            "profileScraperMode": config.APIFY_PROFILE_MODE,
            "queries": batch
        }

        run = client.actor(config.APIFY_ACTOR_ID).call(
            run_input=run_input
        )

        status = _get(run, "status")
        status_message = _get(run, "statusMessage", "status_message")

        dataset_id = _get(run, "defaultDatasetId", "default_dataset_id")

        if not dataset_id:
            print("Apify run returned no dataset id, skipping batch")
            continue

        before_count = len(results)

        for item in client.dataset(dataset_id).iterate_items():

            parsed = parse_apify_item(item)

            # Primary key: the literal URL we submitted, echoed
            # back via "query". This is the most reliable match -
            # it works no matter what URL format the sheet used
            # (vanity slug, URN-style ID, trailing slash, etc.)
            # since it doesn't depend on re-deriving an identifier
            # that might not match what Apify reports back.
            query = _get(item, "query")

            if isinstance(query, str) and query.strip():

                results[normalize_url(query)] = parsed

            elif query:

                # Some actor versions echo "query" as an object
                # instead of the raw string.
                query_url = (
                    _get(query, "url")
                    or _get(query, "profileUrl", "profile_url")
                    or ""
                )

                if query_url:
                    results[normalize_url(query_url)] = parsed


            # Fallback key: the public identifier the scrape
            # itself resolved to. Kept for backward compatibility
            # and as a second chance if the "query" echo above
            # isn't present in this actor version's output.
            query_obj = query if isinstance(query, dict) else {}

            public_id = (
                _get(item, "publicIdentifier", "public_identifier")
                or _get(query_obj, "publicIdentifier", "public_identifier")
                or ""
            )

            public_id = public_id.strip().lower()

            if public_id:
                results[public_id] = parsed

        print(f"Batch complete: {len(results)} profiles parsed so far")

        # If we sent URLs but got nothing back, this is almost
        # always an Apify account/billing limit (e.g. the actor's
        # free-trial run limit, or the free-plan item cap) rather
        # than a bug. Surface it clearly and stop, instead of
        # silently continuing with empty data for every contact.
        if len(results) == before_count:

            detail = f"status={status}"
            if status_message:
                detail += f", message={status_message}"

            raise RuntimeError(
                f"Apify run for this batch returned 0 profiles ({detail}). "
                "This usually means an Apify account/billing limit was "
                "hit (free-trial run limit, free-plan item cap, or out "
                "of credit) - not a bug in this script. Check "
                "https://console.apify.com/billing and the actor's page, "
                "then re-run main.py once it's resolved."
            )


    return results


# ==========================================
# Lookup helper used by main.py
# ==========================================

def lookup_result(results, url):

    # Try the exact URL we submitted first (handles URN-style
    # URLs and any other format the sheet might use - see the
    # comment above normalize_url()).
    direct = results.get(normalize_url(url))

    if direct is not None:
        return direct


    # Fall back to the old public-identifier match, for results
    # keyed that way (older actor output shapes, or items where
    # the "query" echo wasn't available).
    public_id = extract_public_identifier(url)

    if public_id and public_id in results:
        return results[public_id]


    return _empty_result()
