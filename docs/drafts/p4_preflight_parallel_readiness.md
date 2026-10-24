# IT-TEM P4-Preflight 1차 — 병렬 개발 준비 기술 노트

> **DRAFT / NOT APPROVED**, 2026-10-24. `docs/interface_spec.md` 공식 SSOT를 대체하지 않는다.
> 범위: P4A React↔FastAPI 잠정 계약 + 기획/카피/이미지 내부 어댑터 연결 준비 및 기계 검증.

## 1. 이번 작업의 정확한 완료 범위

- P3 33건, P4A 13건, P4-Preflight 신규 19건의 **총 65건**을 독립 재현 컨테이너에서 검증.
- `src/serving/provisional_contracts.py`: ProductFacts / Evidence / PlanResult / CopyResult / VisualBrief / ImageResult / GenerationReceipt / SafeZone을 Pydantic으로 명시. **기존 HTTP API의 반환 형식은 전혀 변경하지 않음**.
- `src/serving/provisional_ports.py`: Research / Planning / Copy / Image의 Python Protocol만 정의. 기획·카피·이미지 팀은 각자 포트 구현체를 작성할 수 있음.
- `tests/contracts/fixtures/*.json`: 동일한 표준 입력·출력 예제 7건. **모두 합성 테스트 예시이며 실제 제품 사실/외부 출처를 의미하지 않음**.
- `tests/test_p4_preflight_contracts.py`, `tests/test_p4_parallel_ports.py`: 유효성·거절·기존 라우팅·Mock/Live 구분을 자동 검증.
- `scripts/export_p4_contracts.py`: FastAPI OpenAPI + 각 Pydantic JSON Schema 7개를 `.runtime/contracts/`에 생성, 해시 매니페스트와 **PROVISIONAL_NOT_APPROVED** 표시.
- React TS 임시 클라이언트의 상태 Enum/업로드 필드 정합성 검사. TS 빌드·브라우저 E2E는 아직 하지 않음.

## 2. 병렬 팀 개발 분업과 충돌 방지

| 연결 | 모델 담당자 구현 | 서빙 책임 | 테스트/실패 기준 |
|---|---|---|---|
| Research→Planning | Evidence 수집기, 제품 사실과 외부 조사 구분 | 호출/타임아웃/증빙 저장 | 검색하지 않았다면 `research_performed=false`; 근거 없는 true 불가 |
| Planning→Copy | PlanResult 소비해 카피 1개+위험 플래그 | 동일 job ID·상태 관리, 승인 전 차단 | `PLAN_READY` 이후에만 Copy 가능 |
| Copy→Image | 승인된 카피+VisualBrief, 제품 보존 | source asset ID 제공, 과금/재시도 관리 | copy revision>0, ID 중복/무효 차단 |
| Image→Composer | ImageResult 및 시각품질 평가 | 최종 규격 1080×1350 Pillow 합성 | 내부 생성 1024×1536도 허용; 최종 PNG만 1080×1350 |
| React→FastAPI | 입력/승인 UI·다운로드 | `/api/v1` OpenAPI·상태 SSOT·동기화 | 409이면 GET 재동기화; 업로드 필드 이름 유지 |

**중요:** `ProvisionalPorts`는 독립 개발용 추상 인터페이스이지 실제 런타임에 연결된 모델이 아니다. `text_adapter.py` P4A는 별도 실제 OpenAI 호출 준비 코드이지만 기본 비활성화·실계정 미검증 상태다. 이미지 모델 래퍼는 연결하지 않았다. 브라우저 검색·논문 검색·광고 심사도 수행하지 않는다.

## 3. 이번 단계에서 바꾸지 않은 것

- 공개 `/api/v1/jobs`, `/mock/*`, `/approvals/*`, `/artifacts/*`와 기존 9개 상태값.
- `Mock` 게이트: 카피 승인 전 이미지 생성 409 / 이미지 승인 전 합성 409.
- Python `JobStore` 및 기존 아티팩트 저장·다운로드 경로.
- `docs/interface_spec.md`: **팀 결재 전에는 직접 수정하지 않음**.
- GCP 방화벽·배포 설정, API Key, OpenAI 비용 설정, 타 팀 코드, `dev`/`main`.

## 4. 월요일(10/26) 팀 결정 — 제안 기본안

1. **PM:** `/api/v1` 고정, API version v0.1, `docs/interface_spec.md` 유일 규범 SSOT, `PROVISIONAL`→`APPROVED` 전환.
2. **React:** multipart 제품2~5/참고0~5; Job 9개 상태; 예외 409/422/413/502/503; 단계별 다운로드; Vite API 프록시 배포 방식.
3. **Research/기획:** 기획 소유자와 OpenAI 웹 검색 실행 책임, Evidence 필드(source URL·수집일·claims 연결), 실패 때 검색 미완료 표시.
4. **카피:** CopyResult·`compliance_checked=false` 기본값·승인 카피 revision, 영어 VisualBrief 생성 책임.
5. **이미지:** 팀 OpenAI 이미지 래퍼의 실제 입력 이미지 수/형태·비용, 제품 외관 보존 기준 및 후보 한 장 제한, Mock과 실제 이미지 구분.
6. **서빙:** 상태 저장/경합·요청 멱등성/중복 과금, 과금 불확실 상태, 단일 워커→다중 워커 전환 방안.
7. **PM/전체:** 안전 영역·4:5 최종 산출물, 거절 후 재생성 정책, 품질 수용 기준, 제한적 실호출 예산.

**서명/동의 전까지 모델별 필수 필드 및 프로토콜 이름은 내부 초안**으로만 사용한다. 기존 P4A TS 임시 타입은 생성형이 아닌 수작업 예시이므로, 승인 후 OpenAPI 생성형 타입으로 교체한다.

## 5. 로컬에서 팀원별 빠른 확인

```bash
python -m pytest -q tests/test_p4_preflight_contracts.py tests/test_p4_parallel_ports.py
python -m scripts.export_p4_contracts --output .runtime/contracts
```

각 팀은 `tests/contracts/fixtures` 입력을 가져가 구현체의 반환값을 대응 DTO로 검증한다. **OpenAPI/JSON Schema는 빌드 산출물**이고, 승인 후 한 번 더 생성한다. `.runtime`은 Git 제외이므로 유출 위험 감소.

## 6. 범위 한계 및 후속 작업

- `63+2=65` 개 테스트는 격리된 Python 3.13 환경에서 재현한 결과. 사용자 GCP VM Python 3.10과 설치된 라이브러리 환경에서 다시 확인해야 한다.
- 이번에는 `P4A` API의 opt-in SDK 요청 형식을 Fake Client로 검사했으나 실제 OpenAI 응답, 웹 검색, 이미지 생성은 검사하지 않았다.
- Test Fixture 내 `example.org` 출처는 **가상 예시**이며 외부 조사 근거로 사용하면 안 된다.
- GCP에서 65개 PASS를 확인하면 이번 브랜치를 커밋·백업하고 월요일 합의 반영은 후속 브랜치/PR로 분리한다.
