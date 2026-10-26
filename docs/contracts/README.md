# IT-TEM 팀 공통 연동 패키지 — 2026-10-26 / Contract v0.2

## 모든 팀원이 먼저 읽을 4개 문서 (순서 고정)

1. ../interface_spec.md — **팀 공통 공식 계약**: 제품 목표, 단계 순서, HTTP/상태/승인/비용/범위.
2. DECISION_REGISTER.md — 10/26 회의 확정 vs 보류 및 기존 C-01~C-12 대조표.
3. SCHEMA_MAPPING.md — 텍스트 schemas.py v0.5 ↔ 기존 서빙 DTO/HTTP 차이 및 필드 책임.
4. IMPLEMENTATION_PLAN.md — 브랜치 현실, 선행조건, 변경 순서, 수용 증빙.

## 담당자별 배포 파일 (공통 4종 + 자신의 1종)

- React / 권혁상: partners/FRONTEND.md
- 텍스트 AI / 김다혜: partners/TEXT_AI.md
- 이미지 AI + 합성 / 박지수: partners/IMAGE_COMPOSER.md
- 서빙·백엔드·인프라 / 이형기: partners/SERVING.md
- PM/QA / 이태민: partners/PM_QA.md

## 예제·호환 자료

fixtures/ 하위 JSON은 **텍스트 v0.5 예시 데이터**이며 실제 Live 결과 또는 current FastAPI HTTP wire 응답이 아니다. 사용자 제공 회의 텍스트의 v0.5 클래스와 함께 확인하고, 텍스트 담당자의 실제 schemas.py와 Pydantic 검증된 Fixture를 최종 교체한 뒤 freeze한다.
- 기존 7개 DTO Fixture와 OpenAPI 생성 도구는 origin/feat/p4-contract-handoff의 tests/contracts/fixtures 및 scripts/export_p4_contracts.py에 있다. **dev에는 아직 없음.**
- 현재 서버에 없는 신규 endpoint나 공통 HTTP 형태를 실구현인 것처럼 소개하지 않는다.
- 필드/계약 변경: 문서 먼저 PR 변경 + 영향 담당 리뷰 + Pydantic/JSON Schema/OpenAPI/TS/Fixture/테스트 동기화. SSOT 중복 복사로 버전 드리프트를 만들지 않는다.

**10/26 회의 결과와 PM 참석은 결정 기준이며, 이 PR의 코드·문서 병합 승인과 동일하지 않다.** 실험 대기 사안은 임의로 확정하지 않는다.
