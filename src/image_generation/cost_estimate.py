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
# One team-observed 4:5 medium PNG edit, used as the same comparison unit for
# both paths. The direct path assumes an initial generation and one revision.
_REFERENCE_MODEL = "gpt-image-2.5-sunburst-2026-09-08"
_REFERENCE_USAGE = {
    "input_tokens": 6491,
    "input_text_tokens": 683,
    "input_image_tokens": 5808,
    "output_tokens": 418,
    "total_tokens": 6909,
}
_DIRECT_ATTEMPTS = 2


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


def summarize_image_costs(attempts: list[dict], *, has_candidate: bool) -> tuple[dict, dict | None]:
    """Summarize recorded image attempts and a same-unit retry scenario."""
    dispatched = [
        attempt for attempt in attempts
        if attempt["stage"] == "image" and attempt["state"] != "RESERVED"
    ]
    priced = [
        Decimal(attempt["estimated_cost_usd"]) for attempt in dispatched
        if attempt["estimated_cost_usd"] is not None
    ]
    # An older live candidate may predate the attempt ledger. Its count is an assumption.
    assumed_count = not dispatched and has_candidate
    service_attempts = len(dispatched) or int(assumed_count)
    unpriced = service_attempts - len(priced)
    known_total = sum(priced, Decimal(0))
    reference_usd, _ = estimate_image_cost(_REFERENCE_MODEL, _REFERENCE_USAGE)
    assert reference_usd is not None
    reference_cost = Decimal(reference_usd)
    summary = {
        "known_estimated_cost_usd": format(known_total, "f") if priced else None,
        "estimated_total_usd": format(known_total + unpriced * reference_cost, "f") if service_attempts else None,
        "priced_attempt_count": len(priced),
        "unpriced_attempt_count": unpriced,
    }
    if not service_attempts:
        return summary, None

    saved_attempts = _DIRECT_ATTEMPTS - service_attempts
    comparison = {
        "reference_usage": dict(_REFERENCE_USAGE),
        "reference_cost_usd": reference_usd,
        "direct_attempt_count": _DIRECT_ATTEMPTS,
        "service_attempt_count": service_attempts,
        "service_attempt_count_is_estimated": assumed_count,
        "direct_estimated_cost_usd": format(reference_cost * _DIRECT_ATTEMPTS, "f"),
        "service_estimated_cost_usd": format(reference_cost * service_attempts, "f"),
        "estimated_savings_usd": format(reference_cost * saved_attempts, "f"),
        "estimated_savings_tokens": _REFERENCE_USAGE["total_tokens"] * saved_attempts,
    }
    return summary, comparison
