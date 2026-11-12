# IT-TEM P03 / Track A — A5-1 Versioned Profile v3 Actual Runtime & React Chrome E2E

**Audit submission date:** 2026-11-10 (Asia/Seoul)
**Work classification:** Developer implementation + independent C-A **submission**, NOT C-A acceptance or PM/Owner approval
**Risk boundary:** Nonbillable, loopback-only, synthetic fixture; actual GCP A / real Provider / real product fidelity / team access **HOLD**.

## 0. Immutable source and evidence authority

- Baseline before this A5-1 unit: HEAD `23cd11bcc96dde4847514308490836a1aad3d4ca`; tree `3ea957e3e16b5268115c9dfeaae5ec4d53efb3a2`.
- **Frozen tested source CODE HEAD:** `3db1c124e0c9e56844d249a480f0cbf60aec5fb1`; **CODE tree** `55315f45e5876b074ede64d9832eebae764a6487`. This source commit is the exact basis for final A/C Chrome evidence and Python 1,161 tests.
- New documentation/evidence may be committed AFTER this frozen code SHA. Do not confuse the future evidence-packet Git HEAD/tree with `3db1c12` tested code tree; independently diff `3db1c12..final HEAD` to ensure **docs/evidence-only changes**.
- **Read-only verification:** `python3 -B docs/integration/evidence/A51_20261110/verify_a51_evidence.py`. Output asserts both evidence sets, actual receipt + SQLite frozen snapshots, 15 browser stages each, SHA invariants, provider/cost/queue zero. PASS as developer self-check; independent C-A replay pending.
- `docs/integration/evidence/A51_20261110/A51_LOCAL_BUILD_SOURCE_PIN.json` pins actual Vite JS asset SHA `34417a2d84d0a1eb60f4165ed1ac39b3abb73d55deb7b3bb5c8792d662784fd1`, HTML SHA, dependency locks and Font+License SHA. Browser displays **short** commit marker `3db1c124`, not full SHA. This is a local TEST build, **not** GCP runtime proof.

## 1. Scope actually implemented

1. **Additive Composed 4:5 v3 A/C**: New Job at ingress freezes `OWNER_COMPOSED_4X5_V3_BETA_A` or `_C`, `owner-composed-4x5-v3-beta-proposal1`, exact layout/safe-zone SHA, `a5-v3-beta-unsigned-20261110` epoch. **A** editorial center = default *implementation reference only*; **C** stronger CTA. Both are unsigned/PM-unaccepted proposals, explicitly `OFFLINE_FIXTURE_ONLY`.
2. **Source-first Owner Image binding**: new `a5-v3-beta-A|C` request field and source-first Korean generation-area instruction on the **Image Owner adapter**; model is directed to leave Head/Sub/CTA unpainted for server compositor. Historical v2 serialized wire is unchanged when optional field absent. This is validated through actual Owner Image **MockTransport** (A/C, replay single attempt, 0 paid calls) and Pydantic negative tests.
3. **Actual Owner compositing of Head/Sub/CTA**: isolated beta style for `compose_ad_png` adds Pretendard variable weights (headline 700, subline 500, CTA 700), CTA A rounded pill radius 50px / C action bar radius 24px and pinned text regions. Real Pillow PNG/Caption are written atomically with receipt and immutable Job/Attempt state. Missing CTA, wrong SHA/font/box, extra text fields, multi-line/overflow, profile mismatch fail closed. Historical v1/v2 compositor receives **original function call signature**, explicitly regression-tested.
4. **Explicit protection limitation**: v3 synthetic `protected_regions` is **a fictitious product target**, not an actual product/logo/label segmentation mask. The receipt explicitly overrides `protected_region_check=false`, `synthetic_target_region_check=true`, `real_customer_assets_permitted=false`, `real_provider_permitted=false`. Do not equate protected rectangle non-overlap with real product fidelity or legal rights.
5. **Security and compatibility**: New v3 selector requires explicit profile A/C, `IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED=YES`, LIVE and billable flags disabled. Signed/real use cannot activate this path; changing LIVE flags after Job creation blocks the Image request. Old v2 Job/template snapshots remain unchanged. No new batch or multiple image candidate API, Freeform receives no compositor overlay, other ratios remain v2. Source priority FE #26 > Text #27 > Image #24 > Serving maintained.

**Code diff to review (baseline → tested source):** `git diff --name-status 23cd11b..3db1c12`. Risk-focused: `demo_staging/live/{a5_beta_profile_v3,store,template_contract,pipeline}.py`; `src/image_generation/{layout_profiles_v3,contracts,backend_adapter,korean_image_policy,composition}.py`; new A5-1 tests and Chrome runner. No implementation changes to prior A2/A3/A4 protective adapters beyond the narrowly required integration.

## 2. Runtime tests actually passed

| Independent developer check (not C-A attestation) | Recorded result | Evidence |
|---|---|---|
| Python complete suite including A2–A4 and v2 compatibility | **1,161 / 1,161 PASS**, exit 0 | `evidence/A51_20261110/A51_FULL_PYTHON_1161.log` |
| React | **57 / 57 PASS**, exit 0 | `A51_REACT_57.log` |
| React Lint / Vite Build | **0 errors** / PASS, exit 0 | `A51_LINT.log`, `A51_BUILD.log` |
| Historical v1/v2 composition callable + template contract | **48 / 48 PASS**, exit 0 | `A51_V2_COMPATIBILITY_48.log` |
| Real Image Owner A/C MockTransport + DTO negative cases | **11 / 11 PASS**, exit 0 | `A51_OWNER_IMAGE_MOCKTRANSPORT_11.log` |
| A Reflow official React **Chrome** from pinned code | **15 browser stages PASS**, 12 screenshots, exit 0 | `A/browser_trace.json` and `A51_CHROME_A_EXIT0.log` |
| C Reflow official React **Chrome** from pinned code | **15 browser stages PASS**, 12 screenshots, exit 0 | `C/browser_trace.json` and `A51_CHROME_C_EXIT0.log` |
| SHA/DB/Receipt/Artifact cross-check (read-only) | **A+C PASS** | `verify_a51_evidence.py`, `A|C/frozen_profile_snapshot.json`, `A|C/owner_composition_receipt.json` |

Each Chrome Job used an independent, randomly generated synthetic dataset, **not** real customer data: product photos 2 → QA analysis/research/plan/copy and actual rule check → copy revision/restore and fresh approval → candidate #1 rejected → explicit one regeneration #2 → approval → 1080×1350 PNG and UTF‑8 caption browser download → GET-only refresh → desktop and 390/360px screenshots → anonymous 401 and Bob 404. Batch candidate_count 2/3/4 and mixed mode request all 422. No outside POST, no browser script errors, **0 paid Provider/Queue/Cost entries**.

### Actual final immutable SHA evidence

| Source | Profile A | Profile C |
|---|---|---|
| Frozen profile ID | `OWNER_COMPOSED_4X5_V3_BETA_A` | `OWNER_COMPOSED_4X5_V3_BETA_C` |
| Frozen Layout SHA-256 | `e4a4f09499b0add2b3189b349c1c710bb698db821268a6dbbb0cdcf4f9c3158f` | `277e0a0f748bfa07d3bc6abd5085375df8935fef89af918b52f67c20f9dd4d90` |
| Final actual Chrome-downloaded 1080×1350 PNG SHA-256 | `52b05579276f65b1d142bb04e7bf53b3ab8be21f33370275af75bb32d8f329e2` | `f49fc2947d893c4d44bb141553192e02e2813b135cc88ef88536670367e96c22` |
| Owner's exact original composition receipt SHA-256 | `295e72fe6ce329c6d5b14ee97c6252d635f3d59c46bf1b63847c5fcd971c19f1` | `d045a8765c13f6aae9a121d06d91046fc0088fba3107460aabb82ff65fb77ba9` |
| UTF-8 caption download SHA-256 | `a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839` | `a2269c826e49dd43406c281935c1fc411e720c278ef24b14f6f9c10ab109c839` |

- Font file SHA: `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22` (`PretendardVariable.ttf` in installed local app dependency; **font binaries not delivered**).
- Font license notice SHA: `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`; final legal-use acceptance **PENDING**.
- Each `A/` and `C/` contains downloaded PNG/Caption, 12 Chrome screenshots, sanitized trace, original SHA manifest (19 files), hash verification log, actual Owner Receipt, read-only frozen SQLite Policy export, and independent DB-artifact verifier output. **No raw SQLite, private invite, cookies, API key, real customer images or personal account data included.**

## 3. Mandatory 7-gate beta decision — strictly separated

| PM mandatory gate | Evidence state, 2026-11-10 | Release gate |
|---|---|---|
| `SOURCE_AND_SECURITY_PASS` | Developer Python/React/old-v2 regression PASS, final source integrity reattestation and C-A independent audit still required | **HOLD pending C-A** |
| `PROFILE_V3_RUNTIME_PASS` | **Mac Studio OFFLINE_FIXTURE actual Owner A/C PNG PASS**, actual GCP A running v3 NOT VERIFIED; v3 still unsigned proposal | **HOLD for beta** |
| `OWNER_INTEGRATION_PASS` | Full official React QA synthetic user journey PASS (A/C), live Text/Image Worker and production dependencies not verified | **HOLD for beta** |
| `REAL_PROVIDER_E2E_PASS` | 0 real Provider Job, 0 billable calls; 6 independent real Job combinations NOT executed | **HOLD** |
| `UI_UX_BETA_PASS` | React, Chrome desktop/390/360 and GET-only synthetic PASS; real deployed browser, accessibility and team UX not audited | **HOLD** |
| `VISUAL_QUALITY_BETA_PASS` | Actual Korean A/C CTA & glyph receipt PASS; **synthetic solid-color image only**, no real product/brand/label or human acceptance | **HOLD** |
| `TEAM_UAT_READY` | No newly deployed accessible isolated team URL / verified signed SSO / PM team accounts / feedback route | **HOLD** |

**Final:** `FULL_FEATURE_BETA_DELIVERY_HOLD`, `COMMERCIAL_RELEASE_READY=NO`. Do **not** apply `CONDITIONAL_GO` to missing major features.

## 4. GCP A gate and exact no-change boundary

The previous C-A A instance observed **older deployed SHA** `9879eb0f85747312a224ecd898aaff84d834590b` and missing expected Image Attempt DB. Latest Mac Studio read-only `gcloud compute instances describe` failed because interactive reauthentication is required. **No new current VM/runtime/SSO/DB observation is established**, no deployment or migrations or backups made.

Before ANY authorized deployment:
1. PM/Owner approve **signed exact** Profile ID/Version/JSON SHA, safe target and real segmentation Mask, Font/License, Policy Epoch, 9:16 CTA handling as applicable; preserve old v2 assets. A/C proposal comparison does not equal approval.
2. Restore GCP A operator auth via user-controlled reauthentication. Read-only observe A-only `/home/macstudio/ittem-e2e-baseline-20261107` and A-only 18096/10443; live execution SHA, source/root, schemas in Job, Queue, Cost, Owner Image Attempt DB, WAL, artifact ACL and rollback points. **Missing DB is HOLD; do not auto-init, auto-migrate, or overwrite**.
3. Run existing `scripts/a3_track_a_guarded_readiness.py --runtime-root /home/macstudio/ittem-e2e-baseline-20261107` only in the approved A read-only operator context. DO NOT touch B 18100, protected Live 18088, protected QA 18095 or official `dev`/Owner PRs.
4. Prepare **separate immutable A-only candidate source + isolated disposable DB/runtime**, verify full SHA+build asset SHA+dependency locks, worker-disabled env and rollback rehearsal. **Do not redirect shared listeners or reuse active DB without separate PM deployment approval.**
5. Paid Provider is separately HOLD pending PM-approved actual money cap, credential source, charged-usage reconciliation, idempotent/non-replay retry and Queue+Cost+Image Owner Attempt ledger proof. Existing `MONITOR_ONLY` is NOT a spend cap.
6. Six real Provider E2E tests are 6 **independent one-image Jobs**, not six candidates in one request. Evaluate A/C/9:16 Composed policy plus Freeform Korean visual fidelity; real product/brand and owner+PM visual UAT acceptance required.

## 5. C-A differential audit — requested review checklist

**A5-1 newly changed surfaces only**, not blanket re-audit of accepted A2–A4:
- Owner/Image/Serving v3 optional field: verify old Owner #24 serialization unchanged, v2 historical render signature and receipt replay, no revoked approval resurrection, no stale context bypass, no multi-candidate admission.
- v3 A/C requested background composition vs final layout: inspect actual Owner request/MockTransport prompt, version/policy/hash, safety-zone geometry and text region, Head/Sub/CTA exactly once, CTA proper roundness, text SHA, font bytes/hash, one-line overflow fail-closed.
- Check `protected_region_check=false` is **truthful**; absence of verified actual product/logo/mask must block actual model/customer release.
- Verify later LIVE flag flips or lost profile/epoch cannot silently convert an unsigned fixture into billable or deployed job; no Provider worker activation and no billing bypass.
- A5-1 full React Chrome trace and independent SHA/Receipt/SQLite snapshot validator: artifacts matched? downloads and refresh GET-only? ACL 401/404 and mixed/batch 422? provenance 0 Provider, 0 Cost, 0 Queue?
- Final source code SHA `3db1c12` vs any subsequent evidence-only HEAD, executable code unchanged; C-A own replay/test/negative cases before issuing `SOURCE_AND_SECURITY_PASS` or `PROFILE_V3_RUNTIME_PASS`.

**Operator command:** `python3 -B docs/integration/evidence/A51_20261110/verify_a51_evidence.py`.

**Submission decision:** `A51_V3_A_C_DEVELOPER_OFFLINE_FIXTURE_E2E_PASS / C_A_DIFFERENTIAL_AUDIT_REQUESTED / REAL_PROVIDER_GCP_HUMAN_ACCEPTANCE_HOLD`. No C-A signature/acceptance is fabricated or implied.
