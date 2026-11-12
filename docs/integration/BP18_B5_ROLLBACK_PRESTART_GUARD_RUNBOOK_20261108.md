# BP18 B5 — Track B 정책 Epoch Rollback Guard 및 운영 진입점

**SSOT:** isolated `integration/bp18-product-complete-20261111`, `deploy/systemd/`, `scripts/bp18_b5_release_prestart.py`.

대상 GCP 루트: `/home/macstudio/ittem-bp18-product-completion-20261111` **한 곳**. A, 기존 Live18088, QA18095는 대상이 아님.

## 운영 원칙

- **허용된 공식 시작 경로:** `systemctl --user start/restart ittem-bp18-b.service`. Service의 `ExecStartPre`가 매번 정책 Epoch·SHA Allowlist·Queue RUNNING·Worker 잠금·포트를 검사한다.
- **허용된 공식 릴리스·Rollback 경로:** `/home/macstudio/ittem-bp18-product-completion-20261111/control/bp18_release_control.sh <trusted-40hex-target>`. 후보와 이전 릴리스 양쪽 Preflight를 **기존 프로세스 종료 전** 실행, 6개 SQLite 백업 후 systemd로 Stop→Symlink Swap→Start→Health 판정, 실패 시 Guard를 통과하는 이전 릴리스로만 복귀.
- 오랫동안 사용했던 `BP18_B3_A_B_HTTPS_DEPLOY`, `BP18_B4_DEPLOY_B_ONLY`, `BP18_B4_SWAP_HTTPS_GCP` 등 **nohup 임의 재시작 스크립트는 기록용으로만 보존**, 더 이상 공식 실행 경로가 아니다.
- B4 이전 바이너리 `564e3731`, `2ab998de`는 이미 활성화된 정책 Epoch DB에 연결해서는 안 된다. 파일 백업 복제본에서만 별도 격리 테스트.
- `config/epoch_capable_shas.txt`는 운영자가 독립 검증 후 허용한 정확한 40자리 Release SHA만 나열한다. 구버전과 임의 후보는 등록하지 않는다. 관리자가 같은 계정으로 Guard를 우회해 직접 `uvicorn`을 실행하는 것은 운영 정책 위반이며 이 검사로 OS 수준 강제까지 보장되지는 않는다.
- `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_LIVE_EXECUTION_APPROVED=NO`, `IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO`, `IT_TEM_QA_FIXTURE_ENABLED=NO`로 기존 공개 User E2E는 무과금이다. 승인된 유료 실모델은 별도 PM Actor Gate·Worker Service가 필요하다.

## 최소 확인

1. `systemctl --user cat ittem-bp18-b.service`에서 독립된 `ExecStartPre`와 loopback bind·환경변수 무과금 설정 확인.
2. `systemctl --user show ittem-bp18-b.service -p ActiveState -p MainPID -p ExecMainCode`, `readlink "$ROOT/repo"`, `cat "$ROOT/repo/SOURCE_SHA.txt"` 비교.
3. `python3 "$ROOT/control/bp18_release_prestart.py" --mode web --port 0 --target <SHA>` 로 사전 확인. 타깃이 오래된 바이너리·활성 Epoch DB 조합이면 실행 자체를 거부하고 **기존 시스템은 계속 동작**.
4. Queue의 RUNNING 또는 Worker.lock 점유 시 Stop/Swap 진행 금지. Billing UNKNOWN은 자동 재실행 금지.
5. 백업 명세 `backups/b5-control-YYYYMMDDTHHMMSSZ/MANIFEST_SHA256.json` 와 SQLite `PRAGMA integrity_check` 확인.
6. `/health` HTTP200, `/demo/api/live/capabilities` 미인증 401, Tailnet TLS 인증서, PNG·Caption SHA 원장, 다른 Track/Live 불변 확인.

## 남은 판정 경계

- `v1→v2→v1` Epoch 방어는 B4 무과금 회귀 PASS. B5는 정식 시작·복귀 경로에 Guard를 묶는다.
- **구바이너리 + 신규 DB 직접 기동은 DENIED가 정답**이며 이 상태에서 성공하는 Rollback이 제품요건은 아니다. 구바이너리 기동 복구를 원할 때는 스냅샷으로 격리된 복제 DB와 코드 함께 사용하고 E2E를 재검증.
- 공식 `dev`, Owner PR, 기존 Live/QA의 실데이터는 절대 변경 금지.
