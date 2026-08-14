# Dockerfile for hosting the lead-validation web GUI (webapp/) as a
# container - built for Kubernetes/Rancher and Render, but runs
# anywhere Docker does. This packages the EXISTING project as-is - no
# scraping, validation, or CLI logic is changed. It just:
#   1) installs the same requirements.txt the project already uses
#   2) makes sure a Chromium browser + its OS deps are present
#      (needed for linkedin_scraper/browser.py's Playwright calls)
#
# This image only ever runs as a hosted deployment (Render sets its
# own RENDER env var automatically; k8s/deployment.yaml sets
# HOSTED_DEPLOYMENT=true) - linkedin_scraper/browser.py's
# is_hosted_deployment()-driven headless mode means Chromium always
# launches headless=True here, so no virtual display (Xvfb) is
# needed. That also keeps memory usage down, which matters on
# Render's free tier (512MB RAM).
#
# Base image version must match the `playwright` version pinned in
# requirements.txt (see https://mcr.microsoft.com/en-us/product/playwright/python/tags)
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Browser binaries for this exact playwright version (the base
# image already ships a matching Chromium, but this keeps the
# build self-contained if the base image ever drifts).
RUN playwright install --with-deps chromium

COPY . .

ENV PORT=8000
EXPOSE 8000

# --------------------------------------------------------------------
# LinkedIn session / headless-mode env vars (all optional - blank
# here means "let linkedin_scraper/browser.py's own defaults decide").
# Declared as empty ENV lines purely so they're visible/documented on
# `docker inspect` and in any dashboard's Environment list, not
# because a value is required here - set actual values via Render's
# Environment tab / Secret Files, or k8s/secret.yaml, never by baking
# them into this file or the image.
#
#   RENDER                     - set automatically BY Render; do not set.
#   HOSTED_DEPLOYMENT           - set to "true" for non-Render hosted
#                                  platforms (see k8s/deployment.yaml).
#   PLAYWRIGHT_HEADLESS          - "true"/"false" to force headless mode,
#                                  overriding the RENDER/HOSTED_DEPLOYMENT
#                                  auto-detection above.
#   LINKEDIN_STORAGE_STATE_PATH  - override the default Secret File mount
#                                  path (/etc/secrets/linkedin_storage_state.json).
#   LINKEDIN_STORAGE_STATE_B64   - base64 fallback session, only for small
#                                  storage_state files - see README.md.
#
# See README.md "Deploying to Render (Free tier)" for the full setup.
# --------------------------------------------------------------------
ENV PLAYWRIGHT_HEADLESS=""
ENV LINKEDIN_STORAGE_STATE_PATH=""
ENV LINKEDIN_STORAGE_STATE_B64=""

# Runs as a non-root user - Rancher/Kubernetes clusters commonly
# enforce this via a Pod Security Standard.
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

# --workers 1: this app manages one browser-driven job at a time
#   (see webapp/app.py) - concurrent workers would fight over the
#   same working files and the single Playwright browser instance.
# --timeout-keep-alive 300: a batch of a few LinkedIn profiles can
#   take a few minutes; give the server room before it drops the
#   connection (your Ingress/reverse proxy in front of this may
#   have its own separate timeout - keep "Leads per batch" small,
#   see README).
CMD uvicorn webapp.app:app \
    --app-dir /app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --timeout-keep-alive 300
