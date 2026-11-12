"""Serving Image #23 DTO -> actual BackendImageAdapter -> mock wire, zero network.

This differs from synthesizing a BackendGeneratedImage: it tests the real Owner
request builder, exact multipart, native generation sizes, model settings,
receipt replay and downstream local composition under real approval gates.
"""
from __future__ import annotations

import base64
import hashlib
from email import policy as email_policy
from email.parser import BytesParser
from io import BytesIO

import httpx
import pytest
from PIL import Image

from demo_staging.live.contracts import LiveGateError
from src.image_generation.assets import LocalAssetStore
from src.image_generation.api_image_processor import ExternalImageProcessor
from src.image_generation.backend_adapter import BackendImageAdapter
from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
from src.image_generation.provider_attempts import ProviderAttemptStore
from tests.demo_live.test_owner_image23_multisize_integration import SIZES
from tests.demo_live.test_pipeline import FakeOwner, FONT, png, prepare_service
from tests.demo_live.test_live_contracts import sample_input


@pytest.mark.parametrize("ratio,policy,native,final,placement",SIZES)
def test_owner23_service_to_mock_transport_no_real_provider(tmp_path,ratio,policy,native,final,placement):
    flow,jid=prepare_service(tmp_path)
    flow.prepare("alice",jid,{**sample_input(),"image_size":ratio},template_profile="A")
    fake=FakeOwner()
    review=flow.text("alice",jid,fake,offline=True)
    flow.state.approve_copy("alice",jid,review["generation"],review["review_sha"])
    flow.prompt("alice",jid,fake,offline=True)
    backend_input=flow.image_input("alice",jid)
    assert backend_input.layout_selection.aspect_ratio==ratio
    requests=[]
    image=png((210,219,227),size=native)
    def handle(request:httpx.Request):
        requests.append(request)
        return httpx.Response(200,json={
            "data":[{"b64_json":base64.b64encode(image).decode()}],
            "usage":{"input_tokens":8,"output_tokens":12,"total_tokens":20}},
            headers={"x-request-id":"owner23-no-network-test"})
    base=tmp_path/"owner_transport"
    def build():
        transport=OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False),
            transport=httpx.MockTransport(handle))
        processor=ExternalImageProcessor(
            LocalAssetStore(base/"assets"),transport,
            ProviderAttemptStore(base/"attempts.sqlite"),
            budget_limit_usd="2",reservation_usd="1")
        return BackendImageAdapter(processor,base/"bindings.sqlite",
            model="gpt-image-2.6-sunburst",quality="medium",complexity="high")
    first=build().generate(backend_input,project_id=flow.project_id)
    second=build().generate(backend_input,project_id=flow.project_id)
    assert first==second and len(requests)==1
    wire=requests[0]
    assert wire.method=="POST"
    assert "api.openai.com" in str(wire.url)
    email=BytesParser(policy=email_policy.default).parsebytes(
        b"Content-Type: "+wire.headers["content-type"].encode()+
        b"\r\n\r\n"+wire.read())
    payload={part.get_param("name",header="content-disposition"):part.get_payload(decode=True)
        for part in email.iter_parts()
        if part.get_param("name",header="content-disposition")!="image[]"}
    assert payload["model"].decode()=="gpt-image-2.6-sunburst",list(payload)
    assert payload["complexity"].decode()=="high"
    assert payload["quality"].decode()=="medium"
    assert payload["size"].decode()==f"{native[0]}x{native[1]}"
    assert first.mock and first.receipt["usage"]["total_tokens"]==20
    flow.accept_image_result("alice",jid,first,offline=True)
    flow.state.approve_image("alice",jid,first.sha256)
    finished=flow.compose("alice",jid,font_path=FONT)
    assert finished["state"]=="COMPLETED"
    with Image.open(flow.root/"outputs"/jid/"final.png") as f:
        assert f.size==final
    assert hashlib.sha256((flow.root/"outputs"/jid/"final.png").read_bytes()).hexdigest()==finished["final_sha"]
    # Adapter's simulated provider attempt is in an offline test ledger only;
    # the Live worker's billable queue and cost ledger remain untouched.
    import sqlite3
    for filename,table in [("queue.sqlite","queued_ops"),("cost.sqlite","attempts")]:
        filename=flow.root/filename
        if not filename.exists():
            # No LiveQueue was even instantiated on this offline Owner path.
            continue
        with sqlite3.connect(filename) as db:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert table not in tables or db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==0
