# IT-TEM P03 / Track A — A5-1B Signed Beta Profile + Candidate-Mask C-A Differential Submission

**Date:** 2026-11-10 KST
**Status:** `A51B_DEVELOPER_VERIFIED / C_A51B_INDEPENDENT_AUDIT_PENDING / FULL_FEATURE_BETA_DELIVERY_HOLD`.

## 0. Fixed authority and work unit

- Prior fixed C-A5-1 accepted source and evidence HEAD: `7681addc04af9a5ba23c862e10d35061885a0a0e`, Tree `f01b22ce67e3ee9b4fb50b497ea5a76aff9634fe`.
- Official C-A51: `C_A51_A_C_PROFILE_V3_OFFLINE_RUNTIME_AND_BROWSER_E2E_ACCEPTED_WITH_BETA_HARD_GATES`; report `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A51_PROFILE_V3_RUNTIME_INDEPENDENT_AUDIT_20261110.md`, SHA `f2bf10708625479158567dd452b4cd803293d30ac4eb45546847f37968ffb36d`.
- **New A5-1B tested code HEAD:** `a08c5c7ea68d5863ecf68eae98d468e319aa2f6f`, Tree `b9d80a196b8f4c1d2cc3e0cfc32856790d7ca5a3`.
- `git diff --name-status 7681add..a08c5c7` contains only `demo_staging/live/{store,template_contract,pipeline,a51b_signed_beta_contract,a51b_candidate_mask_gate}`, new scripts and new tests. **Original Image Owner `src`, React `app`, v2 Jobs, existing A5-1 accepted A/C local Chrome evidence, Track B and official dev/Owner PRs untouched.**
- C-A assessment requested **only for A5-1B new signed contract, mask/rights hard gate, data provenance, GCP future readiness**. Do not reopen already accepted A2–A5-1 source without a demonstrated regression.

## 1. New implementation accepted by development tests; not yet C-A

**Signed immutable NEW Job contract:** distinct `OWNER_COMPOSED_4X5_V3_SIGNED_BETA_A|C` and version `owner-composed-4x5-v3-signed-beta1`. Real Ed25519 detached **dual Image Owner+PM signatures** over exact activation JSON bytes are validated using OpenSSL 4 local public key verification, with pinned external trust-root key SHA-256; independent roles and expiry checked, source design SHA/Font SHA/License SHA/Policy Epoch frozen; deleted/changed signatures trigger Fail-Closed on later Owner request or compose. **All tested signatures use throwaway TEST keys, not real PM/Owner.**

**No unauthorized LIVE:** `IT_TEM_A51B_NEW_JOB_ENABLE` and `IT_TEM_A51B_PROFILE=A|C` are explicit server-only operators, not user-selectable Gallery. New signed-profile integration is still OFFLINE_FIXTURE ONLY: LIVE, LIVE_EXECUTION_APPROVED or billable Text flags block, Provider request cannot be elevated, and `real_provider_permitted=false`, `real_customer_assets_permitted=false` remain. Signed geometry is **not** a spending, law or model quality approval.

**Actual Owner composite candidate-masking:** another detached dual-signature record binds candidate PNG SHA, Job ID, Copy SHA, Approval SHA, policy epoch, signed Profile SHA, layout SHA and exact 1080×1350 binary Mask SHA. Check nonempty 0/255 L PNG, authorized private on-host path, Head/Sub/CTA no intersections and **after-Pillow source-to-final protected RGB pixel preservation**. Missing or tampered mask, stale approval/epoch, changed product pixels, CTA collision or missing evidence fails closed BEFORE final artifact writes. Receipt binds verified geometry/mask SHA, but explicitly says `real_product_rights_authenticated=false`, `actual_brand_label_preservation=NOT_AUDITED`, `paid_provider_authorized=false`, `human_pm_visual_accepted=false`.

**Product policy held fixed:** user chooses one Freeform/Composed and one 3:4/4:5/9:16; exactly one candidate per request, explicit regeneration; no Batch/Gallery/extra A/C product mode. FE #26 > Text #27 > Image #24 > Serving; Composed 9:16 CTA final policy still pending.

## 2. Actual validation / evidence

| Validation performed on Mac Studio | Result |
|---|---|
| New targeted signed activation + owner mask + read-only predeploy tools | **38/38 PASS** (Exit 0) |
| Complete Python tests, including accepted A5-1 and old v2 | **1,199/1,199 PASS** (Exit 0) |
| React test | **57/57 PASS** |
| React Lint | **0 errors / warnings** |
| Vite offline fixture Build | **PASS** |
| JS asset SHA-256 from source-labeled build | `7427c697b6824ac3866cf567e91e5491b69deb3ad479eedf3b005b69ce6c122b` |
| 24 supplied original photo SHA vs previous independent C-A51 CSV | **24/24 exact unchanged** |
| Actual signed Owner/PM + verified mask on customer brand | **0; NOT_AUDITED** |
| Real Provider paid E2E | **0 of required 6 separate Jobs; NOT_AUDITED** |
| GCP A deployed HEAD/SSO/rollback | **No new deployment; NOT_VERIFIED** |

Developer evidence: `docs/integration/evidence/A51B_20261110/`: full/targeted Python logs, React/Lint/Build, local photo **metadata only** and C-A inventory SHA reconciliation, JSON build/source/gate summary, SHA manifest. The tests generate private temporary synthetic Ed25519 keys and masks only while running; no actual keys, customer photo bytes, masks, legal documents, DBs, secrets or paid Provider receipts enter Git.

### Source photo risk requiring explicit Owner decision

The 24 user-provided *JPG-extension* files in `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/잘나온 화장품 모음` are **9 actual JPEG** + **15 actual 2-frame MPO files**, 10 filename-based product groups, 1 exact duplicate pair, 0 reported corruption. All 10 groups offer 2–5 distinct filename-grouped images, but those are only LOCAL QA candidates. An MPO is not a standard single-frame JPEG transfer contract; **do not auto-select first frame, falsely label MPO as JPEG, silently convert or send without Image Owner input/canonicalization/permission**. Rights proof in folder is absent. One previewed product photo shows hand-held/sideways packaging; that is an isolated observation, not evidence that all product sources are upright or suitable for commercial composition.

There is **no real logo/label segmentation mask** for these photos and no validated source→generated product exact reproduction. Signed mask tests operate only on synthetic geometry and do not satisfy actual product quality. Mask success is not a substitute for human product/brand label fidelity validation.

## 3. GCP A beta deployment preparation: read-only and hard gate

C-A51 has already verified via authorized SSH: deployed old source `9879eb0f85747312a224ecd898aaff84d834590b`, application `live.sqlite:live_image_attempts` 8 COMPLETED, Queue `queue.sqlite:queued_ops` 0, Cost `cost.sqlite:attempts` 0; **separate Owner Provider `owner_image/image_attempts.sqlite` missing**. These distinct ledger types must not be confused. **This A5-1B development unit did not repeat GCP SSH, deploy, initialize a DB, or change remote runtimes.** Its `a51b_gcp_a_readonly_ledger_probe.py` is ready for C-A/operator run via previously authorized SSH, but not yet executed remotely.

Before any paid call: explicit PM budget cap, worker-only credentials, cost reservation/enforced hard cap beyond `MONITOR_ONLY`, missing Owner ledger safe initialization in **new A-only isolated candidate** with approval, robust Unknown-Billing no-repeat and Queue/Cost/Owner Provider reconciliation, Signed SSO+Actor ACL, source/build/runtime digest and rollback, actual Owner/PM profile signature, photo/license and human quality acceptance. No API key, token or payment authority should appear in C-A packet.

## 4. C-A replay command & adversarial focus

```bash
cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
PYTHONDONTWRITEBYTECODE=1 IT_TEM_LIVE_ENABLED=NO IT_TEM_LIVE_EXECUTION_APPROVED=NO IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO \
/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3 -B -m pytest -q -p no:cacheprovider -p no:warnings \
  tests/demo_live/test_a51b_signed_beta_contract.py \
  tests/demo_live/test_a51b_candidate_mask_gate.py \
  tests/demo_live/test_a51b_predeployment_tools.py
```

Independent audit should validate: detached signatures using role-separated pinned keys (not merely approval strings); tamper/expiry/trust-root/revocation, no auto-authorized paid flag; mixed old/v2/new and no migration; raw and rendered mask/protected pixels, candidate SHA context + no write on rejection; only true local asset formats, MPO multi-frame handling unresolved; GCP diagnostic NO DB mutation; all beta mandatory gates still HOLD. C-A should **not treat synthetic test signatures or image masks as actual Owner/legal acceptance**.

## 5. Strict beta release gate — no conditional GO

| Mandatory gate | Current |
|---|---|
| `SOURCE_AND_SECURITY_PASS` | DEV 1,199 Python PASS / C-A A51B differential pending |
| `PROFILE_V3_RUNTIME_PASS` | A5-1 local C-accepted; A51B signed contract developer offline PASS; operational authorization HOLD |
| `OWNER_INTEGRATION_PASS` | Existing A5-1 offline Chrome A/C C-accepted; real Provider/Worker untested |
| `REAL_PROVIDER_E2E_PASS` | 0/6, NO payment authority |
| `UI_UX_BETA_PASS` | actual deployed browser/SSO not audited |
| `VISUAL_QUALITY_BETA_PASS` | product/label masks & rights missing, 0 real commercial ads |
| `TEAM_UAT_READY` | No new isolated team beta URL/SSO/UAT, HOLD |

**`FULL_FEATURE_BETA_DELIVERY_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / COMMERCIAL_RELEASE_READY=NO`.**

**Next exact blockers to resolve:** real owner+PM signing identity/trusted public keys and valid final profile contract, explicit rights cleared source photo+MPO policy, annotated **generated** product/logo/label masks and human acceptance, isolated GCP A worker-off runtime + SSH inventory + rollback approval, missing Provider ledger safe path, PM-enforced hard cost cap and signed SSO. Work may continue in independent nonbillable branches without treating any of these as complete.
