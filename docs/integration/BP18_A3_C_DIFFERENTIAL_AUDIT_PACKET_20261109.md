# IT-TEM P03 — A3 Reliability / Guarded Deployment / Billing — C-A Differential Audit Packet

**Date:** 2026-11-09 KST. **Authority:** Track A developer self-validation; **C-A differential audit NOT YET conducted**. Status: `A3_LOCAL_RELIABILITY_PASS / GCP_A_QA_DEPLOYMENT_HOLD / PAID_WORKER_HOLD / C_A3_AUDIT_PENDING / NOT_RELEASE_READY`.

## 1. Immutable code boundaries and commits

- A-only canonical Worktree: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`, Branch `integration/bp18-baseline-e2e-20261111`.
- **Accepted A2 input:** `d34d62b64fc4e50d348a16a9644a38a5c016d16a` / Tree `fa5efbf04056a276bcec6fa8ed5872777067003f`, originally CLEAN.
- **C accepted A2:** `audit/track-a/IT_TEM_P03_C_A2_INDEPENDENT_P0_REPLAY_AUDIT_20261109_1829KST.md` => `C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE`. No A2 code re-architecture, no Phase4 Migration repeat.
- A3-1 fixed concurrent publication harness and Linux primitive probe: `bdd32504b94077d96545ff2d327e4e413a953ab3` / Tree `1c9fa984a4cf7b456af615b6706aa53d8b1d6dee`.
- A3-2/A3-3 read-only A manifest, tri-ledger preflight tests and operator runbook: `79be0b9e06c540a1357b8cd6b7be90191dd0a3bc` / Tree `bce126bbcfbb3e90fafe89e5a2085a25e2782741`.
- A3-4 code-and-evidence review pin after dual-method stress: `173ac440050cd2e9d03f984913be065ccc737c0b` / Tree `45d06113c01b3fa54ec90ab16108b2d7e9b74de1`.
- **Final audit-packet HEAD** is whichever commit contains this report; determine fresh via `git rev-parse HEAD 'HEAD^{tree}'` after commit. Manifest generator returns the *actual* clean HEAD; do not reuse precommit manifest as the deployed build.
- **A3 changed no existing serving runtime, HTTP, security, Owner Text, Owner Image, or FE application source.** Existing PM Owner priority FE #26 > Text #27 > Image #24, one image per request × two modes × three ratios remain unchanged.
- A/B/GCP, protected Live18088, historical QA18095, official GitHub `dev`, Owner PRs, existing operational Job/DB/Artifact/Receipt/Provider keys: **not written**. Actual Provider POSTs: **0**.

## 2. A3-1 — failure mechanism, correction, strengthened concurrency evidence

- **Before:** A2 C-A faulthandler shows one or more **macOS Python 3.12.2** `multiprocessing.get_context("fork")` children segmentation fault at `scripts/bp17_shared_ad_minimal_export.py:35`, during opening SQLite in `read_db()`. The parent failed on child exit code. Source C immutable evidence: `audit/track-a/evidence/C_A2_20261109_1829/C_A2_known_fork_case.log`. This showed a child process crash, **not** a confirmed atomic rename collision, incomplete output or overwritten destination.
- **Mechanism established:** the test forked an already populated pytest process with imported Pillow native extension and prior SQLite setup, inheriting in-process native/interpreter state into the children. An exact single native-library/Apple runtime root cause remains **unproven** without lower-level native debugging. This hazardous test process start path was replaced, *not* the production no-replace syscall.
- **After:** `tests/demo_live/test_bp17_shared_minimal_export.py` defines a module-level spawn-safe worker which opens **new** SQLite connections from a clean child interpreter, re-establishes its own fixture-only allowlist and synchronizes two real contenders at the existing `projection._publish_no_replace` using Barrier. Parameterized test uses **both `spawn` and `forkserver`**, which do not fork the initialized pytest parent. No delay inflation, xfail, skipping or assertion weakening. Still requires **exactly one PUBLISHED and exactly one EXISTS**, both exit code 0; PNG SHA = output manifest SHA; no leaked stage; no output replacement.
- **Observed:** full BP17 module **24/24 PASS**; spawn real 2-process race 30 iterations **30/30 PASS**; two methods ×20 runs **40/40 PASS**; entire Python 3.12 repository **1010/1010 PASS**, exit 0.
- **Linux comparator:** cached local `python:3.13.12-slim-bookworm`, Docker `--network none --pull never --read-only --tmpfs /tmp` and bind-mounted A source **read-only**. `scripts/a3_linux_atomic_noreplace_probe.py --rounds 30` executed genuine Linux `renameat2(RENAME_NOREPLACE)`: one winner/one EXISTS, existing output immutable, no partial/orphan stage, **30/30 PASS**. This is a **kernel-primitive test only**, not the complete PIL/SQLite BP17 app nor deployed GCP Python3.12. Exact Linux production impact remains `NOT_AUDITED`; do not claim it eliminated all native crash possibilities.

## 3. A3-2 — isolated GCP A candidate readiness

- **New:** `scripts/a3_track_a_guarded_readiness.py` prints a deterministic read-only build/source manifest (git SHA/Tree/clean, dependencies lock SHA-256, policy and schema contracts, evidence log SHA), and optionally inspects **only A runtime** `ittem-e2e-baseline-20261107`: its deployed `SOURCE_SHA.txt` and three SQLite ledgers via `mode=ro`, `query_only=ON`. No secrets, raw Actor/Job text or receipt payloads; no service start, migration, remote write, paid POST or rollback operation. `PAID_WORKER` is always `HOLD`.
- **Local manifest after A3 code commit 173ac44:** Branch matches A, `source_gate=PASS`, 5/5 dependency lockfile hashes present, 6/6 evidence-log SHA-256 present, exact source `173ac440050cd2e9d03f984913be065ccc737c0b`, Tree `45d06113c01b3fa54ec90ab16108b2d7e9b74de1`. Re-run for final report HEAD. This is **local source readiness only**, not a deployed GCP manifest.
- **GCP read-only attempt:** `gcloud compute instances describe team2-vm ...` returned **reauthentication required**; operator did not reauthenticate and did not touch GCP. Current GCP SHA/process/storage/SSO/port/Artifact checks **NOT_AUDITED**. C-A2's 18:29 historical read-only observation was A SHA `9879eb0...`, before A2/A3, but must not be presented as the new live state.
- **Runbook:** `docs/integration/BP18_A3_GUARDED_DEPLOYMENT_BILLING_RUNBOOK_20261109.md` defines source/build/SSO/Actor/Stage/Prompt/Legacy approval, six offline mode×ratio, A-only canary, separate deployment permission, immutable backup and rollback safety. **No actual A QA deployment**; protected QA18095/Live18088 are not destinations.
- **Known blocking gate:** Legacy LIVE Approval without `live_copy_policy_bindings` must fail closed and be re-reviewed. New code has not been deployed, and old A GCP schema cannot be presumed compatible. Signed Tailnet SSO and true deployment SHA are separate audit gates.

## 4. A3-3 — budgets, 3 ledgers, external cost and human HOLD policy

- Existing A2 C-accepted Worker/Queue/CostLedger safety code unchanged. Local read-only checker verifies Queue `RUNNING/BILLING_UNKNOWN`, Cost `RESERVED/DISPATCHED/BILLING_UNKNOWN`, Owner Image `submitting/failed/unknown`, missing/corrupt DB, source SHA drift. All uncertain cases result **HOLD**; no auto-reenqueue, no unsafe DB repair.
- `SUCCEEDED_USAGE_UNPRICED` is a confirmed usage response **without a confirmed USD charge**. It is never counted as a zero-dollar bill. `MONITOR_ONLY` currently sets estimated monetary reservation to zero and **does not enforce a real USD budget**, global shared-account usage, or future invoice reconciliation. This is a **hard blocker** for paid activation, not a solved billing cap.
- Manual incident/release runbook requires operator to reconcile Queue Task/Actor/Job/Stage/Context, Cost Attempt+Receipt, Image Owner Provider Attempt and response ID, invoice/statement+shared-account spend, authorized current PM/finance budget and limits, source+SSO. Unclear cases preserve HOLD. Records are immutable: no reset, fabricated cost, automatic retry, direct paid release control or retroactive cancellation of an already-sent Provider HTTP request.
- **Local validation:** `tests/demo_live/test_a3_guarded_readiness.py` **13/13 PASS**, with before/after DB file SHA unchanged, uncertain states and corrupt/missing ledgers held, old source SHA rejected, B/Live/QA path invalid. This is simulated isolated SQLite, **not** actual current GCP tri-ledger or external provider invoice evidence.

## 5. A3-4 validation and exact retained evidence

| Test / evidence | Actual observation | Gate |
|---|---|---|
| Full Python `pytest -q tests` | **1010 passed**, exit=0, no skip/xfail | `PASS` LOCAL |
| BP17 module | **24 passed** (`spawn` + `forkserver`) | `PASS` LOCAL |
| Isolated Mac two-process stress | Spawn 30/30; both methods 40/40 | `PASS` LOCAL |
| Linux atomic primitive | **30/30**, offline local cached Docker; full app not installed there | `PASS_WITH_NOTE` |
| A2 Worker+Prompt safety | Existing 26 included in full regression, unchanged source | `PASS` LOCAL / C-A2 previously accepted |
| C-A authored adversarial tests | **7/7 PASS** separately executed against current A code; original C file SHA `13395f2eadc219907d93dc1f6a6be9ee3497480965087c5639f459156535c4d4` matches C `SHA256_MANIFEST.txt` | `PASS` rerun; fresh C-A3 audit pending |
| PM one-image / 2 modes / 3 ratios | Existing tests included in full Python/React; A3 modifies no UI/API/Worker sources | `PASS_WITH_NOTE` local |
| A3 read-only preflight negatives | **13/13 PASS**, no paid unlock | `PASS` LOCAL |
| React full | **57/57 PASS** | `PASS` LOCAL |
| React lint / build | **0 warnings/errors / PASS** | `PASS` LOCAL |
| GCP A current source/SSO/rollback | Auth token failure; no deployment made | `NOT_AUDITED` / `HOLD` |
| External provider invoice/budget/model | No real Provider I/O, invoice or shared-account reconciliation | `NOT_AUDITED` / `HOLD` |

All A3 durable logs under `docs/integration/evidence/A3_20261109/` are committed. They include `A31_30x_real_process_race.log`, `A31_FULL_PYTHON.log`, `A31_LINUX_SYSCALL_30x.log`, `A32_GCP_READONLY_AUTH_BLOCKED.log`, `A33_READINESS_TEST.log`, `A34_20x_SPAWN_FORKSERVER_CONCURRENCY.log`, `A34_FULL_PYTHON_FINAL.log`, `A34_C_INDEPENDENT_NEGATIVES_REPLAY.log`, `A34_REACT_TEST.log`, `A34_REACT_LINT.log`, `A34_REACT_BUILD.log`. Tests ran with paid keys unset and `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO`.

## 6. Release Master F01–F20 / V01–V08 / S01–S10 — differential scope, not product acceptance

Evidence levels: `CODE_IMPL` ≠ `LOCAL_FIXTURE_PASS` ≠ `C_A3_ACCEPTED` ≠ `REAL_PROVIDER_E2E_PASS` ≠ `HUMAN_PM_OWNER_ACCEPTED` ≠ `RELEASE_DEPLOYED`.

| ID(s) | A3 impact / observed evidence | Product gate still required |
|---|---|---|
| F01 | No Auth source changed; C-A2 local Actor checks accepted | **NOT_AUDITED** live signed SSO, direct-port isolation |
| F02–F04 | Earlier photo/DTO/upload tests retained in Python/React | **NOT_AUDITED** actual multi-device production UAT |
| F05 | Source/Job resume tests unchanged, local regressions | **NOT_AUDITED** deployed source/GET-only browser UAT |
| F06–F08 | Text/VLM/Research/Copy fake/contract tests retained | **HOLD** real-model outputs and factual/copy quality |
| F09 | Regulatory policy SHA binding retained from A2 | **HOLD** actual 2-stage LLM compliance proof/human review |
| F10–F11 | Existing Copy revise/restore/policy tests retained | **HOLD** full real LLM review-policy handoff |
| F12–F14 | PM one candidate × two modes × three ratios Fixture tests retained | **HOLD** 6 real-model jobs, quality, PNG/Caption browser UAT |
| F15 | No typography/layout change | **HOLD** real CTA/9:16 PM policy |
| F16–F17 | Existing Image rejection/retry/PDF-free PNG/Caption SHA tests retained | **HOLD** real Provider/receipt/exports |
| F18 | BP17 shared-result projection concurrency **local PASS**; no new unauthorized sharing | **NOT_AUDITED** deployed team sharing/actor browser |
| F19 | Local queue/recovery tests and no auto paid POST maintained | **NOT_AUDITED** deployed error/restart UX |
| F20 | Manifest generator added; current GCP unreadable | **HOLD** actual deployed SHA/Bundled FE SHA |
| V01–V06 | No new generated imagery, layout or mobile testing | **HOLD** Owner/PM human ad quality, Korean accuracy, 360/390 browser |
| V07–V08 | No font license/regulatory decision changed | **HOLD** license and actual human compliance signoff |
| S01–S02 | A-only path checker and runbook; no GCP execution | **NOT_AUDITED** live isolation/signed SSO |
| S03–S04 | A2 accepted source unchanged; 26 regression and C7 recheck local | `PASS_WITH_NOTE` local only; **HOLD** actual paid runtime |
| S05–S06 | Rollback runbook, no A deployment or protected DB mutation | **HOLD** actual rollback drill/immutable source observation |
| S07 | Privacy-minimal BP17 projection local full tests PASS | **NOT_AUDITED** live data protection |
| S08 | No workload/real cost data collected | **NOT_AUDITED** real latency/CPU/GPU costs |
| S09 | A3 local safety regressions green | **HOLD** product release zero-P0 verification |
| S10 | Invoice/budget procedure documented; no provider actual charges | **HOLD** provider hard spend ceiling and reconciliation |

## 7. Residual risks and requested C-A gate

**Request C-A differential audit** of changed A3 files only plus impacted original tests. Do not repeat previous A2 acceptance as if unfinished. Required C evidence:

1. Independently replay concurrent publication at fixed A3 HEAD using both `spawn` and `forkserver` and compare historical C fork crash. Confirm exactly one publication, no output replacement/corruption/partial exposure and strict assertions. Explicitly classify native fork root cause uncertainty.
2. Verify that the C-A2 A2 P0 26 & protected C-A 7 regressions are unaffected and immutable C test SHA unchanged. Re-run PM one candidate, FE and Owner affected suites only as appropriate.
3. Inspect `a3_track_a_guarded_readiness.py` for read-only DB connections, root A-only validation, fail-closed corruption/no-schema, stale SOURCE_SHA, `SUCCEEDED_USAGE_UNPRICED` **not** equal to $0. Confirm the script cannot enable or bill a provider.
4. Check GCP latest actual A-only SOURCE_SHA/SSO/port/DB/backup under separately authorized read-only access. Until the auth blocker is resolved, mark as `NOT_AUDITED`; **never use protected QA18095 as A target**.
5. Review Release Master 38 states, manually signed incident HOLD clear, paid provider model entitlement, separate A-only deployment and rollback permission. Preserve A2 schema/legacy approval fail-closed, no A/B cross-write.
6. Report `A3_LOCAL_RELIABILITY_ACCEPTED` only if independently reproduced. Keep `A_GCP_PAID_WORKER_HOLD` and `NOT_RELEASE_READY` until separate deployment, budget/invoice, actual Provider and human gates.

**Developer status:** `A3_LOCAL_DEVELOPER_VALIDATED / C_A3_DIFFERENTIAL_AUDIT_PENDING / GCP_A_QA_DEPLOYMENT_NOT_EXECUTED / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
