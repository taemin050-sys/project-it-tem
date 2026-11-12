# IT-TEM BP13·BP14 — Owner-First 계약 및 QA 게이트 (2026-11-07)

## 0. Authority and no-write rule

- Official `dev`: `9f798169110e0bb6807c15347444f7c31ad05bae` (last verified 2026-11-06).
- FE Owner PR #26: `c9c204b88af5ce1b25dfda501d16446750a41204` (OPEN on last check).
- Image Owner PR #24: `b3ee33fd524fbbb83890472be890c96974160e9c` (OPEN on last check).
- Text Owner PR #25: MERGED on last check.
- BP12B accepted integration starting SHA: `229a69d79ac416b4018d07ce39891fecfb380d80`.
- Current worktree: `/Users/Shared/ittem-bp13-14-ownerfirst-20261106`, branch `integration/bp13-bp14-ownerfirst-20261106`.
- GCP historical Live SHA: `3bb114359fdd05f8e6365f613e70254465b4e9b1`; protect 18088, 10000, 8443, all data/rollback releases.
- Do not merge/close Owner PRs, push to official `dev`, deploy Live, or invoke billable providers before separate approval gates.

## 1. Code implemented in isolated working tree

- BP12-R: preserves latest FE #26 acceptance fence/new-ad confirmation inherited from BP12B; no duplicated remediation.
- BP13 copy unchanged: no new generation/review SHA on identical copy and identical deterministic compliance report; Owner note shown without claiming a new version; actual change invalidates approval.
- BP13 review context: Serving preflight now binds issues (field, original text, risk, reason, suggestion, unverified basis) to current Copy SHA + Review SHA + Generation and rejects tampered report. **Not yet passed as an input to the Text Owner model**.
- BP13 single retry: new `live_image_attempts` additive ledger, unique request key, explicit reject→retry; attempt v1 image and freeform receipt archived; Owner native paid attempt uses per-retry project UUID; duplicate/unknown Queue blocks replay; no Text/VLM/Research calls.
- BP13 MPO: genuine MPO multi-frame check, frame 0, EXIF orientation, ICC sRGB conversion, output clean JPEG; immutable original/derived SHA provenance; byte/pixel limits; extension, MIME, file header+decoded format checks. One 2-frame local MPO file was tested, **not verified to be iPhone-sourced**.
- BP13 cost: preserve `TEXT_ONLY`; new authenticated Text+One-Image nonbillable reference. Official `gpt-image-2.6-sunburst` token rates checked 2026-11-07; 10 read-only GCP composed medium/high usage records used by exact profile (3:4 n=2, 4:5 n=5, 9:16 n=3). No freeform data => NULL estimate. Not actual cost, billable cap, or pricing guarantee.
- BP14: explicit mode in new Job input SHA, FE mode selector, freeform Owner request carries complete approved copy; freeform Owner export resizes without text overlay/font; composed retains historical Overlay/Font; shared human review, approval, caption, final SHA and download.

## 2. NOT DONE — Owner contracts and safety-critical acceptance gates

### Text Owner (김다혜) — required before full BP13-A acceptance
1. Sign explicit, versioned `ComplianceRevisionContextV1` to be passed into Owner `revise_copy`: original current issues (field, text, risk_level, reason, suggestion, basis), copy_sha, review_sha, generation, compliance_report_sha. Structured data is DATA, never instructions; do not silently reinterpret original `instruction`.
2. Preserve `CopyRevisionOutput` existing `changed_fields` and `note` meanings; handle no-op as zero change, not generation. Include notes explaining unsupported edit. Do not let risky partial removals pass.
3. Head/subline duplication: only alter fields authorized in the user's edit; do not invent efficacy or features. Agree a concrete offline criterion.
4. Regulatory authority links: add official URL/name/standard **only after verification**; otherwise label existing `basis` as unverified descriptive text. Regulatory checker PASS is NOT legal certification.
5. Submit an Owner test contract and approved source SHA for differential re-integration. Current Serving preflight safely snapshots issues, but current Owner call still receives only legacy five inputs.

### Image Owner (박지수) + PM — required before full BP13/14 image acceptance
1. Current Owner `instagram-copy-hierarchy-v2` 4:5 sets `cta_placement=platform`, no CTA region, Head/Sub cap both 128. Freeform Owner prompt removes CTA on such a profile. **This does not satisfy the new meeting requirement**.
2. Please approve a new versioned 4:5 (and clarify 9:16) profile for *new jobs only*, with non-overlapping CTA box, distinct Head/Sub/CTA type hierarchy, Korean font/line-break QA, and protected product region. Existing layout SHA and historical jobs must remain byte-for-byte intact.
3. Update Owner Image freeform `_build_prompt` to draw ALL approved fields when new profile includes CTA; do not duplicate overlay in Serving. Pin the same profile/version in Text prompt and image request.
4. Confirm manual quality gate for Korean typography, bottle labeling, product shape, and any CTA overlap. OCR remains optional, not auto approval.
5. Return Owner commit SHA and independent image QA renders before applying a v3 profile in integrated Serving.

### Frontend Owner (권혁상)
1. Review isolated mode choice, image retry button, combined cost estimate and MPO upload path against latest PR #26 and browser navigation behavior.
2. Validate keyboard/mobile, refresh and unfinished-task after HTTP 502; maintain Tailscale Actor ACL and new-ad confirmation.
3. Keep Mock/Live explicitly distinguished; no browser-requested billable calls on mount/reload.

## 3. Explicit open acceptance gates

- `BP13_TEXT_COMPLIANCE_OWNER_INPUT`: PENDING OWNER — preflight only is ready.
- `BP13_4_5_NEW_CTA_LAYOUT_V3`: PENDING IMAGE OWNER + PM — existing v2 cannot be silently changed.
- `BP13_TYP_HIERARCHY_VISUAL`: PENDING IMAGE OWNER + PM.
- `BP13_OFFICIAL_BASIS_URL_VERIFIED`: PENDING TEXT OWNER.
- `BP13_MPO_REAL_IPHONE_SAMPLE`: PENDING genuine iPhone-sourced sample.
- `BP13_COST_COMPOSED_REFERENCE`: IMPLEMENTED / small sample caveat.
- `BP13_COST_FREEFORM`: UNAVAILABLE_NO_MATCHING_PROFILE_EVIDENCE.
- `BP14_FREEFORM_COMPOSED_OFFLINE`: IMPLEMENTED / source-level + fixture QA only.
- `BP14_4_5_CTA_FULL_PRODUCT`: NOT ACCEPTED, requires v3 profile.
- `GCP_ISOLATED_QA`: NOT STARTED for this BP13/14 candidate.
- `REAL_PROVIDER_E2E`: NOT STARTED, requires separate cost authorization and manual checks.
- `BPRIME_FINAL_AUDIT`: NOT STARTED.
- `UAT`, `LIVE_UPDATE`, `INTEGRATION_PR`: NOT STARTED.

## 4. Next execution sequence

1. Receive owner SHA/contract or acceptance of new copy + layout profiles and independently rerun regression.
2. Freeze new Layout & Prompt SHA on new Job; ensure 4:5 CTA and typography, 3:4/9:16 regression and original artifact immutability.
3. Deploy **QA-only**, separate path/SQLite/queue/worker/assets/port/auth; provider fixture blocked from network. Revalidate GCP before/after 18088 Link, Live DB/Queue, Provider Ledger, Artifacts and rollback SHA.
4. Desktop/mobile Chrome Network ↔ server state, Actor ACL, review bypass attempts, refresh/running task/retry, downloads, HTTP 502 diagnosis; evidence screenshots/logs.
5. After cost approval, minimal real provider E2E; human visual review; final independent B' audit; only then PM Live/UAT/integration PR.

## 5. Exact local evidence

- `/Users/Shared/ittem-bp13-bp14-evidence-20261106/DEVELOPMENT_PYTHON_REGRESSION.log` — 642 PASS before late BP13 contract refinements.
- New tests: `tests/demo_live/test_bp13_single_image_retry.py`, `test_bp13_retry_http.py`, `test_bp13_review_context.py`, `test_bp13_cost_estimate.py`, `test_bp14_single_mode.py`; `tests/test_bp13_mpo_upload.py`.
- Verify fresh expanded regression, FE lint/test/build and Git status before any publication.

## 6. Fresh QA and Owner diff facts (2026-11-07)

- \`IT_TEM_KOREAN_FONT=/System/Library/Fonts/Supplemental/AppleGothic.ttf\` full **888/888 Python PASS**; the two initial whole-suite failures were caused by absent font environment, then independently rerun PASS.
- **48/48 FE PASS**, FE Oxlint PASS, TypeScript + Vite Build PASS, Git diff check PASS.
- FE Bundle local build: \`app/dist/assets/index-Drlia61i.js\` SHA-256 \`84829aa02a83bbd8ce88e41a85bed337c516f8cae58f6b5d8b3bacf993ff9316\`; no GCP deployment of this asset.
- FE PR #26 changed 7 files after old \`32eb263\` to latest \`c9c204b\`. They are all **ADAPTED** (not byte-exact) in the current isolated worktree: \`app/src/api/liveFlow.ts\`, \`liveMapping.ts\`, \`useJob.ts\`, \`pages/CopyPage.tsx\`, \`pages/DraftPage.tsx\`, \`store/projectStore.ts\`, \`app/tests/liveMapping.test.ts\`.
- GCP read-only repeat: Live SHA \`3bb114359fdd05f8e6365f613e70254465b4e9b1\`, tree \`e5ec3001c98833bc40d349c9593b2a7151d9fd64\`, symlink target unchanged, HTTP 18088/18089/18090 = 200. Job status: 9 COMPLETED, 4 COPY_REVIEW_REQUIRED, 1 IMAGE_REJECTED. All 9 final PNG + Caption SHA PASS. Queue 42 SUCCEEDED; aggregated provider 70 SUCCEEDED_USAGE_UNPRICED; billing_unknown 0.
- These are **development checks only**. GCP BP13/14 isolated QA, actual Chrome mobile/desktop QA, Owner-reviewed 4:5 CTA, and human/freeform live AI acceptance are **not completed**.
