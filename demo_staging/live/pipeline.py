"""Official Text + Image Owner integration orchestrator with deferred provider imports.

Offline fixture exercises the SAME Owner DTO/Compliance/approval/composition
boundaries with an explicit OFFLINE_FIXTURE provenance. Never returns fixtures
as LIVE data. Live dispatch requires a trusted operator/PM budget permit and
durable attempt reservation *before* model client imports/network.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import UUID,uuid5

from PIL import Image

from src.text_generation.schemas import (
    ProductInput, ProductAnalysisResult, ResearchResult, AdCopyOutput,
    ImagePromptOutput, AdPlan
)
from src.serving.job_store import JobStore
from demo_staging.live_safety import AttemptLedger,LiveNotAuthorized
from .contracts import LiveGateError,digest
from .store import LiveStore
from .checkpoints import LiveCheckpoints


class TextProvider(Protocol):
    def analyze(self, images: list[bytes]): ...
    def research(self, product: ProductInput, analysis): ...
    def generate_copy(self, product: ProductInput, analysis, research): ...
    def generate_prompt(self, plan, analysis): ...


class OfficialTextProvider:
    """Only construct/execute inside a guarded worker. Import loads API client."""
    def __init__(self,text_model:str,vision_model:str):
        self.text_model,self.vision_model=text_model,vision_model

    def analyze(self,images):
        from src.text_generation.product_analyzer import analyze_product
        return analyze_product(images,model=self.vision_model)

    def research(self,product,analysis):
        from src.text_generation.researcher import research
        return research(product,analysis,model=self.text_model)

    def generate_copy(self,product,analysis,research_result):
        from src.text_generation.copy_generator import generate_copy
        return generate_copy(product,analysis,research_result,model=self.text_model)

    def generate_prompt(self,plan,analysis):
        from src.text_generation.image_prompt_generator import generate_image_prompt
        return generate_image_prompt(plan,analysis,model=self.text_model)


def atomic_write(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        os.chmod(f.name,0o600)
        f.write(data);f.flush();os.fsync(f.fileno())
        tmp=f.name
    os.replace(tmp,path)


class LivePipeline:
    def __init__(self,root:Path,job_store:JobStore,*,live_enabled=False,
                 pm_authorized=False,budget_limit_usd=0,
                 text_reservation_usd=0,image_reservation_usd=0,
                 request_limit=0,project_id:UUID|None=None,approved_actors:frozenset[str]|None=None):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.jobs=job_store
        self.state=LiveStore(self.root/"live.sqlite")
        self.checkpoints=LiveCheckpoints(self.root/"text_checkpoints.sqlite")
        self.cost=AttemptLedger(self.root/"cost.sqlite",live_enabled=live_enabled,
                                max_requests=request_limit,budget_usd=budget_limit_usd)
        self.live_enabled=bool(live_enabled)
        self.approved_actors=frozenset(approved_actors or ())
        self.pm_authorized=bool(pm_authorized)
        self.text_reservation=float(text_reservation_usd)
        self.image_reservation=float(image_reservation_usd)
        self.project_id=project_id or uuid5(UUID("00000000-0000-0000-0000-000000000001"),"ittem-live-isolated")

    def _photos(self,job_id,expected_hashes):
        assets=self.jobs.get_job(job_id)["assets"]
        expected={a["asset_id"]:a for a in expected_hashes}
        if [x["asset_id"] for x in assets]!=[x["asset_id"] for x in expected_hashes]:
            raise LiveGateError("INPUT_ASSET_LIST_CHANGED")
        product=[];refs=[]
        for a in assets:
            path,_=self.jobs.get_asset(job_id,a["asset_id"])
            raw=path.read_bytes()
            if (hashlib.sha256(raw).hexdigest()!=a["sha256"]
                    or expected[a["asset_id"]]["sha256"]!=a["sha256"]):
                raise LiveGateError("INPUT_ASSET_TAMPERED")
            (product if a["role"]=="product" else refs).append(raw)
        if not 2<=len(product)<=5 or len(refs)>5:
            raise LiveGateError("INPUT_PHOTO_COUNTS_INVALID")
        return product,refs

    def prepare(self,actor,job_id,payload):
        job=self.jobs.get_job(job_id)
        if job["status"]!="INPUTS_VALIDATED":
            raise LiveGateError("B0_JOB_NOT_INPUT_READY")
        return self.state.create(actor,job_id,payload,job["assets"])

    def _guarded(self,actor,job_id,stage,payload,action,*,image=False):
        # No key/client/import/provider even attempted before this transaction.
        cost=self.image_reservation if image else self.text_reservation
        record=self.cost.reserve(
            actor=actor,role="live_operator",job_id=job_id,stage=stage,
            payload=payload,estimated_usd=cost,pm_authorized=self.pm_authorized)
        if not record["new"]:
            raise LiveNotAuthorized("ATTEMPT_EXISTS_NO_AUTOMATIC_RETRY")
        self.cost.dispatch_intent(record["id"])
        from .provider_receipts import collect_receipts
        try:
            with collect_receipts() as captured:
                result=action()
        except BaseException:
            self.cost.mark_billing_unknown(record["id"])
            raise LiveGateError("PROVIDER_RESULT_UNKNOWN") from None
        # Official Image Owner returns its own durable paid attempt receipt.
        # Text Owner uses the isolated sanitized response-usage hook.
        receipts=list(captured.events)
        image_receipt=getattr(result,"receipt",None)
        if image and isinstance(image_receipt,dict):
            if (getattr(result,"mock",True) is False
                and image_receipt.get("submission_status")=="RESPONSE_RECEIVED"
                and image_receipt.get("state")=="succeeded"
                and image_receipt.get("provider_request_id")
                and isinstance(image_receipt.get("usage"),dict)):
                receipts=[{"provider":"openai","model":image_receipt.get("model"),
                  "provider_response_id":image_receipt["provider_request_id"],
                  "usage":image_receipt["usage"],
                  "billing_status":"UNPRICED_RESERVATION_HELD"}]
        if len(receipts)!=1:
            self.cost.mark_billing_unknown(record["id"])
            raise LiveGateError("PROVIDER_BILLING_RECONCILIATION_REQUIRED")
        try:
            self.cost.confirm_usage_unpriced(record["id"],receipts[0])
        except LiveNotAuthorized:
            self.cost.mark_billing_unknown(record["id"])
            raise LiveGateError("PROVIDER_BILLING_RECONCILIATION_REQUIRED") from None
        # The reserved USD remains held until provider invoice reconciliation;
        # no replays, no fabricated 'actual cost' claim.
        return result

    def text(self,actor,job_id,provider:TextProvider|None=None,*,offline=False,
             text_model="gpt-6-luna",vision_model="gpt-6-luna"):
        job=self.state.get(actor,job_id)
        if job["state"]!="INPUT_STORED":
            raise LiveGateError("TEXT_STATE_CONFLICT")
        snapshot=json.loads(job["input_json"])
        product=ProductInput.model_validate(snapshot["product"],strict=True)
        photos,_=self._photos(job_id,snapshot["ordered_asset_hashes"])
        if offline:
            if provider is None:raise LiveGateError("OFFLINE_FAKE_REQUIRED")
        else:
            if not (self.live_enabled and self.pm_authorized):
                raise LiveNotAuthorized("LIVE_NOT_APPROVED")
            if provider is not None:
                raise LiveGateError("INJECTED_PROVIDER_FORBIDDEN_IN_LIVE")
            provider=OfficialTextProvider(text_model,vision_model)
        mode="OFFLINE_FIXTURE" if offline else "LIVE"
        def call(stage,data,model,callback):
            # A stored, verified Owner output may be replayed with zero new calls.
            fingerprint=digest(data)
            saved=self.checkpoints.load(actor,job_id,stage,fingerprint,mode,model)
            if saved is not None:
                return saved
            output=callback() if offline else self._guarded(actor,job_id,stage,data,callback)
            return self.checkpoints.commit(actor,job_id,stage,fingerprint,mode,output,model)
        a=call("vision",
               {"input_sha":job["input_sha"],
                "assets":[x["sha256"] for x in snapshot["ordered_asset_hashes"]],
                "model":vision_model},
               ProductAnalysisResult,lambda:provider.analyze(photos))
        if (a.analysis_succeeded is not True or a.error is not None
            or a.analysis.is_cosmetic is not True):
            raise LiveGateError("VLM_FAIL_CLOSED")
        r=call("research",{"input_sha":job["input_sha"],"analysis_sha":digest(a.model_dump(mode="json")),
                           "model":text_model},
               ResearchResult,lambda:provider.research(product,a.analysis))
        cp=call("copy",{"input_sha":job["input_sha"],
                         "analysis_sha":digest(a.model_dump(mode="json")),
                         "research_sha":digest(r.model_dump(mode="json")),
                         "model":text_model},
                AdCopyOutput,lambda:provider.generate_copy(product,a.analysis,r))
        return self.state.store_text(
            actor,job_id,a,r,cp,mode=mode)

    def prompt(self,actor,job_id,provider:TextProvider|None=None,*,offline=False,
               text_model="gpt-6-luna"):
        job=self.state.get(actor,job_id)
        if job["state"]!="COPY_APPROVED":
            raise LiveGateError("PROMPT_REQUIRES_APPROVED_COPY")
        self.state._approved(job)
        if offline:
            if provider is None:raise LiveGateError("OFFLINE_FAKE_REQUIRED")
        else:
            if not (self.live_enabled and self.pm_authorized):
                raise LiveNotAuthorized("LIVE_NOT_APPROVED")
            if provider is not None:
                raise LiveGateError("INJECTED_PROVIDER_FORBIDDEN_IN_LIVE")
            provider=OfficialTextProvider(text_model,text_model)
        cp=json.loads(job["copy_json"])
        a=ProductAnalysisResult.model_validate(json.loads(job["analysis_json"]),strict=True)
        mode="OFFLINE_FIXTURE" if offline else "LIVE"
        ctx={"copy_sha":job["copy_sha"],"generation":job["generation"],
             "approval_sha":job["approval_sha"],"model":text_model}
        fingerprint=digest(ctx)
        out=self.checkpoints.load(actor,job_id,"image_prompt",fingerprint,mode,
                                  ImagePromptOutput)
        if out is None:
            def do_prompt():
                return provider.generate_prompt(
                    AdPlan.model_validate(cp["plan"],strict=True),a.analysis)
            proposed=do_prompt() if offline else self._guarded(actor,job_id,
                "image_prompt",ctx,do_prompt)
            out=self.checkpoints.commit(actor,job_id,"image_prompt",fingerprint,
                                        mode,proposed,ImagePromptOutput)
        return self.state.store_prompt(actor,job_id,out)

    def image_input(self,actor,job_id):
        job=self.state.get(actor,job_id)
        snapshot=json.loads(job["input_json"])
        photos,refs=self._photos(job_id,snapshot["ordered_asset_hashes"])
        return self.state.image_request(actor,job_id,photos,refs)

    def accept_image_result(self,actor,job_id,output,*,offline=False):
        job=self.state.get(actor,job_id)
        if job["state"]!="PROMPT_READY":
            raise LiveGateError("IMAGE_NOT_READY")
        if bool(output.mock)!=bool(offline):
            raise LiveGateError("IMAGE_MODE_MISMATCH")
        if output.job_id!=job_id or output.copy_revision!=job["generation"] or output.copy_hash!=job["copy_sha"]:
            raise LiveGateError("IMAGE_BINDING_MISMATCH")
        if not output.receipt:
            raise LiveGateError("PROVIDER_RECEIPT_REQUIRED")
        sha=hashlib.sha256(output.image_bytes).hexdigest()
        if sha!=output.sha256:
            raise LiveGateError("IMAGE_HASH_MISMATCH")
        with Image.open(BytesIO(output.image_bytes)) as im:
            if (im.format!="PNG" or im.size!=(1152,1440)
                    or (output.width,output.height)!=im.size):
                raise LiveGateError("OWNER_IMAGE_SIZE_INVALID")
        atomic_write(self.image_path(job_id),output.image_bytes)
        return self.state.store_image_candidate(actor,job_id,sha)

    def image_path(self,job_id):
        if not len(job_id)==32 or not all(x in "0123456789abcdef" for x in job_id):
            raise LiveGateError("JOB_ID_INVALID")
        return self.root/"outputs"/job_id/"image.png"

    def compose(self,actor,job_id,*,layout,font_path):
        from src.image_generation import compose_ad_png,CompositionInput
        job=self.state.get(actor,job_id)
        if job["state"]!="IMAGE_APPROVED":
            raise LiveGateError("FINAL_REQUIRES_IMAGE_APPROVAL")
        self.state._approved(job)
        path=self.image_path(job_id)
        raw=path.read_bytes()
        image_sha=hashlib.sha256(raw).hexdigest()
        if image_sha!=job["image_sha"]:
            raise LiveGateError("IMAGE_BYTES_CHANGED")
        cp=json.loads(job["copy_json"])
        input_obj=CompositionInput(
            job_id=job_id,image_bytes=raw,image_sha256=image_sha,
            copy_revision=job["generation"],copy_hash=job["copy_sha"],
            copy_output=cp,layout=layout)
        result=compose_ad_png(input_obj,font_path=Path(font_path))
        if (result.copy_hash!=job["copy_sha"] or result.copy_revision!=job["generation"]
            or result.source_image_sha256!=image_sha
            or hashlib.sha256(result.image_bytes).hexdigest()!=result.sha256
            or (result.width,result.height)!=(1080,1350)):
            raise LiveGateError("COMPOSED_RESULT_BINDING_FAILED")
        directory=self.root/"outputs"/job_id
        atomic_write(directory/"final.png",result.image_bytes)
        atomic_write(directory/"caption.txt",result.caption_bytes)
        return self.state.composed(actor,job_id,result.sha256,hashlib.sha256(result.caption_bytes).hexdigest())
