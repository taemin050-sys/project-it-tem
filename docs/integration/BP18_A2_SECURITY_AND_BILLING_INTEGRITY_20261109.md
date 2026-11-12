# IT-TEM P03 — A2 Worker / Queue / Billing / Prompt Security Implementation Audit Packet

Date: 2026-11-09 KST
Session: Track A — Owner Source First developer; **self-verification only**.
Authority: C independent A1.2 audit `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A12_FE_PM_INDEPENDENT_AUDIT_20261109.md`.
Disposition: `A2_DEVELOPER_VALIDATED_WITH_KNOWN_PYTHON_FAILURE / C_A2_AUDIT_PENDING / REAL_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

## Immutable scope / commit pins

- A worktree: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`
- Branch: `integration/bp18-baseline-e2e-20261111`
- Starting HEAD: `316c40420ab81bba53a92e4041e3dbd4ade5a91c`; Tree `f4f17b2b169d6a782e2fed277a9a2c1456e2a955`; CLEAN.
- A2.1+A2.2 code: `a2d984efc4599f5b3102b2ac7cecfdfc10c9059b`; Tree `7cab506af25a11a13dd33398468e73c6c29a53ee`.
- A2.3+A2.4 code: `62da379df8be7750f6cde5f5be74e64a10443585`; Tree `d42adec2bf2354c630f0ceaf8be8b1bc938afe35`.
- Official `dev`, Owner PRs, Track B, GCP A/B, Protected Live 18088, Historical QA 18095, pre-existing Job/Artifact/DBs **not written/deployed**.
- No provider key supplied to tests. **Actual paid Provider POSTs: 0.** Synthetic LIVE provenance is explicitly isolated and does not prove real paid execution.

## Defect-by-defect reproduction → cause → fix → negative validation

### P0-01 — Worker revoked Actor / unauthorized Job

- **Before:** C independent fixed-source reproduction on `316c404` queued revoked Actor but `_run_locked` still invoked fake `flow.text` and marked Queue SUCCEEDED. Worker had no current server-side Actor/Job ACL check.
- **Cause:** Worker trusted the durable Queue tuple and a startup `approved_actors` snapshot; did not query latest allowlist, live Job owner, B0 web ledger, Stage/State or Approval immediately before dispatch.
- **Fix:** `demo_staging/live/worker.py:authorize_worker_item` verifies current worker gate environment/allowlist, initial approved Actor snapshot, `demo.sqlite3` Job ownership, B0 Job status, LiveStore Job/Actor/Mode/State/Stage, Queue Context and approved Copy/Prompt. `pipeline._guarded` invokes the same gate before reservation, before dispatch intent and immediately before actual provider callback. Invalid work is held and does not reach Provider.
- **Validation:** `tests/demo_live/test_a2_worker_authority_billing.py` revocation after queue, stale allowlist, foreign Actor, disabled execution, canceled Job, bad Stage, normal authorized Task, pre-billable revocation and host SingleFlight. Negative: Provider callback 0; CostLedger Attempt 0 when revoked before dispatch.
- **Residual:** A revocation arriving *after the final check and after external Provider HTTP send starts* cannot undo an already-sent paid request. A future online administrative revocation writer should coordinate with a serial execution lease/epoch; do not claim synchronous abort of in-flight provider charges. No unapproved revocation mechanism was added.

### P0-02 — Queue vs CostLedger vs Owner Provider Attempt crash recovery

- **Before:** C independent fixed-source reproduction: Queue RUNNING → `BILLING_UNKNOWN`, CostLedger persisted `DISPATCHED` after restart; cost reconciler not invoked by worker. This is not evidence that a paid API was actually charged.
- **Cause:** `queue.reconcile_restart()` ran alone. Three independent SQLite ledgers cannot be covered by a single atomic transaction and the worker could otherwise claim unrelated work while billing uncertainty persisted.
- **Fix:** `reconcile_worker_ledgers()` runs *under host SingleFlight lock* and idempotently invokes both CostLedger `reconcile_crashed_dispatches()` and Queue `reconcile_restart()`. Conservatively HOLDs further LIVE claims if Queue `BILLING_UNKNOWN`, CostLedger `RESERVED`/`DISPATCHED`/`BILLING_UNKNOWN` or Owner Image `submitting`/`failed`/`unknown`. Missing/corrupted Image ledger schema fails closed. The Worker loop terminates with `LIVE_WORKER_BILLING_HOLD`, not another POST. A `SUCCEEDED_USAGE_UNPRICED` Receipt is never erased or fabricated as actual USD.
- **Validation:** Three simulated crash points (reserved/dispatched/usage persisted), repeated reconciliation, no identical `reserve` replay, no new attempts, independent Owner Image submitting/corrupt DB, concurrent worker lock. Queued work preserved in status for manual incident review. Existing `tests/demo_live/test_receipts.py`, `test_queue.py`, `test_bp17_no_replay_operational_recovery.py` retained.
- **Manual resolution:** Do **not** delete, reset or re-queue an unresolved record. Reconcile the Queue task ID, Job/Actor/Stage/Context SHA, CostLedger Attempt ID/status, Image Provider Attempt ID/state/Provider Response ID/usage, provider billing dashboard and Job/Artifact receipts. Preserve evidence. A controlled incident-specific operator decision and independent C/PM approval are required before clearing HOLD. No automatic refund or replay is implemented.

### P0-03 — OFFLINE_FIXTURE → LIVE Prompt provenance

- **Before A own reproduction:** On pre-A2 source, `test_fixture_cannot_be_promoted_to_live_prompt_even_with_enabled_flags` reached the mocked billable gate from a Fixture Job. An altered `mode='LIVE'` with stored Fixture Text checkpoints also reached that gate. Both reproduced with **zero real provider calls**.
- **Cause:** `pipeline.prompt` did not compare requested `offline` flag with persisted Job mode or verify upstream Analysis/Research/Copy checkpoint mode/content before constructing LIVE Provider.
- **Fix:** Mode comparison before Provider construction; LIVE path requires immutable LIVE `vision`, `research`, `copy` checkpoint provenance and content equality under the exact Job/Input SHA, Owner model ID and stage inputs. Mismatched Fixture mode or forged LIVE job is denied before `_guarded`. Authoritative stored Job mode is not set by browser.
- **Validation:** `tests/demo_live/test_a2_prompt_provenance_cas.py`: Fixture→LIVE denial, LIVE Job forged from Fixture checkpoints denial, normal Fixture path, synthetic LIVE checkpoint/Owner-FakeProvider positive. The latter is **fixture-only proof of data contract**, not a real charged model run.

### P0-04 — In-flight Prompt Approval / Review Policy CAS

- **Before A own reproduction:** A initial source accepted a stale Prompt when a provider fake edited Copy, restored identical Copy bytes and re-approved a higher generation before returning; it also accepted results after policy epoch changed. Both independent tests **failed before repair**, without network.
- **Cause:** `store_prompt` tested only current state `COPY_APPROVED` and self-consistent approval, not the Approval/Review/Generation/Policy Context captured at the start; checkpoint was committed **before** State CAS.
- **Fix:** `LiveStore.prompt_context` binds Job/Actor mode, Input, Copy/Review/Approval SHA, Generation, Analysis/Research/Plan/Compliance SHA, actual Text `rules.yaml`+`rule_checker.py`+`report_builder.py` SHA, operator review policy epoch and image-layout Template SHA. Copy approval persists immutable `live_copy_policy_bindings`. Prompt source is recorded in an append-only `live_prompt_context_bindings` row and the latest complete context is checked under `BEGIN IMMEDIATE` before Prompt commit. After provider usage is durably captured, Job CAS is committed before non-authoritative checkpoint memoization, preventing stale checkpoint insertion after CAS failure. New Prompt checkpoint versions use `text_revision_checkpoints` keyed by context; historical single-slot rows remain readable without overwriting.
- **Queue/next-stage link:** `queue-prompt` context now hashes the full approved context including policy epoch. Worker revalidates before execution. Image request, image candidate commit and explicit retry all enforce the stored Prompt binding; an old/changed policy cannot silently reuse Prompt in next paid image stage.
- **Validation:** Copy edit/revert/reapprove while Prompt in flight denied; policy changes during generation and before Worker dispatch denied; subsequent image request under different epoch denied; one winner among two concurrent fixture Prompts; synthetic successful LIVE lineage; separate approved generation gets a new checkpoint; a simulated paid response with real `ReceiptSink` usage is preserved in CostLedger `SUCCEEDED_USAGE_UNPRICED` even though stale Prompt is not committed; new provider POST is **never automatically retried**.

## Code / tests changed

- Production changed: `demo_staging/live/worker.py`, `pipeline.py`, `store.py`, `http_api.py`, `checkpoints.py`. Existing `demo_staging/live/queue.py` source remains unchanged; worker-side coordination is implemented against its current queue contract.
- Added: `tests/demo_live/test_a2_worker_authority_billing.py` (16 tests), `tests/demo_live/test_a2_prompt_provenance_cas.py` (10 tests).
- Updated synthetic test harness to respect real ACL/CostLedger: `tests/demo_live/test_owner_text25_revision_worker_transport.py`, `test_pm_track_a_single_candidate.py`, `test_shared_evaluation.py`. These preserve rather than weaken test safety assertions.
- Unmodified Owner sources: FE #26, Text #27, Image #24 Owner paths, including `src/image_generation/composition.py` A Unicode compatibility patch. No frontend TS code changed in A2.

## Regression / evidence / F-V-S38

- New A2 focused safety suites: **26/26 PASS** (16 Worker/Cost/Owner Image + 10 Prompt provenance/CAS).
- Python entire repository: **995 passed, 1 failed**, exit 1. Only failure `tests/demo_live/test_bp17_shared_minimal_export.py::test_existing_output_replaced_never_after_concurrent_publication` (historical macOS Python3.12 `fork`+SQLite concurrent publication failure; present before A2). **No skip, removal or weakening; FULL PYTHON PASS NOT ACHIEVED.**
- React full `npm --prefix app test`: **57/57 PASS**; `npm --prefix app run lint`: **0 warnings/errors**; `npm --prefix app run build`: **PASS**.
- Safeguarded no-paid test environment unsets OPENAI_API_KEY/GOOGLE_API_KEY/GEMINI_API_KEY/ANTHROPIC_API_KEY and sets `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO`. Some isolated FastAPI tests temporarily monkeypatch LIVE flags and synthetic workers; they have no key or network access and do not invoke real provider calls.
- Repro logs written only to isolated Mac temp paths: `/private/tmp/ittem_a2_prompt_before.log`, `/private/tmp/ittem-a2-full-post-policy-20261109.log`, `/private/tmp/ittem-a2-react-test-20261109.log`, `/private/tmp/ittem-a2-react-lint-20261109.log`, `/private/tmp/ittem-a2-react-build-20261109.log`. Those temporary paths are not durable product artifacts; reproducible pytest commands above are SSOT.
- Relevant Release Master r0.1: `F01, F05, F09, F10, F11, F12, F13, F16, F17, F19, S01, S02, S03, S04, S06, S09, S10`. Status: **CODE_IMPLEMENTED + ISOLATED_FAKE/QA_PASS only** for covered portions. No F/V/S38 aggregate acceptance, no real Provider E2E, no manual Product/PM/Owner UAT. `F09` real LLM-compliance check remains unproven. Release Master proposal awaits Owner/PM approval.

## C-independent audit request and residual risks

1. Reproduce P0-01 revoked Actor **before provider** and verify B0 ownership/LiveStore/Queue stage checks and last-mile _guarded check (zero paid/zero attempts).
2. Reproduce P0-02 DISPATCHED vs RUNNING cross-ledger crash and verify both transition to HOLD; verify Owner Image `submitting`, missing/corrupt schema and idempotence. Confirm old completed artifacts and receipts unchanged.
3. Reproduce A-specific Fixture→LIVE Prompt bypass and forged Job mode; confirm no `OfficialTextProvider` construction or paid Attempt before denial.
4. Reproduce in-flight Copy changed/reapproved and policy epoch drift; verify CAS, append-only prompt/approval records, LIVE upstream checkpoints, Image link, and receipt durability.
5. Re-run A1.1, A1.2, PM one-image/2mode/3ratio, Actor Signed SSO, EX12 GET-only, existing Python full known failure and React/lint/build; compare Git HEAD and committed source.
6. Verify A2 worktree only, no official GitHub push/merge or GCP deployment. C signoff required before any switch in real paid Worker HOLD.

**Open:** Existing macOS Python fork+SQLite failure; legacy LIVE approval lacking newly introduced policy binding must fail closed and be manually re-reviewed rather than silently migrated; administrative revocation during an in-flight external POST cannot retroactively cancel that provider charge; external provider actual usage/invoice reconciliation and per-model entitlement remain untested; C independent verification and real-Signed-SSO/GCP A deployment gates pending.

**Release decision:** `A2_DEVELOPER_VALIDATED / C_A2_AUDIT_PENDING / REAL_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
