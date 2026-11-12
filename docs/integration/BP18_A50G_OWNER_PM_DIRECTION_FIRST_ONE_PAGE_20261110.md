# IT-TEM P03 — Image Owner / PM 디자인 방향만 먼저 결정 요청 (1단계)

**상태:** `DECISION_REQUEST_DRAFT_ONLY / NOT_CONFIRMED_DELIVERED / SIGNOFFS_0`
**검토 대상:** **Instagram 4:5 Composed 내부의 Typography·CTA 레이아웃**만. Freeform/Composed 선택, 3:4·4:5·9:16, 요청당 단일 이미지 및 Batch 제외는 모두 `PRODUCT_POLICY_APPROVED`이며 **재승인 대상이 아닙니다.**

### Image Owner 박지수님 · PM 이태민님께 요청드리는 결정 3개

1. **A Reflow Editorial Center**를 4:5 Composed **기본 레이아웃의 방향**으로 채택할까요? 변경이 필요하면 제품 위치·Headline/Sub·CTA 구도의 수정 의견을 요청드립니다.
2. **C Reflow Contrast Action**을 **CTA 강조형 선택 디자인 방향**으로 보존할까요? CTA 강조의 허용 범위와 브랜드 톤에 관한 의견을 요청드립니다.
3. **B Original Editorial Left**는 기존 브랜드 에디토리얼 참고 후보로 유지하는 방향에 동의하시나요?

각 의견은 **디자인 방향 피드백**으로만 보존합니다. 특정 Pixel Box/Font/Mask/Profile JSON SHA/Policy Epoch, 광고 품질 점수 또는 배포·실모델 실행에 대한 결재로 처리하지 않습니다. **정식 v3 계약과 A5-1 개발 승인은 별도 2단계**로 남습니다.

### 함께 검토할 자료

- 고정된 기존 V2 정본: `handoffs/IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip`, SHA-256 `43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b`.
- A/C 기존↔개선 4분할: `evidence/A50E_20261110/A50E_A_C_BEFORE_AFTER_COMPARISON.png`.
- 개선 A/C 실험 결과: 360px CTA 글자 20px, 내부 Safe Frame 하단 16/16.67px, 가상 Product Target↔CTA 63/59px. 이 숫자는 **미승인 제안치**입니다.
- 추가 QA: `evidence/A50G_20261110/A50G_SYNTHETIC_TYPOGRAPHY_MASK_STRESS_REPORT.json` 및 가상 마스크의 비충돌·충돌 오버레이. **실제 제품·브랜드 마스크나 Meta 인증 Safe Zone 아님.**
- 새로운 비과금 실험에는 Pretendard 로컬 FE 1.3.9을 읽기 전용으로 사용했으며 폰트 파일을 포함하지 않았습니다. 상용 서버 폰트 사용 승인 별도 D50-04 HOLD.

### 회신·2단계 계약 기록의 분리

**1단계 회신 증거:** 역할(Owner 또는 PM), 해당 역할의 인증된 회신 참조, 선택 A/C/B 방향, 수정 사항 및 근거. 회신 실제 접수 전에는 `FEEDBACK_NOT_RECEIVED`. 이 문서에 가상의 서명/시간을 기입하지 않습니다.

**2단계 정식 승인 D50-03/04/05/06/07/09:** 정확한 좌표·버전·Profile JSON SHA, 승인된 Font SHA/License Notice, 사용권 확인된 실제 제품/라벨 Mask 및 보존/충돌 정책, 모바일·장문·Crop 기준, 사람 광고 품질·Rollback, 신규 Job Policy Epoch와 기존 v2 불변, 검증된 양측 서명. **9:16 CTA D50-08은 별도 미결정**.

**Gate:** `PRODUCT_POLICY_APPROVED / DESIGN_PROFILE_V3_PENDING / DIRECTION_FEEDBACK_PENDING / REAL_PRODUCT_RIGHTS_VERIFIED_0 / A5_1_RUNTIME_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

**전달 확인:** 승인된 팀 공유 채널 및 정확한 수신 경로가 이 개발세션에 확인되지 않았습니다. 이 문서와 V2 ZIP은 준비돼 있으나, 실제 전달/수신/회신 완료라고 선언하지 않습니다.
