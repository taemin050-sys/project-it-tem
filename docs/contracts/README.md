# IT-TEM 팀 공통 연동 패키지 · 2026-10-26 / Contract v0.2

> **진입점:** 전체 팀은 이 문서를 먼저 읽고, 담당자별 파일은 **각자 하나만 추가** 읽으면 된다.
> **리뷰 상태:** 계약 PR #4 (머지 전 회의 반영안) · **코드 기준:** `dev=d5d07aa` / 기능 브랜치 `f979331`
> **원칙:** 의미·정책의 공식 SSOT는 `../interface_spec.md`. 이 폴더는 이해·실행·검증용 가이드로, 동일 계약을 다시 정의하지 않는다.
> **실제 B0 HTTP 호출 안내(2026-10-27, PR #5 병합 기준):** [`docs/API_LIST.md`](../API_LIST.md) — `dev@b5e227e` 실제 OpenAPI 기반. 아래 이전 PR/브랜치 상태 설명은 역사적 기록이며 **현행 호출 가능 범위는 API_LIST를 확인**한다.

## 1. 필독 범위 — 전원에게 4문서 강제하지 않음

| 대상 | **최소 필독** | 필요할 때만 참조 |
|---|---|---|
| **전 팀원** | **이 README**, [interface_spec.md 1장(흐름·책임)](../interface_spec.md), 자기 [파트별 가이드](#2-담당자에게-배포할-자료) | [C-01~12 결정표](DECISION_REGISTER.md) |
| **React** | 위 + [계약 2장(HTTP 상태·예제)](../interface_spec.md) | 목표 신규 Wire는 현재 BLOCKED |
| **텍스트·서빙** | 위 + [SCHEMA_MAPPING](SCHEMA_MAPPING.md) + [계약 2.4~2.7장](../interface_spec.md) | Source·검수 sidecar |
| **이미지·합성** | 위 + [계약 6장](../interface_spec.md) | [Wire 후보 JSON](examples/wire_proposals.json) |
| **PM·서빙 통합** | 위 + [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md) 및 [감사 추적표](DOCUMENT_AUDIT.md) | Branch/QA/예산 증거 |

**신규 기술 Freeze 상태:** 10/27 현재 새 HTTP **FROZEN_WIRE 0건**, 제안 7건 **BLOCKED_WIRE**. 10/26 회의 정책(APPROVED_POLICY)은 동결된 엔드포인트나 구현을 뜻하지 않는다. 실제 사용 가능한 예제는 원격 `dev`가 아닌 `f979331`의 **레거시 13 API**라는 제한을 확인한다.

```mermaid
flowchart LR
    A["README + interface_spec 1장"] --> B["내 역할 가이드"]
    B --> C{"목표 Wire 동결?"}
    C -->|"아니요"| D["Owner v0.5/Fake Wrapper"]
    C -->|"예 + 실제 OpenAPI"| E["FastAPI + React 타입"]
    D --> F["Contract / 승인 / QA 검증"]
    E --> F
```

## 2. 담당자에게 배포할 자료

**전 팀원:** README + 통합 계약의 관련 절 + 자기 담당 가이드. [팀 공지문](TEAM_DISTRIBUTION.md)은 배포 담당자가 사용한다.
**개별:** 공통 문서를 중복 복제한 첨부파일이 아니라 **같은 Git 커밋의 링크**와 아래 자기 파트 파일 1개를 전달한다.

| 담당 | 추가 1개 문서 | 바로 수행할 핵심 작업 | 검증 증거 |
|---|---|---|---|
| **권혁상 / React** | [FRONTEND.md](partners/FRONTEND.md) | 사용자 입력·조사 요약·규제 경고·승인·다운로드 | TS build + Browser E2E |
| **김다혜 / 텍스트 AI** | [TEXT_AI.md](partners/TEXT_AI.md) | v0.5 원본·VLM·Research·Copy·Compliance·Prompt Wrapper | Schema / Fake / citation / risk Fixture |
| **박지수 / 이미지·합성** | [IMAGE_COMPOSER.md](partners/IMAGE_COMPOSER.md) | OpenAI Wrapper·원형 보존·Composition | PNG·메타데이터·한글·외형 QA |
| **이형기 / 서빙** | [SERVING.md](partners/SERVING.md) | Job·자산·상태·비용·스키마 매핑·통합 | Contract / Regression / Cost / Mock |
| **이태민 / PM·QA** | [PM_QA.md](partners/PM_QA.md) | 계약 변경·예산·branch merge·수용 판정 | 승인·검증 증빙 레지스터 |

## 3. 현재 구현 현실 / 패키지 증거 수준

| 유형 | 현재 위치 | 해석 |
|---|---|---|
| P1 health | `dev` (`d5d07aa`) | 현재 `dev`에 실제 존재 |
| HTTP 13개·9개 상태·118개 회귀 | `feat/p4-contract-handoff` (`f979331`) | feature 구현, `dev` 미병합 |
| 텍스트 `schemas.py v0.5` | 회의에서 공유된 정의 | **실제 팀원 저장소 원본 path/commit 검증 후 정식 동결** |
| [샘플 Fixture](fixtures/README.md) 8개 | 본 PR | 합성 예제, **회의 스키마 스냅샷 Pydantic 검증과 실제 Owner 원본 검증은 별개** |
| [TS 업로드 샘플](examples/frontend_legacy_upload.ts) | 본 PR | 구 feature HTTP 예제, 현 `dev` API가 아님 |
| 모델·React Live 통합 | 미검증 | 테스트 결과 PASS로 표시 금지 |

## 4. 문서 vs 기계 판독 계약 사용 규칙

```text
텍스트팀 실제 schemas.py v0.5 --(Pydantic JSON Schema/fixtures)--> 텍스트 내부 계약
          ↓ 서빙의 무손실 Mapper 테스트
구현된 FastAPI + /openapi.json ------(타입 생성)------> React TS API 타입
          ↓                                                                    ↓
        pytest Contract/Mock -----------------------> React Browser E2E
```

기존 feature의 `scripts/export_p4_contracts.py`는 **legacy 내부 DTO 7종**에 대한 산출물이다. 새로운 v0.5/HTTP 타입이 자동으로 반영된 것이 아니다. **정식 파일명·엔드포인트가 확정되지 않은 항목을 현재 가동 중 API처럼 문서화하지 않는다.**

이번 문서별 재검토 결과와 검증 한계는 **[DOCUMENT_AUDIT.md](DOCUMENT_AUDIT.md)**에서 확인한다.

## 5. 검증·배포 절차

1. `python3 docs/contracts/validate_package.py`로 **배포 문서·합성 Fixture 정적 검사** (외부 호출 0).
2. 계약 PR 리뷰·병합 후 **고정 Git commit SHA**를 전원에게 배포한다. `TEAM_DISTRIBUTION.md` 사용.
3. 각 파트는 자기 가이드의 입력/출력 Fixture와 오류 케이스를 제출한다.
4. 서빙은 실제 코드 OpenAPI·JSON Schema·TS·Contract Test를 맞춘다. Contract/Mock/Live/Browser/QA는 분리 판정한다.
5. 이후 변경은 **계약 버전 + C-ID + 영향 담당 + 마이그레이션 + PR 링크**를 기록한다.

**보안:** 브라우저로 VM 8000 직접 접근 금지, API 키·민감 사진 Git/프론트 공유 금지, 팀 유료 API 베이스라인 실험 포함 $10 상한 및 서버 승인 게이트 기본 OFF.
