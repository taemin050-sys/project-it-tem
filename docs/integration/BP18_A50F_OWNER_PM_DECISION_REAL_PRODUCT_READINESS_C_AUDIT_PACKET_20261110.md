# IT-TEM P03 Track A — A5-0F Owner/PM Decision Request + Real Product QA Readiness C-A 감사 제출

**일자:** 2026-11-10 KST
**판정 요청:** `A50F_DECISION_REQUEST_PREPARED / RIGHTS_MASK_INTAKE_VALIDATION_READY_WITH_ZERO_REAL_CASES / A5_1_IMPLEMENTATION_HOLD`. C-A 독립 수용/Owner PM 최종 승인/광고 품질 PASS와 다름.

## 1. 공식 C-A 기준점

- 직전 C-A 독립 승인 고정 HEAD `d8e724e299a5047ef707e029673a8024e68b57b0`, Tree `f78dd42bba6ae2a41124c5dc60dde8db334b2f88`. C-A5-0D-R1/A5-0E 감사보고서 `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A50DR1_A50E_DIFFERENTIAL_INDEPENDENT_AUDIT_20261110.md` SHA `2d07dab1510bad8b8a6b04fb30fc0530a52c5eea4e5c91c72afa7664099cb3b8`.
- C-A 판정 `C_A50DR1_APPROVAL_DRAFT_GENERATOR_REPAIR_ACCEPTED` / `C_A50E_REFLOW_MOCK_DESIGN_PROPOSAL_REPRODUCIBLE_ACCEPTED_WITH_NOTE`. 기존 6/6 React 브라우저 기능 C-A 수용 보존. A5-1 Owner v3 Pixel/Profile 계약 승인 0건.
- **A5-0F 범위:** 수신자 확인/의사결정 요청서와 실제 제품 이미지·권리 서류·제품 보호 Mask 증거용 read-only QA 도구와 평가표. 기존 Owner/PM V2 ZIP 불변, `src`·`app/src`·`demo_staging/live`·Track B/GCP·공식 PR/dev·운영 Job/Receipt/Artifacts·유료 API 호출 0.

## 2. Owner/PM에 전달할 준비된 검토 요청

- `BP18_A50F_OWNER_PM_FINAL_DECISION_REQUEST_20261110.md` — 기존 Owner 문서 `BP14_IMAGE_OWNER_VISUAL_V3_REVIEW_GATE_20261107.md`에 기록된 박지수 Image Owner, 이태민 PM 대상.
- 기수용 **V2 Owner/PM ZIP** `handoffs/IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip`, SHA `43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b`. 기존 V1 SHA `fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff`. **새 ZIP이나 승인 프로필을 생성해 기존 ZIP을 덮어쓰지 않음**.
- A = 기본형 우선 검토 / C = CTA 강조형 대안 / 기존 B = 브랜드 에디토리얼 대안. 각 목업의 원본 SHA는 `A50E_REFLOW_DESIGN_MANIFEST.json`에 기록. 시각 방향 의견과 Pixel/Profile/Font/Mask/최종 PM 서명은 구분해 요청.
- D50-02/03/04/05/06/07/09 역할별 Owner/PM 의사결정, 권리/폰트 증거, Profile JSON SHA, Policy Epoch, 수용·Rollback 기준 요청. D50-08 9:16 CTA는 별도 `DECISION_PENDING_PM_OWNER`.
- **실제 전송/접수 여부:** `PREPARED_NOT_CONFIRMED_DELIVERED`, `OWNER_PM_FEEDBACK_NOT_RECEIVED`, 인증된 승인/서명 0건. 저장소에 승인된 팀 채널의 실제 수신 확인이나 검증된 Owner/PM 이메일 전달 경로가 제시되지 않았으므로 **보냈다고 주장하지 않는다**. C-A는 실제 수신증거 없이 전달 완료로 판정하면 안 된다.

## 3. 실제 제품 품질·라벨 보호 검수 데이터 준비

- 실제품 사용권과 실제 제품/브랜드/라벨/초상 Mask 연결 검수 세트가 Track A의 추적된 제출 증거에서 확인되지 않음. 실사용권 보유한 실제 대표 사진 **검증 완료 건수 0**.
- `BP18_A50F_REAL_PRODUCT_PROVENANCE_MASK_VISUAL_QA_PLAN_20261110.md`: 최소 5개 서로 다른 위험 유형 R-01~R-05 권고(일반 용기, 슬림/대형, 반사/투명, 복수 제품, 사람+제품). 이는 PM 미승인 제안 클래스이며 실제 사용권이 없으면 수집·검수 PASS하지 않음.
- `BP18_A50F_REAL_ASSET_INTAKE_TEMPLATE_20261110.json`: `cases=[]` **미수집 상태를 정직하게 표시**. 실제 이미지 원문/라이선스/마스크는 접근 제한된 Mac Studio 위치에만 등록, Git/Owner ZIP에 저장하지 않음.
- `scripts/a50f_real_product_qa_intake.py`: 권리 증거 파일 SHA, 고객/브랜드 소유 이미지 SHA, 1080×1350 후보 캔버스 SHA, 0/255 단일 채널 PNG 제품/라벨 Mask SHA 및 실제 광고 Head/Sub/CTA Rect와 Pixel overlap 기하 검사. Evidence 누락/변조·Mask 오류·Collider → `BLOCKED` 또는 `MASK_COLLISION_HOLD`. 비충돌 경우에도 `MASK_RECT_NONOVERLAP_ONLY`일 뿐 Real Product Fidelity/License/Platform Crop/Human 모두 `NOT_AUDITED/HOLD`.
- `BP18_A50F_OWNER_PM_HUMAN_AD_QUALITY_SCORECARD_UNSIGNED_20261110.csv`: A/C 각각 Typography 30, CTA 25, 제품/브랜드 20, Commercial Visual 15, 모바일 10 **이전 제안 가중치**만 기록; 실제 스코어·사람 서명·승인자 ID·승인 시간 **모두 공란**. 권한 Hard Gate/Regulatory/Copy/SHA/Font 및 실광고 결과 검증 후 D50-07 실제 승인을 받아야 유효.
- `evidence/A50F_20261110/A50F_EMPTY_REAL_PRODUCT_EVIDENCE_REPORT.json`: 0건을 실제로 실행해 기록한 산출물. `rights=NOT_AUDITED`, `d50_05_d50_06_gate=HOLD`, `a5_1_implementation_authorized=false`.
- 실제 360/390 UI 화면, Owner v3 Typography 및 실모델 Generated 결과, Label/Logo 보존, 외부 사용권은 이번 단계에서 아직 **증빙 없음**.

## 4. 검증 명령/증거/회귀

- `python3 -B -m pytest -q -p no:cacheprovider -p no:warnings tests/product_e2e/test_a50f_real_product_qa_intake.py`: **15/15 PASS**, Exit0. 합성 PRIVATE fixture에서 원본/라이선스/마스크 SHA 변조, 빈 Mask·nonbinary·크기 오류·CTA 충돌·미승인 권리 검토, 도구 출력 경로 재사용 불허, 공란 Human Scorecard/미전송 요청서를 검사. 이는 **도구 검증이지 실제품의 허용/성능 검증이 아님**.
- 전체 Python: **1109/1109 PASS**, Exit0. React 57/57 PASS, Lint 0, Build PASS. 실제 제품 실행 소스 변경 없이 전체 회귀.
- C 재현: 고정 HEAD Git Archive에서 **별도 temp** 환경으로 QA 도구를 실행하여 합성 PRIVATE Fixture에 의한 fail-closed 검증; 실제 제품 원문은 전달되지 않으므로 실제품 검수 결과 재현을 요구하거나 입증했다고 주장하지 않는다.
- evidence folder `docs/integration/evidence/A50F_20261110/`에는 최초 빈 샘플 결과, 검증 로그, 정확한 SHA256 Manifest가 존재. 실제 제품/개인정보/서명/키/폰트 바이너리 미포함. 최종 HEAD/Tree와 CLEAN·Source Attestation은 docs 커밋 후 검증한다.

## 5. 후속 결정/강제 보호 게이트

- 실제 팀 채널에 **V2 ZIP 원본 파일**과 본 Owner/PM 요청 메시지를 전달하여 수신·컨셉 의견을 확보. 이 프로젝트 세션은 실제 팀 채널의 승인된 수신자 주소나 전달/회신 영수증을 가지고 있지 않으므로 **회신 전에는 대기**로 기록.
- Owner/PM 방향 피드백은 서명 완료가 아니며, 인증된 최종 D50 계약/폰트·사용권/정본 Profile SHA 및 Policy Epoch, 실제품 Mask/모바일 검증/오버플로/품질 점수 등이 확보된 후 별도 A5-1 실행 승인.
- A5-1은 신규 4:5 Composed Job만 v3 적용, 기존 v2 Receipt/Approval/Artifact SHA 불변, CTA 이미지 정확히 1회 및 단일 후보/승인 CAS/과금 안전 유지.
- `A50F_REVIEW_REQUEST_PREPARED_NOT_DELIVERED / REAL_PRODUCT_RIGHTS_SAMPLES_VERIFIED_0 / D50_05_D50_06_HOLD / OWNER_PM_SIGNOFF_0 / SIGNED_DECISION_LEDGER_NOT_INITIALIZED / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
