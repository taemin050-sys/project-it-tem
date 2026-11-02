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
