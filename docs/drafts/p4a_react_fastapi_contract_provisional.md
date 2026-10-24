# IT-TEM P4A — React ↔ FastAPI + Text Provider 연동 계약 초안

> 상태: **PROVISIONAL / 팀 미승인** · 작성: 2026-10-24 · 선행: P1 `3ac2c72`, P2 `3f80c85`, P3 `2ba82ac`.
> 프론트엔드 담당자, 텍스트/이미지 모델 담당자 및 PM의 합의 후에만 `docs/interface_spec.md`로 승격한다.

## 1. 10/30 E2E 목표와 변경 불변조건

- React + Vite + TypeScript UI; FastAPI `src/serving` 단일 진입점. (과거 CONTRIBUTING의 Streamlit 예시는 폐기 대상으로 PM 협의 필요.)
- 화장품 인스타그램 4:5 단일 피드; 같은 제품 사진 **2–5장**, 참고 사진 **0–5장**.
- 기획 결과 1개 → 카피 1개 **사용자 검토/승인** → 이미지 1개 **사용자 검토/승인** → 최종 합성 1개.
- 상태·원본·단계별 아티팩트를 조회/개별 다운로드. PNG 1080×1350.
- 실 모델 연동 후에도 P3의 `/mock/*`는 회귀 테스트용으로 유지하고 `/ai/*`를 새로 분리한다.
- 실제 LLM 생성 결과는 `mock=false`이나 외부 연구 미실시 시 `research_performed=false`, 광고 심사 미실시 시 `compliance_checked=false`를 반드시 유지한다. 이미지 단계가 Mock이면 최종 출력도 Mock이다.

## 2. 기존 계약 호환 (P2/P3 변경 없음)

| Verb | Path | 성공 | 설명 |
|---|---|---:|---|
| POST | `/api/v1/jobs` | 201 | multipart `product_images`(2–5), `reference_images`(0–5) |
| GET | `/api/v1/jobs/{job_id}` | 200 | 현재 상태·아티팩트 URL·제품 메타데이터 |
| GET | `/api/v1/jobs/{job_id}/assets/{asset_id}` | 200 | 업로드 원본 다운로드 |
| POST | `/{job_id}/mock/plan` | 200 | Mock 기획 (기존) |
| POST | `/{job_id}/mock/copy` | 200 | Mock 카피 (기존) |
| POST | `/{job_id}/approvals/copy` | 200 | `{"approved":true\|false}` (기존) |
| POST | `/{job_id}/mock/image` | 200 | Mock 후보 이미지 (기존) |
| POST | `/{job_id}/approvals/image` | 200 | `{"approved":true\|false}` (기존) |
| POST | `/{job_id}/mock/compose` | 200 | Mock 최종 합성 (기존) |
| GET | `/{job_id}/artifacts/{kind}` | 200 | kind=`plan`,`copy`,`image`,`final`,`caption` (기존) |

상기 축약 경로는 모두 `/api/v1/jobs` 접두어. 업로드 응답의 UUID(hex) 및 상태 문자열은 현재 구현을 따른다.

## 3. P4A 신규 텍스트 연동 제안

| Verb | Path | Body | 응답/실패 |
|---|---|---|---|
| GET | `/api/v1/capabilities` | - | `{mode:"prototype",api_contract:"PROVISIONAL",text_provider_ready:boolean,image_provider_ready:false,mock_workflow_available:true}` |
| POST | `/api/v1/jobs/{job_id}/ai/plan` | `{brand_name:string,product_name:string,product_facts?:string[]}` | `PLAN_READY`; 공급자 미설정 503, 실패 502 |
| POST | `/api/v1/jobs/{job_id}/ai/copy` | - | `COPY_REVIEW_REQUIRED`; 공급자 미설정 503, 실패 502 |

- `product_facts`는 **사용자가 제공한 주장**이며 독립 검증한 사실이 아님. 별도 사실 검증·출처 관리가 필요.
- AI 기획: `{mock:false,research_performed:false,brand_name,product_name,audience,direction,risk_flags,product_facts_user_supplied_unverified,provider,model,disclaimer}`.
- AI 카피: `{mock:false,text,risk_flags,compliance_checked:false,provider,model,disclaimer}`.
- 텍스트 결과는 각각 기존 `plan.json`·`copy.json`으로 저장. UI는 결과를 표시하고 수동 승인 전 다음 단계를 비활성화.
- 오류: 409 잘못된 상태/중복 실행, 422 요청 검증, 502 외부 제공자 문제(상태 유지), 503 공급자 비활성화/SDK 미설치.
- 외부 기획 AI는 **실제 시장/경쟁사 검색을 수행하지 않음**. 리서치 후속 어댑터를 별도 계약으로 정의해야 함.

## 4. React 상태 기반 UX 계약

`INPUTS_VALIDATED → PLAN_READY → COPY_REVIEW_REQUIRED → COPY_APPROVED → IMAGE_REVIEW_REQUIRED → IMAGE_APPROVED → COMPLETED`.
거절: `COPY_REJECTED`, `IMAGE_REJECTED` (현재 버전 terminal; 수정/재생성은 미구현). 모든 상태 변화를 서버 GET `/jobs/{id}`로 재동기화.

- 일반 상태가 아님에도 POST 생성 호출하지 않으며, 상태 경합 시 409 응답 후 GET으로 회복.
- `artifacts[kind].download_url`로 단계별 내려받기. 브라우저의 자동 Content-Disposition 이름 사용.
- React 프록시 예시: 로컬 동일 호스트일 때 `/api`를 `http://127.0.0.1:8000`으로 Vite dev proxy. VM을 임의로 `0.0.0.0` 외부 공개하거나 무차별 CORS 추가 금지.
- 인증·인가 및 HTTPS 미구현. 서버는 개발용 localhost 전용.

## 5. 유료 OpenAI 텍스트 어댑터의 보호장치

기본 **완전 비활성화**. 의존성 `openai`가 설치돼도 네트워크 호출 없음. 아래 환경변수 모두 필요:

```
IT_TEM_TEXT_PROVIDER=openai
IT_TEM_ENABLE_BILLABLE_TEXT_CALLS=YES
IT_TEM_TEXT_MODEL=<team-approved-model-id>
OPENAI_API_KEY=<secret: VM local env only>
```

- 요청당 최대 출력 600 토큰, timeout 30s, 자동 SDK 재시도 0, Responses `store=false`.
- 동일 작업/단계의 동시 과금 요청 차단(단일 프로세스 메모리 잠금); 모든 오류 시 P3 상태 불변.
- 네트워크 타임아웃 시 **업스트림에서 이미 과금됐을 가능성**이 있으며, 현 버전은 분산 멱등성을 제공하지 않는다. 재시도 전에 운영자 확인 필수.
- 모델 공급자는 프롬프트 지시만으로 화장품 표시광고 법률 준수나 제품 사실을 보장하지 못한다. 검증 게이트 추후 추가.
- 오픈API는 아직 내부 목업·임시 계약 상태. 팀 확정 전 프론트엔드 코드에 하드코딩된 영속 계약으로 간주 금지.

## 6. 팀 승인 결정 사항

1. React 담당자: API root, snake_case/JSON, upload field name, 상태·에러 전이·다운로드 UX 승인
2. 텍스트 담당자: 입력 ProductFacts/출처/검색 방식, 기획·카피 응답 스키마, 프롬프트·모델 아이디·예산 승인
3. 이미지 담당자: 이미지 후보 생성 입력·제품 보존 프로토콜, OpenAI Image API 래퍼 및 생성 메타데이터
4. PM: API 버전·보안/인가·과금 한도·PR 병합·`docs/interface_spec.md` 승격 승인
5. 제품 담당자: 이미지 중간 승인 UX, 거절 시 재생성 정책, 광고 법규·사실 검증 책임 분리

## 7. P4B/P4C 이후

P4B 모델팀 API 래퍼 연동 및 증거 기반 광고 기획 → P4C 이미지 API 래퍼·제품 보존 평가 → P4D 합성 품질 검증(글꼴, 줄바꿈, 안전 영역, 대비, 브랜드 로고, 한글 특수문자, 텍스트 오버플로) → React 통합 평가.
