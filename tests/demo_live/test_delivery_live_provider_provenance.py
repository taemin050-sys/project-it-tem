"""Fail-closed actual-LIVE Owner receipt: no forged missing-usage candidate."""
import json
from types import SimpleNamespace
import pytest
from demo_staging.live.pipeline import LivePipeline
from demo_staging.live.contracts import LiveGateError


@pytest.mark.parametrize("receipt", [
    {"state": "succeeded", "attempt_id": "a1", "model": "img",
     "provider_request_id": "req-1"},   # no usage
    {"state": "succeeded", "attempt_id": "a1", "model": "img",
     "provider_request_id": "req-1", "usage": {}},  # no countable usage
    {"state": "succeeded", "attempt_id": "a1", "model": "img",
     "usage": {"total_tokens": 1}},  # no real request ID
])
def test_live_candidate_missing_provider_proof_cannot_advance(receipt):
    # A narrow unit gate: do not call any model, write any DB or generate a
    # synthetic candidate. This is NOT a LIVE E2E success test.
    flow=object.__new__(LivePipeline)
    flow.state=SimpleNamespace(get=lambda actor,job_id:{
        "state":"PROMPT_READY", "mode":"LIVE","generation":1,
        "copy_sha":"a"*64,"input_json":json.dumps({"generation_mode":"composed"})})
    candidate=SimpleNamespace(job_id="b"*32,copy_revision=1,
                              copy_hash="a"*64,mock=False,receipt=receipt)
    with pytest.raises(LiveGateError,match="LIVE_IMAGE_PROVIDER_PROVENANCE_REQUIRED"):
        flow.accept_image_result("actor","b"*32,candidate,offline=False)
