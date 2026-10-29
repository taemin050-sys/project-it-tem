# S3-B React/Vite 브라우저 API 연동 시험 하네스 (Mock 전용)

이 하네스는 **프론트엔드 담당자의 정식 서비스 애플리케이션이 아닙니다.**
현재 구현된 P2/P3 HTTP 흐름을 독립적으로 확인하기 위한 시험용 React 화면입니다.

제품 사진 업로드 → Job 생성 → 기획·카피 생성 → 사용자 승인 → Mock 이미지 생성 → 사용자 승인 → 합성 → PNG 및 UTF-8 캡션 다운로드 순서로 검증합니다.

## 실행 방법

실행 전 Chrome, npm, Python 가상환경과 공식 잠금 의존성(FastAPI, Pillow, uvicorn 등)을 설치해 주셔야 합니다. 모든 서비스는 외부에 공개되지 않는 `localhost`에만 바인딩됩니다.

    npm ci --no-audit --no-fund
    npm run build
    IT_TEM_PYTHON=/absolute/path/to/your/.venv/bin/python \
    IT_TEM_KOREAN_FONT=/absolute/path/to/verified/KoreanFont.ttf \
      ./scripts/run-local-e2e.sh

Vite는 `127.0.0.1:4173`에서 실행되며, `/api` 요청을 로컬 FastAPI 서버 `127.0.0.1:18766`으로 프록시합니다. 하네스는 별도로 브라우저를 다운로드하지 않고 설치된 시스템 Chrome과 `puppeteer-core`를 사용합니다.

시험 입력 이미지는 동일한 가상 화장품을 서로 다른 위치에서 촬영한 것처럼 만든 합성 사진입니다.

실행 증거는 매번 새로 생성되는 Git 추적 제외 디렉터리 `../../.runtime/b0-XXXXXXXX/`에 저장됩니다.

- `browser_network_trace.json`: 실제 브라우저 요청, HTTP 상태 코드, Job ID를 기록합니다.
- `artifact_checks.json`: Chrome에서 조회한 PNG 1080×1350 및 UTF-8 캡션의 검사 결과를 기록합니다.
- `b0_browser_harness_completed.png`: 브라우저 화면 캡처입니다.
- Chrome에서 저장한 파일 검사 결과, `backend.log` 및 `vite.log`도 생성됩니다. 시험 입력 데이터와 JobStore는 기본적으로 시험 종료 시 정리됩니다.

시험에서는 업로드 HTTP 201, 카피·이미지 승인, 잘못된 단계 실행 및 거절 이후 진행에 대한 HTTP 409 차단, 새로고침 후 복구, 결과물과 예기치 않은 JavaScript 오류가 없는지를 확인합니다.

**검증 범위의 한계:** 이 하네스의 성공은 프론트엔드 담당자의 정식 React 앱이 완성됐다는 의미가 아닙니다. 실제 VLM·Text AI·Compliance·이미지 생성 모델, 유료 API 및 GCP와 연결되지 않습니다. 정식 프론트엔드, B1/B2, 인증 및 운영 배포는 각각 별도의 인수 게이트로 검증해야 합니다. 현재 `dev`에 구현된 HTTP API 11개를 사용하는 방법은 PR #6의 `docs/API_LIST.md`를 참고해 주시기 바랍니다.

## 최초 검증 증거 (2026-10-27)

React 19와 Vite 7의 로컬 프록시, 화면 너비 1280px의 실제 헤드리스 시스템 Chrome을 사용했습니다. 백엔드는 `dev@b5e227e` 기준 FastAPI였으며, 모델 호출은 수행하지 않았습니다.

제품 이미지 업로드 HTTP 201, 워크플로 상태 전이, 의도적인 순서 위반 HTTP 409, 카피 거절 후 HTTP 409 차단, 새로고침 이후 Job GET, PNG 1080×1350, UTF-8 캡션 및 브라우저 JavaScript 오류 검사를 통과했습니다. 격리된 백엔드 프로세스를 재시작한 뒤 기존 Job과 최종 PNG도 복원했습니다.

검토 가능한 증거는 `evidence/` 디렉터리에 포함돼 있습니다.

- `b0_browser_harness_completed.png`: 가상 제품과 Mock 상태를 보여주는 화면 캡처입니다.
- `browser_network_trace.json`: `localhost` 경로와 임시 시험 Job ID만 포함한 브라우저 네트워크 기록입니다.
- `artifact_checks.json`: 응답 Content-Type, 이미지 크기, 캡션 및 바이트 수 검사 결과입니다.

이 증거만으로는 정식 프론트엔드 구현, Text AI v0.7 스키마 호환성, 실제 Compliance 서버 승인 게이트 또는 Live 모델 동작을 입증할 수 없습니다.

## S3-B.2 감사 지적 사항 보완 (2026-10-27)

| 독립 검증 게이트 | 실제 검사 방법 | 결과 |
|---|---|---|
| **React UI의 오래된 상태 복구** | 별도 요청이 서버 상태를 먼저 변경한 뒤 오래된 UI에서 버튼을 누릅니다. HTTP 409를 확인하고, GET Job 한 번으로 최신 상태를 반영하며, POST를 자동 재시도하지 않는지 확인합니다. | PASS |
| **Chrome 실제 다운로드** | React 다운로드 버튼을 클릭하여 Chromium이 파일을 저장하도록 합니다. 실제 파일에서 PNG 시그니처·가로세로 크기 및 UTF-8 한국어 내용을 검사합니다. | PASS |
| **다운로드 실패 시 화면 처리** | 캡션 요청에 HTTP 404를 주입하고, React 화면에 오류가 표시되는지 확인합니다. 성공으로 잘못 표시되면 실패 처리합니다. | PASS |
| **새로고침 전후 요청 비교** | Job GET이 발생하는지 확인합니다. 새로고침 후 상태 변경 POST가 0건이고 Job ID·상태·최종 결과물 버튼이 유지되는지 검사합니다. | PASS |
| **서버 재시작 이후 브라우저 복원** | 동일한 임시 JobStore를 사용해 백엔드를 재시작합니다. curl과 새 Chrome 페이지에서 `COMPLETED` 및 PNG 1080×1350 복원을 확인하고, 브라우저 POST가 0건인지 검사합니다. | PASS |
| **백엔드 HTTP 회귀검증** | 실제 OpenAPI 11개 operation과 HTTP 201/200/404/409/413/422, 제품 사진 2~5장·참고 사진 0~5장, 중복·용량·MIME·거절 처리 및 파일 응답 헤더를 pytest로 검증합니다. | PASS |
| **기존 계약 보존** | P2/P3 및 정책 테스트가 계속 통과하는지 확인합니다. HTTP 구현, JobStore, Text 담당자 스키마와 미동결 신규 Wire 7개는 변경하지 않습니다. | PASS |

### 독립 환경에서 재현하는 방법

검토할 브랜치와 커밋을 새로 체크아웃하신 다음, 저장소의 Python 의존성 잠금 파일 `configs/requirements-serving-gcp.lock.txt`를 사용해 격리된 가상환경을 준비해 주시기 바랍니다. 아래 명령은 **저장소 최상위 디렉터리**에서 시작합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r configs/requirements-serving-gcp.lock.txt
IT_TEM_KOREAN_FONT=/path/to/an/installed/KoreanFont.ttf .venv/bin/python -m pytest -q
.venv/bin/python docs/contracts/validate_package.py
.venv/bin/python tests/browser-harness/scripts/audit_b0_openapi.py --output .runtime/b0_openapi_audit.json

cd tests/browser-harness
npm ci --no-audit --no-fund
npm run build
IT_TEM_PYTHON=/absolute/path/to/repository/.venv/bin/python IT_TEM_KOREAN_FONT=/path/to/an/installed/KoreanFont.ttf CHROME_BIN=/path/to/installed/Chrome-or-Chromium ./scripts/run-local-e2e.sh
```

Mac Studio에서 검증할 당시 Python 3.13.12, Node 24.21.0, npm 11.19.0 및 설치된 Noto Sans Gothic 시스템 폰트를 사용했습니다. **외부 모델이나 GCP API는 호출하지 않았습니다.**

실행 스크립트는 먼저 FastAPI 포트 **18766**과 Vite 포트 **4173**이 다른 프로세스에서 사용 중인지 검사하고, 충돌이 있으면 실행을 거부합니다. Python 실행 파일, 한글 폰트 및 Chrome 실행 파일의 존재도 확인합니다. 두 테스트 서버는 `localhost`에서만 실행하고 종료 시 해당 스크립트가 시작한 프로세스를 정리합니다.

시험마다 별도의 `.runtime/b0-XXXXXXXX` 디렉터리를 생성합니다. 기본 설정에서는 시험 종료 시 합성 입력 이미지, 시험용 백엔드 코드 및 JobStore를 삭제하고, 감사에 필요한 네트워크 기록·검사 결과·화면 캡처는 보존합니다. 시험 입력과 JobStore까지 유지해야 하는 경우에는 `B0_KEEP_TEST_DATA=1`을 설정해 주시기 바랍니다. **이 하네스를 실제 공개 서버에 연결하지 마십시오.**

`tests/browser-harness/evidence/`에 게시한 증거는 합성 시험 데이터만 사용합니다. 브라우저 화면, 민감정보를 제외한 요청 경로·메서드·상태 코드 기록, 실제 Chrome 저장 파일 검사, 재시작 후 브라우저 기록·화면 캡처 및 OpenAPI 호환성 진단을 포함합니다. 실제 사용자 사진, API 키, 쿠키 또는 모델 공급자 응답 원문은 포함하지 않습니다.

**OpenAPI 진단 결과의 의미:** 실제 바이너리·UTF-8 `FileResponse` 동작과 현재 생성된 `application/json { }` 스키마 사이에 차이가 있습니다. HTTP 404/409/413/503 응답 설명도 일부 누락돼 있으며, TypeScript의 Job 타입은 수동으로 관리되고 있습니다. 이는 **FOLLOW_UP(후속 개선)** 대상으로 기록한 사항이며, 이 PR에서 `response_model`이나 오류·메서드·경로를 변경해도 된다는 승인은 아닙니다.

**이번 범위에서 검증하지 않은 게이트(NOT VERIFIED):** 프론트엔드 담당자의 정식 B0 앱, 공유 서버의 인증·HTTPS·보안, Text AI v0.7 원본 소스 호환성, B1 Compliance 검수 기록 영속화, CostGuard와 Live 호출의 실제 연결, B2 실제 모델 동작은 별도로 검증해야 합니다. PR #6의 `docs/API_LIST.md`도 이번 작업과 별도로 유지합니다.
