# LinkedIn Lead Validator — Project Document

---

## 1. Project Overview

LinkedIn Lead Validator is an automation tool that validates sales lead data from an Excel calling sheet against live LinkedIn profiles. It takes a list of contacts (name, job title, company, country, LinkedIn URL) and confirms whether each lead is still valid — meaning the person is currently employed at the listed company in the listed role and country.

**Problem it solves:** Sales teams work from large calling sheets that go stale fast. People change jobs, get promoted, retire, or go freelance. Calling an invalid lead wastes time. This tool automates the verification step by cross-referencing every contact against their live LinkedIn profile and stamping each row VALID or INVALID with a specific reason.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Browser Automation | Playwright (sync API) |
| Data Handling | Pandas, openpyxl |
| Scraping (alternative) | Apify API (harvestapi/linkedin-profile-scraper) |
| Concurrency | Python threading (multi-tab parallel scraping) |
| Config | Plain Python config file |
| Session Storage | JSON (cookies + daily usage tracking) |

---

## 3. Architecture

```
main.py
  ├── excel_handler.py        — read/write Excel file (pandas + openpyxl)
  ├── validator.py            — compare Excel data vs LinkedIn data
  ├── config.py               — all settings in one place
  └── linkedin_scraper/
        ├── browser.py        — Playwright browser lifecycle
        ├── scraper.py        — navigate LinkedIn, extract page text
        ├── parser.py         — parse raw page text into structured data
        ├── utils.py          — shared helpers (clean text, scroll, extract country)
        └── apify_scraper.py  — Apify API integration (paid alternative)
```

**Data flow:**
1. `main.py` reads the Excel sheet into a Pandas DataFrame
2. For each unvalidated row it calls `scraper.py` → `browser.py` (Playwright) to open the LinkedIn profile
3. The raw page text is passed to `parser.py` to extract name, job title, company, country, employment flags
4. While still on the profile page, the DOM is queried to extract the company's LinkedIn page URL
5. `validator.py` compares the parsed LinkedIn data against the Excel row
6. If the result is **VALID**, the tool navigates to the company's LinkedIn `/about/` page and extracts industry, company size range, and associated member count
7. All results are written back to the DataFrame (Validation 2, Industry, Company Size, Company Members, Company LinkedIn URL)
8. The DataFrame is saved back to Excel

---

## 4. Key Features

### Scraper Modes
- **Playwright (free):** Uses a saved LinkedIn session (cookies.json) and a real Chromium browser. Slower but free.
- **Apify (paid):** Sends LinkedIn URLs to the Apify cloud actor and gets back structured profile data. Faster, no login required.

### Parallel Scraping (Multi-tab)
Configured via `PLAYWRIGHT_WORKERS` in `config.py`. When set above 1, the tool spawns N worker threads, each running its own completely independent Playwright instance (browser + context + page). This avoids Playwright's sync API thread-safety limitation — a page created on one thread cannot be driven from another, so each worker owns its full stack end-to-end.

### Daily Lead Limit & Account Rotation
LinkedIn rate-limits and bans accounts that make too many profile views in a day. The tool:
- Tracks how many profiles have been checked today per LinkedIn account in `linkedin_usage.json`
- Stops when the `DAILY_LEAD_LIMIT` is reached
- Logs out the current LinkedIn account
- Asks for a second account's cookies file to continue
- The count persists across re-runs on the same day (JSON file, keyed by cookies filename + date)

### Resume / Incremental Processing
Rows that already have a value in the `Validation 2` column are skipped. Running `main.py` again on the same file automatically picks up where it left off. No re-validation of already-processed contacts.

### Country Filter
At startup the user can enter one or more countries (full name or abbreviation — "US", "UK", "in" all work). Only contacts from those countries are processed in that run. Rows with no country in the sheet are passed through (the country gets filled in from LinkedIn after scraping).

### Auto LinkedIn URL Update
After scraping a VALID lead, if LinkedIn redirected the original URL to a canonical vanity URL, the `Linkedin URL` column in the Excel output is updated with the final URL.

### Auto-save
Progress is saved to the output Excel file every 25 contacts so work is never lost if the run is interrupted.

### Auto-login
If `cookies.json` is missing or the LinkedIn session has expired, and `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` are set, the tool logs in automatically and saves a fresh session file. For the CLI these come from `config.py`; the web GUI (`webapp/`) instead lets you save them from the dashboard's "LinkedIn login" card (persisted to `webapp/data/linkedin_credentials.json`), which populates `config.LINKEDIN_EMAIL` / `config.LINKEDIN_PASSWORD` at startup and on every save/clear - see `webapp/app.py`'s `_apply_linkedin_credentials()`.

### Company Enrichment (VALID leads only)
For every lead marked VALID, the tool performs a second scrape — this time on the company's own LinkedIn page. It navigates to the `/about/` section and extracts:
- **Industry** — e.g. `Technology, Information and Internet`
- **Company Size** — the employee range LinkedIn shows, e.g. `10,001+ employees`
- **Company Members** — the exact LinkedIn member count, e.g. `193 associated members on LinkedIn`
- **Company LinkedIn URL** — the canonical company page URL

These are written as four additional columns in the output Excel file, giving the sales team richer context on each valid contact without any manual lookup. Company enrichment only runs for VALID leads to avoid wasting time on leads that will be discarded anyway.

---

## 5. Validation Logic (validator.py)

Each lead is checked across five dimensions in order:

| Check | Logic |
|---|---|
| **Open To Work** | If LinkedIn shows the "Open To Work" badge → immediately return `OPEN TO WORK` (no further checks) |
| **Name** | First name must match (supports nicknames: Tim = Timothy, Jeff = Jeffrey, etc.). Last name initial must match. Credential suffixes (PMP, MBA, PhD) are stripped before comparison. |
| **Company** | Exact match, substring match, or ≥70% word overlap. Handles Inc / LLC / Ltd suffixes. |
| **Job Title** | Abbreviations expanded (VP → Vice President, Sr → Senior, etc.) before comparing. Rank modifier words (Senior, Junior, Lead, Principal) are protected — adding or removing one counts as a mismatch even if the rest overlaps. ≥70% word overlap otherwise. |
| **Country** | Aliases expanded (US/USA → United States, UK → United Kingdom, IN → India, etc.). If LinkedIn didn't show a country at all, result is `COUNTRY UNKNOWN` (not `INVALID`) so it can be reviewed manually rather than discarded. |
| **Current Employee** | LinkedIn must show a "Present" date in the most recent experience entry. |
| **Employment Flags** | If the latest role shows: Remote, Contract, Part-time, Freelance, Retired, Internship, Self-employed → appended to the INVALID reason. |

**Result format examples:**
- `VALID`
- `INVALID - NAME, COMPANY`
- `INVALID - JOB TITLE, NO LONGER`
- `INVALID - REMOTE`
- `OPEN TO WORK`
- `COUNTRY UNKNOWN`
- `NO LINKEDIN`
- `SCRAPING ERROR`

---

## 6. Parser (parser.py) & Company Scraper (scraper.py)

**Profile parsing** — LinkedIn profiles are scraped as raw page text (no structured API). The parser works by:

1. **Finding the Experience section** — locates the "Experience" heading in the text and reads the block below it
2. **Identifying the current role** — searches for a line containing "Present" (LinkedIn's date format for active roles) and walks back to find the job title and company
3. **Country extraction** — checks 50+ US states, Canadian provinces, UK regions, Indian states, etc. mapped to their parent country. LinkedIn often shows only a city/region ("New York Metropolitan Area", "Karnataka, India") without the country name itself.
4. **Employment flags** — scans the current role block for keywords like "remote", "contract", "part-time", "retired"
5. **Open To Work / Hiring badges** — detected from known LinkedIn UI text patterns

**Company URL extraction** — `get_company_url_from_page(page, company_name)` runs a JavaScript `querySelectorAll('a[href*="/company/"]')` on the already-loaded profile page DOM. It first tries to match a link whose visible text contains the already-extracted company name. If no text match is found, it falls back to the first `/company/` link on the page. The result is a full absolute URL (`https://www.linkedin.com/company/...`).

**Company About page parsing** — `get_company_details(company_url, page)` navigates to `company_url/about/`, reads `body.inner_text()`, and scans for known section header keywords (`"industry"`, `"company size"`). The line immediately following each header is the value. For company size, two consecutive lines are captured — the range line (contains "employees" or a number pattern) and the members line (contains "associated").

---

## 7. Technical Challenges & How They Were Solved

**1. Playwright thread safety**
Playwright's sync API ties every browser object to the thread that created it. Early versions shared one browser across worker threads, causing "greenlet.error: cannot switch to a different thread" and nearly every navigation failing with `net::ERR_ABORTED`. Fix: each worker thread creates and owns its own complete Playwright stack (playwright instance → browser → context → page). They all load the same `cookies.json` so they share the LinkedIn session.

**2. LinkedIn dynamic rendering**
LinkedIn renders profile data progressively via JavaScript. Grabbing the page text immediately after `goto()` often returned empty or partial content. Fix: scroll the full page after loading (triggers lazy-loaded sections like Experience), then read `body.inner_text()`. A retry mechanism re-opens the profile with a longer wait if the result looks empty.

**3. Country missing from page text**
The whole-body `inner_text()` dump sometimes drops the location line even when it's visible on the live page. Fix: a DOM-level fallback reads the location directly from the element near the `<h1>` (person's name), which is far more stable than relying on the full-body text dump.

**4. Name mismatches from real data**
Calling sheets use formal names; LinkedIn often shows nicknames (Tim vs Timothy, Jeff vs Jeffrey, Beth vs Elizabeth). Built a nickname→canonical mapping table of ~80 common English nicknames so both sides normalize to the same root name before comparing.

**5. Daily LinkedIn rate limits**
LinkedIn restricts accounts that browse too many profiles too quickly. Fix: configurable `DAILY_LEAD_LIMIT`, persisted across runs in a JSON file keyed by cookies filename + date. When the limit is hit, the account is logged out of LinkedIn and the script asks for a second account to continue the run.

**6. URN-style LinkedIn URLs**
Some calling sheets contain internal URN-format LinkedIn profile links (`/in/ACwAAAC_VkQB...`) instead of vanity URLs. These often never resolve (dead/private profiles). The scraper detects this pattern after page load and logs a clear warning instead of returning a silent empty result.

**7. Extracting the correct company link from a profile page**
LinkedIn profile pages contain many `/company/` links — sidebar ads, "People also viewed" cards, footer links. A naive `querySelectorAll('a[href*="/company/"]')[0]` would often grab the wrong one. Fix: the selector loops through all matching anchors and picks the first one whose visible text content matches the company name already extracted from the profile. Only if no text match is found does it fall back to the first link. This makes the right company page picked reliably even on profiles with multiple company references.

**8. Company size has two separate data points**
LinkedIn shows company size as two distinct lines on the About page: a range ("10,001+ employees") and an associated member count ("193 associated members on LinkedIn"). These are not in a structured format — just lines of text. The parser anchors on the "Company size" header, reads the next line as the range (validated by checking for "employees" or a number-dash-number pattern), and the line after that as the member count (validated by checking for "associated" or "member").

---

## 8. Configuration (config.py)

All behavior is controlled from a single file — no CLI flags needed:

```python
FILE_NAME          # Input Excel file path
SHEET_NAME         # Which sheet to read
OUTPUT_FILE        # Where to save validated output
SCRAPER_MODE       # "playwright" or "apify"
PLAYWRIGHT_WORKERS # Number of parallel browser tabs (1 = sequential)
DAILY_LEAD_LIMIT   # Max LinkedIn profiles per account per day
COOKIE_FILE        # Path to saved LinkedIn session cookies
LINKEDIN_EMAIL     # Auto-login credentials (if cookies expire)
LINKEDIN_PASSWORD
HEADLESS           # Run browser visibly or in background
```

---

## 9. Output Columns Written to Excel

| Column | Populated for | Example value |
|---|---|---|
| `Validation 2` | All processed rows | `VALID` / `INVALID - JOB TITLE, NO LONGER` |
| `Country` | Rows where sheet had no country | `United States` (backfilled from LinkedIn) |
| `Linkedin URL` | VALID leads where URL redirected | `https://www.linkedin.com/in/john-doe` |
| `Industry` | VALID leads only | `Technology, Information and Internet` |
| `Company Size` | VALID leads only | `10,001+ employees` |
| `Company Members` | VALID leads only | `193 associated members on LinkedIn` |
| `Company LinkedIn URL` | VALID leads only | `https://www.linkedin.com/company/microsoft` |

---

## 10. Project Structure Summary

```
lead_finder/
├── main.py                  # Entry point, orchestration, threading
├── config.py                # All settings
├── validator.py             # Validation logic (name/company/job/country)
├── excel_handler.py         # Read/write Excel with pandas
├── linkedin_usage.json      # Daily usage counter (auto-managed)
├── cookies.json             # LinkedIn session (auto-managed)
└── linkedin_scraper/
    ├── browser.py           # Playwright browser start/stop/login
    ├── scraper.py           # Profile navigation and retry logic
    ├── parser.py            # Text parsing → structured data
    ├── utils.py             # Shared helpers
    └── apify_scraper.py     # Apify cloud API integration
```

---

## 11. What I Built / My Contribution

- Designed and built the entire system end-to-end from scratch
- Solved the Playwright thread-safety problem for parallel multi-tab scraping
- Built the fuzzy matching engine (name nicknames, job title abbreviations, country aliases, company partial matching)
- Implemented the daily rate-limit tracking system with account rotation
- Built the two-mode scraper architecture (free Playwright vs paid Apify) with a single config toggle
- Handled LinkedIn's dynamic rendering quirks (lazy loading, missing DOM elements, URN redirects)
- Added resume capability so large sheets can be processed across multiple days/runs without re-work
- Built the company enrichment pipeline — DOM-based company URL extraction from profile pages, company About page scraper, and automatic write-back of Industry, Company Size, Company Members, and Company LinkedIn URL for every valid lead

---

## 12. Potential Interview Questions & Answers

**Q: Why did you choose Playwright over Selenium?**
Playwright is more reliable for modern JavaScript-heavy SPAs like LinkedIn. It has a cleaner async/sync API, better auto-wait behavior, and first-class support for saving/loading browser session state via `storage_state` — which is exactly how the LinkedIn session persistence works here.

**Q: How does the multi-threading work?**
Python's `threading` module is used. Each worker thread creates its own independent Playwright instance. A shared `queue.Queue` holds all the rows to process. Workers pull from it until empty. A `threading.Lock` protects all writes back to the shared Pandas DataFrame. Progress and daily usage counters are also updated under the same lock.

**Q: Why not use LinkedIn's official API?**
LinkedIn's official API is restricted to approved partners and doesn't provide the profile-level employment data needed for this use case (current title, company, employment type flags). The scraper uses an already-logged-in personal session, which is consistent with normal human browsing behavior.

**Q: How do you handle LinkedIn blocking?**
Three layers: (1) `slow_mo` and `wait_for_timeout` to pace navigation naturally, (2) a configurable daily limit per account, (3) account rotation — when one account hits its daily limit, the script logs it out of LinkedIn (not just closes the browser) and prompts for another account's cookies to continue.

**Q: What does the Apify mode add?**
It offloads scraping to a cloud actor (no local browser, no LinkedIn login, no ban risk). The trade-off is cost ($4 per 1,000 profiles) and the free plan cap of 10 profiles per run. The main.py code is identical for both modes — the scraper backend is swapped at import time based on `SCRAPER_MODE` in config.

---

**Q: How did you handle the case where LinkedIn redirects a profile URL to a different URL?**
LinkedIn uses internal URN-format URLs for some profiles (`/in/ACwAAAC_VkQB...`). After `page.goto()` settles, I read `page.url` to get the final URL. If it still looks like a URN after the wait, I log a warning — that usually means the profile is dead or private. For valid leads, the final canonical URL is written back into the Excel sheet so future runs use the clean URL directly.

---

**Q: How do you make sure progress is not lost if the script crashes mid-run?**
Two mechanisms: (1) the DataFrame is auto-saved to the output Excel file every 25 contacts, and (2) on the next run, any row that already has a non-empty `Validation 2` value is skipped. So even a hard crash only loses the last batch of up to 25 rows. The daily usage counter in `linkedin_usage.json` is also written after every single contact, not just at the end.

---

**Q: What happens when a contact has no LinkedIn URL in the sheet?**
The scraper checks for a blank or "nan" URL before doing anything. If missing, it immediately sets the result to `NO LINKEDIN` and moves on — no browser navigation happens and it does not count against the daily limit.

---

**Q: How does the name matching handle edge cases?**
Four layers: (1) normalize both sides — lowercase, strip special characters, collapse spaces; (2) strip credential suffixes like PhD, PMP, MBA so they don't become a fake "last name"; (3) expand nicknames to canonical form — both Tim and Timothy map to "timothy" before comparing; (4) allow last-initial matching — "Peter Briscoe" matches "Peter B." because only the first letter of the last name needs to match.

---

**Q: Why is "COUNTRY UNKNOWN" a separate result from "INVALID - COUNTRY"?**
`INVALID - COUNTRY` means LinkedIn showed a country and it was the wrong one. `COUNTRY UNKNOWN` means LinkedIn showed nothing at all — no location line rendered on the page. These are very different situations. An account with privacy settings or a low connection degree may simply not show location to the scraper. Treating that as a confirmed mismatch would incorrectly discard potentially valid leads. The distinct label lets the sales team review those rows manually instead.

---

**Q: How does the job title matching avoid false positives from abbreviations?**
Before any comparison, both sides are run through an abbreviation expander — VP → Vice President, Sr → Senior, Dir → Director, CEO → Chief Executive Officer, etc. This means "VP of Sales" and "Vice President of Sales" match correctly. However, rank modifier words (Senior, Junior, Lead, Principal, Executive) are protected — if one side has "Senior" and the other doesn't, that's a real difference in seniority and must not be waved through.

---

**Q: Why does each worker thread need its own Playwright instance instead of sharing one browser?**
Playwright's sync API uses Python greenlets internally. The greenlet is tied to whichever thread called `sync_playwright().start()`. Any page object created from that call can only be safely driven from that same thread. Sharing one browser across threads causes "greenlet.error: cannot switch to a different thread" at runtime, and almost every `page.goto()` fails with `net::ERR_ABORTED`. The only safe solution is one complete Playwright stack per thread.

---

**Q: How is the daily limit enforced across multiple re-runs of the script on the same day?**
`linkedin_usage.json` stores the count per cookies file per date:
```json
{ "cookies.json": { "date": "2026-06-24", "count": 87 } }
```
At startup, the script reads this file. If the stored date matches today, it starts from that count. If the date is different (new day), it resets to zero. The count is written to disk after every scraped profile, so it survives crashes and restarts.

---

**Q: What is the role of the Lock in the threaded path?**
The `threading.Lock` in the worker pool protects three things that multiple threads would otherwise race on: (1) writing the validation result back into the shared Pandas DataFrame, (2) backfilling the Country column from LinkedIn data, (3) incrementing the daily usage counter and saving it to disk. Without the lock, two threads could write to the same DataFrame row simultaneously or double-count against the daily limit.

---

**Q: How would you scale this further if needed?**
A few directions: (1) run multiple machines each with their own LinkedIn account, coordinating via a shared job queue (Redis or a database) instead of an in-memory Python queue; (2) switch fully to Apify or a similar cloud scraping service to eliminate the per-account rate-limit problem entirely; (3) add a database backend instead of Excel so multiple operators can work the same lead sheet simultaneously; (4) cache profile results by LinkedIn URL so the same profile is never scraped twice across different sheets.

---

**Q: How do you handle a page crash or tab becoming unresponsive in the threaded mode?**
Each worker wraps its scraping loop in a try/except. If `get_linkedin_details` raises any exception (page closed, navigation aborted, timeout), the worker catches it, tries to close the broken page, opens a fresh page on the same context, and marks that row as `SCRAPING ERROR`. The worker then continues pulling the next row from the queue — it does not crash the entire run.

---

**Q: What would you do differently if you redesigned this project?**
A few things: (1) replace the raw `body.inner_text()` approach with proper DOM selectors — it's more brittle to LinkedIn layout changes; (2) add a proper logging library (like Python's `logging` module) instead of print statements, with log levels and file output; (3) store results in a SQLite database instead of writing back to the source Excel file — cleaner separation between input and output; (4) add a simple web UI so non-technical users don't need to edit config.py directly.

---

**Q: How does the company enrichment feature work end-to-end?**
After a lead passes all validation checks and is marked VALID, the tool performs a second LinkedIn scrape for that lead's company. While still on the person's profile page (before moving to the next contact), it runs a JavaScript DOM query to find anchor tags pointing to `/company/` URLs, matching by the company name already extracted. That URL is appended with `/about/` and navigated to. The About page text is then parsed line-by-line — anchoring on the keywords "Industry" and "Company size" — to extract the industry type, employee range, and associated member count. All four values (industry, size range, member count, company URL) are written as new columns in the output Excel file.

---

**Q: Why do you only run company enrichment for VALID leads?**
Company enrichment adds an extra page navigation per lead — roughly 4-6 extra seconds. Running it on every lead regardless of validation result would significantly slow down the run and burn through more of the daily LinkedIn limit. Since invalid leads are discarded by the sales team anyway, enriching them provides no business value. Restricting it to VALID leads keeps the run time lean and makes the daily limit go further.

---

**Q: How do you ensure the correct company page is found on a profile with multiple company links?**
LinkedIn profile pages contain many `/company/` links beyond just the person's employer — sponsored content, "People also viewed" cards, suggested companies in the sidebar, and footer navigation. A naive approach of grabbing the first link would frequently pick the wrong one. The DOM query loops through all `/company/` anchor tags and checks each one's visible text content against the company name already extracted from the profile. The first link whose text contains the company name (or vice versa) is selected. Only if no text match is found does it fall back to the first link in document order.

---

**Q: What data does the Company About page give you and how do you parse it?**
The About page is read as raw `body.inner_text()` and split into lines. LinkedIn's About section follows a consistent label-then-value structure — a line containing exactly "Industry" is always followed by the industry name, and "Company size" is always followed by the employee range. For company size, LinkedIn shows two pieces of data on consecutive lines: the range (e.g. "10,001+ employees") and a member count (e.g. "193 associated members on LinkedIn"). The parser validates each candidate line before accepting it — the range line must contain "employees" or match a number-range pattern, and the members line must contain the word "associated" or "member" — so noise lines between sections don't get mistakenly captured as values.
