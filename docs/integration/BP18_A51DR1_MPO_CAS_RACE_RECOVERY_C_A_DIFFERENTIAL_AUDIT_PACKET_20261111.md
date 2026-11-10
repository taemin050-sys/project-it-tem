# IT-TEM P03 Track A — A5-1D-R1 Concurrent MPO Token CAS Security Repair

**Developer differential C-A submission · 2026-11-11 KST**

## 0. Independently audited baseline and repaired source

- C-A5-1D independently audited baseline HEAD: c2ba3baa5bcf5211469fdf37da8ed7845130f4a0; Tree: c3effd3d11b6e7d30dee7842a4ab66978023738c.
- Previous C-A report: /Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A51D_REACT_MPO_B0_RACE_INDEPENDENT_AUDIT_20261111.md; SHA-256 c95b9c366038adf16a379a51bf4f662a5bd3d5415d06489a9363745f88ad42ac.
- Repaired executable HEAD: 7c5738b1a2adbe06a96a50a6851add7606a03eba; Tree: 4432c8ad77bb30b62a7044a1ca778cb91dc716c3.
- Exactly 3 changed implementation/test files:
  - demo_staging/live/a51d_mpo_fixture_bridge.py — separates all awaits and file validation from persistent CAS; Job creation and Actor claim become fail-closed.
  - demo_staging/live/a51dr1_mpo_selection_journal.py — NEW SQLite WAL durable actor/source/frame CAS journal with BEGIN IMMEDIATE and single-use tombstones.
  - tests/demo_live/test_a51dr1_mpo_concurrency_recovery.py — NEW concurrency/expiration/crash/error/multi-process regression tests.
- Existing FE #26, Text #27, Image #24, src/serving/job_api.py, existing B0 JobStore, v2 Approval/Receipt/Artifact and A/C v3 compositor were NOT modified. Official GitHub dev, Track B, GCP A, paid Provider, old application/Queue/Cost and Owner Provider Attempt ledgers were NOT modified.

**Requested independent C-A decision:** A51D-P1-01 CONCURRENT_MPO_TOKEN_DOUBLE_JOB_CREATION corrected in the local TEST_ONLY HTTP bridge. No authority to promote that bridge to real signed-SSO team beta is claimed.

## 1. Exact C-A independent negative test — before and after

The developer copied the original C-A independent attack C_A51D_independent_async_duplicate_token.py to /private/tmp, changed ONLY its hardcoded source directory to the repaired Track A checkout, and reexecuted the same simultaneous 2-request asyncio.Barrier attack. Original C-A evidence was never modified.

| Check | Vulnerable C-A original | R1 same attack against fixed code |
|---|---|---|
| Same Actor, MPO input, frame and confirmed token | 2 simultaneous POST | 2 simultaneous POST |
| HTTP responses | [201, 201] | **[201, 409]** |
| Distinct Job IDs published | **2** | **1** |
| Post-reservation token | In-memory, race-prone | SQLite COMMITTED to one Job ID; replay denied |
| C-A R1 verdict | Original P1 reproduced | Developer PASS; INDEPENDENT R1 AUDIT PENDING |

Before: docs/integration/evidence/A51DR1_20261111/R1_BEFORE_C_A51D_INDEPENDENT_DOUBLE_201.log

After: docs/integration/evidence/A51DR1_20261111/R1_AFTER_IDENTICAL_C_A51D_ATTACK_201_409.log

The original C-A script is independently preserved at /Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/evidence/C_A51D_20261111_0010/C_A51D_independent_async_duplicate_token.py.

## 2. R1 state machine, failure and concurrency boundary

| State | Meaning and invariant |
|---|---|
| PREVIEWED | Backend-issued random one-time token; SQLite stores only the token SHA, Actor, original MPO SHA, individual Preview SHA values, frame count and UTC expiry |
| CONFIRMED | Separate authenticated user-selection POST validates Actor, frame/index, exact Preview SHA and TTL under an atomic single-use CAS |
| Before reservation | Every asynchronous file read and all image validation complete OUTSIDE database transaction. A canonical request SHA binds Actor, every uploaded product/reference original-byte SHA, roles/indexes, and selected MPO frame identities |
| RESERVED | SQLite BEGIN IMMEDIATE makes a single atomic transaction over ALL MPO selections of one Job. Checks Actor/source/frame/Preview/TTL again and commits durable RESERVED BEFORE writing a B0 Job |
| COMMITTED | Existing B0 JobStore creates one Job and DemoLedger claims its Actor, then reservation settles with exact resulting Job ID. Replays return 409 even after process restart |
| FAILED_RETRY_REQUIRED or RESERVED | On Job create/Actor claim failures, token is never automatically returned to CONFIRMED. Uncertain states fail closed; operator reconciliation/new Preview required. Private unowned orphan files are cleaned when safely identifiable |

**Crash model:** a subprocess performs durable reserve and executes os._exit(53) before any JobStore create. Starting a fresh app with the same SQLite file still refuses that exact token (409) and creates no second Job. A crash between filesystem publish and Owner claim may leave a private orphan requiring manual reconciliation; this test-only bridge does not promise distributed atomic transactions across SQLite and B0 filesystem storage.

**Multi-process model:** two independent processes opening the same SQLite journal and reserving an identical confirmed token produce one RESERVED and one CONFLICT. Actual historical B0 JobStore remains a single-writer design; this is a token-level durable CAS proof, NOT authorization for multi-worker production B0.

**Scope limitation:** These routes still require explicit TEST_ONLY flags, localhost disposable runtime and OFFLINE_FIXTURE, with Tailscale SSO, Live and Paid flags disabled. The fixture invitation cookie/WeakMap does not constitute signed SSO identity or commercial Owner/PM approval. Real beta authorization requires a separately accepted persistent Job+Owner CAS and policy/version contract.

## 3. Repaired source frozen-code test evidence

| Check | Result |
|---|---|
| Python full suite | **1306/1306 PASS** |
| A51DR1 race + A51D Bridge + cost/Live guard focus | **56/56 PASS** |
| New adversarial cases | 2 and 12 concurrent authenticated HTTP POST; dual process SQLite CAS; Actor mismatch; token tamper/expiry; create-job/claim/settle injected exceptions; forced process crash; restart replay denial |
| Official React Node | **59/59 PASS** |
| React Lint and pinned Vite build | PASS / PASS |
| Owner React real Chrome end-to-end, same MPO → B0 → Copy/F09 → image approval → composed export | **15 steps PASS**, 6 screenshots |
| Browser download / authoritative Job SHA | PNG 2/2 receipt files SHA match (PNG + Caption) |
| Image output | one candidate, 1080×1350 Composed synthetic-only PNG |
| Desktop and 390px/360px | PASS; observed document scroll widths equal viewport width |
| Unauthenticated Chrome / cross-Actor FastAPI | HTTP 401 / 404 |
| Real provider calls and GCP changes | **0 / 0** |

- Pinned React JS bundle SHA-256: 4ab7584362365fa2b7164ef6b65a6524d6d18c70b3b971f537fda99fbf415e89.
- Pinned index.html SHA-256: c77a88186a127be44dc319e16e5818e1cfc1ef547067846f2837b74814b7757a.
- Actual downloaded synthetic PNG SHA: 95b9414d6eac81ef4352ae28a9d30ef41c1af1a0caf50bd492624bc288b34d62.
- Actual downloaded synthetic Caption SHA: a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839.
- Pre-document committed source integrity 805 tracked blobs PASS; clean Track A worktree.

Evidence root: docs/integration/evidence/A51DR1_20261111/

SHA Manifest: docs/integration/evidence/A51DR1_20261111/R1_SHA256_MANIFEST.txt; 18/18 evidence file SHA entries PASS.

To reproduce in existing Mac Studio approved local environment (no new packages or real Provider calls):

    cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
    P='/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3'
    PYTHONDONTWRITEBYTECODE=1 "$P" -B -m pytest -q -p no:cacheprovider -p no:warnings tests/demo_live/test_a51dr1_mpo_concurrency_recovery.py tests/demo_live/test_a51d_mpo_http_fixture_bridge.py tests/demo_live/test_a51d_beta_monitor_only_no_bypass.py tests/demo_live/test_a51c_signed_cost_runtime.py
    PYTHONDONTWRITEBYTECODE=1 "$P" -B -m pytest -q -p no:cacheprovider -p no:warnings tests
    npm --prefix app test
    npm --prefix app run lint

Chrome runner: tests/product_e2e/run_a51d_mpo_react_chrome_fixture.sh with A41_PYTHON, A41_PLAYWRIGHT_CORE_MODULE, A41_FONT and A51D_PORT=18547. It rejects paid API credentials, bound or protected ports, and remote hosts. Actual C-A repeat can be run from a private copied original attack script with only the source root changed.

## 4. Unchanged signed Full-Feature Beta hard gates

1. **Owner MPO policy**: Image Owner #24, FE #26, PM must formally select REJECT_MULTIFRAME or PREVIEW_AND_EXPLICIT_SELECT, contract/version/DTO, signed SSO Actor/Upload Request binding. No human approval generated.
2. **True signed beta ingress**: Replace test-only routes, implement and independently review persistent multi-worker transaction/claim/recovery contracts, forbid v2 silent frame0 for new beta Jobs, preserve historical v2 and all original receipts.
3. **Real product quality**: 2–5 rights-cleared same-SKU photos, actual package/logo/label masks, A/C v3 CTA/Typography and true Owner/PM human review. Original local customer photos not used or sent outside.
4. **Provider safety**: true PM-approved signed Hard Cap, worker-only credential, Queue/Cost/Owner Provider Attempt/Usage/Receipt reconciliation and BILLING_UNKNOWN no automatic retry; code-level guard alone is not actual invoice protection.
5. **GCP/UAT**: A-only isolated latest GCP runtime (previous C-A remote observation was old 9879eb0f85747312a224ecd898aaff84d834590b), approved WAL backup/Rollback, signed SSO team access and real browser UAT.
6. **6 independent paid Jobs**: Freeform/Composed × 3:4/4:5/9:16; one candidate per Job. A/C are Composed 4:5 typography profiles, not modes. No Batch/Gallery.

**C-A review request:** Reapply exact prior C-A asynchronous double-consumption script; validate 2/12 HTTP and 2-process CAS, crash-restart tombstones, Actor/Preview/TTL/input SHA, failure injection, unchanged v2/React Chrome and no Live/paid activation. Keep newly accepted R1 technology distinct from real human approvals.

**Explicit status:** A51DR1_DEVELOPER_RACE_REPAIR_PASS / C_A51DR1_DIFFERENTIAL_PENDING / SAFE_NONBILLABLE_DEVELOPMENT_GO / SIGNED_BETA_MPO_POLICY_PENDING / GCP_A_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / REAL_PROVIDER_E2E_0_OF_6 / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO.
