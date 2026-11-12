# IT-TEM P03 Track A — A4-1 정식 React Chrome 4:5 Composed 제품 E2E C-A 차등감사 제출

**Date:** 2026-11-09 KST · **Owner First:** FE #26 > Text #27 > Image #24 > Serving Adapter, 단 A2/3 필수 Safety/Cost/Actor/SHA 불변.
**보고 책임:** Track A 개발 자체검증. **C-A 독립감사·Owner/PM 품질 승인 아님.**
**기술 판정:** `A4_1_OFFICIAL_FE_CHROME_OFFLINE_FIXTURE_FUNCTIONAL_PASS_WITH_PRODUCT_CTA_HOLD`.
**운영 상태:** `GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

## 1. 승인된 기준점과 분리 커밋

- C-A3R.1 최종 독립 수용: `C_A3R1_LOCAL_SOURCE_ATTESTATION_ACCEPTED_WITH_DEPLOYMENT_NOTE` at `164f592fbd0399c1c464b8ddd0df091d786c3b0e`; audit `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A3R1_FIXED_SOURCE_INDEPENDENT_AUDIT_20261109.md`, verified SHA256 `3807c84e291099d37e302a4d9b88254bd56e005c458867c5ed401d2a2c5e6d30`. Safety revisions ACCEPTED, not reopened.
- A4-0 E2E Matrix **already separately committed** `f045308de805126c7c3c6b2da523ad97a50a5f5c`, Tree `98dedcdf5ba3ef571d242b4611f58fbf2aa91e9b`. Source inventory 26 HEAD-pinned files, 13 stages, 6 mode×ratio scenarios and negative test matrix; no browser PASS claimed at A4-0.
- **A4-1 reproducible browser harness only**: `df4ef6128bd2902e9037a2d943470ea9ebea69a0`, Tree `97a8ce50f3526dc3137b6299c55fb4b38edee94d`. Added `tests/product_e2e/{a41_fixture_server.py,a41_official_react_chrome.cjs,a41_verify_offline_evidence.py,run_a41_offline_chrome.sh,README_A41.md}`. Owner source/Serving runtime/App React source production files unchanged.
- A4-1 browser evidence was independently regenerated **after** harness commit with build `VITE_IT_TEM_CODE_SHA=df4ef6128bd2902e9037a2d943470ea9ebea69a0`. Subsequent report/PNG evidence commit HEAD will differ **only by documentation/evidence**, not FE/Serving/Owner executable sources. Final HEAD/Tree must be checked by C-A from Git; do not mistake code commit for final documentation HEAD.

## 2. Real Chrome / fixture execution isolation

- macOS Google Chrome **157.0.8103.38**, real official frontend `app/src/main.tsx` → `DemoGate` → `ProductPage / CopyPage / DraftPage / ExportPage`, not `tests/browser-harness` B0 app, not Mock Fetch.
- Server `make_demo_app` and original Track A FastAPI are served **same-origin over 127.0.0.1:18538**, disposable `/private/tmp/ittem-a41-product-XXXXXXXX` root. QA credentials are synthetic and never copied to audit packet. Separate QA bundle `VITE_QA_OFFLINE_FIXTURE=YES`; QA persistent banner shows **실제 AI 아님**.
- Server `IT_TEM_QA_FIXTURE_ENABLED=YES`, `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_LIVE_EXECUTION_APPROVED=NO`, `IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO`, `IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO`, `IT_TEM_DEMO_SECURE_COOKIE=NO`; QA actor `alice` only. Provider keys unset. Chrome external URL requests aborted, network external POST 0. No GCP/Live18088/QA18095/B18100 accesses or changes.
- 4:5 Composed, static synthetic RGB inputs 2 × 480×640; reference 0; browser true upload; FakeOwner static Vision/Research/Copy/Image Prompt; QA generated flat-color PNG (NOT a real model). Korean composed overlay uses installed local AppleGothic font; **font rights for commercial delivery are not asserted**.
- Executed through `bash tests/product_e2e/run_a41_offline_chrome.sh`, clean standalone local orchestration, reproducible per `tests/product_e2e/README_A41.md`; actual runner result **Exit 0**. Runner kills only its own ephemeral web process on completion. Browser screenshot+Trace and Receipt review occur before adding any GCP deployment authority.

## 3. Browser-level results (actual user clicks, not only API TestClient)

| ID | Actual Chrome action / independent proof | Result |
|---|---|---|
| B01 | local QA login `/demo/api/session`, real Owner frontend QA badge and actor identity | PASS |
| B02 | upload two product files, select `composed/4:5`, B0 Job HTTP201, Live input HTTP200, frozen server mode/ratio/input SHA | PASS |
| B03 | Copy review current `generation/copy_sha/review_sha` displayed; pre-approval candidate/final GET return 409 | PASS |
| B04 | Browser/API refuses 2,3,4 candidate counts and mixed `image_modes` with HTTP422; no queue/provisioned provider | PASS |
| B05 | UI Copy revision `generation+1` and new `review_sha`; old approval false | PASS |
| B06 | UI previous Copy restore `generation+2`, original `copy_sha` restored **but new `review_sha`**, old evidence approval stays invalid | PASS |
| B07 | stale Copy approval direct authenticated POST returns 409/422; current browser evidence checkbox required | PASS |
| B08 | current Copy approval → QA prompt → **one** `IMAGE_REVIEW_REQUIRED` candidate, GET byte SHA matches server `image_sha` | PASS |
| B09 | user image rejection, old candidate GET409, explicit regeneration only → Attempt 2 and distinct candidate SHA | PASS |
| B10 | stale old `image_sha` approval HTTP4xx; current image preview hash verified before UI approval | PASS |
| B11 | image approval and composed final PNG/Caption, `COMPLETED`, final size 1080×1350 and two SHA-256 digests | PASS |
| B12 | **actual Chrome download buttons** save `ad_1080x1350.png` / `caption.txt`; output bytes hash equal committed `final_sha/caption_sha` | PASS |
| B13 | Chrome reload/resume leaves Job completed and causes **0 additional POST** (GET-only) | PASS |
| B14 | real Chrome desktop 1440×900, mobile 390×844 and 360×844 screenshots | CAPTURED; visual quality **not human accepted** |
| B15 | no-session foreign GET HTTP401, authenticated other actor Bob trying Alice's Job HTTP404 | PASS |

Sanitized Trace `docs/integration/evidence/A41_20261109/browser_trace.json`: **15 steps**, **12 actual browser screenshots**, 75 observed GET and 18 observed POST (including user-authorized fixture workflow and negative tests), **external POST 0**, **page JS errors 0**. This is a single isolated 4:5 Composed journey, **not** six Chrome scenario passes. Failed checks are not weakened into skips.

## 4. Read-only SQLite/Receipt/PNG independent verification

Code: `tests/product_e2e/a41_verify_offline_evidence.py`, separate from Chrome runner's page assertions. It opened isolated 3-ledger SQLite with `mode=ro`, checked:
- final Job `mode=OFFLINE_FIXTURE`, `state=COMPLETED`, `generation=3`, `generation_mode=composed`, `image_size=4:5`, 2 product assets, 0 references.
- Exactly two `live_image_attempts`: version 1 `REJECTED`, version 2 `COMPLETED`; unique Attempt IDs and different image SHA, same `approval_sha` and `prompt_sha`. Copy policy binding one, Prompt context binding one.
- Queue `queued_ops=0`, CostLedger `attempts=0`, simulated provider calls `0`; real provider invoicing **not audited**.
- Final PNG browser download `SHA256=a43bd648a8803a875d7199b9ca10af70fb585e9f2ed29431d5c516fa62e50179`, bytes identical to Server final and `final_sha`, **1080×1350 PNG**.
- UTF-8 Caption download `SHA256=a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839`, bytes identical to committed caption and `caption_sha`. Caption contains Owner Copy **long-form caption and hashtags**; it is not required to repeat the graphic Headline/CTA.
- Composed Receipt field SHA of rendered `headline` and `subline` equals approved Korean Copy exactly; no indication of on-image CTA, see next section.
- Screenshot files hashed and matched Trace. Summary JSON: `docs/integration/evidence/A41_20261109/ledger_artifact_verification.json`, verification Exit 0.

**Regression after A4-1 code commit:** local Python `pytest -q -p no:cacheprovider -p no:warnings tests` with disabled provider vars **1052/1052 PASS** (Mac3.12, Exit 0); `npm --prefix app test` **57/57 PASS**; `npm --prefix app run lint` 0 error/warning; `npm --prefix app run build` PASS. The A4-1 run did not modify any A2/A3/A3R/A3R.1 runtime security/source modules, Owner files, official GitHub, Track B or GCP.

## 5. Newly uncovered product quality blocker — **A41-PRODUCT-CTA-01**

**Issue / severity:** `4X5_COMPOSED_ON_IMAGE_CTA_MISSING` · Product Fidelity P1 (technical flow intact). **Not silently waived by Chrome/PNG SHA PASS.**

1. Existing PM/Owner acceptance text `docs/integration/BP17_T_V_I_OWNER_SOURCE_FIRST_ACCEPTANCE_MATRIX_20261107.md` §Track V explicitly states **new 4:5 Composed needs on-image CTA**, while 9:16 CTA remains `DECISION_PENDING_PM_OWNER`.
2. Real Track A Image Owner file `src/image_generation/layout_profiles.py` `PROFILES["feed-4:5"]` has **only headline/subline text regions**; `make_placement_layout` and `render_layout_instruction` yield `cta_placement=platform` except `feed-3:4`.
3. Actual 4:5 Compose Receipt, bound to final downloaded image, contains `"cta_placement":"platform"`, `"omitted_image_fields":["cta"]`; `placements` has headline/subline only. The approved CTA is `지금 만나보세요`, SHA256 `29f1185e55a4d3499794d36ada72dda3556cb88a0bd220690a9e0811a5fbc0be`, but it is **not rendered in final PNG**.
4. **Disposition:** E2E navigation/download `BROWSER_E2E_PASS(OFFLINE_FIXTURE)`; **4:5 actual advertisement Product Fidelity `HOLD`**, `VISUAL_REVIEW_PASS` and `HUMAN_PM_ACCEPTED` **not granted**. Evidence is objective Receipt and Owner Profile, not speculative OCR.
5. **Required remediation:** Image Owner and PM approve a **versioned 4:5 Composed profile** with on-image CTA region, copy line/bounds/contrast/typography/brand-product safe zone, exact Owner profile SHA and commercial-use font licensing. Track A then adapt the Serving bridge **for newly created Jobs only**, pin Profile/Font/Copy/Approval SHA, preserve earlier Job layouts and historical receipts, and replay 4:5 Chrome plus 360/390px visual comparison; C-A differential audit, Owner/PM quality signoff. Do **not** patch `src/image_generation/layout_profiles.py` blindly, choose arbitrary CTA coordinates, or import Track B code. Existing 9:16 CTA decision remains pending separately.

## 6. Audit artifact location and SHA scope

Mac Track A canonical:
`/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first/docs/integration/evidence/A41_20261109/`

Evidence includes **23 actual browser/result/log files** plus `SHA256_MANIFEST.txt`. 12 Chrome screenshots (login, selected input, Copy initial/revised/restored, candidate first/rejected/new, final desktop/reload and 390/360 mobile), `ad_1080x1350.png`, `caption.txt`, `browser_trace.json`, `ledger_artifact_verification.json`, Python full test, React, Lint/Build, build/runner/validator logs. The file manifest covers evidence content only (not private fixture token or SQLite database), SHA verified after copying. C-A should replay the standalone script from a fixed checkout and compare actual output with this packet.

**C-A differential audit request:**
1. Verify real Owner React UI, not old B0 harness; Chrome must execute actual clicks and file downloads, not only `TestClient`.
2. Validate Job/Actor/Review/Copy/Prompt/Attempt/Image/Final SHA chain and source build label; independently inspect saved downloads, PNG pixels, Receipt and sanitized network Trace.
3. Verify HTTP422 batch counts 2/3/4 and mixed, HTTP401/404 unauthorized ownership, old SHA approval blocked, GET-only reload and no paid queue/cost/provider calls.
4. Independently reproduce **CTA missing finding** from Owner `feed-4:5` layout + committed Receipt/PNG; accept browser function **only with explicit quality HOLD**, not `PRODUCT_COMPLETE`.
5. Reconcile existing A3R.1 local source acceptance `164f592` and new A4-0/A4-1 commits separately; only local test code/docs changed in A4-1. QA deployment still requires separate GCP source/SSO/rollback authorization.
6. Retain `A4-S02..S06` Browser E2E = NOT_AUDITED, actual model and human quality = NOT_AUDITED/NOT_ACCEPTED.

**Developer judgement:** `A4_0_DOCUMENTED + A4_1_OFFICIAL_REACT_BROWSER_FIXTURE_FUNCTIONAL_PASS + A41_PRODUCT_CTA_01_HOLD + C_A4_DIFFERENTIAL_AUDIT_PENDING + GCP_A_QA_DEPLOYMENT_HOLD + A_GCP_PAID_WORKER_HOLD + NOT_RELEASE_READY`.
