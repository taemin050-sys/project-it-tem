# Track B result text revisions v1

This extends the approved Dual 1+1 contract without modifying its two original
candidates. Product acceptance remains `NOT_RELEASE_READY`.

* `FREEFORM_TEXT_EDIT_V1`: an explicitly selected rectangle and the current
  approved target text authorize one masked Image edit. The immutable source
  remains rejected if it was rejected. Only model pixels inside the rectangle
  enter the new native PNG; pixels outside it remain exact. The result is
  `freeform_model_text_corrected_v1`, separately reviewed and receipted. No
  server font overlay is applied. Final export resizes to the selected ratio.
* `COMPOSED_COPY_EDIT_V1`: direct Headline/Subline/CTA editing creates a separate
  copy revision with the existing Caption/Hashtags. Changed wording requires a
  new rule + real LLM F09 and explicit copy approval before composition. A
  separate image review precedes download. Image Provider calls are zero.

The UI does not treat submitting either request as final copy or image approval.
Small unreadable product labels remain a separate human acceptance gate.

The two private stores are `runtime/live/image_corrections.sqlite` and
`runtime/live/composed_copy_edits.sqlite`. They are created by explicit POST,
not ordinary status GET. They do not migrate the existing live job tables.
The existing paid Worker lock serializes both stores and the ordinary queue.
Recovery checks both revision stores before any new dispatch. RUNNING ownership
lost across restart is never authorization to resend; UNKNOWN stops all claims.

Required opt-in configuration in both Web and paid Worker source policies:

```
IT_TEM_IMAGE_CORRECTION_ENABLED=YES
IT_TEM_IMAGE_CORRECTION_PROTOCOL=FREEFORM_TEXT_EDIT_V1
IT_TEM_COMPOSED_COPY_EDIT_ENABLED=YES
IT_TEM_COMPOSED_COPY_EDIT_WORKER_PROTOCOL=COMPOSED_COPY_EDIT_V1
```

Before the first revision request, legacy `6326835` can be a migration bridge.
After revision stores contain work, both approved forward/rollback sources must
include both protocols and the global recovery coordinator. Do not activate a
legacy Worker that ignores those stores. Preserve the stores, receipts and
original artifacts during rollback. A real rollback execution remains a separate
verification; registering a compatible source does not prove it was executed.

Cost records use the original Actor/Job with distinct revision fingerprints.
Common VLM/Text/Image costs are not replayed. Actual USD remains UNPRICED until
provider billing reconciliation. Neither a mask nor OCR establishes human text,
product-label, design or release acceptance.
