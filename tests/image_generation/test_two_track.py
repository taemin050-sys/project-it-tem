"""Image-only two-track boundary; all provider requests use MockTransport."""
from copy import deepcopy
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
import base64

import httpx
from PIL import Image
import pytest
from pydantic import ValidationError

from src.image_generation.contracts import ExternalImageRequest, content_hash
from src.image_generation.errors import GatewayError
from . import test_backend_adapter as backend
from .helpers import FONT, copy_output, layout


def candidate(mode="freeform", **changes):
    copy = copy_output()
    values = dict(generation_mode=mode, copy_output=copy, copy_hash=content_hash(copy),
                  ad_copy=copy["ad_copy"], caption=copy["caption"], hashtags=copy["hashtags"])
    values.update(changes)
    return backend.body(**values)


def fields(request):
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.read())
    return {p.get_param("name", header="content-disposition"): p.get_payload(decode=True).decode()
            for p in message.iter_parts()
            if p.get_param("name", header="content-disposition") != "image[]"}


def test_contract_legacy_request_serialization():
    request = ExternalImageRequest(operation="generate", prompt=dict(
        positive="밝은 화장품 배경", prompt_version="v1", source_revision=1))
    data = request.model_dump(mode="json")
    assert "text_rendering" not in data
    assert content_hash(request) == content_hash(data)
    with pytest.raises(ValidationError):
        ExternalImageRequest(**data, text_rendering="freeform-v1")


@pytest.mark.parametrize("mode", [None, "composed", "freeform"])
def test_contract_complete_copy_and_mode_replay(tmp_path, mode):
    calls = []
    def handler(req):
        calls.append(req)
        return backend.response()
    adapter = backend.setup(tmp_path, handler)
    body = candidate(mode)
    project = uuid4()
    one = adapter.generate(body, project_id=project)
    two = backend.setup(tmp_path, handler).generate(body, project_id=project)
    assert one == two and len(calls) == 1
    assert one.receipt["generation_mode"] == (mode or "composed")


@pytest.mark.parametrize("part", ["hash", "ad", "caption", "hashtags", "plan"])
def test_contract_copy_mismatch_before_assets_or_attempt(tmp_path, monkeypatch, part):
    body = candidate()
    if part == "hash":
        body.copy_hash = "b" * 64
    elif part == "ad":
        body.ad_copy.headline = "다른 문구"
    elif part == "caption":
        body.caption = "다른 본문"
    elif part == "hashtags":
        body.hashtags = ["#다름"]
    else:
        body.copy_output["plan"]["target"] = "다른 대상"
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("No provider call"))
    monkeypatch.setattr(adapter.processor.assets, "put_upload", lambda *a, **k: pytest.fail("No asset write"))
    with pytest.raises(GatewayError) as error:
        adapter.generate(body, project_id=uuid4())
    assert error.value.code == "BACKEND_COPY_INVALID"


def test_contract_mode_change_conflicts_and_freeform_requires_snapshot(tmp_path):
    with pytest.raises(ValidationError):
        backend.body(generation_mode="freeform")
    with pytest.raises(ValidationError):
        candidate(safe_zone=dict(left=.1, top=.1, right=.9, bottom=.3))
    calls = []
    def handler(req):
        calls.append(req)
        return backend.response()
    adapter = backend.setup(tmp_path, handler)
    project = uuid4()
    body = candidate("composed")
    adapter.generate(body, project_id=project)
    with pytest.raises(GatewayError) as error:
        adapter.generate(body.model_copy(update={"generation_mode": "freeform"}), project_id=project)
    assert error.value.code == "BACKEND_INPUT_CONFLICT"
    assert len(calls) == 1


def test_contract_nullable_optional_copy_fields(tmp_path):
    copy = copy_output()
    copy["ad_copy"].update(subline="", cta="")
    body = candidate(copy_output=copy, copy_hash=content_hash(copy),
                     ad_copy=dict(headline=copy["ad_copy"]["headline"], subline=None, cta=None))
    adapter = backend.setup(tmp_path, lambda _: backend.response())
    assert adapter.generate(body, project_id=uuid4()).receipt["state"] == "succeeded"


def test_contract_analysis_failure_blocks_freeform(tmp_path):
    body = candidate(product_analysis=backend.analysis_result(analysis_succeeded=False))
    adapter = backend.setup(tmp_path, lambda _: pytest.fail("No provider call"))
    with pytest.raises(GatewayError) as error:
        adapter.generate(body, project_id=uuid4())
    assert error.value.code == "PRODUCT_ANALYSIS_FAILED"
