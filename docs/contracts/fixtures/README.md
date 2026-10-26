# Text v0.5 JSON Fixture — 예시와 테스트의 구분

> **모든 JSON은 합성(SYNTHETIC) 데이터**이며 실제 검색 인용·광고 적법성·Live 모델 생성·현재 FastAPI HTTP 응답이 아니다.
> 사용자가 제공한 김다혜 `schemas.py v0.5` 회의 스냅샷을 기준으로 형태를 구성했다. **회의 공유 v0.5 코드 스냅샷으로 7개 Pydantic 검증 PASS**. 팀원 공식 저장소의 스키마 path/commit으로 최종 재검증은 필요하다.

| JSON | 모델·성공/실패 케이스 | 핵심 주의 |
|---|---|---|
| `product_input.json` | `ProductInput` / 제품 2장·참고0·사용권한 체크 | brand/category nullable, 사진 수 실제 파일과 검증 |
| `product_analysis.json` | `ProductAnalysis` / is_cosmetic=true | AI가 라벨을 읽은 내용은 독립 사실 확인 아님 |
| `research_result_no_search.json` | `ResearchResult` / 검색 실패 | citations 비움·`research_performed=false`·AI 추론 |
| `ad_copy_output.json` | `AdCopyOutput` / 헤드·서브·CTA/캡션·해시태그 | 단일 legacy CopyResult.text와 구조 다름 |
| `image_prompt_output.json` | `ImagePromptOutput` / 한국어 prompt·mood | `negative_prompt` 없음; 이미지팀 고정 프롬프트 |
| `compliance_report_pass.json` | `ComplianceReport` / 위반 의심 0개 | True여도 법적 적법성 인증 아님 |
| `compliance_report_block.json` | `ComplianceReport` / 위반 의심 1개 | **카피 승인 서버에서 차단**해야 하는 경계 사례 |

```bash
# 본 PR 정적 검사 (외부 유료 API 호출 0)
python3 docs/contracts/validate_package.py

# 실제 text schemas.py v0.5 모듈 경로 수령 후 모델별로 수행할 작업의 형태
# ProductInput.model_validate(json.load(open('.../product_input.json')))
# ... image/copy/compliance도 같은 패턴으로 실제 모듈에서 검증
```

**추가 필요한 Fixture:** 업로드 count mismatch, VLM is_cosmetic=false, 실제 URL citations vs 가짜 URL, 다중 `RiskLevel`, UTF-16 비BMP 이모지 하이라이트, 이미지 메타데이터 위변조, 금액 초과·429/timeout/unknown 과금, approval revision mismatch, Mock/Live 구별. 추가 Fixture는 owner 코드와 함께 작성·검증한다.

`docs/contracts/examples/frontend_legacy_upload.ts`는 **현재 `dev`에 병합되지 않은 레거시 feature**의 FormData 사용법 예시다. v0.5 입력/응답 wire 계약으로 사용하지 않는다.
