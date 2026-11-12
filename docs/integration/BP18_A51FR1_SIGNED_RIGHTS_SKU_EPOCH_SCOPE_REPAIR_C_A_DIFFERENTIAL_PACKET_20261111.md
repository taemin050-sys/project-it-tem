# IT-TEM P03 — Track A A5-1F-R1 차등 독립감사 제출

**Date:** 2026-11-11 KST
**작업:** `A51F-P1-01 SIGNED_RIGHTS_SCOPE_NOT_BOUND_TO_AUTHORITATIVE_SKU_OR_FROZEN_POLICY_EPOCH` 최소 수정.
**현재 판정:** `A51FR1_P1_DEVELOPER_FIXED / C_A51FR1_INDEPENDENT_AUDIT_PENDING / SAFE_NONBILLABLE_DEVELOPMENT_GO / FULL_FEATURE_BETA_DELIVERY_HOLD`

## 1. 독립감사 기준과 고정 코드

- C-A51F 최종 수용 전 제출: `dc2340c4485270863295b514951580fa699e6c7a`, Tree `dab9aeadcb622988d9f09b1c85d8ba7c65672f54`.
- 공식 C-A51F 독립감사 보고서: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A51F_DUAL_SIGNED_RIGHTS_RELEASE_GATE_INDEPENDENT_AUDIT_20261111.md`, SHA-256 `95f298459d96a10507c40bf368e241d8d6c8aad1929ad8a822e9c97afcf83e63`.
- **R1 실행 코드 HEAD:** `6a68998c5d04c10a522265874079de87764aa2f7`, Tree `30a32e87de6657c6d2ac4fea2420c88e392b8864`.
- **변경은 3개 파일만:** `demo_staging/live/a51f_product_rights_authority.py`, `demo_staging/live/worker.py`, `tests/demo_live/test_a51f_signed_source_rights_authority.py`. Old v2 Owner Image/Text/FE/B0 default/GCP/Track B 변경 없음. Signed Profile A51B 자체의 미승인 Boolean/유료 차단 유지.

## 2. P1-01 범위 결속 수정

### A. 기존 Frozen Owner/PM Profile Epoch·Decision SHA가 유일한 기대값

`worker.authorize_worker_item`는 이미 정상 재검증된 `verify_frozen_runtime_activation(frozen)`의 반환값 `verified_profile.safe_zone.policy_epoch` 및 `signed_owner_pm_decision_sha256`를 **필수 인자**로 전달합니다.

`validate_signed_source_rights`는 위 인자 누락·잘못된 형식·Rights JSON과 다른 유효한 Epoch/Decision SHA를 Fail-Closed 차단합니다. **서명된 Rights 문서에서 자기 Epoch를 읽어 권한 값으로 재채택하지 않습니다.** Signed Profile의 실제 이중 서명 검증·기존 Job/Approval/Mask 조건도 우회하지 않습니다.

### B. 별도의 서버 신뢰 SKU ↔ 실제 B0 Job 이미지 결속

Rights 문서의 유효한 `product_sku` 문자열 자체는 권한이 아닙니다. 운영자 보호 경로 `IT_TEM_A51F_SKU_BINDING_ROOT`는 Rights·Trust roots와 서로 달라야 하며, 파일을 자동 생성하거나 기존 자료를 덮어쓰지 않습니다.

새 **비실행/승인 발행 기능이 없는 계약** `IT_TEM_P03_A51FR1_DUAL_SIGNED_IMMUTABLE_SKU_ASSET_BINDING_V1`: `<job_id>.sku_binding.json`과 독립 `image_owner`·`pm` Ed25519 서명 2개가 다음에 결속됩니다.

- 정확한 `job_id`, 인증된 `actor`, 사람 검수 `product_sku`.
- B0 JobStore가 실제 보관하는 **순서 있는 각 자산의 role/asset_id/SHA-256**과 다시 읽어 확인한 이미지 파일 실제 SHA의 canonical digest.
- 해당 Source Commit, Frozen Profile Policy Epoch 및 Signed Profile Decision SHA.
- 검수 유효기간 UTC 최대 30일과 `APPROVED_SKU_AND_ORDERED_INPUT_ASSETS` 결정.

Rights 본문의 SKU와 독립 SKU binding SKU가 다르면, **두 문서의 서명이 모두 진짜여도** Fail-Closed. SKU binding이 누락·기한 초과·변조·서명자 불일치·타 Job/Actor/자산/정책으로 변경되면 차단. 브라우저 텍스트·파일명만으로 SKU 신뢰를 부여하지 않습니다.

이는 실제 제품이 같은 SKU인지 **사람 Owner/PM이 책임지고 판정해야 하는 서명 가능한 계약**입니다. Test keys와 테스트용 임의 SKU는 실제 검수·법적 사용권이 아닙니다. 본 서명 레코드는 운영자 보호 파일로 검증되며, *변경 이력의 append-only 영속 감사 원장까지 완료했다는 의미는 아닙니다*. 실제 Signer 인증·발급·원장 보존·철회 권한은 별도 운영 승인 대상입니다.

### C. MPO 원본 Provenance

신규 베타 A51E는 decoded MPO를 여전히 **전부 거절**합니다. 위 SKU digest는 **실제 B0 JobStore에 저장된 이미지 bytes**를 결속합니다. 미래에 MPO Preview/Frame Select를 정식 승인하는 경우, 최초 MPO 컨테이너 SHA, 프레임 인덱스, EXIF/ICC→sRGB 변환·정규화 SHA, 실제 사용자 선택 이력을 **별도 영속 승인 계약**으로 추가해야 하며, 지금 통과로 선언하지 않습니다. 기존 v2 자동 frame0 동작 불변.

## 3. 재현·공격시험

| 검증 | 개발 세션 결과 |
|---|---|
| A51F SKU/Epoch Rights 표적 | **52/52 PASS** |
| A51F Signed Rights + GCP Readonly Gate 합산 | **62/62 PASS**, 고정 코드 HEAD에서 재실행 |
| Python 전체 | **1,395/1,395 PASS** |
| React | **61/61 PASS** |
| Lint, Vite Build | **PASS / PASS** |
| 고정 Code Source Attestation | **866개 HEAD tracked blobs PASS** |
| 정상 SKU binding + 실제 Ed25519 서명 | **PASS**, 테스트 전용 Ephemeral keys |
| Rights만 유효한 다른 SKU로 바꾸고 이중 재서명 | **BLOCK** |
| Rights만 유효한 다른 Epoch로 바꾸고 이중 재서명 | **BLOCK** |
| Rights만 다른 Signed Profile Decision SHA로 재서명 | **BLOCK** |
| Rights와 SKU binding 모두 다른 Epoch 또는 Decision SHA로 올바르게 재서명 | **BLOCK** (독립 Frozen Profile 미일치) |
| 서명된 SKU binding만 다른 Job/Actor/SKU/자산 SHA로 재서명 | **BLOCK** |
| SKU binding/서명/root 누락, 시각/권한/Source SHA 부정 시험 | **BLOCK** |
| Owner Provider 실제 Paid Calls | **0건**, 테스트 키만 생성 |
| GCP A 변경·실모델·실제품 데이터 외부 전송 | **0건** |

재현: `pytest -q tests/demo_live/test_a51f_signed_source_rights_authority.py tests/demo_live/test_a51f_readonly_beta_release_gate.py`; `pytest -q tests` (Python 3.12 + Mac Studio local Korean font configuration); `npm --prefix app test`, `npm --prefix app run lint`, `npm --prefix app run build`. 서명 검증에서 OpenSSL Ed25519 사용, 임시 private keys는 시스템 테스트 tmp 안에만 생성.

증거: `docs/integration/evidence/A51FR1_20261111/`와 `A51FR1_SHA256_MANIFEST.txt`. 실물 제품·사용권 증명·폰트 바이너리·실 API key·테스트 private key는 포함하지 않음.

## 4. 여전히 미완료인 실제 Full-Feature Beta

- Owner #24, FE #26, PM 실제 MPO 선택·제품 SKU·원본 사용권·마스크·Font License·A/C Profile v3 승인 **없음**. 실사용권이 확보된 브랜드/라벨 상품 광고 `NOT_AUDITED`.
- A51B Signed v3는 4:5 Composed 중심의 Offline-Only 승인 계약, 4개 Provider 권리 Boolean이 FALSE. **R1 코드가 이 플래그를 True로 바꾸지 않았고 Worker가 여전히 차단합니다.** 실제 6개 모드·비율 조합의 승인 가능한 Paid Runtime 계약은 추가 협의/구현 필요.
- C-A51F 실제 GCP 읽기 전용 최신 조사: 실행 Source SHA `9879eb0f85747312a224ecd898aaff84d834590b`, App 이미지 Attempt 8개, Queue 0, Cost 0, Owner Provider Attempt DB 미생성, Beta Ready false. **이번 R1은 그 C-A 읽기 전용 증거를 재활용했으며 GCP에 새로 접근하거나 수정하지 않았습니다**.
- 실제 Signed Tailscale Serve, 고정 Runtime Source/Build/Font, Worker-only secret, 비용 Hard Cap/외부 계정 상한, 원장 대사, WAL Backup/Rollback, 실제 Provider **0/6**, 팀 UAT 모두 HOLD. Fake Signed Local Chrome / 6개 Offline Fixture는 앞선 C-A51E 수용 상태만 유지.
- 현재 PM 결정 요청서: `docs/integration/BP18_A51F_OWNER_PM_ACTUAL_BETA_DECISION_AND_SIGNING_REQUEST_20261111.md`. 작성되었지만 **전송/수신/승인 증거 없음**.

## 5. C-A 검토 요청

**A51F-P1-01의 범위 결속만 우선 차등 재감사**: 실제 검증된 Frozen Profile Epoch+Decision SHA의 Worker→Rights 공급, 두 개 별도 Ed25519 서명 자료의 SKU·자산 SHA 불변 결속, 유효한 다른 SKU/Epoch/Decision SHA 부정 시험, 미서명·바뀐 파일·서명 인증 누락 Fail-Closed, 기존 A51B/Cost/Live·GCP 실행 차단 유지. 다른 A2~A51E 독립 수용 기능 재개발 불필요.

**개발 제출 판정:** `A51FR1_SCOPE_BINDING_DEVELOPER_PASS / C_A51FR1_P1_REAUDIT_PENDING / SAFE_NONBILLABLE_DEVELOPMENT_GO / GCP_A_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / REAL_PROVIDER_E2E_0_OF_6 / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO`.
