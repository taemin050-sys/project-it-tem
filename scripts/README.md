# scripts

실행 및 테스트 스크립트입니다. 프로젝트 루트에서 `python -m scripts.파일명`으로 실행합니다.

## 텍스트 생성 (src/text_generation)

> 표시가 없는 스크립트는 실제 OpenAI API를 호출하므로 비용이 발생합니다.

| 스크립트 | 내용 | 필요한 로컬 파일 |
| --- | --- | --- |
| `test_openai_connection.py` | 모델별 API 연결 확인 | - |
| `test_web_search.py` | OpenAI 웹 검색·url_citation 확인 | - |
| `test_llm_client.py` | 공통 호출 함수 확인 | - |
| `test_product_analyzer.py` | 제품 사진 분석 (제품 1종, 패턴 인자) | `data/test_products/*.jpg` |
| `test_researcher.py` | 기획 AI 조사 (제품 1종) | - |
| `test_copy_generator.py` | 기획 + 카피 (저장된 조사 결과 사용) | `outputs/research/*.json` |
| `test_image_prompt_generator.py` | 이미지 프롬프트 (저장된 카피 결과 사용) | `outputs/copy/*.json` |
| `test_pipeline.py` | 조사 → 카피 → 1차 검수 → 이미지 프롬프트 전체 흐름 | `data/test_products/inputs.json`, `outputs/product_analysis/*.json` |
| `test_compliance.py` | 1차 규제 검수 (위반 예시 + 저장된 카피), **비용 없음** | `data/test_products/inputs.json`, `outputs/product_analysis/*.json`, `outputs/pipeline/*.json` |
| `test_failures.py` | 실패 처리 확인 (없는 모델·잘못된 키·연결 실패), **비용 없음** | - |
| `test_highlight.py` | 검수 하이라이트 위치값 확인 + 위험도별 색 HTML 미리보기 (`outputs/highlight_preview.html`), **비용 없음** | - |

### 실행 예시

```
python -m scripts.test_product_analyzer "제품명-*"
python -m scripts.test_pipeline
python -m scripts.test_pipeline 제품키1 제품키2
python -m scripts.test_compliance
python -m scripts.test_failures
python -m scripts.test_highlight
```

- 결과는 `outputs/` 아래 JSON으로 저장 (Git 업로드 안 함)
- `data/`, `outputs/`는 Git에 올리지 않으므로 로컬에서 준비 필요
- `test_pipeline.py`의 제품 키는 `outputs/product_analysis/`의 파일 이름 앞부분과 같아야 함