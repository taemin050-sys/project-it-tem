# scripts

실행 및 테스트 스크립트입니다. 프로젝트 루트에서 `python -m scripts.파일명`으로 실행합니다.

## 텍스트 생성 (src/text_generation)

> 표시가 없는 스크립트는 실제 OpenAI API를 호출하므로 비용이 발생합니다.

| 스크립트 | 내용 | 필요한 로컬 파일 |
| --- | --- | --- |
| `test_openai_connection.py` | 모델별 API 연결 확인 | - |
| `test_web_search.py` | OpenAI 웹 검색·url_citation 확인 | - |
| `test_llm_client.py` | 공통 호출 함수 확인 | - |
| `test_product_analyzer.py` | 제품 사진 분석 (제품 1종, 패턴 인자). 기본은 config 모델(luna)만, `--models`로 비교 | `data/test_products/*.jpg` |
| `test_researcher.py` | 기획 AI 조사 (제품 1종) | - |
| `test_copy_generator.py` | 기획 + 카피 (저장된 조사 결과 사용) | `outputs/research/*.json` |
| `test_image_prompt_generator.py` | 이미지 프롬프트 (저장된 카피 결과 사용) | `outputs/copy/*.json` |
| `test_pipeline.py` | 조사 → 카피 → 1차 검수 → 이미지 프롬프트 전체 흐름 (검수 차단 시 이미지 프롬프트 생략). 기본은 config 모델(luna)만, `--models`로 비교 | `data/test_products/inputs.json`, `outputs/product_analysis/*.json` |
| `test_emoji.py` | 이모티콘 정도별(없음·보통·많이) 카피 비교. 저장된 luna 조사 결과를 다시 써서 카피만 생성 (검색 비용 없음), 생성 시간·검수·글자 수·제품명·권유 경고 출력 | `data/test_products/inputs.json`, `outputs/product_analysis/*.json`, `outputs/pipeline/*_gpt-6-luna_*.json` |
| `test_revision.py` | 수정 요청 반영 확인. 카피 1개 생성 후 검수하고, 요청 5개(헤드만, 본문만, 전체 톤, 규칙 위반, 검수에서 걸린 표현 빼기)로 각각 수정 (검수 결과를 `issues`로 같이 넘김), 이미지 프롬프트 요청 2개(색, 위쪽 소품)로 수정. 고친 항목·note·검수·남은 표현·헤드·서브 단어 겹침 출력 | `data/test_products/inputs.json`, `outputs/product_analysis/*.json`, `outputs/pipeline/*_gpt-6-luna_*.json` |
| `test_compliance.py` | 1차 규제 검수 (위반 예시 + 저장된 카피), **비용 없음** | `data/test_products/inputs.json`, `outputs/product_analysis/*.json`, `outputs/pipeline/*.json` |
| `eval_compliance.py` | 1차 규제 검수 평가 (검출률·오탐률·위험도 일치율, 혼동 행렬, 놓친 위반·오탐 목록). 기본은 평가셋, 경로를 주면 그 파일로 평가, **비용 없음** | - (`src/text_generation/compliance/eval_set.jsonl`, `eval_holdout.jsonl`은 저장소에 포함) |
| `test_failures.py` | 실패 처리 확인 (없는 모델·잘못된 키·연결 실패, 수정 함수 포함) + 입력 오류(사진 장수, 빈 수정 요청, 300자 초과) 호출 전 차단, **비용 없음** | - |
| `test_highlight.py` | 검수 하이라이트 위치값 확인 + 위험도별 색 HTML 미리보기 (`outputs/highlight_preview.html`), **비용 없음** | - |
| `test_cost.py` | 예상 비용 확인 (처음 생성 사진 2장·5장, 수정 1회, 입력 오류), **비용 없음** | - |

### 실행 예시

```
python -m scripts.test_product_analyzer "제품명-*"
python -m scripts.test_product_analyzer "제품명-*" --models gpt-5.4-mini gpt-6-luna
python -m scripts.test_pipeline
python -m scripts.test_pipeline 제품키1 제품키2
python -m scripts.test_pipeline 제품키 --models gpt-5.4-mini gpt-6-luna
python -m scripts.test_emoji 제품키
python -m scripts.test_emoji 제품키 --levels 많이
python -m scripts.test_emoji 제품키 --levels 보통 많이 --effort medium
python -m scripts.test_revision 제품키
python -m scripts.test_revision 제품키 --level 많이
python -m scripts.test_compliance
python -m scripts.eval_compliance
python -m scripts.eval_compliance src/text_generation/compliance/eval_holdout.jsonl
python -m scripts.test_failures
python -m scripts.test_highlight
python -m scripts.test_cost
```

- 결과는 `outputs/` 아래 JSON으로 저장 (Git 업로드 안 함)
- `data/`, `outputs/`는 Git에 올리지 않으므로 로컬에서 준비 필요
- `test_pipeline.py`의 제품 키는 `outputs/product_analysis/`의 파일 이름 앞부분과 같아야 함
- `test_emoji.py`, `test_revision.py`는 `test_pipeline.py`를 luna로 먼저 실행해 `outputs/pipeline/`에 조사 결과가 있어야 함
- `test_emoji.py`의 `--levels`는 이모티콘 정도, `--effort`는 추론 강도 (생략하면 기본값 low)
- `test_revision.py`의 `--level`은 이모티콘 정도 (기본 보통)
- `eval_compliance.py`의 평가셋 한 줄 형식 : `{"id", "text", "expected", "source"}` + 선택 항목 `product_type`(기본 스킨케어), `is_functional`, `functional_types`, `brand_name`, `product_name`