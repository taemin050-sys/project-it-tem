# IT-TEM P03 Track A — A5-0 4:5 Composed CTA·Typography Profile v3 제안 및 Owner/PM 결정 요청

2026-11-10 KST. STATUS: A5_0_DESIGN_PROPOSALS_PREPARED / OWNER_PM_DECISION_PENDING / A5_1_IMPLEMENTATION_HOLD.

## 1. 공식 감사 인수와 변경 경계

C-A4 정본: IT_TEM_P03_C_A4_OFFICIAL_REACT_BROWSER_INDEPENDENT_AUDIT_20261110.md, SHA256 25d24cab2af9c7a6633ef5ffb5ccde1ece69d151b7fd13ad5dbebdfd9e37a498. 공식 수용 기준 HEAD 4f87c4c4ff0c4cbf08dcbb2c03f8de826119d925 / Tree ca1082c34e3999b062c06d14995a6b281223e6b4.

A4-0 Owner 계약 수용; A4-1 OFFLINE_FIXTURE 공식 React Chrome 15단계 수용; P1 A41_PRODUCT_CTA_01_CONFIRMED_HOLD. 기존 A2/A3/A3R/A3R.1 안전 게이트 재개발 불필요.

**이미 결정된 제품 정책:** 신규 4:5 Composed 광고 이미지에 CTA를 1회 포함해야 한다. 기존 Image Owner v2 feed-4:5는 Head/Sub만 포함하고 CTA를 platform으로 설정해 미합성한다. 기존 Receipt는 cta_placement=platform 및 omitted_image_fields=["cta"]. 이 부분을 제품 기능 PASS로 오인하지 않는다.

**미결정:** 정확한 v3 CTA/Profile 위치·스타일·모바일·폰트·실제 제품/라벨 보호 방식·상업 라이선스·품질 점수. 9:16 CTA는 별도의 DECISION_PENDING_PM_OWNER. A5-0에서 Image Owner 원본, 제품 Serving, 과거 Job/Receipt, Track B/GCP, GitHub PR/dev를 변경하지 않음.

## 2. 동일 승인 카피 및 비교 기준

| 필드 | 승인 문구 | SHA256 UTF-8 |
|---|---|---|
| Headline | 데일리 크림 | fed16d23a8dc3a78ffa55d4412e11866dc687b469f311d153779e67198bff807 |
| Subcopy | 매일 촉촉한 사용감 | ba116b354fb1441d0b11556547acc165d155f5389046a978ff814431248a28e6 |
| CTA | 지금 만나보세요 | 29f1185e55a4d3499794d36ada72dda3556cb88a0bd220690a9e0811a5fbc0be |

원본: docs/integration/evidence/A50_20261110/A41_ORIGINAL_WITHOUT_CTA.png. 원본 A4-1 PNG SHA a43bd648a8803a875d7199b9ca10af70fb585e9f2ed29431d5c516fa62e50179과 동일 바이트.

목업은 동일 A4-1 무과금 단색 QA Fixture Candidate를 바탕으로 중립적인 **무브랜드·무라벨 가상 용기 실루엣**을 각 3안에 동일하게 표시한다. 원본에 없는 실루엣은 글자와 객체의 간섭 평가를 위한 공통 시각 보조물일 뿐 실제 사진/모델 결과/제품 충실도가 아니다.

기존 Image Owner v2의 product target (466,418,611,1183)은 실제 검출된 제품·라벨 Bounding Box가 아닌 구도 목표 영역이다. Mock에서 이 목표와 Layout Region의 직사각 교차 0을 검증했으나 실물 제품 보호는 NOT_AUDITED.

QA 내부 시각화는 macOS AppleGothic.ttf (시스템 경로 참조, 파일 미복제)를 사용했다. 승인 카피의 19종 고유 문자 글리프 19/19 존재. 상용 서체 배포권과 실제 운영 렌더링 라이선스는 NOT_AUDITED / HOLD.

## 3. 디자인 후보 3종 — 제안 좌표, 승인 아님

모두 1080×1350 PNG, 동일 Headline/Subcopy/CTA 원문 각 1회, 390/360 모바일 이미지, 동일 합성 Fixture 및 서체 SHA. LTRB 단위 px. 원래의 UI_SAFE=(64,64,1016,1286) 내부, 임시 product target과 겹침 없음.

| 후보 | Headline LTRB | Subcopy LTRB | CTA LTRB | CTA 크기 / 360 환산 | 차이점 |
|---|---|---|---|---|---|
| A Editorial Center | (86,86,994,218) | (86,246,994,390) | (244,1200,836,1280) | 47px / 15.7px | 중앙 위계와 하단 Pill CTA, 가장 직관적인 정보 흐름 |
| B Editorial Left | (96,90,970,216) | (96,242,960,392) | (94,1200,810,1280) | 49px / 16.3px | 좌측 정렬·여백, 아웃라인 CTA. 긴 Headline 일반화 유의 |
| C Contrast Action | (78,84,1002,215) | (84,245,996,392) | (68,1198,1012,1282) | 50px / 16.7px | 상단 Typography와 고대비 하단 Action Bar 분리 |

**비교물:** docs/integration/evidence/A50_20261110/A50_OWNER_PM_4UP_COMPARISON.png (기존 원본+3종), A_EDITORIAL_CENTER.png / B_EDITORIAL_LEFT.png / C_CONTRAST_ACTION.png 각각 원본 크기, 각 후보의 _mobile_390.png 및 _mobile_360.png, SHA를 적은 A50_DESIGN_PROPOSALS_MANIFEST.json, 재현 스크립트 scripts/a50_composed45_design_concepts.py.

CTA는 Mock에서 단일 draw 호출만 수행한다. Copy 문자 삭제/자동 줄임 없음. Fit 실패 시 A50_COPY_OVERFLOW_FAIL_CLOSED. 단, 실제 제품이 목표 상자를 넘거나 레이아웃 하단 간격이 작으면 보호 실패 가능 — 실제 제품 Bounding Box/segmentation과 사람 검수 완료 전 안전한 디자인으로 간주 금지.

벤치마크 4개 사용 범위: REF01_DALEAF_TYPE_HIERARCHY (정보 위계), REF02_ULOS_DYNAMIC_TYPE (동적 타이포그래피), REF03_DASHU_PROMOTIONAL_NUMERALS (대조/강조), REF04_DRSEED_EDITORIAL_BOTANICAL (여백/에디토리얼). 출처: /Volumes/SSD 4T/z_ai_asset/P03_it-tem/knowledge/benchmarks/2026-11-09-korean-ad-typography/references/. 실제 타사 광고 이미지·브랜드·문구·로고·타사 라이선스 자산을 복제하지 않음. 과거 BENCHMARK_AND_QA_SPEC.md는 현재 미존재.

## 4. Owner 승인 후에만 유효할 v3 Profile 제안 계약

필수 키: design_profile_id, profile_version, policy_epoch, aspect_ratio=4:5, generation_mode=composed, native_size, final_size=(1080,1350), approved_headline_region, approved_subcopy_region, approved_cta_region, cta_placement=image, font_family_ref, font_weight, font_file_sha, font_license_evidence_sha, product_detected_protected_regions, layout_sha, input_sha, copy_sha, review_sha, generation, approval_sha, prompt_context_sha, image_attempt_id/version, image_sha, bound_context_sha, composition_receipt_sha, final_png_sha, caption_sha, source_commit/build_sha.

- 새 Job 생성 시 프로필/정책/폰트/Approval 고정; 과거 v2 Job은 정확히 v2로 재현, 완료 Job·Receipt·Approval·Artifact SHA 변경 금지.
- Composed는 승인 Head/Sub/CTA 서버 1회 합성, 원본 UTF-8 SHA와 실제 Receipt placements.headline/subline/cta 각각 결속. Prompt는 AI에게 광고 글자를 그림에 중복 그리라고 지시하지 않음. Freeform은 모델 자체 렌더라 서버 텍스트 Overlay 금지.
- 글리프 부족·사용권 불확실·텍스트 영역 충돌/범위 초과·시선/대비 불량·실제 제품/라벨 보호영역 미검출 또는 충돌은 Fail-Closed/HOLD. 현재 타깃 구도만으로 제품 충실도 PASS 선언 금지.
- CTA 좌표/폰트 크기·배경·버튼의 정확한 규칙과 최소 수용선은 **Owner/PM 서명으로 정해진 버전 계약**에서만 승격.
- 기존 Actor ACL, 규제, Approval CAS, 단일후보 1장, 거절 후 명시적 재생성, 원장/과금 HOLD, 프롬프트/Artifact SHA 검증 보존.
- 3:4 v2를 승인 없이 변경하지 않음. 9:16 CTA=DECISION_PENDING_PM_OWNER 별도 관리.

## 5. 의사결정 매트릭스 (Owner+PM 승인 대기)

| ID | 필요 결정 | 승인권/검토증거 | 상태 |
|---|---|---|---|
| D50-01 | 신규 4:5 Composed 이미지 내 CTA 필수 | 기존 PM/Owner 계약 | REQUIRED — ALREADY DECIDED |
| D50-02 | A/B/C 디자인 방향 선택 또는 별도 수정 지시 | Image Owner + PM / 4-up, 원본, 모바일 비교 | PENDING |
| D50-03 | 정확한 CTA/Headline/Subcopy 좌표, 버전 ID·SHA, CTA 배경·줄바꿈 | Image Owner 제안, PM 확정 | PENDING |
| D50-04 | 배포 가능한 폰트·서체 가중치·정식 라이선스 증빙 | Image Owner + PM/법무 | HOLD |
| D50-05 | 실제 제품·브랜드·라벨 영역 검출/충돌 관리 및 수동 Override | Image Owner + PM | NOT_AUDITED |
| D50-06 | 자간·행간·가독성·대비·최소 크기·Overflow 실패 규정 | Image Owner+PM | PENDING |
| D50-07 | 시각/상업 품질 가중치·최저 수용점·Human Review | PM+Owner | PENDING |
| D50-08 | 9:16 CTA 이미지/플랫폼 결정 | PM+Image Owner | DECISION_PENDING_PM_OWNER |
| D50-09 | 신규 Job v3 전환, Legacy v2 보존, Rollback 방법 | Serving+PM+Image Owner | A5_1_HOLD |

승인 기록 요구 필드: decision_id, reviewer_role, selected_mock_sha256, exact_profile_id/version, exact_layout_json_sha256, font_license_evidence_sha, owner_source_commit, PM_decision_date, approval_or_rejection, effective_policy_epoch, rationale. 내부 제안 좌표를 개발 기본값으로 자동 채택 금지.

## 6. 수용 경계 및 다음 작업

A5-0의 기계 검증: 3종 Mock, Original SHA, 동일 Copy SHA, 모든 1080×1350, 별도 390/360 모바일 이미지, 대상 Safe 영역 교차 0, SHA Manifest. 이는 CODE/PROPOSAL에 해당하며 HUMAN_PM_ACCEPTED 또는 VISUAL_REVIEW_PASS가 아니다.

A5-1 구현 시작은 D50-02/03/04/05/06 승인된 Owner 계약이 필요한 후속 게이트. 기존 Owner 소스를 무단 수정·병합하지 않고 승인된 Serving Adapter 또는 버전 프로필 방식으로 구현한 뒤 A4-1 전체 Chrome·새 Receipt/CTA·실제 비교와 C-A 차등감사를 수행한다.

A4-2 다섯 모드·비율은 이 결정과 병행해 무과금 브라우저 기능만 검증 가능. 실제 VLM/Research/Freeform 한글 모델 품질, 사용권, PM 인간평가, 실Provider E2E, GCP 배포, 유료 Worker 및 출시 상태는 별도로 HOLD 유지.

VERDICT: A5_0_DESIGN_CONCEPTS_PREPARED / OWNER_PM_APPROVAL_PENDING / A5_1_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / PAID_WORKER_HOLD / NOT_RELEASE_READY.
