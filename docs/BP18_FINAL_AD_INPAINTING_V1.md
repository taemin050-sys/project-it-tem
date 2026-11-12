# Final advertisement inpainting v1

Track B user-authorized extension of RC9, not a change to the Release Master.
The Composed/Freeform **approved final PNG** is the editable source. Pure Freeform generation, prior text corrections, source-stroke retouch and protected Hybrid contracts remain unchanged. A partially edited result is explicitly `final_ad_masked_inpainting_v1`, not a new pure-Freeform generation or inherited approval.

## Open-source selection

React Konva 19.3.2 and Konva 10.9.1, both MIT, pinned in package-lock.json. Official source https://github.com/konvajs/react-konva and https://github.com/konvajs/konva. Free drawing/eraser, retained paths and native PNG export adapt the official example https://konvajs.org/docs/react/Free_Drawing.html. Notices ship in app/public/licenses. React Konva 19.3 matches our React 19.3; no commercial SDK subscription, new VM or new provider credential.

Compared with react-sketch-canvas (SVG-oriented general drawing) and Fabric (broader object/document editor), Konva fits a bounded React canvas mask with touch, compositing/eraser and precise native coordinates. Only our existing form, approval and artifact workflow is added. No whole design editor or third-party storage is introduced. The editor is included in the main bundle for the current signed beta transport; see the runtime note below.

## Lifecycle and trust

GET/POST `/demo/api/live/jobs/{job}/final-inpainting`; GET `/source`; GET `/{id}/artifacts/{preview|final|caption|receipt}`; POST `/{id}/decision`.

Signed SSO and source Job ownership apply to every request, including GET. Registered admin/evaluator actors may request/review only their own Jobs under the existing paid allowlist. The source must be COMPLETED LIVE Dual, final PNG/Caption/manifest/provider receipt intact, with current Copy/F09 approval. The context freezes mode, final/manifest SHA, generation, copy, approval, F09 and Actor. It is rechecked before/after provider I/O and review/download. Unsupported/stale/rejected sources fail closed.

PNG RGBA mask: nonzero alpha selects editable pixels. Server decodes and canonicalizes the exact native mask, rejects empty/wrong-size/animated/non-PNG/oversized masks and selection over 85%. Erased holes remain protected. Native 1080×1440/1350/1920 supported. The model gets a padded multiple-of-64 source and transparent edit mask; output is cropped without scaling. Outside-selection RGB is copied exactly from the source and reverified on retrieval. Transparent model pixels retain the source. This does not guarantee seamless design or text fidelity inside the mask; separate human checks remain mandatory.

Separate opt-in `runtime/live/final_inpainting.sqlite` reuses the audited revision-row schema and CAS/final download transaction. No active core DB migration and no database creation on import, cold start or listing before first explicit request. QUEUED→RUNNING→REVIEW_REQUIRED→COMPLETED/REJECTED, or HOLD/BILLING_UNKNOWN. Crash/uncertain sends never auto retry. The existing lifetime paid Worker/operator lock owns all dispatch. Recovery scans all revision namespaces before any paid claim. Each request freezes prompt/profile/mask/context and an idempotency key; one explicit request has at most one provider attempt. No provider secrets in Web, browser or Derived Worker.

Existing image edit adapter and native Owner Attempt/Receipt/asset plus outer CostLedger are reused. New fingerprint protocol `FINAL_AD_INPAINT_V1`; revision accounting excludes the same attempt from base Dual counts and never counts it twice. No invoice reconciliation is invented: actual USD remains UNPRICED/USD_UNRECONCILED. Same key after uncertain HTTP reuses the frozen body. Failed/rejected/incomplete derivatives cannot download final PNG/Caption.

The prompt preserves approved claims and copy. New copy content uses the separate copy/F09/reapproval flow. Even a visual edit needs new independent product/label/CTA/no-extra-text checks and an exact readback of Head/Sub/CTA. Old final approval is not inherited by the derivative; existing files/receipts never change. Final Receipt binds candidate receipt, human decision, final PNG and UTF-8 Caption.

## Deployment boundary

B-only reviewed source pair, whole-release inventories, B5 Dual/Derived/Auth/Review contracts and compatible rollback source. Existing queues must be idle/UNKNOWN0, Workers stop normally, all existing DB/Artifact bytes and record identities are backed up and compared before activation. New private DB is created by the first explicit edit, not boot. Fallback must include this queue namespace; old RC9 cannot consume pending/new inpainting rows safely and is not an activation rollback target. Actual rollback execution remains separately NOT_TESTED. No changes to A/Live/QA/dev.

Product NOT_RELEASE_READY. CODE/FIXTURE/REAL/HUMAN/RELEASE remain separate.

## RC10 validation baseline

77 targeted Python tests passed (16 inpainting scenarios plus 61 existing correction/copy/cost regressions), 86 frontend tests passed, TypeScript/Vite build passed. MockTransport tests use actual multipart image-edit adapter and verify native mask, erased holes, current final approval, independent mode receipts, CAS/rejection/download gating, unchanged originals and exact CostLedger attribution. Crash/response loss and publication failure do not trigger automatic calls. Three native output sizes have mask/alpha pixel tests; real provider and human quality evidence must be recorded separately. Lint has one nonblocking React state-in-effect warning at external Konva mask export synchronization; existing main chunk-size and Pillow deprecation warnings retained.

Actual Signed browser preflight on the first deployment exposed a transient dynamic module GET failure, which could blank the whole final-results tree. A per-mode error boundary now contains optional editor loading failures while preserving the existing approved PNG/Caption/Receipt actions. Its retry button reloads the page (GET-only); it never regenerates images or repeats a paid request. First deployment made no Provider calls and preserved all 11 existing DBs and 246 business artifacts; the source-bound Worker handshake file was refreshed normally. Final activation and actual provider evidence follow in the C-B submission.

Editor query refresh is disabled on window focus. An unsuccessful background GET retains the existing workspace, selected mask and prompt, with an explicit GET-only refresh button. Server CAS still rejects stale approvals; retaining the editing view does not grant stale writes.

Signed transport trade-off: automatic module subresource requests repeatedly returned 502 while direct signed fetches of the exact same bytes returned 200. The editor is now bundled with the main app rather than waiting for a second module GET. This increases initial JS by about 340 KB uncompressed (about 105 KB gzip) and avoids that additional failure point. Existing read-only gateway failures remain an operational note; this does not claim to fix all 502s. Error containment and workspace preservation remain. No paid retry or security bypass is involved.

Bundled startup was rebuilt and the same 86 frontend tests passed. Backend source/77-test evidence is unchanged. Compatible activation candidates must both include the bundled editor and final-inpainting worker namespace; invoice, actual visual quality, human decision and C independent acceptance remain separate evidence.

## Edge blending after actual model validation

The first two real edits returned valid model results, but hard-mask clipping left a visible color seam. A nonbillable Pillow recipe now erodes inward by min(32,floor(min(mask-bbox-width,height)/6)) native pixels, Gaussian-blurs that inner mask by half the radius, and multiplies by the exact original selection. All weights outside selection remain zero. Thin selections with no eroded interior retain the original selection. This is an explicit server postprocess, not a new Provider call or pure-Freeform claim; human design acceptance remains required.

New requests freeze `edge_blend_version=inside-feather-v1` in their existing request fingerprint. Historical unblended candidates require the explicit `/blend-edges` action before approval. That nonbillable Actor/Source/CAS-guarded action keeps old previews/receipts, writes new content-addressed versions, increments the review revision, and preserves the original Provider/Cost receipts exactly. Old SHA approval/download requests fail closed. There is no DB schema migration and no additional CostLedger entry. The candidate receipt records its parent hashes, recipe, Pillow version and zero additional calls. This bounded local composition runs on the Web, like existing deterministic final composition, without Provider credentials. The original model images, initial final PNGs and approvals are untouched.

After this feature has published versioned candidates, only the newly paired compatible sources may be used for B5 rollback. Actual rollback execution remains NOT_TESTED. Existing hard-edge previews are technical review evidence, not human-accepted final advertisements.
