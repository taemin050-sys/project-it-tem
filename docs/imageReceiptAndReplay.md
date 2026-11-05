# 이미지 원장·저장 결과 재조회 경계

2026-10-30 · 이미지 모듈의 오프라인 인수 범위

## 기존 원장

| 영수증 | 의미 |
|---|---|
| model, request_sha256, attempt_id, provider_request_id | 요청·시도·제공자 응답 연결 |
| complexity | 2.6 요청의 모델별 옵션. 기본 high이며 quality medium과 별개. 이전 모델 영수증에는 필드 없음 |
| state | submitting / succeeded / failed / unknown |
| usage | 제공자가 돌려준 토큰 집계. 없으면 미확인 |
| elapsed_ms | 완료된 성공/실패 시 원장 created_at→updated_at 경과시간 |
| elapsed_source | model_attempt_ledger_wall_clock; 순수 모델 처리시간 측정이 아님 |
| reservation_usd | 서버가 정한 실행 허용량. 추정 가격·청구액·제공자 가격 상한이 아님 |
| billing_status | UNRECONCILED |
| actual_cost_usd | 정산 근거가 없어 None. 0달러로 해석하지 않음 |
| error_code | 원문 오류·비밀값을 제외한 분류 코드 |

정확한 모델·단가·청구 데이터가 없으므로 토큰을 임의 가격표에 곱하지 않는다.
이 원장의 예산은 주입된 저장소의 project 범위이며, 다른 서비스가 쓰는 팀 계정 전체 비용까지 통제하지 않는다.
실제 비용 인수와 팀 계정 총예산 관리는 별도 후속이다.

## 저장된 성공 결과와 새 실행

이전에는 제공자 호출 제한을 먼저 검사해, 정상 저장된 성공 결과도 live_calls=False이면 재조회가 막혔다.
지금은 다음 순서다.

1. 기존 순수 요청 snapshot 검증과 canonical hash 계산.
2. project/job 범위의 원장 조회.
3. 같은 요청의 성공 결과이면 result 계약과 저장된 이미지 해시를 확인하고 반환.
4. 그 밖의 기존 시도는 충돌로 거절.
5. 처음 실행하는 작업만 기존 제공자 설정 검증 → 입력 asset 확인 → 예산 예약 commit → POST 순서로 진행.

따라서 동일 성공 작업은 API 호출이 비활성화됐거나 예산이 0이어도 추가 호출 없이 재사용할 수 있다.
기존 입력 fingerprint, mock/live 구분, project 경계는 유지한다. mock 결과를 실생성으로 전환하지 않는다.
새 작업의 기본 모델은 `gpt-image-2.6-sunburst`, complexity는 `high`, quality는 `medium`이다.
이전 `gpt-image-2.5-sunburst-2026-09-08` / `gpt-image-2-2026-04-21` 저장 요청은 complexity를
추가하지 않아 JSON·해시가 유지된다. 해당 작업을 `generate`로 재조회할 때는 당시 모델·quality를 명시한다.
새 기본 설정으로 같은 job을 재사용하면 `BACKEND_INPUT_CONFLICT`이며, 새 모델에는 새 job을 사용한다.
`get_receipt`는 현재 새 작업 설정과 관계없이 저장된 모델·complexity를 읽는다.
누락·손상된 저장 이미지를 새 생성으로 자동 대체하지 않는다.
submitting / unknown / failed 시도를 재시작·새 예약으로 자동 바꾸지 않는다.
호출자가 새 job ID를 발급하면 별개 시도가 되므로, 서빙은 재시도를 이유로 job을 새로 만들면 안 된다.

## 수집 재처리

`BackendImageAdapter.get_receipt(job_id, project_id=...)`는 provider를 호출하지 않는 읽기다.
관측 도구 재전송은 이 영수증과 이미 저장된 결과/승인 snapshot을 사용한다.
수집 실패 때문에 새 이미지 job을 만들거나 `generate`를 새 입력으로 재호출하지 않는다.
Langfuse/W&B SDK·수집 worker·outbox는 이 이미지 모듈의 필수 의존성이 아니다.
외부 수집기의 실제 재처리는 이 검증에서 수행하지 않았다.

## 최종 산출물과 승인

`compose_ad_png`는 승인된 것으로 공급된 이미지 bytes/hash와 전체 카피 snapshot/hash/revision을 검증한 뒤
1080×1350 PNG와 UTF-8 캡션/태그 bytes를 반환한다. 합성·다운로드 재시도를 위해 새 이미지 호출은 필요 없다.
이 함수는 승인 상태를 인증하지 않는다. 서빙이 인증·권한·승인 snapshot 저장·다운로드 endpoint를 담당한다.
해시 일치, API 성공, 로컬 PNG 생성만으로 실제 사용자 승인 또는 제품 원형 보존 PASS를 표시하지 않는다.

## 검증

- API disabled / budget0 / 둘 다: 저장 성공 재사용, 원장 불변, POST·예약0.
- 입력 hash 변경, 결과 계약 불일치, submitting/failed/unknown: 계속 차단.
- 저장 이미지 누락·손상: 대체 생성 없이 오류.
- 잘못된 snapshot: 기존 PROVIDER_INPUT_INVALID 매핑 유지.
- 다른 project 및 mock/live 전환: 결과 공유 없음.
- 실제 제공자 없이 fixture execute와 HTTP transport 금지로 backend 재조회까지 확인.

저장 결과 조회 성공은 실제 서빙 승인/다운로드 UI 인수를 대신하지 않는다.
