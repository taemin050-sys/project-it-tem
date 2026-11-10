# IT-TEM P03 — A50F-P2-01 / A5-0G 분리 차등감사 제출 패킷

**2026-11-10 KST — C-A 독립감사 요청. 개발 자체검증만 완료.**
`SAFE_NONBILLABLE_DEVELOPMENT_GO / PRODUCT_POLICY_APPROVED / DESIGN_PROFILE_V3_PENDING / OWNER_PM_FEEDBACK_PENDING / A5_1_RUNTIME_HOLD / NOT_RELEASE_READY`

## 1. 기준점과 독립 수용 내용 유지

- C-A5-0F 고정 HEAD `1d88fb25801303ef509cc81b958a1a989b346558`, Tree `704d61f081166a3adccffaa9bf3feadc3224d5bd`. C 보고서 `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A50F_PRODUCT_POLICY_REAL_ASSET_INTAKE_INDEPENDENT_AUDIT_20261110.md`, SHA `81ce811a1df92303e07966dfcb0c10e8035b02facacefe15a5f91f6dc9c4d208`; 판정 `C_A50F_READINESS_TOOLING_ACCEPTED_WITH_P2_NOTE`.
- **기존 PM 제품 정책은 불변**: Freeform/Composed 선택, 3:4/4:5/9:16 비율 선택, 요청당 단일 후보, Batch 2/3/4 제외, FE #26 > Text #27 > Image #24 > Serving Adapter. 이들은 `PRODUCT_POLICY_APPROVED`이고 재승인 불필요. 기존 6/6 정식 React Chrome OFFLINE_FIXTURE 기능 수용 유지.
- Composed 4:5 **내부** Typography/CTA 레이아웃 A Reflow(기본형)·C Reflow(강조형)·B Original(브랜드형 대안)만 `DESIGN_PROFILE_V3_PENDING`; 최종 PM/Image Owner 수용 없음.
- 기존 4:5 Composed v2 실제 PNG CTA 누락 `A41_PRODUCT_CTA_01_HOLD` 불변; 9:16 CTA D50-08 `DECISION_PENDING_PM_OWNER`; GCP QA·유료 Worker·Release HOLD.

## 2. Track 1 — A50F-P2-01 Metadata Echo (별도 수정 커밋)

- 수정 커밋 `008ee9f35575e65050a1b38818358e6bd782d61d`, Tree `ec9788cc53036322afc98dbc1515be228a2a4e51`.
- `scripts/a50f_real_product_qa_intake.py`: 유효 `case_id`는 제한된 ASCII 형식만 허용, 외부 결과 `reports[].case_id` 및 `blocked[].case_id`는 **원문을 절대 사용하지 않고** `CASE_000001`, `CASE_000002`와 같은 순서 기반 비식별 토큰으로 치환. malformed 배열 요소는 안전한 `A50F_CASE_SCHEMA_OR_INPUT_INVALID` HOLD.
- `tests/product_e2e/test_a50f_real_product_qa_intake.py`: C 재현 입력 `SYNTHETIC_ONLY_PRIVATE_PATH:/private/tmp/SECRET_RIGHTS_FOLDER` 외 개인 경로·이메일·Unicode·제어문자·잘못된 데이터형·미승인 권리·서명 근거 누락과 SHA/Mask FAIL CLOSED 포함.
- 기존 SHA/Mask·권리 증빙, 실제품 0건과 D50-05/06 HOLD는 유지. P2 문서 `docs/integration/BP18_A50F_P2_01_CASE_ID_METADATA_ECHO_REPAIR_20261110.md`.
- 테스트 `docs/integration/evidence/A50FP2_20261110/`: P2 관련 **29/29 PASS**, 전체 Python **1123/1123 PASS**, React 57/57, Lint/Build PASS, C의 정확한 synthetic P2 반례를 수정 소스로 재실행해 **원문 대신 CASE_000001** 외부 JSON 출력. 보관 증거/해시 SHA256_MANIFEST.txt.
- **감사 요청:** C-A는 고정 Git Archive에서 P2 공격을 독립 실행하고 모든 출력 Case ID·reason_code·stdout/stderr에 비공개 원문이 남지 않는지 확인. 실제 고객 사진/권리 데이터를 새 도구에 입력하는 것은 **독립 P2 수용까지 HOLD**.

## 3. Track 2 — A5-0G 비과금 제품 충실도 준비 / Owner 의사결정 경량화

- `docs/integration/BP18_A50G_OWNER_PM_DIRECTION_FIRST_ONE_PAGE_20261110.md`: 1단계 **디자인 방향만** 묻는 1페이지 요청서. 박지수 Image Owner/이태민 PM의 A 기본형·C 강조형·B 원본 보존 여부와 수정 요구만. 2단계 Profile v3 서명/Pixel/Font/권리·실제품/Policy SHA 승인과 구분.
- 원본 V2 Owner/PM ZIP **동일 바이트**: `handoffs/IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip`, SHA `43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b`. Actual send/receipt **NOT_CONFIRMED**, 누군가가 읽었다거나 PM이 승인했다고 주장하지 않음. 공식 dev/PR·Notion/팀 채널 자동 수정 없음.
- `scripts/a50g_typography_product_mask_stress.py`, `tests/product_e2e/test_a50g_typography_product_mask_stress.py`: 기존 A50E 해시 원본과 설치된 Pretendard 1.3.9 TTF SHA를 read-only로 사용. 각 A/C의 실제 Head/Sub/CTA **글리프 Ink BBox + cmap**·가상 패키지 Mask 5개(비충돌 2, Hold 3), 360/390 폰트와 2줄 CTA의 **미승인** 기하 가능성을 표시. **실제품/라벨 검출·폰트 서버 배포 사용권·상업적 품질 인증이 아님**.
- 새 증거: `docs/integration/evidence/A50G_20261110/` = Synthetic Mask Overlay 4 PNG + Report JSON + SHA Manifest. 전체 시험 로그는 별도 `evidence/A50G_VALIDATION_20261110/`로 분리. A/C 각각 360 CTA 20px, 실제 세 카피 Ink BBox 제안된 Region 내 3/3, compact/two-product 비충돌 2, tall/wide/headline 침범 HOLD 3. 모두 합성 마스크이며 실제 브랜드·라벨/로고/초상 데이터 0.
- `BP18_A50G_NONBILLABLE_REAL_FIDELITY_PREP_TYPOGRAPHY_MASK_QA_20261110.md`: C가 재현 가능한 실험·제약·후속 실제품 자료 요구. 기존 A50E 목업/실제 Job/Receipt/Artifact는 변경 0.
- Owner/PM은 승인된 팀 채널의 실제 수신 정보가 확인된 이후 V2 ZIP 원본을 전달받아야 한다. 현재 `PREPARED_NOT_CONFIRMED_DELIVERED`; 가상의 서명·시각·Policy Epoch 생성 안함.

## 4. 검증 범위 / 거절 및 제출 권한

- A50G 표적 검증 **12/12 PASS**, 기존 A50F P2 표적 **29/29 PASS**, 두 트랙 통합 전체 Python **1135/1135 PASS**, Exit 0 (최종 검증 로그 참조), FE React 57/57, Lint/Build PASS. 검증 명령은 Python 3.12 `-B -m pytest -q -p no:cacheprovider -p no:warnings tests`; 무과금·외부 Provider 키 제거.
- 검토 대상 신규 파일/코드만 차등. `app/src`, `src/image_generation`, `src/text_generation`, `demo_staging/live`, 보호 GCP/운영 데이터/Track B는 불변.
- Source Integrity 새 HEAD/Tree/CLEAN/Tracked Blob/Modes/Index Flags는 모든 증거 커밋 이후 별도 정확 검증.
- 실제 제품·사용권·Label Mask 자료가 없어 **실제품 품질은 `NOT_AUDITED`**, 실제 사람 검수 및 상용 렌더 `HOLD`. D50-02/03/04/05/06/07/09 정식 승인 및 서명 원장 인증·Policy Epoch 확보 전 **A5-1 Runtime 코드 변경 금지**.
- 별도 C 판정 요청: `C_A50F_P2_01_INDEPENDENT_REPAIR_ACCEPTANCE`와 `C_A50G_SYNTHETIC_PRODUCT_QUALITY_PREP_ASSET_REPRODUCIBILITY`를 분리. Product Policy와 기존 6개 E2E는 수용 유지.

## 5. 잠금 상태

`A50F_P2_DEV_FIXED_C_A_REAUDIT_PENDING / A50G_SYNTHETIC_QA_DEVELOPER_VERIFIED / PRODUCT_POLICY_APPROVED / DESIGN_PROFILE_V3_PENDING / OWNER_PM_FEEDBACK_NOT_RECEIVED / REAL_RIGHTS_CLEARED_PRODUCT_SAMPLES_0 / REAL_CUSTOMER_INTAKE_HOLD / A5_1_RUNTIME_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
