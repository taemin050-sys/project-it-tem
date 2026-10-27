# IT-TEM P3 — Mock E2E 워크플로 잠정 계약

> **PROVISIONAL / NOT APPROVED.** 이 문서는 PM·프론트엔드·텍스트·이미지 담당자의 합의 전 임시 구현 사양이다. `docs/interface_spec.md`의 확정 계약을 대체하지 않는다.

## 목적

- 10/30 1차 E2E 이전에 **단계별 생성 순서·사용자 승인 게이트·산출물 영속성·4:5 PNG**를 실제 유료 모델 없이 검증한다.
- 실제 **시장/경쟁사 리서치, AI 이미지 생성, 화장품 표시광고 법규 준수 심사, 외부 API 호출을 하지 않는다.** 모든 산출물은 Mock임을 표시한다.
- 제품/참고 이미지 2~5/0~5 검증, UUID `job_id`, 원본 에셋 다운로드 등 P2 기능을 유지한다.

## 상태 전이(단일 후보)

```text
INPUTS_VALIDATED
    │ POST .../mock/plan
    ▼
PLAN_READY
    │ POST .../mock/copy
    ▼
COPY_REVIEW_REQUIRED
    ├─ POST .../approvals/copy {"approved": false} → COPY_REJECTED (종료)
    └─ POST .../approvals/copy {"approved": true}  → COPY_APPROVED
                                                     │ POST .../mock/image
                                                     ▼
                                                IMAGE_REVIEW_REQUIRED
                                                     ├─ 거절 → IMAGE_REJECTED (종료)
                                                     └─ 승인 → IMAGE_APPROVED
                                                                 │ POST .../mock/compose
                                                                 ▼
                                                            COMPLETED
```

- 모든 잘못된 순서·중복 실행 요청은 `409 Conflict`로 차단. **재시도 시 두 번째 후보를 생성하지 않음**.
- 거절은 **이번 Mock 버전에서 종료 상태**이며 재생성·수정 워크플로는 별도 팀 계약이 필요함.
- `GET /api/v1/jobs/{job_id}`는 각 단계의 현재 상태, Mock 계획·카피, 승인 결과, 다운로드 링크를 포함.
- 서버 재시작 시 `.runtime/jobs/<job_id>/job.json`에서 상태와 산출물을 복원.

## 임시 API

| 메서드 | 경로 (모두 `/api/v1/jobs` 접두어) | Body / 효과 |
|---|---|---|
| POST | `/{job_id}/mock/plan` | `{ "brand_name":"브랜드", "product_name":"제품" }`; 실제 조사 없는 예시 기획 |
| POST | `/{job_id}/mock/copy` | Body 불필요; 카피 후보 1개 생성, 사용자 승인 전 이미지 생성 불가 |
| POST | `/{job_id}/approvals/copy` | `{ "approved": true\|false }` |
| POST | `/{job_id}/mock/image` | Body 불필요; 첫 제품 사진을 활용한 **Mock placeholder 이미지** 1080×1350 PNG |
| POST | `/{job_id}/approvals/image` | `{ "approved": true\|false }` |
| POST | `/{job_id}/mock/compose` | Body 불필요; 승인된 Mock 이미지에 한국어 카피를 합성하여 1080×1350 PNG |
| GET | `/{job_id}/artifacts/{kind}` | `plan`, `copy`, `image`, `final`, `caption` 별도 다운로드 |

- `plan.json`의 `research_performed=false`, `copy.json`의 `compliance_checked=false`, 이미지와 최종 결과의 `mock=true`는 필수 설명 표지.
- `plan`, `copy`는 JSON, `image`, `final`은 PNG, `caption`은 UTF-8 TXT.
- 서버에서 고객 임의 파일경로를 사용하지 않음. `plan`, `copy`, `image`, `final`, `caption` 등 고정 화이트리스트만 지원.
- 한국어 글꼴을 발견하지 못하면 마지막 합성 단계만 `503`으로 실패하고 상태는 `IMAGE_APPROVED`로 보존(깨진 한글 PNG를 반환하지 않음).
- 개발용 한글 글꼴은 Ubuntu `fonts-nanum` 또는 `IT_TEM_KOREAN_FONT` 환경변수로 설치 경로 지정.

## 개발용 한계·출시 금지

- 인증/인가·CSRF·레이트리밋·재시도 멱등성 키 없음. **127.0.0.1 단일 Uvicorn worker에서만 로컬 통합 검증.** 외부 공개 서버에 직접 배포 금지.
- 파일시스템 `RLock`은 동일 프로세스 내 동시성만 보장. 다중 worker/여러 인스턴스에는 DB 트랜잭션·오브젝트 스토리지로 재설계해야 함.
- Mock 이미지에는 업로드한 상품 사진을 사용하며 **생성 AI 결과가 아님**. 실제 이미지 생성 파트 계약과 혼동 금지.
- 화장품 광고 문구는 예시일 뿐 실제 표시·광고 기준, 상품 사실관계, 최종 사용자 권한 승인을 검증하지 않음.
- 서버가 재시작돼도 작업 조회는 가능하지만 VM 디스크 소실·VM 폐기 시 데이터가 사라질 수 있으므로 백업 전략 필요.

## 팀 합의 대기

1. 업로드~카피~이미지~최종 API 필드/상태 이름, 에러 응답, 승인 사용자 인증/권한
2. 실제 AI 모델 래퍼, 입력 ProductFacts 및 화장품 광고 준수 검증 게이트
3. 시장·경쟁사 조사 데이터 소스와 사실 검증·출처 보존 정책
4. 사용자가 거절했을 때 후보 재생성·수정 방식과 과금/멱등성 관리
5. 서버 공유 범위 및 스토리지(RDB/Object Store), 보존기간, 배포 보안
6. 한국어 텍스트 레이아웃·시각 품질 및 최종 인스타그램 피드 규격 확정

승인 완료 후 `docs/interface_spec.md`에 정식 반영한다.
