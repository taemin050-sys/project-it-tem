# IT-TEM P03 Track A — A5-1H actual GCP A-only nonbillable deployment

**2026-11-11 KST · Deployment performed, Worker OFF. NOT a full-feature team beta.**

## 1. C-A authority reconciliation

- Official C-A51FR1 independently ACCEPTED P1 SKU / Policy Epoch / Frozen Profile Decision SHA binding. Do not relitigate the accepted 1,395 Python / 61 React results.
- Per 2026-11-11 user / team correction, **existing GCP dev/test resources and already-approved paid API dev/test budgets are APPROVED**. Do not request duplicate approval for preapproved scope. No exact remaining USD balance or exact model tariff was independently confirmed here.
- Real technical execution checks and Owner/PM legal SKU / MPO / Signed Profile approvals are *separate* hard requirements.
- Github **Issue #38**, owner/FE/PM assignees, received FE Owner response proposing **REJECT_MULTIFRAME_V1 for current Beta**; final Image Owner / PM policy approval remains pending. Corrections: [existing budget/scope clarification](https://github.com/taemin050-sys/project-it-tem/issues/38#issuecomment-6785390660), [exact FE code paths and v2 preservation](https://github.com/taemin050-sys/project-it-tem/issues/38#issuecomment-6785568428). FE Owner response highlights **MPO must be checked before any browser downscale/re-encode**. A5-1E candidate already checks pre-resize and server decoded-container; not an official Owner/FE merged release.

## 2. Real GCP deployment — what was actually executed

Target: existing GCP VM team2-vm (project sprint-ai-chunk4-02, us-east1-b), reached via previously authorized SSH key and verified known-host key. Gcloud OAuth token was expired, but read-only and limited existing-scope SSH operations were possible without gcloud login.

A-only root: /home/macstudio/ittem-a51h-isolated-nonbillable-20261111 (mode 0700).

- **Deployed executable source HEAD:** 73ff3708c355df51add0c37caa57a984027b4c21
- **Git tree:** f8bf3bd3ddfdf70c4add16e2f611ee4f1660fed8
- Git archive transported and **all 878 tracked files verified on GCP by SHA-256** against the Mac Studio tracked-source manifest.
- Existing built React app/dist transported separately; index and backend worker source SHA in verified JSON.
- Created a dedicated Python virtual environment. Installed configs/requirements-serving-gcp.lock.txt as currently committed, with **additional isolated runtime pin fonttools==4.65.0** because the current GCP lock omits fonttools imported in src/image_generation/composition.py. This is an **identified deployment dependency lock gap**, not a claimed accepted final dependency baseline; official pinned lock and reproducible build require correction/differential verification before beta promotion.
- Created only new isolated candidate runtime and empty invite registry; **no existing A/B/QA/Live DB modified**. No Owner paid Provider Attempt DB initialized, no real customer uploads or proprietary photos copied.
- Started dedicated uvicorn PID (see evidence) bound **exclusively to 127.0.0.1:18561**, one process, no public network or Tailnet Serve endpoint.
- Started with clean isolated environment containing **IT_TEM_LIVE_ENABLED=NO, IT_TEM_LIVE_EXECUTION_APPROVED=NO, IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO, IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=NO, IT_TEM_A51E_SIGNED_BETA_INTAKE=NO** and no Provider API keys.
- Actual HTTP checks: **GET /health 200**, **GET / 200**, **GET /demo/api/session without credentials 401**, **POST /api/v1/jobs without credentials 401**. Current GCP 18096(A), 18088(protected Live), 18095(QA), 18100(B) all returned **HTTP 200** on health check and were not altered.
- Historic active A Source SHA still **9879eb0f85747312a224ecd898aaff84d834590b**. Existing GCP A routing / services remain untouched. No application data migrated.

**Audit proof:**
- docs/integration/evidence/A51H_20261111/A51H_ACTUAL_GCP_WORKER_OFF_DEPLOYMENT_SMOKE.json
- docs/integration/evidence/A51H_20261111/A51H_GCP_TRANSPORT_TRACKED_SOURCE_878_SHA256.txt
- docs/integration/evidence/A51H_20261111/A51H_TRANSPORT_AND_SMOKE_SHA256_MANIFEST.txt

These show actual GCP process and network observations rather than a synthetic readiness assertion. Frontend bundle from deployed app/dist may have a separately pinned build label; the exact frontend index SHA is evidence, **do not infer signed production frontend readiness from the source HEAD**.

## 3. Release hard gates and next critical integration

| Gate | Actual status |
|---|---|
| Already accepted A5-1F-R1 code | C-A ACCEPTED; no executable changes in this work unit |
| Existing GCP dev/test budget authorization | APPROVED by team/user |
| Existing paid API dev/test budget authorization | APPROVED by team/user |
| Actual isolated GCP A candidate nonbillable health/ACL smoke | **PASS (127.0.0.1 only)** |
| Executable Git archive 878/878 SHA | **PASS** |
| Actual Signed Tailscale Serve SSO and Actor/Job E2E | **TECHNICAL_NOT_READY, not audited on this new GCP candidate** |
| Actual Cost HARD_CAP, PM signed numeric cap, Queue/Cost/Owner Attempt reconciliation | **TECHNICAL_NOT_READY**; worker still disabled |
| Real signed SKU rights, mask, font, complete Provider-permitted Profile and MPO policy | **PRODUCT_CONTRACT_PENDING** |
| GCP real Provider 6 independent single-image jobs | **0/6** |
| GCP full frontend/research/copy/image end-to-end + team URL + UAT | **NOT_AUDITED** |
| Full-feature beta/team UAT release | **HOLD** |

### Engineering next actions (not permission bottlenecks)

1. Eliminate serving lock dependency drift with C-A differential verification; do not use the locally installed fonttools overlay as proof of a hermetic final build.
2. Bind an **actual A-only Signed Tailnet HTTPS gateway and persistent Actor registry** to the isolated candidate without replacing existing 10443(A) or 10500(B) routing. Preserve per-job ACL, no legacy fallback, no public exposure. Existing A51E requires a test-only root guard: do not lift it through an environment toggle; implement/review a new scoped beta activation contract.
3. Bring separate new A-only preinitialized Upload/Queue/Cost/Owner Provider Attempt ledgers and actual Mandatory HARD_CAP under the existing approved project budget; reconcile unresolved attempts and receipts before any billable worker startup.
4. Apply formally authorized Image Owner/PM MPO policy, actual product rights and profile/font/mask signatures. **Never transmit the provided 24 unlicensed product candidates to a real Provider**.
5. Validate actual real-provider 6 separate one-candidate jobs and team web UAT; preserve the prior A/B/Live/QA and v2 Job/Approval/Receipt/Artifact.

**No new GCP compute instance, GCP volume or network ACL; no paid Provider call; no existing production data or router modification.** This is real isolated GCP execution, **not** FULL_FEATURE_BETA_READY_FOR_TEAM_UAT.
