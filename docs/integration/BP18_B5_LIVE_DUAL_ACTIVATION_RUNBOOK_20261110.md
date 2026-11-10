# BP18 B5 Live Dual 계약 등록과 복귀 리허설

`LIVE_DUAL_V1`은 전진·복귀 소스 두 개와 배포 운영 승인이 필요하다. C-B의 `10dcc278` MockTransport 판정은 로컬 기술 증거다. 이 문서에서 사용한 승인 레코드와 Release 쌍은 격리 테스트 전용이다.

## 승인 자료 준비

1. 별도 staging 루트의 `releases/<SHA>/`에 두 후보의 고정 소스를 준비한다. `SOURCE_SHA.txt`의 전체 Commit SHA, 해당 Git Tree, 빌드된 Frontend와 Backend·Worker의 Release SHA를 대조한다. 후보 둘 다 기존 SSO·F09·Epoch 계약과 `LIVE_DUAL_V1` 기록을 읽을 수 있어야 한다.
2. 아래 `inspect` 결과를 검토 자료로 제출한다. 도구는 tracked 파일 바이트와 모든 실행 비트를 Git Tree에 대조하고, 7개 Dual 프로토콜 파일의 마커와 SHA-256을 확인한다. 여기에 **전체 staged 파일의 경로·SHA-256·권한** 및 빌드 출처를 담은 인벤토리를 결속한다. 역할별 `release_sha`, `tree_sha`, `protocol_sha256`, `inventory_sha256` 네 해시가 승인 대상이다. 인벤토리와 프로토콜 해시는 정렬된 compact JSON의 SHA-256이다. 추가 소스·모듈·심볼릭 링크·하드 링크·특수 파일·예상 밖 빈 디렉터리는 거부한다. ignored 파일도 예외가 아니다.
3. 별도 운영 승인 후 승인 담당자가 보호 디렉터리에 승인 JSON을 저장한다. `version`은 `2`, `required_mode`는 `LIVE_DUAL_V1`이다. `forward`와 `rollback`의 각 네 해시는 승인된 그대로 보존하고 `approval_reference`에 실제 결정의 식별자를 넣는다. 생성 도구는 `evidence_only`가 포함된 검토 자료와 중복 키, 누락된 역할, 같은 Commit을 쓰는 쌍을 거부한다. 승인 파일은 실행 계정 소유로 두고 `0600`으로 보호한다.

```bash
python3 -I -S "$TRUSTED_TOOL_DIRECTORY/bp18_b5_dual_contract.py" \
  --git-repo "$B_SOURCE" --staging-root "$STAGING" \
  inspect --forward "$FORWARD" --rollback "$ROLLBACK"

umask 077
python3 -I -S "$TRUSTED_TOOL_DIRECTORY/bp18_b5_dual_contract.py" \
  --git-repo "$B_SOURCE" --staging-root "$STAGING" \
  prepare --approval "$APPROVAL_JSON" > "$PREPARED_CONTRACT"
python3 -I -S "$TRUSTED_TOOL_DIRECTORY/bp18_b5_dual_contract.py" \
  --git-repo "$B_SOURCE" --staging-root "$STAGING" \
  verify --approval "$APPROVAL_JSON" --contract "$PREPARED_CONTRACT"
```

`prepare`는 v2의 `version`, `required_mode`, `verified_sources`, `release_inventories`를 출력한다. 인벤토리는 릴리스 내부가 아닌 보호된 운영 계약에 저장한다. B5 시작·전진·복귀 prestart 및 Dual launcher는 전체 파일 목록과 바이트·권한을 다시 검사한다. 기존 Epoch·SSO·F09·Queue·Worker 잠금 게이트도 유지한다. 소스 전용 릴리스에는 Git 파일과 `SOURCE_SHA.txt`만 허용한다.

## Frontend 빌드 증거와 릴리스 경계

배포 폴더의 `app/dist`는 별도 빌드 레코드가 있어야 한다. 고정 소스의 격리된 **빌드 작업 폴더**에서 기존 로컬 의존성을 사용해 `npm run build`를 실행하고 전체 로그·도구 버전·환경 플래그를 보호 증거 위치에 저장한다. `VITE_IT_TEM_CODE_SHA`는 해당 Commit, SSO·Track 플래그는 승인된 B 정책을 사용한다. 빌드가 끝나면 `app/dist`만 새 release에 복사한다. `app/node_modules`, `.venv`, `.tmp`, `__pycache__`는 배포 폴더에 복사하지 않는다. Python venv·vendor는 기존 외부 운영 경로의 별도 승인·무결성 확인 대상이며 이 인벤토리가 그것을 검증했다고 주장하지 않는다.

```bash
umask 077
python3 -I -S "$TRUSTED_TOOL_DIRECTORY/bp18_b5_dual_contract.py" \
  --git-repo "$B_SOURCE" --staging-root "$STAGING" \
  record-frontend --release "$FORWARD" --build-reference "$BUILD_EVIDENCE_REFERENCE" \
  > "$FORWARD_BUILD_JSON"
```

복귀 소스도 별도로 빌드·기록한다. 두 레코드는 릴리스 밖 owner-only 파일로 보관하고 위 `inspect`·`prepare`·`verify`의 하위 명령 **앞에** 각각 `--frontend-build "$FORWARD_BUILD_JSON" --frontend-build "$ROLLBACK_BUILD_JSON"`을 추가한다. 레코드는 Commit·Tree·tracked package-lock SHA·명령·빌드 증거 식별자·모든 dist 파일 해시/권한을 결속한다. 허용된 web 자산 확장자와 비실행 일반 파일만 수용하며 포괄적 dist/의존성 제외 규칙은 없다. 파일 추가·수정·실행권한 변경은 원래 승인을 무효화한다.

`record-frontend`는 현재 파일의 **검토용 증거 생성**이며 빌드 실행·독립 재현·승인을 수행하지 않는다. JS/HTML의 적법성은 실제 빌드 로그·고정 소스·소유자 검토로 확인한다. 레코드를 다시 생성해도 기존 승인에 고정된 inventory SHA를 바꿀 수 없다. 실행 전에도 보호 prestart가 승인한 파일 집합과 정확히 일치해야 한다. 변경 없는 정상 파일은 읽고 해시만 계산하며 매 시작 시 Git/빌드를 다시 실행하지 않는다.

## v1에서 v2로 전환할 때

v1 Dual 계약은 전체 인벤토리가 없어 새 guard에서 거부한다. 구 guard는 v2의 추가 필드를 거부한다. Worker wire 프로토콜 `LIVE_DUAL_V1`은 그대로지만 **운영 계약 reader의 호환성은 별도**다. 전진·복귀 후보 모두 v2 reader/launcher를 포함해야 한다. `9788e58`/`f49b9ac`는 과거 수용 증거이며 v2 활성화 복귀 대상으로 자동 등록하지 않는다. 새 소스 쌍과 보호 `control/bp18_release_prestart.py`를 별도 승인·차등 감사한다. 기존 설치를 자동 변환하거나 기존 승인 파일을 덮어쓰지 않는다. 릴리스는 운영 잠금하에 준비·검증하고 이후 쓰기를 제한한다. 이 검사는 시작 시점의 무결성 확인이며 실행 중 파일을 쓸 수 있는 운영자의 권한 자체를 제거하지 않는다.

**검사 Python 자체의 startup 격리도 필수다.** 일반 Python은 `PYTHONPATH`의 release에서 `sitecustomize.py`를 guard 이전에 실행할 수 있다. systemd ExecStartPre·운영 전진/복귀·Worker 내부 prestart는 `-I -S`를 사용해 cwd/PYTHONPATH와 site 초기화를 제외한다. 운영 CLI도 위 격리 명령만 사용한다. `$TRUSTED_TOOL_DIRECTORY`는 릴리스 밖 운영자 소유의 보호 디렉터리이며, 검토된 고정 SHA의 `bp18_b5_dual_contract.py`와 `bp18_b5_release_prestart.py`를 원래 파일명으로 함께 설치·SHA 대조한다. CLI는 격리 모드에서 이 sibling guard만 절대경로로 로드한다. 운영 prestart 경로 `control/bp18_release_prestart.py`에도 같은 guard 바이트를 설치한다. 배포 폴더 안의 CLI를 신뢰 루트로 삼거나 평문 `python -m`으로 운영 승인을 작성하지 않는다. 실제 설치·unit 변경은 별도 운영 승인 전까지 금지다.

## 운영 승인 후 설치 순서

1. 운영자는 B5 신뢰 경로의 `control/bp18_release_prestart.py`, B5 Release 제어 스크립트, B 전용 서비스 단위와 승인된 소스를 대조한다. 전진·복귀 SHA를 기존 Epoch 허용 목록과 SSO·F09 계약에 실제 승인 범위대로 등록한다. 현재 `repo` 링크와 `SOURCE_SHA.txt`는 승인된 복귀 후보를 가리켜야 한다. B5는 서비스를 중지하기 전에 전진·복귀 대상을 모두 검증한다. 현재 소스가 Dual 이전이고 Dual 이력도 없다면 호환 소스로 이동하는 별도 승인 전환을 먼저 준비한다. 이 전환에서는 Dual이 꺼져 있으며 Dual 계약을 등록하기 전이다. Dual 이력이 있는 DB에 구소스를 연결하는 경로는 차단 상태를 유지한다.
2. 기존 F09 활성화 환경은 소스 SHA가 일치하는 정책으로 Web과 Worker를 시작한다. 정확한 소스별 `config/bp18_live_policies/<SHA>.env` 두 개를 미리 준비한다. `config`와 정책 하위 디렉터리는 운영 계정 소유의 owner-only 디렉터리, 정책은 `0600`이다. 파일 내부 `IT_TEM_BP18_LIVE_RELEASE_SHA`도 파일명의 SHA와 일치해야 한다. 먼저 Dual을 비활성 상태로 준비한다. 별도 승인으로 기능을 켤 때에도 Worker-only Provider credential과 실제 과금 권한은 독립 게이트다.
3. 승인 및 보호 대상 확인 후 기존 `config/.b5_operator_control.lock`을 획득한다. 동일한 보호 `config` 디렉터리에서 임시 `0600` 파일에 준비 계약을 복사한다. 실제 B 루트를 `--staging-root`로 지정하고 임시 파일을 `verify`한다. 이전 계약이 있다면 SHA와 사본을 보호 증거 위치에 남긴다. 검증된 임시 파일을 동일 파일시스템의 `config/bp18_required_dual_contract.json`으로 원자 이동한다. 설치 파일을 다시 `verify`하고 B5 prestart의 `--target "$FORWARD"`와 `--target "$ROLLBACK"`를 `--mode web --port 0`으로 각각 검증한다. 이 과정을 마친 뒤 운영 잠금을 해제한다.
4. Worker 종료와 미해결 RUNNING 행 부재를 확인하고 공식 `control/bp18_release_control.sh "$FORWARD"`에 위임한다. 기존 B5는 SQLite 6개를 백업해 `PRAGMA integrity_check`와 SHA를 기록한 뒤 소스 링크를 교체한다. 전진 시작 실패 시 호환 복귀 소스와 그 SHA의 정책만 선택한다. 기존 런타임 Job·Queue·CostLedger·Artifact는 현재 데이터로 읽는다. `BILLING_UNKNOWN`은 별도 대사에서 처리한다.

승인된 Dual Intent는 생성 시점의 Release와 실행 정책에 결속된다. 전환 전에 기존 소스에서 실행할 수 있는 대기 작업이 정리됐는지 확인한다. 격리한 사고 행은 원장에 남긴다. 남은 실행 의도를 새 Release 정책으로 자동 재승인하거나 DB 스냅샷을 덮어써 옮기지 않는다. [과금 미확정 대사](BP18_LIVE_DUAL_BILLING_RECONCILIATION_20261110.md)

## 격리 재현

```bash
python3 -m pytest -q \
  tests/demo_live/test_bp18_b5_dual_contract.py \
  tests/demo_live/test_live_dual_protocol_guard.py \
  tests/demo_live/test_bp18_b5_release_prestart.py
```

테스트는 임시 Git 소스와 Release 루트에서 양쪽 계약을 생성·검증한다. 기존 B5 셸 스크립트, prestart, SQLite 백업을 임시 루트로 지정하고 systemd·상태·Health 경계는 테스트 대역으로 실행한다. 전진 성공과 전진 시작 실패 후 복귀에서 런타임 Job·Queue·CostLedger·Artifact를 포함한 보호 파일 SHA가 동일하고 백업 SQLite 6개의 무결성이 유지됨을 확인한다. 소스별 launcher 정책 및 실제 Signed Actor/Worker 권한은 별도 검증 항목이다.
