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
- same as running `main.py` from the terminal - since it's the
Docker image, not this local run, that hides it behind Xvfb.

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

### Deploy to Render (still supported)

`render.yaml` still works unchanged - it just points at the same
`Dockerfile`, and Render only cares that the container listens on
`$PORT`.

1. Push this repo to GitHub (see **Before you push** below first).
2. In the [Render dashboard](https://dashboard.render.com/), click
   **New +** → **Blueprint**, and point it at this repo. Render
   reads `render.yaml` and `Dockerfile` and sets everything up.
3. Under the new service's **Environment** tab, set `APP_PASSWORD`
   to whatever password you want the GUI to require. (`SECRET_KEY`
   is generated for you automatically.)
4. Deploy. Once it's live, open the service URL, log in, and start
   a job the same way as local usage above.

No Blueprint? You can instead create the service by hand: **New +**
→ **Web Service** → connect the repo → environment **Docker** → set
`APP_PASSWORD` under Environment → deploy.

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

- **Free Render plan = no persistent disk.** Render's free web
  services don't keep local files across a restart, and the service
  spins down after ~15 minutes idle. An in-progress job's working
  file and uploaded cookies are lost on the next spin-up - download
  your output after each batch, and keep `cookies.json` handy to
  re-upload. A paid Render plan + attached disk (commented out in
  `render.yaml`), or the Rancher/Kubernetes deployment above (which
  includes a PersistentVolumeClaim by default), avoids this.
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
  yourself. On Render the browser runs in a virtual display (Xvfb)
  with nobody watching, so a checkpoint will just time out after 3
  minutes. Make sure `cookies.json` is a currently-valid, already
  logged-in session before uploading it.
- **No "Log in to LinkedIn" button on hosted deployments.** That
  button opens a real browser window on whatever machine runs the
  server - useful locally, meaningless on Render/Rancher since the
  window opens on the server, not your screen. The GUI hides it
  automatically there (Render is detected via Render's own `RENDER`
  env var; the Kubernetes/Rancher manifests set `HOSTED_DEPLOYMENT=true`
  explicitly - see `k8s/deployment.yaml`) and shows only the
  `cookies.json` upload field. To get a `cookies.json`, run this app
  locally (or `python login.py`) once, log in by hand, then upload
  the file it saves to the hosted instance.

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
