# IT-TEM P03 — A5-1E Signed SSO Nonbillable Beta Intake Differential Submission

Date: 2026-11-11 KST. Source-first Track A. Developer candidate, not a commercial/paid deployment approval.

## 1. Authority and source

- Previously independently accepted C-A51D-R1: HEAD 9d74c9da10cc6b9a71b94872b0977f855a2dc314, Tree 3426f5e7281633dadadda7a85e20cdcda3c396ff.
- Prior C-A independent report: /Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A51DR1_SQLITE_MPO_CAS_DIFFERENTIAL_INDEPENDENT_AUDIT_20261111.md. SHA-256 b25e7ab057d5ca78ef86073cee2470a90680ad6bce08b76282a3743384e14006.
- Fixed A5-1E executable HEAD d547c778d5542d706fae454cc7ba669939666f4c, Tree c8fcd7fad435d599201303239ecccae13009adc7; exactly 15 new/modified code and test files, no Owner Image v2 runtime modifications.
- Review requested: signed Actor beta candidate upload, persistent idempotency, MPO rejection pending Owner policy, React real flow, nonbillable six scenario tests and deployment guards. C-A independent A5-1E decision is still PENDING.

## 2. Integrated design and bounded safety claims

- New endpoint POST /demo/api/a51e/beta/jobs binds the existing cryptographically verified Tailscale assertion Actor with a client-supplied 32hex Upload Request ID and a canonical hash of every uploaded source image and UI input JSON. All photos use current B0 validation and JobStore after CAS, returning the actual B0 Job ID. The browser stores an upload ID for retriable unchanged form input; any edits reset it.
- New independent, operator-preinitialized private SQLite WAL file a51e_beta_upload_request.sqlite with BEGIN IMMEDIATE: RESERVED before JobStore creation, COMMITTED to the exact Actor-owned Job. Identical Actor + Request ID + original bytes produces HTTP 200 with the SAME Job ID after success. A different Actor, different uploaded bytes or unresolved RESERVED/FAILED_REQUIRES_REVIEW state is blocked. Eight concurrent requests create no more than one Job. If a post-reservation operation fails, auto retry is denied and operator reconciliation is required. Not a true multi-worker distributed Job/Cost atomic transaction.
- Until Image Owner #24, FE Owner #26 and PM sign the actual MPO contract, the new beta candidate explicitly REJECTS any decoded MPO including disguised .jpg without silently selecting frame 0. Existing v2 B0 stays unchanged, but candidate mode denies direct B0 POST with HTTP 423. Previous A51D test-only MPO Bridge stays disabled under signed beta.
- The candidate starts only in a disposable local test root and requires Signed SSO-only, existing security flags, HARD_CAP policy flags, initialized private upload ledger and all Live/Worker/Paid flags OFF. It does not accept legacy invite-cookie fallback. Browser and server both block unapproved MPO, while backend always checks the full decoded image container. Frontend preserves original bytes rather than silently resizing in candidate mode.
- Official React UX now has candidate-only information explaining Owner MPO approval pending and real AI Provider disabled. A5-1E creates no Tailscale or external GCP session and no actual PM/Owner signature. Even the Chrome HMAC test is an EPHEMERAL localhost imitation of the signed proxy; it is NOT actual Tailscale Serve or a team-signed production SSO proof.
- Immutable approved product policy: Freeform or Composed, 3:4 / 4:5 / 9:16, ONE image candidate per independent Job. No Batch/Gallery. FE #26 > Text #27 > Image #24. A/C remain Composed 4:5 internal typography profiles. No reapproval requested.

## 3. Fixed-code developer validation

| Check | Result |
|---|---|
| Entire Python tests | 1333/1333 PASS |
| A51E signed HMAC ingress focus | 27/27 PASS |
| 6 mode/ratio combinations: distinct signed-assertion OFFLINE_FIXTURE jobs | 6/6 PASS; NOT real Provider |
| Real external Provider / Queue / Cost Attempt | 0 / 0 / 0 |
| Old B0 create blocked only in isolated signed candidate | PASS |
| Cross Actor ACL / malformed HMAC / Origin / missing ledger / URL tampering | PASS |
| Persistent request ID, 8 concurrent posts, same Job after restart | PASS |
| Wrong source bytes / MPO container / failed ownership commit | BLOCKED |
| React tests | 61/61 PASS |
| Oxlint / Vite Build | PASS / PASS |
| Actual React Chrome with LOCAL FAKE signed proxy | 10 steps PASS, 4 screenshots |
| Composed 4:5 final PNG and Caption actual browser SHA | 2/2 match |
| Desktop / mobile 390 / 360 / GET-only refresh | PASS |
| Browser errors / external requests | 0 / 0 |
| Code fixed source attestation | 833/833 tracked blobs PASS |

Source is the fixed Git HEAD noted above, not previous build evidence. Exact built index JS SHA-256 dc179005fc86d754057e5698d289a6a0fe868a1272a3e01faf960e8fa86ee213; index.html SHA-256 38af4ae5cb4776774f7758908506c878d32e8f1195d1b2e8412a6c84e70e3267.

Browser synthetic Composed 1080x1350 PNG SHA-256 95b9414d6eac81ef4352ae28a9d30ef41c1af1a0caf50bd492624bc288b34d62. Caption SHA-256 a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839.

Test reproducer entrypoints:
- tests/demo_live/test_a51e_signed_sso_beta_ingress.py
- tests/product_e2e/a51e_signed_sso_nonbillable_fixture_server.py
- tests/product_e2e/a51e_signed_sso_react_chrome.cjs
- tests/product_e2e/run_a51e_signed_sso_react_chrome_fixture.sh
- Existing Mac Studio Python3.12 venv, local Playwright, system font references; A51E_PORT=18549. Script refuses paid credentials, protected and busy ports; runs localhost only. Does not preserve private synthetic key into evidence.
- Official evidence root: docs/integration/evidence/A51E_20261111/ and its SHA256 manifest.

## 4. Critical real beta gaps and Owner/PM decisions

1. Image Owner #24 + FE Owner #26 + PM must select REJECT_MULTIFRAME versus signed PREVIEW_AND_EXPLICIT_SELECT for actual MPO, approve frame/EXIF/ICC SHA DTO, signed SSO Actor/job request, persistent CAS and human choices. A51E temporarily rejects MPO and does not create approval evidence.
2. Owner+PM actual signed v3 A/C Profile, Policy Epoch, licensed Font, real product/label masks, rights-cleared SAME-SKU photos and actual product/brand and Korean CTA/typography quality remain NOT APPROVED/NOT AUDITED. No locally supplied customer photo was sent to a Provider.
3. Real PM cost authority: signed Hard Cap with actual model price and verified outside account spend ceiling; worker-only API key; Queue/Cost/Owner Provider Attempt/Usage/Receipt reconciliation and BILLING_UNKNOWN no auto retry. Fake test-signing key is NOT PM authorization.
4. PM GCP deployment permission: independently isolated A signed Tailscale Serve listener, WAL-consistent backup/rollback, fixed Source/Tree/JS/Font/Runtime SHA; candidate-specific Provider Attempt DB schema explicit operator approval, no protected GCP historical DB modification. Last independent GCP observed old Source SHA 9879eb0f85747312a224ecd898aaff84d834590b, application image attempts 8, Queue 0, Cost 0, separate Owner paid Attempt DB absent; no new GCP probe or writes this unit.
5. Six actual Provider Job E2E still 0/6. Six signed-assertion OFFLINE_FIXTURE Jobs MUST NOT be reported as six actual billed model jobs. Real team URL, actual Tailscale SSO and team UAT not done.

## 5. C-A next differential audit

Review only source since accepted A51D-R1: signed SSO actor assertion and direct B0 create bypass, decoded MPO reject, source SHA/idempotency/Actor/TTL, replay and eight concurrent, nonbillable candidate root and flags, actual Chrome and six offline Jobs, no Provider calls or data-source authority elevation. Check that the test-only fake signing proxy remains private/local and NEVER becomes an actual signed SSO deployment.

Developer status: A51E_NONBILLABLE_SIGNED_ASSERTION_INPUT_E2E_DEVELOPER_PASS; C_A51E_DIFFERENTIAL_AUDIT_PENDING; PRODUCT_POLICY_APPROVED; MPO_OWNER_POLICY_PENDING; REAL_PRODUCT_RIGHTS_PENDING; REAL_SIGNED_TAILSCALE_TEAM_SSO_NOT_AUDITED; REAL_PROVIDER_E2E_0_OF_6; GCP_A_QA_DEPLOYMENT_HOLD; A_GCP_PAID_WORKER_HOLD; FULL_FEATURE_BETA_DELIVERY_HOLD; COMMERCIAL_RELEASE_READY=NO.

No paid Provider, actual GCP operation, real customer imagery transmission, live signed session, real team access or actual Owner/PM approval was performed in A51E.
