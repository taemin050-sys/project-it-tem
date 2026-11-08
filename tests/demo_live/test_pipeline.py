"""End-to-end offline Owner Text -> Real Compliance -> Image DTO -> Owner Korean composition.

No OpenAI client is initialized. Uses real B0 JobStore and official DTOs.
Every fake result is explicitly labeled OFFLINE_FIXTURE, NEVER LIVE.
"""
import hashlib
import io
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from demo_staging.live.pipeline import LivePipeline
from demo_staging.live.contracts import LiveGateError
from src.serving.main import create_app
from src.image_generation.backend_adapter import BackendGeneratedImage
from src.text_generation.schemas import (
    AdCopyOutput,ProductAnalysisResult,ResearchResult,ImagePromptOutput
)
from tests.demo_live.test_live_contracts import sample_input,safe_copy

FONT=Path(os.environ.get("IT_TEM_TEST_FONT","/System/Library/Fonts/Supplemental/AppleGothic.ttf"))

def png(rgb,size=(450,600)):
    out=io.BytesIO()
    Image.new("RGB",size,rgb).save(out,"PNG")
    return out.getvalue()

class FakeOwner:
    def __init__(self,copy=None):
        self.a,self.r,self.c,self.p=safe_copy()
        if copy is not None:self.c=copy
        self.calls=[]
    def analyze(self,images):
        self.calls.append("analyze")
        assert len(images)==2
        return ProductAnalysisResult.model_validate(self.a,strict=True)
    def research(self,product,analysis):
        self.calls.append("research")
        assert product.brand_name in {"라움","치료"}
        return ResearchResult.model_validate(self.r,strict=True)
    def generate_copy(self,product,analysis,research):
        self.calls.append("copy")
        return AdCopyOutput.model_validate(self.c,strict=True)
    def generate_prompt(self,plan,analysis):
        self.calls.append("prompt")
        return ImagePromptOutput.model_validate(self.p,strict=True)

def prepare_service(tmp_path):
    app=create_app(tmp_path/"jobs")
    with TestClient(app) as client:
        resp=client.post("/api/v1/jobs",files=[
           ("product_images",("p1.png",png((120,130,140)),"image/png")),
           ("product_images",("p2.png",png((150,160,170)),"image/png")),
        ])
        assert resp.status_code==201,resp.text
        jid=resp.json()["job_id"]
    return LivePipeline(tmp_path/"live",app.state.job_store),jid

def layout():
    return {"text_regions":{
      "headline":{"left":.06,"top":.06,"right":.94,"bottom":.24},
      "subline":{"left":.06,"top":.30,"right":.46,"bottom":.65},
      "cta":{"left":.06,"top":.77,"right":.46,"bottom":.90}},
      "protected_regions":[{"left":.53,"top":.30,"right":.91,"bottom":.92}]}

def test_real_owner_contract_approval_composition_offline_provenance(tmp_path):
    pipeline,jid=prepare_service(tmp_path)
    provider=FakeOwner()
    product=pipeline.prepare("alice",jid,sample_input())
    assert product["input_sha"]
    text=pipeline.text("alice",jid,provider,offline=True)
    assert provider.calls==["analyze","research","copy"]
    assert text["state"]=="COPY_REVIEW_REQUIRED" and text["mode"]=="OFFLINE_FIXTURE"
    assert json.loads(text["compliance_json"])["passed"] is True
    approved=pipeline.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    assert approved["state"]=="COPY_APPROVED"
    prompt=pipeline.prompt("alice",jid,provider,offline=True)
    assert provider.calls[-1]=="prompt" and prompt["state"]=="PROMPT_READY"
    input_to_owner=pipeline.image_input("alice",jid)
    assert len(input_to_owner.product_images)==2
    image_bytes=png((227,228,229),size=(1152,1440))
    output=BackendGeneratedImage(
      image_bytes=image_bytes,mime_type="image/png",width=1152,height=1440,
      sha256=hashlib.sha256(image_bytes).hexdigest(),
      job_id=jid,copy_revision=prompt["generation"],copy_hash=prompt["copy_sha"],
      mock=True,receipt={"mode":"OFFLINE_MOCK_TRANSPORT","provider_calls":0})
    candidate=pipeline.accept_image_result("alice",jid,output,offline=True)
    assert candidate["state"]=="IMAGE_REVIEW_REQUIRED"
    pipeline.state.approve_image("alice",jid,output.sha256)
    complete=pipeline.compose("alice",jid,layout=layout(),font_path=FONT)
    assert complete["state"]=="COMPLETED"
    assert complete["final_sha"]
    with Image.open(tmp_path/"live"/"outputs"/jid/"final.png") as im:
        assert im.size==(1080,1350) and im.format=="PNG"
    cap=(tmp_path/"live"/"outputs"/jid/"caption.txt").read_text(encoding="utf8")
    assert "수분" in cap
    assert provider.calls==["analyze","research","copy","prompt"]

def test_live_disabled_before_model_initialization(tmp_path,monkeypatch):
    pipeline,jid=prepare_service(tmp_path)
    pipeline.prepare("alice",jid,sample_input())
    import sys
    assert "src.text_generation.llm_client" not in sys.modules
    with pytest.raises(Exception,match="LIVE_NOT_APPROVED"):
        pipeline.text("alice",jid,offline=False)
    assert "src.text_generation.llm_client" not in sys.modules

def test_brand_treatment_claim_denied_before_image(tmp_path):
    pipeline,jid=prepare_service(tmp_path)
    data=sample_input(brand="치료")
    pipeline.prepare("alice",jid,data)
    owner=FakeOwner()
    owner.c["ad_copy"]["headline"]="치료 크림으로 치료"
    text=pipeline.text("alice",jid,owner,offline=True)
    assert json.loads(text["compliance_json"])["passed"] is False
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        pipeline.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    with pytest.raises(LiveGateError,match="PROMPT_REQUIRES_APPROVED_COPY"):
        pipeline.prompt("alice",jid,owner,offline=True)

def test_own_photos_mutation_fails_before_any_owner_call(tmp_path):
    pipeline,jid=prepare_service(tmp_path)
    inp=pipeline.prepare("alice",jid,sample_input())
    row=pipeline.jobs.get_job(jid)["assets"][0]
    path,_=pipeline.jobs.get_asset(jid,row["asset_id"])
    path.write_bytes(b"tampered")
    owner=FakeOwner()
    with pytest.raises(LiveGateError,match="INPUT_ASSET_TAMPERED"):
        pipeline.text("alice",jid,owner,offline=True)
    assert owner.calls==[]

def test_official_image_adapter_mocktransport_and_replay_once(tmp_path):
    """Real Owner Image adapter, 0 internet calls, receipt from MockTransport."""
    import base64
    import httpx
    from src.image_generation.assets import LocalAssetStore
    from src.image_generation.api_image_processor import ExternalImageProcessor
    from src.image_generation.backend_adapter import BackendImageAdapter
    from src.image_generation.openai_images import OpenAIImagesAdapter,OpenAIImagesConfig
    from src.image_generation.provider_attempts import ProviderAttemptStore

    pipe,jid=prepare_service(tmp_path)
    pipe.prepare("alice",jid,sample_input())
    fake=FakeOwner()
    text=pipe.text("alice",jid,fake,offline=True)
    pipe.state.approve_copy("alice",jid,text["generation"],text["review_sha"])
    pipe.prompt("alice",jid,fake,offline=True)
    owner_input=pipe.image_input("alice",jid)
    calls=[]
    img_bytes=png((219,224,236),size=(1152,1440))
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200,json={
          "data":[{"b64_json":base64.b64encode(img_bytes).decode()}],
          "usage":{"input_tokens":12,"output_tokens":34,"total_tokens":46}},
          headers={"x-request-id":"test-offline-fixture-no-network"})
    image_root=tmp_path/"owner"
    def adapter():
        provider=OpenAIImagesAdapter(
            OpenAIImagesConfig(live_calls=False),
            transport=httpx.MockTransport(handler))
        processor=ExternalImageProcessor(
            LocalAssetStore(image_root/"assets"),provider,
            ProviderAttemptStore(image_root/"attempts.sqlite"),
            budget_limit_usd="2",reservation_usd="1")
        return BackendImageAdapter(processor,image_root/"bind.sqlite")
    first=adapter().generate(owner_input,project_id=pipe.project_id)
    second=adapter().generate(owner_input,project_id=pipe.project_id)
    assert first==second
    assert calls==["POST"]
    assert first.mock is True
    assert first.receipt["usage"]["total_tokens"]==46
    pipe.accept_image_result("alice",jid,first,offline=True)
    pipe.state.approve_image("alice",jid,first.sha256)
    result=pipe.compose("alice",jid,layout=layout(),font_path=FONT)
    assert result["state"]=="COMPLETED"
    assert result["mode"]=="OFFLINE_FIXTURE"
    with Image.open(pipe.root/"outputs"/jid/"final.png") as im:
        assert im.size==(1080,1350)
