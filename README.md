# lead_validation

Validates a calling-sheet Excel file's contacts against their LinkedIn
profile (current employer, job title, country, experience, etc.) and
writes the result back into the sheet.

## Local CLI usage

The original terminal workflow is unchanged:

```
.venv\Scripts\Activate.ps1
python main.py
```

It reads `config.py` for the input/output file paths and LinkedIn
settings, and walks you through a few prompts (experience filter,
enrichment fields, country filter) before scraping.

## Web GUI (FastAPI)

`webapp/` adds a small password-gated FastAPI GUI over the exact
same pipeline, for cases where running `main.py` from a terminal
isn't convenient. It does not change any scraping/validation logic -
it just replaces `main.py`'s `input()` prompts with a web form (file
upload for the Excel sheet and `cookies.json`, plus the same options
main.py asks for), and runs LinkedIn profiles a small batch at a
time (so a run fits inside a normal HTTP request/proxy timeout).

### Run it locally (no Docker)

Everything below runs directly on your machine with the same
`.venv` the CLI uses - no container involved.

**Prerequisites:** Python 3.10+ and the repo's `.venv` (create one
with `python -m venv .venv` if you don't have it yet).

1. Activate the virtual environment and install dependencies:

   ```powershell
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Install the Playwright browser binary (only needed once - this
   is what `linkedin_scraper/browser.py` drives, and it's *not*
   installed by `pip install` alone):

   ```powershell
   playwright install chromium
   ```

3. Set the login password (required) and, optionally, a fixed
   session-signing key so you don't get logged out every restart:

   ```powershell
   $env:APP_PASSWORD = "choose-a-password"
   $env:SECRET_KEY = "any-random-string"   # optional locally
   ```

   (cmd.exe instead of PowerShell? Use `set APP_PASSWORD=choose-a-password`.)

4. Start the app:

   ```powershell
   python webapp\app.py
   ```

   or, equivalently, with auto-reload on code changes:

   ```powershell
   uvicorn webapp.app:app --reload --host 0.0.0.0 --port 8000
   ```

5. Open **http://localhost:8000** in your browser - not
   `http://0.0.0.0:8000`, which is what step 4's `--host 0.0.0.0`
   binds *to*, not an address a browser can open (you'll get
   `ERR_ADDRESS_INVALID`). Log in with the password from step 3,
   upload your Excel file and `cookies.json`, and click through
   batches. Stop the server with `Ctrl+C`.

This uses a real (visible) browser window for the LinkedIn scraping
- same as running `main.py` from the terminal. Only the Docker image
(used for Render/Kubernetes) runs headless - see "Deploy to Render"
below.

### Deploy to Rancher / Kubernetes

See [`k8s/README.md`](k8s/README.md) for the full walkthrough
(build & push the image, fill in `k8s/secret.example.yaml`, apply
the manifests via `kubectl` or Rancher's **Import YAML**). In short:

```
docker build -t your-registry.example.com/lead-validator:latest .
docker push your-registry.example.com/lead-validator:latest
# edit k8s/deployment.yaml's image, fill in k8s/secret.yaml, then:
kubectl apply -f k8s/
```

This gets you a persistent volume for `webapp/data/` (so an
in-progress job survives a pod restart) and a `/healthz` endpoint
for readiness/liveness probes - see that file for sizing/scaling
notes (this app is designed to run as a single replica).

### Deploy to Render (Free tier)

`render.yaml` points at the same `Dockerfile`; Render only cares that
the container listens on `$PORT`. On Render (and on Kubernetes, via
`HOSTED_DEPLOYMENT=true`), the app auto-detects it's hosted and runs
Chromium `headless=True` - no visible window, no Xvfb, low enough
memory to fit Render's free 512MB.

Because Render's free plan has no persistent disk, anything written
to `webapp/data/` (an uploaded `cookies.json` included) is wiped on
every restart / ~15-minute idle spin-down. **Render Secret Files**
are the free, persistent exception to that, and are how this app is
meant to get your LinkedIn session onto a hosted deployment - not by
storing a username/password anywhere.

#### 1. Generate the session locally (once, on your own machine)

```powershell
.venv\Scripts\Activate.ps1
python login.py
```

A real, visible Chromium window opens to the LinkedIn login page. Log
in by hand (this is the only place a password is ever typed - never
in source code, never on the server), then press ENTER in the
terminal when the home feed loads. This saves `cookies.json` (or
whatever filename you choose) in the project root. It is gitignored
(`cookies*.json` in `.gitignore`) and must never be committed.

#### 2. Verify the session works

```powershell
python verify_session.py cookies.json
```

This launches a **headless** browser, loads the saved session, and
confirms it actually reaches the LinkedIn feed instead of the login
wall - no cookies/tokens are ever printed. Fix with step 1 again if
it reports expired.

#### 3. Configure Render

1. Push this repo to GitHub (see **Before you push** below first -
   this repo's history needs a look before it's public/shared).
2. In the [Render dashboard](https://dashboard.render.com/), click
   **New +** → **Blueprint**, and point it at this repo. Render
   reads `render.yaml` and `Dockerfile` and sets everything up.
   (No Blueprint? **New +** → **Web Service** → connect the repo →
   environment **Docker**.)
3. Under the new service's **Environment** tab, set `APP_PASSWORD`
   to whatever password you want the GUI to require. (`SECRET_KEY`
   is generated for you automatically.)
4. Same **Environment** tab → **Secret Files** → **Add Secret File**:
   - **Filename:** `linkedin_storage_state.json`
   - **Contents:** paste the entire contents of your local
     `cookies.json` from step 1.

   Secret Files are never part of `render.yaml` or any committed
   file - they're pasted directly into Render's dashboard/API, kept
   out of git entirely, and (unlike `webapp/data/`) survive restarts
   and redeploys. Render mounts it at
   `/etc/secrets/linkedin_storage_state.json` by default, which is
   exactly the path `linkedin_scraper/browser.py` looks for.

   *If your session file is unusually small* (rare for LinkedIn),
   you can instead set the env var `LINKEDIN_STORAGE_STATE_B64` to
   the base64 of `cookies.json`'s contents
   (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.json")) | Set-Clipboard`
   in PowerShell) - but most real sessions exceed Render's env var
   size limit, so the Secret File above is the supported path.

#### 4. Deploy

```
git push
```

Render auto-deploys on push. On boot, the app copies the Secret
File into `webapp/data/cookies.json` automatically (see
`bootstrap_session_from_secret()` in `linkedin_scraper/browser.py`) -
no manual upload needed, even after a restart. Open the service URL,
log in with `APP_PASSWORD`, and start a job.

#### When the session expires

LinkedIn sessions eventually expire, and Render's IP differs from
your home/office IP, which can make LinkedIn ask for re-verification
sooner than you're used to locally - this is expected, not a bug, and
there's no way to automate past LinkedIn's verification/CAPTCHA (nor
should there be). When a batch reports "session expired":

1. Locally: `python login.py` again, then `python verify_session.py cookies.json`.
2. In the Render dashboard, edit the Secret File's contents to the
   new `cookies.json` (triggers a redeploy) - this is what makes the
   fix survive the *next* restart too.
3. For a same-session, no-redeploy quick fix in the meantime, the
   dashboard's own "Update cookies" upload still works as before.

### How a job works in the GUI

1. Upload your Excel file, the sheet name, and your LinkedIn
   `cookies.json`, plus any options (experience filter, country
   filter, which enrichment fields to fetch, leads per batch).
2. Click **Start Validation** once. Behind the scenes the server
   still processes a handful of leads per request (default 3, so no
   single request runs long enough for a reverse proxy to kill it),
   but the page automatically resubmits itself after each batch -
   saving progress into the working file and updating the on-screen
   counters - until the whole sheet is done, exactly like re-running
   `main.py` picks up where it left off, via the same `Validation 2`
   column. Keep the tab open while it runs; a **Stop auto-run**
   button appears if you want to pause it.
3. Click **Download current file** any time to grab the sheet as-is,
   finished or not.
4. If LinkedIn's daily limit is hit or the session expires, the GUI
   asks for another account's `cookies.json` instead of stopping the
   whole job.

### Known limitations of the hosted version

- **Free Render plan = no persistent disk for job state.** `webapp/data/`
  (the in-progress Excel file, `job_meta.json`, any saved LinkedIn
  auto-login credentials) is wiped on restart/idle spin-down -
  download your output after each batch. The LinkedIn *session*
  itself is the exception: it's restored automatically from a Render
  Secret File on every boot (see "Deploy to Render" above), so that
  part specifically does NOT need re-uploading after a restart. A
  paid Render plan + attached disk (commented out in `render.yaml`),
  or the Rancher/Kubernetes deployment above (PersistentVolumeClaim
  by default), avoids the rest of this for job state too.
- **Batch size vs. request timeouts.** Any proxy/ingress in front of
  this app (Render's, or an nginx Ingress on Kubernetes) cuts off
  HTTP requests that run too long. The Playwright scraper takes
  roughly 15-30 seconds per profile, so keep "Leads per batch" small
  (3-5).
- **One job at a time.** The GUI is built for a single operator
  running one sheet at a time (matching the local tool), not
  multiple concurrent users.
- **2FA/checkpoints can't be solved by hand.** Locally, a visible
  browser window lets you solve a LinkedIn verification challenge
  yourself. On Render the browser runs fully headless with nobody
  watching, so a checkpoint will just time out after 3 minutes -
  there's no way to automate past it, nor should there be. Make sure
  `cookies.json` is a currently-valid, already logged-in session
  (`python verify_session.py cookies.json`) before uploading/deploying
  it. Render's IP also differs from your own, which can make LinkedIn
  ask for re-verification sooner than you're used to locally.
- **No "Log in to LinkedIn" button on hosted deployments.** That
  button opens a real browser window on whatever machine runs the
  server - useful locally, meaningless on Render/Rancher since the
  window opens on the server, not your screen. The GUI hides it
  automatically there (Render is detected via Render's own `RENDER`
  env var; the Kubernetes/Rancher manifests set `HOSTED_DEPLOYMENT=true`
  explicitly - see `k8s/deployment.yaml`) and shows only the
  `cookies.json` upload field. To get a `cookies.json`, run
  `python login.py` locally once, log in by hand, then either upload
  the file it saves to the hosted instance for a quick same-boot fix,
  or (recommended, survives restarts) put it in a Render Secret File
  as described above.
- **Auto-login with email/password (alternative to cookies.json).**
  The dashboard's "LinkedIn login" card also lets you save a
  LinkedIn email/password directly - the server then logs in
  automatically whenever a batch starts without a valid session,
  which is the only way to authenticate a hosted deployment without
  ever running the app locally. Credentials are stored in plaintext
  on the server's disk (`webapp/data/linkedin_credentials.json`,
  same persistence caveats as `cookies.json` above) - use "Clear
  saved credentials" when you're done, and note the 2FA/checkpoint
  limitation above still applies to this login just like any other.

### Before you push: existing secrets in this repo

This repo's git history already contains a real `cookies.json`
(LinkedIn session) and `config.py`'s hardcoded Apify API token from
before this `.gitignore` fix. Both were removed from tracking going
forward as part of this change, but they're still visible in past
commits. Recommended before making this repo more widely
accessible:

- Rotate/regenerate the Apify token in the Apify console, and rely
  on the `APIFY_API_TOKEN` environment variable instead of the
  hardcoded fallback in `config.py`.
- Treat the committed `cookies.json` as burned - log that LinkedIn
  account out everywhere (or just don't reuse those cookies) and
  upload a fresh `cookies.json` through the GUI/CLI going forward.
- If you want the secrets gone from history entirely (not just
  future commits), that needs a history rewrite (`git filter-repo`
  or BFG) and a force-push - ask if you'd like help with that.
