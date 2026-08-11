# linkedin_scraper/__init__.py
#
# Force stdout/stderr to UTF-8 (with errors="replace" as a last-
# resort safety net) before anything else in this package runs a
# single print() - this file is the first thing Python executes
# when ANY submodule here gets imported, regardless of entry point
# (main.py, webapp/app.py, debug_profile.py, login.py), so it's the
# one place this needs to happen.
#
# Root cause (confirmed on a real profile - Corey Brant, whose
# LinkedIn activity feed includes a repost caption with an emoji,
# "🌶️🔥 Pouring hot sauce over a bad dish can't fix it..."):
# parser.py/scraper.py print extensive debug output (profile text
# lines, header/experience results) for troubleshooting. On Windows,
# Python's stdout defaults to the console's legacy codepage (cp1252
# here, reported by Python as "charmap"), which can't encode emoji.
# print()-ing a line containing one raised UnicodeEncodeError from
# INSIDE extract_header() - before it had even computed full_name -
# which get_linkedin_details()'s generic `except Exception` handler
# caught, logged as "LinkedIn Scraping Error", and retried. The SAME
# emoji is still there on retry, so it crashed identically again and
# gave up after max_attempts, returning a completely blank result
# (no name, no job title, no company, current_employee=False). That
# blank result is what produced the false "INVALID - NAME, COMPANY,
# JOB TITLE, NO LONGER" for a lead whose profile was, in fact, fine -
# re-running with UTF-8 stdout shows the existing parsing logic
# (including the grouped multi-role company header handling and the
# /details/experience/ fallback) already gets this profile exactly
# right. Not a parsing bug - a console-encoding crash masquerading as
# one. Any profile with an emoji anywhere in its first ~20 header
# lines or printed experience block (headline, post captions pulled
# into the header window, job titles...) could hit this same silent
# failure, so fix it once for the whole package instead of special-
# casing this one profile.
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # reconfigure() needs Python 3.7+ and a real TextIOWrapper -
        # e.g. a no-op when output has been redirected to something
        # else (like a test harness's StringIO) that doesn't have it.
        pass
