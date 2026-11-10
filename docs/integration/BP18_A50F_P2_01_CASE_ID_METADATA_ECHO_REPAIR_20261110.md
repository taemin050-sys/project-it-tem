# IT-TEM P03 — A50F-P2-01 Invalid Case ID Metadata Echo 최소 수정

**2026-11-10 KST | DEV_VERIFIED_ONLY / C-A DIFFERENTIAL_REAUDIT_PENDING**

## 1. 기준·수정 범위

- C-A5-0F 고정 HEAD `1d88fb25801303ef509cc81b958a1a989b346558`, Tree `704d61f081166a3adccffaa9bf3feadc3224d5bd`; 감사 `IT_TEM_P03_C_A50F_PRODUCT_POLICY_REAL_ASSET_INTAKE_INDEPENDENT_AUDIT_20261110.md`, SHA-256 `81ce811a1df92303e07966dfcb0c10e8035b02facacefe15a5f91f6dc9c4d208`.
- 원인: `evaluate_case()`에서 `case_id`가 잘못된 경우 ValueError를 차단하지만, `make_report()`의 `blocked[].case_id`는 **미검증 원문**을 사용해 `/private/tmp/...` 또는 사용자 메타데이터가 보고서에 반사될 수 있었다.
- 수정: `scripts/a50f_real_product_qa_intake.py`와 `tests/product_e2e/test_a50f_real_product_qa_intake.py` + 본 문서와 독립 재현 로그에 한정. 제품 Runtime/FE/Owner 소스·Job/Receipt·Track B/PR/GCP/유료 Worker 불변.

## 2. 구현과 보고서 필드 변경

- 허용 입력 `case_id`: **ASCII** 영문/숫자로 시작, 이후 ASCII 영문/숫자/하이픈/밑줄 허용, 전체 1~80자. Unicode 글자·공백·슬래시·역슬래시·콜론·이메일 @·제어문자/너무 긴 ID는 `A50F_CASE_ID_INVALID`로 HOLD.
- 입력으로 통과한 Case ID라도 고객 이름/내부 ID가 섞일 수 있으므로 **출력 결과에는 원본 case_id를 사용하지 않는다**. 읽기 전용 결과의 `reports[].case_id` 및 `blocked[].case_id`를 입력 순서에 따른 `CASE_000001`, `CASE_000002`와 같은 **이 호출에서만 유효한 익명 인덱스 토큰**으로 대체한다.
- 비정상 `cases[]` 항목도 원문을 출력하지 않고 `CASE_00000N`과 고정 `A50F_CASE_SCHEMA_OR_INPUT_INVALID`만 출력한다.
- Duplicate valid case ID 검증은 유지한다. SHA256·권리 증빙/원본 이미지·PNG 마스크·Canvas 크기 및 Region 충돌/Overflow HOLD 논리는 **변경 없음**.
- 이 토큰은 사용자의 안정적 인증 ID나 공식 승인 ID가 아니며, **보고서 순서와 비공개 입력 Manifest의 순서만으로 매핑**한다. 외부 보고서와 내부 원본 매핑을 공개/배포하지 않는다.
- 출력 근거 단계는 `P2_FIX_DEV_VERIFIED`이며 실제 고객 검수 도구 투입은 C-A의 독립 P2 수용까지 HOLD 유지.

## 3. 차등 부정 시험

- C-A에서 재현한 `SYNTHETIC_ONLY_PRIVATE_PATH:/private/tmp/SECRET_RIGHTS_FOLDER`를 포함한 잘못된 ID, POSIX/Windows 경로, 이메일, 한글 이름, 제어문자, 80자 초과, dict/list/int 비정상값을 독립 Private Fixture에 넣는다.
- 기존 승인된 형식의 ID조차 익명 `CASE_00000N` 토큰만 외부 보고서에 기록되는지, BLOCKED `reason_code`에 원문/경로/사용자정보가 반사되지 않는지 테스트.
- CLI 실제 JSON 파일 기록 및 stdout/stderr에 사설 경로·Case ID가 출력되지 않는지 검증.
- 기존 D50-05/06 `HOLD`, `A5_1_IMPLEMENTATION_HOLD`, 실제품 0건·권리 미인증·제품 무결성 未검증을 유지.
- 검증 명령: `/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3 -B -m pytest -q -p no:cacheprovider -p no:warnings tests/product_e2e/test_a50f_real_product_qa_intake.py`.

## 4. 이미 확정된 제품 정책 (재승인 요구 금지)

`PRODUCT_POLICY_APPROVED`: 사용자 Freeform/Composed 선택, 3:4·4:5·9:16, 요청당 **단일 후보 1개**, Batch 2/3/4 제외, Owner 계약 우선권 **FE #26 > Text #27 > Image #24 > Serving Adapter**. 기존 6/6 Chrome Fixture E2E의 C-A 수용 유지.

`DESIGN_PROFILE_V3_PENDING`: Composed 4:5 **내부** A Reflow 기본 디자인 / C CTA 강조형 / B 브랜드 에디토리얼 후보, 픽셀·폰트·실제품 마스크·품질·Profile SHA 및 Policy Epoch. D50-02는 신규 모드 선택이 아닌 이 내부 디자인 후보 판단이다. D50-08의 9:16 CTA는 별도 `DECISION_PENDING_PM_OWNER`.

## 5. 운용 게이트

`A50F_P2_01_DEV_FIXED_REAUDIT_PENDING / PRODUCT_POLICY_APPROVED / DESIGN_PROFILE_V3_PENDING / REAL_CUSTOMER_INTAKE_BEFORE_C_ACCEPTANCE_HOLD / OWNER_PM_SIGNOFF_PENDING / SIGNED_DECISION_LEDGER_NOT_INITIALIZED / A5_1_RUNTIME_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

**C-A는 Source 고정 Archive에서 원본 P2 공격을 독립 재실행하고 잘못된 Case ID가 어떤 결과 JSON 필드에도 반사되지 않는지를 검증할 것.** 이번 수정은 제품 설계·광고 품질 수용이나 서명 기록 구축을 뜻하지 않는다.
