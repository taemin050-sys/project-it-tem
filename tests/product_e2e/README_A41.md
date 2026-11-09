# A4-1 — Official React Chrome OFFLINE_FIXTURE E2E

Scope: Track A only, real `app/src/main.tsx`/Owner #26 React UI and actual headless Google Chrome, **NOT** old B0 browser harness. Synthetic product photos, no paid models, no GCP. Never use real customer assets or an existing production database.

### Preconditions

- macOS Mac Studio, existing project Python 3.12 venv with Pillow/FastAPI/Uvicorn, repo `app/node_modules`, local Chrome.
- Existing pinned `playwright-core` module path accessible **read-only**; no npm network install needed on the verified Mac.
- Official A4-1 tests must **not** run on protected 18088/18095/18100, shared GCP QA or real Live.
- All provider API key environment variables must be absent/empty. The harness refuses to run if any are populated.
- Local Korean font path must exist. Do not copy proprietary font files into source or evidence.

### Reproduction from Track A worktree

```bash
cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
export A41_PYTHON='/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3'
export A41_PLAYWRIGHT_CORE_MODULE='/Volumes/SSD 4T/z_ai_asset/P03_it-tem/experiments/free-first-benchmark-lab/.tools/t06_browser_tools/node_modules/playwright-core'
export A41_FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
export A41_PORT=18538
bash tests/product_e2e/run_a41_offline_chrome.sh
```

An isolated `/private/tmp/ittem-a41-product-XXXXXXXX` folder contains the build, loopback FastAPI service, synthetic product images, disposable cookies, locally hashed invitation records, throwaway SQLite databases, and all **sanitized** screenshot/trace/PNG/Caption evidence. The runner kills its own web server on exit; it never stops/changes any preexisting service. A pointer to the latest directory is written under `/private/tmp/IT_TEM_A41_LAST_RUN_PATH`; only copy `evidence/`, **not** the invite token or runtime private SQLite, to audit packets. `git status` after the run must remain clean (the app build is ignored).

Browser script `a41_official_react_chrome.cjs` verifies login, two product photos, Composed 4:5 frozen Job, Copy revise and restore (same Copy SHA, new review SHA/generation, no old approval), Copy approval, one synthetic candidate, explicit image rejection/retry with new attempt/version/image SHA, old image SHA approval rejection, final SHA-checked Chrome PNG/UTF-8 Caption downloads and GET-only refresh, 390/360px real screenshots, unauthorized actor 401, authenticated foreign Job 404, count 2/3/4/mixed batch 422, external POST count 0. Local images are static synthetic pixels; they do **not** establish real model quality.

Python `a41_verify_offline_evidence.py` separately opens the **throwaway** three SQLite ledgers read-only, requires exactly two Image Attempts (REJECTED and COMPLETED with identical Prompt/Copy approval provenance), zero Queue/Cost rows, byte-exact download-vs-committed final SHA, PNG 1080×1350, Caption contains approved long-form caption + hashtags, and Receipt Head/Sub text SHA matching approved Korean strings.

**Known quality blocker `A41-PRODUCT-CTA-01`:** PM contract requires on-image CTA for new Composed 4:5, yet existing Image Owner v2 `feed-4:5` profile emits `cta_placement=platform` and Receipt `omitted_image_fields=["cta"]`. This is a **fail** of final product/advertising-quality acceptance, not a failed browser functional control. The verifier preserves `product_quality.gate=HOLD` and never silently changes Owner #24 layout, coordinates or PM decisions. Do not confuse 9:16 `DECISION_PENDING_PM_OWNER` with this already-specified 4:5 requirement.

Acceptance states: `BROWSER_E2E_PASS(OFFLINE_FIXTURE)` only; `4x5_ON_IMAGE_CTA=HOLD`, `REAL_PROVIDER_E2E=NOT_AUDITED`, `VISUAL_REVIEW=HOLD`, `HUMAN_PM_ACCEPTED=PENDING`, `GCP_A_QA_DEPLOYMENT_HOLD`, `PAID_WORKER_HOLD`, `NOT_RELEASE_READY`.

Owner Source First priority remains FE #26 > Text #27 > Image #24 > Serving; A2/A3/A3R/A3R.1 safety code unchanged. No part of this harness authorizes paid Worker activation, official dev/Owner PR changes, Source v3 retag, or GCP deployment.
