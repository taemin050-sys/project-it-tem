# PR #4 독립 감사 17건 조치 추적·재감사 증거 (2026-10-27)

> 본 파일은 **P0-01~07 / P1-01~10**을 한곳에서 추적한다. 코드의 새로운 런타임 게이트를 이 PR에서 구현했다는 뜻이 아니다. **현재 PR은 리뷰·병합 전**이며 10/26 합의 정책과 신규 공개 Wire의 확정은 별개다.

## 1. 기준·검증 출처

| 근거 | 실제 상태 |
|---|---|
| 독립 의견서 | Mac Studio `it-tem_handoff/07_PR4_CONTRACT_AUDIT_20261027.md` 전체 115줄 |
| 10/26 회의 | 사용자 제공 결정·보류·고도화 + 김다혜 `schemas.py v0.5` 회의 텍스트 |
| `dev` / feature | `dev=d5d07aa`(P1 health), `f979331`(13 legacy API/9 JobStatus/118 feature 회귀) |
| 실제 텍스트팀 원본 | GitHub `dev` 및 본 PR에는 없음: Owner official repo/path/commit/SHA **BLOCKED_BY_SOURCE** |
| 실제 이미지 Wrapper | GitHub 대상 브랜치에 이미지팀 구현 소스/호출 시그니처 없음: **BLOCKED_BY_SOURCE** |
| 회의 스키마 스냅샷 | 별도로 검사 가능한 원문 코드이며 **Owner 공식 SHA의 대체 증빙이 아님** |

## 2. P0 감사 조치

| ID | 결함 | 수정 파일·검증 | 상태·다음 차단 조건 |
|---|---|---|---|
| **P0-01** | 신규 VLM·Research·Copy/Compliance·승인·Image·Composition HTTP Wire 미동결 | `interface_spec.md §2.4~2.7`, `examples/wire_proposals.json` / `tests/test_contract_wire_proposals.py` | **BLOCKED_BY_SOURCE/DECISION**. 7개 proposal의 method/path/body/error/status/owner 정의·JSON 검증; **FROZEN 0건**. Owner signature와 PM 승인 필요 |
| **P0-02** | 텍스트 Owner 원본 없고 합성 Fixture를 실제 계약이라고 오인 | `SCHEMA_MAPPING.md §7`, `check_owner_schema.py` SHA 확인 / 8개 Fixture 검사 | **BLOCKED_BY_SOURCE**. 회의 스냅샷 Pydantic PASS와 Owner SHA 검증 분리. Owner 공식 repo/commit, signature 및 lossless mapper/TS 결과 필요 |
| **P0-03** | 잘못된 `issue.text` 자기 슬라이싱 | `validation.py`, `validate_package.py`, `fixtures/copy_for_block.json`, `tests/test_contract_review_validation.py` | **RESOLVED (계약 검사)**. 전체 원본 copy field의 `[start:end)` 검증/잘못된 offset FAIL; 실제 FastAPI 승인 차단은 별도 |
| **P0-04** | 검수·승인 revision/hash·검수 stale·Actor 불일치 | `interface_spec.md §3.2`, `validation.py.approval_allowed` 및 pytest | **FOLLOW_UP (runtime BLOCKED)**. 승인 정확성 계약 검사 PASS; JobStore 영속 게이트/인증·HTTP error는 서빙 PR+PM 결정 필요 |
| **P0-05** | CostGuard가 팀 $10/동일 단계 순차 호출 보장 못함 | `interface_spec.md §7.3`, `IMPLEMENTATION_PLAN.md` | **FOLLOW_UP**. 서버 예약·실청구·다른 계정 팀 원장 3층 분리. `/ai/*` 미연결, 런타임 보호 PASS 금지 |
| **P0-06** | VLM false/unknown/error 후속 동작 미정 | `interface_spec.md §2.6`, `examples/vlm_outcomes_proposed.json` / proposal tests | **BLOCKED_BY_DECISION**. 모든 false/unknown/error에서 후속 과금 0 안전 제안; 실제 HTTP 상태/UX·재업로드 방식 Owner·PM 승인 필요 |
| **P0-07** | 정책 합의·Wire Freeze·구현 완료 혼동 | `interface_spec.md §2.4`, `DECISION_REGISTER.md §5`, `README.md` | **RESOLVED (표기·배포 경계)**. APPROVED_POLICY / LEGACY_IMPLEMENTED_UNMERGED / FROZEN_WIRE(현재0) / BLOCKED_WIRE / EXPERIMENT / DEFER 명시 |

## 3. P1 감사 조치

| ID | 결함 | 수정·증거 | 상태·잔여 |
|---|---|---|---|
| **P1-01** | 대형 사진 UX와 서버 hard cap / EXIF·원본 hash 불명확 | `interface_spec.md §7.4` — 클라이언트 preflight·서버 hard cap·EXIF·ICC/투명/asset variant 분리 | **BLOCKED_BY_DECISION** hard cap 수치·전처리 실험 및 서빙 구현 |
| **P1-02** | 개별 insight ↔ citation 연결 증거 없음 | `interface_spec.md §7.5`, `SCHEMA_MAPPING.md` — optional provenance sidecar | **FOLLOW_UP** Owner 근거 ID·인용 metadata 필요. 임의 사실 승격 금지 |
| **P1-03** | 누락·stale 검수/자동 수정 재검토 규칙 미정 | `interface_spec.md §3.2`, `validation.py`, pytest missing/stale/auto-fix | **RESOLVED (정책+Fixture 검사)**. 실제 서버 구현 **FOLLOW_UP** |
| **P1-04** | legacy Job ID가 인증된 owner 증명처럼 기술 | `interface_spec.md §3.2, §7.4` — 현재 계정/actor 검증 미구현 | **RESOLVED (문서 경계)**, 인증/권한·retention 실제 구현 **FOLLOW_UP** |
| **P1-05** | 9 JobStatus와 VLM/검색/검수 진행상태 혼동 | `interface_spec.md §2.6, §7.5` — stage_progress 제안·기존 상태 불변 | **FOLLOW_UP** 새 진행상태 persistence/HTTP/React 합의 |
| **P1-06** | 300s/1200 tokens/retry0 적용 범위 검증 없음 | `interface_spec.md §7.5` 실측·절단/timeout 검증 분리 | **FOLLOW_UP** 각 실제 제공자 Wrapper 및 프록시 측정 |
| **P1-07** | CONTRIBUTING 옛 Streamlit/기본 dev 표현 | `CONTRIBUTING.md` 실제 기본 main, 팀 통합 dev, `feat/react-ui` | **RESOLVED** remote default 검증 |
| **P1-08** | `{"approved":true|false}` invalid JSON | `interface_spec.md §2.7` true/false 개별 완전 JSON + `tests/test_contract_wire_proposals.py` | **RESOLVED** JSONDecodeError 부정 테스트 |
| **P1-09** | legacy DTO와 v0.5 nullable/structured copy/prompt 차이 | `SCHEMA_MAPPING.md §§2,5,7` 보존 책임 및 검증 차단 | **BLOCKED_BY_SOURCE / FOLLOW_UP** Owner SHA + 실제 mapper round-trip/TS 구현 필요 |
| **P1-10** | 전원 공통 4개+담당 1개 읽기 부담 | `README.md §1`, `TEAM_DISTRIBUTION.md` 역할별 최소 필독 재구성 | **RESOLVED** README+계약 관련 장+본인 문서, 심화는 owner만 |

## 4. 검증의 의미·범위와 미완료 작업

| 실행 | 무엇을 증명하는가 | 아직 못 증명하는 것 |
|---|---|---|
| `python3 docs/contracts/validate_package.py` | 문서 경로/필수자료·합성 Fixture/offset 규칙 구조 | Owner 실제 Wrapper, 새 HTTP/Live |
| `pytest -q tests/test_contract_review_validation.py tests/test_contract_wire_proposals.py` | 전체 카피 field offset/negative tests, revision policy, 제안 JSON 형식 | 서버 JobStore 경로 승인 차단 |
| `python docs/contracts/check_owner_schema.py --source /trusted/owner/schemas.py --expected-sha256 <sha256>` | **실제 전달된 파일**의 SHA 및 Pydantic Fixture 합치 여부 | Mapper/OpenAPI/TS/비용 |
| `python -m pytest -q` (독립 `f979331` tree) | 기존 118 테스트, feature에 대한 과거 기술 회귀 | PR #4 새 Wire 또는 Browser/Live |
| `GET /openapi.json` (실제 backend) | 그 SHA의 **구현된 legacy API** | 명세상의 새 목표 Wire의 존재 |

**신규 FROZEN_WIRE 0건**, Live/Text/Image/Composition/React/광고·원본 보존·$10 실제 총합 비용은 **NOT_VERIFIED**. 이 PR의 계약·Fixture 테스트 PASS가 서버·모델 구현 완료 의미는 아니다.

## 5. 독립 재감사 · PM 병합 판단 안내

- 모든 P0/P1 항목을 이 파일로 추적하되, **BLOCKED_BY_SOURCE/DECISION·FOLLOW_UP을 RESOLVED로 바꾸지 않는다**.
- 독립 감사자는 PR #4 최신 SHA의 `interface_spec.md §2.4~2.7, §3.2, §7.3~7.5`, 신규 Python 계약 검사·부정 테스트·Owner 실제 소스 차단 및 C-ID를 검토한다.
- **권고:** 문서의 상태 표현·검증기 오류가 해소되어도, 실제 신규 HTTP Freeze(0건) 및 텍스트 Owner/이미지 Wrapper가 없는 상황에서는 **'완전 통합 가능한 계약'로 병합 승인하지 않는다**. 정책·문서 SSOT만 범위 제한 승인할지는 PM+영향 담당 리뷰가 필요하다.
- **별도 후속 PR:** 텍스트/이미지 Owner 소스·서명 수령 → 각 Wire Freeze → 실제 HTTP·Approval·CostGuard·Mapper·인증/보안 구현·OpenAPI/TS/브라우저 검증. 기존 dev/main 직접 변경 금지.
