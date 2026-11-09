# IT-TEM P03 Track A — A3R.1 Fixed-Source Attestation Hardening: C-A 차등 재감사 제출

**작성:** 2026-11-09 KST · Track A 개발 자체검증 보고서 (독립감사 아님)
**공식 제출 상태:** `A3R1_SOURCE_ATTESTATION_DEVELOPER_VALIDATED / C_A3R1_DIFFERENTIAL_AUDIT_PENDING / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`

## 1. 인수 기준점·변경 경계

- 승인 Worktree: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`
- Branch: `integration/bp18-baseline-e2e-20261111`
- 착수 시 HEAD: `258fe731502cf020d6a9fb7af8a065b63902fc39`; Tree: `52cae8a0949d4277f08c0e8fe9ac9099ce8969ca`; CLEAN
- C-A3R 독립 감사 정본: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A3R_DIFFERENTIAL_AUDIT_20261109_2215KST.md`; SHA256 `9bc88839cb5295ee7cc1730b93236268b79cb4646058c892dd27704d4092dae8`
- C-A3R 원본 취약 동작 재현: `audit/track-a/evidence/C_A3R_20261109_2215/C_A3R_source_attestation_bypass.py`; SHA256 `6006817185cca48a27e9ac5f7233965f74b85461ccfc8c4aa37e9d1967d77a93`. **독립 감사 원본은 한 바이트도 변경하지 않음.**
- 변경 코드 커밋: `be79ceb18722ac6f11195fdeb722212527d89f5a`; Tree `a5f7e6f86795848a17c7c75594414a95a5ba16b4`.
- 최종 문서/증거 제출 HEAD·Tree: 본 보고서 커밋 후 `git rev-parse HEAD 'HEAD^{tree}'`를 기준으로 고정하여 C-A에 전달. **로컬 개발 SHA는 실제 GCP 배포 SHA가 아님.**
- 기존 수용 유지: `C_A2_SAFETY_CODE_ACCEPTED_WITH_KNOWN_TEST_NOTE`, `C_A3_LOCAL_RELIABILITY_ACCEPTED`, `C_A3R_ORIGINAL_FINDINGS_ACCEPTED`. A2 Serving 권한/과금 및 A3 BP17 동시 발행, A3R 경로·3중 원장 코드는 변경하지 않음.
- 변경 파일: `scripts/a3_track_a_guarded_readiness.py`, `tests/demo_live/test_a3_guarded_readiness.py`, `docs/integration/BP18_A3_GUARDED_DEPLOYMENT_BILLING_RUNBOOK_20261109.md`, 본 보고서와 `docs/integration/evidence/A3R1_20261109/*`만.

## 2. A3R-P1-04 수정 전/후 대조

문제: 기존 `source_manifest()`는 5개 Lock 및 A3 증거 6개만 HEAD Git Blob을 직접 비교하고, Worker/API/Owner 등 다른 추적 파일은 `git status --porcelain`에 의존했다. C-A가 실제 A/B가 아닌 격리된 고정 Git Archive에서 Worker 파일 바이트를 변경한 뒤 `git update-index --assume-unchanged` 또는 `--skip-worktree`를 적용하자, STATUS가 false-CLEAN이면서 Source Integrity가 잘못 PASS했다.

**재현 (수정 전 `258fe73` 고정 Git Archive → 새 임시 Git 저장소):**
`01_BEFORE_C_ORIGINAL_BYPASS.log`에서 `SOURCE_GATE PASS` 2건, `SOURCE_INTEGRITY_BYPASS_REPRODUCED=2/2`, 스크립트 exit 0을 확인. 재현 시 Git의 특수 인덱스 플래그 및 파일 변조는 임시 Git에만 적용하고 `finally`에서 복원.

**수정 (`be79ceb` 고정 Git Archive → 별도의 임시 Git 저장소):**
- `02_AFTER_C_ORIGINAL_EXPECTED_FAIL.log`: 취약 동작을 PASS라고 주장하는 옛 C 스크립트 Assertion이 예상대로 실패(exit 1). 이것은 새로운 보안 테스트 FAIL이 아니라 **옛 취약성의 재현 불가능함을 나타내는 증거**. 원본 C 스크립트를 삭제·수정·약화하지 않았다.
- `03_AFTER_C_BOTH_BLOCKED.log`: 동일 C 스크립트 소스를 메모리에서만 부정 검증 조건 `SOURCE_GATE=HOLD`로 바꿔 실행하여 `assume-unchanged`, `skip-worktree` 모두 Worker 바이트 변조와 false-clean 상태에서도 `SOURCE_GATE HOLD`, `PAID_GATE HOLD`; `SOURCE_INTEGRITY_BYPASS_BLOCKED=2/2`; 스크립트 원본 SHA 불변.
- 정식 테스트에 `test_a3r1_hidden_serving_worker_change_fails_closed` 2조건, `test_a3r1_special_index_flag_alone_is_not_a_clean_source`, Worker/API·Text·Image·Frontend 실제 바이트 변조 부정, tracked 파일 삭제/심볼릭 링크, Git Status 모의 false-clean, A3R 증거 누락 및 정상 HEAD 정합성 시험 추가.
- 위 공격/회귀는 **Track A/B 원본 Git Index/Source를 절대 변경하지 않고**, `git archive HEAD`를 새로운 임시 디렉터리에 추출한 후 별도 `git init`한 테스트 저장소에만 적용. 이 임시 Git HEAD는 원본 커밋과 다른 ID를 갖지만 **Tree 및 파일 바이트는 고정 입력과 동일**.

## 3. 새로운 Source Manifest V3 검증 계약

대상 소스: HEAD Tree의 **전체 370개 추적 파일**(현재 코드 커밋 기준), Serving Worker/API, FE/Text/Image Owner, 보안·정책·스키마·Config, Lock, 테스트, 배포 진입점과 문서를 빠짐없이 직접 검증한다. 특정 파일만 선택하여 attestation PASS를 반환하지 않는다.

구현:
1. `git ls-tree -rz --full-tree HEAD`를 기준으로 전 파일 경로, blob OID, mode를 확보. 현재 저장소는 SHA-1 object format이며, unsupported Git object mode / submodule / 비정상 경로 => HOLD.
2. `git ls-files -v -z`로 특수 플래그를 읽고 HEAD 경로 집합과 비교. 일반 `H`가 아닌 `h`(assume-unchanged), `S`(skip-worktree) 등은 값 자체로 HOLD.
3. 파일마다 `O_DIRECTORY|O_NOFOLLOW` 기반 부모 dirfd와 `O_NOFOLLOW` 일반 파일 FD를 열고 실제 파일 bytes로 Git blob OID(`sha1("blob <size>\\0" + contents)`) 및 executable mode를 비교. 누락·변조·심볼릭 링크·해시/파일 모드 불일치·읽기 중 변경은 HOLD.
4. 전 파일 순회 후 HEAD, Tree, Index 플래그를 재확인. `git status --porcelain` 결과는 부가 관측(`git_status_clean`)일 뿐, 강한 `worktree_clean`이나 `source_integrity_gate`의 유일한 근거로 사용하지 않음.
5. **Lock 5/5**, 기존 **A3 evidence 6/6**에 더해 **A3R evidence 7/7**을 별도 이름과 SHA256으로 검증. 해당 파일 실제 바이트가 `HEAD:<path>`의 Git Blob과 불일치하거나 누락되면 HOLD. 최신 A3R.1 증거는 제출 패키지에 별도 SHA256_MANIFEST로 보호되며 A3/A3R 증거 버전과 혼동하지 않음.
6. `build_provenance`: 고정 `source_commit`, `source_tree`, 전체 검사 파일 수/종합 SHA, `expected_git_archive_sha256` 제공. **불변 Archive의 예상 SHA**는 향후 빌드 파이프라인의 비교 기준일 뿐, 실제 `built_artifact_sha256` 및 `running_build_sha256`은 `null`, `build_runtime_match_gate=NOT_AUDITED`로 남김. 실제 A 배포 전 서명된 아티팩트/프로세스 SHA 증거를 별도로 요청.
7. `source_integrity_gate` / `ledger_integrity_gate` / `qa_deployment_readiness_gate` / `paid_worker_authorization_gate` 분리. 지금 QA 배포 및 유료 Worker는 무조건 HOLD.

**적용 범위 한계:** 이 검증은 해당 시점 로컬 tracked Worktree의 바이트/HEAD 일치성을 입증한다. 숨겨진 외부 런타임, Git 비추적·ignored 파일의 실행 간섭, Build Pipeline과 실제 GCP 실행 이미지의 일치, root 권한 행위자의 동시 변경까지 자동 인증하지 않는다. 운영 배포는 **검증된 Git Archive로 격리 빌드하고, Build 및 실행 프로세스 SHA를 별도 독립 비교**해야 한다. SHA-1 Git 저장소는 플랫폼에서 현재 사용 중인 형식이며 SHA-256 기반 Archive SHA가 공급망 검증을 보강한다.

## 4. 테스트·사전/사후 증거

| 항목 | 실제 결과 | 파일 / 근거 |
|---|---|---|
| 수정 전 C 원본 공격 | 2/2 우회 재현, Exit 0 | `01_BEFORE_C_ORIGINAL_BYPASS.log` |
| 수정 후 C 원본 공격 | 옛 PASS Assertion 예상대로 실패, Exit 1 | `02_AFTER_C_ORIGINAL_EXPECTED_FAIL.log` |
| 수정 후 동일 공격 HOLD 검증 | 2/2 차단, Exit 0 | `03_AFTER_C_BOTH_BLOCKED.log` |
| A3R.1 신규 포함 Readiness | **55/55 PASS**, Exit 0 | `04_A3R1_55_TARGET.log` |
| Python 전체 | **1052/1052 PASS**, Exit 0 | `05_FULL_PYTHON.log` |
| C-A3R 원본 별도 부정 테스트 | **13/13 PASS**, Exit 0 | `06_C_A3R_13_NEGATIVE.log` |
| C-A2 원본 별도 부정 테스트 | **7/7 PASS**, Exit 0 | `07_C_A2_7_NEGATIVE.log` |
| BP17 동시 발행 | 10회 × spawn+forkserver = **20/20 PASS**, Exit 0 | `08_BP17_20_RACE.log` |
| React 전체 | **57/57 PASS**, Exit 0 | `09_REACT_57.log` |
| ESLint / Build | **PASS / PASS**, Exit 0 | `10_LINT.log`, `11_BUILD.log` |
| 코드 커밋 CLEAN Manifest | 370/370 HEAD Blob PASS, Index PASS, 5 Lock + 6 A3 + 7 A3R evidence PASS | `12_CODE_COMMIT_SOURCE_MANIFEST.json` |
| 본 증거 집합 | 별도 `SHA256_MANIFEST.txt`로 각 로그/JSON 해시 보존 | `docs/integration/evidence/A3R1_20261109/` |

로컬 실행은 Mac Studio Python3.12.2, Fake/Fixture, 유료 환경변수 비활성화 및 외부 유료 API 키 unset. 실제 Provider POST 0, GCP 배포 0, DB/Job/Artifact/Receipt 변경 0.

## 5. 보호 및 GCP 잔여 게이트

C-A3R이 2026-11-09 22:15 KST 읽기 전용 SSH로 관측한 기존 GCP A SHA는 `9879eb0f85747312a224ecd898aaff84d834590b`이며, Queue LIVE 0건, Cost Attempt 0건, 예상 Owner Image Attempt DB **MISSING**, A `/health` HTTP 200, Signed SSO **NOT_AUDITED**. **A3R.1에서 GCP에 새 배포·접속·재시작·원장 생성·Migration 또는 외부 POST를 하지 않음.** 오래된 SHA/원장 경로/SSO/rollback 문제는 여전히 독립 승인 대상.

- 기존 정책 SHA 없는 Legacy LIVE Approval의 자동 승인·마이그레이션 불가.
- `SUCCEEDED_USAGE_UNPRICED`는 USD 0이 아님. Provider 예산/실제 Invoice 대사가 끝나기 전 유료 Worker HOLD.
- FE PR #26 > Text PR #27 > Image PR #24 제품 통합 우선순위 유지. Image는 Freeform/Composed×3:4/4:5/9:16, 요청당 1장 및 명시적 재생성만 허용.
- Release Master F01–F20/V01–V08/S01–S10 중 이번 변경으로 증거가 증가한 항목은 **F20/S05의 로컬 소스 무결성 계약**에 한정. 실제 GCP/Signed SSO, 실모델, UX/품질, 원장/예산 및 상용화 수용 항목은 NOT_AUDITED/HOLD를 유지.

## 6. C-A3R.1 차등 재감사 수용 요청

1. 신규 최종 HEAD/Tree/CLEAN 상태 고정. **A3R-P1-04만** 집중 검증; 기수용 A2/A3-1/A3R 3건 재설계 금지.
2. C-A 원본 `C_A3R_source_attestation_bypass.py` 및 원본 부정 13건의 SHA 보존. C 원본 옛 취약성 Assertion 실패를 보안 회귀 FAIL로 해석하지 말고 새로운 **HOLD 부정 Assertion**을 독립 작성하여 두 플래그 각각 Worker 변조를 차단하는지 확인.
3. Worker뿐 아니라 실제 FE/Text/Image Owner, config, schema, entrypoint 등 **전체 HEAD 트리**에 누락·변조·simulated false-CLEAN 시나리오 적용, Index 특수 플래그와 실제 Blob 해시 불일치 구별.
4. 정상 CLEAN 소스에 대해 370개 이상 HEAD Blob PASS, Lock 5/5, A3 6/6, A3R 7/7 SHA 검증과 Archive SHA 재현. 새 최종 제출 커밋의 SHA가 기존 코드 커밋 `be79ceb`과 달라지는 점을 구별.
5. 기존 A3R 경로 격리·미정의 원장·SQLite/WAL 보존 44개, C-A3R 13개, C-A2 7개, BP17, 전체 Python, React/lint/build 재확인.
6. `build_runtime_match_gate=NOT_AUDITED`, `qa_deployment_readiness_gate=HOLD`, `paid_worker_authorization_gate=HOLD`가 소스 PASS로 자동 전환되지 않는지 확인.
7. QA 후보 배포·Signed SSO·실제 provider/예산·유료 Worker는 **독립 변경 게이트**이며 기존 A/B/GCP/보호 18088/18095 환경 변경 금지.

**최종 개발 자체 판정:** `A3R1_SOURCE_ATTESTATION_DEVELOPER_VALIDATED / C_A3R1_DIFFERENTIAL_AUDIT_PENDING / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.
