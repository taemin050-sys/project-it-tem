# IT-TEM P03 Track A — A5-0D Owner/PM v3 결정 준비 차등감사 제출 자료

**일자:** 2026-11-10 KST
**개발 판정:** `A5_0D_DECISION_PACKET_PREPARED / OWNER_PM_SIGNOFFS_0 / A5_1_IMPLEMENTATION_HOLD`
**권한 경계:** Owner Source First FE #26 > Text #27 > Image #24 > Serving; A2~A3R.1 안전성·권한·Approval·과금·SHA 변조 금지. Track B, GitHub 공식 dev/PR, GCP, 운영 Job/Receipt/Artifact, 유료 Provider 변경 없음.

## 1. 감사 기준

- 직전 C-A 수용 코드 기준: HEAD `3842db04123fc8a8c681a2bf50c90dc82464c143`, Tree `03e9d11eaa0d3e02d57f09367fa571f8d0a65580`, 기존 A/B Worktree 원본 불변.
- C-A4.2/A5-0 report: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A42_A50_DIFFERENTIAL_INDEPENDENT_AUDIT_20261110.md`; SHA-256 `360674367278527c0a6ea5cf099212417b16418e199edffb541a3dc72657e940`. 결과 `C_A42_FIVE_OFFICIAL_REACT_FIXTURE_BROWSER_E2E_ACCEPTED`, `C_A50_DESIGN_MOCKS_REPRODUCIBLE_PROPOSAL_ACCEPTED`, `A41_PRODUCT_CTA_01_HOLD`.
- **본 A5-0D는 프로덕션 Profile v3 구현 작업이 아니며**, 코드·렌더러·데이터베이스·A4 브라우저 하네스를 수정하지 않는다. 새로운 HEAD/Tree는 문서/제안 전용 스크립트/증거/테스트를 보존하는 **새 커밋**에서 확인해야 한다.

## 2. 실체화된 제출물

| 자료 | Track A 루트 기준 경로 | 권한 상태 |
|---|---|---|
| Owner/PM용 결재/검토 본문 | `docs/integration/BP18_A50D_OWNER_PM_PROFILE_V3_DECISION_PACKET_20261110.md` | REVIEW_ONLY |
| D50-01~09 서명 기록 CSV | `docs/integration/BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv` | D50-01 기존 정책 외 전원 대기 |
| 비실행 Profile v3 계약 Envelope | `docs/integration/BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json` | selected_profile=null / Epoch=null / signoffs=null |
| A/B/C 비교 가독성·Safe 여백 사전점검 | `docs/integration/evidence/A50D_20261110/A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json` | 모든 후보 제안 하단 여백 미달 |
| 기존 FE Pretendard 후보·원문 라이선스 증거 | `docs/integration/evidence/A50D_20261110/A50D_EXISTING_FE_PRETENDARD_LICENSE_CANDIDATE.json` | 후보만 확인 / 상용 서버 승인 대기 |
| 원본+3종·모바일 목업, CSV, JSON을 묶은 PM 검토 ZIP | `docs/integration/handoffs/IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip` | 18개 엔트리, 서명 0건, Font/SQLite/Credential 0 |
| 재현 스크립트·회귀 | `scripts/a50d_owner_pm_decision_preflight.py`, `scripts/a50d_make_owner_pm_review_zip.py`, `tests/product_e2e/test_a50d_owner_pm_decision_preflight.py` | 문서/증거만 생성 |

ZIP SHA-256: `fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff`. 임시 격리 경로에서 Bundle을 다시 생성하여 1:1 **재현 가능한 ZIP 바이트 SHA 일치** 검증. ZIP에는 타사 이미지·상용 서체 바이너리·운영 DB·비밀키가 없다.

## 3. 새로 규명한 Product Fidelity 결정 위험

- 제안 임계값: 360px에서 CTA 글자 ≥16px, Safe Frame 하단 inset ≥12px, CTA 색 대비 ≥4.5:1 — 이는 **정식 Owner/PM 승인 기준이 아니라 협의용 예시**임.
- A/B/C 현재 360px CTA = 15.67/16.33/16.67px, 내부 safe bottom = 2.00/2.00/1.33px, 버튼 글자 대비 = 10.93/6.77/9.96:1. 제안 예시 기준으로 모두 하단 Safe margin 실패, A는 글자 크기 실패.
- 이 Safe Frame은 v2 Owner Layout 내부 box이지 Instagram/Meta 플랫폼 인증 Safe Zone이 아니다. 실제 사용자 이미지 crop/브랜드/라벨 보호를 임의로 PASS하지 않음. 가상 제품 Target=(466,418,611,1183)은 Segmentation 결과가 아니라 아트디렉션 지시.
- 해결 방향 제안: **A Editorial Center = 기본 검토**, **C Contrast Action = CTA 강조 옵션**, **B Editorial Left = 브랜드 에디토리얼 대안**. 기계 제안 좌표는 정식 계약 아님. 상하 구도 및 실제 객체/CTA 영역이 충돌하면 새로운 v3에서 제품·카피 리플로우/검출 보호를 설계해야 하며 Overflow Fail-Closed.
- 기존 Mac FE에 `pretendard@1.3.9` 설치, `app/package-lock.json` SHA `de5d56ac4eff9570c11b2dcb9c939088073f500537df02eaa25019b49fb0b6e7`, 로컬 Variable TTF SHA `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22`, OFL-1.1 LICENSE SHA `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`; Pillow 렌더로드, 해당 QA 카피 cmap 19/19 확인. **Font 바이너리는 어떤 제출물에도 포함하지 않았음.** FE 설치가 곧 서버 배포/굵기·권한·특정 사용권 승인인 것은 아니므로 D50-04 계속 HOLD. Upstream: https://github.com/orioncactus/pretendard/blob/main/LICENSE (대안 Noto CJK KR https://github.com/notofonts/noto-cjk).
- D50-08 9:16 CTA는 `DECISION_PENDING_PM_OWNER`로 4:5와 철저히 분리.

## 4. 테스트·증거·권한 검증

- A5-0D 표적 + 기존 A5-0 Mock: **24 PASS**, Exit Code 0. 이 중 신규 A5-0D는 서명 0건, Draft Review Only, 선호안 SHA, 폰트 증거, 레거시/9:16/배포/유료 HOLD, ZIP 내용과 모든 내부 파일 SHA 확인을 포함.
- Mac Studio Python 3.12 전체 `pytest -q -p no:cacheprovider -p no:warnings tests`: **1076/1076 PASS**, Exit 0, 기존 A2/A3/A4/A5-0 회귀 포함.
- React `npm --prefix app test`: **57/57 PASS**, ESLint 0 warning/error, Vite Build PASS. 모두 실제 제품 실행 소스 무변경에서 재확인.
- 로그·SHA 검증: `docs/integration/evidence/A50D_20261110/`의 개별 자산 SHA 및 제출 Manifest를 독립 C-A가 재검산할 수 있음.
- C-A 권고 재실행: 고정 Git Archive를 격리한 다음 원본 A50 Manifest와 새 A50D Geometry/Contract/CSV를 대조. `python3 -B scripts/a50d_owner_pm_decision_preflight.py --out <temporary-owned-directory>`는 **docs 아래 정본 CSV·Contract도 갱신하므로**, 재실행은 원본 Worktree가 아닌 **격리 복제 checkout**에서만 진행. ZIP 생성 역시 격리 출력 경로로 한정; 절대 Owner 서명 값을 자동 채우지 않는다.
- A5-1 구현 게이트: D50-02/03/04/05/06/07/09 Owner/PM 서명 + 최종 immutable versioned Profile JSON SHA, 폰트/라이선스 SHA, 실제 제품 Safe/Label 검수 기준 및 Policy Epoch와 Rollback 승인. 그 전 Owner 원본/Serving Adapter v3 코드 작성 금지.

## 5. 최종 상태

`A50D_REVIEW_PACKET_READY / NO_ACTUAL_OWNER_PM_APPROVAL / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / REAL_PROVIDER_E2E_NOT_AUDITED / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

C-A에는 **설계 제안의 재현성/근거 충실도**만 검토 요청하며 실제 Owner/PM 서명을 대신하지 않는다. 서명/보완 요청 수령 후에는 별도 A5-1 승인된 구현 코드 단위에서 C-A 차등감사를 요청한다.
