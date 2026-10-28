# text_generation

화장품 인스타그램 피드 광고의 텍스트 파트 모듈입니다.
제품 사진 분석부터 기획 AI 조사, 카피 생성, 이미지 배경 프롬프트 생성까지 담당합니다.

## 흐름

```
제품 사진 2~5장 (bytes)
   ↓ analyze_product        → ProductAnalysisResult   (VLM, 1회 호출)
사용자 입력 + 사진 분석
   ↓ research               → ResearchResult          (웹 검색 포함, 1회 호출)
   ↓ generate_copy          → AdCopyOutput            (1회 호출)
   ↓ generate_image_prompt  → ImagePromptOutput       (1회 호출)
```

- 단계마다 OpenAI 호출 1회, 자동 재시도 없음
- 타임아웃 300초, 최대 출력 1200토큰

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `config.py` | `.env`에서 API 키·모델 이름 읽기 |
| `llm_client.py` | OpenAI 호출 공통 함수 `call_structured`, 오류 `LLMError` |
| `schemas.py` | 입출력 스키마 (Pydantic) |
| `product_analyzer.py` | 제품 사진 분석 (화장품 여부, 용기, 색, 라벨 글자) |
| `researcher.py` | 기획 AI 사전 조사 (웹 검색, 출처 추출, 화면용 요약) |
| `copy_generator.py` | 광고 기획 + 카피 (헤드·서브·CTA·본문·해시태그) |
| `image_prompt_generator.py` | 한국어 배경 이미지 프롬프트 |
| `compliance/` | 규제 검수 (구현 예정) |

## 함수 사용법

```python
from src.text_generation.product_analyzer import analyze_product
from src.text_generation.researcher import research
from src.text_generation.copy_generator import generate_copy, copy_lengths
from src.text_generation.image_prompt_generator import generate_image_prompt

analysis_result = analyze_product(images)          # images : list[bytes], 2~5장
analysis = analysis_result.analysis

research_result = research(product, analysis)      # product : ProductInput
copy = generate_copy(product, analysis, research_result)
image_prompt = generate_image_prompt(copy.plan, analysis)
```

- 모든 함수에 `model`, `reasoning_effort` 선택 인자 있음
- 모델 기본값은 `.env`의 `OPENAI_MODEL_TEXT`, `OPENAI_MODEL_VISION`
- `gpt-6-luna` 사용 시 `reasoning_effort="low"` 필요 (없으면 추론에 출력 토큰을 다 써서 응답이 잘림)

## 실패 처리

| 함수 | 실패 시 |
| --- | --- |
| `analyze_product` | 예외 없음. 기본값 + `analysis_succeeded=False` + `error` |
| `research` | 예외 없음. 입력·사진 분석만으로 기본 조사 + `research_performed=False` + `error`, 조사 내용은 전부 "AI 추론" |
| `generate_copy` | `LLMError` 발생 |
| `generate_image_prompt` | `LLMError` 발생 |

- `analysis_succeeded=False`일 때 `analysis`는 임시 기본값이라 다음 단계에 쓰면 안 됨
- `research`에서 호출은 성공했지만 검색만 안 된 경우 : `research_performed=False`, `error=None`

## 주요 처리

**기획 AI 조사**
- 조사 내용마다 출처 표시 : 사용자 입력 / 검색 결과 / AI 추론
- 출처 URL은 OpenAI 응답의 `url_citation`에서만 추출 (utm 추적값·중복 제거)
- 인용이 없으면 "검색 결과" 표시를 "AI 추론"으로 바꿈
- 조사 텍스트 안의 링크와 출처 이름은 제거

**카피**
- 입력하지 않은 효능·성분·용량 생성 금지, 기능성 표현 범위 준수
- 사진 라벨 글자는 카피 근거로 쓰지 않음
- 글자 수는 `copy_lengths()`로 계산 (헤드 + 서브 + CTA + 본문, 해시태그 제외)
- 임시 기준 400자, 초과 시 로그 경고만 (차단·재생성 없음)

**이미지 프롬프트**
- 한국어 배경 프롬프트, 제품 놓일 자리 비움, 배경 색은 용기 색과 다른 계열
- 금지 문구·제품 보존 문구는 넣지 않음 (이미지 쪽에서 추가)
- `concept`·`mood`는 `AdPlan` 값으로 고정

## 환경 설정

`.env` (루트, Git 업로드 금지)

```
OPENAI_API_KEY=...
OPENAI_MODEL_TEXT=gpt-5.4-mini
OPENAI_MODEL_VISION=gpt-5.4-mini
```

## 테스트

`scripts/README.md`의 텍스트 생성 항목 참고