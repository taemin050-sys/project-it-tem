# IT-TEM P4-Preflight Stage 2 — Research / Planning / Image Adapter + Failure & Cost Guard

> **PROVISIONAL / NOT TEAM-APPROVED — 2026-10-24.** Build on `fa2c597` (`feat/p4-parallel-preflight`). This document is a proposal, **not** `docs/interface_spec.md` and **not** a change to official API contracts.

## 1. Deliverables / ownership

| Internal module | Responsibility | Owner review |
|---|---|---|
| `p4_research_adapter.py` | Normalize external search results to `Evidence` (unverified by default), reject duplicate IDs/unsafe reference schemes, preserve source type, retrieve timestamp | Research/Planning + Backend |
| `p4_planning_bridge.py` | Transfer only actually collected sources into `PlanResult`; reject changed product identity, invented/rewritten evidence and false `research_performed` | Planning/Text |
| `p4_image_adapter.py` | Inject image-team `ImageGenerator.generate(VisualBrief, product_images, reference_images)`. Validate generated file bytes, MIME, dimensions, digest, `mock`/billable mode; emit `ImageResult`, `GenerationReceipt`, bytes (memory only) | Image + Backend |
| `p4_cost_guard.py` | SQLite single-host reservation by `(job_id, stage)`; request fingerprint; local estimated spend budget in **micro-USD**; opt-in paid-call gate; no automatic retry; uncertainty after timeout/error; suppress repeated dispatch | Backend/Infra + PM |

No files in `src/serving/main.py`, `text_adapter.py`, `text_workflow.py`, `job_store.py`, `mock_workflow.py` were changed. All existing `/api/v1` requests, responses and state machine remain untouched. **No new HTTP endpoint is exposed** and the image adapter does **not** save candidates to `JobStore` yet.

## 2. What the tests prove — and do not prove

- Existing **65 tests** + Stage 2 tests for input normalization, evidence provenance, independent image handoff, file integrity, duplicate suppression across SQLite guard instances, budget exhaustion, 429/502/503/504 and crash-held reservations.
- `SearchHit` test inputs and `FakeImageGenerator` are synthetic **fixtures**, not live web results or model generations.
- `mode="live"` is a provisional trusted-provider assertion. The adapter does **not** verify whether a web page or paper was fetched or whether a claim is accurate. Only the research owner can attest `live`; production needs retrieval logs/citations and verification.
- Research results are always `verification_status="unverified"` until independently checked.
- Budget reservation is an **upper-bound estimate**, not actual OpenAI billing or precise cost monitoring. A successful paid call can still have unknown actual charge. Reservations are deliberately not auto-refunded.
- Default `enable_billable=False`; any *real* provider wiring requires explicit authorization, separate actual-price/limit policy, credential and service gates, and persistence/reconciliation acceptance.
- Existing P4A `/ai/plan` / `/ai/copy` do **NOT** use the Stage 2 SQLite ledger yet. They have their earlier in-process guard. **Do not enable paid traffic on those routes claiming that Stage 2 ledger enforces their budget.** Integrate after Monday's contract and owner decision.
- SQLite ledger is only one host and one database path; it is **not** shared distributed locking, billing reconciliation or a production-grade billing system. Crash leaves `reserved`, which blocks re-dispatch until operator reconciliation. No auto-retry on 429/timeout.
- Image product identity preservation is **not** verified automatically. It is explicitly `preservation_review="pending"`; the model owner's human/evaluation checks are still required.

## 3. Minimal integration guides by team

### Research / Planning team

1. Implement `SearchProvider.search(ProductFacts) -> list[SearchHit]` for one approved search source; capture **actual** source URL/DOI and retrieval time outside the LLM. No provider calls by default.
2. Normalize hits with `normalize_hits(...)`; pass `ResearchBundle` into `build_plan(planner, facts, bundle)`.
3. Check that the product identity and cited evidence stay unchanged, and that research is never marked performed when there was no verified external retrieval. Sources may still be `unverified` and cannot be represented as factually corroborated.
4. PM decision needed: web, academic search, browser-use provider scope; evidence validation standard, quota per job, and factual evaluation criteria.

### Image team

1. Implement only `ImageGenerator.generate(VisualBrief, product_images, reference_images) -> GeneratedImage` in the team's wrapper; backend retrieves bytes by validated `asset_id` from `JobStore` after **COPY_APPROVED** and passes them to the wrapper.
2. Match `content_type` and actual magic/decoded format, dimensions and bytes; do **not** generate Korean copy inside the image. Preserve original product packaging/labeling.
3. Backend calls `generate_handoff(...)` with one candidate; it returns `ImageResult` + bytes + `GenerationReceipt` after contract checks; **not persisted until separate integration work**.
4. PM decision needed: exact image provider/method, input image/reference-image limits, permitted formats, price ceiling, candidate persistence and product-preservation QA.

### Backend / Infra

1. Before provider dispatch, verify `job.status == COPY_APPROVED` and matching `copy_revision`, request authorization, source-asset ownership and credential/feature gates. These checks are **not** performed by this internal image adapter.
2. Use per-job/phase reservation with `P4CostGuard(db_path, max_budget_micro_usd, enable_billable=False)` for mock-only test; `enable_billable=True` is a **deliberate explicit switch** for approved paid traffic, not automatic.
3. Derive `operation_key` from a stable user action/idempotency key; a repeated request returns 409 and **must not** call again; frontend GETs job status. Do not include secrets/PII in ledger; it stores request hash, not request body.
4. Manual reconciliation is required after billing-uncertain provider timeout/error or VM interruption. Never auto-retry.
5. After team approval, integrate actual provider results into existing JobStore transition/storage atomically, add app-level contract tests, and only then expose / enable live image route.

### React / PM

- **No change** to current React mock flow or provisional TypeScript client. HTTP status proposals here are *internal* until approved.
- Monday decisions: existing workflow 409 (bad state); Stage 2 candidate error semantics 429 budget or throttling, 502 invalid upstream, 503 provider not ready, 504 timeout; no automatic retries. Separate provider billing from approval and show `pending` QA.

## 4. Verification

```bash
python -m pytest -q
python -m scripts.export_p4_contracts --output .runtime/contracts
git diff --check
```

For the GCP verification of **this patch** (with current sources already at commit `fa2c597`): expected **107 passed** and unchanged 8 exported artifacts (7 schemas + 1 OpenAPI, with manifest as the ninth file). If GCP differs, treat local results as inconclusive and stop before commit.

## 5. Monday decisions and readiness blockers

1. Assign trusted provider for web/paper/browser search and Evidence claims verification, with tool provenance audit.
2. Approve per-provider and per-job cost estimates/budget; implement reconciliation for uncertain billing.
3. Decide owner of VisualBrief and approved copy revision; image-team wrapper input and actual image quality acceptance.
4. Authorize safe image storage/approval integration and final composer tests; baseline still P3 Mock.
5. Finalize `docs/interface_spec.md` with PM; regenerate type/schema artifacts, confirm React integration, choose limited paid smoke testing only afterward.
