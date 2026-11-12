"""BP13 image *estimate*, not invoiced charges or a cost reservation.

Evidence:
- Official public rates checked 2026-11-07:
  https://developers.openai.com/api/docs/pricing
  gpt-image-2.6-sunburst standard: text input $5, image input $8,
  image output $30 per 1M billable tokens.
- Read-only reconciled GCP Owner image receipts: 10 successful,
  medium quality, high complexity, COMPOSED, 2026-11-06.
  Each tuple is (text input tokens, image input tokens, image output tokens).
- No Freeform observations; never extrapolate from Composed samples.
- Pricing may change, token counts vary; NONE are actual charges/caps.
"""
from __future__ import annotations

from statistics import median
from typing import Literal

MODEL = "gpt-image-2.6-sunburst"
QUALITY = "medium"
COMPLEXITY = "high"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
SAMPLE_ID = "IT_TEM_GCP_OWNER_IMAGE_COMPOSED_10_20261106"
RATES_PER_MILLION_USD = {"input_text":5.0, "input_image":8.0, "output_image":30.0}
OBSERVED_USAGE: dict[str, tuple[tuple[int, int, int], ...]] = {
    "3:4": ((1242,2727,1347),(1309,4501,1347)),
    "4:5": ((1173,2904,1380),(1187,2727,1380),
            (1203,5808,1380),(1206,5808,1380),(1221,5808,1380)),
    "9:16": ((1176,2727,1212),(1186,4356,1212),(1194,2904,1212)),
}


def _usage_cost(tokens: tuple[int, int, int]) -> float:
    text, image, output = tokens
    return (text*RATES_PER_MILLION_USD["input_text"]
            + image*RATES_PER_MILLION_USD["input_image"]
            + output*RATES_PER_MILLION_USD["output_image"]) / 1_000_000


def estimate_image_once(*, ratio: str, generation_mode: str,
                        model: str, quality: str = QUALITY,
                        complexity: str = COMPLEXITY) -> dict:
    """Return evidence-backed observed-sample range ONLY on exact profile match."""
    if ratio not in OBSERVED_USAGE or generation_mode not in {"composed","freeform"}:
        raise ValueError("Unsupported image ratio or generation mode")
    evidence = {
        "scope":"SINGLE_IMAGE_ONE_ATTEMPT","model":model,"quality":quality,
        "complexity":complexity,"ratio":ratio,"generation_mode":generation_mode,
        "pricing_source":PRICING_SOURCE,"source_checked_date":"2026-11-07",
        "rate_per_million_usd":dict(RATES_PER_MILLION_USD),
        "actual_charges_known":False,"billing_cap":False,"monitor_only":True,
        "method":"observed_token_usage_times_standard_non_cached_rates",
    }
    if (model,quality,complexity,generation_mode)!=(MODEL,QUALITY,COMPLEXITY,"composed"):
        return {**evidence,"status":"NO_MATCHING_PROFILE_EVIDENCE",
                "reason":"선택한 이미지 방식·모델·품질과 일치하는 실제 사용량 표본이 없어 예상 금액을 표시하지 않습니다.",
                "sample_count":0,"reference_median_usd":None,
                "observed_min_usd":None,"observed_max_usd":None}
    amounts=sorted(_usage_cost(tokens) for tokens in OBSERVED_USAGE[ratio])
    return {**evidence,"status":"LIMITED_EMPIRICAL_REFERENCE",
        "reason":"소수의 기존 합성형 실사용 표본만 사용한 참고값이며 실제 청구액이나 비용 상한이 아닙니다.",
        "sample_id":SAMPLE_ID,"sample_count":len(amounts),
        "reference_median_usd":round(median(amounts),6),
        "observed_min_usd":round(amounts[0],6),
        "observed_max_usd":round(amounts[-1],6)}
