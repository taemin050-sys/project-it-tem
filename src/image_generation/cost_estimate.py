"""Standard-rate estimates from recorded OpenAI Images PNG usage."""

from decimal import Decimal


RATE_VERSION = "openai-images-standard-uncached-2026-11-09-v1"
# USD per million tokens: text input, image input, image output.
# https://developers.openai.com/api/docs/models/gpt-image-2
# https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst
# https://developers.openai.com/api/docs/models/gpt-image-2.6-sunburst
_MODEL_RATES = {
    "gpt-image-2-2026-04-21": (5, 8, 30),
    "gpt-image-2.5-sunburst-2026-09-08": (5, 8, 30),
    "gpt-image-2.6-sunburst": (5, 8, 30),
}


def estimate_image_cost(model: object, usage: object) -> tuple[str | None, str | None]:
    """Return a decimal USD estimate and its rate version for a saved receipt."""
    if not isinstance(model, str) or model not in _MODEL_RATES or not isinstance(usage, dict):
        return None, None
    input_tokens = usage.get("input_tokens")
    text_tokens = usage.get("input_text_tokens")
    image_tokens = usage.get("input_image_tokens")
    output_tokens = usage.get("output_tokens")
    counts = (input_tokens, text_tokens, image_tokens, output_tokens)
    if any(type(count) is not int or not 0 <= count <= 2**63 - 1 for count in counts):
        return None, None
    if text_tokens + image_tokens != input_tokens:
        return None, None
    total_tokens = usage.get("total_tokens")
    if total_tokens is not None and (type(total_tokens) is not int or total_tokens != input_tokens + output_tokens):
        return None, None

    text_rate, image_rate, output_rate = _MODEL_RATES[model]
    micro_usd = text_tokens * text_rate + image_tokens * image_rate + output_tokens * output_rate
    return format(Decimal(micro_usd).scaleb(-6), "f"), RATE_VERSION
