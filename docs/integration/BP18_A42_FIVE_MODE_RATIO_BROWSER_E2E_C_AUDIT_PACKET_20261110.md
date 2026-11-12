# IT-TEM P03 Track A — A4-2 5개 모드·비율 공식 React Chrome E2E 차등감사 제출

2026-11-10 KST · Track A 개발 자체검증. **C-A 독립 재감사 아님, 실제 Provider/광고 품질 승인 아님.**

## 1. Source/Owner/감사 기준선과 분리 커밋

- 이전 C-A4 수용: HEAD 4f87c4c4ff0c4cbf08dcbb2c03f8de826119d925 / Tree ca1082c34e3999b062c06d14995a6b281223e6b4, C_A4_0_CONTRACT_MATRIX_ACCEPTED_WITH_OWNER_PR_RECHECK_NOTE 및 C_A4_1_OFFICIAL_REACT_OFFLINE_FIXTURE_BROWSER_E2E_ACCEPTED. C-A4 최종 감사보고서 SHA256 25d24cab2af9c7a6633ef5ffb5ccde1ece69d151b7fd13ad5dbebdfd9e37a498.
- A5-0 비제품 설계 제안 커밋 1baf75128041e26d3eac1113b8e97aaa3945a66e (Owner/PM 서명 대기, A5-1 코드 미착수)과 **A4-2 기능 QA 구현 커밋 0a6ab598807f7bd29405d0d5ea983acd744c1b21**은 분리. 기존 수용된 A4-1 Chrome 하네스 코드는 수정하지 않고 새로운 tests/product_e2e/a42_* 및 run_a42_five_scenarios.sh 추가.
- A4-2 재실행은 code commit 0a6ab598807f7bd29405d0d5ea983acd744c1b21을 기준으로 Vite QA bundle을 빌드하여 진행. 최종 문서/증거 커밋 이후 HEAD가 달라지는 것은 **문서·증거만 추가**된 결과다. 동일 build SHA·실행 컨테이너 증명을 QA/GCP 운영 증명으로 승격하지 않는다.
- Owner Source First 우선권 FE #26 > Text #27 > Image #24 > Serving; A2~A3R.1 보안·과금·승인·무결성 코드, Track B, Owner PR, 공식 dev, GCP A/B, 보호 Live/QA는 불변.

## 2. 실제 시스템 Chrome, 실제 공식 React의 다섯 독립 사용자 여정

A4-S01 Composed 4:5는 C-A4에서 독립 수용했다. 아래는 나머지 S02~S06을 **각각 별도 Job**으로 공식 React ProductPage→CopyPage→DraftPage→ExportPage에서 실제 Chrome으로 실행한 결과다. 하나의 임시 loopback FastAPI 서버를 공유하지만 Job ID/Copy SHA/Attempt/Artifact SHA는 각각 구분했다.

| Scenario | mode | ratio | downloaded PNG | Chrome 15단계 | Receipt/이미지 텍스트 | Product Quality |
|---|---|---|---|---|---|---|
| A4-S02 | composed | 3:4 | 1080×1440 | PASS | Owner v2 Head/Sub/CTA 각 text SHA와 Copy 일치 | 사람 시각/상업 검수 HOLD |
| A4-S03 | composed | 9:16 | 1080×1920 | PASS | Owner v2 Head/Sub, CTA 플랫폼 표시 | 9:16 CTA DECISION_PENDING_PM_OWNER |
| A4-S04 | freeform | 4:5 | 1080×1350 | PASS | 서버 추가 Overlay 없음, receipt rendering=provider_drawn_text | 실제 모델의 한글 생성·제품 충실도 NOT_AUDITED |
| A4-S05 | freeform | 3:4 | 1080×1440 | PASS | 서버 추가 Overlay 없음 | 실제 모델의 한글 생성·제품 충실도 NOT_AUDITED |
| A4-S06 | freeform | 9:16 | 1080×1920 | PASS | 서버 추가 Overlay 없음 | 실제 모델의 한글 생성·제품 충실도 및 9:16 CTA 정책 미수용 |

각 시나리오 브라우저 15개 단계에는 로그인, 제품 사진 2개/참고 0개 실업로드, visible Label 클릭으로 모드·비율 선택 및 Job 고정, Copy QA 생성/검수, Copy 수정→복원→Generation 3 및 새 Review SHA/옛 승인 비활성, Copy 승인, 이미지 후보 하나, 거절, **명시적** 재생성 후 Attempt v1 REJECTED / v2 COMPLETED(서로 다른 이미지 SHA), 오래된 후보 승인 거부, 최종 합성/Resize, 실제 버튼 PNG·Caption 다운로드와 저장 바이트 SHA 대조, 새로고침 시 신규 POST 0, 390/360 스크린샷, 로그인 없는 401 및 다른 Owner 404, 미승인 batch 2/3/4/mixed 422가 포함됐다.

검증기는 각 Job의 두 Attempt ID와 Copy Approval/Prompt SHA 결속을 임시 SQLite에서 읽기 전용으로 점검. 모든 시나리오에서 Queue 0, Cost Attempt 0, 외부 Provider POST 0, React 예외 0. Freeform은 model-generated text를 Fixture에서 실제 생성하지 않으므로 Caption SHA와 Blob 검증이 일치해도 Freeform 이미지 내 한글 정확성/브랜드 보존 PASS를 의미하지 않는다. 390/360 화면은 캡처 증거이며 사람의 실제 가독성 수용 점수가 아니다.

**A4-2 실행 명령:** bash tests/product_e2e/run_a42_five_scenarios.sh (환경·포트·경로는 README_A42.md 참조), 최종 5/5 PASS, Exit Code 0. 5종 × 15단계 = 75개 확인 단계, 총 60개 Chrome Screenshot, 5개 PNG와 5개 UTF-8 Caption의 다운받은 실제 SHA 검증 PASS. 모두 Mac Studio Chrome 157, OFFLINE_FIXTURE/합성 RGB 단색 입력, 127.0.0.1:18540, 미사용 포트 사전 점검, 실제 유료 API 키 해제, 서버 사후 종료.

## 3. 증거·회귀·정본 경로

A4-2 증거 루트: docs/integration/evidence/A42_20261110/

- A42_FIVE_SCENARIO_AGGREGATE.json — code HEAD, 다섯 Job·Mode·Ratio·출력 픽셀·최종 SHA·승인/Attempt 결과·잔여 품질 HOLD 별도 목록.
- composed_3x4, composed_9x16, freeform_4x5, freeform_3x4, freeform_9x16 각 폴더 — browser_trace.json, 12개 Screenshot, 실제 ad_WxH.png, caption.txt, ledger_artifact_verification.json, browser.log, verify.log, SHA256_MANIFEST.txt.
- A42_BUILD.log — 실제 QA Vite 빌드 로그.
- A42_FULL_PYTHON.log — 전체 Python **1063/1063 PASS** (A5-0 신규 asset tests 11 포함), Exit 0, 기존 A2 보안/기존 BP17 경합 모듈 회귀 포함.
- A42_REACT_57.log — React **57/57 PASS**, Exit 0.
- A42_LINT.log / A42_BUILD_REGRESSION.log — Lint 0 error/warning, Build PASS, Exit 0.
- 각 원본 증거 SHA256과 루트 증거의 별도 SHA256 매니페스트를 검증. 계정 쿠키, 임시 Invite 원문, 실 SQLite/WAL/SHM, 유료 API 키, 실제 고객 제품 이미지는 포함하지 않음.
- 참고 Repro README: tests/product_e2e/README_A42.md, 기존 C-A4 수용 하네스 A41은 그대로 유지.

**실행 보장 제한:** Fixture는 Python FastAPI + Owner 모듈의 로컬 QA 분기를 사용한다. 실제 Live Queue/Worker가 유료 Provider에 전달하는 운영 경로, GCP 실행 Build/SSO/롤백, Owner 원본 최신 PR 재대조, 실광고 규제·폰트 권한·상업적 품질을 A4-2 Chrome 증거만으로 PASS하지 않는다.

## 4. C-A 차등감사 요청 및 게이트

1. 고정 신규 최종 HEAD/Tree와 원본 A4-2 실행 코드를 함께 비교. A4-1 기수용 테스트/코드의 변경 없음, A5-0 목업·계약 제안과 A4-2 검증 코드·증거 커밋을 구분.
2. 고정 Git Archive에서 실제 공식 React Chrome 5개 Job을 각각 재실행. 각 15개 browser + API negative 단계, 12 screenshot, 서로 독립된 mode/ratio, Approval Copy/Review/Generation, two Attempt and SHA, PNG/Caption artifact byte hash, GET-only/ACL/batch 차단을 확인.
3. Freeform 3개에 서버 Composition Overlay가 없음, Composed 3:4 CTA Receipt 정확한 Copy SHA, Composed 9:16 CTA 정책 결정 전 Human PASS 부여 금지, 실제 Provider/E2E 품질을 NOT_AUDITED로 유지.
4. 4:5 Composed 기존 P1 CTA 미합성 문제는 A5-0에서 모의 개선안만 마련했으므로 **A41_PRODUCT_CTA_01_HOLD** 유지. v3 Owner/PM 결정 없이 A5-1이나 실제 Product Fidelity PASS로 승격하지 않는다.
5. 기존 A2/A3R.1, GCP A 배포·Signed SSO·실비용·유료 Worker, 9:16 CTA 의사결정은 각각 독립 게이트. 공식 GitHub dev/PR 및 GCP 변경 금지.

**개발 자체 판정:** A4_2_FIVE_OFFICIAL_REACT_CHROME_OFFLINE_FIXTURE_SELF_PASS / C_A42_DIFFERENTIAL_AUDIT_PENDING / A5_0_OWNER_PM_DECISION_PENDING / A5_1_IMPLEMENTATION_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / PAID_WORKER_HOLD / NOT_RELEASE_READY.
