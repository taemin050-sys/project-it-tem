# IT-TEM API List — 팀 협업용 HTTP Reference (B0 Mock)

> **기준일:** 2026-10-27 · **문서 버전:** 0.1.0-B0 · **구현 기준:** `dev@b5e227e83e7ce0989f4573845909de66ea942da8` (PR #4 정책 SSOT + PR #5 P2/P3 병합).
>
> **SSOT 계층:** 정책·승인·데이터 의미는 [`interface_spec.md`](interface_spec.md), **실제 HTTP 경로·요청 모델**은 해당 커밋에서 실행한 FastAPI `app.openapi()` / `GET /openapi.json`, 본 문서는 사람을 위한 **사용 가이드**다. 모순 발견 시 계약을 임의 변경하지 않고 이슈·PR에서 조정한다.
>
> **안전 표시:** 현재 모든 Job workflow는 **MOCK**. 모델·웹검색·실제 Compliance 검수·실제 이미지 생성 없음. 기본 유료 호출 **OFF**, 신규 HTTP Wire **7건 BLOCKED_WIRE / FROZEN 0**. **B0 Python API 테스트 PASS는 React Browser E2E PASS가 아니다.**

## 0. Quick Start · 실행 위치 · 상태 범례

| 환경 | 실행 / 접속 | 증거·주의 |
|---|---|---|
| 단일 PC 로컬 | 저장소 최상위에서 `IT_TEM_KOREAN_FONT=/path/to/verified/Korean-font.ttf python -m uvicorn src.serving.main:app --host 127.0.0.1 --port 8000` | 한글 Mock 합성은 Nanum/Noto 등 설치된 폰트 필요. macOS 검증 경로: `/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf` |
| 같은 PC의 React+Vite | Vite dev proxy를 `/api` → `http://127.0.0.1:8000`로 설정; 프론트 요청은 `/api/v1/...` 상대 경로 | Vite 설정은 React 담당자가 구현/검증해야 하며, **현재 저장소에 React 앱은 없음** |
| 분리 PC / GCP | **승인된 접근·인증·TLS·proxy가 확정된 경우에만** 실제 호스트 사용 | `localhost`는 브라우저가 실행 중인 PC를 가리킨다. GCP 공개 URL **미검증**; VM 8000 외부 공개 금지 |
| Swagger / OpenAPI | `http://127.0.0.1:8000/docs` · `http://127.0.0.1:8000/openapi.json` | 해당 앱을 **로컬 실행했을 때** 사용할 수 있음. OpenAPI는 `app.openapi()`로도 추출 가능 |

예시는 **로컬 동작 기준**이다. 사전에 서로 다른 실제 화장품 사진을 `/tmp/ittem-product-a.png`, `/tmp/ittem-product-b.png`에 준비한다. 예제의 경로는 사용자가 실제 파일로 바꿔야 한다. **같은 바이트를 두 번 업로드하면 422**다.

```bash
export API_BASE=http://127.0.0.1:8000
curl -sS "$API_BASE/health"
curl -sS "$API_BASE/openapi.json" -o /tmp/ittem-openapi.json
# uvicorn 서버는 다른 터미널에서 실행되어 있어야 한다.
```

**두 축으로 읽기**

- **구현 위치:** `IMPLEMENTED_DEV`(해당 dev + OpenAPI 확인), `IMPLEMENTED_FEATURE`(다른 feature만), `NOT_IMPLEMENTED`.
- **실행 모드:** `MOCK` / `FAKE` / `LIVE` / `N/A`. 이번 10개 Job 경로는 모두 `IMPLEMENTED_DEV + MOCK`이며, `/health`는 `IMPLEMENTED_DEV + N/A`.
- `PROVISIONAL`은 내부 DTO·Adapter 또는 잠정적 구현 조건, `BLOCKED_WIRE`는 기술 동결·HTTP 구현 승인 전인 제안, `FROZEN_WIRE`는 승인된 미래 기술 계약이다. **이번 기준 신규 FROZEN_WIRE=0**.
- 협업 대상: [React](contracts/partners/FRONTEND.md) · [Text](contracts/partners/TEXT_AI.md) · [Image/Compose](contracts/partners/IMAGE_COMPOSER.md) · [Serving](contracts/partners/SERVING.md) · [PM/QA](contracts/partners/PM_QA.md). 결정 및 매핑은 [결정표](contracts/DECISION_REGISTER.md)·[매핑표](contracts/SCHEMA_MAPPING.md)를 참조.

## 1. API Overview — 현재 dev 실제 구현 11개

**전체 11개 = 현재 dev HTTP 11개** (`GET /health` 1개 + Job 10개). `GET /docs`·`GET /openapi.json`은 FastAPI 제공 메타데이터 엔드포인트로 **아래 11개 OpenAPI operation 수에서 제외**한다.

| Group | Method | Endpoint | 기능 / 성공 상태 | 구현 | 모드 | 담당 |
|---|---|---|---|---|---|---|
| System | GET | [`/health`](#2-system--health) | 서버 상태 / 200 | IMPLEMENTED_DEV | N/A | Serving |
| Job | POST | [`/api/v1/jobs`](#3-upload--job) | 업로드·Job 생성 / 201 | IMPLEMENTED_DEV | MOCK | Serving |
| Job | GET | [`/api/v1/jobs/{job_id}`](#3-upload--job) | Job/상태·아티팩트 조회 / 200 | IMPLEMENTED_DEV | MOCK | Serving |
| Asset | GET | [`/api/v1/jobs/{job_id}/assets/{asset_id}`](#7-artifacts--download) | 원본 수신 이미지 다운로드 / 200 | IMPLEMENTED_DEV | MOCK | Serving |
| Plan | POST | [`/api/v1/jobs/{job_id}/mock/plan`](#4-planning--copy) | Mock 기획 / PLAN_READY | IMPLEMENTED_DEV | MOCK | Serving |
| Copy | POST | [`/api/v1/jobs/{job_id}/mock/copy`](#4-planning--copy) | Mock 카피 / COPY_REVIEW_REQUIRED | IMPLEMENTED_DEV | MOCK | Serving |
| Approval | POST | [`/api/v1/jobs/{job_id}/approvals/copy`](#5-approval) | 카피 승인/거절 | IMPLEMENTED_DEV | MOCK | Serving |
| Image | POST | [`/api/v1/jobs/{job_id}/mock/image`](#6-image--composition) | 사진 기반 Mock 이미지 / IMAGE_REVIEW_REQUIRED | IMPLEMENTED_DEV | MOCK | Serving |
| Approval | POST | [`/api/v1/jobs/{job_id}/approvals/image`](#5-approval) | 이미지 승인/거절 | IMPLEMENTED_DEV | MOCK | Serving |
| Composition | POST | [`/api/v1/jobs/{job_id}/mock/compose`](#6-image--composition) | Mock 합성 / COMPLETED | IMPLEMENTED_DEV | MOCK | Serving |
| Artifact | GET | [`/api/v1/jobs/{job_id}/artifacts/{kind}`](#7-artifacts--download) | JSON·PNG·caption 파일 다운로드 / 200 | IMPLEMENTED_DEV | MOCK | Serving |

**별도 보류:** 전체 누적 feature `f979331`는 실제 **14개 OpenAPI operation(health 1 + /api/v1 13)**으로, 현재 dev보다 **추가 3개**(`POST /api/v1/jobs/{job_id}/ai/plan`, `POST /api/v1/jobs/{job_id}/ai/copy`, `GET /api/v1/capabilities`)가 있다. 이들은 현 dev에 없다. 신규 v0.5 연동용 [제안 7건](#8-pending--proposed-wire)은 **11개 현재 호출 가능 API에 포함되지 않는다**.

## 2. System / Health

**GET `/health`** · `IMPLEMENTED_DEV / N/A` · 입력 없음 → 200 JSON.

```bash
curl -fsS "$API_BASE/health"
```
```json
{"status":"ok","service":"it-tem-backend","version":"0.1.0"}
```

`/docs`와 `/openapi.json`은 FastAPI 기본 Swagger UI 및 기계판독 규격이다. **`/capabilities`는 현재 dev에 구현되지 않음**(과거 feature는 별도 검증); 존재하지 않는 경로를 UI에서 호출하지 않는다.

## 3. Upload / Job

### POST `/api/v1/jobs` — 제품·참고 사진 업로드

**상태:** `IMPLEMENTED_DEV + MOCK` · Owner Serving · P2 인수 `4d1740a` → PR #5 병합 `b5e227e`. Mock 여부와 무관하게 서버에 실제 사진 bytes를 저장한다.

| Param | 위치 | 형식 | 필수 | 현재 코드의 제한 |
|---|---|---|---|---|
| `product_images` | multipart form 반복 | PNG/JPEG/WEBP file array | 예 | **2~5장**, MIME와 디코드 실제 포맷 일치 |
| `reference_images` | multipart form 반복 | PNG/JPEG/WEBP file array | 아니요 | **0~5장**; 생략 시 0 |
| 파일 크기 | 서버 검증 | 각 이미지 | — | 기본 파일당 10 MiB, 전체 60 MiB, 최대 40 MP / 이미지; 임시 기술 안전 한도이며 UX 정책 최종값이 아님 |
| `brand_name`, `product_name` | **이 업로드 API에 없음** | — | — | **Mock Plan API의 JSON body로 전달**; `ProductInput` 신규 multipart 확장은 BLOCKED_WIRE |

```bash
curl -fsS -X POST "$API_BASE/api/v1/jobs" \
  -F "product_images=@/tmp/ittem-product-a.png;type=image/png" \
  -F "product_images=@/tmp/ittem-product-b.png;type=image/png" \
  -o /tmp/ittem-created-job.json

# jq가 설치된 경우 생성된 Job ID를 다음 호출에서 재사용:
export JOB_ID="$(jq -r .job_id /tmp/ittem-created-job.json)"
```

**201 응답 — 실제 스키마 기반 예제(식별자·시각·해시·크기는 요청마다 달라짐):**

```json
{
  "job_id": "ba5f89c55b0d4c029cc8cba935745791",
  "status": "INPUTS_VALIDATED",
  "created_at": "2026-10-27T07:37:35.973260+00:00",
  "assets": [
    {
      "asset_id": "c31d5df684864b4689ad8b336363a154",
      "role": "product",
      "original_filename": "a.png",
      "content_type": "image/png",
      "size_bytes": 326,
      "width": 100,
      "height": 120,
      "sha256": "208ded4893c5d36531fa82feb6ef51eca07e90334b949fdddf36d82f394b4889"
    },
    {
      "asset_id": "4df65be932d64fd8bc1bd65c9d7e8600",
      "role": "product",
      "original_filename": "b.png",
      "content_type": "image/png",
      "size_bytes": 327,
      "width": 100,
      "height": 120,
      "sha256": "a7aecb2b434589b31d5614cc20e655928644262a8bf93133db5ba093a3cc0b21"
    }
  ]
}
```

**오류:** 422(사진 수 2~5 위반, 중복 바이트/해시, 빈 사진, 손상, MIME 불일치, 형식/픽셀/애니메이션 오류), 413(파일·전체 제한 초과). **파일 업로드 응답은 자동 생성된 새 `ProductInput` 객체가 아니다.** 같은 바이트 이미지를 다른 파일명으로 보내도 422다. 업로드된 상품 사진은 *동일한 제품을 촬영한 서로 다른 원본 이미지*로 준비한다.

### GET `/api/v1/jobs/{job_id}` — 저장된 Job 재조회

**상태:** `IMPLEMENTED_DEV + MOCK` · Path `job_id` = 서버가 발급한 32자리 lowercase hex 문자열. 상태, `assets[]`, 현재까지 생성된 `artifacts{}`, `plan`, `copy_candidate`, `image_candidate`, `final_output` 등 **해당 단계까지 실제 저장된 필드만** 응답한다. **공통 `code/msg/data` 래퍼는 없다.**

```bash
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID"
```

**200 주요 필드:** `job_id:string`, `status:string`, `created_at:ISO 8601`, `assets:array`; 단계 진행에 따라 `plan`, `copy_candidate`, `copy_approved`, `image_candidate`, `image_approved`, `final_output`, `artifacts`이 추가된다. `artifacts[kind].download_url`은 서버가 반환하는 **상대 경로**다. 미존재 Job/잘못된 ID는 404.

**접근·보안:** Job ID는 로그인 사용자 소유권을 증명하지 않는다. 현재 JobStore는 **단일 프로세스/로컬 파일 저장**, 외부 공개·멀티 worker·인증된 사용자 접근을 보장하지 않는다. React는 B0 제한된 개발 환경에서만 사용한다.

---

## 4. Planning / Copy

두 API 모두 **`IMPLEMENTED_DEV + MOCK`**, Serving 관리. 텍스트팀의 실제 Research/Copy/Compliance LLM을 호출하지 않는다.

### POST `/api/v1/jobs/{job_id}/mock/plan`

| Param | Location | Type | 필수 | 제약 |
|---|---|---|---|---|
| `job_id` | path | string | 예 | 유효한 Job ID |
| `brand_name` | JSON body | string | 예 | **입력 원문 1~80자** 검사 후 앞뒤 공백 제거·빈 값/제어문자 차단 |
| `product_name` | JSON body | string | 예 | **입력 원문 1~100자** 검사 후 앞뒤 공백 제거·빈 값/제어문자 차단 |

**이전 상태:** `INPUTS_VALIDATED` → **200** `PLAN_READY`. 응답은 **전체 Job JSON**이며 `plan` 객체와 `artifacts.plan`이 추가된다.

```bash
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/plan" \
  -H 'Content-Type: application/json' \
  --data '{"brand_name":"라움","product_name":"데일리 크림"}'
```

```json
{
  "job_id": "<JOB_ID_FROM_UPLOAD>",
  "status": "PLAN_READY",
  "plan": {
    "mock": true,
    "research_performed": false,
    "brand_name": "라움",
    "product_name": "데일리 크림",
    "audience": "화장품 관심 고객(검증되지 않은 예시 세그먼트)",
    "direction": "제품을 일상적인 루틴의 일부로 소개",
    "disclaimer": "실제 시장·경쟁사 조사 및 화장품 광고 적법성 검토 미실시"
  }
}
```

> 위 JSON은 **전체 Job 응답에서 관련 필드만 표시한 발췌 예시**다. 실제 반환에는 `created_at`, `assets`, `artifacts.plan`도 들어간다. 필수 필드 누락·빈 문자열은 422, 상태 순서 위반/동일 작업 반복은 409. **외부 리서치는 수행하지 않는다.**

### POST `/api/v1/jobs/{job_id}/mock/copy`

**Request:** path의 `job_id`만 필요. JSON body 없음. **이전 상태:** `PLAN_READY` → **200** `COPY_REVIEW_REQUIRED`. 응답은 전체 Job이며 `copy_candidate` 및 `artifacts.copy`가 추가된다.

```bash
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/copy"
```

**응답에 포함되는 핵심 카피 구조(전체 Job 중 발췌):**

```json
{
  "status": "COPY_REVIEW_REQUIRED",
  "copy_candidate": {
    "mock": true,
    "text": "라움 데일리 크림, 일상의 루틴을 위한 한 가지 선택",
    "compliance_checked": false,
    "disclaimer": "AI 광고 문구 초안 예시. 실제 표시·광고 적법성 및 상품 사실관계 검증 필요"
  }
}
```

**중요:** 텍스트 v0.5의 구조화된 `AdCopyOutput`(`headline/subline/cta/caption/hashtags`)이 아니다. 실제 ComplianceReport도 없다. `compliance_checked=false`를 프론트에서 **검수 통과 표시로 바꾸지 않는다**. 이 API의 재호출 또는 `PLAN_READY` 이전 호출은 409.

## 5. Approval

두 엔드포인트는 같은 서버 `ReviewRequest` 모델을 사용한다. **`approved:boolean` 단일 필수 JSON**, 추가 필드는 Pydantic `extra=forbid`로 422. **프론트는 JSON Boolean `true`/`false`만 전송해야 한다.** 현재 타입은 일반 Pydantic `bool`이므로 `"yes"`, `1`, `"FALSE"` 등도 형변환되어 수락된다(**StrictBool 아님**); 타입 엄격화는 후속 정책·서버 PR 대상이다. 신규 카피 revision/hash/검수기록을 기존 Boolean API에 임의 추가할 수 없다.

| Method / Endpoint | 이전 상태 | Request | 승인 결과 | 거절 결과 | 중복·순서 위반 |
|---|---|---|---|---|---|
| POST `/api/v1/jobs/{job_id}/approvals/copy` | `COPY_REVIEW_REQUIRED` | `{"approved":true}` 또는 `false` | `COPY_APPROVED` | `COPY_REJECTED`(종료) | 409 |
| POST `/api/v1/jobs/{job_id}/approvals/image` | `IMAGE_REVIEW_REQUIRED` | `{"approved":true}` 또는 `false` | `IMAGE_APPROVED` | `IMAGE_REJECTED`(종료) | 409 |

**실행 가능한 정상 승인·거절 예:**

```bash
# 카피 승인 (B0: Mock 초안에 대한 사용자 결정일 뿐, 법적 Compliance 검증 아님)
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/approvals/copy" \
  -H 'Content-Type: application/json' --data '{"approved":true}'

# 이미지 승인 (mock/image 호출 후)
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/approvals/image" \
  -H 'Content-Type: application/json' --data '{"approved":true}'

# 거절 경로 테스트는 **새 Job**에서 실행해야 하며, 거절 후 같은 Job의 복구 API는 없음:
# --data '{"approved":false}'
```

**200 응답 예:** 전체 Job JSON의 `status`가 `COPY_APPROVED` 또는 `IMAGE_APPROVED`, `copy_approved: true` 또는 `image_approved:true` 필드가 추가된다. 거절은 각각 `COPY_REJECTED`/`IMAGE_REJECTED` 및 false.

**대표 409 두 형식(실제 TestClient 및 코드 확인):**

```json
{"detail":{"error":"INVALID_WORKFLOW_STATE","current_status":"COMPLETED","expected_status":"COPY_REVIEW_REQUIRED"}}
```

```json
{"detail":"Copy must be approved before image"}
```

React는 `detail`을 **string 또는 object 모두** 처리하고 `409`에서는 `GET /api/v1/jobs/{job_id}`를 다시 호출해 UI 상태를 동기화한다. **현재 HTTP 승인 엔드포인트는 서버 소유 ReviewRecord/generation 검사와 연결되지 않았음(B1-R NOT IMPLEMENTED)**. [승인 정책 SSOT §3.2](interface_spec.md)와 동일하다고 간주하지 않는다.

## 6. Image / Composition

### POST `/api/v1/jobs/{job_id}/mock/image`

**상태:** `IMPLEMENTED_DEV + MOCK`; Request body 없음. **이전:** `COPY_APPROVED` → **200** `IMAGE_REVIEW_REQUIRED`. 응답 전체 Job에는 `image_candidate`와 `artifacts.image.download_url`이 생긴다.

```bash
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/image"
```

```json
{
  "status": "IMAGE_REVIEW_REQUIRED",
  "image_candidate": {
    "mock": true,
    "source": "uploaded_product_photo",
    "size": [1080, 1350]
  }
}
```

> 위는 응답 Job의 **발췌**다. `artifacts.image`는 실제 응답에 포함되며 사진 중 **첫 상품 이미지**를 서버 Pillow로 배치한 **MOCK placeholder**이다. Image Owner의 생성 모델이나 OpenAI Image API를 호출하지 않는다. 승인 전 요청은 409, 동일 단계 중복 호출도 409.

### POST `/api/v1/jobs/{job_id}/mock/compose`

**상태:** `IMPLEMENTED_DEV + MOCK`; body 없음. **이전:** `IMAGE_APPROVED` → **200** `COMPLETED`. 승인된 Mock 이미지에 한글 카피를 합성한다.

```bash
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/compose"
```

```json
{
  "status": "COMPLETED",
  "final_output": {
    "mock": true,
    "width": 1080,
    "height": 1350,
    "format": "PNG"
  }
}
```

> 전체 Job의 발췌이며 `artifacts.final`·`artifacts.caption`의 다운로드 URL이 추가된다. **한글 폰트를 못 찾으면 503**(`detail: "Korean font missing. Install fonts-nanum or set IT_TEM_KOREAN_FONT"`)이고, 기존 `IMAGE_APPROVED` 상태를 유지한다. 정책 SSOT의 실제 광고 적합성/상품 외관 QA까지 검증한 것은 아니다.

## 7. Artifacts / Download

### GET `/api/v1/jobs/{job_id}/assets/{asset_id}`

업로드했던 원본 **바이너리 파일**을 다운로드한다. `asset_id`는 Job 응답 `assets[].asset_id`에서 받아 사용한다. 반환 200, 실제 업로드 파일의 `Content-Type` (image/png/jpeg/webp), `Content-Disposition: attachment`. 미존재 Job·Asset은 404.

```bash
# 최초 Job JSON을 저장해 둔 경우
export ASSET_ID="$(jq -r '.assets[0].asset_id' /tmp/ittem-created-job.json)"
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/assets/$ASSET_ID" -o /tmp/ittem-original.png
```

### GET `/api/v1/jobs/{job_id}/artifacts/{kind}`

실제 **FileResponse**, JSON API 래퍼가 아니다. Job 응답 `artifacts[kind].download_url`을 신뢰해 해당 상대 경로를 GET한다.

| `kind` | 실제 포맷 | Content-Type | FileResponse 저장 파일명 | 생성 시점 |
|---|---|---|---|---|
| `plan` | JSON 파일 | `application/json` | `plan.json` | Mock plan 완료 |
| `copy` | JSON 파일 | `application/json` | `copy.json` | Mock copy 완료 |
| `image` | PNG 바이너리 | `image/png` | `image_candidate.png` | Mock image 완료 |
| `final` | **1080×1350 PNG 바이너리** | `image/png` | `final_mock.png` | Mock compose 완료 |
| `caption` | UTF-8 텍스트 | `text/plain; charset=utf-8` | `caption.txt` | Mock compose 완료 |

```bash
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/plan" -o /tmp/ittem-plan.json
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/copy" -o /tmp/ittem-copy.json
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/image" -o /tmp/ittem-image.png
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/final" -o /tmp/ittem-final.png
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/caption" -o /tmp/ittem-caption.txt
```

**응답 의미:** 파일 스트림·`Content-Disposition: attachment; filename="..."` 사용. 아직 없는 `kind`, 잘못된 `kind`, 다른 Job의 자료는 404. **이미지·caption을 JSON 문자열/BASE64라고 가정하지 않는다.** React는 Blob/Text로 받거나 브라우저 다운로드로 처리한다.

**검증된 캡션 파일 예:**

```text
라움 데일리 크림, 일상의 루틴을 위한 한 가지 선택

#화장품 #일상루틴
```

**필수 구분:** `GET /artifacts/final`과 `GET /artifacts/caption`은 **서로 다른 응답**, 합성된 JSON 하나가 아니다. 파일은 서버 `.runtime/jobs/` 아래 Job별로 영속되지만 사용자 인증·외부 공개 보안은 아직 없음.

---

## 8. Pending / Proposed Wire — 호출 금지

**이 표는 현재 Swagger/실행 API 목록이 아니다.** 10/26 정책 승인과 HTTP 기술 동결은 별개이며, [제안 예제 데이터](contracts/examples/wire_proposals.json) 7건 모두 **BLOCKED_WIRE / FROZEN 0**. 정확한 method/path도 **제안**이므로 프론트 SDK에 고정하지 않는다.

| ID | 제안 method/path 또는 기존 경로 확장 | 역할 | 미확정·필수 증거 / 승인 담당 |
|---|---|---|---|
| UP-EXT | POST `/api/v1/jobs` **확장** | 업로드 시 v0.5 `ProductInput` 함께 전달 | Form 필드·호환성·크기 정책·OpenAPI / React+Serving+PM |
| VLM | POST `/api/v1/jobs/{job_id}/ai/analyze` | 이미지 해석·`is_cosmetic` 분류 | Text 실제 Wrapper 서명·입력 Asset·false/unknown/error 처리 / Text+Serving+React+PM |
| RESEARCH | POST `/api/v1/jobs/{job_id}/ai/research` | 검색·인용·조사 요약 | 검색 포함 내부 Wrapper 소스·Citation 출처 / Text+Serving+React |
| COPY_COMPLIANCE | POST `/api/v1/jobs/{job_id}/ai/copy-review` | 카피·실제 ComplianceReport | 원본 v0.5 소스/SHA·검수 입력 scope·비용·실패 규칙 / Text+Serving+React |
| COPY_APPROVAL_V2 | POST `/api/v1/jobs/{job_id}/approvals/copy` **확장** | 검수 기록/revision 기반 승인 | JobStore ReviewRecord·generation·actor 권한·원자 처리 / Serving+React+Text+PM |
| IMAGE | POST `/api/v1/jobs/{job_id}/ai/image` | 실제 이미지 생성 | Image Owner 소스·서명·비용·MIME·영수증·품질 QA / Image+Serving+PM |
| COMPOSITION | POST `/api/v1/jobs/{job_id}/compose` | 실제 광고 이미지 합성 | Image/Composition 실제 반환 바이트·font·보존 QA·인수 / Image+Serving+React |

**별도 feature에 존재하지만 현재 dev에는 없는 구형 API:** `feat/p4-contract-handoff@f979331`의 `/api/v1/jobs/{job_id}/ai/plan`, `/api/v1/jobs/{job_id}/ai/copy` 및 `GET /api/v1/capabilities`는 **IMPLEMENTED_FEATURE**, 신규 v0.5 Wire와 동일하다고 가정할 수 없다. 해당 두 경로를 React B0에서 호출하지 않는다. 레거시 내부 DTO/Mapper는 [`SCHEMA_MAPPING.md`](contracts/SCHEMA_MAPPING.md) 참조.

**Owner 접점:** 현재 Text/이미지팀은 공식 Schema/Wrapper 원본(commit SHA, 함수 인자·응답·실패 예제)을 Serving에 제공해야 한다. 그 전에는 내부 Fake/Fixture 연동만 가능하다. **B1-R**은 실제 서버 Fake Compliance 차단 구현 후에만, **B1-L**은 실제 Text Compliance 연동 후에만, **B2-T/I/F**는 비용·안전 게이트와 각각의 Live 증거가 있을 때만 PASS. 한쪽만 Live면 **HYBRID**.

## 9. B0 Mock E2E — 실제 호출 순서

**기준:** 현재 `dev@b5e227e`에 실제 구현된 API만 사용한다. B0 React 브라우저 검증은 **10/28 목표 / 현재 NOT VERIFIED**. Job 상태 9개 외의 가짜 상태를 생성하지 않는다.

| 순서 | 실제 HTTP | 이전 상태 → 성공 상태 | 브라우저 처리 |
|---|---|---|---|
| 0 | POST `/api/v1/jobs` | 새 Job → `INPUTS_VALIDATED` | 사진 2~5장(서로 다른 바이트), reference 0~5장. 201 응답의 `job_id` 보관 |
| 1 | POST `.../mock/plan` | INPUTS_VALIDATED → `PLAN_READY` | `brand_name,product_name` JSON |
| 2 | POST `.../mock/copy` | PLAN_READY → `COPY_REVIEW_REQUIRED` | Mock 카피 표시·사용자 확인 |
| 3 | POST `.../approvals/copy` | COPY_REVIEW_REQUIRED → `COPY_APPROVED` | true; false면 `COPY_REJECTED` 종료 |
| 4 | POST `.../mock/image` | COPY_APPROVED → `IMAGE_REVIEW_REQUIRED` | 사진 기반 Mock 이미지, Blob 미리보기 |
| 5 | POST `.../approvals/image` | IMAGE_REVIEW_REQUIRED → `IMAGE_APPROVED` | true; false면 `IMAGE_REJECTED` 종료 |
| 6 | POST `.../mock/compose` | IMAGE_APPROVED → `COMPLETED` | 최종 Job 반환, 1080×1350 PNG 메타데이터 |
| 7 | GET `.../artifacts/final` 및 `.../artifacts/caption` | COMPLETED (변경 없음) | PNG Blob + UTF-8 Text 다운로드 |
| 재조회 | GET `/api/v1/jobs/{job_id}` | 상태 불변 | 오류 409·새로고침 뒤 서버 기준으로 UI 복원 |

**한 번에 실행하는 로컬 Bash + curl + jq 예제** (두 이미지 파일 및 로컬 API 서버가 실제 존재해야 함, 도구 `jq` 설치 필요):

```bash
set -euo pipefail
API_BASE=http://127.0.0.1:8000
IMAGE_A=/tmp/ittem-product-a.png
IMAGE_B=/tmp/ittem-product-b.png
test -s "$IMAGE_A" && test -s "$IMAGE_B"
test "$(shasum -a 256 "$IMAGE_A" | awk '{print $1}')" != \
  "$(shasum -a 256 "$IMAGE_B" | awk '{print $1}')"
JOB_ID="$(curl -fsS -X POST "$API_BASE/api/v1/jobs" \
  -F "product_images=@$IMAGE_A;type=image/png" \
  -F "product_images=@$IMAGE_B;type=image/png" | jq -r .job_id)"
test -n "$JOB_ID" && test "$JOB_ID" != null
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/plan" \
  -H 'Content-Type: application/json' \
  --data '{"brand_name":"라움","product_name":"데일리 크림"}' > /tmp/ittem-plan-response.json
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/copy" > /tmp/ittem-copy-response.json
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/approvals/copy" \
  -H 'Content-Type: application/json' \
  --data '{"approved":true}' > /tmp/ittem-copy-approval.json
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/image" > /tmp/ittem-image-response.json
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/approvals/image" \
  -H 'Content-Type: application/json' \
  --data '{"approved":true}' > /tmp/ittem-image-approval.json
curl -fsS -X POST "$API_BASE/api/v1/jobs/$JOB_ID/mock/compose" > /tmp/ittem-final-response.json
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/final" -o /tmp/ittem-final.png
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID/artifacts/caption" -o /tmp/ittem-caption.txt
curl -fsS "$API_BASE/api/v1/jobs/$JOB_ID" |
  jq '{job_id,status,final_output,artifacts}'
# 정상 기대: status=COMPLETED, final 1080×1350 PNG, caption UTF-8
```

**실제 curl 재현:** 위 Bash 예제를 `127.0.0.1:18765`에만 바인딩한 **별도 임시 uvicorn**에서 실행하고(두 테스트 사진은 임시 생성), 상태 `COMPLETED`, PNG `1080×1350`, UTF-8 한국어 캡션을 확인했다. 임시 서버/데이터는 정리했다. **React Vite UI, 브라우저 Network/HAR/스크린샷은 NOT RUN**이므로 **B0 Browser E2E PASS는 아니다**. 브라우저 인수는 10/28 별도 수행한다.

## 10. Error Handling · Integration FAQ

| HTTP | 실제 코드의 예 | Response 형태 | React/협업 대응 |
|---|---|---|---|
| **404** | 존재하지 않는 Job ID/Asset ID, 없는 kind 또는 아직 생성되지 않은 Artifact | `{"detail":"Job not found"}` 등 문자열 | Job ID·선행 단계·서버 저장 경로 확인. 동일 Job을 다시 조회 |
| **409** | 앞 단계가 미완료, 이미 실행한 Mock 단계 재요청, 승인 거절 뒤 후속 호출, 중복 승인 | `detail` **object 또는 string** | **GET Job 재조회**, 버튼·단계 상태 동기화; 무조건 POST 재시도 금지 |
| **413** | 파일당/전체 업로드 크기 초과 | `{"detail":"Image exceeds per-file size limit"}` 등 | 사용자 사진 리사이즈/용량 줄이기; 임시 서버 안전 상한 유지 |
| **422** | 사진 수/형식/중복·손상·픽셀, 필수 JSON 필드 누락, `approved` 타입 오류 | 문자열 `detail` 또는 FastAPI Pydantic 오류 **배열** | 입력값·multipart 필드명을 확인하고 재업로드; 새 `product_input_json` 임의 추가 금지 |
| **503** | Mock 합성 한글 폰트 부재 | `{"detail":"Korean font missing. Install fonts-nanum or set IT_TEM_KOREAN_FONT"}` | 운영자가 font 설치·env 설정; `IMAGE_APPROVED` 상태에서 문제 해결 후 다시 합성 가능 |
| **500** | 손상된 서버 Job 메타데이터 등 | `{"detail":"Job record is invalid"}` 등 | 서버 운영자에게 보고; 데이터 수동 수정·무한 재시도 금지 |

`400`·`429`·`502`·`504`는 **이번 S3-A 경로에서 실제 구현된 표준 비즈니스 오류로 확인되지 않았다**. 향후 Provider·CostGuard 계약으로 별도 결정/구현한다. FastAPI 자동 `422`는 OpenAPI에 나타나지만, 코드에서 발생시키는 `409/413/503/404`는 **현재 OpenAPI responses 목록에 명시적으로 전부 선언돼 있지 않다**. 이는 계약 자동화의 **미해결 문서화 차이**이며 현 단계에서 서버 구현을 임의 변경하지 않는다.

**FAQ**

- **왜 `/api/v1/jobs/{job_id}/ai/analyze`가 404인가요?** 제안 Wire이며 현재 dev에 없음. Mock `/mock/plan`부터 진행.
- **API 응답에 `data` 래퍼가 없어요.** 맞다. 현재 반환은 Job 원본 JSON이다. `job_id/status/assets/artifacts` 기준으로 파싱.
- **200으로 표시된 다운로드가 JSON이 아닌가요?** 실제 `FileResponse`이다. 현재 FastAPI OpenAPI에 JSON `{ }`로 표기되는 것은 명시적 `responses` 스키마 부재 때문이며 실제 파일을 Blob으로 처리해야 한다.
- **왜 단계별 409가 발생하나요?** Job 상태 순서가 서버에서 강제되기 때문이다. 먼저 `GET Job`으로 확인하고 서버가 허용하는 다음 단계만 호출.
- **왜 업로드 2장이 거절되나요?** 동일 파일 바이트를 2번 제출했거나, 사진 포맷·파일 수·용량이 제한을 벗어났을 수 있다.
- **모델/Compliance가 실행됐나요?** 아니다. Mock 카피의 `compliance_checked=false`와 Mock 이미지 `mock=true`를 UI에 명시.
- **React가 다른 노트북에서 `localhost`로 서버 연결할 수 있나요?** 아니다. 승인된 reverse proxy 또는 안전한 연결 환경을 설정해야 한다.
- **비용·키 제한은?** B0는 외부 호출하지 않으며 OpenAI 키가 필요 없다. Live 호출 전 팀 예산·서버 CostGuard·멱등성·미확인 청구 처리·키 비노출을 별도 검증한다.

## 11. 검증 증거 · 갱신 규칙

| 체크 | 현재 결과 / 명령 / 한계 |
|---|---|
| Source Commit | `dev@b5e227e83e7ce0989f4573845909de66ea942da8`; 해당 tree의 `src/serving/main.py`, `job_api.py`, `job_store.py`, `mock_workflow.py` |
| 등록 HTTP | `from src.serving.main import app; app.openapi()` 실제 **11 operations** (Health 1+Job/Mock 10) |
| 실제 정상·오류 예시 | 로컬 `fastapi.testclient.TestClient(create_app(temp_storage))`: 201 upload, Mock·Approval 6 POST, 200 file downloads, 409 wrong stage, 422 duplicate, 404 missing. 별도 127.0.0.1 uvicorn + curl 전체 B0 시퀀스도 **PASS**. JSON 응답은 실제 구조 또는 발췌로 구분 |
| 참조·서빙 회귀 | `IT_TEM_KOREAN_FONT=/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf python -m pytest -q` → 이전 dev S3-A **89 PASS** (문서 PR에서 재실행·재확인 필요) |
| 계약 문서/Fixture | `python3 docs/contracts/validate_package.py`, 테스트 `tests/test_job_api.py`, `tests/test_mock_workflow.py`, `tests/test_contract_review_binding.py` |
| 문서 정합성 | 이 문서는 인간용 사용 가이드. 모델 Owner Source, 실 OpenAPI의 포괄적 response 모델·오류 선언, 브라우저 TS 클라이언트 연결·Live는 **NOT VERIFIED** |

API가 바뀌면 **실제 FastAPI 코드 → OpenAPI/Response 설명 → 테스트·Fixture → API_LIST 해당 섹션**의 순서로 확인한다. 실제 Wire 추가·변경은 [`interface_spec.md`](interface_spec.md) 및 [결정 레지스터](contracts/DECISION_REGISTER.md)의 C-ID/Owner/PM 승인 절차에 따른다. 모델·텍스트·이미지팀은 HTTP 경로를 추정하지 말고 담당 Wrapper의 Python input/output와 버전을 서빙 담당에게 공유한다. 이 문서가 OpenAPI와 어긋나면 **SSOT를 새로 정의하지 말고** 불일치·Owner·후속 PR을 기록한다.

**B0의 최종 인수 조건:** 고정 Git SHA, 실제 `/openapi.json`, 관련 pytest, 실제 브라우저 Network/HAR(민감 사진·키 제거), 상태/409/다운로드, 결과 PNG 1080×1350 및 UTF-8 캡션, Mock/Hybrid/Live 수준과 차단 사항 구분.
