# LinkedIn Lead Validator — Project Status

End-to-end status of the whole project: the original CLI scraper/validator
tool, and the web GUI + hosted-deployment layer built on top of it. For deep
implementation detail, validation logic, and interview-style Q&A on the
scraping/parsing internals, see [`PROJECT_DOCUMENT.md`](PROJECT_DOCUMENT.md) —
this file is the higher-level "what exists, what works, what's done" map,
covering both halves of the project.

---

## 1. What the project is

Two things, layered on top of each other:

1. **A CLI tool** (`main.py` + `config.py` + `validator.py` + `excel_handler.py`
   + `linkedin_scraper/`) that reads a calling-sheet Excel file, checks every
   contact against their live LinkedIn profile, and writes back a
   `VALID`/`INVALID - reason` verdict plus enrichment data (industry, company
   size, company LinkedIn URL). Run directly with `python main.py`, driven by
   `input()` prompts and settings in `config.py`.
2. **A web GUI** (`webapp/`) wrapping that same pipeline in a FastAPI app with
   a password-protected dashboard, so it can be deployed once (Docker, on
   Render or Kubernetes/Rancher) and operated from a browser instead of a
   terminal on someone's own machine. It reuses `main.py`'s functions
   directly (`lookup_linkedin_data`, `load_usage`/`save_usage`,
   `start_browser`/`close_browser`) — no scraping/validation logic is
   duplicated.

---

## 2. Architecture at a glance

```
CLI path:
  main.py → excel_handler.py / validator.py / config.py / linkedin_scraper/*

Web path:
  webapp/app.py (FastAPI)
    ├── webapp/templates/  (Jinja2: base.html, login.html, dashboard.html)
    ├── webapp/static/style.css
    ├── webapp/data/       (gitignored: current.xlsx, cookies.json,
    │                        job_meta.json, linkedin_credentials.json)
    └── imports main.py's lookup_linkedin_data/load_usage/save_usage,
        and linkedin_scraper.browser's start_browser/close_browser/get_page

Deployment:
  Dockerfile (Playwright base image, runs `uvicorn ...` headless - see
    linkedin_scraper/browser.py's is_hosted_deployment()/_headless_mode())
    ├── k8s/  → Rancher / Kubernetes (Deployment, Service, Ingress, PVC, Secret)
    └── render.yaml → Render Blueprint (same Dockerfile + a Render Secret
        File for the LinkedIn session - see bootstrap_session_from_secret())
```

---

## 3. CLI tool — completed ✅

Everything in this section is implemented, working, and documented in detail
in `PROJECT_DOCUMENT.md`:

- [x] Excel read/write pipeline (`excel_handler.py`, pandas + openpyxl)
- [x] Two scraper backends behind one `SCRAPER_MODE` toggle: free Playwright
      (own logged-in session) and paid Apify (no login, no ban risk)
- [x] Multi-tab parallel scraping (`PLAYWRIGHT_WORKERS`), one fully
      independent Playwright stack per worker thread (thread-safety fix)
- [x] Fuzzy validation engine: nickname matching, job-title abbreviation
      expansion with protected rank modifiers, country alias expansion,
      company partial/word-overlap matching
- [x] Daily LinkedIn lead limit + account rotation (`linkedin_usage.json`,
      logs out and prompts for a second account's cookies when hit)
- [x] Resume/incremental processing — reruns skip rows with a non-blank
      `Validation 2`
- [x] Country filter prompt at startup
- [x] Auto-save every 25 contacts
- [x] Auto-login via `LINKEDIN_EMAIL`/`LINKEDIN_PASSWORD` in `config.py` when
      `cookies.json` is missing/expired, including a 3-minute wait for a
      human to solve a LinkedIn checkpoint in the visible browser window
- [x] Company enrichment for VALID leads (industry, company size range,
      member count, company LinkedIn URL)
- [x] Canonical LinkedIn URL backfill after redirects

---

## 4. Web GUI — completed ✅

- [x] FastAPI app (`webapp/app.py`) mirroring `main.py`'s CLI loop as a
      button/form-driven flow — same underlying functions, no reimplemented
      scraping logic
- [x] Single shared-password auth (`APP_PASSWORD` env var), Flask-style flash
      messages backed by a signed session cookie
- [x] Job lifecycle on disk (`job_meta.json`) so an in-progress job survives
      worker/pod restarts: upload Excel + `cookies.json` → batch runs →
      resume/download
- [x] Batched processing (`/run-batch`, default up to 15 leads/click) with a
      dashboard auto-run loop (`localStorage`-driven JS) that keeps
      resubmitting after each batch until done, a stall-detector, and a
      "Stop Validation" control that breaks the batch between rows
- [x] Country filter, max-experience-years, daily-limit, and enrichment-field
      overrides exposed as form fields (same semantics as the CLI's `ask_*`
      prompts, minus `input()`)
- [x] Multi-sheet Excel upload handling (auto-detects single-tab files, asks
      for the sheet name otherwise)
- [x] Daily-limit-reached / session-expired states surfaced in the UI with an
      "Update cookies & continue" flow to swap in a different account
- [x] `/healthz` liveness/readiness endpoint for Kubernetes/Rancher probes
- [x] `_batch_lock` guarding every Playwright-driving route so two overlapping
      clicks can't drive two browsers from two threads at once

---

## 5. Hosted deployment — completed ✅

- [x] `Dockerfile`: Playwright base image, installs Chromium + OS deps, runs
      the whole app under `xvfb-run` so `headless=False` Playwright calls
      (unmodified from the local code path) work on a display-less server
- [x] Kubernetes/Rancher manifests (`k8s/`): Deployment (single replica,
      `Recreate` strategy), Service, Ingress, PersistentVolumeClaim for
      `webapp/data/`, Secret template
- [x] Render Blueprint (`render.yaml`) pointing at the same Dockerfile
- [x] Documented known limitations: free-Render-plan disk loss on
      restart/spin-down, batch size vs. reverse-proxy request timeouts,
      single-job-at-a-time design, checkpoints/2FA can't be solved by hand on
      a hosted deployment

### Checkpoint: "Log in to LinkedIn" button was misleading on hosted deployments — fixed ✅

**Problem found:** the button opened a real Playwright browser window with
`headless=False`. Locally that's a real, visible window. On Render/Rancher
the whole container runs under Xvfb, so the launch technically *succeeded* —
but the window opened on the server's invisible virtual display, so nobody
could ever see or click through the LinkedIn login page. This looked like a
silent failure rather than the inherent limitation it actually was.

**Fix shipped:**
- [x] `is_hosted_deployment()` in `webapp/app.py` — detects Render (its own
      auto-set `RENDER` env var) or Rancher/Kubernetes (`HOSTED_DEPLOYMENT=true`,
      set explicitly in `k8s/deployment.yaml`)
- [x] `/login-linkedin/start` short-circuits on a hosted deployment instead of
      attempting the doomed browser launch, with a clear flash message
      pointing at the `cookies.json` upload
- [x] The button itself is hidden entirely in `dashboard.html` on hosted
      deployments
- [x] README "Known limitations" section documents the behavior

### Checkpoint: LinkedIn email/password auto-login from the dashboard — completed ✅

**Goal:** give hosted deployments a way to authenticate without ever running
the app locally, as an alternative to uploading `cookies.json`.

- [x] Reused the CLI's existing auto-login mechanism
      (`linkedin_scraper/browser.py`'s `_ensure_linkedin_session` /
      `login_linkedin_with_credentials`, previously only reachable by
      hand-editing `config.py`) — no scraper-side code changed
- [x] New credentials store in `webapp/app.py`: `webapp/data/linkedin_credentials.json`,
      loaded/applied to `config.LINKEDIN_EMAIL`/`LINKEDIN_PASSWORD` at process
      startup and on every save/clear
- [x] New routes: `POST /update-linkedin-credentials`, `POST /clear-linkedin-credentials`
- [x] New "Auto-login with email/password" form in the dashboard's "LinkedIn
      login" card (status tag, save, clear) — shown on both hosted and local
      deployments
- [x] `start_job()` and `_run_batch()`'s "must have cookies.json" gates
      relaxed to also accept saved credentials, so the very first batch with
      no `cookies.json` at all can self-heal by logging in and writing a
      fresh session file
- [x] Hosted-aware error messaging when a LinkedIn checkpoint/verification
      challenge times out mid-auto-login (points at the `cookies.json`
      fallback instead of the generic "try again" wording)
- [x] Documented tradeoffs in README: plaintext credential storage on disk,
      no persistence on Render's free plan, checkpoint/CAPTCHA risk from an
      unfamiliar server IP

**Verified:** `webapp/app.py` compiles, `dashboard.html` parses, and the
save/load/clear credential functions were exercised directly (confirmed they
correctly write/read the JSON file and mutate `config.LINKEDIN_EMAIL`/
`LINKEDIN_PASSWORD` in both directions).

---

### Checkpoint: True headless mode + persistent LinkedIn session on Render Free — completed ✅

**Problem found:** Chromium was hardcoded `headless=False` everywhere
(`browser.py`'s `start_browser()`/`launch_worker_browser()`), only made to
work on a display-less server via Xvfb in the Dockerfile - heavier than
necessary for Render's free 512MB RAM. Separately, the only way to get an
authenticated LinkedIn session onto a hosted deployment was a manual
`cookies.json` upload through the dashboard, which Render's free ephemeral
disk wipes on every restart/idle spin-down - requiring a fresh manual
upload every time.

**Fix shipped:**
- [x] `linkedin_scraper/browser.py`: `is_hosted_deployment()` moved here
      from `webapp/app.py` (single source of truth); new `_headless_mode()`
      (auto `True` on Render/hosted, `False` locally, with a
      `PLAYWRIGHT_HEADLESS` override escape hatch) replaces both hardcoded
      `headless=False` launches
- [x] `bootstrap_session_from_secret()`: on process startup, copies a
      Render **Secret File** (`/etc/secrets/linkedin_storage_state.json`,
      configured by hand in the Render dashboard, never committed to git,
      survives restarts/redeploys unlike `webapp/data/`) into
      `webapp/data/cookies.json` - falls back to a base64
      `LINKEDIN_STORAGE_STATE_B64` env var for very small sessions. Never
      logs cookie/session content.
- [x] `webapp/app.py` imports both from `browser.py` instead of keeping a
      duplicate `is_hosted_deployment()`; calls the bootstrap once at
      module load, same pattern as the existing credentials bootstrap
- [x] `Dockerfile`: Xvfb removed entirely (apt-get install + `xvfb-run`
      wrapper) - no longer needed once headless is always `True` in this
      image; lowers memory footprint on Render's free tier
- [x] `.gitignore`: `cookies.json` → `cookies*.json` + `*storage_state*.json`
      wildcards, so a rotated second/third LinkedIn account's cookie file
      (any filename, per `main.py`'s `ask_next_linkedin_account()`) is
      covered too, not just the literal default name
- [x] New `verify_session.py`: headless-only script that loads a
      storage_state file and confirms it actually reaches the LinkedIn
      feed (vs. the login/authwall/checkpoint page) without ever printing
      cookie/token values - used after `login.py` and before configuring
      the Render Secret File
- [x] `login.py`: unchanged login flow, added a post-save reminder not to
      commit the session file and pointing at `verify_session.py` +
      README's Render section
- [x] `render.yaml`, `README.md`, `k8s/README.md`: documented the exact
      generate → verify → configure (Secret File) → deploy steps, and why
      Secret Files (not `render.yaml` env vars) are the right mechanism -
      they're pasted directly into the dashboard, never touch a committed
      file, and aren't wiped by Render's free-tier ephemeral disk

**Still true / not solved by this (inherent to LinkedIn, not this app):**
LinkedIn sessions expire on their own timeline, and Render's IP differing
from your own can trigger LinkedIn's re-verification sooner than locally.
No CAPTCHA/2FA/checkpoint automation was added or attempted - when a
session dies, the fix is always the human step (`python login.py` again),
never an automated bypass.

**Verified:** `python -m py_compile` on all changed `.py` files;
`bootstrap_session_from_secret()` exercised directly against a mock Secret
File and against `LINKEDIN_STORAGE_STATE_B64` (both materialize a valid
`cookies.json`; both correctly no-op when neither is set, confirmed via
manual test).

---

## 6. Known limitations / not done

- **2FA/checkpoints still can't be solved on a hosted deployment.** Neither
  the browser-window flow (removed there) nor the email/password auto-login
  can get a human past a LinkedIn verification challenge with nobody
  watching the virtual display — the attempt times out after 3 minutes.
  `cookies.json` from an already-verified local session remains the most
  reliable path for hosted use.
- **Free Render plan has no persistent disk** — `cookies.json`,
  `linkedin_credentials.json`, and `job_meta.json` are all lost on
  restart/idle spin-down. The Kubernetes/Rancher deployment (PVC) and a paid
  Render plan + attached disk avoid this.
- **Single job, single operator, single replica** by design — not built for
  concurrent multi-user use.
- **No automated test suite** — verification so far has been manual smoke
  tests (`python -m py_compile`, Jinja template parsing, direct function
  calls) rather than a `pytest` suite.
- **PR for the hosted-deployment fixes is not yet merged** — the work in
  sections 5's two checkpoints lives on branch
  `fix/hide-linkedin-login-on-hosted-deploy`, pushed to GitHub, PR not yet
  opened (blocked on `gh auth login` in this environment — see
  `k8s/README.md`/repo remote for manual PR creation instructions).

---

## 7. File map (what to open for what)

| Looking for... | File |
|---|---|
| Full CLI architecture, validation rules, parser internals, interview Q&A | `PROJECT_DOCUMENT.md` |
| CLI entry point / orchestration | `main.py` |
| All CLI settings | `config.py` |
| Web GUI routes, job state, batch loop | `webapp/app.py` |
| Dashboard UI | `webapp/templates/dashboard.html` |
| Playwright browser lifecycle + auto-login | `linkedin_scraper/browser.py` |
| Local/hosted deployment instructions | `README.md` |
| Kubernetes/Rancher manifests | `k8s/` (see `k8s/README.md`) |
| Render Blueprint | `render.yaml` |
