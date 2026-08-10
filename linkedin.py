from playwright.sync_api import sync_playwright
import os
import re


# ==================================================
# Global Browser Variables
# ==================================================

playwright = None
browser = None
context = None
page = None


# ==================================================
# Clean Text
#
# Keep line breaks because LinkedIn profile sections
# depend on line structure.
# ==================================================

def clean_text(text):

    if not text:
        return ""

    lines = []

    for line in str(text).splitlines():

        line = " ".join(line.split())

        if line:
            lines.append(line)

    return "\n".join(lines)


# ==================================================
# Start Browser
# ==================================================

def start_browser():

    global playwright, browser, context, page

    print("\nStarting Browser...")

    playwright = sync_playwright().start()

    browser = playwright.chromium.launch(
        headless=False,
        slow_mo=300
    )


    options = {
        "viewport": {
            "width": 1400,
            "height": 900
        }
    }


    # Load LinkedIn login session
    if os.path.exists("cookies.json"):

        print("Loading saved LinkedIn session...")
        options["storage_state"] = "cookies.json"

    else:

        print("No cookies found. Login may be required.")


    context = browser.new_context(
        **options
    )


    page = context.new_page()


    page.set_default_timeout(
        40000
    )


    print("Browser Started Successfully")


# ==================================================
# Close Browser
# ==================================================

def close_browser():

    global playwright, browser, context, page


    print("\nClosing Browser...")


    try:

        if page and not page.is_closed():
            page.close()

    except Exception:
        pass


    try:

        if context:
            context.close()

    except Exception:
        pass


    try:

        if browser:
            browser.close()

    except Exception:
        pass


    try:

        if playwright:
            playwright.stop()

    except Exception:
        pass


    print("Browser Closed Successfully")


# ==================================================
# Scroll LinkedIn Profile
#
# Loads Experience, Education, Skills etc.
# ==================================================

def scroll_profile():

    global page


    print("Scrolling profile...")


    for _ in range(15):

        page.mouse.wheel(
            0,
            2500
        )

        page.wait_for_timeout(
            1200
        )


    # Scroll back to top
    page.mouse.wheel(
        0,
        -50000
    )

    page.wait_for_timeout(
        2000
    )


    print("Scrolling completed")


# ==================================================
# Get Complete Profile Text
# ==================================================

def get_profile_text():

    global page


    try:

        body = page.locator(
            "body"
        ).inner_text()


        body = clean_text(
            body
        )


        print(
            "\nProfile text length:",
            len(body)
        )


        return body


    except Exception as e:

        print(
            "Profile text extraction error:",
            e
        )

        return ""

# ==================================================
# Extract Country
# ==================================================

def extract_country(text):

    countries = [
        "United States",
        "Canada",
        "India",
        "United Kingdom",
        "Australia",
        "Singapore",
        "Germany",
        "France",
        "Netherlands",
        "Japan",
        "China",
        "Italy",
        "Spain"
    ]

    if not text:
        return ""

    text = text.lower()

    for country in countries:

        if country.lower() in text:

            print("Country Found:", country)

            return country

    return ""


# ==================================================
# Extract Profile Header
#
# Extract:
# - Full Name
# - Job Title
# - Location
# - Country
# ==================================================

def extract_header(profile_text):

    result = {
        "full_name": "",
        "job_title": "",
        "location": "",
        "country": ""
    }


    if not profile_text:
        return result


    lines = []

    for line in profile_text.split("\n"):

        line = line.strip()

        if line:
            lines.append(line)


    # -----------------------------------------
    # Remove LinkedIn navigation noise
    # -----------------------------------------

    ignore_words = [

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
        "more",
        "open to",
        "search",
        "sign in"
    ]


    clean_lines = []


    for line in lines:

        lower = line.lower()


        if any(word in lower for word in ignore_words):
            continue


        # Remove lines containing only numbers
        if line.isdigit():
            continue


        # Remove very short garbage text
        if len(line) < 3:
            continue


        clean_lines.append(line)


    print("\n========== CLEAN HEADER ==========")

    for i, item in enumerate(clean_lines[:20], 1):

        print(f"{i}. {item}")

    print("==================================")


    # -----------------------------------------
    # Find Name
    # Usually first valid line with 2-5 words
    # -----------------------------------------

    for line in clean_lines[:10]:

        words = line.split()


        if (
            2 <= len(words) <= 5
            and not any(char.isdigit() for char in line)
        ):

            result["full_name"] = line

            break


    # -----------------------------------------
    # Find Job Title
    # Usually after name
    # -----------------------------------------

    if result["full_name"]:

        try:

            name_index = clean_lines.index(
                result["full_name"]
            )


            for line in clean_lines[
                name_index + 1:
                name_index + 6
            ]:


                # Avoid locations
                if extract_country(line):
                    continue


                if (
                    len(line) > 10
                    and len(line.split()) >= 3
                ):

                    result["job_title"] = line

                    break


        except:
            pass


    # -----------------------------------------
    # Find Location / Country
    # -----------------------------------------

    for line in clean_lines:

        country = extract_country(line)


        if country:

            result["location"] = line

            result["country"] = country

            break


    print("\n===== HEADER RESULT =====")

    print(
        "Name:",
        result["full_name"]
    )

    print(
        "Job Title:",
        result["job_title"]
    )

    print(
        "Location:",
        result["location"]
    )

    print(
        "Country:",
        result["country"]
    )

    print("=========================")


    return result

# ==================================================
# Extract Current Experience
#
# Finds:
# - Current Company
# - Current Job Title
# - Current Employee Status
# ==================================================

def extract_current_experience(profile_text):

    result = {
        "company_name": "",
        "experience_job_title": "",
        "current_employee": False
    }


    if not profile_text:
        return result


    lines = [
        line.strip()
        for line in profile_text.split("\n")
        if line.strip()
    ]


    # ---------------------------------------------
    # Find Experience section
    # ---------------------------------------------

    start = -1

    for i, line in enumerate(lines):

        if line.lower() == "experience":

            start = i + 1
            break


    if start == -1:

        print("Experience section not found")

        return result


    exp_lines = lines[start:start + 50]


    print("\n========= EXPERIENCE BLOCK =========")

    for item in exp_lines[:20]:
        print(item)

    print("====================================")


    # ---------------------------------------------
    # Find current job block
    # Stop at second date range
    # ---------------------------------------------

    current_block = []


    for line in exp_lines:

        current_block.append(line)


        if "present" in line.lower():

            result["current_employee"] = True
            break


    print(
        "Current Employee:",
        "YES" if result["current_employee"] else "NO"
    )


    if not current_block:

        return result


    # ---------------------------------------------
    # Case 1:
    #
    # Ciena
    # Full-time
    # VP Head...
    # May 2022 - Present
    # ---------------------------------------------

    if (
        len(current_block) > 1 and
        "full-time" in current_block[1].lower()
    ):

        # Format:
        # Job Title
        # Company · Full-time
        # Date

        result["experience_job_title"] = current_block[0]

        company = current_block[1].split("·")[0]

        result["company_name"] = company.strip()

#VP Head of Pre-Sales Blue Planet - Global


    # ---------------------------------------------
    # Case 2:
    #
    # Director Sales
    # Ciena · Full-time
    # Oct 2020 - Present
    # ---------------------------------------------

    elif (
        len(current_block) > 1 and
        "full-time" in current_block[1].lower()
    ):

        parts = current_block[1].split("·")

        result["company_name"] = parts[0].strip()

        result["experience_job_title"] = current_block[0]


    # ---------------------------------------------
    # Better detection for mixed formats
    # ---------------------------------------------

    else:

        for i, line in enumerate(current_block):

            lower = line.lower()


            # Company line
            if "full-time" in lower:

                company = line.split("·")[0]
                result["company_name"] = company.strip()


                if i > 0:
                    result["experience_job_title"] = current_block[i-1]

                break


    print(
        "Company Found:",
        result["company_name"]
    )

    print(
        "Experience Job Title:",
        result["experience_job_title"]
    )


    return result

# ==================================================
# Main LinkedIn Scraper Function
# ==================================================

def get_linkedin_details(url):

    global page, context


    data = {
        "full_name": "",
        "job_title": "",
        "company_name": "",
        "country": "",
        "current_employee": False,
        "profile_text": ""
    }


    try:

        # -----------------------------------------
        # Recover closed page
        # -----------------------------------------

        if page is None or page.is_closed():

            print("Creating new browser page...")

            page = context.new_page()

            page.set_default_timeout(40000)


        print("\nOpening LinkedIn Profile...")


        # -----------------------------------------
        # Open LinkedIn Profile
        # -----------------------------------------

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )


        print(
            "Current URL:",
            page.url
        )


        # Wait for LinkedIn UI to render
        page.wait_for_timeout(5000)


        # -----------------------------------------
        # Scroll full profile
        # -----------------------------------------

        scroll_profile()


        page.wait_for_timeout(2000)


        # -----------------------------------------
        # Get complete page text
        # -----------------------------------------

        profile_text = get_profile_text()


        if not profile_text:

            print("No profile text found")

            return data


        data["profile_text"] = profile_text


        # -----------------------------------------
        # Extract Header
        # -----------------------------------------

        header = extract_header(
            profile_text
        )


        data["full_name"] = (
            header["full_name"]
        )


        data["job_title"] = (
            header["job_title"]
        )


        data["country"] = (
            header["country"]
        )


        # -----------------------------------------
        # Extract Experience
        # -----------------------------------------

        exp = extract_current_experience(
            profile_text
        )


        # Current company

        if exp["company_name"]:

            data["company_name"] = (
                exp["company_name"]
            )


        # Use experience title if headline is empty

        # if (
        #     not data["job_title"]
        #     and exp["experience_job_title"]
        # ):

        #     data["job_title"] = (
        #         exp["experience_job_title"]
        #     )
        # Always prefer current experience title
        if exp["experience_job_title"]:

            data["job_title"] = (
                exp["experience_job_title"]
    )


        # Current employee status

        data["current_employee"] = (
            exp["current_employee"]
        )


        # -----------------------------------------
        # Final Debug Output
        # -----------------------------------------

        print("\n========== LINKEDIN DATA ==========")

        print(
            "Name:",
            data["full_name"]
        )


        print(
            "Job Title:",
            data["job_title"]
        )


        print(
            "Company:",
            data["company_name"]
        )


        print(
            "Country:",
            data["country"]
        )


        print(
            "Current Employee:",
            "YES"
            if data["current_employee"]
            else "NO"
        )


        print(
            "===================================\n"
        )


        return data


    except Exception as e:

        print(
            "\nLinkedIn Scraping Error:",
            e
        )


        # -----------------------------------------
        # Try to recover browser page
        # -----------------------------------------

        try:

            if page and not page.is_closed():

                page.close()

        except Exception:

            pass


        try:

            page = context.new_page()

            page.set_default_timeout(
                40000
            )

            print(
                "New browser page created"
            )

        except Exception as err:

            print(
                "Page recovery failed:",
                err
            )


        return data