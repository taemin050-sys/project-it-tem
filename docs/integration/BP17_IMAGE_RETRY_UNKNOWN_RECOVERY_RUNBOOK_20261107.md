# IT-TEM BP17-F — 이미지 재생성 중단·청구 불명확 원장 복구 운영 절차
2026-11-07 · Owner-First / MONITOR_ONLY / No automatic replay
**상태: 읽기 전용 진단·안전 정합화 기준 제안. Live SQL 복구 실행 승인 또는 Provider 과금 검증 완료를 의미하지 않음.**

## 0. 운영 원칙
- 작업 시작 전 실행 JobID·Actor·Generation·Copy SHA·Review SHA·Approval SHA·Image AttemptID/Version·Image SHA·Queue task/context SHA·Provider RequestID/receipt/usage를 **동일 Job으로 결속**한다.
- 기존 완료 Job/Artifact/Receipt/Invoice/Provider Attempt를 절대 변조하지 않는다. 현재 Live 18088 및 Tailscale 10000/8443의 데이터나 서비스 구성에 무단 접근 변경·재시작하지 않는다.
- 반드시 **동일 요청키(request_key)/AttemptID/Queue context** 중심으로 조사한다. HTTP 요청 실패, 브라우저 새로고침, Job 상태만으로 새 유료 요청을 만들지 않는다.
- `BILLING_UNKNOWN` 및 저장 결과/DB 불일치가 한 번이라도 발견되면 **자동 재호출 금지**, 수동 Provider 조회/청구 조회/Artifact 원장 증거 확보 전 HOLD. 사용자에게 실제 비용 확인 불가를 명확히 표시.
- QA Fixture 합성·Text 샘플과 실제 Provider 성공·요금은 서로 다른 출처로 구분한다. 개발용 Mock receipt를 실제 사용료 영수증으로 승격하지 않는다.
- 기존 `MONITOR_ONLY` 유지. 별도 Hard Cap, 자동 비용 예약, PM 건별 과금 승인 체계를 새로 만들지 않는다.

## 1. 읽기 전용 스냅샷 확보

1. 정확한 GCP ROOT, Git SHA/Tree, 실제 배포 포트와 Actor scope 확인. 인증 정보·실제 키·서명 토큰은 감사 산출물에 포함 금지.
2. 원장 파일의 **읽기 전용 스냅샷**을 원본과 다른 제한된 경로에 확보한다. SQLite WAL 활성 상태에서는 단순 파일 복사 대신 `sqlite3.Connection.backup()`을 사용해 일관된 DB 복사본 생성. 파일 SHA, 수집시각 UTC, 원본 절대경로와 접근권한 기록.
3. 사용 중인 원장에 직접 SQL UPDATE/DELETE를 실행하지 말 것. 다음 read-only 검사기에 스냅샷 `runtime/live` 경로와 검증된 32hex JobID만 전달:
   `python scripts/bp13_image_recovery_audit_readonly.py <SNAPSHOT_RUNTIME_LIVE> <JOB_ID>`
4. `live_jobs`, `live_image_attempts`, `queued_ops`, `attempts`, 저장된 PNG/Receipt SHA, 과거 Archive PNG/Receipt SHA를 Actor/JobID/Attempt ID 기준으로 교차 확인한다. 자동 Provider 호출·Queue enqueue는 수행하지 않는다.
5. Provider RequestID가 있는 경우 **Provider 측 요청/응답/usage와 실제 청구원장**을 별도로 대조한다. 소스 외부에서 획득한 근거와 일시를 기록. 발급받은 API key 또는 토큰 자체는 보관하지 않는다.

## 2. 장애 지점별 FAIL-CLOSED 의사결정

| 경계 | 판별 증거 | 기본 판정 | 허용되는 후속 조치 |
|---|---|---|---|
| 재생성 State `PROMPT_READY` commit 후 Queue enqueue 이전 | 새 Attempt `REQUESTED` 있으나 관련 Queue 없음 | `ORPHAN_ATTEMPT_REQUIRES_MANUAL_TASK_RECONCILIATION` | 외부 유료 발행 흔적 없음을 원장으로 증명한 뒤 동일 Attempt의 *적법한 task 복구* 방안을 개발·감사 검토; 자동 새 Attempt 금지 |
| Queue `QUEUED`, Worker 미점유 | 정확한 context_sha의 하나의 Task | `HOLD_INFLIGHT_NO_REQUEUE` | 기존 Task 유지. 명시된 운영 절차로 기존 Worker 준비 상태만 확인. 중복 Task·RequestKey 신규 생성 금지 |
| Queue `RUNNING`, 연결 끊김/Worker 종료 | Provider 발행 여부 미확인 | `HOLD_INFLIGHT_NO_REQUEUE` → 검증된 재시작의 `BILLING_UNKNOWN` | 양쪽 원장·Provider response/usage 대조. 상태를 `QUEUED`로 되돌려 재호출 금지 |
| Provider 성공 이후 Candidate PNG/receipt write 전 실패 | Provider response ID 또는 청구 신호, 파일/DB 없음 | `HOLD_MANUAL_PROVIDER_AND_ARTIFACT_RECONCILIATION` | 동일 Provider 시도 결과 회수 가능 여부 조사. 성공 요청 자동 재전송 금지 |
| Candidate PNG/Receipt 기록 완료 후 DB commit 실패 | 파일 SHA 존재하나 Attempt/Job 상태는 REQUESTED/PROMPT_READY | `HOLD_MANUAL_PROVIDER_AND_ARTIFACT_RECONCILIATION` | 새로 저장된 바이트 SHA 및 Provider 영수증이 동일 Attempt에 결속되는지 수동 판독. 검증되지 않은 수동 DB 완료처리 금지 |
| Provider Attempt `BILLING_UNKNOWN` | 청구 판단 불가 | **HARD HOLD** | 실제 Provider/인보이스 확인 전 중복 실행 불허. 비용·사용량 확정도 불허 |
| 이미지 승인 후 최종 합성 파일 저장 실패 | `IMAGE_APPROVED`, 원본 이미지 승인 정상, Compose artifact 미완료 | **합성만 재시도 후보** | 기존 복합 SHA/고정 Layout/Font 재확인 후 **무과금 서버 합성만** 새로 수행 가능. 이미지 Provider 재호출 금지 |
| Job `COMPLETED` 및 Final PNG·Caption·Receipt/manifest SHA 일치 | 기존 Artifact 동일 | **COMPLETED_READONLY** | 사용자 다운로드만. 이미지 재생성 재실행 금지 |

## 3. 안전한 수동 정합화 요청서 필수 필드

- Job/Actor/Owner Role 및 요청자·수집 시각·환경/코드 SHA
- `input_sha/copy_sha/review_sha/approval_sha`, Copy Generation
- `image_attempt_id`, Version, Retry RequestKey (해시 또는 참조만), Queue TaskID, `context_sha`
- 각 시점의 Queue state·Provider AttemptID/status 및 `billing_unknown`, Receipt의 Provider RequestID와 usage
- DB Snapshot SHA, 기존 Reject 이미지 SHA, Archived bytes SHA, Candidate PNG/Receipt SHA, 최종 PNG/Caption SHA
- Provider/인보이스 조회 결과 출처, 상태 확정 가능 여부, 누락된 검증 근거
- 제안 정합화 대상 **신규 독립 QA 복제본**과 전/후 예상 SHA·Event delta
- **두 차례 검증:** Operator 단독 조사 → 독립 B′가 원장·SHA·Actor/과금 증거 대조; 미확정 시 상태 유지
- 본 문서는 운영용 직접 UPDATE SQL이나 실계정 Provider 재전송 명령을 제공하지 않는다. 진짜 청구가 미확정이면 복구 테스트도 실모델 호출 금지.

## 4. 검증 증거/수용 경계
- 단위: `tests/demo_live/test_bp13_retry_failure_injection.py` (begin/enqueue gap, concurrency, bytes/receipt/DB commit failure), `tests/demo_live/test_bp13_recovery_inspector.py`, `tests/demo_live/test_queue.py`, `tests/demo_live/test_worker_guard.py`.
- 기존 자동 안전성: Queue unique(job_id,stage,context_sha), `assert_image_retry_safe`, Worker restart `reconcile_restart()`은 RUNNING→BILLING_UNKNOWN. 이것은 **안전한 중복 방지**이지 성공 호출의 복구까지 완료했다는 뜻이 아니다.
- B′와 PM에게 모든 파일 무결성·상태 분류 및 no-replay 증거를 보고. 이후 실제 Provider 영수증 기반 운영 정합화는 별도 통제된 과정으로 검증하고 승인된 내용만 프로덕션 절차에 반영.
- 실제 유료 Worker 강제 중단 실험은 이번 무과금 QA 범위가 아니며, **검증하지 않았음**을 보고할 것.
