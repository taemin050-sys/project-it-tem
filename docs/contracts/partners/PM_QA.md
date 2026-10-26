# PM·QA / 이태민 — 배포·병합·인수 가이드

공통 필독: ../README.md → ../../interface_spec.md → ../DECISION_REGISTER.md → ../SCHEMA_MAPPING.md → ../IMPLEMENTATION_PLAN.md

**우선 실행:**
1. 문서 PR에서 10/26 회의 결론, 텍스트 schemas.py v0.5 우선, 박지수 이미지·합성 소유, 기존 기능/목표 계약 구분을 검토·병합. 팀원에게 공통 인덱스+자신의 역할 가이드를 동일 SHA로 제공.
2. dev=d5d07aa는 P1만. P2/P3/P4A/Stage1/Stage2/Stage3은 f979331 누적. PM과 서빙이 선행 단계부터 diff 검토/중복 없이 리뷰·병합.
3. 텍스트 실제 schemas.py v0.5 경로·커밋/JSON Schema/Fixture, 이미지 wrapper 경로·I/O signature·실험 결과를 수합.
4. 베이스라인 실험을 포함 **팀 합계 $10**. 초과 전에 PM 승인; 누가 무슨 모델을 얼마 사용했는지 ledger/실청구 내역 확인 후 Live 스위치 승인.
5. 합성 방식·글자 수·비화장품 처리·동일제품 판별·카피 수정 루프를 이번 회의 확정 사항으로 오인하지 않음.

**인수 구분:** CONTRACT / MOCK / LIVE TEXT / LIVE IMAGE+COMPOSITION / REACT BROWSER / COMPLIANCE·IMAGE QA / COST·SECURITY. 항목별 owner, commit SHA, 시간, 테스트 명령/증빙, PASS/FAIL/NOT_TESTED를 각각 기록. Mock 118건 PASS만으로 Live를 승인하지 않음.

**변경 규칙:** 계약 버전, C-ID, 변경 사유, 영향 API·DTO·테스트·비용·UI, 담당자 검토, PR 링크 명시 후 승인/병합. direct dev/main push·VM 중지/재시작·실결제 무승인 금지.
