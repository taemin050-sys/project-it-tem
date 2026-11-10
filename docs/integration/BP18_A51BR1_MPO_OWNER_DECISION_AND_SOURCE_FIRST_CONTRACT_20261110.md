# IT-TEM P03 / Track A — A51B-R1 MPO Source-First Owner Decision Packet

**Date**: 2026-11-10 KST. **Scope:** Implementation readiness and Owner/PM decision, not signed authorization. `MPO_PROVIDER_USE=HOLD`.

## 0. Confirmed actual baseline

- C-A51B evidence: 24 unchanged original SHA, filename-derived 10 product groups, 1 duplicate pair, 9 ordinary JPEG, **15 two-frame MPO files disguised as .jpg/.JPG**. All 15 are actual two-frame MPO; no corruption observed.
- Existing Image Owner `src/image_generation/assets.py` `LocalAssetStore.put_upload`: when PIL identifies MPO, silently `seek(0)` and publishes one normalized PNG. Contract validated in `tests/image_generation/test_asset_portability.py`. AssetRef/public metadata does not demonstrate **user confirmation** of frame choice.
- Existing provisional upload `src/serving/job_api.py` `validate_upload`: when filename is `.mpo`, calls `_normalize_mpo_upload` and silently selects **frame index 0**, recording original filename, source SHA, frame count, EXIF orientation, ICC SHA and converted JPEG SHA in `source_provenance`. Validated by `tests/test_bp13_mpo_upload.py`.
- **Path discrepancy:** in provisional `job_api.validate_upload`, if a file is named `.jpg` yet decodes as `MPO`, the normal JPEG branch rejects it as non-JPEG (`IMAGE_FORMATS.get('MPO')=None`). The Owner `LocalAssetStore.put_upload` accepts decoded MPO independent of extension and automatically selects 0. Neither current path requires a user-selected frame index. This may materially affect the supplied 15 JPG-named MPO photos.
- These two existing Image Owner/Serving source paths are **NOT** being silently modified or promoted by this packet. FE #26 > Text #27 > Image #24 > Serving Adapter retains priority; require Image Owner and PM to choose a single exposed Beta ingress policy.

## 1. Minimal requested Owner/PM decision

| Decision | Concrete question | Safety-conservative fallback until decided |
|---|---|---|
| MPO-C01 | Reject all multi-frame MPO in beta, or permit selected-frame import? | **Reject or require user-selected normalized single frame before beta** |
| MPO-C02 | On permitted import, must user explicitly preview/select 0 or 1 (or supported indices) and confirm? | **Explicit selection and confirmation; never silent 0** |
| MPO-C03 | Must import accept disguised JPG-named MPO? | **Validate decoded container and original suffix separately, never trust extension** |
| MPO-C04 | Define source SHA, frame index/total, selected frame pixel fingerprint, normalized bytes SHA, transformations. | **Retain complete provenance for new Jobs only** |
| MPO-C05 | EXIF rotation, ICC→sRGB, alpha, JPEG quality, resize: author and approve a deterministic normalization contract. | **No production normalization before formal Owner decision** |
| MPO-C06 | Who reviews all frames for customer-visible selection and confirms target product, packaging, label, color? | **Owner/PM human review; no automated brand quality PASS** |
| MPO-C07 | How will FE #26 show selection and retries? | **No hidden automatic upload/Provider call, 1 final candidate only** |
| MPO-C08 | What changes permitted without invalidating old v2/A5-1 receipts? | **Versioned new Job/asset import only; old artifacts immutable** |

**Recommended narrow design:** New Track A Beta import contract `MPO_EXPLICIT_FRAME_SELECTION_V1`: decoded true MPO with 2+ frames → display each frame locally, require user to select one index and approve → normalize ONLY selected frame with documented EXIF orientation and color transformation → persist raw container SHA + chosen frame index + conversion algorithm/version + normalized single-frame SHA + confirmation provenance in new immutable Job input/asset binding. Raw input must not be transmitted to external Provider without explicit legal-use authority. This is a **proposal**, not a change to the existing Owner source or approved Image policy.

**Temporary option:** For rights-cleared JPEG-only product groups use already single-frame source photos, while MPO UI/Owner contract is reviewed. Original product/brand rights are not currently verified for any group, therefore the real Provider remains HOLD even for ordinary JPEG.

## 2. Acceptance and negative tests for Owner MPO implementation

1. The fifteen supplied MPO files (two frames each) can be classified without relying on `.jpg` extension, but **no raw files** are committed/exported/transmitted.
2. Without explicit choice, MPO beta ingress fails closed *before* asset persistence or Provider/Queue/Cost Attempt. Explicit frame 0/1 choice is the user selection, not a hidden default.
3. Selected frame index outside available frames, altered source container SHA, mismatched MIME, invalid EXIF/ICC, pixel/byte limits, forged or replayed selection, and mismatched normalized SHA all fail closed.
4. Preserve exact and versioned transformations; check EXIF upright dimensions, ICC→sRGB color consistency, label/font fidelity. Face/person/private metadata must not leak into normalized export.
5. New Job requests remain one mode, one ratio, one output candidate. Existing v2 jobs/receipts and existing Image Owner's legacy MPO behavior remain unchanged until explicit versioned contract migration.
6. Real marketing use additionally requires image rights, same-physical-product identity proof (not filenames), mask accuracy, source↔output logo/label check, C-A differential and human Owner/PM visual acceptance.

## 3. Recipient roles and actionable request

- **Image Owner 박지수:** Select MPO-C01–C06, document exact normalization API/DTO and required provenance field names, approve versioned implementation or reject MPO for Beta.
- **Frontend Owner #26:** Confirm UI for frame preview and user choice, actor/job binding and single-candidate flow if MPO supported.
- **PM 이태민:** Confirm safety-conservative temporary rejection vs release-quality explicit selection scope, rollout/rollback and marketing sample rights. No reapproval request for Freeform/Composed, 3 ratios or single candidate.
- **Track A Serving:** Implement only the signed versioned Owner/FE contract, protect prior Jobs and require C-A differential.

**Request delivery status:** `PREPARED_NOT_CONFIRMED_DELIVERED`. No actual Owner/PM receipt or signature is asserted. All examples and real-product media remain restricted to local nonbillable QA. GCP, paid Worker, real Provider, team UAT HOLD.
