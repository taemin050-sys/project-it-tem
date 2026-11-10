# IT-TEM P03 Track A — A5-0D Owner/PM 결정 준비 패키지 (결정 요청용)

**2026-11-10 KST | STATUS: REVIEW_READY / SIGNATURES_0 / A5_1_IMPLEMENTATION_HOLD**
이 문서는 **서명 직전 검토 기준을 명료화한 제안서**입니다. 실제 Owner #24, PM의 승인·선택 또는 상용화 허가가 기록됐다는 뜻이 아닙니다.

## 1. 확정된 사실과 남은 결정

- C-A4.2/A5-0 최종 독립감사: Track A HEAD `3842db04123fc8a8c681a2bf50c90dc82464c143`, Tree `03e9d11eaa0d3e02d57f09367fa571f8d0a65580`. 감사 보고서 `audit/track-a/IT_TEM_P03_C_A42_A50_DIFFERENTIAL_INDEPENDENT_AUDIT_20261110.md`, SHA-256 `360674367278527c0a6ea5cf099212417b16418e199edffb541a3dc72657e940`. 제출 때 직접 확인 완료.
- `C_A42_FIVE_OFFICIAL_REACT_FIXTURE_BROWSER_E2E_ACCEPTED` 및 기존 S01 수용으로 6/6 **무과금 공식 React Chrome 기능** 독립 수용. 실모델·광고 품질·상용 라이선스 및 출시 수용은 아니다.
- `C_A50_DESIGN_MOCKS_REPRODUCIBLE_PROPOSAL_ACCEPTED`: A/B/C 목업 바이트 재현성 수용. **`A41_PRODUCT_CTA_01_HOLD` 유지**, 실제 Image Owner v2 `feed-4:5` CTA 누락은 미수정.
- 이미 결정된 요구는 **신규 4:5 Composed 이미지 내 승인 CTA를 정확히 1회 넣는 것**. 미결정은 v3 좌표/폰트/제품 충실도/모바일 기준/평가·운영 방식. **9:16 CTA는 별도 `DECISION_PENDING_PM_OWNER`**.
- 실행 소스 `src/image_generation/layout_profiles.py` / `src/image_generation/composition.py` / `app/src` / `demo_staging/live` 변경하지 않는 설계 문서 단계. Track B/공식 PR/dev/GCP/운영 Job·DB·Receipt·Artifact/Provider 비용 변경 금지.

## 2. C-A 권고에 기반한 디자인 방향 (승인 아님)

| 검토 우선순위 | 후보·실제 SHA256 | 위치 및 용도 제안 | 미해결 제약 |
|---|---|---|---|
| **1** | **A Editorial Center** `630ccd5f64e2d525a4562ef16677491e575256072261ac42abc2b395edb565de` | 기본형 v3 검토 우선. 중앙 카피·독립 Pill CTA | 360px CTA 15.67px, 안전프레임 하단 2px 환산 ⇒ 권고 최소값 검토 필요 |
| **2** | **C Contrast Action** `ca63c30ab2fd98d98425c535b896898911ac9f72651d0f3f2230206de66b524b` | 프로모션·강조형 선택 프로필 방향 | 360px CTA 16.67px, 안전프레임 하단 1.33px 환산; UI 크롭·브랜드 톤 검증 필요 |
| **3** | **B Editorial Left** `940634bfd74ea86b71b9d1624022874f6a72f552e9ecdd5cc5b84594e8a36693` | 편집/브랜드형 대안 보존, 폐기 금지 | 360px CTA 16.33px, Safe 하단 2px; 아웃라인 CTA 강조 약함 |

동일 승인 Copy: Headline **데일리 크림** / Subcopy **매일 촉촉한 사용감** / CTA **지금 만나보세요**. 기존 A4-1 PNG SHA `a43bd648a8803a875d7199b9ca10af70fb585e9f2ed29431d5c516fa62e50179`와 4-up 비교 `docs/integration/evidence/A50_20261110/A50_OWNER_PM_4UP_COMPARISON.png`, 단품 3종 및 360/390 프리뷰 검토 필수. 제품 용기는 무브랜드 Synthetic Fixture임.

### A/B/C CTA 계측 및 예시 임계값 실패

정본: `docs/integration/evidence/A50D_20261110/A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json`

| 항목 | A | B | C | 제안 검토 임계값 (**미승인**) |
|---|---:|---:|---:|---|
| CTA 크기 360px 환산 | 15.67px | 16.33px | 16.67px | ≥16px |
| Safe Frame 하단 360px 환산 | 2.00px | 2.00px | 1.33px | ≥12px |
| CTA 글자 대비(버튼 배경) | 10.93:1 | 6.77:1 | 9.96:1 | ≥4.5:1 |
| CTA 상단 ↔ **미검출 구도 target** 하단 (1080 기준) | 17px | 17px | 15px | 실물 객체 검사 전 미확정 |
| 해당 예시 임계값 동시 충족 | NO | NO | NO | **Owner/PM 미승인·적합성 아님** |

여기서 Safe Frame=(64,64,1016,1286)과의 inset은 **기존 레이아웃 내부 기하**이지 Meta 플랫폼 공식 UI safe-zone 기준이 아니다. 4:5 피드 Cropping·미디어 축소, UI 오버레이 및 실제 브랜드/라벨 픽셀은 별도 실제 테스트가 필요하다. WCAG 대비 수치는 **버튼 글자↔배경 색상 두 값만** 기준으로 계산한 색 대비 예시이며 광고 시각적 합격 점수가 아니다.

**핵심 구조적 문제:** 현재 가상 제품 target 하단 y=1183, Safe Frame 하단 y=1286이며, 상용을 가정해 모바일 Safe inset/CTA 글자를 동시에 늘리려면 아래 CTA에 충분한 세로 공간이 부족할 수 있다. 단순히 A의 CTA 글자 1px 증가만으로 해결할 문제가 아니며, 실제 제품의 객체 마스크/브랜드 라벨을 확인한 뒤 카피/제품 레이아웃 재배치 또는 CTA band 확보가 필요하다. **임의로 CTA 픽셀 박스를 정식 계약으로 고정하지 않는다.**

## 3. 폰트 권한 D50-04 — 공식 라이선스 확인 후보 (채택 전 단계)

**현재 목업용 AppleGothic.ttf**: Mac 로컬 디자인 Mock에만 사용. 실서버 배포·상용 이미지 생산·폰트 파일 재배포 권한이 확인된 증거가 없으므로 **상용 승인 근거로 쓰지 않는다**. 파일은 프로젝트로 복사하지 않았으며 복사하지 않는다.

| 검토용 후보 | 공급처·라이선스 원문 | 현재 판정 | 추가 결정 근거 |
|---|---|---|---|
| Pretendard | https://github.com/orioncactus/pretendard/blob/main/LICENSE 및 프로젝트 한국어 README; SIL OFL-1.1 | **사용권 출처 확인, 실제 파일 미선정** | 버전/Weight/실제 다운로드 Font SHA, 원문 라이선스/저작권 공지, 배포 이미지·서버 설치 범위, 한글 렌더 검증 |
| Noto Sans CJK KR | https://github.com/notofonts/noto-cjk (License + Sans README); SIL OFL-1.1 | **대안 출처 확인, 실제 파일 미선정** | 정확한 KR Subset/Weight/Version/Font SHA/라이선스 SHA, 라이선스 공지 및 임베딩·서버 권한 검토 |

**추가 발견 — 이미 정식 FE에 설치된 Pretendard 사용 자산:** `app/src/main.tsx`는 `pretendard/dist/web/variable/pretendardvariable.css`를 사용하며 `app/package-lock.json`은 `pretendard@1.3.9`를 고정한다. Mac Studio 설치 패키지에 서버 합성용으로 기술 검토 가능한 `PretendardVariable.ttf`가 **로컬에 존재함**을 확인했으며 그 파일 SHA256은 `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22`, 설치 패키지의 SIL OFL-1.1 `LICENSE.txt` SHA256은 `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`, `app/package-lock.json` SHA256은 `de5d56ac4eff9570c11b2dcb9c939088073f500537df02eaa25019b49fb0b6e7`이다. Pillow/FreeType에서 이 Variable TTF 로드 성공, 해당 QA Copy 문자 19/19 cmap 존재 확인. 증거: `docs/integration/evidence/A50D_20261110/A50D_EXISTING_FE_PRETENDARD_LICENSE_CANDIDATE.json`. **실제 폰트 파일은 증거에 복사하지 않았다.** 로컬 설치 패키지는 Git이 추적하는 제품 바이너리가 아니므로 정식 서버에 사용할 때 패키지 해시·정식 Font SHA·원문 License Notice 및 통제된 복제/배포를 재현하고, 정확한 Weight·렌더 결과·상업 사용 범위를 Owner/PM이 서명해야 한다. **해시가 발견됐다는 사실 자체는 D50-04 승인이나 A5-1 구현 허가가 아니다.**

두 upstream은 상업적 사용을 허용하는 OFL 계열을 명시하지만, **정확한 실제 배포 방식·Weight/Font 선택·License Evidence SHA의 승인 없이 D50-04를 PASS하지 않는다.** 정본 글꼴 파일은 사용자에게 공유하거나 결과물에 첨부하지 않는다. 승인자는 Name/Version/Weight/FileSHA/EvidenceSHA/서버 사용 범위를 함께 남겨야 한다.

## 4. 최종 Profile v3 결정 사항 — 서명용 D50 목록

정형 Decision Register: `docs/integration/BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv`. 프로필 형식 제안: `docs/integration/BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json` (status `DRAFT_NOT_APPROVED`, selected_profile=null, 임의 Profile ID/Version/Epoch 없음). 정식 승인된 JSON과 동일하다고 주장 금지.

| 결정 | Owner/PM이 명시할 결과 | 현재 상태 |
|---|---|---|
| D50-01 | 신규 4:5 Composed CTA **1회 이미지 내 표시** | PM 요구 이미 확정 |
| **D50-02** | A 기본·C 옵션 방향 채택/변경, B 보존 여부 및 각 Mock SHA | PENDING |
| **D50-03** | 신규 Profile IDs/Versions, Head/Sub/CTA 정확한 Pixel LTRB, 표준 JSON canonical hash, 색상·정렬·CTA 배경 | PENDING |
| **D50-04** | 배포 가능한 Font Family/Weight/Version/바이트 SHA, License Notice·Evidence SHA, 서버 상용 사용권 | HOLD |
| **D50-05** | 실제 제품·패키지·라벨·로고 Mask 검출과 collision, 미검출/긴급 manual review 기준 | NOT_AUDITED |
| **D50-06** | 360/390 최저 CTA 폰트, 플랫폼 Cropping·Safe Zone, 여백·색 대비·문구 길이/Overflow Fail-Closed | PENDING |
| **D50-07** | 사람 평가 항목·가중치/최저점/Reject Rule, PM/Owner 판단 | PENDING |
| D50-08 | **9:16 CTA 위치** 별도 결정 | DECISION_PENDING_PM_OWNER |
| **D50-09** | 버전 잠금·신규 Job에만 적용·기존 v2 보존·Rollback·Policy Epoch | A5-1 HOLD |

**권고 평가표 초안 (아직 승인 점수 아님):** 모든 광고는 Copy/규제·Font 사용권·제품/라벨 침범·CTA 1회·SHA/Actor 안전 규칙을 **독립 Hard Gate**로 먼저 통과. 그 후 사람 평가에서 (a) 한국어 가독성·계층 30점, (b) CTA 발견성·행동 유도 25점, (c) 제품/브랜드 시각 통합 20점, (d) 조형 완성도 15점, (e) 360/390 기기 크롭/읽기 10점 = 총 100점. 실제 수용 Cutoff/평가자 수/일치도/영역별 최저 점수는 PM·Owner가 정한다. 본 문서에서 기본 합격선이나 점수를 임의 확정하지 않는다.

**리뷰 후 요구 필드:** decision_id, status=APPROVED/REJECTED/REVISION_REQUESTED, reviewer_role, signed_identity_ref, reviewer_timestamp, selected_mock_sha256, approved_profile_id/version, exact_signed_layout_json_sha256, font_file_sha256, font_license_evidence_sha256, image_owner_source_commit, effective_policy_epoch, legacy_v2_rollback_plan_ref, review_evidence_ref, rationale. 두 역할의 서명과 필요한 보호증거가 하나라도 빠지면 A5-1은 HOLD. D50-08 별도 승인 없이 9:16은 계속 HOLD.

## 5. 구현 경계·필수 A5-1 Gate (지금은 미승인)

- 새 4:5 Composed Job만 정식 Owner/PM v3 Profile/Font/Policy/Approval SHA를 **Job 생성 시 immutable snapshot**; 이미 생성된/처리 중 v2 Job은 완료·재시도 과정에서 자동 v3 승격 금지. 과거 Receipt·Blob·Caption·요청 SHA 변조/마이그레이션 금지.
- Serving Adapter가 서명된 Profile 버전과 Owner #24 원본을 분리해서 수용; Owner 파일 무단 덮어쓰기 금지, FE#26/Text#27와 계약 충돌 우선권 보호. Rollback은 이후 신규 Job 라우팅만 승인된 이전 버전으로 전환, 기존 Job 불변.
- `CTA=image`, 승인 Head/Sub/CTA UTF-8 각각의 `placements.*.text_sha256`, Font/Profile/Layout/Approval/Generation/Policy Epoch/Attempt/Final SHA가 결속된 Receipt. 실제 상품 마스크가 없는 경우 자동 제품 보호 PASS 금지. 겹침/Overflow/글리프/폰트 권한 미확인은 Fail-Closed.
- Freeform에 서버 텍스트 오버레이 금지, 3:4 기존 Profile 불변, 9:16 별도 CTA 정책 미결정. 이미지 후보 1개, 승인 CAS·아티팩트·과금·실모델 호출 통제 유지.
- 승인 완료 후에만 A5-1 제품 구현, 4:5 Chrome 완전 재생/구버전 Job 역호환/모바일/사람 광고 검수, 신규 HEAD/Tree/CLEAN 및 C-A 차등감사. 실 Provider/GCP/유료 Worker는 별도 승인이다.

## 6. PM·Image Owner 검토 시 전달할 결정 요청 (복사 가능)

**검토 주제:** IT-TEM 4:5 Composed on-image CTA v3 — A 기본 / C 강조 대안 / B 브랜드 대안.
**첨부:** A50_OWNER_PM_4UP_COMPARISON.png, 각 1080/360/390 PNG, A50D Geometry JSON, Draft Contract JSON, Decision Register CSV.
**요청:** D50-02/03/04/05/06/07/09 각 항목 승인/수정 요청과 근거, 본인의 역할·일시·선택 Mock SHA·정본 Profile JSON SHA/Font License SHA 및 Epoch를 기재해 주십시오. 기존 v2가 완성된 작업에 소급 적용되지 않는지 승인해 주십시오.
**주의:** 현 A/B/C 목업은 제안 Safe 여백 기준을 모두 충족하지 못하므로 **방향 승인**과 **최종 Pixel 좌표/폰트 승인**을 분리해 결정해 주십시오. 9:16 CTA는 별도 의제로 남겨 둡니다.

**최종 상태:** `A5_0D_REVIEW_PACKAGE_PREPARED / OWNER_PM_DECISION_NOT_RECEIVED / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / REAL_PROVIDER_E2E_NOT_AUDITED / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
