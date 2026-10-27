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

Evidence is saved under a **unique per-run** gitignored ../../.runtime/b0-XXXXXXXX/:
- browser_network_trace.json: real browser requests, statuses, Job ID
- artifact_checks.json: 1080x1350 PNG and UTF-8 caption retrieved in Chrome
- b0_browser_harness_completed.png: screenshot
- Chrome physical download checks, backend.log, vite.log; generated inputs and JobStore are removed after test by default

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


## S3-B.2 audit hardening (2026-10-27)

| Independent test gate | Evidence | Result |
|---|---|---|
| **React UI stale state** | Competing server POST advances the state; UI click fails HTTP 409, then exactly one GET Job, matching UI state, zero automatic POST retry | PASS |
| **Real Chrome downloads** | React buttons clicked; files saved by Chromium; PNG magic signature/width/height and UTF-8 Korean text decoded from filesystem | PASS |
| **Download failure UX** | Network injection returns HTTP 404 for caption; React displays visible error, no silent success | PASS |
| **Refresh network diff** | Job GET is observed; zero side-effectful POST after reload, same Job ID/status and final artifact button | PASS |
| **Restart + browser** | Backend process restarted with same disposable JobStore; curl and new Chrome page both restore COMPLETED and 1080x1350 PNG; browser POST=0 | PASS |
| **Backend HTTP regression** | pytest covers real 11-route OpenAPI and 201/200/404/409/413/422, upload counts 2~5 / references 0~5 / duplicate/size/MIME/rejection and file headers | PASS |
| **Contract continuity** | Existing P2/P3/Policy tests still pass, no change to HTTP implementation, JobStore, Text owner schemas or 7 BLOCKED Wire | PASS |

### Exact standalone reproduction

From a new checkout of the reviewed branch/commit, use an isolated Python
virtual environment with the repository's Python lock
`configs/requirements-serving-gcp.lock.txt`. From repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r configs/requirements-serving-gcp.lock.txt
IT_TEM_KOREAN_FONT=/path/to/an/installed/KoreanFont.ttf .venv/bin/python -m pytest -q
.venv/bin/python docs/contracts/validate_package.py
.venv/bin/python tests/browser-harness/scripts/audit_b0_openapi.py --output .runtime/b0_openapi_audit.json

cd tests/browser-harness
npm ci --no-audit --no-fund
npm run build
IT_TEM_PYTHON=/absolute/path/to/repository/.venv/bin/python IT_TEM_KOREAN_FONT=/path/to/an/installed/KoreanFont.ttf CHROME_BIN=/path/to/installed/Chrome-or-Chromium ./scripts/run-local-e2e.sh
```

Mac Studio validation used Python 3.13.12, Node 24.21.0, npm 11.19.0
and an installed Noto Sans Gothic system font. **No external model/GCP calls**.

Runner refuses occupied ports **18766** (FastAPI) and **4173** (Vite)
before starting, and uses only localhost. It checks the Python executable,
font file and Chrome binary. Both child servers are terminated on EXIT.
Every invocation uses a fresh isolated `.runtime/b0-XXXXXXXX` directory.
By default the synthetic source images, the isolated backend code and JobStore
are removed after execution; Network logs, results and screenshots are kept
for audit. To retain test-generated inputs/JobStore explicitly set
`B0_KEEP_TEST_DATA=1`. Never point this harness at a real public server.

Evidence published in `tests/browser-harness/evidence/` is from synthetic
test data only: UI screenshot, sanitized route/method/status trace, real
Chrome file checks, post-restart browser trace/screenshot and OpenAPI
compatibility diagnostic. No user photos/keys/cookies/provider responses.

**OpenAPI diagnostic only**: actual binary/UTF-8 FileResponse semantics
differ from the current generated `application/json { }` schema, explicit
404/409/413/503 response documentation is incomplete and TypeScript Job is
hand-maintained. These findings are **FOLLOW_UP**, not a license to alter
`response_model`, errors or method/path in this PR.

**Gates intentionally NOT VERIFIED**: Frontend Owner's official app B0,
authentication/HTTPS/security of shared hosting, Text v0.7 source compatibility,
B1 Compliance persistent server review, CostGuard Live integration,
B2 actual models. PR #6 `docs/API_LIST.md` remains separate.
