# 10/26 이후 실행 로드맵 — 계약 배포 최우선

## Git/구현 기준
- 2026-10-26 origin/main=05ed2b0, origin/dev=d5d07aa (P1 PR #3 merged).
- origin/feat/p4-contract-handoff=f979331 은 P2→P3→P4A→Stage1→Stage2→Stage3 누적, **dev에는 미병합**.
- 본 계약 PR은 dev 기반 docs-only. 선행 기능 구현을 이 PR에 혼합하지 않는다.

| 순서 | 작업·담당 | 핵심 산출물 | 완료 조건 |
|---|---|---|---|
| S0 P0 | 10/26 합의·text v0.5·현재 코드 대조 / 서빙+PM | contract v0.2, 결정표, 스키마 매핑 | 확정/보류/미구현 구분 |
| S1 P0 | 공통+파트별 패키지 배포 / 서빙+PM | 공통 인덱스, 5개 역할별 가이드, Fixture 예시 | 담당자와 정확한 commit SHA 연결 |
| S2 P0 | docs-only PR / PM·전원 | dev 공식 docs/interface_spec.md | 영향 담당 리뷰·병합 |
| S3 P0 | feature 병합 / PM·서빙 | P2→P3→P4A→Stage1→Stage2→Stage3 개별 안전 PR | 각 단계 diff/중복 이력 검증·회귀 |
| S4 P0 | 서빙 Core v0.5 호환 / 서빙·텍스트·React | ProductInput/VLM/Research/AdCopy/Compliance/Prompt mapper, Job persistence | 모든 필드 보존·검수 false 승인 차단 |
| S5 P0 | Cost/Approval + Live 어댑터 연결 / 서빙·모델·PM | copy revision/hash, suboperation ledger, $10 limit, wrapper integration | 중복 과금 0, Mock/Live 독립 증거 |
| S6 P0 | React/Live E2E·품질 / 전원 | OpenAPI/TS 타입·Browser E2E·PNG·caption·QA | Contract/Mock/Live/Browser/Quality 구분 PASS |
| S7 P1 | 고도화 | 같은 제품 판별, 거절 후 편집 재승인, 합성 방식 실험 반영 | 별도 결정·버전/PR |

병렬 규칙: S0~S2 신속 완료, 텍스트·이미지는 wrapper와 Fake Fixture를 병렬 제작. 공용 main.py/JobStore/interface_spec의 변경 책임은 서빙 통합 담당. Stacked feature를 한 번에 중복 병합하거나 force push하지 않는다. GPU VM 중지·재부팅 금지, 실과금 API 기본 OFF, 총 $10 초과 시 PM 승인.

## 인수 게이트 (개별 평가)
- CONTRACT: 실제 schemas.py v0.5, adapter, HTTP OpenAPI, Fixture, TS 타입 일치
- MOCK: 기존 118 회귀와 승인/409/1080×1350 PNG/caption
- LIVE TEXT: VLM + 실제 검색/출처 + copy + Compliance
- LIVE IMAGE/COMPOSER: 생성 파일, 4:5, 제품 라벨·로고/한글 품질
- REACT BROWSER: 업로드→조사·경고→승인→다운로드
- COST & SECURITY: billable gate, $10 제한, 429/timeout/응답 유실, HTTPS/CORS/인증
- AD/IMAGE QA: 주장 근거·위반 의심 차단·사용자 확인, 외형 보존
하나의 PASS가 다른 PASS를 의미하지 않는다.

계약 변경은 version + 사유 + owner + 필드/API/비용/테스트 영향 + 호환성 + PR 리뷰 후 반영. 같은 commit SHA의 공통/파트별 패키지만 배포한다.
