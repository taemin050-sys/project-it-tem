# v0.5 Fixture — 모델 응답 형식 예시, **전부 합성 데이터**

**주의:** 이 JSON은 10/26 회의에 제공된 텍스트 v0.5 클래스 필드를 토대로 작성한 **참조 Fixture**이며, 텍스트 담당자가 커밋한 실제 schemas.py v0.5에 의한 최종 검증/승인 또는 Live/실제 조사 증명이 아니다. 연구 문구·브랜드·출처는 합성 데이터.

- product_input.json — React 입력의 후보 구조. 현 feature POST /jobs가 ProductInput을 받는다는 의미가 아님.
- product_analysis.json — VLM ProductAnalysis 구조 (실제 사진 분석 결과가 아님).
- research_result_no_search.json — research_performed=false/citations=[]/AI 추론의 올바른 구분.
- ad_copy_output.json — 현재 v0.5 CopySet의 3필드 + caption/hashtags. 합성 표현·글자수는 실험 대기.
- image_prompt_output.json — 한국어 prompt + mood; negative_prompt 없음.
- compliance_report_pass.json / compliance_report_block.json — passed=true/false 및 start/end. block은 서버 승인 금지 케이스.

텍스트팀 실제 schemas.py v0.5가 팀 저장소에 들어오면 해당 코드를 import하여 각 JSON을 Pydantic model_validate 한 뒤 서빙 JobStore/HTTP mapper round-trip까지 테스트할 것. 기존 7개 Serving DTO Fixture와 이름이 같지 않으며 **그대로 프론트 HTTP 응답이라고 사용하면 안 된다**.

개발용 자체 검사: python3 docs/contracts/validate_package.py (외부 모델 호출 없음).
