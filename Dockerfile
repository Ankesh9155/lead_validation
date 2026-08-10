# Dockerfile for hosting the lead-validation web GUI (webapp/) as a
# container - built for Kubernetes/Rancher, but runs anywhere
# Docker does. This packages the EXISTING project as-is - no
# scraping, validation, or CLI logic is changed. It just:
#   1) installs the same requirements.txt the project already uses
#   2) makes sure a Chromium browser + its OS deps are present
#      (needed for linkedin_scraper/browser.py's Playwright calls)
#   3) runs the app under a virtual display (Xvfb) so
#      browser.py's hardcoded `headless=False` launches work on a
#      display-less server, unmodified
#
# Base image version must match the `playwright` version pinned in
# requirements.txt (see https://mcr.microsoft.com/en-us/product/playwright/python/tags)
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

# Xvfb provides the virtual display browser.py's headless=False
# needs when there's no real monitor attached.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Browser binaries for this exact playwright version (the base
# image already ships a matching Chromium, but this keeps the
# build self-contained if the base image ever drifts).
RUN playwright install --with-deps chromium

COPY . .

ENV PORT=8000
EXPOSE 8000

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
CMD xvfb-run -a --server-args="-screen 0 1400x900x24" \
    uvicorn webapp.app:app \
    --app-dir /app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --timeout-keep-alive 300
