import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_TEXT = os.getenv("OPENAI_MODEL_TEXT", "gpt-5.4-mini")
MODEL_VISION = os.getenv("OPENAI_MODEL_VISION", "gpt-5.4-mini")

if not OPENAI_API_KEY:
    raise RuntimeError(".env에 OPENAI_API_KEY가 없습니다.")
