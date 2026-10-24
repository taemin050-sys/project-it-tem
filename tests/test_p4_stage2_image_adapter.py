from io import BytesIO
import json
from pathlib import Path
from PIL import Image
import pytest
from fastapi import HTTPException

from src.serving.p4_image_adapter import (GeneratedImage, generate_handoff, verify_image)
from src.serving.p4_cost_guard import P4CostGuard
from src.serving.provisional_contracts import VisualBrief

FIXTURES = Path(__file__).parent / "contracts" / "fixtures"


def png():
    f = BytesIO()
    Image.new("RGB", (64, 96), "blue").save(f, format="PNG")
    return f.getvalue()


def brief():
    return VisualBrief.model_validate_json((FIXTURES / "visual_brief.json").read_text())


def guard(tmp_path):
    return P4CostGuard(tmp_path / "private" / "ledger.sqlite3",
                       max_budget_micro_usd=1_000_000, enable_billable=True)


class FakeImageGenerator:
    def __init__(self, *, mock=True, image=None):
        self.mock = mock
        self.image = image or png()
        self.called = 0
    def generate(self, brief, product_images, reference_images):
        self.called += 1
        assert brief.copy_revision > 0 and len(product_images) == 1
        return GeneratedImage(data=self.image, content_type="image/png", mock=self.mock)


def invoke(tmp_path, *, generator=None, price=0, assets=None, operation_key="image_req_001"):
    candidate = brief()
    return generate_handoff(generator=generator or FakeImageGenerator(), brief=candidate,
                            assets=assets or {candidate.product_asset_ids[0]: png()},
                            guard=guard(tmp_path), operation_key=operation_key,
                            max_cost_micro_usd=price)


def test_fake_image_returns_strict_result_and_receipt(tmp_path):
    out = invoke(tmp_path)
    assert out.result.mock and (out.result.width, out.result.height) == (64, 96)
    assert out.result.preservation_review == "pending"
    assert out.receipt.billing_state == "not_called"
    assert out.result.sha256 and out.bytes_data.startswith(b"\x89PNG")


def test_live_adapter_stub_reports_uncertain_billing(tmp_path):
    out = invoke(tmp_path, generator=FakeImageGenerator(mock=False), price=500000)
    assert not out.result.mock
    assert out.receipt.billing_state == "unknown"
    assert guard(tmp_path).snapshot()[0]["reserved_micro_usd"] == 500000


def test_duplicate_dispatched_image_is_blocked(tmp_path):
    g = FakeImageGenerator()
    invoke(tmp_path, generator=g)
    with pytest.raises(HTTPException) as e:
        invoke(tmp_path, generator=g)
    assert e.value.status_code == 409 and g.called == 1


def test_missing_product_fails_before_reservation(tmp_path):
    with pytest.raises(KeyError):
        invoke(tmp_path, assets={"not-the-id": png()})
    assert guard(tmp_path).snapshot() == []


@pytest.mark.parametrize("item", [GeneratedImage(b"garbage", "image/png", True),
    GeneratedImage(png(), "image/jpeg", True),
    GeneratedImage(b"", "image/png", True),
    GeneratedImage(png(), "image/gif", True)])
def test_bad_wrapper_result_never_accepted(item):
    from src.serving.p4_cost_guard import ProviderInvalidResponse
    with pytest.raises(ProviderInvalidResponse):
        verify_image(item)


def test_mock_live_mismatch_blocks_and_records_uncertain(tmp_path):
    with pytest.raises(HTTPException) as e:
        invoke(tmp_path, generator=FakeImageGenerator(mock=True), price=800)
    assert e.value.status_code == 502
    row, = guard(tmp_path).snapshot()
    assert row["status"] == "unknown"


def test_approved_copy_is_contract_requirements_not_asserted_here():
    # Calling adapter directly does not authenticate/approve a JobStore status.
    # Wiring into HTTP must verify COPY_APPROVED before entering generate_handoff.
    assert brief().copy_revision >= 1
