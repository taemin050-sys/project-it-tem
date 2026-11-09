# IT-TEM P03 Track A A3 — Guarded Deployment & Billing Incident Runbook

Policy: A2 security code accepted by C-A 2026-11-09, `C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE`. This document describes **preparation only**. Neither a passing manifest nor an HTTP 200 is authorization for a deployment, billed HTTP POST, official GitHub merge, or production release.

## 1. Protected environments and scope

| Target | Fixed locus | A3 permission |
|---|---|---|
| **A only** | GCP project `sprint-ai-chunk4-02`, `team2-vm`, us-east1-b; `/home/macstudio/ittem-e2e-baseline-20261107`, port 18096, Tailnet HTTPS 10443 | **Read-only observation**, manifest/plan/offline local test only. Actual A deployment needs separate approval |
| B | `/home/macstudio/ittem-bp18-product-completion-20261111`, 18100/10500 | NO CHANGES |
| Protected Live | 18088 | NO CHANGES |
| Historical protected QA | 18095 | NO CHANGES |
| Official GitHub `dev`, Owner PRs; previous Jobs/Artifacts/Attempts | Shared or owner-controlled | NO CHANGES |

C-A2 observed older deployed A SHA `9879eb0f85747312a224ecd898aaff84d834590b` on 2026-11-09 18:29 KST. This **does not** prove the current live state. An A3 independent read-only GCP lookup using `gcloud compute instances describe` was denied due to expired/re-authentication-required credentials. We did not reauthenticate or modify any VM, DB, service or secret. **Current GCP A SHA, active processes, port/SSL/SSO, three ledgers, artifacts: NOT_AUDITED in A3.**

## 2. A-only source manifest & inspection commands

Run only from approved A worktree (no root-level deletion or git checkout):

```bash
A='/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
cd "$A"
git rev-parse HEAD 'HEAD^{tree}'
git status --porcelain
python3 scripts/a3_track_a_guarded_readiness.py
```

The read-only manifest returns commit/tree, clean state, approved Owner priority, single-image contract, lockfile SHA-256, current Python version and explicit `PAID_WORKER=HOLD`. **Generate a fresh manifest only after final commit**; previous snapshots are not deploy SHA evidence. It never contains provider credentials, user assets, Actor identities, raw jobs or receipts.

On the future separately approved GCP A read-only operator session (and ONLY A), `--runtime-root /home/macstudio/ittem-e2e-baseline-20261107` inspects `repo/SOURCE_SHA.txt`, and three existing SQLite DBs in `runtime/live/` via `mode=ro` and `query_only=ON`, returning counts by non-sensitive state. Missing/corrupt DB → HOLD; mismatched deployed SHA → HOLD; unpriced receipts → NOT externally reconciled; paid-worker remains HOLD. The script does **not** initialize/migrate/reconcile any database, write files, restart a service or contact the provider.

Lock/hash inputs: `configs/requirements-serving-gcp.lock.txt`, `demo_staging/requirements-live-extra.txt`, `app/package-lock.json`, `tests/browser-harness/package-lock.json`, `tests/image_generation/requirements.txt`. Runtime manifests and tests must be tied to the same Git commit/tree and exact dependency set.

## 3. Pre-deployment gates (all must be separately verified/approved)

1. Exact A source SHA/tree & lock hashes, no uncommitted delta, locally passed full Python/BP17 concurrent proof/A2 26/FE57/PM six fixtures/lint/build. Independent C-A differential acceptance recorded.
2. A-only isolated process/network/storage identity; no access to B/Live/QA DB, artifact, auth-cookie/secret or port. Existing A deployment left untouched until separate deployment permission. Track-specific `__Host-` cookie audience and signed Tailnet host/port validation; externally accessible unauthenticated direct API denied. HTTP health 200 **is not signed SSO acceptance**.
3. Runtime `SOURCE_SHA.txt`, actual process build SHA, static frontend bundle hash, worker source, Python and Node lock consistency; **read-only** state/count snapshots and backups planning for A-only Job, SQLite/WAL, artifacts, attempt and receipt. No actual migration/backup/restore performed in A3.
4. Worker remains disabled in QA configuration: `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_LIVE_EXECUTION_APPROVED=NO`, `IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO`, no worker-only API key in web process. Fixture route may be used only through separate loopback-only, explicit QA gate, never on protected 18095. On a future paid candidate, `policy_from_env` independently requires execution permit, readiness, key, `MONITOR_ONLY`, Actor allowlist; those flags are **not** permission by themselves.
5. A2 runtime gates: live allowlist and B0 Job ownership, Stage/Queue context and signed Actor/SSO; Queue/Cost/Image Attempt triple recovery; LIVE-only Vision/Research/Copy checkpoints; immutable Copy/Review/Generation/Approval SHA and actual rules/code/template policy hash; CAS Prompt→Image binding. Revoked Actor after HTTP transmission cannot retroactively cancel that Provider charge.
6. Existing Legacy LIVE approvals missing `live_copy_policy_bindings` must be **HOLD**, not default-approved/migrated. Require Owner/PM manual re-review and a fresh versioned approval, with original receipts/artifacts unchanged. Do not silently patch old LIVE rows or bypass CAS.
7. Six **fixture-only** modes×ratios, each one candidate per request; 2/3/4 mixed gallery never exposed. Compare dimensions, PNG bytes/SHA, UTF-8 Caption, Actor ACL, reject→explicit one regenerate, GET-only resume, no billed POST.
8. Separate pre-approval for GCP A staging rollout, signed SSO/HTTPS acceptance, actual rollback exercise, any schema migration, real model entitlements, hard provider spend cap/usage receipt and real six-case Provider E2E. No direct protected QA18095 or Live18088 deployment.

## 4. Planned A-only change and rollback sequence (NOT EXECUTED)

**Preflight (read-only):** C/PM accept code SHA and manifest. Record existing A process/port/health, repo `SOURCE_SHA.txt`, Tailnet host certificate identity, DB schema version/count/status, exact Artifact/Receipt SHA, filesystem ACLs and access controls. Do not collect raw PII or keys. If any mismatch or unknown, HOLD.

**Approval-gated candidate rollout:** Separate immutable A-only candidate directory and independently isolated DB/runtime, worker disabled and no billable keys. Deploy exactly signed manifest SHA, then validate 401/403/404/409, Signed SSO, full approved copy/review/prompt binding, GET-only recovery, six fixtures and deployment/source hash. Any use of existing A runtime DB or live listener replacement requires explicit deployment approval; code in A3 does not do so.

**Fail / rollback:** Immediately keep Worker and paid queue disabled, stop further candidate exposure **only under approved operational change**, revert A candidate process/router to prior approved code without overwriting active SQLite DBs, preserving new and legacy data in immutable backup. Never reset/migrate down A2 binding tables or delete/zero Queue/Cost/Image Attempt/Artifacts/Receipt to restore a green indicator. Recheck SOURCE_SHA, Tailnet SSO, API 401/404, health plus end-to-end canary, checksum and source/receipt integrity. If A2 schema and prior runtime are incompatible, maintain HOLD and choose new isolated copy rather than silently rolling back DB history. GCP B/Live/QA and official `dev` untouched.

## 5. Billing tri-ledger state and conservative transition contract

| Ledger / state | Semantics | Allowed automatic next action |
|---|---|---|
| Queue `QUEUED` | Not yet claimed; not proof that no provider attempt exists | Claim only when **all three ledgers** unambiguous and A2 authority passes |
| Queue `RUNNING` | Claimed task; may have dispatched a paid call | On crash: `BILLING_UNKNOWN`, no auto-requeue |
| Cost `RESERVED` | Record created, no confirmed dispatch; crash gap may precede intent | **HOLD** pending manual incident review; no reset or automatic retry |
| Cost `DISPATCHED` | Intent durably written **before** network I/O; actual send/charge uncertain | Restart reconciles to `BILLING_UNKNOWN`; HOLD |
| Cost `BILLING_UNKNOWN` | Billing or result cannot be proved | HOLD all new LIVE work, preserve IDs and original rows |
| Cost `SUCCEEDED_USAGE_UNPRICED` | Provider returned response+usage; **actual charge unknown** and receipt preserved | Never treat as USD 0; external invoice reconciliation required |
| Image Owner `submitting`/`failed`/`unknown` | Own independent provider transport/attempt may be charged | HOLD until human evidence resolves, even if CostLedger seems clean |
| Queue `SUCCEEDED` + Cost usage receipt | Logical stage completion, not proof actual invoice charge | Check artifact/receipt/context before any later stage; no repeated billed POST |

Unpriced usage, declined/unknown attempts, delayed external billing and shared team usage can defeat a money cap built only from local `RESERVED` rows. **Current `MONITOR_ONLY` sets monetary reservation to 0 micro-USD and does not enforce a dollar stop threshold or a reliable shared-account charge cap.** The historical 10/26 `$10` policy is not proof of a currently effective provider hard limit. We must not claim budget enforcement or real-provider readiness from this ledger alone.

## 6. Incident response / HOLD release contract

- Capture *references, not secrets*: Track A Source SHA+Tree, isolated runtime/build, UTC incident ID, Actor (in restricted incident record only), Job, Queue Task ID/Stage/Context SHA, Cost Attempt ID/status/time, Image Owner Attempt+Provider Response IDs, Usage receipt SHA, candidate/final file SHA and immutable user approval/generation/policy binding.
- Provider evidence: finance/PM verifies correct OpenAI project/key, current provider statement or API usage/invoice period, pending charges and shared account spend, amount **actually billed** versus provider reported token/usage, unsettled cases, delays and disputed charges. Provider dashboard delay must be treated as uncertainty, not zero.
- Require explicitly approved remaining team spending budget, provider-side project hard caps/alerts verified (if offered), **separate worker key**, per-request permitted model/cost bounds, actual spend reconciliation and conservative unresolved-account reserve. If instant hard cap cannot be proven, **paid activation remains HOLD**. Monitoring-only does not establish a limit.
- Human decision register: Incident ID; exact 3-ledger observed status; raw evidence available in restricted source; full owner/PM/security/financing approvals; verified expected Source and SSO; reconciliation path; read-only snapshot hashes before; explicit one-time operator action after separate authorization. C independent security review before restoring paid dispatch. No automated release button in this A3 implementation.
- Never delete/replace Job, Attempt, Receipt or Artifact; never mark UNKNOWN as free/failed/succeeded by assumption; never resurrect stale approval; never automatically replay a failed, timed-out or dispatched billed request. If unclear, retain HOLD indefinitely pending investigation.
- A new authorized request must have independent, explicitly reviewed approval and attempt identity; historical ambiguous request remains unreplayed. An external paid HTTP request already in flight cannot be canceled retroactively by actor revocation.

## 7. Validation evidence and remaining classifications

- A3-1 BP17: **24/24 PASS** after `spawn` and `forkserver` parametrization, original `spawn` two-process race repeated **30/30 PASS**, subsequent 20 iterations × 2 methods = **40/40 PASS** on Mac Python 3.12; full Python **1010/1010 PASS**. Linux offline cached Python 3.13 container with `--network none` tested **30/30** atomic `renameat2(RENAME_NOREPLACE)` two-process races; **not** the full Pillow/SQLite application nor GCP Linux 3.12.
- A3-2/A3-3: `scripts/a3_track_a_guarded_readiness.py` + `tests/demo_live/test_a3_guarded_readiness.py` **13/13 PASS**, checks source/dependency hashes and four independent issue classes including missing/corrupt ledger and no paid unlock. GCP current read-only check: **NOT_AUDITED** because `gcloud` requires reauthentication; C-A2 18:29 historical evidence is only a prior observation.
- A2.1–A2.4 accepted source unchanged. Re-run all relevant regressions if A3 impacts tests or code.
- Evidence levels: `CODE_IMPL`, `LOCAL_TEST_PASS`, `LINUX_PRIMITIVE_ONLY`, `CURRENT_GCP_NOT_AUDITED`, `SIGNED_SSO_NOT_AUDITED`, `REAL_PROVIDER_E2E_NOT_AUDITED`, `INVOICE_NOT_AUDITED`. Release Master F01–F20/V01–V08/S01–S10 is **not** declared accepted.

**FINAL A3 operational verdict:** `A3_LOCAL_RELIABILITY_PASS / A3_GCP_GUARDED_DEPLOYMENT_READINESS_PLAN_ONLY / A3_BILLING_OPERATOR_RUNBOOK_DOCUMENTED / C_A3_DIFFERENTIAL_AUDIT_PENDING / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
