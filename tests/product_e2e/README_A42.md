# A4-2 — Five remaining official React Chrome fixture E2Es

A4-S01 Composed 4:5 already C-A accepted. The new A42 harness is intentionally **separate** from the C-A accepted A41 harness and does not modify product code or Owner source.

## Scenario matrix

| Scenario | Mode | Ratio | PNG | Product quality |
|---|---|---|---|---|
| A4-S02 | composed | 3:4 | 1080×1440 | VISUAL/HUMAN PM REVIEW PENDING |
| A4-S03 | composed | 9:16 | 1080×1920 | CTA DECISION_PENDING_PM_OWNER |
| A4-S04 | freeform | 4:5 | 1080×1350 | MODEL-DRAWN KOREAN TEXT NOT AUDITED IN FIXTURE |
| A4-S05 | freeform | 3:4 | 1080×1440 | MODEL-DRAWN KOREAN TEXT NOT AUDITED IN FIXTURE |
| A4-S06 | freeform | 9:16 | 1080×1920 | MODEL-DRAWN KOREAN TEXT NOT AUDITED; 9:16 CTA PENDING |

All tests use the *actual official React frontend*, Chrome on 127.0.0.1, disposable Actor and Job, synthetic source images and OFFLINE_FIXTURE. 2 product photographs, 0 reference; per scenario 15 steps with copy revise and restore, stale approval rejection, single image candidate 1 then explicit 2nd Attempt, new SHA, actual PNG/Caption download, 390/360 screenshot, GET-only refresh, wrong Actor 401/404, batch count 2/3/4/mixed HTTP422, Queue 0, Cost Attempt 0, external paid POST 0.

Freeform must not contain a server text overlay: expected receipt contains rendering=provider_drawn_text, *no font_sha256 and no placements*. Fixture source image is solid-color synthetic, so correctness of real model-generated Korean text is **NOT_AUDITED**, not PASS. Composed 3:4 has CTA on image under existing v2 contract; the rendering is mechanically bound by Receipt SHA, not a human advertising quality PASS. Composed 9:16 CTA platform vs on-image remains undecided by Owner/PM.

## Controlled Mac Studio reproduction

Use exact existing read-only local Playwright-core and Python venv paths; do not install new dependencies without approval.

    cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
    export A41_PYTHON='/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3'
    export A41_PLAYWRIGHT_CORE_MODULE='/Volumes/SSD 4T/z_ai_asset/P03_it-tem/experiments/free-first-benchmark-lab/.tools/t06_browser_tools/node_modules/playwright-core'
    export A41_FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
    export A42_PORT=18540
    unset OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY
    bash tests/product_e2e/run_a42_five_scenarios.sh

The runner is local Mac only, refuses protected ports or occupied port, rejects provider keys, disables Live/Worker, creates a disposable /private/tmp/ittem-a41-product-a42-* folder, restarts no global process, and terminates **only its own loopback** uvicorn. It stores sanitized evidence under its private evidence_five folder and a pointer to the latest root in /private/tmp/IT_TEM_A42_LAST_RUN_PATH. Never add an invitation token, cookie, SQLite/WAL/SHM or secrets to audit evidence.

Each scenario gets an independently saved 12-screenshot set, browser_trace.json, actual ad_<width>x<height>.png, caption.txt, read-only SQLite + Receipt verifier JSON and sha manifest. There is one localhost service for the five Jobs; a per-Job Attempt count is verified with image_attempts for that Job and Queue/Cost ledger remain empty globally.

This is an **OFFLINE_FIXTURE browser functional test only**. It does not execute real model VLM, live Queue/Worker, commercial font licensing, PM human visual acceptance, GCP A deployment, receipt invoice reconciliation, or paid Worker authorization. C-A should independently replay from a fixed Git archive and compare SHA, 5 separate state traces and downloads.

All previous A2/A3R.1 security, A4-1 accepted browser code, and Owner FE/Text/Image code must remain unchanged.
