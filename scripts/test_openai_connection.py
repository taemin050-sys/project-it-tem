from openai import OpenAI

from src.text_generation.config import OPENAI_API_KEY
from src.text_generation.schemas import CopySet

client = OpenAI(api_key=OPENAI_API_KEY)

# 1M 토큰당 (입력, 출력) 달러 — 2026-10-25 공식 가격 페이지 기준
PRICES = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-6-luna": (0.10, 0.50),
}
PROMPT = "수분 크림 인스타 광고 카피를 헤드라인, 서브라인, CTA로 써줘."

for model, (p_in, p_out) in PRICES.items():
    print(f"\n===== {model} =====")
    try:
        res = client.responses.parse(model=model, input=PROMPT, text_format=CopySet)
        u = res.usage
        cost = u.input_tokens / 1e6 * p_in + u.output_tokens / 1e6 * p_out
        print(res.output_parsed)
        print(f"토큰 {u.input_tokens} in / {u.output_tokens} out, 약 ${cost:.5f}")
    except Exception as e:
        print("실패:", type(e).__name__, e)
