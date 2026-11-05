"""실패 처리 테스트 : python -m scripts.test_failures

일부러 실패를 만들어서 각 함수가 약속대로 동작하는지 확인
- 없는 모델 이름 → OpenAI가 바로 거절 (과금 없음)
- 잘못된 API 키 → 인증 실패 (과금 없음)
- 연결 불가 주소 → 네트워크 오류 (요청이 OpenAI에 안 감)
- 입력 오류 (사진 장수, 수정 요청 길이) → 호출 전에 막힘
"""

import io
import logging

from openai import OpenAI
from PIL import Image

from src.text_generation import llm_client
from src.text_generation.copy_generator import (
    REVISION_REQUEST_MAX,
    generate_copy,
    revise_copy,
)
from src.text_generation.image_prompt_generator import (
    generate_image_prompt,
    revise_image_prompt,
)
from src.text_generation.llm_client import LLMError
from src.text_generation.product_analyzer import analyze_product
from src.text_generation.researcher import default_research, research
from src.text_generation.schemas import (
    AdCopyOutput,
    AdPlan,
    CopySet,
    ImagePromptOutput,
    ProductAnalysis,
    ProductInput,
    ResearchResult,
)

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)

BAD_MODEL = "gpt-model-does-not-exist"

PRODUCT = ProductInput(
    brand_name="테스트",
    product_name="테스트 수딩젤",
    product_category="수딩젤",
    features="촉촉한 수딩젤",
    ad_purpose="여름 홍보",
    is_functional=False,
    photo_verified=True,
    product_image_count=2,
)
ANALYSIS = ProductAnalysis(
    is_cosmetic=True,
    product_type="스킨케어",
    container_type="튜브",
    colors=["초록색"],
    label_text=[],
    mood=["청량"],
    is_transparent=False,
)
PLAN = AdPlan(target="t", concept="c", key_message="k", tone="친근한", mood=["청량"])
RESEARCH = ResearchResult(
    research=default_research(PRODUCT, ANALYSIS), research_performed=False
)
COPY = AdCopyOutput(
    plan=PLAN,
    ad_copy=CopySet(headline="헤드", subline="서브", cta="CTA"),
    caption="본문",
    hashtags=["#테스트"],
)
IMAGE = ImagePromptOutput(concept="c", prompt="밝은 배경", mood=["청량"])

ORIGINAL_CLIENT = llm_client.client
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")


def tiny_image() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buf, format="JPEG")
    return buf.getvalue()


def use_client(client: OpenAI) -> None:
    llm_client.client = client


def expect_research_fallback(name: str, **kwargs) -> None:
    try:
        r: ResearchResult = research(PRODUCT, ANALYSIS, **kwargs)
    except Exception as e:
        record(name, False, f"예외가 나면 안 됨 : {type(e).__name__}: {e}")
        return
    ok = (
        not r.research_performed
        and r.error is not None
        and r.citations == []
        and all(i.source == "AI 추론" for i in r.research.display_summary)
    )
    record(
        name,
        ok,
        f"research_performed={r.research_performed}, error={str(r.error)[:80]}",
    )


def expect_llm_error(name: str, func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except LLMError as e:
        record(name, True, f"LLMError : {str(e)[:80]}")
    except Exception as e:
        record(name, False, f"LLMError가 아닌 예외 : {type(e).__name__}: {e}")
    else:
        record(name, False, "예외가 안 남")


def expect_value_error(name: str, func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except ValueError as e:
        record(name, True, f"ValueError : {e}")
    except Exception as e:
        record(name, False, f"ValueError가 아닌 예외 : {type(e).__name__}: {e}")
    else:
        record(name, False, "ValueError가 안 남")


def expect_analysis_fallback(name: str, images: list[bytes], **kwargs) -> None:
    try:
        r = analyze_product(images, **kwargs)
    except Exception as e:
        record(name, False, f"예외가 나면 안 됨 : {type(e).__name__}: {e}")
        return
    ok = not r.analysis_succeeded and r.error is not None
    record(
        name,
        ok,
        f"analysis_succeeded={r.analysis_succeeded}, error={str(r.error)[:80]}",
    )


def main():
    images = [tiny_image(), tiny_image()]

    print("\n===== 1. 없는 모델 이름 =====")
    expect_analysis_fallback("analyze_product", images, model=BAD_MODEL)
    expect_research_fallback("research", model=BAD_MODEL)
    expect_llm_error(
        "generate_copy", generate_copy, PRODUCT, ANALYSIS, RESEARCH, model=BAD_MODEL
    )
    expect_llm_error(
        "generate_image_prompt", generate_image_prompt, PLAN, ANALYSIS, model=BAD_MODEL
    )
    expect_llm_error(
        "revise_copy",
        revise_copy,
        PRODUCT,
        ANALYSIS,
        RESEARCH,
        COPY,
        "헤드를 더 귀엽게",
        model=BAD_MODEL,
    )
    expect_llm_error(
        "revise_image_prompt",
        revise_image_prompt,
        PLAN,
        ANALYSIS,
        IMAGE,
        "더 밝게",
        model=BAD_MODEL,
    )

    print("\n===== 2. 잘못된 API 키 =====")
    use_client(OpenAI(api_key="sk-invalid-key-for-test", max_retries=0, timeout=30))
    expect_analysis_fallback("analyze_product", images)
    expect_research_fallback("research")
    expect_llm_error("generate_image_prompt", generate_image_prompt, PLAN, ANALYSIS)

    print("\n===== 3. 네트워크 연결 실패 =====")
    use_client(
        OpenAI(
            api_key="sk-test", base_url="http://127.0.0.1:9", max_retries=0, timeout=5
        )
    )
    expect_analysis_fallback("analyze_product", images)
    expect_research_fallback("research")
    expect_llm_error("generate_image_prompt", generate_image_prompt, PLAN, ANALYSIS)

    use_client(ORIGINAL_CLIENT)

    print("\n===== 4. 입력 오류 (호출 전에 막힘) =====")
    expect_value_error("analyze_product 1장", analyze_product, [images[0]])
    expect_value_error(
        "revise_copy 빈 요청", revise_copy, PRODUCT, ANALYSIS, RESEARCH, COPY, "   "
    )
    expect_value_error(
        f"revise_copy {REVISION_REQUEST_MAX + 1}자 요청",
        revise_copy,
        PRODUCT,
        ANALYSIS,
        RESEARCH,
        COPY,
        "가" * (REVISION_REQUEST_MAX + 1),
    )
    expect_value_error(
        "revise_image_prompt 빈 요청", revise_image_prompt, PLAN, ANALYSIS, IMAGE, ""
    )

    passed = sum(ok for _, ok, _ in results)
    print(f"\n===== 요약 : {passed} / {len(results)} 통과 =====")


if __name__ == "__main__":
    main()
