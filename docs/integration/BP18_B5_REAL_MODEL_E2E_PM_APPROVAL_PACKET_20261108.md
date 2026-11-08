# IT-TEM BP18 B5 — 실제 AI 모델 E2E 실행 승인 요청 및 기술 게이트

작성 기준: 2026-11-08 KST. **상태: REQUEST_FOR_APPROVAL / ZERO PAID CALLS IN B.** 제품 릴리스 승인이 아님.

## PM에게 승인받을 실행 범위

| 구분 | 제안 | 승인 상태 |
|---|---|---|
| 타깃 | 격리된 Track B 전용 GCP, 기존 Live/A/QA 변경 금지 | PENDING |
| 지정 사용자(Actor) | `bp18_b_pm`만, PM 개인 코드 사용 | PENDING |
| Text/Vision 모델 | `gpt-6-luna` | PENDING (계정 접근 검증 필요) |
| Image 모델 | `gpt-image-2.6-sunburst`, medium, high complexity | PENDING (계정 접근 검증 필요) |
| 출력 | 3:4 / 4:5 / 9:16 × composed / freeform, 총 6개 | PENDING |
| 가격 정책 | `MONITOR_ONLY`, 기존 Owner Attempt/Receipt/Usage/UNKNOWN 그대로 | 유지 (하드 캡 아님) |
| 비용 승인 요청 | **최대 미화 $10의 제한된 E2E 실험**; PM이 예산과 호출 수를 명시 승인 | **미승인** |
| 모델 이미지 유효 요청 | 최초 6회, 각 조합 정확히 1회; 불확실 결제/실패 시 자동 재시도 0회 | 승인 필요 |
| 텍스트 파이프라인 | 6개 Job의 분석→조사→카피→Prompt, 승인 과정 중 수정 재호출은 별도 예산 승인 | 승인 필요 |
| 차단 | 승인 없는 Provider API 호출, 모델 자동 폴백, 다른 Actor 호출, 재시도/Unknown 재호출, Fixture를 실모델로 표기 | 절대 금지 |

### 근거 기반 비용 추정 (청구액·상한이 아님)

- 실제 실행 전 비과금 산출: Text 2장/Job 예상 `$0.02357`, 6 Jobs 합계 `$0.14142` (11/4 평균 토큰 기준이며 검색 최대 2회 포함).
- Composed Image 과거 GCP 실제 성공 표본 10건을 현행 단가로 재계산한 비율별 중앙값: 3:4 `$0.075700` (n=2), 4:5 `$0.093879` (n=5), 9:16 `$0.065562` (n=3). 3장 합계 참고치 `$0.235141`.
- 그러므로 6 Job Text + 3 Composed Image 합계 관측 기반 **참고**는 약 `$0.376561`; **Freeform 3회는 일치하는 실사용 토큰 표본이 없어 금액 불명**, 실제 LLM 재검수·재생성·실패 요청 비용 별도.
- 이미지 2.6 Sunburst 표준 단가 소스: https://developers.openai.com/api/docs/pricing ; 이미지 API 지원 모델: https://developers.openai.com/api/reference/resources/images/methods/generate . 프로젝트의 승인·모델 접근·계정 실사용 한도는 API 호출 없이 확정할 수 없음.
- `MONITOR_ONLY`는 모니터링이지 실행 차단형 결제 상한이 아님. **PM이 OpenAI 플랫폼 사용량 대시보드와 가능한 청구 한도/경고를 별도 관리하고, 최초 1건 결과의 Receipt·Usage를 확인한 뒤 다음 실행을 허용**해야 함.

## 실제 실행 순서와 중단 조건

1. PM의 모델/Actor/총 최대비용/실행일/6건 회수 명시적 승인 확인. 팀 프로젝트 Owner가 승인한 제품 이미지 사용권·모델 공유 범위 확인.
2. Text Owner의 1차 규칙 검수와 LLM 2차 규제 검수의 적용 여부를 별도 표기. **F09가 아직 완료되지 않았다면 본 E2E는 정식 광고 품질 인수가 아니라 제한된 실모델 시험**으로만 기록.
3. 우선 B의 web queue와 worker를 **서로 다른 프로세스**에서 승인 Actor에 한해 활성화. 웹에는 API 키를 배포하지 않고 Worker 전용 0600 키 로더를 사용. 백엔드가 이미 지원하는 실행 Gate를 그대로 준수.
4. 1개 대표 조합 4:5 Composed → 승인→실제 모델 Image→최종 PNG/Caption SHA 및 Receipt/Usage/BILLING_UNKNOWN 검증. 모든 호출 결과 정상·소진 한도 확인 전 2번째 호출 금지.
5. 3:4 Composed, 9:16 Composed, 3:4 Freeform, 4:5 Freeform, 9:16 Freeform 순서. 모드/비율/JobID/승인/Owner 모델 ID/Usage/원본과 final SHA를 분리 저장.
6. Owner/PM 실제 브라우저로 PNG·Caption 다운로드, 360/390 px Korean 가독성, 브랜드/용기/라벨·CTA/Head/Sub 구조, 책임 분리와 실제 모델 출처 확인.
7. **즉시 중단**: 미확정 비용, 승인 외 Actor, receipt 모호/UNKNOWN, 모델 요청 실패 또는 Provider Attempt 불일치, 원본·브랜드 왜곡, 정책 재검수 미완료, 이미지 출처 불명, 예상치 초과. 자동 재시도 금지.

## 6개 실모델 조합 인수 체크 (모든 항목 현재 PENDING)

| 비율 | Composed | Freeform |
|---|---|---|
| 3:4 | 모델 생성+CTA/Head/Sub+SHA 검증 필요 | 모델 자체 문자 렌더링·한국어+SHA 검증 필요 |
| 4:5 | **이미지 내부 CTA 필수**+원본 보호+SHA 검증 필요 | 원본·라벨·브랜드+한국어+SHA 검증 필요 |
| 9:16 | **9:16 CTA 정책 PM 결정 전 완성 인수 불가** | CTA 정책·한국어 정확성·SHA 검증 필요 |

각 조합 별 최소 산출물: Job ID / Input SHA / Copy SHA / Review SHA / Policy Epoch / Approval SHA / Owner 이미지 원본·모델 Receipt SHA / Attempt ID / Usage / 이미지 후보 SHA / Final PNG SHA / Caption SHA / 실제 다운로드 SHA / Browser screenshots / Text/Image Owner & PM 평가.

## PM이 승인해야 할 결정

**(1)** 테스트 총비용 최대 승인액(제안 USD $10, hard cap 아님), **(2)** 정확한 모델 ID와 모델 사용권, **(3)** Actor `bp18_b_pm` 지정, **(4)** 1회 성공 후 2~6회 순차 실험을 허용할지, **(5)** 9:16 이미지 CTA 정책, **(6)** 상업적 이미지·한글 폰트 이용허락.

서면 승인 전 기본 설정은 유지: `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_LIVE_EXECUTION_APPROVED=NO`, `IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO`. 실제 API 키는 웹이나 문서·Git에 절대 포함하지 않음.
