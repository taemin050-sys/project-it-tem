# BP18 Track B · B0 소스·운영 기준선

2026-11-09 KST · **B0 기준선 확인 완료** · **NOT_RELEASE_READY**

M 원장의 A/B ACK와 `C_PHASE4_MIGRATION_ACCEPTED`가 일치한다. C 판정 범위는 Git/worktree 마이그레이션과 개발 CWD 전환이다. [M 최종 수용 기록](</Volumes/SSD 4T/z_ai_asset/P03_it-tem/migration_handoff/2026-11-09-M3/07_C_PHASE4_ACCEPTANCE_RECORD_20261109.md>) · [ACK 원장](</Volumes/SSD 4T/z_ai_asset/P03_it-tem/migration_handoff/2026-11-09-M3/ACKNOWLEDGEMENT_LEDGER.json>)

| 구분 | B0에서 확인한 값 |
|---|---|
| Worktree | `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/B-outcome-first` |
| 시작·종료 Branch | `integration/bp18-product-complete-20261111` |
| 시작·종료 HEAD | `bd900538887c00b613e37fe9cdd2099fe73dcf7e` |
| 시작·종료 Tree | `b3b169a9834fa32eeabaa2f183ab43a3a5df68a7` |
| Git common dir | `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/project-it-tem/.git` |
| 초기 상태 | Git CLEAN. B0 변경분은 이 근거 문서 한 건 |
| 기존 B 폴백 | `/Users/Shared/ittem-bp18-product-completion-20261107`. M3 ACK 시 같은 HEAD·Tree와 CLEAN 확인 |

## 공식 dev와 Owner 소스

인증된 `gh api`와 `gh pr view`로 공식 `dev`, PR 상태, 원격 브랜치 HEAD를 대조했다. 공식 `dev`는 `62b6dcdef5663d5aa15c596b77ac601b245886db`이며 M3의 로컬 `origin/dev` 스냅샷보다 22커밋 앞선다. [공식 dev](https://github.com/taemin050-sys/project-it-tem/tree/dev)

| 출처 | 상태와 HEAD | 현재 B와 대조 |
|---|---|---|
| [Integration #18](https://github.com/taemin050-sys/project-it-tem/pull/18) | OPEN · `3ddbf732b5816cfeba147cce53a0dfa43cfccca2` | B의 조상. 통합 API·큐·Worker를 바탕으로 정책 Epoch, B 격리, EX12 적용 |
| [Image #24](https://github.com/taemin050-sys/project-it-tem/pull/24) | OPEN · `b3ee33fd524fbbb83890472be890c96974160e9c` | B의 조상. Owner 단일 후보 호출과 모드 분리 유지. B는 4:5 내부 CTA 프로필을 별도로 고정 |
| [FE #26](https://github.com/taemin050-sys/project-it-tem/pull/26) | MERGED · `c9c204b88af5ce1b25dfda501d16446750a41204` · merge `b73d6452ba0f4f9e40fba4c17c9d37534136759b` | 마지막 두 Owner 커밋의 승인 시 버전 확인, 승인 성공 후 이동, 입력만 바뀐 새 광고 초기화 보호를 B가 별도 구현. 이미지 바이트 결속 문제는 아래 P0 참조 |
| [Text #27](https://github.com/taemin050-sys/project-it-tem/pull/27) | MERGED · `33c46b765c17b8f028553c343124f29de2969382` · merge `62b6dcdef5663d5aa15c596b77ac601b245886db` | 기능성 종류별 규칙, `basis_url`, 수정 이슈 입력, 규칙 평가 100건과 홀드아웃 30건의 출처. B `2ab998d`의 구조화된 검수 입력과 Copy SHA·Review SHA·정책 Epoch/CAS를 보존하며 선별 검토 |

10/26 계약에서 사진 2–5장과 참고 0–5장, 화장품 VLM 선행, 검색 실패 시 AI 추론 표시, 카피 및 이미지 사람 승인, 규칙+LLM 검수, 단일 4:5 PNG와 Caption을 확인했다. 예산은 현재 승인된 `MONITOR_ONLY`를 적용한다. 최종 인수 범위는 38개 항목과 3비율 × 2모드다. [Owner 결정 레지스터](../contracts/DECISION_REGISTER.md) · [Release Master r0.1](</Volumes/SSD 4T/z_ai_asset/P03_it-tem/handoffs/B/2026-11-09-codex-self-contained-v3/SOURCE_REFERENCES/RELEASE_ACCEPTANCE_MASTER_r0.1.md>) · [38개 원문 CSV](</Volumes/SSD 4T/z_ai_asset/P03_it-tem/handoffs/B/2026-11-09-codex-self-contained-v3/DOCS/REQUIREMENTS_38_SOURCE_EXTRACT.csv>)

## 현재 실행 증거

| 층위 | 관측 결과 |
|---|---|
| Python 회귀 | Mac Studio에서 전체 **996 passed, 22.65초**. Loopback만 허용한 네트워크 격리, Provider 호출 없음 |
| React | 동일 소스의 M3 ACK 시 **52/52 통과**. M의 별도 원본 로그도 **52/52 통과** |
| 배포·Health | GCP B 배포 Source SHA·Tree가 위 기준선과 일치. B 런타임 `/home/macstudio/ittem-bp18-product-completion-20261111`, Backend `127.0.0.1:18100`, Health HTTP 200. FE `index-kMU_J4Oy.js` SHA-256 `50a1e4ca88129ac125d5cd4092b06b8a8efc668ad00382ef95ddfc7f33b667e8` |
| SSO | B HTTPS에서 서명 세션 HTTP 200, 미서명 HTTP 401. 이번 Mac 세션에서 PM Actor `bp18_b_taemin`으로 인증되지 않음 |
| DB·Worker | Policy Epoch 1. B Job은 COMPLETED 9건, INPUT 5건. 큐 0건, Provider Attempt 0건. B Worker 프로세스·unit과 B 전용 Worker Secret이 확인되지 않았으며 Live 실행 capability는 차단 상태 |
| Font·CTA | 배포 NanumGothic SHA-256 `48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733`. B 소스의 4:5 v3 프로필은 1080×1350과 이미지 내부 CTA를 지정한다. 폰트 권리 증빙과 실제 결과의 가독성·시각 수용은 대기 |
| Paid·Browser·Human | 이번 B0에서 Provider 호출 0회. 새 실모델 Receipt, 실제 광고 PNG/Caption 다운로드 SHA, Owner/PM 평가 없음. PM의 실제 서명 세션과 사용권 확인된 제품 입력이 필요 |

C가 이전 Mac Python 3.12에서 재현한 `test_existing_output_replaced_never_after_concurrent_publication`의 fork+SQLite 동시 발행 예외는 열린 항목으로 유지한다. 이번 전체 통과와 과거 C의 독립 실패 기록을 함께 보존한다. Signed SSO, B5 Rollback, EX12는 기존 수용 증거를 계승하며, 관련 구현이 바뀌면 해당 회귀를 검증한다. [알려진 테스트](../../tests/demo_live/test_bp17_shared_minimal_export.py:156) · [B5 Rollback](BP18_B5_P102_SSO_AWARE_ROLLBACK_GATE_20261108.md) · [EX12 GET-only 근거](BP18_B6_EX12_DOWNLOAD_GET_ONLY_RECOVERY_20261108.md)

## 38개 수용 기준의 증거 상태

| 증거 층위 | B0 기준 |
|---|---|
| CODE_IMPL | 동일 B HEAD의 11월 8일 매트릭스는 IMPLEMENTED 11, PARTIAL 22, PROVISIONAL 5. B0에서 아래 소스 차이를 추가 확인 |
| FIXTURE·브라우저 | 이전 후보 HEAD의 6조합 fixture와 EX12 GET-only 브라우저 회귀 증거를 매트릭스에서 분리해 유지 |
| REAL_PROVIDER·다운로드 | B의 유효 실모델 6조합은 0/6. B0에서 Provider Attempt나 광고 다운로드 SHA 증거가 추가되지 않음 |
| HUMAN·C·RELEASE | Owner/PM 평가와 제품 범위 C 독립 인수 대기. 38개 최종 인수는 0/38, 정식 Release는 NOT_RELEASE_READY |

항목별 구현·fixture·사람 수용의 상세 상태는 F01–F20, V01–V08, S01–S10의 이전 매트릭스에 보존한다. [B6 F/V/S38 매트릭스](</Volumes/SSD 4T/z_ai_asset/P03_it-tem/handoffs/B/2026-11-09-codex-self-contained-v3/SOURCE_REFERENCES/FVS38_STATUS_B6_SNAPSHOT.json>)

## 구현 순서와 C 검증 범위

| 우선순위 | 관측된 차이와 다음 검증 |
|---|---|
| P0 · B1 · S02/S04/S10 | Worker가 실행 직전에 큐의 Actor를 현재 허용 목록과 다시 대조해야 한다. Worker의 `IT_TEM_*_MODEL` 선택과 Secret Loader의 `OPENAI_MODEL_*` 선택을 일치시킨다. B 전용 Worker Secret, 모델 권한, 관리되는 Worker 시작, MONITOR_ONLY, 동일 요청 재실행과 BILLING_UNKNOWN 차단을 확인한다. [Worker](../../demo_staging/live/worker.py:96) · [Secret Loader](../../demo_staging/live/env_loader.py:43) |
| P0 · B2 · F16/S03 | 후보 파일 URL이 고정되고 React Query는 경로를 캐시 키로 사용한다. 재생성 전 이미지 바이트가 남아 승인 대상 SHA와 어긋날 수 있다. 표시 바이트를 현재 후보 SHA에 결속하고 이전 후보·다른 Actor·동시 변경을 차단한다. [후보 매핑](../../app/src/api/liveMapping.ts:48) · [캐시](../../app/src/api/useJob.ts:40) |
| P0 · B2/B3 · F07/F09/F11 | 현재 B 검수와 #27 평가기는 규칙 기반이다. 첫 실제 B2 전에 별도 LLM 검수를 규칙 검수와 연결하고, 실제 Copy·Review·정책 Epoch에 결과를 결속한다. #27의 근거·기능성 규칙과 평가 데이터를 검증하고 B의 구조화된 수정 계약을 유지한다. [B 검수 경로](../../demo_staging/live/contracts.py:94) · [B 수정 문맥](../../demo_staging/live/pipeline.py:250) |
| P0 · B2 · F14/F15/F17/V01–V08 | 인증된 PM Actor와 사용권이 확인된 실물 사진으로 4:5 Composed 1건을 끝까지 수행한다. 1080×1350 내부 CTA, 제품·라벨·한글, PNG와 UTF-8 Caption의 브라우저 다운로드 SHA, Actor/Job/Approval/Prompt/Model과 Provider Receipt를 함께 기록한다 |
| P1 · B4–B6 | 나머지 5개 실모델 조합, 9:16 CTA 정책, 360/390px 모바일, EX03/EX10과 12개 예외, 실측 성능·비용과 Owner/PM UAT를 증거로 채운다. C는 해당 후보 SHA의 서명 SSO·격리, 재실행 안전성, Rollback, 실모델 Receipt와 다운로드 SHA 및 사람 평가를 독립 재확인한다 |

네트워크를 차단한 가짜 Provider에서 세 결함을 재현했다. 허용 목록에서 빠진 Actor의 오래된 분석 큐 항목이 가짜 호출 세 건을 실행했다. Worker 중단 복구가 Queue만 `BILLING_UNKNOWN`으로 바꾸고 비용 원장을 `DISPATCHED`에 남겼다. Fixture Job에 LIVE Prompt를 실행할 수 있었고, 응답 전 카피를 다시 승인하면 이전 Prompt가 새 승인에 붙었다. 이 재현은 GCP나 실제 Provider에 접근하지 않았다.
