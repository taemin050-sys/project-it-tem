# text_generation

화장품 인스타그램 피드 광고의 텍스트 파트 모듈입니다.
제품 사진 분석, 기획 AI 조사, 카피 생성, 1차 규제 검수, 이미지 배경 프롬프트 생성을 담당합니다.

## 흐름

```
제품 사진 2~5장 (bytes)
   ↓ analyze_product        → ProductAnalysisResult   (VLM, 1회 호출)
사용자 입력 + 사진 분석
   ↓ research               → ResearchResult          (웹 검색 포함, 1회 호출)
   ↓ generate_copy          → AdCopyOutput            (1회 호출)
   ↓ review_copy            → ComplianceReport        (규칙 검수, 호출 없음)
   ↓ (사용자 카피 승인)
   ↓ generate_image_prompt  → ImagePromptOutput       (1회 호출)
```

- 단계마다 OpenAI 호출 1회, 자동 재시도 없음
- 타임아웃 300초, 최대 출력 1200토큰
- 이미지 프롬프트는 카피 승인 후에만 생성 (`passed=False`면 승인할 수 없으므로 호출하지 않음, 거절 시 호출 비용 절약)

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `config.py` | `.env`에서 API 키·모델 이름·추론 강도 읽기 |
| `llm_client.py` | OpenAI 호출 공통 함수 `call_structured`, 오류 `LLMError` |
| `schemas.py` | 입출력 스키마 (Pydantic) |
| `product_analyzer.py` | 제품 사진 분석 (화장품 여부, 용기, 색, 라벨 글자) |
| `researcher.py` | 기획 AI 사전 조사 (웹 검색, 출처 추출, 화면용 요약) |
| `copy_generator.py` | 광고 기획 + 카피 (헤드·서브·CTA·본문·해시태그) |
| `image_prompt_generator.py` | 한국어 배경 이미지 프롬프트 |
| `compliance/rules.yaml` | 1차 규제 검수 금지어 사전 |
| `compliance/rule_checker.py` | 금지어 매칭, 위험 표현 위치 계산 |
| `compliance/report_builder.py` | 검수 리포트 생성 `review_copy` |

## 함수 사용법

```python
from src.text_generation.product_analyzer import analyze_product
from src.text_generation.researcher import research
from src.text_generation.copy_generator import generate_copy, copy_lengths, check_copy_limits
from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.image_prompt_generator import generate_image_prompt

analysis_result = analyze_product(images)          # images : list[bytes], 2~5장
analysis = analysis_result.analysis

research_result = research(product, analysis)      # product : ProductInput
copy = generate_copy(product, analysis, research_result)
report = review_copy(copy, product, analysis)      # report.passed가 False면 승인 차단

if report.passed:                                  # 실제 서비스는 사용자 카피 승인 후 호출
    image_prompt = generate_image_prompt(copy.plan, analysis)
```

- `analyze_product`, `research`, `generate_copy`, `generate_image_prompt`에 `model`, `reasoning_effort` 선택 인자 있음
- 기본 모델은 `gpt-6-luna` (`.env`의 `OPENAI_MODEL_TEXT`, `OPENAI_MODEL_VISION`으로 변경 가능)
- `reasoning_effort` 기본값은 `"low"` (`.env`의 `OPENAI_REASONING_EFFORT`로 변경 가능)
    - luna는 추론 강도를 지정하지 않으면 출력 토큰을 추론에 다 써서 응답이 잘림 → 기본값 유지 권장
- 이 모듈은 유료 호출 허가 여부를 따로 확인하지 않음 → 호출 전 확인은 서빙에서

## 실패 처리

| 함수 | 실패 시 |
| --- | --- |
| `analyze_product` | 예외 없음. 기본값 + `analysis_succeeded=False` + `error` (사진이 2~5장이 아니면 호출 전에 `ValueError`) |
| `research` | 예외 없음. 입력·사진 분석만으로 기본 조사 + `research_performed=False` + `error`, 조사 내용은 전부 "AI 추론" |
| `generate_copy` | `LLMError` 발생 |
| `review_copy` | 외부 호출 없음 |
| `generate_image_prompt` | `LLMError` 발생 |

- `analysis_succeeded=False`일 때 `analysis`는 임시 기본값이라 다음 단계에 쓰면 안 됨
- `research`에서 호출은 성공했지만 검색만 안 된 경우 : `research_performed=False`, `error=None`
- `error`에는 OpenAI 원문 에러가 들어감 → 로그용, 사용자 화면에는 안내 문구만 표시

## 주요 처리

**기획 AI 조사**
- 웹 검색 최대 2회 (`max_tool_calls=2`)
- 조사 내용마다 출처 표시 : 사용자 입력 / 검색 결과 / AI 추론
- 출처 URL은 OpenAI 응답의 `url_citation`에서만 추출 (utm 추적값·중복 제거)
- 인용이 없으면 "검색 결과" 표시를 "AI 추론"으로 바꿈
- 조사 텍스트 안의 링크와 출처 이름은 제거
- 제품 요약에는 사진 라벨에서 읽은 성분·효능을 넣지 않음 (카피로 넘어가지 않게)
- 사용자 입력에 치료·재생·질환명 같은 표현이 있으면 기능성 효능과 구분해 "의약품 오인 표현이라 사용 불가"로 정리
- 결과물(피드 이미지 1장)로 만들 수 없는 연출(영상, 모델, 사용 전후 비교 등)은 제안하지 않음

**카피**
- 입력하지 않은 효능·성분·용량 생성 금지, 기능성 표현 범위 준수
- 의약품 오인 표현(치료·재생·질환명 등)은 사용자 입력에 있어도 쓰지 않음
- 사진 라벨 글자는 카피 근거로 쓰지 않음
- 헤드·서브·CTA는 이미지 합성용, 본문·해시태그는 게시글 캡션용
- 이미지 위 문구 글자 수 기준 (이미지 합성 A 템플릿, 공백·문장부호 포함, 줄바꿈 제외)

| 항목 | 총 글자 수 | 한 줄 | 최대 줄 수 |
| --- | --- | --- | --- |
| 헤드 | 15자 | 15자 | 1줄 |
| 서브 | 25자 | 15자 | 2줄 |
| CTA | 10자 | 10자 | 1줄 |

- 서브가 15자를 넘으면 의미 단위로 줄바꿈(`\n`)을 넣어 두 줄로 보냄 (합성기에서 `\n` 위치로 줄을 나눔), 줄 앞뒤 공백은 코드에서 정리
- 본문은 150~250자, "~요" 체 통일, 제품명 전체는 한 번만, 권유("~해 보세요")는 마지막 문장에서 한 번, 사용 장면 포함
- 글자 수는 `copy_lengths()`로 계산 (헤드·서브·CTA는 줄바꿈 제외, `subline_lines`·`subline_line_max` 포함, 합계는 해시태그 제외)
- 헤드·서브·CTA 기준 초과, 본문 150~250자 벗어남은 `check_copy_limits()`로 확인, 로그 경고만 (차단·재생성 없음)
- 헤드 + 서브 + CTA + 본문 합계 임시 기준 400자

**이미지 프롬프트**
- 한국어 배경 프롬프트 1~2문장 (80~200자), 제품 놓일 자리(가운데) 비움, 배경 색은 용기 색과 다른 계열
- 위쪽(카피 영역)은 단순한 단색·그라데이션, 소품은 좌우·아래쪽에만 배치 (프롬프트에는 카피·문구 같은 말을 쓰지 않음)
- 금지 문구·제품 보존 문구는 넣지 않음 (이미지 쪽에서 추가)
- `concept`·`mood`는 `AdPlan` 값으로 고정

## 1차 규제 검수

식약처 「화장품 표시·광고 관리 지침」(2025.8.14) 별표 1·2와 식약처 FAQ·뉴스레터·적발 사례를 기준으로 한 규칙 검수입니다. LLM을 호출하지 않습니다.

**위험도**

| 위험도 | 기준 | 처리 |
| --- | --- | --- |
| 위반 의심 | 지침 별표 1 금지 표현 | `passed=False` → 카피 승인 차단 |
| 근거 확인 필요 | 별표 2 실증 대상, 지침 외 출처·자체 기준의 애매한 표현 | 경고만 |

**주요 규칙**

| 위험도 | 표현 예시 |
| --- | --- |
| 위반 의심 | 치료·재생·질환명(아토피, 피부염 등), 염증 완화, 시술·줄기세포, 의사 추천, 최고·1위, 일반 화장품의 기능성 표현 |
| 근거 확인 필요 | 진정, 노화·탄력 개선, 수치(OO% 개선, 30초 만에), 지속 시간(하루 종일, 12시간 지속), 비교(○○보다 촉촉, 기존 제품 대비), 임상·테스트 완료, 천연·무첨가, 인생템 |

- 영어 표현 일부 포함 (cure, regenerate, anti-inflammatory, clinically proven, dermatologist recommended, soothing 등)
- 기능성 표현(미백·주름 개선·자외선 차단 등) : 일반 화장품이면 위반 의심, 기능성 화장품이면 근거 확인 필요
- 색조 제품은 "가려준다·연출한다·채워준다"와 함께 쓰면 흔적·홍조·V라인·필러 등 허용
- 사용자가 입력한 브랜드명·제품명 안의 표현은 검수 제외
- 문장 전체 과장("한 번의 터치만으로도")처럼 금지어가 없는 표현은 규칙으로 못 잡음 → 2차 LLM 검수 예정

**ComplianceReport**

| 필드 | 내용 |
| --- | --- |
| `passed` | 위반 의심이 하나도 없으면 True |
| `issues` | 위험 표현 목록 (`field`, `text`, `start`, `end`, `category`, `risk_level`, `reason`, `suggestion`, `basis`) |
| `revised_fields` | 현재 빈 값 (단어만 바꾸면 문장이 어색해져서 LLM 재작성 단계에서 처리 예정) |
| `checklist` | 게시 전 사용자가 확인할 항목 |
| `notice` | "게시 전 최종 확인 책임은 사용자에게 있습니다" 안내 |

- `suggestion`이 None이면 삭제 권장

**하이라이트 위치값 (`start`, `end`)**
- 필드별 위치 : `field`가 `headline`이면 헤드 문구 안에서의 위치
- `text[start:end]`가 위험 표현 (`end` 미포함)
- 서브에 줄바꿈(`\n`)이 있으면 `\n`도 한 글자로 세서 위치 계산 (받은 문자열 그대로 자르면 됨)
- 해시태그는 공백으로 이어 붙인 문자열 기준 (`" ".join(hashtags)`)
- 파이썬 글자 수 기준이라 이모지가 있으면 자바스크립트 위치와 어긋날 수 있음 → 프론트에서 `Array.from(text)` 기준으로 세거나 `issue.text`로 찾기

**규칙 추가**
- `compliance/rules.yaml`에 항목 추가 (`patterns`는 정규식, 대소문자 무시)
- `rules` : 일반 규칙 / `functional_rules` : 기능성 여부에 따라 위험도가 바뀌는 규칙 / `color_exceptions` : 색조 예외
- `basis`(근거)는 사용자 화면에 그대로 보이므로 개발 메모를 쓰지 않음

## 환경 설정

`.env` (루트, Git 업로드 금지)

```
OPENAI_API_KEY=...
OPENAI_MODEL_TEXT=gpt-6-luna
OPENAI_MODEL_VISION=gpt-6-luna
OPENAI_REASONING_EFFORT=low
```

- 모델·추론 강도 줄은 생략해도 위 값이 기본으로 쓰임

필요 패키지 : `openai`(3.37.0에서 테스트), `pydantic`, `python-dotenv`, `pyyaml`, `pillow`

## 테스트

`scripts/README.md`의 텍스트 생성 항목 참고