# B1-R — 격리 Fake Compliance 서버 승인 게이트 설계·검증 (잠정)

> **범위:** PR 독립 검토용 · 기준 `dev@b5e227e` · **Owner 공식 계약 아님 / 실제 Compliance 아님 / 배포 금지**
> **시행 조건:** 서버 생성 시 명시적으로 `create_app(storage_root=..., enable_b1_fake_compliance=True)` 사용. 기본 `app=create_app()`는 기존 B0 방식 그대로입니다.

## 1. 목적 및 B0 보호

B1-R은 실제 모델 코드가 도착하기 전에 **서버 소유 검수 기록과 기존 HTTP 승인 게이트의 결속**을 검증하는 Fake 프로토타입입니다. 기존 서버의 `POST /api/v1/jobs/{job_id}/approvals/copy`에서 `approved=true`일 때만 검수 기록을 요구하며, `approved=false` 거절은 기존 워크플로와 동일합니다.

새로운 HTTP 경로는 추가하지 않았습니다. 기존 11개 OpenAPI operation, multipart 업로드, Job 상태, 응답 형태와 기본 B0 테스트가 보존됩니다. `B1-R` 모드는 실제 앱 배포 기본값이 아니므로 React Owner의 B0 연동을 차단하지 않습니다.

| 계층 | 구현 대상 | 책임 |
|---|---|---|
| HTTP | 기존 `/approvals/copy`의 B1 Fake 모드 분기 | 외부에서 검수 결과·해시·기록 ID 생성 금지 |
| 서버 내부 | `FakeComplianceGate` | 카피·Context 스냅샷, 검수 시작/완료, 필수 불변조건 |
| 저장 | `b1_fake_review.json` (Job별 개인 파일, 권한 0600) | 검수 기록·입력 해시·세대·실행 provenance를 파일에 보존 |
| 상태 전이 | 기존 `transition_job()`와 공유하는 `JobStore._lock` | 검수 재검증 후 승인 상태를 동일 잠금 아래 영속 저장 |
| 변경 감지 | B1 활성 시에만 `transition_job()` 옵서버 | 카피/실제 검수 입력 변경마다 서버 세대 무효화 |

### 1.1 실제 데이터·임시 어댑터 경계

- B0의 `copy_candidate.text`는 Text Owner의 공식 `AdCopyOutput`이 아닙니다. 테스트에서는 이를 합성 `headline/caption`으로 옮긴 **Fake 전용 브리지**만 사용합니다.
- `canonical_copy_hash`, `canonical_review_input_hash`, `validate_compliance`는 현재 `docs/contracts/validation.py`의 **P0-04/P0-04R 참조 알고리즘**을 사용합니다. 실제 Text Owner v0.7 소스/스키마와 상호운용 검증한 결과가 아닙니다.
- Fake 검수 입력은 카피 객체, 제품명, 명시적 `user_text`, `product_facts`, 실제 업로드 Asset 순서·ID·SHA, Fake가 소비한다고 선언한 추가 맥락 및 검수 버전을 포함합니다. 공식 Owner의 실제 검수 입력 범위가 확정되면 새로운 계약 검증이 필요합니다.
- Fake 보고서의 `passed=true`는 **조건부 테스트 허용 신호**일 뿐, 화장품 광고 적법성이나 실제 공급자 검증의 근거가 아닙니다.

## 2. 필수 불변조건

| 항목 | 차단 방식 |
|---|---|
| 검수 누락·서버 레코드 부재 | 승인 HTTP 409 · `MISSING_TRUSTED_REVIEW_RECORD` 등 |
| `passed=false`·위반 의심 | HTTP 409 · `COMPLIANCE_BLOCKED` |
| 외부 입력으로 검수 보고서/해시 제출 | 기존 승인 DTO의 extra-forbid를 통해 HTTP 422 |
| 검수 토큰 재사용·별개 Job 기록 | 검수 실행 provenance 검증 후 차단 |
| Copy·제품명·사용된 사실·Asset·추가 입력 변경 | 스냅샷 JSON / SHA 비교·실제 Job 변경 옵서버로 차단 |
| Copy v1→v2→v1, Context A→B→A | **서버 세대 증가**로 이전 기록 무효화; 결과값/해시 원복만으로 승인 불가 |
| 동일 스냅샷 반복 Stage | 멱등성 유지, 세대 증가하지 않음 |
| 검수 진행 도중 입력 변경 | 과거 검수 완료 금지 |
| 중복 HTTP 승인/승인·변경 경쟁 상태 | 같은 `JobStore._lock` 아래 검사·상태 전이. 한 번만 승인 성공 |
| 검수 Sidecar 또는 보고서 내용 조작 | 불변조건·해시·실행 인덱스 검사 실패 시 차단 |
| Job 파일 교체 실패 | 기존 JobStore rollback이 승인 노출을 차단 |
| 재시작 | 별도 Fake 검수 기록 파일을 다시 읽고, 기존 Job을 기준으로 승인 판정 |

**영속성·원자성 범위:** 파일 Sidecar는 임시 파일에 `fsync` 후 `os.replace`, 승인 Job은 기존 `transition_job`의 동일 Job JSON 교체로 기록합니다. Sidecar와 Job은 **단일 DB 트랜잭션이 아니며**, 변경 옵서버가 검수 기록을 선제 무효화한 후 Job 기록 실패가 발생하면 보수적으로 **재검수 필요** 상태가 될 수 있습니다. 이는 승인 누락보다 안전하지만 운영급 완전 원자성 보장은 아닙니다.

## 3. 검증 방식과 실행 명령

```bash
# 공식 저장소 루트에서 잠금 의존성을 설치한 가상환경 사용
IT_TEM_KOREAN_FONT=/path/to/KoreanFont.ttf \
  .venv/bin/python -m pytest -q tests/test_b1_fake_review_gate.py

# 기본 B0 및 계약 참조 테스트를 포함한 전체 회귀
IT_TEM_KOREAN_FONT=/path/to/KoreanFont.ttf .venv/bin/python -m pytest -q
.venv/bin/python docs/contracts/validate_package.py
```

테스트는 FastAPI `TestClient`로 **실제 POST 승인 라우트**를 실행합니다. 추가로 별도 Python 프로세스에서 검수 기록을 작성하고 기존 서버가 승인하는지, 앱 인스턴스 재생성 후 영속 기록을 다시 사용할 수 있는지 검사합니다.

정상 승인 외에 검수 누락/실패, 필드 모순, 부적합 보고서, 재생 토큰, 위조 저장 기록, 검수 범위 변경, 변경→원복, 세대 증가, concurrent approval, 기록 저장 실패와 실제 Job 상태 복원을 검증합니다.

## 4. 비지원 범위와 병합 조건

**이번 PR에서 구현하거나 완료했다고 주장하지 않는 사항**

- 실제 Text Owner `schemas.py v0.7` / `product_analyzer.py` / `llm_client.py` 및 실제 Compliance Wrapper
- 인증된 `actor_id`·Job 소유권·권한, HTTPS, 멀티프로세스 공유 파일 잠금, 운영 DB 다중 행 트랜잭션
- API를 통한 새 검수 시작/완료 HTTP Wire 또는 `ReviewRecord` 노출
- 실제 VLM/텍스트/이미지 모델 호출, 광고 적법성 보증, CostGuard 유료 호출 검증
- 본 테스트를 정식 React B0-O Browser E2E PASS로 승격하는 행위

**통합 전 별도 게이트:** Owner 공식 소스·SHA 확정, 규칙 입력 범위, 진짜 ReviewRecord/실 DB 트랜잭션, 인증된 사용자 승인, 실패 HTTP 응답 정책, 실제 모델 비용·멱등성 게이트, 독립 감사·PM 승인.

신규 모델 HTTP Wire **7 BLOCKED_WIRE / FROZEN_WIRE 0** 상태를 유지하며, 이 Fake 기능을 기본 B0 서빙으로 전환하거나 `dev/main`에 직접 병합하지 않습니다.

**자체 판정 범위:** `B1-R FAKE OPT-IN SERVER GATE ONLY`, `B0 DEFAULT UNCHANGED`, `PRODUCTION / B1-L / B2 LIVE NOT VERIFIED`.
