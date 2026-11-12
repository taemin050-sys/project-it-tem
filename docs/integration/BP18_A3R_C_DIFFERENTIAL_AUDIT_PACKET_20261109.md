# IT-TEM P03 Track A — A3R Targeted Readiness Preflight Hardening

Date: 2026-11-09 KST. Owner: Track A developer; **self-verification only**. This is a submission to C-A for independent differential re-audit, **not** a C acceptance or permission for actual QA deployment.

## 0. Baseline / provenance

- Approved A Worktree: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`.
- Branch: `integration/bp18-baseline-e2e-20261111`.
- **Starting HEAD:** `d75433e9bc2d15b398646b530b8b68ff6174bf26`.
- **Starting Tree:** `15af2ae8580e0c8de64728e802caa9e2f529f203`; CLEAN.
- C-A3 independently accepted A3-1 Reliability: `C_A3_LOCAL_RELIABILITY_ACCEPTED`. A2 four safety gates remain `C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE`. Neither code nor acceptance was reopened.
- **C-A3 original audit:** `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A3_DIFFERENTIAL_AUDIT_20261109_1921KST.md`, SHA-256 `f9efceec674bb989e08682eb2bd7a7ac7a2d5e5f7da503c1f94867bd1d2545b6`.
- **Original auditor-authored adversarial script:** `audit/track-a/evidence/C_A3_20261109_1920/C_A3_preflight_adversarial.py`, SHA-256 `ead6e8beca594e8dcfde358a41c244ffdce5427d250591a82fd8fe6b71190cc6`; unchanged before/after both replay runs.
- **Final HEAD/Tree:** verify directly via `git rev-parse HEAD 'HEAD^{tree}'` after this report is committed; do not infer deployed GCP source from local Git.

## 1. BEFORE versus AFTER — independently grounded repro and narrow repair

| Finding | Old fixed d754 C-A3 adversarial result | A3R developer repro/repair result | Gate |
|---|---|---|---|
| **A3-P1-01 A→B subtree symlink** | C's fake A `runtime/live` pointed at temp fake B; tool read fake-B state counts and returned `PASS_WITH_NOTE`. `PROTECTED_B_SYMLINK_READ_NOT_REJECTED=True` | CLI operational root must be **exactly** `/home/macstudio/ittem-e2e-baseline-20261107`; test fixture mode is Python-only explicit `fixture_mode=True`. Ancestor-by-ancestor `O_DIRECTORY|O_NOFOLLOW`, pinned root/child FD, regular DB `O_NOFOLLOW`, `/dev/fd` read-only sqlite, directory/file inode postflight. Intermediate and final symlinks fail closed. C's fake B reads now empty; `PROTECTED_B_SYMLINK_READ_NOT_REJECTED=False` | Developer `PASS` / C pending |
| **A3-P1-02 unknown states** | C changed three state columns to `UNRECOGNIZED_STATE`; old tool returned `PASS_WITH_NOTE` each | Worker/Queue/Cost/Image enum whitelist and required schema columns, Queue mode/stage, cost `billing_unknown` type, unpriced usage receipt presence, image result presence. All unknown/NULL/wrongly typed states, missing schema, or uncertain billing => `HOLD`; no auto replay/reset | Developer `PASS` / C pending |
| **A3-P2-03 missing proof/lock hash** | Old source gate still `PASS` for missing lock and missing evidence | 5 required Lock and 6 mandatory evidence files must be present, regular, unsymlinked and byte-identical to `HEAD:<relpath>` Git blob, with SHA-256. Missing, tampered, uncommitted, mismatched Tree/Branch, or dirty worktree => `source_integrity_gate=HOLD` | Developer `PASS` / C pending |

**Before-repair replay:** `docs/integration/evidence/A3R_20261109/A3R_BEFORE_C_A3_ADVERSARIAL.log` executes the **actual d754 Git blob** via isolated `/private/tmp` Python module, using C's original synthetic attack script; with clean Git state simulated solely for the historical module because today's legitimate A workspace has developer changes. Reproduces all three unsafe classifications and original symlink B fixture read. No actual B resource.

**After-repair replay:** `docs/integration/evidence/A3R_20261109/A3R_AFTER_C_A3_ADVERSARIAL.log` executes the unchanged C script with **only** the obsolete implicit test fixture API adapted to explicit `fixture_mode=True` through a runtime wrapper (no auditor file edits). It reports `DEVIATIONS []` and fake protected-B symlink read rejected. **Qualification:** C's old toy SQLite schemas have fewer columns than the new canonical contract, so its nominal baseline now intentionally HOLDs; independent new full-schema fixtures in `tests/demo_live/test_a3_guarded_readiness.py` verify positive `PASS_WITH_NOTE` ledger-only inspection separately.

## 2. Scope and exact file changes

- **Production preflight script only:** `scripts/a3_track_a_guarded_readiness.py`. Does NOT create DBs, sidecars, receipts, jobs, Source SHA markers or enable a Worker.
- **Test only:** `tests/demo_live/test_a3_guarded_readiness.py`, existing 13 tests retained and strengthened + 31 additional parameterized test cases = **44**.
- **Runbook only:** `docs/integration/BP18_A3_GUARDED_DEPLOYMENT_BILLING_RUNBOOK_20261109.md`, with GCP C-A3 actual observation, safe FD/WAL interpretation and four independent readiness/authorization gates.
- **New:** this A3R audit report and immutable developer test/replay logs in `docs/integration/evidence/A3R_20261109/`.
- **Unchanged:** `demo_staging/live/*`, `demo_staging/live_safety.py`, `src/text_generation/*`, `src/image_generation/*`, `app/*`, BP17 process/concurrency test and implementation, all prior C audit evidence, official `dev`, Track B, any GCP A/B/Live/QA service or operating DB.

## 3. TOCTOU and SQLite WAL policy

The readonly checker opens every path component using `dir_fd` and `O_NOFOLLOW`; a transient rename/symlink may produce HOLD, but cannot change the pinned SQLite inode read to the linked fake-B inode. After reading, the checker re-opens components with nofollow to compare parent/file device and inode identity. No arbitrary `Path.resolve` of untrusted runtime children is used.

For SQLite with **active `-wal` or `-shm`**, the inspector records SHA-256 before and after but deliberately **HOLDs without opening SQLite**: immutable mode otherwise ignores WAL, and normal read-only SQLite may alter SHM. For a DB with no sidecars, it opens only an existing O_RDONLY FD via `file:/dev/fd/N?mode=ro&immutable=1`, sets `PRAGMA query_only=ON`, validates required schema/data, and checks DB bytes, sidecars and inode identity afterward. A quiesced consistent A-only backup/snapshot and OS-level authorization is a **separate approved operation**. Race checks are point-in-time and do not constitute a proof against an adversary with root-level filesystem mutation privileges. All external invoice/budget controls remain unverified.

New fixture WAL test creates a valid **temporary** WAL and SHM via SQLite, with immutable fake Receipt in same fixture root, and compares SHA-256 of **all DB/WAL/SHM/Receipt files before vs after**; no operational files touched. Any active WAL => HOLD, unchanged byte hashes.

## 4. Local regression / evidence

| Test | Developer observation | Evidence |
|---|---|---|
| A3R readiness focused (13 old + 31 new) | **44/44 PASS**, exit 0 | Full Python log; repeatable `pytest tests/demo_live/test_a3_guarded_readiness.py` |
| Python entire repository | **1041/1041 PASS**, exit 0 | `A3R_FULL_PYTHON.log` |
| A2 C-owned original extra negatives | **7/7 PASS**, exit 0 | `A3R_C_A2_7_NEGATIVES.log`, original C SHA still unchanged |
| A3 Reliability / BP17 | Existing `spawn`/`forkserver` included in full Python, no source changes | `A3R_FULL_PYTHON.log` |
| React | **57/57 PASS**, exit 0 | `A3R_REACT.log` |
| Lint | **0 warnings/errors**, exit 0 | `A3R_LINT.log` |
| Build | **PASS**, exit 0 | `A3R_BUILD.log` |
| C-A3 original adversarial script before/after | Old unsafe reproduced; new synthetic fake-B read rejected; `DEVIATIONS []` | `A3R_BEFORE_C_A3_ADVERSARIAL.log`, `A3R_AFTER_C_A3_ADVERSARIAL.log` |
| Actual Provider POST / VM deployment / legacy DB edits | **0 / none / none** | Tool implementation and A-only change scope |

All test processes used Python3.12 local venv, no billable provider credentials, `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO`. C-A3 independent reproduction is **not** claimed for the new A3R snapshot.

## 5. Actual GCP A information and outstanding separate gates

Use only **C-A3's independently observed read-only SSH data as of 2026-11-09 19:21 KST** (A3R did not perform fresh GCP inspection):

- A `SOURCE_SHA.txt=9879eb0f85747312a224ecd898aaff84d834590b`, much older than A2/A3/A3R.
- Queue LIVE state entries 0, Cost Attempt entries 0; **NOT** proof of external provider zero charges.
- Expected Owner Image attempt DB path `runtime/live/owner_image/image_attempts.sqlite` **MISSING**. The stricter Readiness script must HOLD, not initialize or migrate it.
- A port 18096 `/health` HTTP 200; **Signed SSO NOT_AUDITED**.
- **QA deployment readiness HOLD** until separate A-only read-only runtime inspection, signed SSO, complete source/dep/DB schema and protected resource isolation, independently approved worker-disabled A-only QA candidate and rollback drill. Protected QA18095 and Live18088 are NEVER A3R deployment targets.
- **Paid Worker Authorization HOLD**, irrespective of local source or clean ledger, until provider entitlements, budget hard cap, unpriced receipt and actual invoice reconciliation, incident HOLD release and C/PM approvals.
- Existing legacy LIVE approvals without pinned new policy SHA require manual re-review; no automatic migration, backfill or approval reuse.

## 6. F/V/S38 differential disposition

- `F01/S01/S02`: Local root/SSO boundary stronger at preflight; **actual Signed SSO and GCP isolation NOT_AUDITED**.
- `F19/S04/S09/S10`: Missing/corrupt/unknown State and billing uncertainty HOLD, unpriced usage is **not cost 0**; **live 3-ledger, hard budget, actual invoices HOLD**.
- `F20/S05/S06`: Source SHA/Tree/Git-proof manifest strict; old A GCP SHA and missing ledger -> **QA DEPLOYMENT HOLD**, rollback rehearsal not executed.
- `F12/F13/F14/F16/F17/S03`: A2 source unchanged, existing PM one-candidate and CAS Python regressions pass; **real provider six-case E2E and user acceptance HOLD**.
- `F02–F11/F15/F18/V01–V08/S07/S08`: No new approval or production evidence; prior documented evidence retained but **NOT AUDITED by A3R**, product release remains HOLD. Avoid upgrading user/product gates from these targeted test results.

## 7. C-A3R requested independent acceptance gates

1. Pin new HEAD/Tree and audit only A3R script+tests+runbook+packet/evidence. Ensure accepted A2 and A3-1 code SHAs unchanged.
2. Independently repeat C-A3 fake A→fake B directory+DB symlink attacks, plus real-structure fixture: **no real B access**, no symlink follow, code returns HOLD.
3. Independently insert unknown/NULL/wrong-type Queue/Cost/Image State and schema drift; all HOLD. Test active WAL/SHM+Receipt files unchanged.
4. Try missing/forged Lock and proof logs with clean-version simulation: source gate HOLD. Verify valid clean committed HEAD and exact Git blobs produce local source gate PASS, without implying deployed A.
5. Confirm split gates `source_integrity`, `ledger_integrity`, `qa_deployment_readiness`, `paid_worker_authorization`. QA and paid worker remain HOLD irrespective of successful local preflight.
6. Re-run C-owned 7 negatives, A2 targeted 26, BP17, Python full, React lint/build as necessary; no Provider/VM/GitHub/Track B/Live/QA writes.
7. Request any GCP A-only isolated deployment **separately**, with explicit approved source SHA/Tree, worker disabled, SSO, three ledgers, legacy approval hold and rollback plan. Do not unilaterally activate paid Worker.

**Developer disposition:** `A3R_TARGETED_PREFLIGHT_DEVELOPER_VALIDATED / C_A3R_DIFFERENTIAL_AUDIT_PENDING / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
