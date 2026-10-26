# 팀 배포 안내문 / 10·26 결정 반영 v0.2

## 전 팀원에게 보낼 공지 (계약 PR 리뷰·병합 기준)

IT-TEM 10/26 PM 참석 파트 연동 회의 결정에 따라 연동 계약 v0.2를 정리했습니다. **모든 팀원은 같은 커밋의 docs/contracts/README.md를 시작점으로 사용해 주세요.** 이전 10/26 이전 interface_spec v0.1과 M1~M5 기술 보고서는 작업 이력/검증 기준이며, 새 회의의 역할·데이터 필드 결정과 충돌하면 v0.2를 따릅니다.

먼저 공통으로 docs/interface_spec.md / docs/contracts/DECISION_REGISTER.md / docs/contracts/SCHEMA_MAPPING.md / docs/contracts/IMPLEMENTATION_PLAN.md를 확인한 뒤, 본인 패키지만 추가로 읽고 개발을 진행합니다.

- 권혁상 / React: docs/contracts/partners/FRONTEND.md
- 김다혜 / VLM·Research·Planning·Copy·Compliance: docs/contracts/partners/TEXT_AI.md
- 박지수 / Image+Composition: docs/contracts/partners/IMAGE_COMPOSER.md
- 이형기 / FastAPI·상태·비용·자산·통합: docs/contracts/partners/SERVING.md
- 이태민 / PM·QA·병합: docs/contracts/partners/PM_QA.md

**핵심 변경:** 텍스트 schemas.py v0.5 데이터 계약을 서빙이 수용, VLM 화장품 분석, 조사 요약, ComplianceReport 기반 위반 의심 승인 차단, 한국어 이미지 Prompt+mood, 이미지팀 합성 책임, 베이스라인 실험 포함 총 $10, 순차 연산/중복 호출 구분.

**아직 실험/후속 결정:** 카피 필드 활용·각 필드 글자 수·합성 방법, 동일제품/비화장품 UX, 수정 재승인 루프, 추가 HTTP 경로 이름, 최종 모델/상용 노출 정책. 미정 내용을 임의 확정하지 않습니다.

**중요:** 10/26 현재 dev에는 P1(/health)만 합쳐졌고, 기존 13개 API는 f979331 feature 브랜치에 있습니다. 실제 서빙 endpoint/TS 타입이 v0.2에 자동으로 반영됐다고 생각하지 말아 주세요. 확정 계약에 맞춰 단계별 PR·Contract/Mock/Live/React Browser E2E를 검증합니다.

발견된 차이나 변경 요청은 C-ID, 영향을 받는 필드/API, 예상 영향 범위, 담당자, PR 링크를 함께 남겨 주세요. 추가 회의 자체를 선행 조건으로 삼지 않고, 변경사항은 버전과 PR 리뷰로 반영합니다.

## 배포 시 운영자 체크
- [ ] 문서 PR 영향 담당 리뷰·dev 병합 확인
- [ ] docs/contracts/README.md 고정 GitHub URL과 commit SHA 전달
- [ ] 각 담당자에게 공통 4종 + 자신에게 해당하는 1종 전송
- [ ] schemas.py v0.5 실제 source commit·wrapper signature 수령
- [ ] P2→Stage3 feature 중복 병합 방지·비용 기본 OFF 확인
