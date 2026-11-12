# Track B RC7 beta scope — 2026-11-12 KST

Target: team UX testing this morning, project demonstration tomorrow morning.
This beta remains `NOT_RELEASE_READY` and does not change Release Master r0.1.

The implementation commit `06c9e4f3b1b333788c42f4e2d1796af6222fa196`
provides the compatible fallback for this documentation-only forward candidate.
Both candidates read historical text-edit v1/v2 records and new frozen
`source-style-preserving-glyph-edit-v3` requests. After a v3 request is admitted,
the older `2db299ad` source is not an eligible rollback reader.

## User-visible behavior

- Independently approved copy/image revisions are discoverable at the top of
  the comparison and final-results pages. Their PNG, Caption and Receipt can
  be saved without falsely approving the rejected original candidate.
- Freeform repairs use the smallest changed text span as model context and
  preserve source pixels outside the deliberately selected rectangle. The
  original and corrected regions are shown at equal scale. Spelling and
  typography quality still require fresh human review; no automatic acceptance.
  Selection coordinates use the displayed image's native aspect ratio for all
  three output ratios, without a fixed 4:5 letterbox or mismatched wrapper.
- Revision image-edit and copy-review attempts are separated from initial
  shared planning and image generation counts. USD remains unreconciled;
  no unverified amount is recorded as zero and no automatic paid retry is added.
- New composed manual-copy requests freeze their LLM review model. Historical
  request, F09, approval and Receipt bindings retain their original format.

The B Mac gateway transport fix separates client disconnects from upstream
failures and does not emit a second HTTP status after response headers. It
preserves SSO signing, allowlists and ports. Historical intermittent GET 502
causes are not all proven closed by this patch.

## Exact human approval already received

The user approved composed copy revision `050ab5fe7b0a46a1bc6cd82609957bab`
and then explicitly confirmed label comparison and image approval for preview
SHA `9ed30aae561d3cc918c504ce77f4ffbbb78f8dac0b430011c78ebfee7e97eb7c`.
The Signed browser downloaded this 1080×1350 PNG, UTF-8 Caption and independent
Receipt, all matching server SHA. This is one artifact's human attestation;
it does not establish global label ground truth or approve other candidates.

## Activation gates

Use exact source-pinned Frontend builds and full Dual/Derived inventories for
both candidates, B5 operator lock, normal Worker shutdown, transactional
backups, and unchanged existing DB/Artifact witnesses. No schema migration is
introduced here. Verify Signed SSO, all B services and other Track health after
each transition. Preserve all historical Provider/cost records and block
`BILLING_UNKNOWN` before dispatch. Rollback eligibility and actual rollback
execution are separate evidence.

CODE, FIXTURE, REAL, HUMAN, C independent audit and RELEASE remain separate.
Freeform typography, remaining ratios, team UX/UAT and final product acceptance
must not be inferred from the successful composed download.
