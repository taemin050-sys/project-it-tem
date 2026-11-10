# IT-TEM P03 — A5-1B Signable Beta Contract / Real-Asset Mask / GCP A Preflight

**2026-11-10 KST | Developer implementation, C-A INDEPENDENT AUDIT PENDING**
**No real Owner/PM signature, no legal-rights approval, no GCP deployment, no paid Provider requests.**

## 1. Why this is a separate new beta contract

A5-1 A/C `OWNER_COMPOSED_4X5_V3_BETA_A|C` is C-A accepted as **OFFLINE_FIXTURE ONLY**. Do not remove that lock, repurpose its Profile ID or mutate old v2 Jobs, approvals, receipts or artifacts.

A5-1B adds **a distinct, future-authorizable signed-profile type** `OWNER_COMPOSED_4X5_V3_SIGNED_BETA_A|C`, version `owner-composed-4x5-v3-signed-beta1`; it reuses the reviewed A/C actual Owner typography, Korean font and CTA layout bytes, but binds those geometry bytes to an explicit epoch, actual Owner+PM public-key signature attestation and immutable per-Job snapshot.

This stage enables only new **OFFLINE_FIXTURE** Jobs under a trusted operator-controlled policy bundle. Signed layout activation **does not** enable LIVE, Provider calls, real-customer uploads or distribution. It never declares full-beta-ready. Old 6 modes (2 generation methods × 3 image ratios) and single candidate/image policy remain fixed.

### A5-1B implementation surfaces

- `demo_staging/live/a51b_signed_beta_contract.py`: real Ed25519 public-key verification via OpenSSL, distinct Owner/PM keys, pinned operator-issued public-key SHA and trusted nonrepository 0700 private directories; exact signed activation bytes; validity window; signed design/file/font SHA; revoke/change/read-time recheck; no private key in runtime or Git.
- `demo_staging/live/{store,template_contract,pipeline}.py`: new-Job signed Profile frozen in SQLite, externally renewed signature checked before Owner request and before final compose, exact layout and Font SHA; source-first Owner Image DTO retains A/C fields and legacy v2 unchanged. Existing 4:5 unsigned v3 remains gated.
- `demo_staging/live/a51b_candidate_mask_gate.py`: independent per-Job **detached Owner + PM signed** binary product/package/logo/label *candidate* mask review, candidate SHA, approval SHA, copy SHA, epoch/layout/Profile hash and 1080×1350 canvas binding. Mask cannot intersect any Head/Sub/CTA region. Fail-closed for altered signature, missing mask, malformed format, wrong SHA, text collision, or changed pixel under protected mask after actual Owner PNG composition. Entire review is checked **before** final PNG/Caption/Receipt atomic file writes.
- All mask and signoff data stay OUTSIDE Git and review ZIP. Receipt preserves only verified immutable SHA and a nonauthorizing mask report; **actual product identity, logo/label text, source similarity and legal rights are explicitly `NOT_AUDITED` and `HOLD`**.
- `scripts/a51b_local_product_cohort_audit.py`: read-only local photo inventory, precise product-name grouping, SHA/dimensions, duplicate detection; no raw image copied, no automatic multiframe canonicalization.
- `scripts/a51b_gcp_a_readonly_ledger_probe.py`: standalone GCP A **READ-ONLY** source SHA & three-DB-kind inventory, uses SQLite `mode=ro` and `PRAGMA query_only=ON`, never initializes/migrates a DB or starts Worker. Not yet run remotely on GCP A in this development session.

## 2. Real approval operator input required

The only allowed formal signing process is via separately authenticated actual Owner and PM identities; this development task has **not** obtained or produced those signatures.

The trusted operator must separately provide two pinned public-key SHA-256 references and non-Git external private directories with 0700 permissions:

`IT_TEM_A51B_POLICY_ROOT` and `IT_TEM_A51B_TRUST_ROOT`, and `IT_TEM_A51B_IMAGE_OWNER_PUB_SHA`, `IT_TEM_A51B_PM_PUB_SHA`. Trust root contains `image_owner.pub.pem` and `pm.pub.pem`, owned by the authorized operator, not downloadable data. Both must be distinct keys. No signing private key is supplied to the server. Profile bundle contains `activation.json` and `image_owner.sig` / `pm.sig` detached Ed25519 signatures over **exact same bytes**. All files mode 0600, and both dirs mode 0700. Source files and keys are never committed.

`activation.json` required fields: `contract=IT_TEM_P03_A51B_PROFILE_ACTIVATION_V1`, `decision_id`, `profile_choice=A|C`, `policy_epoch`, `profile_sha256` (= canonical A/C developer design fingerprint), pinned Pretendard Font SHA, pinned license-text SHA, UTC valid-from/expires (≤90 days), `deployment_scope=GCP_A_ISOLATED_BETA_ONLY`. Decision must be **really signed** by both authorized principals. No dummy approval data may be used outside the isolated negative tests.

To exercise **only offline signed-profile integration** after formal identities have been verified, operators explicitly enable `IT_TEM_A51B_NEW_JOB_ENABLE=YES` and `IT_TEM_A51B_PROFILE=A|C` in a process with `IT_TEM_LIVE_ENABLED=NO`. The role signing files are independently verified and bound into the newly frozen Job. A signature alone never enables the paid worker.

## 3. Candidate mask and product/label protection

For every accepted Image Attempt, operator-private `IT_TEM_A51B_MASK_REVIEW_ROOT` contains a distinct `{job_id}.maskreview.json`, `{job_id}.protected_mask.png` (exact 1080×1350 single-channel L-mode binary 0/255), `{job_id}.image_owner.sig` and `{job_id}.pm.sig`, all mode 0600. The signed review must contain exact Job ID, existing Copy+Approval+raw image SHA, frozen layout SHA, epoch, signed Profile decision SHA, mask SHA and declared scope.

Signing the mask record authorizes at most **the candidate mask's geometry review**, never a legal title, identity restoration, brand-claim accuracy, or paid external transfer. The current policy deliberately accepts `LOCAL_READ_ONLY_PRODUCT_QA_ONLY` or `RIGHTS_DECLARED_PENDING_INDEPENDENT_LEGAL_REVIEW` only and sets `real_provider_transfer_authorized=false` in Receipt. No result can be interpreted as `VISUAL_QUALITY_BETA_PASS` without humans examining product/label text, color, form, brand and claim fidelity.

This is a **two-stage proof**: separate profile signatures at new Job creation, then separate per-image signed mask + SHA and pixel preservation at final compose. Existing v2/v3 snapshots and historic assets remain byte-identical.

## 4. Provided local product-photo folder (read-only results)

User source: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/잘나온 화장품 모음`. Original **24 photo files** in **10 filename-derived product groups**, **1 exact byte-duplicate pair**, **no corrupt decoded file**. Unexpected actual container type: **9 ordinary JPEG**, **15 MPO with two frames each** although named `.jpg/.JPG`. This is a compatibility gate, not a finding of corruption. Do **not** auto-pick MPO frame 0, re-encode, send to Provider or silently strip embedded images/metadata. Image Owner must approve an explicit frame selection and canonicalization/provenance SHA policy for any eventual external use.

Every group has at least 2 unique file bytes, allowing **2–5 same-name local QA candidates**. Filename grouping is not evidence of identical physical product, brand-license ownership, image-transfer permission or original label accuracy. All 24 photos stay in their user-supplied folder, untouched. Only sanitized SHA/dimension/product-filename metadata is included at `docs/integration/evidence/A51B_20261110/LOCAL_PRODUCT_METADATA_ONLY.json`.

For immediate local read-only comparisons requiring no MPO transcoding, use individual 2-photo groups with JPEG containers (Gatsby spray, Mediheal sheet mask, OBgE sunstick, Physiogel lotion) **subject to visual same-product verification**. Do not combine separate groups in one Job. Rights certificates not found, thus **all real Provider uploads and team beta distribution remain HOLD**.

## 5. GCP A read-only ledger scope

The C-A51 independent auditor's known observation is valid and should not be superseded by guesses: GCP A source `9879eb0f85747312a224ecd898aaff84d834590b` remains old; `runtime/live/live.sqlite:live_image_attempts` app image ledger **8 COMPLETED**, Queue `queue.sqlite:queued_ops` **0**, Cost `cost.sqlite:attempts` **0**, separate Owner Provider `runtime/live/owner_image/image_attempts.sqlite` **missing** at C-A observation time. **Missing Owner Provider ledger is not equivalent to missing app image ledger.**

`a51b_gcp_a_readonly_ledger_probe.py` must be executed using authorized pre-existing SSH on A with:

`python3 scripts/a51b_gcp_a_readonly_ledger_probe.py --root /home/macstudio/ittem-e2e-baseline-20261107`

Copying/authorizing the diagnostic itself on remote may require operator approval; no remote execution was attempted in this developer turn. Source SHA must be compared only after actual live read. Do not create a missing owner directory/DB under protected A, or imply `Queue 0 / Cost 0` proves billing reconciliation.

Owner paid workflow additionally requires separate **hard USD spend cap** beyond existing monitoring-only, worker-only secrets, predispatch budget reservation, `BILLING_UNKNOWN` no retry, Provider Attempt/Usage/Receipt and Queue/Cost reconciliation, idempotent operation keys and rollbacks. **No money-bound Worker enabled**.

## 6. Test evidence vs beta mandatory gates

All unit signers are ephemeral OpenSSL **TEST KEYS** generated under pytest private temporary folders. They are destroyed with test fixtures; no real Owner/PM signature is fabricated or saved.

Targeted validations:
- Signed activation: dual authentic Test Key signatures, SHA, expiry, revocation, missing roles, wrong profile/font and LIVE activation negatives.
- Candidate mask: absent review/permissions/wrong Job/candidate/copy/approval/epoch, altered PNG/bytes, text collision/changed protected pixels, final file Fail-Closed; one full OFFLINE_FIXTURE signed-profile→actual Owner composited PNG→receipt PASS.
- Photo cohort: 24/10/1, 9 JPEG+15 two-frame MPO, no raw photo export.
- GCP three-ledger: disposable app 8/queue 0/cost 0/owner missing all read-only, zero DB creation or mutation.

**Developer-ready is not beta team-ready.** Current mandatory gate statuses:
`SOURCE_AND_SECURITY_PASS=C_A_A51B_PENDING`; `PROFILE_V3_RUNTIME_PASS=SIGNED_BETA_OFFLINE_DEV_ONLY`; `OWNER_INTEGRATION_PASS=OLD_A51_FIXTURE_ACCEPTED_NEW_BETA_MASK_DIFFERENTIAL_PENDING`; `REAL_PROVIDER_E2E_PASS=NOT_AUDITED`; `UI_UX_BETA_PASS=NOT_AUDITED`; `VISUAL_QUALITY_BETA_PASS=NOT_AUDITED`; `TEAM_UAT_READY=HOLD`; `COMMERCIAL_RELEASE_READY=NO`.

**Operating principle:** preserve C-A accepted A5-1 Local/Browser; investigate only A5-1B new risks. Deployment, legal rights, signed SS0, approved hard budget and human product quality require authentic PM/Owner authorization. Until then `GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / FULL_FEATURE_BETA_DELIVERY_HOLD`.
