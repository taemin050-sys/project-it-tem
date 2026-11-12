# IT-TEM P03 Track A — A5-0D-R1 / A5-0E 차등 독립감사 제출

**Date:** 2026-11-10 KST. **C-A 감사를 요청하는 개발 자체검증 제출 자료. C 독립 PASS, Owner/PM의 정식 승인, A5-1 구현 승인 아님.**

## 1. 감사 기준점 및 커밋 분리

- C-A5-0D 독립감사 기준 HEAD `9ccd8d95aa3d33cde00b166e25ba494e34e75bb6`, Tree `948589492eb4afa0158aa494eb3a6c719b21c9f6`.
- C 보고서: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A50D_OWNER_PM_DECISION_READINESS_INDEPENDENT_AUDIT_20261110.md`, SHA256 `6c8a8484cc5ab6ef8cf6bb2c78fd994e717be00ac4df931ff53cd1e7fc0bf475`. 기존 판정 `C_A50D_REVIEW_READINESS_ACCEPTED_WITH_NOTE`, P1 signed record overwrite·P2 external out.
- **R1 보완 커밋:** `945fef01f491bff7d5829db09ce6e2c904f47faa`, Tree `3c22f0e82192728adbd3dfd234813f96607d5482` — Draft 전용 출력, 기존 파일 O_EXCL 거부, 외부 `--out` 지원, Git Archive 6부정 검증, 서명 이벤트 체인 제안.
- **A5-0E 시각 제안 커밋:** `a7c5249bfc7ff0a637c1f8c24b651bce8772816a`, Tree `a8c1610c8a014463abb2670defae2128d9bc0da4` — A/C 제품-CTA Reflow 목업, 모바일/crop 시뮬레이션, 9개 스트레스 시나리오, V2 unsigned Owner/PM ZIP.
- 본 보고서·테스트 로그/증거는 **별도 추가 문서 전용 커밋**에 포함되므로 최종 HEAD/Tree는 독립 감사에서 `git rev-parse`로 다시 확인할 것.
- `app/src`, `src/image_generation`, `src/text_generation`, `demo_staging/live`, 기존 A4 브라우저 기능 및 A2/A3R 안전성 Product Runtime **변경 0**. Track B, 공식 dev/Owner PR, GCP A/B, 보호 Job/DB/Receipt/Artifact 및 유료 Provider POST 변경·호출 0.

## 2. A50D-P1-01과 P2-02 Before/After

기존 생성기 `scripts/a50d_owner_pm_decision_preflight.py`는 `--out`이 외부여도 `docs/integration/BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv` 및 `...PROFILE...json`을 무조건 덮어쓰고, 외부 경로에서 `relative_to(BASE)` 예외로 종료했다. C는 이것을 격리 아카이브에서 독립 재현했다.

**R1 이후** 원본 C 감사 코드가 아니라 별도의 `tests/product_e2e/test_a50dr1_approval_record_protection.py`를 고정 HEAD `9ccd8d9` 실제 `git archive`에 새 생성기만 복사하여 실행:

1. 임시 Git Archive 정본 CSV/JSON에 가상 `APPROVED`, Owner+PM 서명 참조, Profile SHA, Policy Epoch 삽입.
2. `--out /private/tmp/.../new-draft` 실행 **Exit 0**, 신규 unsigned Draft 3개만 생성; 임시 Git Archive의 가상 승인 CSV/JSON 바이트·SHA 전/후 **동일**.
3. 해당 서명 파일이 존재하는 디렉터리를 `--out`으로 직접 지정하면 `A50D_SIGNED_OR_EXISTING_DESTINATION_HOLD`, **파일 변경 0**.
4. 외부 감사 Output 안에 가상 승인 파일이 이미 있으면 사전 충돌 검증에서 **HOLD/바이트 변경 0**. 동일 Draft 디렉터리 재실행도 HOLD. Symlink 대상 거부.
5. 기존 **V1 ZIP** `docs/integration/handoffs/IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip`은 기존 SHA `fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff` 유지; `scripts/a50d_make_owner_pm_review_zip.py`로 독립 외부 재생성 후 `cmp` 결과 동일.
6. R1 표적 6/6 PASS, Exit 0. 생성기는 기존 공식 CSV/JSON이나 실제 서명 원장을 어떠한 경우에도 암묵적으로 갱신하지 않음. **서명 원장 자체는 아직 생성하거나 실행하지 않았으며**, 미래의 append-only version/previous_sha/SHA/Role/Time/Evidence/Supersede·인증 확인 규칙을 `BP18_A50DR1_SIGNED_DECISION_PRESERVATION_CONTRACT_20261110.md`에 제안. 실제 Owner/PM 서명 0건.

R1 검증 로그 및 SHA: `docs/integration/evidence/A50DR1_20261110/`.

## 3. A5-0E CTA+제품 구도 Reflow 개선 (미승인 Synthetic)

정본 자료 `docs/integration/BP18_A50E_CTA_PRODUCT_REFLOW_OWNER_PM_DECISION_V2_20261110.md`, `docs/integration/evidence/A50E_20261110/`. `scripts/a50e_composed45_product_cta_reflow_concepts.py`가 동일 기존 승인 Head/Sub/CTA Copy SHA 및 동일 Synthetic Fixture Background에 대해 제안용 A/C Reflow를 생성, B Original SHA 불변.

| 항목 | A Reflow | C Reflow |
|---|---:|---:|
| 1080×1350 목업 PNG SHA | `bcf1b8081a6164ed236cca0cc370d8b906dcd2b0b841aca7db1dc58c14e3e509` | `eec55373cca228de34838b33baaf3b11e703e341b05739b34f4c909b1afea6fd` |
| CTA Rectangle LTRB (1080 px) | (218,1108,862,1238) | (80,1094,1000,1236) |
| 새 **가상** Product Target bottom | 1045 px | 1035 px |
| CTA↔가상 Target 간격 | 63 px | 59 px |
| CTA Font 360px 축소 | 20 px | 20 px |
| 내부 Safe Frame 하단 360px | 16.00 px | 16.67 px |
| CTA 전경/배경 Contrast | 10.933:1 | 9.964:1 |
| 360px 축소 후 **하단 12px 단순 Crop 시뮬레이션** CTA 끝∼Crop 하단 | 25.33 px | 26.00 px |

기존 A/C(각각 CTA 15.67/16.67 px, Safe Frame 여유 2.00/1.33 px) 대비 **가상 객체 구도·CTA를 함께 Reflow한 개선 제안**이다. 360 CTA ≥16px, Safe Frame 여유 ≥12px, 대비 ≥4.5:1은 **PM 미승인 협의용 임계값**이다. 기존 v2 구도 `product target`은 실제 모델 출력에서 검출한 사람/제품/라벨 마스크가 아니며, 새 Synthetic Mask 역시 무브랜드 용기 일러스트에 불과하다. 실물 제품·라벨/로고 보호 검증 PASS 금지. 360/390 플랫폼 Crop도 단순 12px 테스트 이미지이지 Instagram/Meta 공식 인증이 아니다.

스트레스 증거 `A50E_SYNTHETIC_STRESS_RESULTS.json`: 실제 Mask 입력 부재·과대 제품 Mask·CTA 충돌·너무 긴 한글 Headline/CTA·미승인 2줄 CTA·3줄 CTA는 Fail Closed, 별도 2줄 계산 가능 여부·작은 Fixture Mask는 기하 실험으로만 보고. `tests/product_e2e/test_a50e_product_cta_reflow_concepts.py`: PNG SHA, 모바일/크롭·구도/카피·폰트·기존 B 불변·외부 재생성 바이트 일치·ZIP V2 재현성 포함 **12/12 PASS**. A50E Output 13개 + SHA256_MANIFEST.txt 13/13 PASS.

실제 Owner/PM 결정 필요: D50-02/03(A/C 도입/정확한 좌표·Profile v3 ID·Version·Layout SHA), D50-04(정식 Pretendard Font/Weight/License Evidence), D50-05(실제 제품/브랜드/라벨 마스크·실패 정책), D50-06(360/390/Meta Crop/장문/2줄/충돌 규칙), D50-07(사람 광고 품질 수용 기준), D50-09(v2 Job/Receipt/Approval/Artifact 불변, 신규 Job Epoch, Rollback). D50-08 9:16 CTA는 `DECISION_PENDING_PM_OWNER`로 분리.

## 4. 수정된 Owner/PM ZIP V2 — 원본 V1 보존

V2: `docs/integration/handoffs/IT_TEM_P03_A50E_OWNER_PM_REFLOW_REVIEW_ONLY_V2_20261110.zip`. SHA256 `43dba59f205b0cb5fc9a73eb9085481bd059cd1b2c3b3e383a05b32b0ba1579b`. 24 엔트리(22 allowlist+manifest+conditions), 재생성 ZIP SHA **바이트 동일**, 기존 V1 ZIP 불변, 폰트 바이너리·SQLite/DB·Credentials·실제 고객 제품 이미지 **0**, Owner/PM signoff 0, `profile_v3_implementation=NOT_AUTHORIZED`. A50E ZIP은 신규 버전이며 기존 서명 기록을 교체하지 않는다.

## 5. 전 구간 회귀 및 제출 요청

- Python3.12 전체 `pytest -q -p no:cacheprovider -p no:warnings tests`: **1094/1094 PASS**, Exit 0. 기존 1076에 R1 6 + A50E 12 추가.
- React `npm --prefix app test` **57/57 PASS**, `npm --prefix app run lint` 0 errors/warnings, `npm --prefix app run build` PASS.
- 개발 실행 로그 및 SHA: `docs/integration/evidence/A50DR1_A50E_VALIDATION_20261110/`.
- C-A는 **P1-01 서명 손실 반례가 더 이상 발생하지 않음**, P2-02 외부 `--out` Exit0와 정본 무변경, 원본 ZIP SHA 유지, A50E A/C 실제 PNG와 Synthetic Mask/모바일 구도·스트레스 증거, 24-entry V2 ZIP + Owner 승인이 0건인 상태를 독립 차등감사할 것.

## 6. 강제 유지 게이트

`C_A50DR1_A50E_DIFFERENTIAL_AUDIT_PENDING / OWNER_PM_SIGNOFF_PENDING / SIGNED_DECISION_LEDGER_NOT_INITIALIZED / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / REAL_PROVIDER_E2E_NOT_AUDITED / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

**A5-0E 완료는 실제 4:5 CTA 미합성 버그 수정이 아니다.** 기존 Image Owner v2 Runtime에는 여전히 CTA가 없는 상태다. 해당 결함 수정은 실제 Owner/PM 상세 승인 이후의 **A5-1 별도 구현 및 독립감사** 범위에서만 진행한다.
