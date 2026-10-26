# 텍스트 AI / 김다혜 — 연동 가이드

공통 필독: ../README.md → ../../interface_spec.md → ../DECISION_REGISTER.md → ../SCHEMA_MAPPING.md

**소유:** 텍스트 schemas.py v0.5, OpenAI API wrapper, VLM 제품 사진 분석, 텍스트 모듈 내부 웹 검색·기획·카피·Compliance·이미지 프롬프트.
- 입력 ProductInput + **서버 검증을 통과한 제품 2~5장의 바이트**. 사용자 이미지 내용은 검색으로 확인된 사실 아님.
- ProductAnalysis: is_cosmetic, product_type,container_type,colors,label_text,mood,is_transparent. is_same_product는 고도화.
- ResearchOutput: product_summary,functional_notes,market_insights,similar_products,ad_direction,display_summary. display_summary는 별도 유료 호출 없이 3~5줄 생성.
- ResearchResult: 코드에서 ResearchOutput + 실제 OpenAI url_citation에서 title/URL 추출 + research_performed 조립. 검색 실패 시 false, 조사 내용을 AI 추론으로 구분. AI가 쓴 URL 사용 금지.
- AdCopyOutput: plan(타깃·콘셉트·핵심메시지·톤·무드), ad_copy(headline/subline/cta), caption, hashtags.
- ComplianceReport: 1차 사전/정규식, 2차 LLM. issue 위치 field/start/end, 종류·위험도·근거·대체문구·auto_fixed 및 사용자 책임 고지. '위반 의심' 하나라도 있으면 passed=false.
- ImagePromptOutput: concept, **한국어 prompt**, mood. 이미지팀은 별도 고정 negative/보존 문구를 추가. negative_prompt는 v0.5에 없음.
- 호출 설정 합의 초기값 timeout 300초, output 1200 tokens, SDK retry 0; 복수 **서로 다른 순차 내부 연산**과 동일 요청 중복을 식별하도록 호출 목적/시도 metadata 협력. $10 팀 통합 실험 예산 준수.

**인계 필수 산출물:** 실제 schemas.py v0.5 경로·SHA, import 가능한 모듈, v0.5 JSON Schema, 정상/검색실패/화장품아님/위반의심/근거확인/실제 citations Fixture, Fake wrapper+민감정보 제거 Live 로그, 단계별 호출/usage/error 정보. 모델 프롬프트·품질은 담당, JobStore·승인·비용 차단은 서빙.
