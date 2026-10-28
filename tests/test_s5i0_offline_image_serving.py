"""S5-I0 real Owner code + Serving JobStore offline-only E2E.

The official dev does NOT contain the unmerged Image Owner package. These
owner-dependent tests explicitly SKIP on dev, and must PASS in an isolated
integration checkout that merges owner@65c2e84 with S5 branch. No HTTP wire
or live provider path is added by the S5 implementation.
"""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import os
from pathlib import Path
import socket
from uuid import UUID, NAMESPACE_URL, uuid5

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest

image_owner = pytest.importorskip("src.image_generation", reason="Owner image code unmerged: test in isolated combined checkout")
from src.image_generation.assets import LocalAssetStore
from src.image_generation.api_image_processor import ExternalImageProcessor
from src.image_generation.openai_images import OpenAIImagesAdapter, OpenAIImagesConfig
from src.image_generation.provider_attempts import ProviderAttemptStore
from src.image_generation.backend_adapter import BackendImageAdapter
from src.image_generation.contracts import content_hash
from src.serving.image_offline_bridge import OfflineImageFlow
from src.serving.main import create_app
from src.serving.job_store import transition_job, get_mock_artifact

PROJECT_ID = uuid5(NAMESPACE_URL, "ittem/s5i0/offline-fixed-project")
FONT = Path(__file__).parent / "image_generation" / "fixtures/fonts/NanumGothic-Regular.ttf"


def png(rgb=(30, 80, 130), size=(110, 150)):
    file = BytesIO()
    Image.new("RGB", size, rgb).save(file, "PNG")
    return file.getvalue()


def output_image():
    return png((230, 240, 245), (1152, 1440))


def approved_copy():
    return {
        "plan": {"concept": "화장품 일상 루틴", "audience": "화장품 이용 고객"},
        "ad_copy": {"headline": "오늘의 루틴", "subline": "하루를 위한 부드러운 선택",
                    "cta": "제품 살펴보기"},
        "caption": "매일의 루틴",
        "hashtags": ["#일상루틴", "#뷰티"],
    }


def layout():
    return {
        "text_regions": {
            "headline": {"left": .06, "top": .06, "right": .94, "bottom": .24},
            "subline": {"left": .06, "top": .30, "right": .46, "bottom": .65},
            "cta": {"left": .06, "top": .77, "right": .46, "bottom": .90},
        },
        "protected_regions": [{"left": .53, "top": .30, "right": .91, "bottom": .92}],
    }


def analysis(is_cosmetic=True, succeeded=True, error=None):
    return {
        "analysis": {
            "is_cosmetic": is_cosmetic, "product_type": "스킨케어",
            "container_type": "스틱", "colors": ["흰색"],
            "label_text": ["미확인 OCR"], "mood": ["차분한"],
            "is_transparent": False,
        },
        "analysis_succeeded": succeeded, "error": error,
    }


@pytest.fixture(autouse=True)
def prohibit_all_real_sockets(monkeypatch):
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("S5-I0 must not open any actual network socket")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    yield
    assert attempts == [], "Unauthorized network activity attempted"


@pytest.fixture
def setup(tmp_path):
    app = create_app(tmp_path / "job_store")
    calls = []
    def handler(req):
        calls.append({"url": str(req.url), "method": req.method})
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(output_image()).decode("ascii")}]},
            headers={"x-request-id":"offline-only-s5"},
        )
    adapter = make_adapter(tmp_path, handler)
    with TestClient(app) as http:
        resp = http.post("/api/v1/jobs", files=[
            ("product_images", ("p01.png", png((15,50,80)), "image/png")),
            ("product_images", ("p02.png", png((20,60,90)), "image/png")),
        ])
        assert resp.status_code == 201, resp.text
        job = resp.json()["job_id"]
        assert http.post(f"/api/v1/jobs/{job}/mock/plan", json={
            "brand_name": "라움", "product_name": "데일리 크림",
        }).status_code == 200
        assert http.post(f"/api/v1/jobs/{job}/mock/copy").status_code == 200
        flow = OfflineImageFlow(app.state.job_store, adapter=adapter, project_id=PROJECT_ID,
                                font_path=FONT)
        yield app, http, job, flow, calls


def make_adapter(root, handler):
    root = Path(root)
    owner = OpenAIImagesAdapter(
        OpenAIImagesConfig(live_calls=False, api_key=None),
        transport=httpx.MockTransport(handler),
    )
    assert owner.offline and not owner.config.live_calls
    processor = ExternalImageProcessor(
        LocalAssetStore(root / "image_assets"), owner,
        ProviderAttemptStore(root / "image_attempts.sqlite3"),
        budget_limit_usd="10",
    )
    return BackendImageAdapter(processor, root / "image_bindings.sqlite3")


def stage_and_approve(setup, revision="mock-copy-r01", copy=None):
    _, _, job, flow, _ = setup
    copy = approved_copy() if copy is None else copy
    staged = flow.stage_copy(
        job, copy_output=copy, copy_revision=revision,
        product_analysis=analysis(),
        image_prompt={"concept":"부드러운 일상", "prompt":"한국어 광고 장면. 제품 비율 유지.",
                      "mood":["차분함","밝음"]},
    )
    assert staged["status"] == "COPY_REVIEW_REQUIRED"
    return flow.approve_fixture_copy(job)


def assert_409(exc, reason):
    assert exc.value.status_code == 409
    assert exc.value.detail["reason"] == reason


def test_real_offline_owner_generate_approve_compose_download(setup):
    app, http, job, flow, calls = setup
    stage_and_approve(setup, revision="mock-copy-r01")
    with pytest.raises(Exception) as blocked:
        flow.compose(job, layout=layout())
    assert getattr(blocked.value, "status_code", None) == 409

    generated = flow.generate(job)
    assert generated["status"] == "IMAGE_REVIEW_REQUIRED"
    assert generated["image_candidate"]["mock"] is True
    assert generated["image_candidate"]["copy_hash"] == content_hash(approved_copy())
    assert generated["image_candidate"]["copy_revision"] == "mock-copy-r01"
    assert len(calls) == 1  # 1 *MockTransport* dispatch, zero real sockets
    with pytest.raises(Exception):
        flow.compose(job, layout=layout())
    assert flow.approve_image(job)["status"] == "IMAGE_APPROVED"
    result = flow.compose(job, layout=layout())
    assert result["status"] == "COMPLETED"
    assert result["final_output"]["mock"]
    assert result["final_output"]["copy_hash"] == content_hash(approved_copy())
    assert result["final_output"]["copy_revision"] == "mock-copy-r01"
    assert result["final_output"]["source_image_sha256"] == generated["image_candidate"]["sha256"]
    image_response = http.get(f"/api/v1/jobs/{job}/artifacts/final")
    caption_response = http.get(f"/api/v1/jobs/{job}/artifacts/caption")
    assert image_response.status_code == 200 and caption_response.status_code == 200
    with Image.open(BytesIO(image_response.content)) as rendered:
        assert rendered.format == "PNG" and rendered.size == (1080, 1350)
    assert "매일의 루틴" in caption_response.content.decode("utf-8")
    assert "#일상루틴" in caption_response.text
    assert hashlib.sha256(image_response.content).hexdigest() == result["final_output"]["sha256"]
    assert len(calls) == 1
    with pytest.raises(Exception) as duplicate:
        flow.generate(job)
    assert_409(duplicate, "COPY_NOT_APPROVED")
    assert len(calls) == 1
    assert app.state.job_store.get_job(job)["status"] == "COMPLETED"


@pytest.mark.parametrize("revision", ["1", 1])
def test_revision_type_is_preserved_end_to_end(setup, revision):
    app, http, job, flow, calls = setup
    stage_and_approve(setup, revision=revision)
    generated = flow.generate(job)
    assert type(generated["image_candidate"]["copy_revision"]) is type(revision)
    assert generated["image_candidate"]["copy_revision"] == revision
    flow.approve_image(job)
    final = flow.compose(job, layout=layout())
    assert type(final["final_output"]["copy_revision"]) is type(revision)
    assert final["final_output"]["copy_revision"] == revision
    assert len(calls) == 1


def test_staged_copy_changed_and_restored_requires_fresh_stage(setup):
    app, http, job, flow, calls = setup
    flow.stage_copy(job, copy_output=approved_copy(), copy_revision="r01",
                    product_analysis=analysis(), image_prompt="밝은 제품 배경")
    original = app.state.job_store.get_job(job)["copy_candidate"]
    transition_job(app.state.job_store, job, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED",
                   updates={"copy_candidate":{**original, "text":"다른 카피"}})
    transition_job(app.state.job_store, job, expected_status="COPY_REVIEW_REQUIRED",
                   next_status="COPY_REVIEW_REQUIRED", updates={"copy_candidate":original})
    with pytest.raises(Exception) as stale:
        flow.approve_fixture_copy(job)
    assert_409(stale, "STALE_STAGED_COPY_GENERATION")
    assert len(calls) == 0
    flow.stage_copy(job, copy_output=approved_copy(), copy_revision="r02",
                    product_analysis=analysis(), image_prompt="새 문구")
    assert flow.approve_fixture_copy(job)["status"] == "COPY_APPROVED"


def test_changed_approved_copy_and_input_bytes_cannot_generate(setup):
    app, _, job, flow, calls = setup
    stage_and_approve(setup)
    with pytest.raises(Exception) as edit:
        transition_job(app.state.job_store, job, expected_status="COPY_APPROVED",
                       next_status="COPY_APPROVED",
                       updates={"offline_copy":{"plan":"changed"}})
    assert_409(edit, "APPROVED_COPY_IMMUTABLE")
    product = next(x for x in app.state.job_store.get_job(job)["assets"] if x["role"]=="product")
    path, _ = app.state.job_store.get_asset(job, product["asset_id"])
    original = path.read_bytes()
    try:
        path.write_bytes(b"tampered bytes")
        with pytest.raises(Exception) as hash_error:
            flow.generate(job)
        assert_409(hash_error, "INPUT_ASSET_HASH_CHANGED")
        assert len(calls) == 0
    finally:
        path.write_bytes(original)


def test_image_sha_mismatch_and_approval_gate_fail_closed(setup):
    app, _, job, flow, calls = setup
    stage_and_approve(setup)
    generated = flow.generate(job)
    image_path, _ = get_mock_artifact(app.state.job_store, job, "image")
    original = image_path.read_bytes()
    try:
        image_path.write_bytes(b"tampered owner output")
        with pytest.raises(Exception) as image_problem:
            flow.approve_image(job)
        assert_409(image_problem, "IMAGE_APPROVAL_HASH_MISMATCH")
        assert len(calls) == 1
    finally:
        image_path.write_bytes(original)
    flow.approve_image(job)
    assert len(calls) == 1
    original = image_path.read_bytes()
    try:
        image_path.write_bytes(b"tampered after approval")
        with pytest.raises(Exception) as final_problem:
            flow.compose(job, layout=layout())
        assert_409(final_problem, "APPROVED_IMAGE_CHANGED")
    finally:
        image_path.write_bytes(original)
    assert flow.compose(job, layout=layout())["status"] == "COMPLETED"


def test_offline_image_failclosed_on_false_vlm_and_error(setup):
    app, http, job, flow, calls = setup
    stage_and_approve(setup)
    # Stored owner input has a failure-style VLM envelope; must block before
    # any provider attempt. Changes are made ONLY in trusted staging before
    # approving; once approved, input is immutable.
    # Here we use an independent Job because active approved input is frozen.
    app2 = create_app(app.state.job_store.root.parent / "fail-jobs")
    with TestClient(app2) as h:
        created=h.post("/api/v1/jobs", files=[
            ("product_images",("a.png",png((30,20,40)),"image/png")),
            ("product_images",("b.png",png((40,30,20)),"image/png")),
        ])
        fail_job=created.json()["job_id"]
        h.post(f"/api/v1/jobs/{fail_job}/mock/plan",json={"brand_name":"라움","product_name":"크림"})
        h.post(f"/api/v1/jobs/{fail_job}/mock/copy")
        flow2=OfflineImageFlow(app2.state.job_store, adapter=flow.adapter,
                               project_id=PROJECT_ID, font_path=FONT)
        flow2.stage_copy(fail_job, copy_output=approved_copy(), copy_revision="r01",
                         product_analysis=analysis(succeeded=False),
                         image_prompt="밝은 배경")
        flow2.approve_fixture_copy(fail_job)
        from src.image_generation.errors import GatewayError
        with pytest.raises(GatewayError) as error:
            flow2.generate(fail_job)
        assert error.value.code == "PRODUCT_ANALYSIS_FAILED"
        assert h.get(f"/api/v1/jobs/{fail_job}").json()["status"]=="COPY_APPROVED"
        assert len(calls)==0


def test_replay_after_serving_job_save_failure_no_second_transport(setup, monkeypatch):
    from src.serving import job_store
    app, http, job, flow, calls = setup
    stage_and_approve(setup)
    replace_original = os.replace
    def fail_only_job_write(src,dst):
        if str(dst).endswith("/job.json"):
            raise OSError("simulated ledger persistence failure")
        return replace_original(src,dst)
    with monkeypatch.context() as mp:
        mp.setattr(job_store.os, "replace", fail_only_job_write)
        with pytest.raises(OSError,match="ledger persistence"):
            flow.generate(job)
    assert len(calls) == 1
    assert http.get(f"/api/v1/jobs/{job}").json()["status"]=="COPY_APPROVED"
    recreated = make_adapter(app.state.job_store.root.parent,
                             lambda req: (_ for _ in ()).throw(
                                 AssertionError("provider must never be re-run")
                             ))
    restarted = OfflineImageFlow.__new__(OfflineImageFlow)
    # Equivalent service restart: new JobStore and real owner attempt/binding files,
    # and adapter constructed with same durable paths.
    from src.serving.job_store import JobStore
    store2=JobStore(app.state.job_store.root)
    flow2=OfflineImageFlow(store2,adapter=recreated,project_id=PROJECT_ID,font_path=FONT)
    result=flow2.generate(job)
    assert result["status"]=="IMAGE_REVIEW_REQUIRED"
    assert len(calls)==1


def test_real_provider_configuration_is_refused_before_any_call(setup):
    app, http, job, flow, calls = setup
    from src.image_generation.openai_images import OpenAIImagesConfig
    class NotOffline:
        offline=False
        config=OpenAIImagesConfig(live_calls=True,api_key="dummy-test-only")
    class FakeProcessor:
        adapter=NotOffline()
    class UnsafeAdapter:
        processor=FakeProcessor()
    from src.serving.job_store import JobStore
    with pytest.raises(ValueError,match="OFFLINE_MOCK_TRANSPORT_REQUIRED"):
        OfflineImageFlow(JobStore(app.state.job_store.root.parent/"untrusted"),
                         adapter=UnsafeAdapter(),project_id=PROJECT_ID,font_path=FONT)
    assert len(calls)==0



def test_composition_store_failure_is_recoverable_without_second_owner_call(setup, monkeypatch):
    from src.serving import job_store
    app, http, job, flow, calls = setup
    stage_and_approve(setup)
    flow.generate(job)
    flow.approve_image(job)
    original_replace = os.replace
    def fail_ledger_commit(src, dst):
        if str(dst).endswith("/job.json"):
            raise OSError("simulated composition ledger failure")
        return original_replace(src, dst)
    with monkeypatch.context() as patch:
        patch.setattr(job_store.os, "replace", fail_ledger_commit)
        with pytest.raises(OSError, match="composition ledger failure"):
            flow.compose(job, layout=layout())
    assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "IMAGE_APPROVED"
    assert http.get(f"/api/v1/jobs/{job}/artifacts/final").status_code == 404
    assert http.get(f"/api/v1/jobs/{job}/artifacts/caption").status_code == 404
    assert flow.compose(job, layout=layout())["status"] == "COMPLETED"
    assert len(calls) == 1


def test_offline_unapproved_full_copy_and_duplicate_restage_block(setup):
    app, http, job, flow, calls = setup
    with pytest.raises(Exception) as unapproved:
        flow.generate(job)
    assert_409(unapproved, "COPY_NOT_APPROVED")
    flow.stage_copy(job, copy_output=approved_copy(), copy_revision="r01",
                    product_analysis=analysis(), image_prompt="한글 이미지 프롬프트")
    with pytest.raises(Exception) as unapproved2:
        flow.generate(job)
    assert_409(unapproved2, "COPY_NOT_APPROVED")
    assert flow.approve_fixture_copy(job)["status"]=="COPY_APPROVED"
    with pytest.raises(Exception) as locked:
        flow.stage_copy(job, copy_output=approved_copy(), copy_revision="r01",
                        product_analysis=analysis(), image_prompt="동일")
    assert_409(locked, "COPY_NOT_AWAITING_REVIEW")
    assert len(calls)==0


def test_exact_copy_full_hash_and_image_approval_reject_mismatch(setup):
    app, http, job, flow, calls = setup
    stage_and_approve(setup, revision=1)
    generated=flow.generate(job)
    original=app.state.job_store.get_job(job)
    # mutate image metadata only via direct test-file tamper, not through HTTP
    # This simulates a corrupt persisted image candidate with stale copy hash.
    path=app.state.job_store._job_dir(job)/"job.json"
    import json
    raw=path.read_text(encoding="utf-8")
    data=json.loads(raw)
    data["image_candidate"]["copy_hash"]="0"*64
    path.write_text(json.dumps(data, ensure_ascii=False),encoding="utf-8")
    with pytest.raises(Exception) as blocked:
        flow.approve_image(job)
    assert_409(blocked,"IMAGE_APPROVAL_HASH_MISMATCH")
    assert http.get(f"/api/v1/jobs/{job}").json()["status"]=="IMAGE_REVIEW_REQUIRED"
    path.write_text(raw,encoding="utf-8")
    assert flow.approve_image(job)["status"]=="IMAGE_APPROVED"
    assert flow.compose(job, layout=layout())["status"]=="COMPLETED"
    assert len(calls)==1


def test_image_source_stays_explicitly_offline_before_generation(setup):
    app, http, job, flow, calls = setup
    stage_and_approve(setup)
    assert flow.adapter.processor.adapter.offline is True
    object.__setattr__(flow.adapter.processor.adapter.config,"live_calls",True)
    with pytest.raises(Exception) as rejected:
        flow.generate(job)
    assert_409(rejected,"OFFLINE_PROVIDER_NOT_AVAILABLE")
    assert len(calls)==0
    assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_APPROVED"



def test_full_owner_copy_snapshot_tamper_blocks_generation_before_mocktransport(setup):
    import json
    app, http, job, flow, calls = setup
    stage_and_approve(setup)
    path = app.state.job_store._job_dir(job) / "job.json"
    before = path.read_text(encoding="utf-8")
    try:
        altered = json.loads(before)
        altered["offline_copy"]["copy_output"]["caption"] += " 조작된 광고 문구"
        path.write_text(json.dumps(altered, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(Exception) as blocked:
            flow.generate(job)
        assert_409(blocked, "FULL_COPY_HASH_MISMATCH")
        assert len(calls) == 0
        assert http.get(f"/api/v1/jobs/{job}").json()["status"] == "COPY_APPROVED"
    finally:
        path.write_text(before, encoding="utf-8")
