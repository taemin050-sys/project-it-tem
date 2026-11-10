# IT-TEM P03 — A5-0F Image Owner·PM 최종 디자인 방향 검토 및 실제품 검증 자료 요청

**전달 대상 (Owner 문서로 확인):** Image Owner **박지수**, PM **이태민**. 폰트 라이선스는 필요 시 법무/관리 책임자, 기존 v2 호환성은 Serving 담당자 동반 검토.
**전달 상태:** `PREPARED_NOT_CONFIRMED_DELIVERED`. 본 파일은 *보낼 메시지 원본*이지 실제 전송·수신·서명 증빙이 아닙니다.
**요청 구분:** 1차 *디자인 방향 피드백* → 2차 실제 사진/제품 보호/폰트/플랫폼 기준 검토 → 3차 *정식 버전 Profile 계약 및 인증된 최종 승인*. 1차 의견만으로 A5-1을 시작하지 않음.

## 전달할 본문

박지수 Image Owner님, 이태민 PM님께

현재 IT-TEM Track A의 Instagram 4:5 Composed 사용자 여정과 전체 6개 모드·비율의 무과금 React Chrome E2E는 C-A 독립 기술검증을 통과했습니다. 다만 기존 Image Layout v2의 최종 광고 PNG에는 승인된 CTA **「지금 만나보세요」**가 표시되지 않는 제품 결함이 남아 있습니다.

이 문제를 해결하기 위한 디자인 방향으로 **A Reflow Editorial Center(기본형 우선 검토)**와 **C Reflow Contrast Action(CTA 강조형 대안)** 두 개선 시안을 전달합니다. 이전 **B Editorial Left**는 브랜드 에디토리얼 대안으로 남겨 둡니다. 모두 합성 Fixture를 활용한 검토 목업이며 실제 브랜드·제품·라벨이 보존된 광고가 아닙니다.

**검토 패키지 V2 파일**

`IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip`

SHA256 `43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b`

Mac Studio의 Track A 디렉터리 `docs/integration/handoffs/`에 원본 바이트 보존. 파일은 별도 팀 공유 채널로 승인된 방식에 따라 **실제 ZIP 파일을 전달**해야 하며, 로컬 경로만 공유하면 수신자가 열 수 없을 수 있습니다.

**우선 회신 요청 — 디자인 방향 D50-02**

- A Reflow를 신규 4:5 Composed의 기본형 방향으로 채택할지, 수정할지
- C Reflow를 별도 CTA 강조형으로 유지할지
- B Original을 브랜드 에디토리얼 대안으로만 보유할지
- 각 선택/수정 이유와 추가 요구사항. **방향 동의와 픽셀 좌표·폰트·출시 승인은 별개**입니다.

**A5-1 구현 전에 확정해야 할 후속 결정**

| 결정 | 확인 및 증빙 요청 |
|---|---|
| D50-03 | 정확한 Head/Subcopy/CTA 좌표, Product Reflow 규칙, 새 Profile ID/Version/정본 JSON SHA |
| D50-04 | 서버 상업용 Pretendard 또는 대안 Font의 Version/Weight/파일 SHA·License Notice 및 사용·배포 권한 확인 |
| D50-05 | **사용권이 확보된 실제 대표 제품 사진**, 브랜드/패키지/라벨/인물 보호 마스크와 출처·신뢰도, 미검출 시 Fail-Closed/수동 검수 규칙 |
| D50-06 | 360·390px 모바일 최소 글자 크기·대비·하단 Safe Zone, 실제 플랫폼 Crop, 긴 한글 카피·2줄 CTA·충돌 처리 |
| D50-07 | 광고 품질 사람 평가표, 필수 Hard Gate, 평가자·가중치·최저 수용선·거부 사유 |
| D50-09 | 신규 Job만 v3 고정, 기존 v2 Job/Receipt/Approval/Artifact 불변, Policy Epoch, 승인된 Rollback |
| D50-08 | **9:16 CTA는 이번 4:5 승인과 분리**하여 `DECISION_PENDING_PM_OWNER` 유지 |

개선 A/C는 360px 기준 CTA 글자 20px, 내부 Safe Frame 하단 여백 16~16.67px, *가상* 제품 목표영역과 CTA 간격 59~63px로 재현 검증됐습니다. 그러나 실제 제품·라벨 검출 및 Instagram/Meta 실제 화면 크롭으로 검증한 것은 아닙니다. 이 수치들을 최종 승인치로 자동 사용하지 않겠습니다.

**실제 제품 이미지 제공 시 주의사항:** 권한이 확인된 브랜드 또는 고객 제공 사용허가의 범위(광고 제작/테스트/저장/팀 내부 공유)를 확인해야 합니다. 사진·권리 서류·마스크를 공개 Git/ZIP/채팅에 무심코 첨부하지 않고 접근 제한된 위치에 보관하며, SHA와 권한 증거만 보고서에 기록합니다. 권리·라벨·제품 검증은 별도의 사람 검토 전까지 HOLD입니다.

**회신·서명 기록:** 역할별 승인자 신원/검토 링크, 회신 원문 증거, 검토 대상 목업/JSON/Font/권한 SHA, 수정안 및 근거를 실제 인증된 팀 채널에서 보존하십시오. 현재 unsigned Draft CSV/JSON은 정식 불변 서명 원장이 아니며, 임의의 Owner/PM 서명·승인 시각·Policy Epoch는 생성하지 않습니다.

프로필 설계의 방향을 먼저 회신해 주시면 그 결과와 실제품 검수 근거를 분리하여 최종 계약 검토를 진행하겠습니다. **A5-1 실제 제품 코드 구현은 두 분의 인증된 최종 승인과 필수 권한·품질 증거가 확보되기 전까지 진행하지 않습니다.**

---

## 현 시점 진행과 미확인 사항

- `C_A50DR1_APPROVAL_DRAFT_GENERATOR_REPAIR_ACCEPTED`; `C_A50E_REFLOW_MOCK_DESIGN_PROPOSAL_REPRODUCIBLE_ACCEPTED_WITH_NOTE`.
- `OWNER_PM_FEEDBACK_NOT_RECEIVED`, `FINAL_PROFILE_V3_SHA_NOT_SIGNED`, `RIGHTS_CLEARED_REAL_PRODUCT_DATASET_NOT_VERIFIED`.
- `A41_PRODUCT_CTA_01_HOLD`, `A5_1_IMPLEMENTATION_HOLD`, `GCP_A_QA_DEPLOYMENT_HOLD`, `A_GCP_PAID_WORKER_HOLD`, `NOT_RELEASE_READY`.
- 현재 자동화로 검증 가능한 항목은 오프라인 Mock 재현·Artifact SHA 및 명시된 보호마스크와 텍스트 Region의 **기하 충돌 여부**까지. 사용자 사진의 사용권, 실제 제품·라벨 충실도, 광고 품질, 최종 사람 승인에 대한 자의적 PASS 금지.
