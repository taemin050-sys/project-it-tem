# IT-TEM Live A template — immutable job contract (2026-11-02)

Authority: PR #18 at 92c51a7. This worktree is isolated; no remote PR, GCP or live SQLite mutation.

| Boundary | New HTTP Job | Legacy Job pre-policy |
|---|---|---|
| Creation | POST Live /input installs A_CENTERED_V1 from Owner make_a_template() in the same transaction as new Live Job. Original owner safe_zone, layout, canonical digests stored. | Existing Job has no row in new table and must not be auto assigned A. Offline fixtures/direct library may create explicitly LEGACY. |
| Owner image | Use stored A zone; copy revision, asset order, original binding & owner fingerprint are unchanged. | Pass safe_zone=None; existing Owner binding/fingerprint unchanged. |
| Layout | Server-stored layout is authoritative. Client omitted layout allowed; supplied layout must match exact canonical digest, else 409. | Only an explicit new-version legacy ingress marker allows first compose to pin a provided, validated layout if no prior files exist. **Pre-policy IMAGE_APPROVED Jobs without a layout contract are manual reconciliation HOLD, not silently imported.** Otherwise no guessing/retrofitting. |
| Font | Pin SHA of server-specified font at first compose attempt. On retry require identical SHA, approved Copy revision/hash, image hash and image approval SHA. | Pin on first allowed legacy compose without rewriting original Job or Owner binding. |
| Receipt | Preserve exact result.receipt JSON in manifest, linked to artifact SHA, layout SHA and approval identities, in same SQLite transaction as COMPLETED. Stage files to private temp paths; finalize files before DB COMMIT. | Completed historical Jobs remain readable via existing final/caption GET. No synthetic receipt or retroactive A flags. |
| Recovery | IMAGE_APPROVED + frozen contract -> retry compose only, never Image Provider. Pending/partial files may be replaced only under same frozen contract. | Existing incomplete partial output with no frozen contract -> require manual reconciliation. |
| Completed | No compose overwrite or automatic regeneration; validate stored bytes + receipt/envelope hashes on reads. | Legacy completed GET continues using saved PNG/caption hashes; no receipt invented. |
| QA | needs_manual_check, missing protected_regions, or Owner warning => explicit manual review required. Never auto-claim product/label preserved. | No automatic product preservation PASS. |

Schema: live_job_templates(job_id PK, profile_id, profile_version, safe_zone_json, safe_zone_sha, layout_json, layout_sha, bound_font_sha, bound_context_sha, created_utc); live_compose_manifests(job_id PK, receipt_json, envelope_json, receipt_sha, envelope_sha, final_sha, caption_sha, created_utc). Existing tables' columns and records remain untouched. Manifest insert and live_jobs state update are one SQLite transaction. Provider attempts, billing, image binding & fingerprint tables remain untouched. Public GET exposes only minimized review status and final/caption (not raw receipt).

Manual product region review cannot be inferred from static A rectangles. A defaults to protected_regions=[]. No new HTTP wire for approving product bounds until PM/Owner review; lack of review is explicitly surfaced.

Rollback: switch isolated source checkout to previous SHA; no deployment is authorized in this task. Optional additive tables are ignored by old code; do not drop them or remove their contents when existing Jobs or manifests exist.

## Independent audit correction — P0 manifest-required invariant

Baseline audited SHA: 0eef75d22bc63749a6af2519027e0fccad260593.
The independent negative test deleted only the SQLite manifest of a new completed A Job and showed that the old compatibility exception silently allowed reads. This is now fail-closed.

- A ingress records template_a_ingress_contract_v1 atomically with new Job and pinned policy; first composition freezes compose_contract_frozen_v1. They are append-only provenance in the existing live_events table.
- If a finished Job has a stored template row, an A ingress marker or a frozen-composition marker, a missing live_compose_manifests row means COMPOSITION_MANIFEST_REQUIRED. It applies equally to A_CENTERED and LEGACY_PINNED, including if the policy row is also removed.
- IMAGE_APPROVED Jobs legitimately lack a completed manifest after render/file/DB failures, allowing identical-contract retries.
- Truly pre-policy completed Jobs with no template, no managed markers and no manifest still use legacy final/caption SHA verification. Receipt is never synthesized.
- Owner-scoped GET and artifact download, team share, shared file access and evaluations fail closed if managed manifest integrity is unavailable. Raw receipt and envelope stay private.
- Owner A v1 policy is verified against immutable versioned digests: safe zone c0fed10c854d6c8483d782f8721d60df7e6b975ceabeaab23dfb5ebe0861f4ce; layout c9fe0d76a35e8171cbfca2b23ae1eafc2bd4d60e9ad7cb8164098b6f420d43e1. Historical verification never calls a future Owner default factory. If Owner defaults change, new v1 creation fails with A_TEMPLATE_VERSION_DRIFT until an explicit v2 contract is released.
- Additional DB tables are unchanged. Existing PR #18 baseline, Provider usage records, GCP and Tailnet remain untouched.

Re-audit requires independent focused tests for manifest/policy deletion, HTTP GET/download/share/evaluation safety, missing artifacts and Owner factory evolution; plus full offline Python and React regression. Local test success does not constitute independent audit acceptance.
