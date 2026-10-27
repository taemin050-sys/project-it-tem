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
| **P0-04** | 검수↔카피/제품 맥락 신뢰 결속 누락(T-03/T-04 수정 전 True 직접 재현) | `validation.py` `ReferenceReviewLedger` + `tests/test_contract_review_binding.py` T-01~T-16 및 `interface_spec.md §3.2` | **RESOLVED (REFERENCE CONTRACT)**: 옛 report+새 hash, 제품명 변경 차단. **FOLLOW_UP (RUNTIME NOT IMPLEMENTED)**: 실제 JobStore/인증/원자 전이 |
| **P0-05** | CostGuard가 팀 $10/동일 단계 순차 호출 보장 못함 | `interface_spec.md §7.3`, `IMPLEMENTATION_PLAN.md` | **FOLLOW_UP**. 서버 예약·실청구·다른 계정 팀 원장 3층 분리. `/ai/*` 미연결, 런타임 보호 PASS 금지 |
| **P0-06** | VLM false/unknown/error 후속 동작 미정 | `interface_spec.md §2.6`, `examples/vlm_outcomes_proposed.json` / proposal tests | **BLOCKED_BY_DECISION**. 모든 false/unknown/error에서 후속 과금 0 안전 제안; 실제 HTTP 상태/UX·재업로드 방식 Owner·PM 승인 필요 |
| **P0-07** | 정책 합의·Wire Freeze·구현 완료 혼동 | `interface_spec.md §2.4`, `DECISION_REGISTER.md §5`, `README.md` | **RESOLVED (표기·배포 경계)**. APPROVED_POLICY / LEGACY_IMPLEMENTED_UNMERGED / FROZEN_WIRE(현재0) / BLOCKED_WIRE / EXPERIMENT / DEFER 명시 |

## 3. P1 감사 조치

| ID | 결함 | 수정·증거 | 상태·잔여 |
|---|---|---|---|
| **P1-01** | 대형 사진 UX와 서버 hard cap / EXIF·원본 hash 불명확 | `interface_spec.md §7.4` — 클라이언트 preflight·서버 hard cap·EXIF·ICC/투명/asset variant 분리 | **BLOCKED_BY_DECISION** hard cap 수치·전처리 실험 및 서빙 구현 |
| **P1-02** | 개별 insight ↔ citation 연결 증거 없음 | `interface_spec.md §7.5`, `SCHEMA_MAPPING.md` — optional provenance sidecar | **FOLLOW_UP** Owner 근거 ID·인용 metadata 필요. 임의 사실 승격 금지 |
| **P1-03** | 누락·stale 검수/자동 수정 재검토 규칙 | `interface_spec.md §3.2`, T-08/T-11/T-12 부정·정상 테스트 | **RESOLVED (참조 계약)**. 실제 서버 적용은 FOLLOW_UP |
| **P1-04** | legacy Job ID가 인증된 owner 증명처럼 기술 | `interface_spec.md §3.2, §7.4` — 현재 계정/actor 검증 미구현 | **RESOLVED (문서 경계)**, 인증/권한·retention 실제 구현 **FOLLOW_UP** |
| **P1-05** | 9 JobStatus와 VLM/검색/검수 진행상태 혼동 | `interface_spec.md §2.6, §7.5` — stage_progress 제안·기존 상태 불변 | **FOLLOW_UP** 새 진행상태 persistence/HTTP/React 합의 |
| **P1-06** | 300s/1200 tokens/retry0 적용 범위 검증 없음 | `interface_spec.md §7.5` 실측·절단/timeout 검증 분리 | **FOLLOW_UP** legacy `text_adapter.py`는 실제 **30s/600 tokens/retries 0**; 회의 300s/1200 미반영. 각 실제 제공자 Wrapper 및 프록시 측정 |
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


## 6. 최종 재현 실행 증거 (실행일 2026-10-27, Mac Studio)

| 검증 | 관찰 결과 | 제한 |
|---|---|---|
| `python3 docs/contracts/validate_package.py` | **PASS**: 필수 파일·합성 Fixture 8개 + Markdown 상대 링크/코드펜스/필수 절 | Owner 공식/Live 아님 |
| `pytest -q tests/test_contract_review_validation.py tests/test_contract_wire_proposals.py tests/test_serving_health.py` | **28 passed**: offset·반복·emoji·hashtags 교차·revision/hash·VLM/Wire 제안 포함 | 실제 FastAPI 승인·신규 endpoint 아님 |
| `python docs/contracts/check_owner_schema.py --source /tmp/ittem_meeting_schemas_v05.py --expected-sha256 d3baa625480e0e767437ea41f56dc485409e55f60b808ddd92fec4261c310e7a` | **8 Fixture Pydantic PASS** (회의 원문 코드 스냅샷) | **김다혜 Owner 공식 SHA가 아님**, official Owner validation **BLOCKED_BY_SOURCE** |
| 별도 `f979331` 독립 스냅샷 `python -m pytest -q` | **118 passed** (Mac 한글 폰트 지정) | 기존 legacy 구현, 새 Wire/React/Live 제외 |
| `python -m scripts.export_p4_contracts` + `python -m scripts.audit_p4_handoff` | 8 schema files + manifest, **13/13 legacy routes, PASS_FOR_TEAM_REVIEW** | 새 VLM/Image/Composer endpoint OpenAPI에 **없음** |
| `gh api POST /markdown` GFM 렌더 구조 | **9개 대영역 h2, 22개 표, 12개 code block** | Mermaid 실제 SVG/접근성 시각 검토 별도 |
| `git diff --check` | PASS | 순수 문서·계약 테스트 변경 |

**위 실증은 PR #4의 신규 API/Mapper/TS/Live E2E를 PASS로 승격하지 않는다.** 각각의 Runtime 구현과 Owner source 확보는 별도 게이트다.

## 7. 2차 재감사 P0-04 추가 반례 및 수정 (2026-10-27)

**출처:** 지정 핸드오프 폴더의 `08_PR4_REAUDIT_DECISION_20261027.md`를 확인했다. 전체 의견서 `IT_TEM_PR4_Independent_Reaudit_20261027.md`는 지정 폴더에 없었으므로 내용을 직접 검증했다고 주장하지 않는다.

| 반례 | 수정 전 직접 재현 | 수정 후 참조 승인 | 검증 이름 |
|---|---|---|---|
| **T-03** 카피 변경 + 최신 client hash + 과거 pass report | **True** | **차단 — STALE_REVIEW_COPY** | `test_t03_stale_report_with_new_copy_hash_remains_rejected` |
| **T-04** 제품명 변경 + 기존 copy hash | **True** | **차단 — STALE_REVIEW_CONTEXT** | `test_t04_product_name_changes_while_copy_hash_unchanged_fails` |
| T-01/T-12 | 정상 승인 경로 유지 필요 | **PASS** (서버 발행 정상 기록/새 revision 검수) | `test_t01...`, `test_t12...` |
| T-02/T-05~07 | 이전에는 맥락/변경 결속 부족 | **차단** (카피·사용자 원문·제품 주장·revision) | `test_t02...`, `test_t05...`~`test_t07...` |
| T-08~11/T-13~15 | 누락/불일치·검수 실패·위조 기록 경계 | **차단** (보고서/기록 부재·실패·수정·보고서 hash·다른 Job·판본 충돌) | `test_t08...`~`test_t15...` |
| T-16 | 운영 원자 승인 미구현 | **참조 메모리 RLock** 중복 요청 중 한 건만 성공, 검수 진행 중 입력 변경 결과 거부 | `test_t16_concurrent_double_approval_only_one_commits_in_memory`, `test_t16_review_finishing_after_context_race_rejected` |

**참조 계약 설계:** `canonical_copy_hash()`는 기존 AdCopyOutput 전용 SHA-256을 유지한다. 새 `review_input_sha256`는 서버가 검수에 보낸 전체 카피·Job·revision·제품명·user_text·제품 주장/추가 실제 입력·source/model/rules 버전을 묶는다. 검수 시작에 고정한 immutable 스냅샷과 내부 완료 결과가 만나는 시점에만 서버 소유 `StoredReview`를 만든다. 승인 요청자가 제출한 해시끼리 일치하는지만 검사하는 경로는 제거했다.

**신뢰/실행 경계:** `ReferenceReviewLedger`는 인증·서명·영속성 없는 단일 프로세스 **참조 구현**이다. `begin_review`의 토큰도 공급자 진위 인증이 아닌 backend 내부 상관관계 ID이다. 실제 JobStore/인증/권한·DB 트랜잭션·동시 worker·재시작 복원·HTTP 409 및 TS 타입은 **FOLLOW_UP**이며 검수 Owner의 실제 입력 범위는 **BLOCKED_BY_SOURCE**이다. 신규 공개 HTTP Wire 7개는 **BLOCKED_WIRE / FROZEN 0** 유지.

**최종 테스트 재현:**
```bash
python3 docs/contracts/validate_package.py
python -m pytest -q tests/test_contract_review_binding.py tests/test_contract_review_validation.py tests/test_contract_wire_proposals.py tests/test_serving_health.py
git diff --check
```

**검증 의미:** 기존 계약 28개 + 신규 23개 = **51 PASS**는 참조 계약 수준만 증명한다. 기존 `f979331` 118 회귀는 별도 고정 스냅샷 검증이며 새 runtime 승인 게이트를 보증하지 않는다. 판정: **REFERENCE CONTRACT PASS / RUNTIME NOT IMPLEMENTED**. 독립 재감사 및 PM 병합 보류 유지.
