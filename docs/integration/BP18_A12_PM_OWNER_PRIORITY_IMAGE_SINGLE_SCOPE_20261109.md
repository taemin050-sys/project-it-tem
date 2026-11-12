# IT-TEM P03 Track A — PM Integration Priority + Single-Image Scope Addendum

- Date: 2026-11-09 KST
- Policy source read directly: `handoffs/A/2026-11-09-a7141b8-session-restart/06_PM_INTEGRATION_PRIORITY_AND_IMAGE_SCOPE_20261109.md`.
- Policy ID: `PM_TRACK_A_OWNER_INTEGRATION_PRIORITY_AND_IMAGE_SCOPE_20261109`.
- Role: Track A implementation self-check, **NOT C independent acceptance**.
- Starting Worktree: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`, `integration/bp18-baseline-e2e-20261111@b976aa13b27552a59471d2591ae1c1c31253e7a9`, Tree `92e4b99f98e632b3b3c6a9642dbdb659861f8a29`, CLEAN at start.
- **Timeline correction:** policy handoff was written while A1.2 changes were uncommitted at `a7141b8`. This A session had subsequently committed those changes as `b976aa1`. Do not reset/cherry-pick/reapply the old snapshot.
- GCP/official dev/B Worktree unchanged in this unit; **no paid provider calls**.

## PM owner authority and conflict resolution

**Priority: FE #26 > Text #27 > Image #24 > Serving/Backend adapter**, except that F/V/S38, Actor/Job ACL, copy review/policy epoch, billing and artifact SHA safety are non-waivable.

| Owner | Verified source / A disposition | Decision |
|---|---|---|
| FE #26 | MERGED, original `c9c204b88af5ce1b25dfda501d16446750a41204`; previous A1.2: 3 EXACT + 7 ADAPTED + 3 ALREADY_EQUIVALENT | FE two-mode, three-ratio, single preview and explicit approval/retry is product authority. New `singleImageContract.ts` pins selected mode/ratio in the only input DTO; FE mode and ratio now both disabled while uploading/running or continuing active Job |
| Text #27 | MERGED, original `33c46b765c17b8f028553c343124f29de2969382`; previous A1.1 13/13 EXACT | Preserve Owner untouched. Serving SHA-bound compliance/revise adapter remains authoritative for safe approval; no unnecessary source copy |
| Image #24 | OPEN, original `b3ee33fd524fbbb83890472be890c96974160e9c`; 9/10 EXACT at start. A-adapted `composition.py` uses `unicodedata2` | Preserve single-candidate Owner adapter and overlay/resize behavior. Do NOT expose multiple Owner demonstration Job IDs as an A batch API. Source under `src/image_generation/` remains unchanged |
| Serving/Backend/Worker | **ADAPTED**, A-only integration contracts/HTTP/Worker | Reject N>1 and mixed selection at ingress, HTTP queue, QA fixture, persisted Job image request, and paid Worker *before* provider adapter and cost reservation |

### Explicit PM deferrals

The following are **`DEFERRED_PM_NOT_APPROVED`**, regardless of functions shown in Image Owner's documents or sequential calls in its internal test examples:

- `free-1 + composed-1` (2 candidates), `free-2 + composed-1` (3), `free-3 + composed-1` (4).
- Per-request `candidate_count=2/3/4`, `freeform_count`, `composed_count`, `batch`, `image_modes` mixed arrays.
- Gallery/multi-preview/comparison/voting/all-at-once-generation REST or UI.
- Any additional unapproved image variations. **9:16 CTA rendering policy is separately `DECISION_PENDING_PM_OWNER`.**

The underlying Owner package still allows an internal caller to create separate single-candidate Job IDs in sequence. This is an **internal library capability, not an exposed A user/API/Queue/Worker feature**; no direct Image Owner bulk copying or deletion is necessary. Preventing an arbitrary privileged programmer from directly importing internal libraries is outside this app's exposed product gate.

## Changed implementation and exact single-request evidence

- `app/src/api/singleImageContract.ts` [NEW]: runtime FE mode/ratio/Job ID validation, **exactly** `{customer_request_id,product,image_size,generation_mode}` JSON; no `candidate_count`, combination/mix flags or batch parameter. `app/src/api/liveJobs.ts` uses this helper.
- `app/src/pages/ProductPage.tsx`: both FE selection controls become locked while upload or AI is busy or an unfinished Job exists, preserving immutable selection.
- `demo_staging/live/contracts.py`: `assert_single_image_scope` validates **stored canonical snapshots** and refuses unknown count/mix fields, invalid modes or invalid ratios. Legacy no-mode Jobs preserve their original composed/4:5 interpretation; new explicit mode requires a pinned ratio. `validate_input` calls it before creating a Job.
- `demo_staging/live/http_api.py`: input HTTP request schema uses strict `Literal` for two modes/three ratios and forbids extras; authenticated `capabilities` advertises `candidate_count=1,batch_supported=false`; `queue-image` and QA `prompt-image` reject nonempty body or query params with 422 **before queueing**; `regenerate-image` and QA retry reject query count/mix and persisted violations; QA direct retry still calls only one local fixture candidate.
- `demo_staging/live/store.py`, `demo_staging/live/pipeline.py`: recheck the persisted scope on image-request assembly, including tamper/future extensions.
- `demo_staging/live/worker.py`: scope gate is rechecked **before** creating `live_image_adapter`, generating a provider request or reserving cost. Invalid jobs become held-for-reconciliation, never automatic retry.
- `src/image_generation/openai_images.py` existing Owner provider transport sets **`n=1`**, and `tests/image_generation/test_two_track.py` existing transport asserts that exact outgoing value. A did not modify the Owner transport.
- Live Queue `queued_ops UNIQUE(job_id,stage,context_sha)`; `LiveStore` one `image_sha` per Job, one immutable approved attempt at a time. Retry of a rejected image requires new explicit request key and attempt version; never create a multi-candidate batch from one click.

## Evidence and test separation

The new `tests/demo_live/test_pm_track_a_single_candidate.py` covers:

1. **6 positive** 2-mode × 3-ratio offline QA HTTP E2E cases with one candidate SHA, approved Copy→Prompt→Image→Compose→PNG/Caption, actual final sizes, Freeform font/overlay absent and Composed font receipt present.
2. **8 negative** input payloads, including candidate count 2/3/4, mixed mode, batch and unsupported mode.
3. **3 negative** direct queue/QA invocation count 2/3/4: HTTP422 with 0 queue ops / 0 paid attempts.
4. **1 negative** persisted Job mutation + real Worker dispatch simulation: explicit hold `PM_IMAGE_MULTICANDIDATE_SCOPE_NOT_APPROVED`, provider adapter never instantiated, 0 costs.
5. **4 negative** malformed/mixed persisted snapshots; **3 negative** regeneration batch attempts each followed by one successful explicit single retry, new SHA and attempt version, original Copy/Review SHA unchanged.
6. **1 OpenAPI negative** no batch/candidates/gallery/variants POST route.
7. Existing Owner Image `test_two_track.py` (single `n=1` per call) and `test_bp14_single_mode.py` continue PASS.
8. New `app/tests/singleImageContract.test.ts`: FE positive two modes/three ratios + invalid mode/ratio/job negative tests, no batch field.

Targeted full Owner Image + PM regression: **71/71 PASS**.
React: **57/57 PASS**; Lint 0 warnings/errors; Vite/TypeScript build PASS.
Full Python (no paid provider keys, full existing suite): **969 PASS / 1 FAIL**; existing `tests/demo_live/test_bp17_shared_minimal_export.py::test_existing_output_replaced_never_after_concurrent_publication` fails due to macOS Python 3.12 `fork`+SQLite child segmentation fault. **FULL PYTHON PASS NOT ACHIEVED**. The failure was already isolated under A1.2 (prior run 943/1), is not a modified Python source/test in this PM unit, and remains an open issue; no skip or test weakening. Final evidence: `/Users/Shared/ittem-a1-2-owner26-evidence-20261109/PM_SCOPE_FULL_PYTHON_FINAL.log`. FE evidence at the same protected Mac directory: `PM_SCOPE_REACT.log`, `PM_SCOPE_LINT.log`, `PM_SCOPE_BUILD.log`; targeted `PM_SCOPE_IMAGE_OWNER_TARGETED.log` covers the 70-test earlier subset, follow-up OpenAPI guard yields 71/71 PASS.

## Security / QA / C audit / remaining gates

- Authenticated Actor and Job owner check still precede HTTP image queue access; Image approval remains bound to Copy/Review/Generation, immutable attempt and candidate SHA.
- No alteration to Paid Provider secret, retry/billing policy or MONITOR_ONLY. No GCP A or B deployment; prior GCP A `9879eb0` is a historical snapshot, not a new release.
- Browser manual UAT, actual paid Provider, 6 real model results and Image Owner/PM visual review **NOT RUN**. Existing macOS Python 3.12 `fork`+SQLite intermittent segmentation fault still tracked as separate open failure.
- C independent audit: Verify FE live request DTO, formal REST 422 for 2/3/4 and mixed flags, Worker fail-before-provider, no automatic Job/Cost ledger growth, new explicit retry still single, mode/ratio freeze, 4:5 Composed internal CTA and Freeform no overlay, unmodified Owner source, frontend SHA binding from previous A1.2.
- Release Master r0.1: relevant F05/F12/F13/F14/F15/F16/F17/F19 and S02/S03/S04/S09/S10 are **CODE_IMPL/FIXTURE_EVIDENCE only**, not REAL_PROVIDER_E2E or HUMAN_PM_ACCEPTED. Owner/PM r0.1 approvals still separately required.
- Outcome: **A1.2 PM scope adjustment implemented locally; NOT_RELEASE_READY**.
