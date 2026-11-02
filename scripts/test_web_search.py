from openai import OpenAI

from src.text_generation.config import MODEL_TEXT, OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

res = client.responses.create(
    model=MODEL_TEXT,
    tools=[{"type": "web_search"}],
    input="2026년 국내 수분 크림 트렌드를 3줄로 요약하고 출처 URL을 같이 알려줘.",
)
print(res.output_text)
print("[토큰]", res.usage.input_tokens, "in /", res.usage.output_tokens, "out")
