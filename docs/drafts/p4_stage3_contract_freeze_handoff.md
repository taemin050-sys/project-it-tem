# IT-TEM P4-Preflight Stage 3 — Contract Freeze Readiness & Team Handoff

> **2026-10-24 · DRAFT / REVIEW ONLY / NOT TEAM-APPROVED**
> 기준 커밋: `eb8a512` (`feat/p4-provider-readiness`), GCP 실환경 `107 passed` 및 GitHub Push는 사용자 로그로 확인.
> 공식 SSOT는 **PM 승인 후의** `docs/interface_spec.md`. 본 문서는 그 파일을 수정·승격하지 않는다.
> 목적: 2026-10-26(월) 팀 협의 1회로 **공통 계약 freeze → 파트별 병렬 개발 → 순차 통합**을 시작하는 데 필요한 증거·결정사항·책임 경계를 한곳에 정리한다.

## 0. 2분 요약 / 이번 주말에 확정할 수 없는 것

- **확인됨:** FastAPI 단일 VM 모의 워크플로(P1~P3), 텍스트 호출 준비(P4A), DTO/Fixture/포트(Stage 1), 연구·기획·이미지 내부 어댑터 및 단일-host 비용 예약(Stage 2). 테스트 **107 passed**는 GCP에서 확인됐다.
- **아직 아님:** 팀 최종 합의, React 브라우저 E2E, 실제 웹/논문 검색, 실제 이미지 모델 호출, 광고 적법성 검수, 제품 원형 보존, 최종 실모델 통합 E2E, 분산/운영 보안.
- **주요 단절:** (1) Stage 2 Research→P4A `/ai/plan` 미연결 (2) Stage 2 SQLite 비용 원장→P4A `/ai/*` 미연결 (3) Image Adapter→JobStore/승인검증/최종 합성/HTTP 미연결.
- **월요일 선결정:** P0 결정표 C-01~C-12의 담당자·변경 요청·최소 범위·승인, 특히 **누가 VisualBrief를 생산하고 어떤 copy revision을 소비하는가**, **어떻게 중복 과금을 막는가**, **이미지 래퍼 실제 입력 제약**.
- **보호:** GPU VM 중지/재부팅 금지. 유료 모델 API는 기본 OFF. `dev`·`main` 직접 변경·팀 승인 없는 기존 API 변경 금지.

## 1. 구현 상태 / 계약 진실표

| 기능/인터페이스 | 현재 실제 상태 | 팀 논의 필요 사항 / 방어선 |
|---|---|---|
| POST `/api/v1/jobs`; GET `/api/v1/jobs/{job_id}`; asset download | P2 implemented & HTTP smoke PASS | 제품2~5/참고0~5, 크기 제한, 파일 형식; 권한/보존 정책 미완 |
| `/mock/plan`, `/mock/copy`, `/mock/image`, `/mock/compose` | P3 implemented; 의도적 잘못된 순서 `409`, 최종 PNG 1080×1350 | 회귀용 유지; 실제 AI 생성 증거 아님 |
| POST `/approvals/copy`, `/approvals/image` | P3 implemented; `approved:false`는 종료 상태 | 거절 후 재시도 범위, actor/revision 기록은 신규 제안 |
| GET `/artifacts/{kind}` | P3 implemented (`plan`, `copy`, `image`, `final`, `caption`) | 다운로드·출처 표시 UX/접근 권한 |
| `/api/v1/capabilities`, `/ai/plan`, `/ai/copy` | P4A implemented, **실모델 기본 OFF**; Fake SDK 테스트 | 실모델 ID/금액/활성화 승인; 현재 plan은 **검색하지 않음** |
| `ProductFacts`, `Evidence`, `PlanResult`, `CopyResult`, `VisualBrief`, `ImageResult`, `GenerationReceipt` | Stage1 **내부 Provisional DTO**, JSON Fixture 7개 | 기존 API 응답과 **동일한 wire schema가 아님**; 필드 승인 필요 |
| Research/Planning Bridge | Stage2 내부 구현, fake 검색 결과 검증 | 실제 검색 도구/권한, Evidence 신뢰도, 출처 대응 |
| Image Adapter | Stage2 내부 구현, 이미지 바이트·MIME·digest 검사 | 래퍼 생성 실험과 이미지 보존 수용, **HTTP 경로·저장/상태 변경 없음** |
| SQLite `P4CostGuard` | Stage2 내부 구현, 단일 DB 예약/중복 차단 | 기존 P4A API 연결 전 실과금 금지; 청구 내역 수동 확인 |
| POST `/ai/image` / POST `/compose` | **NEW PROPOSED / NOT IMPLEMENTED** | PM 승인 전 경로 생성·프론트 연동 금지 |
| 오류 DTO 확장 `error_code` 등 | **NEW PROPOSED** | 기존 `detail` 문자열 또는 객체 유지; 최종 형식 합의 |
| React TS Client | P4A `docs/drafts/react_client_provisional.ts` 예시 | 실제 React 빌드·브라우저 연동 **미검증** |

**결론:** 107 PASS는 *계약 도구/내부 어댑터 및 Mock* 검증이다. 사용자에게 **Live E2E PASS**라고 보고하지 않는다.

## 2. 공통 계약 / 변경 불변조건

1. API 루트는 `/api/v1`, 제품2~5·참고0~5, multipart `product_images`/`reference_images`, 상태값 기존 9개를 합의 전까지 변경하지 않는다.
2. 승인순서 `INPUTS_VALIDATED → PLAN_READY → COPY_REVIEW_REQUIRED → COPY_APPROVED → IMAGE_REVIEW_REQUIRED → IMAGE_APPROVED → COMPLETED`; 거절 terminal 두 상태(`COPY_REJECTED`, `IMAGE_REJECTED`).
3. 현재 409는 허용되지 않은 상태 전이의 **정상 거절**이며 React는 `GET job`으로 회복한다.
4. 공통 DTO는 **내부 구조**. OpenAPI의 현재 HTTP 응답과 외관상 유사하더라도 무단 치환하지 않는다.
5. 기획이 검색하지 않았으면 `research_performed=false`; 검색했더라도 근거의 `verification_status=unverified`는 검증 완료를 뜻하지 않는다. 제품 주장·시장 가설·독립 검증 사실을 구분한다.
6. `CopyResult.compliance_checked=false` 기본; 카피/사진 미검토 상태를 규제 승인·상품 보존 성공으로 표시 금지.
7. 이미지 생성은 승인된 카피 버전(현 P3에는 영속 revision 없음), 원본 asset ID의 소유권, 이미지 1개, 출력 바이트 해시를 확인한다. 승인 revision 저장 도입은 계약 승인 대상.
8. 최종 1080×1350 PNG 합성에서 한글은 결정론적 렌더링(Pillow 등) 우선. 실제 생성 이미지와 Mock 산출물은 플래그 분리.
9. 타임아웃/429/응답 유실은 **자동 재제출 금지**, 과금 불명확한 ledger는 운영자 확인 전 재사용 금지.
10. PM 승인 전 보안 미구현 개발 서버를 외부 공개하거나 실제 키를 프론트로 전달하지 않는다.

## 3. 월요일 회의 — 우선 결정 12개 (30~40분 권장)

| ID | 승인할 항목 (변경 없으면 권고안 채택) | 주 담당 / 영향 담당 | 기한/결과 |
|---|---|---|---|
| C-01 | `/api/v1` 고정, `docs/interface_spec.md` 단일 SSOT·버전 v0.1 | PM/서빙/전원 | 버전·효력 시작 기준 |
| C-02 | 제품2~5/참고0~5, PNG/JPEG/WEBP, 용량 제한·MIME 검증 | React/이미지/서빙 | 업로드 Fixture 동결 |
| C-03 | 기획 필드·`Evidence` 검증단계·웹 검색 최소 1개 출처 정책 | 기획/카피/PM | 리서치 입력/출력 승인 |
| C-04 | `VisualBrief.prompt_en`, 카피 승인 revision, 수정/재승인 규칙 | 카피/이미지/서빙 | VisualBrief Fixture 승인 |
| C-05 | 이미지 제공자 지원 해상도·입력 사진 수·후보1개·라벨 보존 검수 | 이미지/PM/서빙 | 생성 DTO·품질 수용 |
| C-06 | 상태·승인·거절 이후 workflow (M1 terminal 권고) | React/PM/서빙 | Job UX 결정 |
| C-07 | 409/422/413/429/502/503/504, 지연/응답 유실/중복 과금 | 서빙/PM/이미지 | 오류·재시도 표준 |
| C-08 | 웹 검색 제공자, 논문/브라우저 사용 범위·제약 | 기획/서빙/PM | 리서치 최소범위 |
| C-09 | `not_checked/review/block/pass` 판정 주체·광고 심사 | 카피/PM | 표시·게시 차단 기준 |
| C-10 | 단계별 실제 API 비용·횟수·키/격리 정책, billable OFF→ON 조건 | 서빙/PM/모델 담당 | 승인된 제한 호출만 허용 |
| C-11 | 10/30 Mock+Live 구분된 인수 기준·고정 제품 테스트셋 | PM/전원 | E2E acceptance checklist |
| C-12 | 소유자/RACI, 파일 충돌 규칙·PR 병합 순서·대응자 | PM/전원 | 계약 freeze/통합 책임 |

회의 운영: (a) 기존 API/상태 5분 (b) 기획→카피 7분 (c) 카피→이미지 7분 (d) 이미지→합성 5분 (e) 승인·오류·비용 8분 (f) PM 결정 및 Issue owner 5분. 미결정 항목은 `HOLD`/owner/date와 **Mock 계약 우회 방식**을 명시하고 종료. 암묵적 합의 금지.

## 4. 담당자별 바로 실행할 작업 / 완료 증빙

### 4A. React 프론트엔드
- **받는 것:** GET `/api/v1/jobs/{job_id}` 응답, 상태 9개, 아티팩트 URL, `docs/drafts/react_client_provisional.ts`.
- **지금 할 수 있는 일:** 업로드 FormData, 상태별 버튼 표시/disable, 승인·다운로드 UI를 P3 Mock으로 연결. `409 → GET` 재동기화, `503` 제공자 미준비 안내, 제출 중 재클릭 차단.
- **반드시 상의:** 배포 도메인/HTTPS/인증 방법과 Vite proxy, `approved:false` UX, 근거 표시, 진행중 모델 로딩 표시. 브라우저에서 서버 `127.0.0.1` 주소는 **사용자 컴퓨터를 가리키므로 원격 VM 접근 경로로 사용 불가**.
- **완료 증빙:** 브라우저에서 제품2장 업로드 → P3 Mock 단계별 승인 → PNG/캡션 다운로드 영상·콘솔 에러0. TypeScript 타입은 **승인 후 OpenAPI에서 재생성**.

### 4B. 기획 / Research (텍스트·LLM 주책임)
- **받는 것:** `ProductFacts` Fixture, `p4_research_adapter.py`, `p4_planning_bridge.py`, `provisional_ports.py`.
- **지금 할 수 있는 일:** Fake `SearchHit` → `normalize_hits` → `ResearchBundle` → `build_plan(...)` 계약 테스트. 검증된 실제 검색 제공자와 모델의 결과를 혼동하지 않음.
- **반드시 상의:** 웹 검색 단일 출처의 최소 적합성, 상품 주장 검증 책임, 인용 claim↔source 매핑, 논문·Browser Use(격리/allowlist) 우선순위.
- **완료 증빙:** 제품 사실/근거 1세트 + `PlanResult` Fixture 통과, 실제 검색 시 URL/수집일·검색 로그 제출, 근거없음 상태 정상 표시.

### 4C. 카피 / VisualBrief (텍스트·LLM 주책임)
- **받는 것:** `PlanResult`, `CopyResult`, `VisualBrief`, Stage1 Fixture.
- **지금 할 수 있는 일:** 기획 Fixture → 카피 1안 → 영어 `prompt_en` 1안 + SafeZone/금지조건; 사람이 승인하지 않은 카피는 이미지 입력 불가.
- **반드시 상의:** 카피 revision 영속화, 승인된 문구 해시·타깃 프롬프트 버전, 금칙/불확실 주장 검수 결과.
- **완료 증빙:** 실제 승인 카피 1개와 대응 `VisualBrief` 1개, 과장 표현 위험 케이스 1개, `compliance_checked` 상태 명확.

### 4D. 이미지 생성 (이미지팀 주책임)
- **받는 것:** `VisualBrief`, 제품사진/참고 이미지의 서버 검증 바이트, Stage2 `p4_image_adapter.py`의 `ImageGenerator` 포트.
- **지금 할 수 있는 일:** Fake 구현체 또는 팀 소유 Wrapper로 후보 1개 반환, 실제 바이트 포맷·해시·치수 불일치 차단. 텍스트 합성은 분리.
- **반드시 상의:** OpenAI 이미지 API 래퍼 지원 inputs/outputs, 제품 외형/라벨 보존, 배경 투명/잘림/4:5, 비용·응답 유실 정책.
- **완료 증빙:** 후보 1개 + `ImageResult`/`GenerationReceipt` + 사람 평가표. **모델 생성 성공 ≠ 제품 보존 합격**.

### 4E. 서빙 / 백엔드 / 인프라
- **받는 것:** 13개 현재 경로, 상태 머신, Stage2 내부 포트, 비용/중복 차단 원장.
- **지금 할 수 있는 일:** 107개 회귀, Stage3 read-only 감사, OpenAPI + DTO 스키마 + 해시 매니페스트 재생성, 담당팀에 7개 Fixture 전달. 승인 전 실연동 routes는 만들지 않음.
- **반드시 상의:** Research→`/ai/plan` 연동 책임, Stage2 ledger→P4A API 실제 연결, 이미지의 승인/asset ownership/JobStore persist 트랜잭션, 취소·오류 처리, 다중 worker 전환 제약, CORS/인증/HTTPS.
- **완료 증빙:** 동일 `job_id`에서 Mock E2E, Job 재시작 복원, 비용 사전예약·중복 차단·오류 수동 확인, 공개 API 계약 테스트 PASS.

### 4F. 최종 합성 / 디자인 품질 (서빙 + 이미지 + React 협업)
- **받는 것:** 승인 이미지 asset+sha, 승인 카피 text+revision, SafeZone, 최종 1080×1350 규격.
- **지금 할 수 있는 일:** P3 Pillow 합성 확인, 한글 폰트/줄바꿈/여백/겹침/긴 문구 시각 검수 Fixture 수립.
- **반드시 상의:** 모델 내부 해상도와 최종 4:5 크롭, 텍스트가 제품·로고·법정표시를 가리지 않는 배치.
- **완료 증빙:** 1080×1350 PNG+캡션, 한글 2종 길이(짧음/김)와 원형 보존 평가 시트.

### 4G. PM / QA
- **받는 것:** 이 문서의 C-01~12, `p4_stage3_audit.json`, 고정 E2E 샘플.
- **지금 할 수 있는 일:** 각 파트 변경 제안의 compatibility 위험/시간/예산 표시; `dev` 병합 전 사전 검토.
- **반드시 상의:** 정책상 인증·상업용 실사용 여부와 10/30 데모 목표 경계, 무료/유료 호출 상한, 광고 법규 검수의 사람 책임.
- **완료 증빙:** 승인자/버전/날짜/이슈 리스트, CT-01~15 체크, MOCK/LIVE 분리 평가표.

## 5. 계약-코드 차이점 / 변경 위험 우선순위

| GAP ID | 발견된 공백 | 위험 | 권고 / 소유 / 선행조건 |
|---|---|---|---|
| G-01 | Stage1 `PlanResult`과 현재 P4A HTTP `plan` wire JSON이 다름 | React 잘못된 필수 필드 접근 | **P0** BE+기획: wire vs internal DTO 사상계층 합의, fixture 재검증 |
| G-02 | Stage2 `ResearchBundle`이 실제 `/ai/plan`에 미연결 | 리서치 없는 계획을 조사완료 오인 | **P0** 기획+BE: 실제 provider/출처 확인 후 연결, `research_performed` 정직 표시 |
| G-03 | Stage2 SQLite CostGuard가 P4A 텍스트 엔드포인트에 미연결 | 다중 요청·응답 유실·중복 과금 | **P0** BE+PM: 실호출 전 ledger 연결과 과금 불확실 상태 테스트 |
| G-04 | Stage2 ImageAdapter가 HTTP/JobStore에 미연결 | 이미지 Mock/Live 혼합·승인 미준수 | **P0** 이미지+BE: 입력 asset·승인 copy 검증, atomic persist, feature flag OFF 기본 |
| G-05 | P3 승인에는 actor/revision 영속화 없음 | 승인 이후 바뀐 프롬프트/이미지 무검증 | **P0 결정**, 구현은 합의범위 기반 BE+FE+이미지 |
| G-06 | 최종 합성은 Mock Pillow 전용 | 실제 이미지·카피 합성 누락 | **P0** BE+이미지: 실제 승인 아티팩트로 composer 전환 |
| G-07 | 실제 브라우저/React E2E·보안 없음 | 로컬 테스트만으로 납품 오판 | **P0** FE+BE+PM: 라우팅/인증·데모 환경 승인 |
| G-08 | Stage2 가격은 예약 추정치이고 reconciliation 미구현 | 잔액/비용 보고 왜곡 | **P1** PM+BE: 사용자 비용 예산과 실청구 대조 규칙 |
| G-09 | 체계적 논문 검색·브라우저 자동화 미연결 | 기획 범위 확장으로 납기 지연 | **P1/DEFER** 기획+PM: 10/30 최소 웹 검색과 분리 |
| G-10 | `main.py`, `job_store.py`, `docs/interface_spec.md` 공통 수정 충돌 | 병렬 PR 재작업 | **P0** BE 통합 소유, 모델 파트는 별도 모듈. contract PR 우선 |

## 6. Git / 팀 통합 (stacked branches 주의)

확인된 작업의 선형 스택:

```text
3ac2c72 P1 -> 3f80c85 P2 -> 2ba82ac P3 -> 9d5dbc7 P4A
  -> fa2c597 Stage1 -> eb8a512 Stage2 -> (Stage3 review-only)
```

- `feat/p4-provider-readiness`는 **`dev`에 독립적으로 병합 가능한 단일 변경분이 아님**. 선행 P1~Stage1 커밋이 포함된 stacked feature 브랜치.
- P1 PR #3은 이전에 OPEN이었으나 **현재 상태는 확인되지 않음**. 월요일 PM에게 병합 상태를 먼저 확인해야 한다.
- 안전한 접근: PM이 현재 `dev`의 정확한 merge/squash 이력을 확인 후, 각 기능을 선행순서로 리뷰하고 필요시 새 `dev` 기반 브랜치에 *필요한 커밋만* cherry-pick. 재작성/force push/무단 squash를 자동 실행하지 않는다.
- 다른 팀 담당자는 현재 우리 브랜치를 그대로 `dev`에 PR해서 중복 코드를 끌어오지 않도록 **선행 PR/베이스**를 명시한다.
- 계약 최종 내용은 PM 승인 후 별도 contract-only PR 또는 `dev` 기준 브랜치로 승격. 이 Stage3 패치는 리뷰 문서·읽기 전용 감사 도구·검증 테스트 추가만 포함.

## 7. P4-Parallel → Integration → E2E 단계별 인수 조건

| 단계 | Entry | Exit / 실패 시 대응 |
|---|---|---|
| Contract freeze | C-01~12 주담당 코멘트와 문제 없는 기존 API를 분리 기록 | `APPROVE`/`CONDITIONAL`/`HOLD`, 공식 계약 버전·PM 서명, Fixture 고정 |
| Parallel | 승인된 Fixture 및 모듈 경계 전달 | 각 파트 단위 성공+실패 테스트, Mock/Live 비용 구분, PR 소유 명시 |
| Integration | 다음 단계 이전까지 전 단계 Mock이든 실이든 Contract PASS | 한 파트씩 실제 어댑터 연결, ledger/approval/asset 원자성 검증, 실패하면 명시적 OFF (성공 은폐 금지) |
| E2E Mock | 2~5장·참고0~5장 유효 업로드 | P3 상태+승인/다운로드·최종 PNG 1080×1350 PASS |
| E2E Live | PM 허용 모델·실호출 예산·보안/키/ledger; 실제 UI | 웹/기획/카피/이미지/합성 중 실제 단계와 Mock 단계 분리 기록, 비용·근거·광고/이미지 QA 증빙, 미충족이면 LIVE NOT READY |

### E2E 품질·실패 시나리오 최소표

- **Happy path:** 2장 업로드 → 조사 근거 처리 → PlanResult → 카피 1개 승인 → 이미지 1개 승인 → 합성 PNG+TXT 다운로드.
- **승인:** 카피 승인 전 이미지 409, 이미지 승인 전 합성 409, 거절 terminal 409, 상태 refresh 복구.
- **데이터:** 잘못된 타입/중복 이미지/필드 누락, 위험한 제품 주장, 빈/중복 근거, 이미지 digest 위변조, 무효 revision.
- **비용:** 모델 OFF 503, 타임아웃·429·응답 유실→미승인 재호출 0회, SQLite 예약 흔적과 billing unknown 표시.
- **품질:** 한글 실제 렌더, Safe Zone, 로고/라벨, 긴 카피·오버플로, 제품 원형 보존 사람이 검토.

## 8. 실행 증거 생성 (모델 호출 없음)

```bash
cd ~/project-it-tem
source .venv/bin/activate
python -m pytest -q
python -m scripts.export_p4_contracts --output .runtime/contracts
python -m scripts.audit_p4_handoff --output .runtime/handoff/p4_stage3_audit.json
python -m json.tool .runtime/handoff/p4_stage3_audit.json | head -70
```

- Auditor는 현재 FastAPI OpenAPI 라우트(필수 13개), React 9개 JobStatus, 내부 Fixture 7개, OpenAPI/Schema 8개 + Manifest 1개의 체크섬 및 현재 코드의 재생성 결과를 비교한다.
- 기대 결과는 `PASS_FOR_TEAM_REVIEW`이지 `APPROVED`가 아니다. **GCP 실환경에서의 실제 출력이 증거**이며, 별도 작업환경 통과는 참고.
- 산출물 `.runtime/contracts/`와 `.runtime/handoff/`는 `.gitignore` 영역이므로 Git에 올리지 않는다. JSON에는 API Key·제품 원본을 넣지 않는다.
- 감사 도구는 외부 API를 호출하거나 유료 사용을 켜지 않는다. 현 프로토타입 앱 객체를 읽기 위해 임시 로컬 JobStore 디렉터리만 생성할 수 있다(시스템 임시 디렉터리, 작업 종료시 제거).

## 9. 최종 승인 후 문서화 및 구현 가이드 생성 조건

1. `docs/interface_spec.md`에 `[DECIDE]` 미결정 항목/충돌을 해소하고 **`v0.1-approved`** 날짜/PM/파트 서명 및 변경 기록 부여.
2. 확정된 요청·응답 wire DTO, JSON Fixture, 버전/오류 예제, 실제 모델 입력/출력 매핑과 승인 revision을 반영.
3. FastAPI OpenAPI 재생성 → TS 타입 자동 생성/프론트 실 빌드 → API 계약 회귀/실 모델 통합 Smoke 단계.
4. 각 파트별 구체 구현 가이드(호출 URL/JSON request/response, 승인/실패/예산, 최소 테스트)를 재작성·배포.
5. Live provider 별로 opt-in·키/권한·가격·재시도 정책을 PM 승인. 이 감사 도구/문서는 어떤 실호출도 자동 승인하지 않는다.
