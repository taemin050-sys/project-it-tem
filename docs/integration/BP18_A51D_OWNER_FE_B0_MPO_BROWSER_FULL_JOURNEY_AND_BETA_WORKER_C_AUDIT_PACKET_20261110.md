# IT-TEM P03 — Track A A5-1D: Owner React → Authenticated MPO → B0 Job → Copy/Image/Final PNG E2E

**2026-11-10 KST. Differential developer submission for independent C-A audit.**

## 0. Authority, version and strict classification

- **Previous independently accepted baseline:** Track A `0a0b35f5d596cc8d41d035c9cc05e1d0ee81c555`, tree `35a744e2b4356a521ea692a91dbec60eddc772cb`. C-A51C-R1 report `IT_TEM_P03_C_A51CR1_ICC_SIGNED_COST_WORKER_DIFFERENTIAL_INDEPENDENT_AUDIT_20261110.md` SHA256 `b086d74e86d761162db62d42fb6497a255c8f83956d4f6b6a82940850f8beb7a`.
- **A51D integration code commit:** `2c13e31277fcc501d904a8d6069f119414cf091a`, tree `20842c0b6573e2f7328570c364140313b5b9b9b2` (14 path-scoped files).
- **A51D final tested executable code commit:** `67db6d8109efb88f172afc1eac7f01f687d7da26`, tree `691bf5d24680f89227a1f2582ebd0ab9f6b558ed` (one additional fixture-only raw-JPEG safety change).
- **Current scope:** actual owner React + FastAPI B0 + existing QA Text/Image/Compositor inside one **localhost-only OFFLINE_FIXTURE** Job. Genuine Chrome clicks and SHA-bound PNG/Caption downloads; no real AI or actual customer/brand photo.
- **Prohibited promotion:** This is **NOT** Image Owner/PM-approved MPO input policy, production-ready multi-worker token ledger, signed beta Profile, commercial product-rights QA, GCP latest deployment, actual Provider billing, real-model six-job E2E or team UAT acceptance.
- Immutable PM product policy protected: Freeform/Composed, 3:4/4:5/9:16, exactly 1 image candidate per Job, explicit regenerate, FE #26 > Text #27 > Image #24. A/C are Composed 4:5 typography candidates only, not 2 more image modes.

## 1. A51D officially rendered React integration — source and proven flow

**Diff limited to new A51D test-only paths plus minimal feature-flag branching**: `app/src/{components/PhotoDrop.tsx,api/jobs.ts,lib/mpo.ts,lib/shrinkImage.ts,lib/a51dMpoSelection.ts}`, `app/tests/a51dMpo.test.ts`, `demo_staging/app.py`, `demo_staging/live/a51d_mpo_fixture_bridge.py`, `tests/demo_live/test_a51d_mpo_http_fixture_bridge.py`, Chrome runner and script. The existing Owner Image rendering, Serving B0 routers, v2 JobStore, signed A/C compositor and existing historical v2 records remain unchanged.

1. **Real hidden MPO**: The fixture creates a *synthetic 2-frame actual MPO* named `hidden-mpo.jpg` alongside another separately generated synthetic PNG representing a second same-product angle. Browser detects MPO binary MPF marker despite `.jpg` extension. **No frame 0 fallback.**
2. **Authenticated Preview**: `POST /demo/api/a51d/mpo/preview` under existing Demo signed/origin/session middleware returns two distinct source-frame preview PNGs and SHA, plus cryptographically random scoped token. Only the actor who requested Preview can use the token.
3. **Explicit selection action**: Official React renders both previews; frame #2 selected, then explicit user click. Separate authenticated `POST /demo/api/a51d/mpo/confirm` CAS records frame index and preview SHA once; incorrect/missing/repeated/tampered/foreign Actor confirms fail closed. This proves an authenticated browser action was observed, **not that a person legally approved use of the photo or genuinely visually inspected it**.
4. **Authenticated Job commit**: `POST /demo/api/a51d/mpo/jobs` checks original raw SHA, selected Preview index/SHA and confirmed Actor token; consumes token before writing; converts only chosen frame through the independently accepted `EXIF_UPRIGHT_ICC_TO_SRGB_V2` normalizer. It feeds `ValidatedUpload` into the *real existing* B0 `JobStore.create_job` and commits DemoLedger Actor ownership before returning the ID. Other plain photos are validated by the existing B0 validation. No duplicate candidate/batch/gallery.
5. **Product source Provenance**: raw original SHA, frame count/index, Preview PNG SHA, original ICC SHA, canonical upright sRGB SHA, resulting JPEG SHA, Actor-scoped upload-request digest, transform contract stored on the new asset record. Actual raw MPO bytes are not stored in Job asset directory, only chosen normalized JPEG.
6. **Product workflow**: same selected Job reaches the existing isolated QA analysis/research/copy/F09 and real React Copy review; explicit copy approval → single image candidate version 1 → Image approve → composed 1080×1350 PNG + Caption. **All synthetic OFFLINE_FIXTURE**, no real Provider.
7. **Receipt and download**: actual Chrome PNG SHA `95b9414d6eac81ef4352ae28a9d30ef41c1af1a0caf50bd492624bc288b34d62`, Caption SHA `a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839`. Both match the authoritative Completed Job SHA and downloaded exact bytes. Real 1440, 390, 360 browser screenshots (no mobile horizontal overflow observed), refresh GET-only, second unauthenticated context 401. Python FastAPI separately checks other Actor 404.
8. **Prevent browser-silent transcode**: final safety commit keeps unidentified JPG/JPEG **unmodified** in fixture mode even if early MPF signature scan misses a late APP2 marker; the B0 MIME/container verifier then rejects actual MPO-as-JPG before any implicit first-frame JPEG transcoding. Existing v2 resizing is unchanged with fixture flag OFF.

**Default flag OFF.** New routes require `IT_TEM_A51D_MPO_FIXTURE_BRIDGE=YES`, `IT_TEM_A51D_NONDEPLOYABLE_TEST_ONLY=YES`, QA enabled, Mac localhost test root, `secure_cookie=False`, Live/Paid/HardCap/Tailscale all disabled. Real signed Tailnet or real paid runtime **cannot install test-only routes**. JS fixture selection UI additionally requires `VITE_A51D_MPO_FIXTURE_BRIDGE=YES`. In actual team beta these exact fixture-only routes **must not be enabled**.

## 2. Hard Cap deployment bypass prevention

A new optional deployment indicator `IT_TEM_A51D_SIGNED_BETA_RUNTIME=YES` adds a **fail-closed startup, web Queue and last-mile Worker guard**:
- Requires `IT_TEM_A51C_HARD_CAP_ENABLE=YES`, `IT_TEM_LIVE_COST_POLICY=HARD_CAP`, Signed Tailscale SSO config at server creation. Inconsistent/missing values reject; never fall back to legacy `MONITOR_ONLY`.
- Uses C-A-accepted earlier A51C signed PM financial decision, pre-existing non-uncertain Owner Provider/Cost/Queue ledgers, Actor Job ACL and A51B actual separately signed product rights/Mask/Profile flags. A cost signature alone does not permit an Image/Provider request.
- Added tests deny wrong policy/marker combinations, SSO missing, PM cost record absent and legacy fallback while preserving old v2 path with marker OFF.
- **Important limit:** The Beta marker itself must be locked by an independently reviewed release/runtime attestation and non-modifiable operator process configuration; an operator editing deployment env can remove the marker. This is not an external account spend ceiling. Real Provider maximum price, Usage/Receipt and invoice reconciliation remain **NOT AUDITED**. No current GCP configuration has this marker activated.

## 3. Fixed-code technical evidence (not C-A acceptance)

| Check | Developer result |
|---|---|
| Fixed-code Python all regressions | **1296/1296 PASS** |
| Official React Node test suite | **59/59 PASS** |
| ESLint / Vite build fixed code label | PASS / PASS |
| Formal official React real Chrome fixture Job | **15 steps PASS**, 6 screenshots |
| Explicit HTTP requests | Preview 200 → confirmed selection 200 → B0 Job 201 |
| B0 ownership / provenance | PASS; unauthorized 401, cross Actor 404 |
| Selected frame output / receipt / browser downloaded SHA | PASS, 1 candidate, 1080×1350 |
| Desktop/390/360 mobile screenshots | PASS; no horizontal overflow |
| External requests / actual Provider calls | **0 / 0** |
| Final code | `67db6d8109efb88f172afc1eac7f01f687d7da26` |
| Frontend JS SHA-256 | `3da343e51a88b912079c3a0fb2546076de5795de33e51eb68a32aa88e6ed2d29` |
| Frontend index.html SHA-256 | `60a2bd70f551463f1cd686b7264ad4357f11c3dbc7d9668b8da776b3cec44e71` |

Reproduce with the in-repo `tests/product_e2e/run_a51d_mpo_react_chrome_fixture.sh` on Mac Studio with `A41_PYTHON`, `A41_PLAYWRIGHT_CORE_MODULE`, `A41_FONT` set to previously accepted local install paths and `A51D_PORT=18547`. Rejects paid provider env vars, bound ports and remote hosts; creates disposable `/private/tmp/ittem-a41-a51d-*` and stops only its own uvicorn. Artifacts are **synthetic** and safe to copy into the evidence path. Manifest `docs/integration/evidence/A51D_20261110/A51D_SHA256_MANIFEST.txt` attests all copied logs/screenshots/downloads with no credential, private token, real customer photos or font binary.

## 4. Owner first and remaining true beta critical path

**Workstream A (MPO)**: Image Owner 박지수, FE Owner #26 and PM 이태민 still must sign or formally record **REJECT_MULTIFRAME** vs **PREVIEW_AND_EXPLICIT_SELECT**, adopt exact Canonical Contract/DTO/version and safe failed/reloaded request behavior. For actual signed SSO Beta, replace fixture-memory pending tokens with independently reviewed durable Actor-bound anti-replay CAS receipts, validate actual product usage rights and forbid all old v2 first-frame shortcuts on newly signed beta jobs. This implementation is evidence of feasibility, not a human policy decision.

**Workstream B (product/visual)**: the local 24 cosmetic inputs remain legally unverified; no user photos used in this E2E. Obtain 2–5 licensed images of same SKU, independently validated masks of product/package/logo/label, Korean Typography and Owner+PM real advertisement acceptance. A/C signed Beta Product Mask/rights flags remain false.

**Workstream C (paid)**: PM actual Ed25519 signed hard spend limit and account owner, model-price maximum, valid provider key storage, Owner Provider Attempt/Cost/Queue/Usage/Receipt **atomic reconciliation** and `BILLING_UNKNOWN` no auto-retry. Enforce hard cap in true worker from pinned config AND external account. The current approved GCP A reported image app attempts 8 COMPLETED, Queue 0, Cost 0, separate Owner Provider Attempt DB missing. **No DB was initialized or migrated** here.

**Workstream D (GCP/UAT)**: GCP A latest Source/Tree/Build/Runtime SHA, Signed SSO, Actor/Job, WAL-consistent backup/rollback, separate beta hostname and deployment **require separate PM permission**. Last C-A observed A runtime `9879eb0f85747312a224ecd898aaff84d834590b`; A5-1D never deployed. Six real-model one-candidate Jobs `Freeform|Composed × 3 ratios` remain **0/6**. Final 7 beta gates all still need full connected evidence.

## 5. Explicit C-A differential audit requests

Audit only new changes since accepted `0a0b35f...`: exact FE binary-MPO detection+user-frame-CAS flow, test-only route installation barriers, authenticated B0 ownership, raw/selected/normalized SHA consistency, retry/replay Actor isolation, v2 source unaffected, hardcap marker NO-MONITOR_ONLY bypass, true synthetic Chrome PNG/Caption, submitted code/JS hashes. Avoid repeating accepted A2–A5-1C-R1 tests without risk impact. Check whether in-memory preview tokens and test-only flags remain unreachable on any real deployment; **do not promote their use to production**.

**Status:** `A51D_DEVELOPER_INTEGRATION_FIXTURE_PASS / A51D_C_A_DIFFERENTIAL_PENDING / MPO_OWNER_PM_POLICY_PENDING / REAL_PRODUCT_RIGHTS_PENDING / GCP_A_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / REAL_PROVIDER_E2E_0_OF_6 / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO`.

No GitHub official Owner/dev PR edit, Track B edit, GCP write, Provider call, invoice authorization, real customer upload or signed Owner/PM approval was performed.
