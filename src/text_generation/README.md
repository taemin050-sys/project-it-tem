# text_generation

화장품 인스타그램 피드 광고의 텍스트 파트 모듈입니다.
제품 사진 분석, 기획 AI 조사, 카피 생성, 1차 규제 검수, 이미지 배경 프롬프트 생성, 수정 요청 반영, 예상 비용 계산을 담당합니다.

## 흐름

```
(생성 전) estimate_generation_cost  → CostEstimate      (호출 없음, 예상 비용 안내)

제품 사진 2~5장 (bytes)
   ↓ analyze_product        → ProductAnalysisResult   (VLM, 1회 호출)
사용자 입력 + 사진 분석
   ↓ research               → ResearchResult          (웹 검색 포함, 1회 호출)
   ↓ generate_copy          → AdCopyOutput            (1회 호출)
   ↓ review_copy            → ComplianceReport        (규칙 검수, 호출 없음)
   ↓ (카피 수정 요청 시) revise_copy → CopyRevisionOutput → review_copy 다시
   ↓ (사용자 카피 승인)
   ↓ generate_image_prompt  → ImagePromptOutput       (1회 호출)
   ↓ (배경 수정 요청 시) revise_image_prompt → ImagePromptRevisionOutput
```

- 단계마다 OpenAI 호출 1회, 자동 재시도 없음
- 타임아웃 300초, 최대 출력 1200토큰 (카피 생성·수정은 4000토큰, 추론 강도를 올려도 잘리지 않게)
- 이미지 프롬프트는 카피 승인 후에만 생성 (`passed=False`면 승인할 수 없으므로 호출하지 않음, 거절 시 호출 비용 절약)
- 수정 요청은 저장된 조사 결과를 다시 쓰므로 검색을 다시 하지 않음

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `config.py` | `.env`에서 API 키·모델 이름·추론 강도 읽기 |
| `llm_client.py` | OpenAI 호출 공통 함수 `call_structured`, 오류 `LLMError` |
| `schemas.py` | 입출력 스키마 (Pydantic) |
| `product_analyzer.py` | 제품 사진 분석 (화장품 여부, 용기, 색, 라벨 글자) |
| `researcher.py` | 기획 AI 사전 조사 (웹 검색, 출처 추출, 화면용 요약) |
| `copy_generator.py` | 광고 기획 + 카피 (헤드·서브·CTA·본문·해시태그), 카피 수정 |
| `image_prompt_generator.py` | 한국어 배경 이미지 프롬프트, 프롬프트 수정 |
| `cost.py` | 예상 비용 계산 (생성 전 안내용, 호출 없음) |
| `compliance/rules.yaml` | 1차 규제 검수 금지어 사전 |
| `compliance/rule_checker.py` | 금지어 매칭, 위험 표현 위치 계산 |
| `compliance/report_builder.py` | 검수 리포트 생성 `review_copy` |

## 함수 사용법

```python
from src.text_generation.product_analyzer import analyze_product
from src.text_generation.researcher import research
from src.text_generation.copy_generator import (
    generate_copy, revise_copy, copy_lengths, check_copy_limits, check_copy_content,
)
from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.image_prompt_generator import generate_image_prompt, revise_image_prompt
from src.text_generation.cost import estimate_generation_cost, estimate_revision_cost, format_usd

# 생성 전 예상 비용
estimate = estimate_generation_cost(photo_count=len(images))
print(format_usd(estimate.total_usd))              # 예 : "약 $0.024"

analysis_result = analyze_product(images)          # images : list[bytes], 2~5장
analysis = analysis_result.analysis

research_result = research(product, analysis)      # product : ProductInput
copy = generate_copy(product, analysis, research_result)
report = review_copy(copy, product, analysis)      # report.passed가 False면 승인 차단

# 카피 수정 요청 (이전 카피·조사 결과는 서빙에서 임시 저장)
revision = revise_copy(product, analysis, research_result, copy, "헤드를 더 귀엽게 바꿔줘")
copy = revision.revised                            # revision.changed_fields, revision.note
report = review_copy(copy, product, analysis)      # 수정 후 다시 검수

if report.passed:                                  # 실제 서비스는 사용자 카피 승인 후 호출
    image_prompt = generate_image_prompt(copy.plan, analysis)

    # 배경 수정 요청
    image_revision = revise_image_prompt(copy.plan, analysis, image_prompt, "배경을 더 밝게")
    image_prompt = image_revision.revised          # image_revision.note
```

- `analyze_product`, `research`, `generate_copy`, `revise_copy`, `generate_image_prompt`, `revise_image_prompt`에 `model`, `reasoning_effort` 선택 인자 있음
- 기본 모델은 `gpt-6-luna` (`.env`의 `OPENAI_MODEL_TEXT`, `OPENAI_MODEL_VISION`으로 변경 가능)
- `reasoning_effort` 기본값은 `"low"` (`.env`의 `OPENAI_REASONING_EFFORT`로 변경 가능)
    - luna는 추론 강도를 지정하지 않으면 출력 토큰을 추론에 다 써서 응답이 잘림 → 기본값 유지 권장
    - `generate_copy`·`revise_copy`는 인자를 넘기지 않으면 이모티콘 정도별 기본값(`LEVEL_REASONING_EFFORT`)을 쓰고, 비어 있으면 위 기본값을 씀 (현재 비어 있음, medium은 3배 느리고 품질 차이가 없어서)
- 이 모듈은 유료 호출 허가 여부를 따로 확인하지 않음 → 호출 전 확인은 서빙에서

**고도화 입력값 (`ProductInput`, 둘 다 기본값이 있어 기존 입력과 호환)**

| 필드 | 값 | 기본값 | 쓰이는 곳 |
| --- | --- | --- | --- |
| `functional_types` | 기능성 종류 목록 (예: `["자외선차단"]`, 화장품법 시행규칙 제2조 10종) | `[]` | 조사·카피의 표현 범위, 검수 위험도 |
| `emoji_level` | `"없음"` / `"보통"` / `"많이"` | `"없음"` | 게시글 본문의 이모티콘·말투 |

- `functional_types`를 하나라도 고르면 `is_functional`은 자동으로 True

**수정 요청 결과**

| 스키마 | 필드 | 내용 |
| --- | --- | --- |
| `CopyRevisionOutput` | `revised` | 수정 요청을 반영한 카피 전체 (`AdCopyOutput`) |
| | `changed_fields` | 실제로 바뀐 항목 (`plan`, `headline`, `subline`, `cta`, `caption`, `hashtags` 중) |
| | `note` | 요청 중 반영하지 못한 부분과 이유 한 문장 (화면에 그대로 표시, 모두 반영했으면 None) |
| `ImagePromptRevisionOutput` | `revised` | 수정 요청을 반영한 이미지 프롬프트 (`ImagePromptOutput`) |
| | `note` | 요청을 바꿔서 반영했거나 뺀 부분과 이유 한 문장 (모두 반영했으면 None) |

## 실패 처리

| 함수 | 실패 시 |
| --- | --- |
| `analyze_product` | 예외 없음. 기본값 + `analysis_succeeded=False` + `error` (사진이 2~5장이 아니면 호출 전에 `ValueError`) |
| `research` | 예외 없음. 입력·사진 분석만으로 기본 조사 + `research_performed=False` + `error`, 조사 내용은 전부 "AI 추론" |
| `generate_copy` | `LLMError` 발생 |
| `revise_copy` | `LLMError` 발생 (요청이 비었거나 300자를 넘으면 호출 전에 `ValueError`) |
| `review_copy` | 외부 호출 없음 |
| `generate_image_prompt` | `LLMError` 발생 |
| `revise_image_prompt` | `LLMError` 발생 (요청이 비었거나 300자를 넘으면 호출 전에 `ValueError`) |
| `estimate_generation_cost` | 외부 호출 없음 (사진이 2~5장이 아니거나 단가표에 없는 모델이면 `ValueError`) |
| `estimate_revision_cost` | 외부 호출 없음 (단가표에 없는 모델이면 `ValueError`) |

- `analysis_succeeded=False`일 때 `analysis`는 임시 기본값이라 다음 단계에 쓰면 안 됨
- `research`에서 호출은 성공했지만 검색만 안 된 경우 : `research_performed=False`, `error=None`
- `error`에는 OpenAI 원문 에러가 들어감 → 로그용, 사용자 화면에는 안내 문구만 표시
- 수정 함수가 실패하면 이전 카피·프롬프트를 그대로 두고 다시 요청하게 하면 됨 (처음으로 돌아갈 필요 없음)

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
- 입력하지 않은 효능·성분·용량 생성 금지, 기능성 표현 범위 준수 (기능성 종류를 골랐으면 그 종류의 효능만)
- 의약품 오인 표현(치료·재생·질환명 등)은 사용자 입력에 있어도 쓰지 않음
- 사진 라벨 글자는 카피 근거로 쓰지 않음
- 헤드·서브·CTA는 이미지 합성용, 본문·해시태그는 게시글 캡션용
- 이미지 위 문구 글자 수 기준 (이미지 합성 A 템플릿, 세 비율 공통, 공백·문장부호 포함, 줄바꿈 제외)

| 항목 | 총 글자 수 | 한 줄 | 최대 줄 수 |
| --- | --- | --- | --- |
| 헤드 | 15자 | 15자 | 1줄 |
| 서브 | 25자 | 15자 | 2줄 |
| CTA | 10자 | 10자 | 1줄 |

- 서브가 15자를 넘으면 의미 단위로 줄바꿈(`\n`)을 넣어 두 줄로 보냄 (합성기에서 `\n` 위치로 줄을 나눔), 줄 앞뒤 공백은 코드에서 정리
- 화면에서는 기준을 넘으면 다음 버튼을 막고 수정하게 함 (자바스크립트는 `Array.from(text.replace(/\n/g, "")).length`로 세면 파이썬 기준과 같음)
- 본문 규칙
    - 길이 : 없음·보통 250~400자, 많이 250~350자 (줄바꿈·이모티콘 포함), 처음 생성 때 250자보다 짧아지지 않게 지시 (수정 요청에서 짧게 해 달라고 하면 그보다 짧아져도 반영)
    - 제품명 전체는 브랜드명을 포함해 입력 그대로 한 번만, 이후엔 제품 종류에 맞게 짧게 부름 ("이 마스크", "이 크림")
    - 권유("~해 보세요")는 없음·보통 2번까지, 많이는 쓰지 않고 감탄으로 마무리
    - 사용 장면 포함, 같은 내용 반복 금지
    - 길이가 부족하면 공감 상황·사용 장면·광고 목적 안내로 채움 (새 효능·성분은 만들지 않음)
    - 입력과 관계없는 피부 고민(번들거림, 트러블 등)은 쓰지 않음 (제품이 해결해 주는 것처럼 읽혀서)
    - 이벤트는 입력에 있는 내용만 한 문장으로, 기간·할인율·혜택이나 "자세한 내용은 ~에서 확인"은 만들지 않음
- 글자 수는 `copy_lengths()`로 계산 (헤드·서브·CTA는 줄바꿈 제외, `subline_lines`·`subline_line_max`·`caption_emojis` 포함, 합계는 해시태그 제외)
- 확인 함수 (로그 경고만, 차단·재생성 없음)
    - `check_copy_limits(output, emoji_level)` : 헤드·서브·CTA 기준 초과, 본문 길이 벗어남, 이모티콘 개수가 정도와 맞지 않음
    - `check_copy_content(output, product)` : 본문에 제품명 전체가 없음, 권유 표현("~보세요", "~주세요", "~하세요") 개수 초과
- 헤드 + 서브 + CTA + 본문 합계 임시 기준 500자

**이모티콘 (`emoji_level`)**

| 정도 | 본문 모양 | 말투 | 이모티콘 |
| --- | --- | --- | --- |
| 없음 | 3문단, 한 문단 2~3문장 | 차분한 "~요" 체 | 0개 |
| 보통 | 짧은 줄 (25자 안팎, 한 줄에 한 문장 이하), 2~3줄마다 빈 줄, 빈 줄을 뺀 12줄 이상 | 따뜻한 "~요" 체 | 문단 끝 0~1개, 전체 3~5개 |
| 많이 | 짧은 줄 (20자 안팎), 질문형 첫 줄 → "바로 (제품명) ✨" → 특징 목록 → 공감 → 감탄 마무리 | "~요"와 가벼운 반말, "~다구요", "~잖아?", ㅎㅎ, ㅠㅠ | 거의 모든 줄, 두 개 붙여 쓰기, ʚ♡ɞ |

- 이모티콘은 게시글 본문에만 넣음. 헤드·서브·CTA·해시태그에 들어오면 코드에서 제거 (이미지 위 문구에 이모티콘이 들어가지 않게)
- 이모티콘은 정해 둔 목록(`EMOJI_PALETTE`)을 기본으로 쓰고, 제품·계절에 어울리는 것(예: 당근 패드에 🥕, 겨울에 ❄️)은 1~2개 더 허용
- 보통·많이의 예시와 좋은 예·나쁜 예는 가상 제품(△△ 워터 젤 크림, □□ 립 오일)이라 실제 제품 정보가 섞이지 않음
- 줄은 문장 끝이나 쉼표 뒤에서만 바꾸고, 꾸미는 말과 꾸밈 받는 말 사이에서는 끊지 않음
- 말투가 가벼워져도 효능 표현 규칙과 검수는 같음

**수정 요청 (카피·이미지를 거절해도 처음으로 돌아가지 않게)**
- 사용자는 수정 요청을 문장으로 입력 (300자 이내, 예: "헤드를 더 귀엽게", "배경을 더 밝게")
- 카피 (`revise_copy`)
    - 모델이 고친 항목을 `changed_fields`로 함께 내보내고, 목록에 없는 항목은 코드가 이전 값으로 되돌림 (헤드만 바꿔 달라고 했는데 본문까지 바뀌지 않게)
    - `changed_fields`는 실제로 바뀐 항목만 남김 → 화면에서 "헤드가 바뀌었어요"처럼 표시할 때 사용 가능
    - 말투·이모티콘 양·본문 길이 요청은 반영 ("본문을 짧게"는 최소 길이보다 짧아져도 반영, 경고 로그만 남음), 효능 규칙과 헤드·서브·CTA 글자 수는 요청보다 우선
    - 규칙과 부딪히는 요청(예: "피부 재생 효과 강조")은 반영하지 않고 `note`에 이유를 씀
    - 결과는 `review_copy`로 다시 검수해야 함
- 이미지 프롬프트 (`revise_image_prompt`)
    - 배치 규칙(위쪽 단순, 가운데 비움, 사람·글자 금지)은 요청보다 우선
    - 규칙과 부딪히는 요청도 규칙 안에서 최대한 살려 반영 (예: "위쪽에 꽃" → 꽃을 좌우·아래쪽에 배치), `note`에는 실제로 한 것만 씀
- 요청 안에 규칙을 무시하라는 내용이 있어도 수정 요청으로만 읽음
- "요청 없이 다시 만들기"는 `generate_copy`·`generate_image_prompt`를 다시 호출하면 됨

**이미지 프롬프트**
- 한국어 배경 프롬프트 1~2문장 (80~200자는 대략적인 기준, 서빙 입력 규격은 3,000자), 제품 놓일 자리(가운데) 비움, 배경 색은 용기 색과 다른 계열
- 위쪽(카피 영역)은 단순한 단색·그라데이션, 소품은 좌우·아래쪽에만 배치 (프롬프트에는 카피·문구 같은 말을 쓰지 않음)
- 사진 비율(3:4, 4:5, 9:16)은 이미지 API의 크기 설정으로 정하므로 프롬프트에 넣지 않음
- 금지 문구·제품 보존 문구는 넣지 않음 (이미지 쪽에서 추가)
- `concept`·`mood`는 `AdPlan` 값으로 고정

**예상 비용 (`cost.py`)**
- 생성 전에 보여 주는 예상값 (실제 호출 없음), 텍스트 파트만 (이미지 생성 비용은 이미지 파트에서 따로 계산), 단위 달러
- 단가 × 단계별 평균 토큰 (11/4 gpt-6-luna 측정값을 넉넉하게 올림), 웹 검색은 최대치 2회로 계산
- 단가 (1M 토큰당 입력 / 출력) : luna $0.10 / $0.50, mini $0.75 / $4.50, 웹 검색 1회 $0.01

| 함수 | 내용 | luna 예상 |
| --- | --- | --- |
| `estimate_generation_cost(photo_count)` | 처음 생성 (사진 분석 + 조사 + 카피 + 이미지 프롬프트) | 약 $0.024 (대부분 웹 검색 $0.02) |
| `estimate_revision_cost("copy")` | 카피 수정 1회 추가 비용 | $0.001 미만 |
| `estimate_revision_cost("image_prompt")` | 이미지 프롬프트 수정 1회 추가 비용 | $0.001 미만 |
| `format_usd(amount)` | 화면 표시용 문자열 ("약 $0.024", "$0.001 미만") | - |

- `CostEstimate` : `model`, `steps`(단계별 금액), `total_usd`
- 프롬프트가 크게 바뀌면 `STEP_TOKENS`를 다시 측정해야 함

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
| 근거 확인 필요 | 진정, 노화·탄력 개선, 수치(OO% 개선, 30초 만에), 지속 시간(하루 종일, 12시간 지속), 비교(○○보다 촉촉, 기존 제품 대비), 임상·인체적용시험, 테스트 완료·테스트도 완료·시험 통과, 천연·무첨가, 인생템 |

- 영어 표현 일부 포함 (cure, regenerate, anti-inflammatory, clinically proven, dermatologist recommended, soothing 등)
- 기능성 표현(미백·주름 개선·자외선 차단 등)
    - 일반 화장품 : 위반 의심
    - 기능성 + 종류 선택(`functional_types`) : 고른 종류는 근거 확인 필요, 고르지 않은 종류는 위반 의심
    - 기능성 + 종류 미선택 : 모두 근거 확인 필요
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
- 파이썬 글자 수 기준이라 이모지가 있으면 자바스크립트 위치와 어긋날 수 있음 → 프론트에서 `Array.from(text)` 기준으로 세거나 `issue.text`로 찾기 (이모티콘 "보통"·"많이"는 본문에 이모지가 많으니 특히 주의)

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