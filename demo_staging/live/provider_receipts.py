"""Per-request sanitized receipt capture for Owner Text LLM code.

No OpenAI import, no credentials, user content or raw response payloads.
Raw provider response metadata is used only for countable usage evidence.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import re

_collect: ContextVar[list|None] = ContextVar("ittem_live_receipt_sink",default=None)
_REQUEST_ID=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,199}$")

@dataclass
class ReceiptSink:
    events:list[dict]=field(default_factory=list)

@contextmanager
def collect_receipts():
    sink=ReceiptSink()
    token=_collect.set(sink.events)
    try:yield sink
    finally:_collect.reset(token)

def record_owner_response(body:dict, request_id:str|None=None) -> None:
    sink=_collect.get()
    if sink is None:
        return
    if not isinstance(body,dict):return
    usage=body.get("usage")
    if not isinstance(usage,dict):
        return
    counts={}
    for field in ("input_tokens","output_tokens","total_tokens"):
        n=usage.get(field)
        if type(n) is not int or n<0:
            return
        counts[field]=n
    model=body.get("model")
    if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}",model):
        return
    receipt_id=body.get("id") or request_id
    if not isinstance(receipt_id,str) or not _REQUEST_ID.fullmatch(receipt_id):
        return
    status=body.get("status")
    if status!="completed":
        # A provider response with incomplete output may be billable.
        return
    sink.append({
      "provider":"openai","model":model,"provider_response_id":receipt_id,
      "usage":counts,"billing_status":"UNPRICED_RESERVATION_HELD",
    })
