# linkedin_scraper/scraper.py

import re

from .browser import (
    get_page,
    create_new_page,
    SessionExpiredError
)

from .utils import (
    clean_text,
    scroll_profile,
    extract_country
)

from .parser import (
    parse_linkedin_data,
    extract_current_experience
)


# ==========================================
# Get Full LinkedIn Profile Text
# ==========================================

def get_profile_text(page):

    try:

        body = page.locator("body").inner_text()

        body = clean_text(body)

        print("\nProfile text length:", len(body))

        return body

    except Exception as e:

        print("Profile text extraction failed:", e)

        return ""


# ==========================================
# Fallback: Read Location Straight From The DOM
#
# Whole-page body.inner_text() occasionally drops the
# top-card location line entirely - confirmed by a user
# screenshot showing "Albuquerque, New Mexico, United
# States" plainly visible on the live page while the same
# text never showed up in two separate scrape attempts
# (including a longer-wait retry). That rules out a pure
# render-timing issue, so instead of waiting longer, read
# the location directly off the known top-card element
# instead of relying on the whole-body text dump.
# ==========================================

def get_location_from_dom(page):

    # Hard-coded class-name selectors are brittle - LinkedIn
    # renames its CSS classes often enough that a guessed
    # selector list can silently match nothing (which is exactly
    # what happened: none of the previous guesses ever found
    # anything). Anchor on the <h1> (the person's name) instead,
    # which is far more stable, and pull the text from the few
    # DOM levels around it where the headline/location row lives.

    try:

        blocks = page.evaluate(
            """
            () => {
                const h1 = document.querySelector('h1');
                if (!h1) return null;

                const results = [];
                let node = h1.parentElement;

                for (let level = 0; level < 5 && node; level++) {
                    results.push(node.innerText || '');
                    node = node.parentElement;
                }

                return results;
            }
            """
        )

    except Exception as e:

        print("DOM location lookup raised an exception:", e)

        return []

    if blocks is None:

        print("DOM location lookup: no <h1> found on page")

        return []

    print(
        "DOM location lookup: scanning",
        len(blocks),
        "ancestor block(s) around <h1>"
    )

    candidates = []

    for level, block in enumerate(blocks):

        if not block:
            print(f"  level {level}: empty")
            continue

        print(
            f"  level {level} raw text:",
            repr(block[:200])
        )

        for raw_line in block.split("\n"):

            line = clean_text(raw_line).strip()

            # A real location line is short and comma-separated
            # (e.g. "Albuquerque, New Mexico, United States").
            # Anything longer/without a comma is almost certainly
            # an unrelated bit of nearby text (headline, button
            # labels, etc.) picked up by walking the DOM tree.
            if (
                line
                and "," in line
                and len(line) < 100
                and line not in candidates
            ):
                candidates.append(line)

    print("DOM location candidates found:", candidates)

    return candidates


# ==========================================
# Fallback: Fetch Experience From Its Own Detail Page
#
# Root cause of profiles like Olivia Bianchi, Karen Cabrera Rosales,
# Laura Bernier, Rachel Lam, Thomas Wojan and Chuck Phelps coming back
# INVALID - COMPANY, JOB TITLE even though the Experience section is
# plainly visible on the live page: scroll_profile()'s lazy-scroll
# loop sometimes never gets the "Experience" heading to actually
# render in body.innerText() before it gives up (profiles with a big
# About/Activity/Posts block above Experience push it far enough down
# that the scroll+wait budget runs out first). Since that failure is
# structural (the scroll loop always does the same thing regardless
# of how long we wait beforehand), retrying with a longer initial
# wait_ms - which is all get_linkedin_details() did before - produced
# the exact same blank result both times, confirmed by the console
# log showing identical profile_text lengths on both attempts.
#
# LinkedIn exposes the SAME experience list on its own dedicated
# subpage - "<profile-url>/details/experience/" - which renders with
# nothing (no About, no Activity/Posts feed) above the experience
# list, so there's nothing to scroll past. Used only as a last-resort
# fallback when the main profile page's Experience section didn't
# come through.
# ==========================================

def _experience_detail_url(profile_url):

    base = profile_url.split("?")[0].rstrip("/")

    if "/details/" in base:
        base = base.split("/details/")[0]

    return base + "/details/experience/"


def get_experience_details_text(profile_url, page):

    detail_url = _experience_detail_url(profile_url)

    try:

        print(f"\nExperience section not found on main profile - "
              f"falling back to detail page: {detail_url}")

        page.goto(
            detail_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(3000)

        # This subpage has no About/Activity content above the list,
        # so a handful of scroll passes is enough to load every
        # entry (unlike the main profile page).
        for _ in range(6):

            page.mouse.wheel(0, 2500)

            try:
                page.evaluate("window.scrollBy(0, 2500)")
            except Exception:
                pass

            page.wait_for_timeout(500)

        text = get_profile_text(page)

        return text

    except Exception as e:

        print("Experience detail page fetch failed:", e)
        return ""


# ==========================================
# Open LinkedIn Profile
# ==========================================

def open_profile(url, page=None, wait_ms=3000):

    # If no specific page was handed to us (old single-tab
    # flow), fall back to the one global page. When a page IS
    # passed in (multi-tab/threaded flow), use it as-is and
    # never touch the global page - that would step on other
    # worker threads.
    if page is None:

        page = get_page()

        if page is None or page.is_closed():

            print("Creating new browser page...")

            page = create_new_page()


    print("\nOpening LinkedIn Profile...")


    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )


    print("Current URL (right after goto):", page.url)


    # Let LinkedIn load dynamic data
    page.wait_for_timeout(wait_ms)


    # URN-style profile links (e.g.
    # ".../in/ACwAAAC_VkQBZFNgkAL9SUCrtT0TpgyXiskI6l4") are
    # supposed to get redirected by LinkedIn to the real vanity
    # URL once it resolves who the URN belongs to. If page.url
    # STILL looks like the raw URN after the page has settled,
    # the redirect never happened - almost always because the
    # link is dead/private/wrong rather than anything this
    # scraper can fix, so flag it loudly instead of silently
    # returning an empty result that looks like a generic
    # scrape failure.
    final_url = page.url

    print("Current URL (after wait):", final_url)

    urn_match = re.search(
        r"linkedin\.com/in/(acwaa[a-z0-9_-]+)",
        final_url,
        re.IGNORECASE
    )

    if urn_match:

        # LinkedIn resolves this internal URN format to the real
        # vanity profile URL via a CLIENT-SIDE redirect that can take
        # noticeably longer than the fixed wait_ms above - especially
        # with multiple worker tabs competing for the CPU/network.
        # Confirmed on a real batch where every single URN-style
        # lead (Julie Miller, Kate Foley, Joseph Patten, and ~30
        # others) came back blank/"NO LONGER" here, even though every
        # one of those profiles opens and loads completely fine when
        # checked manually in a real logged-in browser tab - so the
        # link isn't broken/private, the redirect just hadn't
        # finished yet when we checked. Poll for a few more seconds
        # before concluding it's a dead link.
        for _ in range(6):

            page.wait_for_timeout(1000)

            final_url = page.url

            if not re.search(
                r"linkedin\.com/in/acwaa[a-z0-9_-]+",
                final_url,
                re.IGNORECASE
            ):

                print("URN redirected after extra wait:", final_url)
                break

        urn_match = re.search(
            r"linkedin\.com/in/(acwaa[a-z0-9_-]+)",
            final_url,
            re.IGNORECASE
        )

    if urn_match:

        print(
            "WARNING: this profile URL is still in LinkedIn's "
            "internal URN format after loading - it never got "
            "redirected to a real vanity profile URL ("
            + urn_match.group(1) +
            "). This usually means the link is broken, private, "
            "or no longer resolves to a real profile, not a "
            "scraper bug. Worth checking this lead's URL "
            "manually."
        )


    # If we landed on LinkedIn's authwall ("Join LinkedIn" / sign
    # in page) instead of the actual profile, the session's
    # cookies are no longer logged in. This is NOT a per-profile
    # problem - retrying or recreating the tab will hit the same
    # authwall on every remaining profile in this session, which
    # is exactly what produced long runs of identical blank "Join
    # LinkedIn" results across many different contacts in a row.
    # Raise immediately so the caller can stop using this session
    # and rotate to a different LinkedIn account instead of
    # quietly burning through the rest of the batch.
    #
    # Same deal for a "checkpoint" URL - LinkedIn's rate-limit/
    # "unusual activity" interstitial (a verification code prompt
    # or "is this you?" puzzle), same page browser.py already
    # handles during the INITIAL login flow. That handling only
    # covers session start-up though - mid-batch, LinkedIn can
    # still redirect a profile navigation to a checkpoint page
    # after too many rapid requests, and without this check that
    # checkpoint page just got scraped like a blank profile: no
    # name, no job title, no company, no country - which is what
    # produced runs of several contacts in a row all coming back
    # "INVALID - NAME, COMPANY, JOB TITLE, COUNTRY UNKNOWN, NO
    # LONGER" (confirmed from a real run: Brian Mcelyea, Chad
    # Wasserman, David D., Duane Lovelace, Erica Rocha, Evelyn
    # Franco-Motta all failed identically in a row). A real, no
    # longer employed lead fails on its OWN - it never takes out
    # five unrelated contacts after it in lockstep like that.
    if (
        "authwall" in final_url.lower()
        or "/login" in final_url.lower()
        or "checkpoint" in final_url.lower()
    ):

        raise SessionExpiredError(
            "LinkedIn session hit the authwall/login/checkpoint "
            "page. Cookies have expired, this account was logged "
            "out, or LinkedIn is asking for extra verification - "
            "needs a fresh login/cookies file, not a retry."
        )


    return page


# ==========================================
# Main LinkedIn Scraper
# ==========================================

def get_linkedin_details(url, excel_job="", page=None, raise_errors=False):

    result = {

        "full_name": "",
        "job_title": "",
        "company_name": "",
        "country": "",
        "current_employee": False,
        "profile_text": "",
        "final_url": "",
        "company_linkedin_url": ""

    }


    # Up to 2 attempts. A blank/empty result on the first try
    # almost always means the page hadn't finished rendering yet
    # (more likely now that profiles load faster + multiple tabs
    # can be competing for resources) rather than a real "no
    # data" profile - so retry once with a longer wait before
    # giving up and marking the lead invalid.

    max_attempts = 2

    for attempt in range(1, max_attempts + 1):

        try:

            # -----------------------------
            # Open profile
            # -----------------------------

            wait_ms = 3000 if attempt == 1 else 6000

            page = open_profile(url, page, wait_ms=wait_ms)

            result["final_url"] = page.url


            # -----------------------------
            # Scroll complete profile
            # -----------------------------

            scroll_profile(page)


            # -----------------------------
            # Get profile text
            # -----------------------------

            profile_text = get_profile_text(page)


            if not profile_text:

                print("No profile text found")

                if attempt < max_attempts:

                    print("Retrying with a longer wait...")
                    continue

                return result


            # -----------------------------
            # Parse LinkedIn data
            # -----------------------------

            parsed_data = parse_linkedin_data(
                profile_text
            )


            # If literally nothing useful came out (no name, no
            # job title, no company), the profile almost
            # certainly hadn't loaded yet - retry once instead of
            # accepting a blank result.
            #
            # Also retry when job_title AND company are BOTH blank
            # even if the name parsed fine. The header (name,
            # headline, location) renders fast, but the Experience
            # section is lazy-loaded further down the page and can
            # still be missing by the time inner_text() is captured
            # - especially with 3 parallel tabs competing for
            # resources. Requiring ALL THREE fields blank (the old
            # check) almost never fired in practice, because the
            # name nearly always parsed even when Experience hadn't
            # rendered yet - confirmed against real runs where
            # full_name came back correct but job_title/company_name
            # were both empty, and no retry happened.

            looks_empty = (
                not parsed_data.get("full_name")
                or (
                    not parsed_data.get("job_title")
                    and not parsed_data.get("company_name")
                )
            )

            # Retrying the main profile page with a longer wait only
            # helps when the miss was a one-off render-timing fluke.
            # When job_title/company are blank because the Experience
            # heading never rendered in body.innerText() at all (the
            # structural case - see get_experience_details_text() doc
            # above), every retry hits the exact same wall. Try the
            # dedicated Experience detail subpage BEFORE burning the
            # last retry / giving up, since it doesn't depend on
            # scrolling past About/Activity content at all.
            # IMPORTANT: don't gate this only on job_title/company_name
            # both being blank. The internal "first Present date"
            # fallback inside get_experience_lines() can latch onto
            # About-section/noise text and produce a NON-blank but
            # GARBAGE job_title/company_name when the real "Experience"
            # heading never actually loaded in profile_text at all -
            # confirmed from a real profile (Joe Comeau) where the
            # About section text got mistaken for the experience block
            # ("Company: TFT Global Inc., Job Title: NDHS" - "NDHS" was
            # actually his school, not a job title), so job_title/
            # company_name were both non-empty and this check never
            # fired, even though the real "Director of Applications"
            # role was never scraped. heading_found being False means
            # the genuine "Experience"/"work experience" heading was
            # never located, regardless of what the fallback guessed -
            # that's the real signal to retry via the detail subpage.
            if (
                parsed_data.get("full_name")
                and (
                    (
                        not parsed_data.get("job_title")
                        and not parsed_data.get("company_name")
                    )
                    or not parsed_data.get("heading_found")
                )
            ):

                # Use page.url (where open_profile() actually landed),
                # NOT the original `url` argument. For a URN-style
                # link (linkedin.com/in/ACwAA...) LinkedIn resolves
                # the real vanity URL via a client-side redirect on
                # the MAIN profile page, but that redirect never
                # touches `url` itself - it's still the raw URN
                # string. Building the detail-page URL by appending
                # "/details/experience/" to that URN base hits
                # LinkedIn's generic "Something went wrong - Refresh
                # the page" error page instead of the real experience
                # list (confirmed on two real profiles - Andrew Hub
                # and Austin Bolles, both from URN-style sheet links -
                # where this produced an identical ~1266-character
                # error page for both, versus a correct ~4200-char
                # experience list when built from page.url instead).
                # Since parsed_data["full_name"] is already known good
                # at this point (checked above), the page reliably
                # finished resolving before we get here.
                exp_text = get_experience_details_text(page.url, page)

                if exp_text:

                    # IMPORTANT: parse exp_text on its OWN, do not
                    # splice it onto profile_text. The detail page's
                    # captured text already contains its own genuine
                    # "Experience" heading line (right after its own
                    # name/headline at the top of that page) - if we
                    # concatenate profile_text + a manually-inserted
                    # "Experience" marker + exp_text, get_experience_
                    # lines() finds OUR inserted marker first (it
                    # comes earlier in the combined text) and reads
                    # the 40 lines after THAT, which land on exp_text's
                    # own "Try for ₹0" / name / headline noise instead
                    # of the real job/company list further down -
                    # confirmed from a real run (Laura Bernier) where
                    # this produced "Company: Laura Bernier, Job
                    # Title: Try for ₹0". Parsing exp_text alone lets
                    # it find ITS OWN "Experience" heading correctly,
                    # same as it would on a normal profile page.

                    experience = extract_current_experience(exp_text)

                    if (
                        experience.get("job_title")
                        or experience.get("company_name")
                    ):

                        parsed_data["job_title"] = experience["job_title"]
                        parsed_data["company_name"] = experience["company_name"]
                        parsed_data["current_employee"] = experience["current_employee"]
                        parsed_data["employment_flags"] = experience["employment_flags"]
                        parsed_data["additional_job_titles"] = experience["additional_job_titles"]
                        parsed_data["job_start_date"] = experience["job_start_date"]

                        # Country fallback from the detail page's own
                        # location lines, same as parse_linkedin_data()
                        # already does for the main profile page.
                        if not parsed_data.get("country"):

                            for line in exp_text.split("\n"):

                                country = extract_country(line)

                                if country:
                                    parsed_data["country"] = country
                                    break

                    # Go back to the original profile page so the
                    # rest of this function (company URL lookup,
                    # final_url) still reads the right page.
                    try:
                        page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=60000
                        )
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        print(
                            "Could not navigate back to profile "
                            "page after detail-page fallback:", e
                        )

                    looks_empty = (
                        not parsed_data.get("full_name")
                        or (
                            not parsed_data.get("job_title")
                            and not parsed_data.get("company_name")
                        )
                    )

            if looks_empty and attempt < max_attempts:

                print(
                    "Scraped profile looks empty/incomplete "
                    "(missing name, or missing both job title "
                    "and company) - retrying with a longer wait..."
                )
                continue


            # Country sometimes comes back blank even when name/
            # job/company all loaded fine. Before burning a full
            # retry (re-opening the page, waiting again), try
            # reading the location straight off the known top-card
            # DOM element - cheap, and catches cases where the
            # whole-body text dump just drops that one line even
            # though it's plainly visible on the live page.

            if not parsed_data.get("country"):

                dom_candidates = get_location_from_dom(page)

                for dom_location in dom_candidates:

                    dom_country = extract_country(
                        dom_location
                    )

                    if dom_country:

                        print(
                            "Country recovered from DOM "
                            "location lookup:",
                            dom_location
                        )

                        parsed_data["country"] = dom_country

                        if not parsed_data.get("location"):
                            parsed_data["location"] = dom_location

                        break


            # If the DOM lookup above also came up empty, fall
            # back to one more full retry with a longer wait - the
            # location line under the person's headline can still
            # render slightly later than the rest of the page on
            # rare occasions.

            if (
                not parsed_data.get("country")
                and attempt < max_attempts
            ):

                print(
                    "Country not found - "
                    "retrying with a longer wait..."
                )
                continue


            result["profile_text"] = profile_text

            result.update(parsed_data)

            # Extract company LinkedIn URL from the already-loaded
            # profile page DOM (used later if lead is VALID).
            result["company_linkedin_url"] = get_company_url_from_page(
                page,
                result.get("company_name", "")
            )

            # Nothing usable on the profile page itself (no
            # hyperlinked company logo/name) - search LinkedIn for
            # the company directly by name instead of leaving this
            # blank, so VALID leads still get Industry/Company Size
            # enrichment.
            if (
                not result["company_linkedin_url"]
                and result.get("company_name")
            ):

                result["company_linkedin_url"] = search_company_url(
                    page,
                    result["company_name"]
                )


            # -----------------------------
            # Debug output
            # -----------------------------

            print("\n========== FINAL LINKEDIN DATA ==========")

            print("Name:", result["full_name"])

            print("Job Title:", result["job_title"])

            print(
                "Additional Job Titles:",
                result.get("additional_job_titles", [])
            )

            print("Company:", result["company_name"])

            print("Country:", result["country"])

            print(
                "Current Employee:",
                "YES" if result["current_employee"] else "NO"
            )

            # Was missing from this summary even though it's a real
            # field that feeds validate_lead() and can add REMOTE/
            # CONTRACT/PART-TIME/etc. to the INVALID reasons - a lead
            # could come back INVALID - REMOTE with nothing here
            # explaining why, since this print block never showed
            # employment_flags at all (only debug_profile.py's own
            # separate summary loop happened to print it, by dumping
            # every dict key generically).
            print(
                "Employment Flags:",
                result.get("employment_flags", [])
            )

            print(
                "Open To Flags:",
                result.get("open_to_flags", [])
            )

            print("Company URL:", result["company_linkedin_url"])

            print("==========================================")


            return result


        except SessionExpiredError:

            # No point retrying within this function - the
            # session is dead and every retry would hit the same
            # authwall. Always bubble this straight up so the
            # caller (worker pool / main.py) can stop this session
            # and rotate accounts, regardless of raise_errors.
            print(
                "\nLinkedIn session expired - stopping retries "
                "for this profile and bubbling up to caller."
            )
            raise

        except Exception as e:

            print("\nLinkedIn Scraping Error:", e)

            if attempt < max_attempts:

                print("Retrying after error...")
                continue


            # In multi-tab/threaded mode (raise_errors=True), the
            # caller owns the page and is responsible for
            # recovering it (recreating a fresh page for that
            # worker). We just bubble the error up instead of
            # touching shared state.
            if raise_errors:
                raise


            # Old single-tab flow: try to recover the global page
            try:

                create_new_page()

                print("Browser page recovered")

            except Exception as err:

                print(
                    "Page recovery failed:",
                    err
                )


            return result


    return result


# ==========================================
# Get Company LinkedIn URL from Profile Page
#
# While still on the person's profile page, reads the DOM to
# find the LinkedIn company page URL linked from their current
# experience entry. Tries to match by company name first so we
# don't accidentally grab a sponsor/ad link.
# ==========================================

def get_company_url_from_page(page, company_name=""):

    try:

        company_url = page.evaluate(
            """
            (companyName) => {
                const links = Array.from(
                    document.querySelectorAll('a[href*="/company/"]')
                );
                const lower = companyName.toLowerCase();

                // Prefer a link whose visible text matches the company name
                if (lower) {
                    for (const link of links) {
                        const text = (link.textContent || '').toLowerCase();
                        if (text.includes(lower) || lower.includes(text.trim())) {
                            return link.getAttribute('href');
                        }
                    }
                }

                // NOTE: deliberately no "fall back to the first
                // company link on the page" here anymore. That used
                // to grab literally any "/company/" link anywhere in
                // the DOM - including sidebar ads, "More profiles
                // for you", and "People you may know" widgets that
                // have nothing to do with this person's employer.
                // Confirmed on a real profile (Travis Neal, Walmart)
                // whose Experience entry has no real hyperlinked
                // company icon (just a generic placeholder), so the
                // name-match above found nothing and the old
                // fallback grabbed an unrelated IBM link from
                // elsewhere on the page - writing IBM's Industry/
                // Company Size onto a Walmart employee's row. A
                // missing company URL (no About-page enrichment) is
                // far less harmful than a confidently wrong one.
                return null;
            }
            """,
            company_name
        )

        if not company_url:
            return ""

        # Make absolute and strip query params / trailing slash
        if company_url.startswith("/"):
            company_url = "https://www.linkedin.com" + company_url

        company_url = company_url.split("?")[0].rstrip("/")

        return company_url

    except Exception as e:

        print("Company URL extraction error:", e)
        return ""


# ==========================================
# Search LinkedIn For a Company's Page
#
# Fallback for when the profile page itself has no usable company
# link (e.g. the company logo/name isn't hyperlinked at all - a
# generic placeholder icon instead of the real company logo,
# confirmed on a real profile - Travis Neal/Walmart). Rather than
# grabbing some unrelated link off the page (the old, wrong
# behavior) or giving up with no enrichment data at all, look the
# company up directly by the name already parsed from the profile
# and take LinkedIn's own top search result for it.
# ==========================================

def search_company_url(page, company_name):

    if not company_name:
        return ""

    try:

        search_url = (
            "https://www.linkedin.com/search/results/companies/"
            "?keywords=" + company_name.replace(" ", "%20")
        )

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2000)

        company_url = page.evaluate(
            """
            () => {
                const link = document.querySelector(
                    'a[href*="/company/"]'
                );
                return link ? link.getAttribute('href') : null;
            }
            """
        )

        if not company_url:
            return ""

        if company_url.startswith("/"):
            company_url = "https://www.linkedin.com" + company_url

        return company_url.split("?")[0].rstrip("/")

    except Exception as e:

        print("Company search fallback failed:", e)
        return ""


# ==========================================
# Get Company Details from LinkedIn About Page
#
# Navigates to the company's /about/ page and extracts:
#   - Industry
#   - Company size range  (e.g. "10,001+ employees")
#   - Associated members  (e.g. "193 associated members on LinkedIn")
# ==========================================

# ==========================================
# Get Company Revenue From ZoomInfo
#
# Per request: for a VALID lead, search Google for
# "<company name> zoominfo", open the first ZoomInfo result, and
# read the "Revenue" figure off its public company overview page
# (e.g. "$156.1 Million") - the same figure visible without logging
# into ZoomInfo.
#
# CAVEAT: this drives an actual Google search with an automated
# browser. Google can and does show CAPTCHAs / block automated
# queries, especially after many searches in a row - this hasn't
# been verified against a live, sustained batch run. If you start
# seeing "Revenue" come back empty for many leads in a row, check
# whether Google is showing a CAPTCHA/"unusual traffic" page instead
# of real results before assuming this function is broken.
# ==========================================

def get_company_revenue_from_zoominfo(company_name, page):

    if not company_name:
        return ""

    try:

        query = company_name + " zoominfo"

        search_url = (
            "https://www.google.com/search?q="
            + query.replace(" ", "+")
        )

        print(f"\nSearching Google for ZoomInfo revenue: {query}")

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2000)

        # Google shows a cookie/consent wall ("Before you continue
        # to Google Search") on a fresh/automated session before it
        # will show real results at all - try to dismiss it so the
        # actual search results can render. Harmless no-op if it's
        # not present.
        try:
            for label in ["Accept all", "I agree", "Accept"]:
                btn = page.get_by_role("button", name=label)
                if btn.count() > 0:
                    btn.first.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    break
        except Exception:
            pass

        # First organic result whose link points at a ZoomInfo
        # company page ("zoominfo.com/c/<slug>/<id>").
        result_url = page.evaluate(
            """
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                for (const link of links) {
                    const href = link.getAttribute('href') || '';
                    if (href.includes('zoominfo.com/c/')) {
                        return href;
                    }
                }
                return null;
            }
            """
        )

        if not result_url:

            # Diagnostics - since "No ZoomInfo result found" was
            # coming back 100% of the time across every company in
            # a real run (Lucas Oil, Ludia, LumenData, etc. - all
            # verified to have real ZoomInfo pages), something
            # structural is very likely blocking real results from
            # rendering at all (a CAPTCHA/"unusual traffic" page, or
            # the consent wall not getting dismissed above). Print
            # what the page actually shows so this is diagnosable
            # from the console output instead of guessing blind.
            print("No ZoomInfo result found in Google search results.")
            print("Diagnostic - page title:", page.title())
            print("Diagnostic - page URL:", page.url)
            try:
                snippet = page.locator("body").inner_text()[:300]
                print("Diagnostic - page text snippet:", repr(snippet))
            except Exception:
                pass

            return ""

        print(f"Opening ZoomInfo page: {result_url}")

        page.goto(
            result_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2000)

        revenue = page.evaluate(
            """
            () => {
                const bodyText = document.body.innerText;
                const match = bodyText.match(
                    /Revenue\\s+(\\$[0-9.,]+\\s*(Million|Billion|Thousand|Trillion)?)/i
                );
                return match ? match[1].trim() : null;
            }
            """
        )

        print("Revenue        :", revenue or "(not found)")

        return revenue or ""

    except Exception as e:

        print("ZoomInfo revenue lookup failed:", e)
        return ""


def get_company_details(
    company_url,
    page,
    company_name="",
    want_industry=True,
    want_emp_size=True,
    want_revenue=True
):

    result = {
        "industry": "",
        "company_size_range": "",
        "company_size_members": "",
        "revenue": ""
    }

    if not company_url and not company_name:
        return result

    # Only bother opening LinkedIn's About page at all if Industry
    # or Company Size was actually asked for - per request, an
    # enrichment field the user didn't select shouldn't just be
    # silently fetched anyway.
    if company_url and (want_industry or want_emp_size):

        about_url = company_url.rstrip("/") + "/about/"

        print(f"\nFetching company About page: {about_url}")

        try:

            page.goto(
                about_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(3000)

            text = page.locator("body").inner_text()

            text = clean_text(text)

            lines = [l.strip() for l in text.split("\n") if l.strip()]

            SECTION_HEADERS = {
                "website", "industry", "company size", "headquarters",
                "founded", "specialties", "overview", "type"
            }

            for i, line in enumerate(lines):

                lower = line.lower()

                # Industry
                if want_industry and lower == "industry" and i + 1 < len(lines):
                    candidate = lines[i + 1].strip()
                    if candidate.lower() not in SECTION_HEADERS:
                        result["industry"] = candidate

                # Company size — range on the next line, member count
                # on the line after that (if it contains "associated")
                if want_emp_size and lower == "company size" and i + 1 < len(lines):

                    range_line = lines[i + 1].strip()

                    if (
                        "employee" in range_line.lower()
                        or "+" in range_line
                        or re.search(r"\d+\s*[-–]\s*\d+", range_line)
                    ):
                        result["company_size_range"] = range_line

                    if i + 2 < len(lines):
                        members_line = lines[i + 2].strip()
                        if (
                            "associated" in members_line.lower()
                            or "member" in members_line.lower()
                        ):
                            m = re.search(r"[\d,]+", members_line)
                            result["company_size_members"] = m.group().replace(",", "") if m else members_line

            print("Industry       :", result["industry"])
            print("Company Size   :", result["company_size_range"])
            print("Members        :", result["company_size_members"])

        except Exception as e:

            print("Company details scraping error:", e)

    # Revenue comes from ZoomInfo (via Google search), not LinkedIn -
    # runs regardless of whether the LinkedIn About-page fetch above
    # succeeded, as long as we have a company name to search for AND
    # it was actually asked for.
    if want_revenue and company_name:
        result["revenue"] = get_company_revenue_from_zoominfo(
            company_name,
            page
        )

    return result
