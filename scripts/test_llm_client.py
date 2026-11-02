import logging

from src.text_generation.llm_client import LLMError, call_structured
from src.text_generation.schemas import CopySet

logging.basicConfig(level=logging.INFO)

try:
    result = call_structured(
        "수분 크림 인스타 광고 카피를 써줘.",
        CopySet,
        instructions="너는 화장품 광고 카피라이터야. 입력에 없는 효능은 쓰지 마.",
    )
    print(result)
except LLMError as e:
    print("실패:", e)
