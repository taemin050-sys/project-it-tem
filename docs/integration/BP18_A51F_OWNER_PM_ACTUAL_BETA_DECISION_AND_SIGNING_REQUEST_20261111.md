# IT-TEM P03 / A5-1F — 실제 Owner/PM 베타 계약·승인 요청서

**용도:** 실제 승인자에게 전달할 의사결정 요청. **작성만 완료, 실제 발송/승인/서명 아님.**
**기준점:** C-A51E 독립 수용 HEAD `60dca54e16a5614318806532d122053ca8246d95`, Tree `b27f7c8889bc352e303f32ef419ce040a44931ac`. 기존 6개 모드·비율·1시안 정책 재승인 불필요.

## 1. 단일 회신으로 필요한 세 가지 결정 (초안, 권한 없음)

**To Image Owner #24 (박지수), FE Owner #26, PM (이태민).**

기술 구현 측은 Signed SSO 모사 경로와 비과금 6/6 조합을 C-A 독립 수용받았습니다. 현재 실제 Full-Feature Beta를 위해 필요한 사람 결정 사항은 **MPO**, **실제 SKU 사진·권리·제품보호**, **실제 A-only 배포와 비용** 세 가지입니다.

### 결정 A — MPO 입력 정책

- **우선 제안:** `PREVIEW_AND_EXPLICIT_SELECT_V1` — JPG로 저장된 2프레임 MPO 포함 모든 실제 MPO를 서버가 decoded-container 기준 식별 → React에서 각 프레임 미리보기 → 인증된 Actor가 0 또는 1을 직접 선택/확인 → 서버에서 원본 Bytes SHA, 원본 전체 프레임 수, 프레임 index, EXIF orientation, ICC 입력/변환 SHA, sRGB-normalized SHA를 영속 Job+Upload Request CAS에 결속 → 취소·동시 중복·변조·TTL 실패는 Fail-Closed. 제품 원본에는 사용권이 있어야 하며 프레임별 제품·라벨 비교가 필요합니다.
- **대체 가능한 승인안:** `REJECT_MULTIFRAME_V1` — 실제 제품에서는 단일 프레임만 허용하되 기존 원본 24장 중 15장 MPO를 그대로 업로드할 수 없으므로 전처리 운영 책임/품질 기준/UX 문구를 확정해야 합니다.
- **반드시 확정할 계약:** Image Owner 정규화 DTO 필드·소스 SHA·ICC/EXIF 처리, FE Owner confirmation / reload / secure SSO UX, PM beta 적용 범위와 기존 v2/MPO 자동 프레임0 불변 경계. A5-1D-R1의 SQLite CAS 재사용은 가능하지만 TEST_ONLY HTTP Bridge를 배포하지 않습니다.
- **현재:** 공식 Owner/FE/PM 승인 없음. A5-1E는 새로운 Signed Beta 입력에서 모든 다중 프레임을 거부합니다.

### 결정 B — 동일 SKU 사용권과 실제 A/C v3 브랜드 품질

- **증빙 요청:** 동일 실제 SKU의 사진 2~5장(각 원본 SHA, 촬영·취득·가공권, 시험/광고/외부 Provider 전송 권한), 원본 패키지·제품·로고·라벨 식별 마스크, 검수자(Owner/PM), 프레임별 실제품 동일성 및 디자인 샘플 A/C 선택, Head/Sub/CTA Font·Contrast·Crop·Safe Zone·360/390px 검수.
- **보관:** 실제 원본/사용권 문서/마스크는 GitHub PR, 공개 ZIP 또는 채팅이 아닌 승인된 보호 폴더에. Git에는 문서·이미지 내용이 아닌 승인 증거 SHA/지문만 남깁니다. PM은 원본 사진이 다른 제품군의 파일명 유사성만으로 동일 SKU라는 결정을 하지 않습니다.
- **기술 추가:** `demo_staging/live/a51f_product_rights_authority.py`는 private rights evidence, Owner+PM 독립 Ed25519 서명, Actor·Job·SKU·원본 애셋 전체 SHA·Provider·모드·화면비·소스 커밋·유효기간을 검증한 뒤에만 해당 **권리 검증 단계**를 통과시킵니다. **권리 승인 발행기 아님**. 실제 담당자의 법률/지식재산 검토를 대체하지 않으며 금전/배포 허가는 별도입니다. 직전 통과된 Signed A51B Profile v3의 4개 Provider-related Boolean은 여전히 false, 실제 유료 경로는 차단되어 있습니다.
- **Owner/PM 요청 사항:** 검토 가능한 실제 샘플, 원본/License 근거, signed rights decision과 approved Provider ID, signed Profile v3/Font/Mask/Policy Epoch 및 실제 CTA 가독성·패키지/라벨 보존 승인. 불확실하면 사용권·외부 전달은 계속 HOLD.

### 결정 C — A-only 배포 및 비용 권한

- **PM·Infra:** 구 GCP A `9879eb0f85747312a224ecd898aaff84d834590b`는 A5-1E/A5-1F 미배포. 별도 승인한 **새 A-only 경로**와 Signed Tailscale Serve/Actor 검증, 기존 A·B·Live·QA 비변경, Source/Tree/JS/CSS/Font SHA 및 실행 런타임, WAL-consistent DB Backup/Restore, 실제 rollback 복귀 여부 수용.
- **PM Finance:** 사용 Provider/Model/Quality/사전 가격표·실제 지출 기준, USD 예산 Hard Cap 상한·최대 시도 횟수·승인 Actor, 별도 보호된 Worker-only API secret, Ed25519 비용 승인 및 Actor·Queue·Cost·Owner Provider Attempt·Usage·Receipt 3중/다중 대사. `BILLING_UNKNOWN`은 수동 대사 전 절대 중복 재호출 금지.
- **배포 조건:** **GCP 쓰기 변경, DB 신규 생성, 모델 API 과금은 각각 명시적 승인 이후에만 진행**. 최신 HEAD를 GCP에 올리는 행위만으로 배포 승인 완료 또는 실모델 E2E 6/6를 선언하지 않습니다.

## 2. Owner/PM 실제 회신 및 증거를 기록할 필드

| 주체 | 회신/서명할 항목 | 필수 정본 링크·SHA·증빙 | 현재 |
|---|---|---|---|
| Image Owner #24 | MPO 선택/정규화 DTO + 권리 확인 원본/마스크/폰트/프로필 | 승인된 정책 버전, 대표 SKU 및 SHA, 실제 제품 라벨 픽셀 검수 증거 | PENDING |
| FE Owner #26 | 선택 UI·Signed SSO Actor·Upload Request 결속·브라우저별 실패/재접속 | 화면 검수 결과, 정규화 UX/에러, 팀 베타 고정 빌드 SHA | PENDING |
| PM 이태민 | MPO Beta 옵션/승인 범위, 실제 라이선스·시각 품질, A-only 배포, 실모델 예산 | 서명된 정책 Epoch, 재무 Hard Cap, GCP 변경 승인 원문·일시 | PENDING |
| C-A 독립 감사 | 신규 실제 계약·권리·원장·보안·배포·E2E 차등 수용 | 실제 고정 소스/배포/Rollback 증거·Provider Receipts | NOT_AUDITED |

**중요:** 실제 승인/서명 파일은 수신 전 존재한다고 표시하지 않습니다. 외부 정보 없이 추정한 USD 상한, 사용권, 사진 출처, 브랜드 승인 또는 서명 시각을 임의로 기록하지 않습니다.

## 3. 현재 기술 상태

- 기존 C-A51E 독립 통합 수용은 유지합니다. 신규 A5-1F source-rights verifier는 **미감사 추가 구현**이며 기존 Accepted 범위의 무단 승격이 아닙니다.
- 무료·비과금 개발은 계속 GO. 실제 GCP 및 유료 호출 **HOLD**.
- 현재 Signed A51B Profile v3는 Composed 4:5 한정, 4개 제품 승인 Boolean false이고, 같은 코드가 실제 LIVE 실행을 차단합니다. 6개 생성 방식·비율의 **전체 유료 Runtime 활성화 계약은 미완성**입니다. C-A/Owner/PM의 versioned 계약 없이 단순 flag 조작으로 해제하지 않습니다.
- 실모델 독립 6 Job: **0/6**. 실제 팀 UAT: 미수행. `FULL_FEATURE_BETA_DELIVERY_HOLD` / `COMMERCIAL_RELEASE_READY=NO`.
