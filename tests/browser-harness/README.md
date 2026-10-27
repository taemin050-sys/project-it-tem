# S3-B React/Vite Browser API integration harness (MOCK only)

This is NOT the frontend owner's production application. It exercises the actual
P2/P3 HTTP flow: upload distinct photos → Job → plan/copy → human approval →
mock image → human approval → composition → PNG and UTF-8 caption download.

## Run

Requirements: installed Chrome, npm, and Python venv with official locked
FastAPI/Pillow/uvicorn dependencies. All services bind to localhost only.

    npm ci --no-audit --no-fund
    npm run build
    IT_TEM_PYTHON=/absolute/path/to/your/.venv/bin/python \
    IT_TEM_KOREAN_FONT=/absolute/path/to/verified/KoreanFont.ttf \
      ./scripts/run-local-e2e.sh

Vite runs on 127.0.0.1:4173 and proxies /api to local FastAPI 127.0.0.1:18766.
The harness uses puppeteer-core and installed system Chrome, not a downloaded browser.
Synthetic photos depict the same imaginary product from slightly different positions.

Evidence is saved under gitignored ../../.runtime/b0_browser_harness/:
- browser_network_trace.json: real browser requests, statuses, Job ID
- artifact_checks.json: 1080x1350 PNG and UTF-8 caption retrieved in Chrome
- b0_browser_harness_completed.png: screenshot
- backend.log, vite.log, and synthetic image files

The test verifies upload 201, both approvals, expected 409 wrong order,
409 rejection, refresh recovery, generated files and no unintended JavaScript error.

LIMITATION: This is an independent test harness and does NOT prove completion
of the frontend Owner's React app. It has no actual VLM, Text, Compliance,
Image generation, billable API or GCP connection. Owner FE, B1/B2, authentication,
and production deployment are separate gates. PR #6 API_LIST.md is the intended
reference for the currently implemented dev 11 API operations.

## Verified evidence checkpoint (2026-10-27)

Real headless system Chrome 1280px viewport using React 19 + Vite 7 local proxy;
backend was FastAPI from dev@b5e227e, no model calls. Test passed:
upload 201, workflow statuses, intentional 409 invalid step, copy rejection 409,
page refresh Job GET, 1080x1350 PNG, UTF-8 caption, browser JS exception gate.
The isolated backend was also restarted and the prior Job and final PNG recovered.

Sanitized reviewable artifacts in evidence/:
- screenshot b0_browser_harness_completed.png (fictional product, mock status)
- browser_network_trace.json (only localhost routes, ephemeral test Job IDs)
- artifact_checks.json (content-type, dimensions, caption, byte count)

These are NOT proof of the actual frontend Owner implementation, owner v0.7
schema, Compliance server gate, or real Live models.
