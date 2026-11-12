# IT-TEM P03 — Track A A5-1C Full-Feature Beta Integration, Differential Audit Packet

**작성일:** 2026-11-10 KST
**제출 범위:** 신규 MPO 사용자 명시 선택 경계 + 격리된 3원장 Hard Cap 리허설. **실제 베타 배포/실모델 사용 승인이 아님.**

## 0. C-A 승인 기준과 고정 소스

- C-A5-1B-R1 최종 독립 수용: `C_A51BR1_SIGNED_TIME_REPAIRS_ACCEPTED` 및 `C_A51BR1_MPO_READONLY_PROVENANCE_ACCEPTED`.
- A5-1C 작업 시작 기준 HEAD `c03eb3ea803be8a8dba0cdad85276ca38be3ac1a`, tree `a3e29dd926a1c2216276cda68db85871bc8d1663`.
- 신규 코드 고정 HEAD `5c83265ff04dd85325636c8e3674987570a2084a`, tree `8534d19a38f2317ed30cb90283f020c441f74300`.
- 코드 변경은 4개 신설/추가 파일에 제한: `demo_staging/live/a51c_explicit_mpo_ingress.py`, `scripts/a51c_synthetic_three_ledger_hard_cap_rehearsal.py`, `tests/demo_live/test_a51c_explicit_mpo_ingress.py`, `tests/demo_live/test_a51c_three_ledger_rehearsal.py`; 추가 EXIF/ICC 재현 테스트 커밋 포함. `git diff --name-status c03eb3e..5c83265`로 검증.
- **기존 Owner FE/Text/Image 실행 소스, 기존 React 정식 UI·Worker·v2 Job/Receipt·A5-1B 서명 경계 변경 없음.** 공식 dev/Owner PR, Track B 및 GCP A/B 보호 실행 환경도 변경하지 않음.

## 1. Workstream A — 명시적 MPO 프레임 선택의 실제 코드 준비

신규 `a51c_explicit_mpo_ingress.py`는 현재 Owner/PM **승인 대기 중인 별도 후보 계약** `IT_TEM_P03_A51C_MPO_EXPLICIT_USER_SELECTION_PROPOSAL_V1`을 구현합니다. 이는 LIVE 환경, Provider 업로드, 기존 B0 API 또는 React 업로드에 **연결·활성화되지 않았습니다.**

- 실제 컨테이너 `MPO`를 확장자와 무관하게 검증. `.jpg`로 위장된 MPO도 컨테이너를 별도 판별. MIME·마커·원본 SHA·파일크기·프레임 수·픽셀수 검증.
- 실제 둘 이상의 각 프레임에서 **개별 디코딩 RGB SHA 및 EXIF-upright PNG Preview SHA**를 산출하되 기본 프레임을 선택하지 않음. 실제 고객 이미지 썸네일이나 원본 바이너리는 Git·감사 ZIP에 저장하지 않음.
- 승인된 후속 호출이 반드시 `selected_frame_index` (0 또는 1 등), `source_frame_count`, `source_sha256`, `selected_preview_sha256`, `upload_request_sha256`, `USER_VIEWED_AND_CONFIRMED_SELECTED_MPO_FRAME_V1`을 제공해야 JPEG 변환. 누락·변조·잘못된 선택은 Fail-Closed.
- 선택 프레임에 대한 EXIF 방향 처리, 검증된 ICC→sRGB 변환, JPEG 품질 94/4:4:4, 개인 EXIF/ICC 메타데이터 제거, 변환 SHA·실제 너비/높이·원본 SHA·Frame ID·선택 계약을 `ValidatedUpload.provenance`에 결속. 신규 격리 `JobStore`에서 provenance 보존과 2장·단일 Job 규칙을 테스트.
- **중요 제한:** 클라이언트가 보낸 선택 문자열과 SHA만으로 사람이 실제 Preview를 보았다는 사실·사용 권리를 입증할 수 없음. 공식 FE는 Preview 표시 및 사용자 행동 로그를 서버 인증 Actor와 Job에 연결해야 함. 이 모듈은 해당 FE·Actor 경로가 승인되기 전까지 호출되지 않음. `external_provider_transfer_permitted=false`를 명시.

### 기존 Owner Source와 새 베타의 충돌 지점 (결정 대기)

- `src/image_generation/assets.py`: MPO 입력의 0번 프레임 자동 선택.
- `src/serving/job_api.py`: 명시적 `.mpo` 확장자에만 MPO 변환 적용, 내부 컨테이너가 MPO인 `.jpg`는 JPEG 검증 단계에서 거절될 수 있음.
- `app/src/lib/mpo.ts`, `app/src/lib/shrinkImage.ts`: `.mpo` 확장자만 별도 취급하며, `.jpg` 내부 MPO는 일반 JPEG 브라우저 `createImageBitmap` 경로로 암묵적으로 디코딩·축소될 위험이 있음.
- 제공된 실제 제품 사진은 **9 JPEG + 15 이중 프레임 MPO(모두 JPG 확장자)**. 9개의 일반 JPEG는 EXIF Orientation 6 및 ICC 프로필을 보유. 15개 MPO의 프레임0과 프레임1은 모두 서로 다른 RGB SHA. 단순 자동 0번 선택을 새 Beta의 최종 정책으로 채택하면 안 됨.

**Image Owner #24, Frontend Owner #26, PM**은 MPO 거절 대 명시 선택 UI, 서버 DTO와 MIME/EXIF/ICC, 프레임별 SHA, 사용권, 기존 v2 보존을 공동 결정해야 합니다. 본 후보 구현이 최종 승인된 계약은 아닙니다.

## 2. Workstream B — 실제 제품/브랜드 사진의 진단

사용자가 제공한 `잘나온 화장품 모음` 원본은 이전 C-A와 **24/24 원본 SHA 동일**, 파일 손상 없음. 원본·썸네일·상품 라벨을 Git 또는 외부 Provider로 전송하지 않았음.

추가 **로컬 사람 시각 관찰**: 일반 JPEG 제품군 네 그룹의 8장 비공개 축소 미리보기에서 손에 든 제품, 매장 배경, 정면·후면 라벨, EXIF 회전이 보였음. 원본을 그대로 광고 배경에 배치하는 방식은 라벨/브랜드 보존, 컷아웃, 패키지 크기, 카피 Safe Zone을 실제 모델 출력으로 증명하지 못함. EXIF 방향은 정규화 시 반영해야 함.

- 법적 브랜드/초상권·자료 사용권 증거: `NOT_VERIFIED`.
- 실제 제품/라벨 로고 Mask 검수 및 원본 대비 정밀 검증: `NOT_AUDITED`.
- 실제 제품 AI 생성 광고 6조합 및 Owner/PM Human Visual: `0/6`, `PENDING`.
- 사용권 확인 후 **동일 물리 제품** 사진 2~5장·객체 Mask·라벨 읽기·색/형태/로고 비교 계약 확정 필요. 파일명 그룹화만으로 동일 제품이라고 단정하지 않음.

## 3. Workstream C — 실제 원장 코드를 사용하는 무과금 Hard Cap 리허설

신규 `scripts/a51c_synthetic_three_ledger_hard_cap_rehearsal.py`는 실행 때마다 **비어 있는 /private/tmp 아래 0700 디렉터리**를 생성한 뒤 즉시 정리합니다. 실제 `AttemptLedger`, `ProviderAttemptStore`, `LiveQueue` 클래스를 사용해 *인위적* $0.60 비용 상한/$0.10 예약의 6개 독립 `Composed|Freeform × 3 ratios` 단일 시안 Job을 시험합니다.

- Queue 0건, Test Cost 예약 6건, Owner Provider Test Attempt 6건의 독립 DB 생성.
- 7번째 Cost 예약 차단, 7번째 Owner Provider 예약 차단, 동일 Job의 2차 Attempt 거절.
- 결과 불명 `unknown` Owner Attempt를 보존하고 추가 재호출을 허용하지 않는 경계 확인.
- 네트워크 Provider 요청/실제 승인·실청구/운영 DB 수정은 **각각 0건**.
- 여기에 사용된 숫자는 시험값이며 실제 OpenAI 비용·PM 예산 상한·환율/가격표·실청구를 의미하지 않음.
- 이는 **실제 GCP Worker가 Hard Cap을 사용한다는 증거가 아님**. 현재 승인된 GCP A Worker `demo_staging/live/worker.py`에는 여전히 `MONITOR_ONLY` 경로가 있어 실제 과금 상한으로 승격 불가. 승인된 비용값·PM 서명·SSO·3중 원장/Receipt 대사가 확립된 후에만 별도 구현/배포/독립감사.

현 시점 GCP A 관측의 정본은 C-A51B 읽기 전용 보고서: 구버전 `9879eb0f85747312a224ecd898aaff84d834590b`, 앱 이미지 원장 8 COMPLETED, Queue 0, Cost 0, Owner Provider Attempt 별도 DB 없음. **이번 A51C에서 원격 SSH/배포/DB 생성/Worker 시작은 실행하지 않았음.**

## 4. Developer 검증 (C-A 독립 수용 아님)

| 검증 | 최종 결과 |
|---|---|
| 신규 A51C 표적 테스트 | **23/23 PASS** (EXIF/ICC 사례 포함) |
| 전체 Python 회귀 | **1,246/1,246 PASS** (최종 로그 참조) |
| React | **57/57 PASS** |
| Lint / Vite Build | PASS / PASS |
| FE bundle SHA (고정 코드 라벨) | `c38b8449c07e2659d442c886bae4ce2236d09529b7d911682f6022b3efaf6f97` |
| HTML SHA | `01a8441541f6eb025e20bcce43c63ae289a3a6d5f8d09216681c967322f29b1b` |
| 비용 Provider / GCP / 팀 UAT | **실제 0건 / 미실행 / HOLD** |

로컬 증거 `docs/integration/evidence/A51C_20261110/`와 SHA256 manifest. 완료한 개발 코드는 별도 커밋에 고정되며, 이후 모든 변경은 증거/문서만으로 제한합니다. **C-A 재감사 대상은 신규 A51C 네 개 파일과 EXIF/ICC 추가 테스트만**입니다.

## 5. 7개 Full-Feature Beta Gate

| Gate | 현 상태 |
|---|---|
| `SOURCE_AND_SECURITY_PASS` | 기존 C-A 수용 유지; 신규 A51C 개발 회귀 PASS, C-A 차등감사 대기 |
| `PROFILE_V3_RUNTIME_PASS` | A/C 로컬 Offline C-A 수용; 실제 Beta 서명/실제품 Mask 미수용 |
| `OWNER_INTEGRATION_PASS` | 신규 MPO adapter는 단독 Offline 테스트, 실React+B0 연계 미완료 |
| `REAL_PROVIDER_E2E_PASS` | 실제 Provider 0/6 |
| `UI_UX_BETA_PASS` | GCP/실제 SSO 팀 브라우저 검증 안 됨 |
| `VISUAL_QUALITY_BETA_PASS` | 실제 브랜드/라벨 품질 및 상업적 권리 미검증 |
| `TEAM_UAT_READY` | 운영URL·권한·회신·PM 승인 부재, HOLD |

정책 재승인 불필요: Freeform/Composed 2가지, 3:4·4:5·9:16, 요청당 단일 이미지, 명시적 재생성, FE #26 > Text #27 > Image #24. A/C는 Composed 4:5 내부 Profile 선택. 9:16 CTA 처리 정책 별도 미확정.

**최종 상태** `A51C_SAFE_NONBILLABLE_COMPONENTS_IMPLEMENTED / OWNER_PM_MPO_DECISION_PENDING / REAL_PRODUCT_RIGHTS_PENDING / GCP_A_DEPLOYMENT_HOLD / PAID_WORKER_HOLD / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO`.
