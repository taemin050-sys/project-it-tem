# IT-TEM P03 Track A — A51B-R1 GCP A isolated full-feature beta deployment preflight

**Status: DEPLOYMENT HOLD, worker disabled, no GCP writes; 2026-11-10.** This is a reproducible change plan, not permission to deploy. C-A51B independently inspected GCP via preauthorized read-only SSH; no extra `gcloud auth login` needed for those read-only probes.

## 1. Pinned local candidate and known remote mismatch

- Latest development source on Track A after R1 and standalone read-only MPO probe: `ab1ee76462ba4a6935b7b9987d64557dba4dd138`; git tree `47f09d081a8b88e51a2ff8a971aafbfbc5589a34`. **No actual GCP A runtime of this version is verified.**
- React Build is `OFFLINE_FIXTURE` with source label `ab1ee764` only; currently pinned JS bundle SHA `256bc2197aefefd8d5e9ea5ba642584efb1c8fdb2d233fda05c317d4cc65c0bd`; index.html SHA `913ddcf27412659c242efc91d97ea4bb79fbcdc63c924c38df4457376af12d2a`. **Not a deployable signed beta artifact.**
- Original A/C actual Owner compositor receipt + React Chrome E2E previously accepted C-A51; new signed-profile v3 has only local throwaway Ed25519 signatures, synthetic protected masks, **not real product rights or PM/Owner signoff**.
- Most recent independently observed GCP A source is **old** `9879eb0f85747312a224ecd898aaff84d834590b`; read-only evidence `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/evidence/C_A51B_20261110_1900/C_A51B_GCP_REMOTE_READONLY_PROBE.json`. A-only root `/home/macstudio/ittem-e2e-baseline-20261107`.
- C-A51B known data: `runtime/live/live.sqlite:live_image_attempts` = **8 COMPLETED** (app ledger); `runtime/live/queue.sqlite:queued_ops` = **0**; `runtime/live/cost.sqlite:attempts` = **0**; **`runtime/live/owner_image/image_attempts.sqlite` missing** (separate Owner paid provider ledger). Presence of app attempts never substitutes for Owner Provider attempts. No missing DB is to be created automatically in protected current runtime.

## 2. Dependency map, change boundary and acceptance proof

| Plane | Approved change boundary | Required non-mutating acceptance evidence |
|---|---|---|
| Source | New immutable A-only candidate directory, separate from active root | Git HEAD/tree, diff provenance, file-mode/SHA manifest and installed owner source packages |
| Frontend | Same React official source built for A-only runtime and correct HTTPS origin | Exact JS and index SHA, source label, API endpoint, 390px/360px browser trace |
| Identity | Signed Tailscale SSO and per-Actor Job ACL on separate A listener | 401/no session, 404/cross-Actor, cookie/CSRF and OAuth claims validation; never publicly bypass SSO |
| Product/Mask | New signed-beta A/C profile, real product/labeled region verified | Owner/PM real dual signing in protected key root, licensed font/brand, explicit product mask/profile SHA, Overflow/CTA |
| Worker | Fully disabled until PM **separately** authorizes paid calls | Process list showing no active billable worker, env flags NO, no provider secret in public app |
| App ledger | Candidate-only isolated `live.sqlite` (not old DB) | `live_image_attempts` schema and attempt idempotency / rejected→retry CAS |
| Owner paid ledger | Candidate-only `owner_image/image_attempts.sqlite` **after explicit approved init** | `provider_attempts` DDL hash, non-null constraints, valid binding to request/job/receipt, fail-closed missing/unknown |
| Queue+Cost | Candidate-only dedicated queue.sqlite/cost.sqlite | 3-way reconciliation with Owner Provider ledger, `BILLING_UNKNOWN` no auto retry, hard spend cap with bounded reservation |
| Rollback | Immutable old A deployment and old original DBs untouched | Snapshot/digest, independently rehearsed rollback to old A listener/source, no B/Live/QA changes |

## 3. Ordered A-only rollout plan (not executed)

1. **PM approval:** A-only isolated beta deployment permission, intended hostname, target listener, signed SSO permission, dedicated operator. Keep B18100, protected Live18088, QA18095 and historical A runtime unmodified. No changes to official GitHub dev/Owner PR.
2. **Current read-only state:** With preauthorized SSH, rerun `scripts/a51b_gcp_a_readonly_ledger_probe.py` streamed over stdin as C-A51B did. Cross-check active process PID, runtime root, installed SHA, current WAL/SHM, free space, firewall/listeners, TLS cert, Tailnet identity, credential scope. Do not write to the old VM just to determine this.
3. **Prechange backup:** Under separate PM-authorized operator action only, generate consistent SQLite online backups (including WAL states), file-digest baseline and reproducible source/config snapshots in protected A-only backup path. `cp` of an open SQLite DB without WAL consistency is NOT an adequate verified backup. Establish recovery drill with explicit restore destination.
4. **Build fixed isolated source:** Copy only pinned allowed Git source from `ab1ee764...` or later C-A accepted commit. Install dependency locks, pinned Pretendard binary and license; produce exact build and backend runtime SHA. Do not use `VITE_QA_OFFLINE_FIXTURE=YES` as evidence of signed real betas. Build/sign actual candidate with documented, reviewed A-only config after authentic Owner/PM approval and rights evidence.
5. **Separate DB paths:** Initialize a new candidate directory with fresh, explicit schema migrations and full manifest including Owner Provider Attempt DB **only after authorized change review**. Do not auto-migrate historical old A jobs; protect default v2/A5-1 receipt contracts. Start with worker disabled and verify zero external Provider calls.
6. **SSO and dry browser E2E:** Verify signed SSO, Actor/Job separation, upload→analysis/research→F09→F11→image approval/retry→PNG/Caption, 6 fixture independent one-image Jobs and no automatic provider calls, browser 360/390/resume/refresh GET-only, corrected v3 typography and mark authenticity.
7. **Paid release separate:** PM approves max spend, hard cap, API key custody, actual 3-ledger schema reconciliation, service process Idempotency and unresolved receipt fail-closed, legal rights/brand QA. Only then enable worker for six separate `Freeform|Composed × 3 ratios` requests (one candidate per Job). Never repurpose a fixture as real output.
8. **Team UAT:** Real Chrome from externally reachable **signed** private team URL, Actor/ACL, real model artifacts, 6 real job receipts + usage and costs, Owner/PM human advertising QA, feedback channel, incident runbook. New commit/runtime SHA and authority evidence must match manifest before declaring `TEAM_UAT_READY`.
9. **Rollback rehearsal:** Stop only newly isolated A worker/listener. Verify no unknown billing attempts; restore old A routing atomically only under operator authority, confirm previous SHA/health/ACL and historical data, preserve all candidate receipts for reconciliation. Never rewind or delete paid ledger rows before cost settlement.

## 4. Immediate blockers and authorization owner

- **Image Owner #24**: MPO selection/EXIF/ICC Provenance Contract (see `BP18_A51BR1_MPO_OWNER_DECISION_AND_SOURCE_FIRST_CONTRACT_20261110.md`) and actual product/logo/label masks; 15 named-JPG MPO files cannot be assumed acceptable to current prototype API.
- **PM + Image Owner**: authentic signed A/C exact profile/fonts/mask and a real rights-cleared product sample. Existing TEST signatures are not authority.
- **PM financial**: cost hard cap (not `MONITOR_ONLY`), worker-only credential ownership, bounded reservation and Unknown Billing reconciliation; never invent $ amount.
- **Infra owner**: A-only isolation, known-host SSH, approved backup path, rollback test, signed SSO and protected URL. The observed older A build is not an approved forward deployment.
- **C-A**: differential audit of R1 signed-time repairs, new MPO trace, deployment candidate and actual cost/Provider/visual evidence. Already accepted C-A51 A/C local Chrome need not be repeated in bulk.

**Strict status:** `SAFE_NONBILLABLE_DEVELOPMENT_GO`, `SIGNED_PROFILE_REAL_OWNER_PM_APPROVAL_PENDING`, `MPO_OWNER_POLICY_PENDING`, `GCP_A_QA_DEPLOYMENT_HOLD`, `A_GCP_PAID_WORKER_HOLD`, `REAL_PROVIDER_E2E=0/6`, `FULL_FEATURE_BETA_DELIVERY_HOLD`, `COMMERCIAL_RELEASE_READY=NO`.
