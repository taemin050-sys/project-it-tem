"""Official Text Owner DTO and PR#10 Image offline bridge integration.

This test was introduced with v0.8. The Owner PR25 v0.10 baseline is retained
below. Track B adds exact claim references to Research citations while
preserving the baseline DTO fixtures and fail-closed contract cases.

On dev alone, these integrations SKIP (never count as integrated PASS).
In an isolated combined checkout, NO SKIP is acceptable. No OpenAI/API calls.
"""
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import socket
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest

text_owner = pytest.importorskip("src.text_generation.schemas", reason="Text owner unmerged")
image_owner = pytest.importorskip("src.image_generation", reason="Image owner unmerged")
pytest.importorskip("src.serving.image_offline_bridge", reason="PR10 unmerged")

from src.image_generation.assets import LocalAssetStore
from src.image_generation.api_image_processor import ExternalImageProcessor
from src.image_generation.backend_adapter import BackendImageAdapter
from src.image_generation.contracts import content_hash
from src.image_generation.openai_images import OpenAIImagesAdapter, OpenAIImagesConfig
from src.image_generation.provider_attempts import ProviderAttemptStore
from src.serving.image_offline_bridge import OfflineImageFlow
from src.serving.main import create_app
from src.serving.text_v08_mapper import (
    TextBoundaryError, prepare_offline_stage, verify_analysis, verify_research,
)

# Original v0.8 historical schema hash (not the current Owner source).
LEGACY_V08_SCHEMA_SHA256 = "051aab8b02d461b4d8787053e6af6dfc1267acbd48fd0304ff0f4f090bac18f7"
OWNER_SCHEMA_SHA256 = "93849c85a1bd155136f69a71ce22aa9371e7b48cfd5b432ce07a0617e1560235"
B_F07_SCHEMA_SHA256 = "76558bbbe4b1cd91bceef37f917486a35b488b367bddd7b5300851ef87277489"
FIX = Path(__file__).resolve().parents[1] / "docs/contracts/fixtures"


@pytest.fixture(autouse=True)
def no_real_sockets(monkeypatch):
    attempts = []
    def blocked(*args, **kwargs):
        attempts.append(1)
        raise AssertionError("REAL_NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    yield
    assert not attempts, "No socket connection attempt is permitted"


def f(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def official_inputs():
    # Own read code and fixture data only; never import text config or client.
    raw_analysis = f("product_analysis.json")
    research = f("research_result_no_search.json")
    return (
        text_owner.ProductAnalysisResult.model_validate({
            "analysis": raw_analysis, "analysis_succeeded": True, "error": None
        }, strict=True),
        text_owner.ResearchResult.model_validate(research, strict=True),
        text_owner.AdCopyOutput.model_validate(f("ad_copy_output.json"), strict=True),
        text_owner.ImagePromptOutput.model_validate(f("image_prompt_output.json"), strict=True),
    )


def png(color, size=(115,160)):
    out=BytesIO()
    Image.new("RGB",size,color).save(out,"PNG")
    return out.getvalue()


def layout():
    return {
        "text_regions": {
            "headline": {"left":.06,"top":.06,"right":.94,"bottom":.24},
            "subline": {"left":.06,"top":.30,"right":.46,"bottom":.65},
            "cta": {"left":.06,"top":.77,"right":.46,"bottom":.90},
        },
        "protected_regions":[{"left":.53,"top":.30,"right":.91,"bottom":.92}],
    }


def test_owner_official_models_and_strict_no_coercion():
    assert hashlib.sha256(Path(text_owner.__file__).read_bytes()).hexdigest() == B_F07_SCHEMA_SHA256
    a,r,c,p = official_inputs()
    assert verify_analysis(a, model=text_owner.ProductAnalysisResult).image_owner_input["analysis_succeeded"] is True
    assert verify_research(r, model=text_owner.ResearchResult).outcome == "search_not_performed"
    assert r.error is None
    for raw in ({"analysis": f("product_analysis.json"), "analysis_succeeded": "true","error":None},
                {"analysis": f("product_analysis.json"), "analysis_succeeded": False,"error":None},
                {"analysis": f("product_analysis.json"), "analysis_succeeded": True,"error":"failure"}):
        with pytest.raises(TextBoundaryError):
            prepare_offline_stage(raw,r,c,p,owner_schemas=text_owner,copy_revision="1")
    assert "src.text_generation.config" not in __import__("sys").modules
    assert "src.text_generation.llm_client" not in __import__("sys").modules


def test_owner_research_default_error_is_backward_compatible():
    legacy=f("research_result_no_search.json")
    legacy.pop("error",None)
    parsed=text_owner.ResearchResult.model_validate(legacy,strict=True)
    assert parsed.error is None
    result=verify_research(legacy,model=text_owner.ResearchResult)
    assert result.original["error"] is None
    assert result.outcome == "search_not_performed"


def test_image_owner_error_excluded_during_dump_still_blocks():
    # The official Image Owner hides this field in model_dump(exclude=True).
    analysis=image_owner.ProductAnalysisResult.model_validate({
        "analysis": f("product_analysis.json"),
        "analysis_succeeded": True, "error": "provider failed",
    },strict=True)
    assert "error" not in analysis.model_dump()
    with pytest.raises(TextBoundaryError) as denied:
        verify_analysis(analysis,model=text_owner.ProductAnalysisResult)
    assert denied.value.code == "VLM_FAILED"


def test_owner_research_error_fallback_is_not_cosmetic_failure():
    a,r,c,p=official_inputs()
    r.error="temporary provider issue"
    r.research_performed=False
    stage=prepare_offline_stage(a,r,c,p,owner_schemas=text_owner,copy_revision="1")
    assert stage.research.original["error"] == "temporary provider issue"
    assert stage.research.outcome == "research_failed_fallback"
    assert stage.research.display["research_performed"] is False
    assert stage.research.display["citations"] == []
    # A fallback is allowed for offline staging. Compliance remains absent.
    assert stage.fixture_args()["copy_revision"] == "1"


@pytest.mark.parametrize("mutate", ["caption", "hashtags", "plan", "prompt", "mood", "analysis"])
def test_s4_stage_mutation_cannot_reach_pr10_stage_copy(tmp_path, mutate):
    analysis, research, copy, prompt = official_inputs()
    stage = prepare_offline_stage(analysis, research, copy, prompt,
                                  owner_schemas=text_owner, copy_revision="1")
    # Frozen dataclass doesn't freeze mutable nested dictionaries.
    if mutate == "caption":
        stage.copy_output["caption"] += " 변조"
    elif mutate == "hashtags":
        stage.copy_output["hashtags"].append("#변조")
    elif mutate == "plan":
        stage.copy_output["plan"]["key_message"] += " 변조"
    elif mutate == "prompt":
        stage.image_prompt["prompt"] += " 변조"
    elif mutate == "mood":
        stage.image_prompt["mood"] = ["변조"]
    elif mutate == "analysis":
        stage.product_analysis["analysis"]["colors"].append("변조")

    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        created = client.post("/api/v1/jobs", files=[
            ("product_images", ("a.png", png((20, 30, 40)), "image/png")),
            ("product_images", ("b.png", png((80, 70, 60)), "image/png")),
        ])
        assert created.status_code == 201
        job = created.json()["job_id"]
        assert client.post(f"/api/v1/jobs/{job}/mock/plan",
                           json={"brand_name": "라움", "product_name": "크림"}).status_code == 200
        assert client.post(f"/api/v1/jobs/{job}/mock/copy").status_code == 200

        calls = []
        def handler(request):
            calls.append(request)
            raise AssertionError("Unexpected fake provider call")
        provider = OpenAIImagesAdapter(
            OpenAIImagesConfig(live_calls=False, api_key=None),
            transport=httpx.MockTransport(handler))
        adapter = BackendImageAdapter(
            ExternalImageProcessor(
                LocalAssetStore(tmp_path / "image_assets"), provider,
                ProviderAttemptStore(tmp_path / "attempts.sqlite3"),
                budget_limit_usd="10"),
            tmp_path / "bindings.sqlite3")
        font = Path(__file__).parent / "image_generation/fixtures/fonts/NanumGothic-Regular.ttf"
        flow = OfflineImageFlow(app.state.job_store, adapter=adapter,
                                project_id=uuid5(NAMESPACE_URL, "s4-integrity-negative"),
                                font_path=font)
        with pytest.raises(TextBoundaryError) as denied:
            flow.stage_copy(job, **stage.fixture_args())
        assert denied.value.code in {
            "STAGED_COPY_CHANGED", "STAGED_PROMPT_CHANGED", "STAGED_ANALYSIS_CHANGED",
            "PROMPT_PLAN_MISMATCH",
        }
        unchanged = app.state.job_store.get_job(job)
        assert unchanged["status"] == "COPY_REVIEW_REQUIRED"
        assert "offline_copy" not in unchanged
        assert calls == []


@pytest.mark.parametrize("revision",["1",1])
def test_real_current_owner_owner_through_existing_pr10_offline_image_flow(tmp_path,revision):
    assert hashlib.sha256(Path(text_owner.__file__).read_bytes()).hexdigest() == B_F07_SCHEMA_SHA256
    source = official_inputs()
    stage=prepare_offline_stage(*source,owner_schemas=text_owner,copy_revision=revision)
    assert content_hash(stage.copy_output) == stage.copy_hash
    assert stage.research.original["research_performed"] is False
    assert stage.image_prompt["concept"] == source[2].plan.concept
    assert stage.image_prompt["mood"] == source[2].plan.mood

    calls=[]
    generated_png = png((240,238,234),(1152,1440))
    def handler(request):
        calls.append("mock")
        return httpx.Response(
            200, json={"data":[{"b64_json":base64.b64encode(generated_png).decode()}]},
            headers={"x-request-id":"s4-offline-fixture"}
        )
    provider=OpenAIImagesAdapter(OpenAIImagesConfig(live_calls=False,api_key=None),
                                 transport=httpx.MockTransport(handler))
    assert provider.offline and not provider.config.live_calls
    processor=ExternalImageProcessor(
        LocalAssetStore(tmp_path/"image_assets"), provider,
        ProviderAttemptStore(tmp_path/"image_attempts.sqlite3"), budget_limit_usd="10",
    )
    adapter=BackendImageAdapter(processor,tmp_path/"image_bindings.sqlite3")
    app=create_app(tmp_path/"jobs")
    project_id=uuid5(NAMESPACE_URL,"s4-offline-fixture-project")
    font=Path(os.environ.get("IT_TEM_KOREAN_FONT",
                             str(Path(__file__).parent / "image_generation" /
                                 "fixtures/fonts/NanumGothic-Regular.ttf")))
    assert font.is_file()
    with TestClient(app) as client:
        response=client.post("/api/v1/jobs",files=[
            ("product_images",("p1.png",png((120,200,150)),"image/png")),
            ("product_images",("p2.png",png((130,190,160)),"image/png")),
        ])
        assert response.status_code==201,response.text
        job=response.json()["job_id"]
        assert client.post(f"/api/v1/jobs/{job}/mock/plan",
                           json={"brand_name":"라움","product_name":"크림"}).status_code==200
        assert client.post(f"/api/v1/jobs/{job}/mock/copy").status_code==200
        flow=OfflineImageFlow(app.state.job_store,adapter=adapter,
                              project_id=project_id,font_path=font)
        staged=flow.stage_copy(job,**stage.fixture_args())
        assert staged["status"]=="COPY_REVIEW_REQUIRED"
        assert staged["offline_copy"]["copy_hash"]==stage.copy_hash
        assert staged["offline_copy"]["review_scope"]=="OFFLINE_FIXTURE_NO_COMPLIANCE"
        approved=flow.approve_fixture_copy(job)
        assert approved["offline_copy_approval"]["scope"]=="OFFLINE_FIXTURE_APPROVAL_NOT_COMPLIANCE"
        assert calls==[]
        generated=flow.generate(job)
        assert generated["status"]=="IMAGE_REVIEW_REQUIRED"
        assert type(generated["image_candidate"]["copy_revision"]) is type(revision)
        assert len(calls)==1
        image_approved=flow.approve_image(job)
        assert image_approved["offline_image_approval"]["scope"]=="OFFLINE_FIXTURE_APPROVAL_NOT_REAL_USER"
        final=flow.compose(job,layout=layout())
        assert final["status"]=="COMPLETED"
        assert final["final_output"]["copy_hash"]==stage.copy_hash
        assert type(final["final_output"]["copy_revision"]) is type(revision)
        assert final["final_output"]["scope"]=="OFFLINE_FIXTURE_NOT_LIVE"
        image=client.get(f"/api/v1/jobs/{job}/artifacts/final")
        caption=client.get(f"/api/v1/jobs/{job}/artifacts/caption")
        assert image.status_code==200 and caption.status_code==200
        with Image.open(BytesIO(image.content)) as im:
            assert im.size==(1080,1350) and im.format=="PNG"
        assert source[2].caption in caption.content.decode("utf8")
        assert len(calls)==1
