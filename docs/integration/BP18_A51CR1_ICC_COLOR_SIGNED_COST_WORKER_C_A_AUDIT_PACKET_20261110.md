# IT-TEM P03 Track A — A5-1C-R1 ICC Color Repair + Signed PM Hard-Cap Web/Worker Branch

**Date:** 2026-11-10 (Asia/Seoul). **Submission:** differential C-A audit requested.
**Baseline C-A accepted:** HEAD `4daf7afb8c9b174be4be533e340ebbcd24744bcc`, Tree `4ed9881b84fcb3681eeba68a772d5270d7050e29`.
**Baseline C-A verdict:** `C_A51C_ISOLATED_COMPONENTS_ACCEPTED_WITH_P2_NOTE`; ICC finding `A51C_P2_01_REPAIR_BEFORE_FE_ACTIVATION`.
**Implementation HEAD:** `c6c7c29d518417bb6d66313d8ce98373cf940890`, Tree `523ea9460ea281e3356c8f285b3e0e0de52ebd72`.
The following documentation/evidence-only commit does **not** change tested executable code.

## 1. R1 — ICC color management repair (2-file bounded diff)

Commit `0b69f6a3dc3c5d3b5d4831bef95b6e8a127259f8`. Changed only:

- `demo_staging/live/a51c_explicit_mpo_ingress.py`
- `tests/demo_live/test_a51c_explicit_mpo_ingress.py`

`_to_srgb_upright` now performs one versioned EXIF-upright + embedded ICC→sRGB transform, with no ICC source profile using explicit RGB assumption. **Both** `inspect_source` / `preview_frame` PNG and `normalize_selected_source` JPEG use exactly that canonical path before resampling/encoding. Color contract `EXIF_UPRIGHT_ICC_TO_SRGB_V2` and original ICC SHA, selected-frame RGB SHA, sRGB-upright SHA, preview PNG SHA and normalized JPEG SHA are separately bound in provenance. Invalid ICC fails closed at Preview/Export.

Reproduction on Mac uses **installed system ColorSync AdobeRGB1998 and Display P3 profiles** for two independently selected synthetic MPO frames, including ICC SHA, RGB comparison (max channel delta ≤3), wrong/fake ICC rejection, EXIF rotation and metadata stripping. No ICC binary copied to Git or ZIP. The accepted original v2 Image Owner MPO processor is unchanged. Selection UI/Owner Beta ingress has NOT been activated.

## 2. A5-1C Worker — signed PM Hard Cap beta branch (4-file additive/opt-in diff)

Commit `c6c7c29d518417bb6d66313d8ce98373cf940890`. Changed only:

- `demo_staging/live/a51c_signed_cost_authority.py` (new)
- `demo_staging/live/http_api.py` (A-only optional signed queue authorization)
- `demo_staging/live/worker.py` (A-only optional signed Worker authorization and model adapter cap)
- `tests/demo_live/test_a51c_signed_cost_runtime.py` (new)

`IT_TEM_A51C_HARD_CAP_ENABLE=YES` selects a new explicit signed-policy path. **Default remains OFF**; legacy monitoring behavior stays scoped to the previously accepted branch. The new path requires:

1. Ed25519 **PM financial approval signature** (separate from the Image Owner+PM design signatures), authentic externally pinned PM public-key SHA, sealed private policy/trust dirs, exact canonical signed approval bytes.
2. Signed `source_commit`, `candidate_runtime_root`, `GCP_A_ISOLATED_BETA_ONLY` scope, strict UTC 30-day validity, policy epoch, Actor allowlist, max total request count, exact six-decimal USD budget and positive text/image per-attempt reservation bounds.
3. Signed Tailscale SSO configuration and no legacy invite-cookie fallback for beta; web Queue and Worker independently revalidate signed financial policy. A source SHA declared solely by environment is NOT proof of actually deployed binary: C-A must independently attest Git/Build/Runtime SHA.
4. **Read-only schema preflight of existing candidate-only** `live/live.sqlite`, `live/queue.sqlite`, `live/cost.sqlite`, `live/owner_image/image_attempts.sqlite`. Missing/uncertain Cost/Queue/Owner Attempt = hard denial; no silent Provider DB initialization or historical GCP data migration.
5. Worker `LivePipeline` uses `monitoring_only=False`, signed `budget_usd`, `max_requests`, `text_reservation_usd` and `image_reservation_usd`. The Owner Image Adapter uses the same signed cap/reservation and native ProviderAttemptStore; *not* the prior monitor-only zero reservation.
6. At last-mile dispatch, checks Authenticated Actor/Job + signed budget/ledger, rejects unsigned/legacy image Job and **rejects A5-1B signed Typography-only Profile with `real_provider_permitted=false` or `rights_review_verified=false`**, as all existing A51B profiles are. A forged DB row with booleans True must pass a fresh actual Owner+PM Ed25519 profile verification and currently fails without valid independently pinned authority.

**No actual PM financial signature, signed product rights or signed runtime beta deployment exists in this development session.** All crypto tests use temporary test-only Ed25519 keys and synthetic photos; no actual customer media or Provider credentials are accessed.

### Financial caveat

An internally reserved budget is NOT automatically a guarantee of actual external provider invoice spend. A true live **monetary Hard Cap** still needs model-price maximum, external account spending limits, reliable Provider Usage/Receipt, 3-way Queue/Cost/Owner Attempt reconciliation and C-A audit. Billing-unknown must remain terminal pending human reconciliation; no automatic retry. **This code is a tested optional protection branch, NOT a cleared real-paid release.**

## 3. Differential verification

| Test / evidence | Developer result |
|---|---|
| Existing C-A ICC reproduction + Adobe RGB/Display P3 actual profiles | PASS; max corresponding pixel channel delta ≤3 |
| ICC, selected frame, preview/JPEG SHA, EXIF and invalid ICC | PASS |
| Signed PM budget/Actor/source/scope/SSO and missing/unknown Owner ledger negative tests | PASS |
| Real Worker authorization refuses unapproved legacy/profile and re-verifies PM signature | PASS |
| A5-1C Worker/PM one candidate + legacy compatibility focused regressions | 79/79 PASS after scope adjustment |
| Final FULL Python after both code commits | **1,270/1,270 PASS** |
| React official code | 57/57 PASS |
| ESLint / Vite OFFLINE_FIXTURE build | PASS / PASS |
| Pinned final frontend JS bundle SHA | `38a64b31d4015a44bd0b61fc37d1295dc747cc2d73cb3bbde324752ecdafdc10` |
| Pinned final index.html SHA | `6c316af5049408f7ee19143847ef515f2e42c56dc5edae2f185e72abdf62a1ce` |
| Latest actual GCP A deployment, paid Provider, signed Owner/PM record | NOT PERFORMED / 0 / 0 |

Code diffs to review (nothing from previously accepted A2–A5 repeated):
`git diff 4daf7afb8c9b174be4be533e340ebbcd24744bcc..0b69f6a3 -- demo_staging/live/a51c_explicit_mpo_ingress.py tests/demo_live/test_a51c_explicit_mpo_ingress.py`
`git diff 0b69f6a3..c6c7c29d -- demo_staging/live/a51c_signed_cost_authority.py demo_staging/live/http_api.py demo_staging/live/worker.py tests/demo_live/test_a51c_signed_cost_runtime.py`

Evidence: `docs/integration/evidence/A51CR1_20261110/` and `A51CR1_SHA256_MANIFEST.txt`; every included file hashed. **C-A independent review still PENDING.**

## 4. Owner/PM decisions and strict beta boundaries

- **MPO:** Image Owner 박지수 + Frontend Owner #26 + PM 이태민 choose `REJECT_MULTIFRAME` or `PREVIEW_AND_EXPLICIT_SELECT`. For second choice, authorize Beta Controller actor-bound Preview/selection receipts, image source/EXIF/ICC→sRGB version 2 provenance, anti-replay and normalizing upload into new Job. At present there is NO signed Owner/PM MPO policy and NO official FE/B0 activation; old v2 unchanged. The confirmation string alone is not human evidence.
- **Images/visual:** local 24 cosmetic photos unchanged, commercial rights not verified. Obtain 2–5 rights-cleared same SKU images, actual product/package/logo/label masks and human advertisement quality acceptance. No local product media are committed, copied to audit packet or sent to Provider.
- **Infra/finance:** separate PM authorization for strictly A-only candidate GCP deployment, signed SSO/Actor, WAL-consistent backups and Rollback; approve actual PM finance record, dedicated credential, real provider ledger migration and pricing. Last independent GCP A SHA `9879eb0f85747312a224ecd898aaff84d834590b`; app image attempts 8 completed, Queue 0, Cost 0, Owner Provider Attempt DB missing. No GCP write or provider invocation in A51C-R1.
- **Beta completeness:** 2 generation modes × 3 ratios = **6 separate one-candidate requests**; A/C are internal composed 4:5 layouts, no batch/gallery. `REAL_PROVIDER_E2E=0/6`. A5-1B signed Typography-only profile still denies paid runtime and remains pending product authorization. Actual team URL, SSO, full UAT and 7 release gates not achieved.

**Requested C-A verdicts independently:** `A51CR1_ICC_REPAIR` and `A51C_SIGNED_HARD_CAP_WEB_WORKER_GUARD`; do not mistake technical acceptance for authorization.

**Current release gates:** `SAFE_NONBILLABLE_DEVELOPMENT_GO`, `A51C_R1_DEVELOPER_VERIFIED`, `C_A_DIFFERENTIAL_PENDING`, `OWNER_FE_MPO_CONTRACT_PENDING`, `GCP_A_QA_DEPLOYMENT_HOLD`, `A_GCP_PAID_WORKER_HOLD`, `FULL_FEATURE_BETA_DELIVERY_HOLD`, `COMMERCIAL_RELEASE_READY=NO`.
