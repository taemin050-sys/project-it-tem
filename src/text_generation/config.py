import os

from dotenv import load_dotenv

if os.getenv("PYTHON_DOTENV_DISABLED") != "1":
    load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_TEXT = os.getenv("OPENAI_MODEL_TEXT", "gpt-6-luna")
MODEL_VISION = os.getenv("OPENAI_MODEL_VISION", "gpt-6-luna")

REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low") or None

if not OPENAI_API_KEY:
    raise RuntimeError(".env에 OPENAI_API_KEY가 없습니다.")
