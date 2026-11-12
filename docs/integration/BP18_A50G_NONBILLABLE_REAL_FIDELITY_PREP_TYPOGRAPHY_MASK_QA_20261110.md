# IT-TEM P03 — A5-0G 비과금 Typography·제품 보호 마스크 사전 검증

**2026-11-10 KST | `SYNTHETIC_QA_PROPOSAL_VERIFIED / ACTUAL_PRODUCT_FIDELITY_NOT_AUDITED / DESIGN_PROFILE_V3_PENDING`**

## 1. 분리된 정책·디자인 계약

- `PRODUCT_POLICY_APPROVED` (재승인 금지): Freeform/Composed 사용자 선택, 3:4/4:5/9:16, 요청당 **단일 광고 시안 1개**, Batch 제외, FE #26 > Text #27 > Image #24 > Serving Adapter.
- `DESIGN_PROFILE_V3_PENDING`: Composed 4:5에서 A Reflow를 기본형, C Reflow를 CTA 강조형으로 검토 중. 기존 B 에디토리얼 원본 보존. **A/C는 Freeform/Composed와 다른 생성 모드가 아니다**.
- 신규 4:5 Composed의 이미지 내 CTA 1회 요구사항은 이미 확정된 PM 제품 요구. 기존 Image Owner v2의 실제 PNG CTA 누락 `A41_PRODUCT_CTA_01_HOLD`는 이번 목업 QA로 해결되지 않는다.
- 실제 제품·라벨·로고/초상 사용권 및 실제 검출 마스크 0건. D50-05/06 및 최종 Profile/Font/Policy SHA 서명은 아직 PENDING/HOLD.

## 2. 독립된 비과금 증거와 의미

`scripts/a50g_typography_product_mask_stress.py`를 실행하여 기존 A50E Accepted Mock Manifest **입력 SHA**와 두 후보 A/C의 동일 승인 Head/Sub/CTA Text SHA, FE 설치 Pretendard 1.3.9 로컬 TTF SHA를 확인하고 다음 산출물을 생성했다.

- 각 후보 1080×1350의 가상 Mask Overlay PNG **2개**: Compact Bottle 비충돌 1, 장형 패키지/CTA 침범 HOLD 1. 합계 4개.
- `docs/integration/evidence/A50G_20261110/A50G_SYNTHETIC_TYPOGRAPHY_MASK_STRESS_REPORT.json`: A/C의 Head/Sub/CTA **실제 글리프 잉크 Bounding Box**와 배치 Region 내 포함 여부, 글자별 cmap 지원, Native/360/390 Typography 규모, 5개 가상 패키지·CTA Mask의 충돌 결과.
- 입출력 원본 A50E PNG·Owner v2/V3 원본, FE·Serving·Text Runtime은 **수정하지 않는다**. 보고서/ZIP에 폰트 바이너리·실제품/권리 서류·고객 정보·실제 Logo 파일을 포함하지 않는다.
- 원본 SHA 및 출력 SHA·재생성 일치 테스트, 기존 V2 Owner/PM ZIP SHA 보존.

| 계측 (제안 수치) | A Reflow | C Reflow | 의미 |
|---|---:|---:|---|
| CTA 360px 폰트 | 20px | 20px | 가안 ≥16px |
| 내부 Safe Frame 하단 여유(360px) | 16px | 16.67px | 가안 ≥12px |
| Head/Sub/CTA 글리프 지원 | 3/3 | 3/3 | QA 카피 한정 |
| Head/Sub/CTA 실제 Ink BBox가 제안 Text Region 내 | 3/3 | 3/3 | Synthetic Layout Raster 확인 |
| Compact / Two-product 가상 Mask | 2개 비충돌 | 2개 비충돌 | 실제 제품 보호 증거 아님 |
| Tall/Wide/Headline 침범 가상 Mask | 3개 HOLD | 3개 HOLD | 복잡한 패키지 재배치/재검토 필요 |
| 2줄 CTA | Synthetic 공간 계산 가능 | Synthetic 공간 계산 가능 | **미승인: 제품 CTA 2줄 허용하지 않음** |

**중요:** 위 자료의 제품 마스크는 실제 제품 사진에서 추출된 객체/라벨 분할 결과가 아니라 실험용 1080 좌표 Box이다. 실제 이미지 경계/폰트 글리프 잉크/브랜드 라벨 기하를 완벽하게 보장하지 않는다. 또한 CTA 잉크 박스가 텍스트 Region 안에 있다는 것은 **한국어 시각적 가독성, 사용권 또는 실제 광고 품질 PASS가 아니다.**

## 3. 제품 수준으로 승격하기 위해 실제로 필요한 Owner/PM 결정

1. **방향 피드백 1단계:** `BP18_A50G_OWNER_PM_DIRECTION_FIRST_ONE_PAGE_20261110.md`와 기존 V2 ZIP을 박지수 Image Owner·이태민 PM에게 승인된 팀 채널로 전달하고 A 기본/C 강조/B 보존 의견을 수령한다. 인증된 전달·회신이 없으면 `PREPARED_NOT_DELIVERED`.
2. **실제품 근거:** 사용권과 브랜드 Owner가 확인된 대표 스킨케어 패키지 사진·라벨/로고(필요시 인물) 실제 보호 Mask를 제한된 데이터 저장소에 수집하고 Input↔Output 좌표계, 인쇄 텍스트/라벨 보존, Thumbnail Crop 충실도 및 엉뚱한 모델 재생성 여부를 사람이 평가한다. 이 검증은 내부 A50F read-only intake 도구의 P2 C-A 독립 수용 이후에만 실제 고객 자료를 입력.
3. **2단계 최종 Profile 승인:** 정확한 v3 Layout/Font/Mask/Policy JSON 및 SHA·Owner+PM 인증·Policy Epoch/기존 v2 보존/rollback을 D50-03~07/09에 기록. 9:16 CTA D50-08 별도.
4. **A5-1은 제품 Runtime에 대한 별도 승인 및 C-A 재감사 후에만** 신규 4:5 Composed Job에 적용.

## 4. 판정 및 감사 경계

`A50G_SYNTHETIC_TYPOGRAPHY_MASK_PRECHECK_PASS / PRODUCT_POLICY_APPROVED / DESIGN_PROFILE_V3_PENDING / REAL_CUSTOMER_DATA_INTAKE_C_A_P2_AUDIT_PENDING / OWNER_PM_FEEDBACK_PENDING / A5_1_RUNTIME_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

**C-A 독립감사에는 A50G 측정/재현성, P2 데이터 보호와 제품 실사용 증거의 부재를 별도 항목으로 제출**한다. 기존 A2~A4 Chrome 6/6 통합 기능은 불필요하게 재감사하지 않는다.
