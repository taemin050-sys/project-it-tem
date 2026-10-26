# React / 권혁상 — 연동 가이드

공통 필독: ../README.md → ../../interface_spec.md → ../DECISION_REGISTER.md → ../SCHEMA_MAPPING.md

**담당 산출물:** React+Vite+TS 사용자 입력, 제품 2~5/참고 0~5장, 조사 요약+출처, 구조화된 CopySet/caption/hashtags, ComplianceReport 경고·하이라이트·대체문구·notice, 카피·이미지 승인/다운로드.

- ProductInput: brand_name?, product_name, product_category?, features, ad_purpose, is_functional, photo_verified, product_image_count, reference_image_count.
- ResearchResult.research.display_summary: text/source 3~5줄. 검색 결과는 실제 citations의 URL만 표시, AI 추론과 구분.
- AdCopyOutput: plan, ad_copy{headline,subline,cta}, caption, hashtags. 합성 필드/글자 수는 실험 전 임의 결정 금지.
- ComplianceReport: issues[].field/start/end 기준 텍스트 하이라이트, category/risk_level/reason/suggestion/basis/checklist/notice 표시. **passed=false → 승인 버튼 차단**(서버도 차단). '근거 확인 필요'는 경고.
- 기존 Feature 공개 경로(현재 dev 미병합): POST /api/v1/jobs; GET /jobs/{job_id}; GET /jobs/{job_id}/assets/{asset_id}; /mock/plan,/mock/copy,/mock/image,/mock/compose; /approvals/copy,/approvals/image; GET /artifacts/{kind},GET /capabilities; POST /ai/plan,/ai/copy (전부 /api/v1 prefix).
- multipart 반복 필드 **product_images** 및 **reference_images**. Legacy 201 Job, 직접 Job JSON, status 9개. 409 오류는 GET Job 재동기화 후 안내하고 모델 요청 자동 재실행 금지.
- dev에는 health만 있고 실 브라우저 E2E 미검증. HTTP DTO는 실제 FastAPI /openapi.json에서 생성; 텍스트 Pydantic v0.5가 즉시 공개 wire 타입이라는 가정 금지.
- 브라우저 127.0.0.1은 사용자 컴퓨터. 배포 URL/인증/CORS/HTTPS는 운영 결정 전 외부 공개 금지.

**바로 할 일:** Fixture를 이용한 입력/검수/요약 UI → Mock E2E → 승인/오류·실 다운로드 → OpenAPI/TS 동기화 → Live 화면. TS build + 브라우저 네트워크/상태·409/검수 경고/PNG+caption을 완료 증거로 제출.
보류: 카피 거절 후 편집 루프, 최종 카피 길이, 합성 방식, 신규 API 경로는 단독 확정 금지.
