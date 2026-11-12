# IT-TEM P03 Track A — A5-1B-R1 Time Repairs, MPO Frame Provenance and GCP A Readiness: C-A Differential Submission

**Submitted for independent C-A audit; 2026-11-10 KST.** No C-A R1 verdict or real Owner/PM design approval is claimed. `FULL_FEATURE_BETA_DELIVERY_HOLD`, `COMMERCIAL_RELEASE_READY=NO`.

## 0. Fixed source & prior accepted authority

- C-A5-1B acceptance-with-notes baseline: Track A `847a9c891072cd561ca2f543de2f9aa9244bb7c7`, tree `13a17657387573b8cbefdffe392b7e92b06e0360`. Independent C-A5-1B report SHA `611ffac29f912e25f9bd1389a94cf413035a3f7ebfe3c5d847ae353d59241bc3`. C technical acceptance of signed Profile and synthetic product mask **subject to time fixes**, not full beta authorization.
- **R1 minimal bug-fix code commit:** `db70a60bbb845303888519f6d572899957b3b289`, tree `9f2b9642f5e5fe0e7ff25f7e1bb3321db70c3f84`. Exactly 4 changed files: `demo_staging/live/a51b_candidate_mask_gate.py`, `demo_staging/live/a51b_signed_beta_contract.py`, and their two existing test files.
- **Final actual tested source code commit including separate read-only MPO tool:** `ab1ee76462ba4a6935b7b9987d64557dba4dd138`, tree `47f09d081a8b88e51a2ff8a971aafbfbc5589a34`. MPO-only commit adds `scripts/a51br1_mpo_frame_readonly_probe.py` and `tests/demo_live/test_a51br1_mpo_frame_readonly_probe.py`; no original FE/Image Owner/Text Owner/Serving code modification. Subsequent evidence-only commit must be reviewed separately.
- **Differential review commands:** `git diff --name-status 847a9c8..db70a60` (R1 only), `git diff --name-status db70a60..ab1ee76` (MPO diagnostic only), `git diff --name-only ab1ee76..final HEAD` (must be docs/evidence only). All source is local Mac Studio canonical Track A repo.
- R1 preserves existing historical v2 jobs/receipts and A5-1 A/C local offline Chrome C-A51 acceptance. Does not change batch/single candidate, FE #26 > Text #27 > Image #24 precedence, worker, GCP or GitHub official dev.

## 1. Two C-A findings: repair details and negative coverage

### P1-01 Signed future-dated mask review (FIXED IN CODE)

- Prior condition `abs((now-review).total_seconds()) <= 90d` falsely accepted a **+30-day future** review with valid dual signatures.
- Now `validate_review_time(review_time_utc)` parses timezone-aware UTC only, requires review `<= now + 30 seconds` (explicit bounded clock skew) AND `now - review <= timedelta(days=90)`; reject naive, non-UTC, malformed, future +31 sec, +5 min, +30 days, stale 90 days +1 second. Past 90 days exactly and current time accepted in deterministic frozen-clock tests.
- Two separate integration scenarios generate VALID THROWAWAY Ed25519 signatures for future +5 min/+30d and call the actual `/compose` endpoint. Both rejected and leave Job IMAGE_APPROVED and no final PNG. No real user signatures or media involved.
- Explicit `LiveGateError` codes are preserved after parse: rejection must not accidentally be swallowed by the `ValueError` handler.

### P2-02 Signed Profile max 90-day window (FIXED IN CODE)

- Prior `(end-start).days>90` floored fractional days and admitted >90d.
- Now exact `end-start > timedelta(days=90)`, with timezone-aware UTC validity checks and timestamp order. Exact 90d accepted; 90d+1sec, +23h rejected. Every test re-signs the altered activation JSON under separate throwaway Image Owner+PM Ed25519 keys and verifies actual trusted-pinned-public-key checking. Fail-closed errors remain distinguishable.

### Measured code & regression

| Actual Mac Studio execution | Result |
|---|---|
| R1 signed-time/beta-mask targeted suite | **52/52 PASS** |
| Standalone MPO frame provenance tests | **5/5 PASS** |
| FULL Python suite after both code commits | **1,223/1,223 PASS** |
| React | **57/57 PASS** |
| ESLint / Vite Build with `VITE_IT_TEM_CODE_SHA=ab1ee764...` | PASS / PASS |
| JS bundle SHA-256 | `256bc2197aefefd8d5e9ea5ba642584efb1c8fdb2d233fda05c317d4cc65c0bd` |
| Local source manifest & test logs | `docs/integration/evidence/A51BR1_20261110/` |

**Evidence status:** Developer self-test/manifest PASS; new C-A independent R1 replay **PENDING**. C-A should independently rerun new boundary tests and inspect only the R1 diff (not full old A2–A5 security audit absent regression evidence).

## 2. MPO policy and actual user photo checks (READ ONLY)

Local source `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/잘나온 화장품 모음` remains unchanged. `a51br1_mpo_frame_readonly_probe.py` cryptographically inventories all original containers without selecting a frame, exporting a normalized image, copying images into Git, sending files to Provider or altering originals:

- **24 files, 9 decoded JPEG, 15 decoded two-frame MPO = 39 decoded frames total.**
- **15/15 MPO frame0 and frame1 RGB pixel SHA values differ.**
- C-A51 prior original raw SHA **24/24 exact same**. No rights/brand/license acceptance.
- Important source-first discrepancy: `src/image_generation/assets.py` accepts MPO and silently selects frame0; `src/serving/job_api.py` selects frame0 only for `.mpo` filenames and records provenance, but renamed `.jpg` files internally MPO are rejected by provisional JPEG route. Current real photos are JPG-named MPO. The Owner must choose explicit frame-selection or fail-closed policy for **NEW signed beta**, not retroactively rewrite v2 Owner behavior.
- Owner/PM decision packet `BP18_A51BR1_MPO_OWNER_DECISION_AND_SOURCE_FIRST_CONTRACT_20261110.md`. Recipients: Image Owner 박지수, Frontend Owner #26 and PM 이태민. Delivery `PREPARED_NOT_CONFIRMED_DELIVERED`; formal policy decision and actual authorization **PENDING**.

## 3. GCP A: exact known ledger mapping, no unauthorized changes

C-A5-1B independently ran the new A-only read-only probe via previously authorized SSH. Known source `9879eb0f85747312a224ecd898aaff84d834590b` remains older. App `live.sqlite:live_image_attempts` **8 COMPLETED**; `queue.sqlite:queued_ops` **0**; `cost.sqlite:attempts` **0**; **separate Owner paid Provider `owner_image/image_attempts.sqlite` absent**. Do not confuse app attempts with billable attempts, and do not auto-create Provider ledger or migrate protected live DB.

New A-only candidate plan `BP18_A51BR1_GCP_A_ISOLATED_BETA_DEPLOYMENT_READINESS_AND_ROLLBACK_20261110.md` pins source, frontend bundle, font, dependency locks, real auth/actor, backup/WAL/rollback, worker-disabled separate runtime, 3-ledger consistency and explicit hard budget. **No new GCP SSH was needed or executed by developer in this R1 work unit**, no GCP write, no DB migration, no paid Provider. Existing read-only C-A remote report remains point-in-time evidence, not proof of current A5-1B deployment.

## 4. Seven mandatory PM beta gates

| PM beta gate | Current |
|---|---|
| `SOURCE_AND_SECURITY_PASS` | Developer R1 1,223 tests & source locks PASS, **C-A R1 pending**, actual GCP Runtime unverified |
| `PROFILE_V3_RUNTIME_PASS` | C-A51 A/C local fixture PASS, C-A51B signed contract synthetic-mask technical PASS, **real signatures, rights, live authorization HOLD** |
| `OWNER_INTEGRATION_PASS` | Accepted local React E2E; actual A-only Worker/paid model chain NOT_AUDITED |
| `REAL_PROVIDER_E2E_PASS` | **0/6** real Provider independent single-image Jobs |
| `UI_UX_BETA_PASS` | Browser local fixture accepted; team GCP Signed SSO+live UX NOT_AUDITED |
| `VISUAL_QUALITY_BETA_PASS` | Real product/logo/label masks and Brand/Claim QA NOT_AUDITED |
| `TEAM_UAT_READY` | No latest signed/runtime/SSO/team accessible beta accepted |

**A5-1B-R1 signoff and future candidate deployment:** C-A may accept time repairs independently. It must **not** promote test signatures, synthetic mask, two-frame source inventory or an offline frontend bundle to actual product quality, cost permission or team release. `FULL_FEATURE_BETA_DELIVERY_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

## 5. Request to C-A and Owner/PM

- **C-A differential:** independently confirm the exact R1 four-file time diff and separate two-file MPO read-only probe, replay signed positive/negative boundaries, manifest SHA, historical contract and latest source integrity.
- **Image Owner/Frontend/PM:** decide MPO explicit frame preview/selection vs outright reject, author source SHA/frame/orientation/ICC/normalized SHA contract; provide rights-cleared same-product images and actual mask review; don't reapprove fixed 2 modes/3 ratios/1 candidate policy.
- **Infra/PM:** approve only a strictly A-only isolation rollout plan, schema/backup/rollback, Signed SSO+Actor, genuine authorization, hard spend cap, Owner Provider/Cost/Queue reconciliation, before any actual GCP deployment or paid model calls.
- **Full-feature beta:** 6 separate real model single-image Jobs, artifact/caption SHA, Owner/PM visual acceptance and real team browser UAT are still required. No `CONDITIONAL_GO` for missing major capabilities.
