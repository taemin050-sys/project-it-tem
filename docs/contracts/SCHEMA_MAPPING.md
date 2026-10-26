# 텍스트 schemas.py v0.5 ↔ Serving API/DTO 매핑 기준

규범 소유: **텍스트/김다혜**의 실제 schemas.py v0.5. 본 문서는 서빙 호환 및 결손 필드 감사를 위한 색인이다. 기존 서빙 Pydantic provisional DTO 7개는 별도 내부 스키마이며 HTTP wire JSON을 대체하지 않는다.

| 텍스트 모델·필드 (원문 그대로) | 서빙 기존 필드/차이 | 수신·보관·변환 책임 |
|---|---|---|
| ProductInput.brand_name?, product_name | ProductFacts.brand_name,product_name 존재, nullable 의미 다름 | React 입력 → Job metadata → 텍스트 |
| ProductInput.product_category?, features, ad_purpose, is_functional, photo_verified | 기존 HTTP ai/plan은 product_facts[] 중심; **상당수 부재** | 확장 입력+검증+Pydantic/TS 타입 |
| ProductInput.product_image_count[2..5], reference_image_count[0..5] | 업로드 file count 별도, 현재 수치 저장이나 bind 규칙 불완전 | 실제 검증된 asset 목록으로 서버가 교차 검증 |
| ProductAnalysis.is_cosmetic, product_type, container_type, colors[], label_text[], mood[], is_transparent | 기존 중간 분석 단계·Job 필드 없음 | VLM 반환·버전 기록; React에 사실처럼 표시 금지 |
| ResearchResult.research.* | 기존 PlanResult/Evidence와 필드 불일치 | Lossless 저장. display_summary(text,source) React에 제공 |
| ResearchResult.citations[{title?,url}], research_performed | 기존 Evidence는 다른 분류/출처 형태 | url_citation 실제 응답을 보존; 생성 URL·AI 의견을 근거로 승격 금지 |
| AdCopyOutput.plan{target,concept,key_message,tone,mood[]} | 기존 PlanResult/CopyResult 별개 | 콘셉트·무드 정합성 검증 후 Job artifact |
| AdCopyOutput.ad_copy{headline,subline,cta}, caption, hashtags[] | 기존 CopyResult.text 단일 필드, 게시글 별도 구조 없음 | 구조 손실 금지, 사용자 승인 대상 digest 규정 |
| ImagePromptOutput{concept,prompt,mood[]} | VisualBrief.prompt_en/negative_constraints/safe_zone; mood 없음 | prompt 한국어 유지; mood 추가; 이미지팀 금지 지시 별도 |
| ComplianceReport{passed,issues[],revised_fields,checklist,notice} | 기존 CopyResult.risk_flags/compliance_checked만 존재 | 통째 저장·조회, false면 서버 승인 거절 |

### v0.5 Literal / 필드 상세 제약

- SourceType = 사용자 입력 / 검색 결과 / AI 추론 (사진 분석도 AI 추론).
- RiskLevel = 정상 / 근거 확인 필요 / 위반 의심.
- RiskCategory = 의약품 오인 / 기능성 오인 / 효능 과장 / 소비자 오인 / 수치·임상 표현 / 순위·최상급 표현 / 전문가·매체 추천 / 가상 후기 / 확정 정보 불일치 / 기타.
- CopyField = product_name / headline / subline / cta / caption / hashtags / user_text.
- ComplianceIssue = field, text, start, end, category, risk_level, reason, suggestion?, basis?, detected_by(rule|llm), auto_fixed.
- ProductType = 스킨케어/색조/바디/헤어/기타; ContainerType = 병/튜브/펌프/스포이드/자/콤팩트/스프레이/파우치/기타.
- LLM 직접 Structured Output(ProductAnalysis, ResearchOutput, AdCopyOutput, ImagePromptOutput, LLMIssue)은 필수 필드를 모두 출력(빈 배열/nullable 허용). ResearchResult·ComplianceReport는 코드 조립.
- ResearchOutput = product_summary, functional_notes, market_insights[{text,source}], similar_products[{text,source}], ad_direction, display_summary[{text,source}] 3~5줄 권장(40자 이내 설명값; 코드 enforce 여부 별도).
- ImagePromptOutput에 negative_prompt 없음; VisualBrief.negative_constraints는 레거시 호환 빈 리스트, 고정 금지문구는 이미지팀.
- User input brand_name/product_category는 nullable. ProductInput.product_image_count ge=2 le=5, reference_image_count ge=0 le=5.
- Code source 실물을 텍스트팀에서 제공받아 **스키마 검증·hash를 기록**해야 한다. 본 문서를 수동 Pydantic 정의로 역생성하여 텍스트팀 SSOT를 덮어쓰지 않는다.

### 반드시 구현할 호환성 테스트
1. ProductInput 누락/None/asset count mismatch.
2. PhotoAnalysis 데이터의 미인증 사실 표시, is_cosmetic=false 보류.
3. research_performed=false이면 citation 위조 금지 / display_summary 정보 소실 없음.
4. 승인 전 ComplianceReport.passed=false 우회 HTTP 거절 (서버).
5. AdCopyOutput 3개 텍스트 필드 + 캡션·해시태그 JSON 왕복 무손실.
6. 승인 copy revision/hash와 ImagePromptOutput/Composer 입력 일치.
7. 구 legacy HTTP 13개/API/9 status 회귀, 새 HTTP는 별도 버전·OpenAPI 검증.
