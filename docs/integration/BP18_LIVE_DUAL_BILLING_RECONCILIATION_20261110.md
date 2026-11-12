# BP18 Live Dual 과금 미확정 대사와 Queue 재개

`LIVE_DUAL_V1`의 `BILLING_UNKNOWN`은 Web 입력과 별도로 Queue의 **모든 신규 Claim**을 막는다. Worker 재시작은 원본 시도를 다시 전송하지 않는다. 운영자는 원장 원본과 증거를 보존하고, 정확한 사고에 대한 종결 기록을 작성해 **관련 없는 승인 작업**의 재개만 허용할 수 있다. 사고의 부모·Freeform 자식과 이미 대기 중인 시안은 계속 격리된다. 이미 저장된 정상 결과는 기존 다운로드 계약으로 읽을 수 있다.

## 사고 확인과 근거

1. Worker와 배포 작업을 멈춘 상태에서 현재 Release, 정확한 Queue Task ID와 `context_sha`, Actor, 부모·자식, `authority_sha`, CostLedger 및 Native Owner 원장을 확인한다. 기존 B5 백업과 [읽기 전용 사고 조사 절차](BP17_IMAGE_RETRY_UNKNOWN_RECOVERY_RUNBOOK_20261107.md)를 사용한다.
2. 승인된 Release 소스에서 사고를 조회한다. 명령은 기존 DB를 읽기 전용으로 열고 같은 사고의 `plan_sha`, 원장 상태·영수증 SHA, 가능하면 Native Image Owner의 사용량과 응답 ID를 출력한다. 조회 결과는 보호 경로에 보관한다.

```bash
umask 077
cd "$B_ROOT/repo"
python3 -m scripts.bp18_dual_billing_reconcile \
  --root "$B_ROOT" inspect "$TASK_ID" > "$PROTECTED_PLAN"
```

| 대사 기록 | 판단 기준 |
|---|---|
| `RECEIPT_MATCHED_UNPRICED` | 동일 Image Intent의 CostLedger payload SHA, Native Request SHA·응답 ID·사용량·저장 결과가 일치한다. 실제 금액은 미확정이며 기존 CostLedger 상태를 보존한다. |
| `QUARANTINED_UNRESOLVED` | 영수증을 정확히 연결할 수 없거나 Text의 전체 하위 Attempt를 확정할 수 없다. 운영 승인 기록과 검토 근거를 결속한다. 사고의 과금 상태는 미확정으로 보존한다. |

Native 원장 행이나 인보이스가 없다는 사실에서 미과금 또는 무전송을 추론하지 않는다. 도구는 실제 청구액을 기록하거나 결과를 수동 성공 처리할 권한을 갖지 않는다. 검증 가능한 Provider 청구 원본은 별도 대사 대상으로 보존한다.

## 승인 기록과 반영

운영 승인 담당자는 검토한 근거 파일과 승인 JSON을 운영 계정 소유의 보호 경로에 둔다. 디렉터리는 `0700`, 파일은 `0600`이다. 승인 JSON에는 버전 `1`, B 역할 원장의 admin Actor인 `operator`, 실제 승인 식별자 `approval_reference`, `plan_sha`, 근거 파일의 `evidence_sha`, 위 표의 `disposition`, `acknowledge_no_replay: true`를 넣는다. 운영 계정과 승인 파일이 CLI의 접근 경계이며, Web Actor에게 원장 변경 권한을 부여하지 않는다.

```bash
python3 -m scripts.bp18_dual_billing_reconcile \
  --root "$B_ROOT" apply "$TASK_ID" \
  --approval "$APPROVAL_JSON" --evidence "$PROTECTED_EVIDENCE"
```

명령은 B5 운영 잠금, Worker 잠금 순으로 확보한다. Release의 실행 코드와 Queue 정책, 계획/근거 SHA, admin 등록, Task·Actor·Job·Intent를 다시 확인한다. `RUNNING` Queue 행이나 정리 전 `DISPATCHED` 원장이 남아 있으면 차단한다. 부모 그룹의 hold를 먼저 고정한 뒤 Queue에 불변 대사 기록을 추가한다. 중간 중단은 전체 차단을 유지하고 같은 승인으로 다시 실행할 수 있다. 승인이나 사고 문맥이 바뀌면 새 검토를 요구한다.

## 재개와 복귀

- `global_queue_held: true`는 다른 사고 또는 유효하지 않은 기록이 남아 있는 상태다. 해당 사고를 확인한다.
- `global_queue_held: false`는 무관한 사전 승인 작업이 Claim 가능하다는 뜻이다. 실제 Worker 기동은 별도 운영 승인과 현행 Signed B, B5, Worker-only credential을 사용한다. `apply`는 Worker를 기동하거나 Provider를 호출하지 않는다.
- 같은 Task와 CostLedger 멱등 키, 원본 영수증 및 파일의 SHA는 유지된다. 직접 SQL 초기화, Job 재호출, 과금 미확정을 0 USD 또는 성공으로 기록하는 절차는 허용 범위 밖이다.
- 대사 기록을 읽는 코드보다 앞선 호환 복귀 소스는 원본 `BILLING_UNKNOWN`을 읽어 전역 차단을 다시 적용한다. 대사 기록과 원본 원장을 보존하고, 승인된 소스로 돌아갈 때 유효한 기존 결속을 다시 읽는다. DB를 이전 시점으로 덮어쓰는 방식으로 차단을 해제하지 않는다.

격리 검증은 `tests/demo_live/test_live_dual_billing_reconcile.py`에서 Native Receipt 유실 후 원장 결속, 완료 형제 파일 보존, 대기 형제 Claim 금지, 무관한 작업 재개, 승인·근거 변조, 복수 사고, 잠금과 중간 실패를 재현한다. 테스트는 MockTransport와 임시 원장으로 실행한다.
