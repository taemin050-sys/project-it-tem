# IT-TEM P03 Track A — A5-0E CTA·Product Reflow 비교안 v2 및 Owner/PM 결정 요청

**2026-11-10 KST | `A5_0E_TWO_REFLOW_MOCKS_SYNTHETIC_VERIFIED / D50_REVISION_REVIEW_REQUIRED / A5_1_IMPLEMENTATION_HOLD`**

## 1. 왜 CTA 상향 이동만으로 해결하지 않는가

C-A5-0D 독립감사 `IT_TEM_P03_C_A50D_OWNER_PM_DECISION_READINESS_INDEPENDENT_AUDIT_20261110.md` (SHA `6c8a8484cc5ab6ef8cf6bb2c78fd994e717be00ac4df931ff53cd1e7fc0bf475`)가 확인한 바와 같이, A/B/C 하단 CTA를 그대로 위로 30/30/32px 이동하면 기존 **가상 product target**과 각각 13/13/17px 세로로 겹친다. 여기서 대상은 실제 상품·라벨의 검출 마스크가 아닌 Owner v2 아트디렉션용 target `(466,418,611,1183)`이다.

본 v2 비교안은 CTA만 올리지 않고 **제품 가상 목표영역의 상단 이동·높이 축소와 CTA band 확보를 함께 제안**한다. 이것은 검증 가능한 지오메트리 실험이지 실제 상업 광고의 최종 안전한 좌표가 아니다. 4:5 Composed에 승인 카피 Head/Sub/CTA를 **모두 정확하게 1회 포함해야 한다는 PM 요구**는 그대로 준수한다.

## 2. 개선 A/C 후보 vs 원본

1080×1350 네이티브 px; LTRB는 좌상단 원점에서 (left,top,right,bottom). FE에 이미 잠금된 로컬 `pretendard@1.3.9` Variable TTF를 **시뮬레이션에서만** 로드했으며, File SHA `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22`, OFL LICENSE SHA `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`. 폰트 바이트는 증거·ZIP에 넣지 않는다. 서버 배포 및 실제 Weight/License 승인 `D50-04 HOLD`.

| 항목 | 기존 A | **개선 A Reflow (기본형 검토)** | 기존 C | **개선 C Reflow (행동 유도형 검토)** |
|---|---|---|---|---|
| Product Target bottom (가상 px) | 1183 | **1045** | 1183 | **1035** |
| CTA LTRB (px) | 244,1200,836,1280 | **218,1108,862,1238** | 68,1198,1012,1282 | **80,1094,1000,1236** |
| 360px CTA 글자 | 15.67px | **20.00px** | 16.67px | **20.00px** |
| 360px Safe Frame 하단 | 2.00px | **16.00px** | 1.33px | **16.67px** |
| CTA ↔ 가상 Target 세로 간격 | 17px | **63px** | 15px | **59px** |
| CTA 특징 | 중앙 Pill | 더 명확한 중앙 Pill | 전면 Action Bar | 제품 구도와 분리한 Action Bar |
| 실제 제품·라벨 마스크 | 없음 | **없음 — 미검증** | 없음 | **없음 — 미검증** |

**협의용 제안 최소값**: 360px에서 CTA ≥16px, 내부 Safe Frame 하단 ≥12px, CTA 전경/배경 명목 대비 ≥4.5:1. 개선 A/C는 *이 기하학적 가안*에 부합하나, 임계값 자체가 Owner/PM 승인된 기준이 아니고 실제 플랫폼 UI 크롭/제품 마스크를 포함하지 않기 때문에 `VISUAL_REVIEW_PASS`가 아니다.

**B Editorial Left**는 원본 A5-0 `B_EDITORIAL_LEFT.png`, SHA `940634bfd74ea86b71b9d1624022874f6a72f552e9ecdd5cc5b84594e8a36693`를 그대로 **브랜드 에디토리얼 대안**으로 보존. B가 기존 협의용 하단 기준 미충족임을 숨기거나 자동 채택하지 않는다. B 개선은 Owner/PM 수정요청 후 별도 버전으로 추진.

### 시각자료 및 SHA 결속

- 전후 4분할: `docs/integration/evidence/A50E_20261110/A50E_A_C_BEFORE_AFTER_COMPARISON.png`
- 개선 1080 원본: `A_REFLOW_EDITORIAL_CENTER.png` / `C_REFLOW_CONTRAST_ACTION.png`
- 360/390 모바일 크기별 `*_mobile_360.png`, `*_mobile_390.png`
- **하단 12px 자르기 시뮬레이션**: `*_mobile_360_crop12_simulation.png`, `*_mobile_390_crop12_simulation.png` — Instagram/Meta의 공식 크롭 정책을 재현하거나 인증하지 않는다.
- 정형 설계·폰트·문구·구도·원본 SHA: `A50E_REFLOW_DESIGN_MANIFEST.json`.
- 자동 충돌·장문·1~2줄·Small Product 마스크 실험: `A50E_SYNTHETIC_STRESS_RESULTS.json`.
- 무과금 재현 스크립트: `scripts/a50e_composed45_product_cta_reflow_concepts.py`, 검사 `tests/product_e2e/test_a50e_product_cta_reflow_concepts.py`.
- 동일 Copy UTF-8 SHA: Head `fed16d23a8dc3a78ffa55d4412e11866dc687b469f311d153779e67198bff807`; Sub `ba116b354fb1441d0b11556547acc165d155f5389046a978ff814431248a28e6`; CTA `29f1185e55a4d3499794d36ada72dda3556cb88a0bd220690a9e0811a5fbc0be`.
- 모든 광고 소재 이미지는 **A4-1 무과금 Synthetic 배경/무브랜드 가상 실루엣**, 실제 상품 사진·로고/제품 라벨·AI 모델 결과가 아님. 원본 A50 PNG·이미지·SHA를 수정하지 않음.

## 3. 안전성/품질 부정 테스트와 실제 제품 보호의 차이

합성 Fixture에서 9개 사례를 검사한다: (1) 실제 마스크 없음 시 Reject, (2) 대상보다 큰 패키지 마스크 Reject, (3) CTA/마스크 충돌 Reject, (4) 매우 긴 Headline Overflow Reject, (5) 긴 CTA Overflow Reject, (6) 2줄 CTA *승인 없는* 요청 Reject, (7) 3줄 CTA Reject, (8) 2줄 CTA를 **별도 승인했다고 가정한 계산**은 Geometry 가능하지만 정식 v3 계약에서는 미승인, (9) 작은 가상 패키지 Mask는 기하 검증만 PASS. 진짜 모델/제품 유사성·상업성에 대한 PASS를 내리지 않는다.

**Owner #24에 제안할 실제 제품·라벨 보호 계약 (구현 전 의사결정)**:

1. 승인된 실제 제품 Input와 이미지 결과에서 제품/용기/포장/로고/라벨/인물 등 보호 대상의 바운딩 박스 또는 Pixel segmentation을 산출한다. 입력·결과 비교에는 좌표계 변환과 Model Confidence, 출처, Mask SHA, Owner/PM 판단을 기록한다.
2. 실제 이미지에서 보호 객체를 신뢰성 있게 검출하지 못하거나 일부 라벨이 읽히지 않으면 가상 Target을 실제 Mask로 대체해 PASS하면 안 된다. **Human Review/HOLD** 또는 승인된 수동 Mask 기록과 서명 필요.
3. Head/Sub/CTA region 및 실제 문자 **ink bbox**와 보호 마스크의 겹침을 검증한다. 장문·2줄 CTA·제품 크기 편차/화면 밖 영역, 플랫폼 Cropping·360/390 가독성 부적합은 **Fail-Closed**.
4. 새로운 v3 Job 생성 시에만 확정된 Profile ID/Version, Layout/Font/Copy/Review/Approval/Policy Epoch/Mask/Attempt SHA를 immutable snapshot에 고정. 과거 v2 Job·Receipt·Approval·Artifact 불변, 3:4 Layout 불변. Freeform에 서버 문자 중복 합성 금지.
5. 실제 모델/제품/브랜드/폰트 상용 사용권과 수동 사람 평가가 끝나기 전 Product Quality 및 Human Acceptance = **HOLD**.

본 Mock 코드는 일부 **가상 Mask Bounding Box**와 **텍스트 Region 직사각형**의 비충돌만 검증한다. 실제 픽셀 Ink Bounding Box, 데이터 기반 모델 검출, 실기기 360/390 Crop 충실도는 아직 검증되지 않은 후속 A5-1 Acceptance Requirement다.

## 4. Owner/PM 결정 업데이트 요청 (D50-02/03/05/06 우선)

- **D50-02:** A Reflow를 기본형 검토하고 C Reflow를 CTA 강조형 대안으로 검토할지 **실제 Owner/PM 의견/선택** 필요. B 원본은 브랜드형 후보로 보존.
- **D50-03:** Owner가 실제 제품 마스크 및 플랫폼 요구에 따라 정확한 Head/Sub/CTA Region·Font/Weight·색/수직 여백을 다시 산정하여 **새 정본 Profile JSON 버전/SHA** 제안. 여기 제시한 숫자는 Mock 제안치로 자동 채택 금지.
- **D50-04:** 기존 FE Pretendard SHA/License 확인은 후보 검토에 불과. 법무/Owner 상용 서버 렌더·바이너리 재배포·라이선스 고지/Weight 인증 필요.
- **D50-05:** 대표 제품·라벨/브랜드 및 인물 사진을 **사용권 확보 후** 검수 세트로 선정하고 객체 보호·검출 실패/수동 override 계약 결정.
- **D50-06:** CTA 360/390 최저 글자 크기, 모바일/플랫폼 Crop, 두 줄 CTA 허용 여부, 장문 Overflow 및 실제 이미지 대비 기준 승인.
- **D50-07:** 시각 점수·사람 검수 최소선/Reject 규칙 PM·Image Owner 승인.
- **D50-09:** 신규 Job v3 적용 Policy Epoch, 기존 v2 Job 보존·Rollback/불변 SHA 및 서명 승인.
- **D50-08 (별도):** 9:16 CTA `DECISION_PENDING_PM_OWNER`, 이 문서의 4:5 의사결정과 결합하거나 무단 추정 금지.

**서명/승인 문서 보존:** A5-0D-R1이 생성기에서 unsigned Draft와 signed Decision Record의 역할을 분리했다. 기존 A50D ZIP은 SHA `fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff`로 불변. 새 A50E 비교안은 별도 추가 버전 패키지로 전달. 실제 승인 참조·인증·시각 평가 점수를 자동 입력하지 않는다.

## 5. 수용 게이트

`A5_0E_A_C_REFLOW_DESIGN_PROPOSED / MOCK_GEOMETRY_AND_STRESS_PASS / OWNER_PM_APPROVAL_PENDING / ACTUAL_PRODUCT_MASK_NOT_AUDITED / FONT_SERVER_LICENSE_HOLD / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / 9x16_CTA_DECISION_PENDING_PM_OWNER / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

본 문서와 이미지는 **실제 광고를 제작해 낸 제품 기능이 아니라 Owner/PM 결정을 앞당기는 설계 실험**이다.
