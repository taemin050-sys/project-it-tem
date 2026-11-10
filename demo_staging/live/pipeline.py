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
    ImagePromptOutput, AdPlan, CopyRevisionOutput, ComplianceIssue, ComplianceReport
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
    def revise_copy(self,product,analysis,research,previous,instruction,
                    *,issues:list[ComplianceIssue]|None=None): ...


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

    def revise_copy(self,product,analysis,research,previous,instruction,
                    *,issues:list[ComplianceIssue]|None=None):
        from src.text_generation.copy_generator import revise_copy
        return revise_copy(product,analysis,research,previous,instruction,
                           issues=issues,model=self.text_model)


def atomic_write(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            tmp=f.name
            os.chmod(tmp,0o600)
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    # Durably commit the rename itself, not just the staged file bytes.
    if hasattr(os, "O_DIRECTORY"):
        try:
            descriptor=os.open(path.parent,os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            pass
        else:
            try:os.fsync(descriptor)
            finally:os.close(descriptor)


class LivePipeline:
    def __init__(self,root:Path,job_store:JobStore,*,live_enabled=False,
                 pm_authorized=False,budget_limit_usd=0,
                 text_reservation_usd=0,image_reservation_usd=0,
                 request_limit=0,project_id:UUID|None=None,approved_actors:frozenset[str]|None=None,
                 monitoring_only=False):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.jobs=job_store
        self.state=LiveStore(self.root/"live.sqlite")
        self.checkpoints=LiveCheckpoints(self.root/"text_checkpoints.sqlite")
        self.cost=AttemptLedger(self.root/"cost.sqlite",live_enabled=live_enabled,
                                max_requests=request_limit,budget_usd=budget_limit_usd,
                                monitoring_only=monitoring_only)
        self.live_enabled=bool(live_enabled)
        self.monitoring_only=bool(monitoring_only)
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

    def prepare(self,actor,job_id,payload,*,template_profile="LEGACY"):
        job=self.jobs.get_job(job_id)
        if job["status"]!="INPUTS_VALIDATED":
            raise LiveGateError("B0_JOB_NOT_INPUT_READY")
        return self.state.create(actor,job_id,payload,job["assets"],
                                 template_profile=template_profile)

    def _guarded(self,actor,job_id,stage,payload,action,*,image=False):
        # Worker dispatch reauthorizes at the actual provider boundary.
        # Direct isolated unit usage is not an activated worker.
        claim=getattr(self,"_worker_claim",None)
        if claim is not None:
            from .worker import authorize_worker_item
            if claim["actor"]!=actor or claim["job_id"]!=job_id:
                raise LiveGateError("WORKER_CLAIM_PRINCIPAL_MISMATCH")
            authorize_worker_item(self,claim)
        # No key/client/import/provider even attempted before this transaction.
        cost=self.image_reservation if image else self.text_reservation
        record=self.cost.reserve(
            actor=actor,role="live_operator",job_id=job_id,stage=stage,
            payload=payload,estimated_usd=cost,pm_authorized=self.pm_authorized)
        if not record["new"]:
            raise LiveNotAuthorized("ATTEMPT_EXISTS_NO_AUTOMATIC_RETRY")
        if claim is not None:
            from .worker import authorize_worker_item
            authorize_worker_item(self,claim)
        self.cost.dispatch_intent(record["id"])
        from .provider_receipts import collect_receipts
        try:
            with collect_receipts() as captured:
                if claim is not None:
                    from .worker import authorize_worker_item
                    authorize_worker_item(self,claim)
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
                and image_receipt.get("state")=="succeeded"
                and image_receipt.get("attempt_id")
                and image_receipt.get("model")
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

    def revision_context(self,actor,job_id,instruction,
                         expected_generation,expected_review_sha,*,text_model="gpt-6-luna"):
        """Preflight without model imports, reservation, external calls or writes."""
        job=self.state.get(actor,job_id)
        if (job["state"]!="COPY_REVIEW_REQUIRED" or job["mode"] not in
            ("LIVE","OFFLINE_FIXTURE")):
            raise LiveGateError("COPY_REVISION_STATE_CONFLICT")
        if (type(expected_generation) is not int or
            type(expected_review_sha) is not str or
            job["generation"]!=expected_generation or
            job["review_sha"]!=expected_review_sha):
            raise LiveGateError("STALE_REVIEW_OR_REVISION")
        if (type(instruction) is not str or
            not 1<=len(instruction.strip())<=300 or
            instruction!=instruction.strip()):
            raise LiveGateError("REVISION_INSTRUCTION_INVALID")
        report=json.loads(job["compliance_json"])
        analysis=json.loads(job["analysis_json"])
        current_copy=json.loads(job["copy_json"])
        # The review proof binds exactly the report the user saw, not a
        # stale saved issue list or a newly inferred regulatory verdict.
        from src.image_generation.contracts import content_hash
        if (content_hash(current_copy)!=job["copy_sha"] or
            digest({"input_sha":job["input_sha"],"analysis":analysis,
                    "copy":current_copy,"report":report,
                    "generation":job["generation"]})!=job["review_sha"]):
            raise LiveGateError("REVISION_REVIEW_CONTEXT_INTEGRITY_FAILED")
        issues=[{k:record.get(k) for k in (
            "field","text","risk_level","reason","suggestion","basis")}
            for record in report.get("issues",[])]
        return {
            "job_id":job_id,"generation":job["generation"],
            "review_sha":job["review_sha"],"copy_sha":job["copy_sha"],
            "input_sha":job["input_sha"],"instruction":instruction,
            "model":text_model,
            "compliance_context_contract":"BP13_OWNER_TEXT_PROPOSED_V1",
            "compliance_report_sha":digest(report),
            "compliance_issues":issues,
            "basis_verification":"UNVERIFIED_FREE_TEXT_NOT_LEGAL_ADVICE",
        }

    def revise_copy(self,actor,job_id,instruction,expected_generation,
                    expected_review_sha,provider:TextProvider|None=None,*,offline=False,
                    text_model="gpt-6-luna"):
        """Owner #25 instruction-aware revision + mandatory rule re-review.

        Live uses the same one-shot signed worker/Attempt Ledger as all Text
        stages; paid calls are never performed by this method when disabled.
        QA can inject a fake ONLY with explicit offline=True and remains
        OFFLINE_FIXTURE in all stored snapshots.
        """
        context=self.revision_context(
            actor,job_id,instruction,expected_generation,expected_review_sha,
            text_model=text_model)
        job=self.state.get(actor,job_id)
        # Owner #27 issues must come from the CURRENT, SHA-verified review,
        # not an untrusted browser DTO or old pre-revision review. Recheck
        # after the context read to prevent a stale actor/job tuple being
        # used for the paid one-shot revision.
        report_payload=json.loads(job["compliance_json"])
        if (job["generation"]!=context["generation"] or
            job["review_sha"]!=context["review_sha"] or
            job["copy_sha"]!=context["copy_sha"] or
            digest(report_payload)!=context["compliance_report_sha"]):
            raise LiveGateError("REVISION_REVIEW_CONTEXT_INTEGRITY_FAILED")
        review_issues=ComplianceReport.model_validate(
            report_payload,strict=True).issues
        if bool(offline)!=(job["mode"]=="OFFLINE_FIXTURE"):
            raise LiveGateError("COPY_REVISION_PROVENANCE_MISMATCH")
        if offline:
            if provider is None:
                raise LiveGateError("OFFLINE_FAKE_REQUIRED")
        else:
            if not (self.live_enabled and self.pm_authorized and actor in self.approved_actors):
                raise LiveNotAuthorized("LIVE_NOT_APPROVED")
            if provider is not None:
                raise LiveGateError("INJECTED_PROVIDER_FORBIDDEN_IN_LIVE")
            provider=OfficialTextProvider(text_model,text_model)

        from src.serving.text_v08_mapper import verify_analysis,verify_research,verify_copy
        product=ProductInput.model_validate(
            json.loads(job["input_json"])["product"],strict=True)
        analysis=ProductAnalysisResult.model_validate(json.loads(job["analysis_json"]),strict=True)
        if analysis.analysis_succeeded is not True or analysis.error is not None:
            raise LiveGateError("VLM_FAIL_CLOSED")
        research=ResearchResult.model_validate(json.loads(job["research_json"]),strict=True)
        previous=AdCopyOutput.model_validate(json.loads(job["copy_json"]),strict=True)
        fingerprint=digest(context)
        mode="OFFLINE_FIXTURE" if offline else "LIVE"
        result=self.checkpoints.load(actor,job_id,"copy_revision",
                                     fingerprint,mode,CopyRevisionOutput)
        if result is None:
            # Existing FakeOwners keep the 5-argument fixture interface.
            # LIVE always constructs OfficialTextProvider, whose Owner #27
            # signature explicitly accepts the structured ComplianceIssues.
            if offline:
                action=lambda:provider.revise_copy(
                    product,analysis.analysis,research,previous,instruction)
            else:
                action=lambda:provider.revise_copy(
                    product,analysis.analysis,research,previous,instruction,
                    issues=review_issues)
            proposed=(action() if offline else
                self._guarded(actor,job_id,"copy_revision",context,action))
            result=self.checkpoints.commit(
                actor,job_id,"copy_revision",fingerprint,mode,
                proposed,CopyRevisionOutput)
        old=previous.model_dump(mode="json")
        revised=result.revised.model_dump(mode="json")
        actual=(
            (["plan"] if revised["plan"]!=old["plan"] else [])+
            [field for field in ("headline","subline","cta")
             if revised["ad_copy"][field]!=old["ad_copy"][field]]+
            [field for field in ("caption","hashtags")
             if revised[field]!=old[field]])
        if actual!=result.changed_fields and set(actual)!=set(result.changed_fields):
            raise LiveGateError("REVISION_CHANGED_FIELDS_INVALID")
        # A refusal/no-op is a legitimate, billable Owner response, but not
        # a new Copy version. The Store compares review-policy output atomically.
        if not actual and not result.note:
            result.note="수정된 항목이 없습니다. 기존 카피와 검수 상태를 유지합니다."
        feedback={
            "note":result.note,"changed_fields":result.changed_fields,
            "context_sha":fingerprint,
            "source":("OWNER_TEXT_V010_OFFLINE" if offline else "OWNER_TEXT_V010_LIVE"),
        }
        return self.state.apply_copy_revision(
            actor,job_id,revised,instruction,
            expected_generation,expected_review_sha,owner_feedback=feedback)

    def _assert_live_prompt_sources(self,actor,job_id,job,*,text_model,vision_model):
        """Verify immutable LIVE Owner Text checkpoints, never fixture-derived.

        A manually edited mode='LIVE' cannot promote OFFLINE_FIXTURE
        Analysis/Research/Copy into a paid Prompt stage.
        """
        if job["mode"]!="LIVE":
            raise LiveGateError("PROMPT_LIVE_SOURCE_PROVENANCE_INVALID")
        snapshot=json.loads(job["input_json"])
        a=json.loads(job["analysis_json"])
        r=json.loads(job["research_json"])
        cp=json.loads(job["copy_json"])
        photo_hashes=[item["sha256"] for item in snapshot["ordered_asset_hashes"]]
        analysis_ctx={"input_sha":job["input_sha"],"assets":photo_hashes,
                      "model":vision_model}
        try:
            verified_a=self.checkpoints.load(actor,job_id,"vision",digest(analysis_ctx),
                                             "LIVE",ProductAnalysisResult)
            if verified_a is None or verified_a.model_dump(mode="json")!=a:
                raise LiveGateError("PROMPT_LIVE_SOURCE_ANALYSIS_UNVERIFIED")
            research_ctx={"input_sha":job["input_sha"],"analysis_sha":digest(a),
                          "model":text_model}
            verified_r=self.checkpoints.load(actor,job_id,"research",digest(research_ctx),
                                             "LIVE",ResearchResult)
            if verified_r is None or verified_r.model_dump(mode="json")!=r:
                raise LiveGateError("PROMPT_LIVE_SOURCE_RESEARCH_UNVERIFIED")
            copy_ctx={"input_sha":job["input_sha"],"analysis_sha":digest(a),
                      "research_sha":digest(r),"model":text_model}
            verified_cp=self.checkpoints.load(actor,job_id,"copy",digest(copy_ctx),
                                              "LIVE",AdCopyOutput)
            if verified_cp is None or verified_cp.model_dump(mode="json")!=cp:
                raise LiveGateError("PROMPT_LIVE_SOURCE_COPY_UNVERIFIED")
        except LiveGateError as exc:
            raise LiveGateError("PROMPT_LIVE_SOURCE_PROVENANCE_INVALID") from None

    def prompt(self,actor,job_id,provider:TextProvider|None=None,*,offline=False,
               text_model="gpt-6-luna"):
        job=self.state.get(actor,job_id)
        if job["state"]!="COPY_APPROVED":
            raise LiveGateError("PROMPT_REQUIRES_APPROVED_COPY")
        self.state._approved(job)
        if (job["mode"]=="OFFLINE_FIXTURE")!=bool(offline) or job["mode"] not in (
                "LIVE","OFFLINE_FIXTURE"):
            raise LiveGateError("PROMPT_JOB_PROVENANCE_MISMATCH")
        # Pin approval, original analysis/research/ad plan and effective
        # policy epoch at the SAME time before any provider is constructed.
        expected=self.state.prompt_context(actor,job_id)
        # The preflight snapshot may have changed between get() and CAS read.
        # Never feed an old Plan/Analysis into a newly approved Prompt.
        if (expected["mode"]!=job["mode"] or
                expected["copy_sha"]!=job["copy_sha"] or
                expected["review_sha"]!=job["review_sha"] or
                expected["approval_sha"]!=job["approval_sha"] or
                expected["generation"]!=job["generation"] or
                expected["analysis_sha"]!=digest(json.loads(job["analysis_json"])) or
                expected["research_sha"]!=digest(json.loads(job["research_json"]))):
            raise LiveGateError("PROMPT_START_CONTEXT_CAS_FAILED")
        if offline:
            if provider is None:raise LiveGateError("OFFLINE_FAKE_REQUIRED")
        else:
            if not (self.live_enabled and self.pm_authorized and actor in self.approved_actors):
                raise LiveNotAuthorized("LIVE_NOT_APPROVED")
            if provider is not None:
                raise LiveGateError("INJECTED_PROVIDER_FORBIDDEN_IN_LIVE")
            self._assert_live_prompt_sources(actor,job_id,job,text_model=text_model,
                vision_model=os.environ.get("IT_TEM_VISION_MODEL","gpt-6-luna"))
            provider=OfficialTextProvider(text_model,text_model)
        cp=json.loads(job["copy_json"])
        a=ProductAnalysisResult.model_validate(json.loads(job["analysis_json"]),strict=True)
        mode="OFFLINE_FIXTURE" if offline else "LIVE"
        ctx={**expected,"model":text_model}
        fingerprint=digest(ctx)
        out=self.checkpoints.load(actor,job_id,"image_prompt",fingerprint,mode,
                                  ImagePromptOutput)
        if out is None:
            def do_prompt():
                return provider.generate_prompt(
                    AdPlan.model_validate(cp["plan"],strict=True),a.analysis)
            # A paid attempt/usage receipt is durably written within _guarded.
            # If approval/policy changes during I/O, CAS refuses stale result,
            # and NO second paid retry is automatic.
            out=do_prompt() if offline else self._guarded(actor,job_id,
                "image_prompt",ctx,do_prompt)
            # Commit Job first. A crash between Job CAS and checkpoint cannot
            # replay the provider because Job is already PROMPT_READY.
            result=self.state.store_prompt(actor,job_id,out,
                                           expected_context=expected)
            self.checkpoints.commit(actor,job_id,"image_prompt",fingerprint,
                                    mode,out,ImagePromptOutput)
            return result
        return self.state.store_prompt(actor,job_id,out,
                                       expected_context=expected)

    def begin_image_retry(self,actor,job_id,expected_sha,request_key):
        """Explicit rejection recovery. No Text/VLM/Research/Prompt rerun."""
        current=self.state.get(actor,job_id)
        prior=self.state.current_image_attempt(actor,job_id)
        if (current["state"]=="PROMPT_READY" and prior and
            prior["request_key"]==request_key and prior["state"]=="REQUESTED"):
            return prior
        if current["state"]!="IMAGE_REJECTED" or current["image_sha"]!=expected_sha:
            raise LiveGateError("IMAGE_RETRY_STALE_REJECTION")
        original=self.image_path(job_id)
        try:raw=original.read_bytes()
        except OSError:raise LiveGateError("REJECTED_IMAGE_BYTES_UNAVAILABLE") from None
        if hashlib.sha256(raw).hexdigest()!=expected_sha:
            raise LiveGateError("REJECTED_IMAGE_INTEGRITY_FAILED")
        version=prior["attempt_version"] if prior else 1
        archive=self.root/"outputs"/job_id/"attempts"/f"v{version}-{expected_sha}.png"
        if archive.exists():
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected_sha:
                raise LiveGateError("REJECTED_IMAGE_ARCHIVE_CHANGED")
        else:
            atomic_write(archive,raw)
        if json.loads(current["input_json"]).get("generation_mode")=="freeform":
            receipt_file=self.root/"outputs"/job_id/"owner_candidate_receipt.json"
            try:receipt_bytes=receipt_file.read_bytes()
            except OSError:raise LiveGateError("REJECTED_RECEIPT_UNAVAILABLE") from None
            if (prior is None or prior["candidate_receipt_sha"] is None or
                hashlib.sha256(receipt_bytes).hexdigest()!=prior["candidate_receipt_sha"]):
                raise LiveGateError("REJECTED_RECEIPT_INTEGRITY_FAILED")
            archived_receipt=self.root/"outputs"/job_id/"attempts"/f"v{version}-receipt.json"
            if archived_receipt.exists():
                if hashlib.sha256(archived_receipt.read_bytes()).hexdigest()!=prior["candidate_receipt_sha"]:
                    raise LiveGateError("REJECTED_RECEIPT_ARCHIVE_CHANGED")
            else:
                atomic_write(archived_receipt,receipt_bytes)
        return self.state.begin_image_retry(actor,job_id,expected_sha,request_key)

    def image_input(self,actor,job_id):
        job=self.state.get(actor,job_id)
        snapshot=json.loads(job["input_json"])
        from .contracts import assert_single_image_scope
        assert_single_image_scope(snapshot)
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
        mode=json.loads(job["input_json"]).get("generation_mode","composed")
        if mode=="freeform" and (output.receipt.get("generation_mode")!="freeform"
               or output.receipt.get("state")!="succeeded"):
            raise LiveGateError("FREEFORM_OWNER_RECEIPT_UNVERIFIED")
        sha=hashlib.sha256(output.image_bytes).hexdigest()
        if sha!=output.sha256:
            raise LiveGateError("IMAGE_HASH_MISMATCH")
        owner_request=self.image_input(actor,job_id)
        if owner_request.layout_selection is not None:
            from src.image_generation.size_selection import resolve_size_choice
            _,profile=resolve_size_choice(owner_request.layout_selection.aspect_ratio)
            expected_native=profile.native
        else:
            expected_native=(1152,1440)
        with Image.open(BytesIO(output.image_bytes)) as im:
            if (im.format!="PNG" or im.size!=expected_native
                    or (output.width,output.height)!=im.size):
                raise LiveGateError("OWNER_IMAGE_SIZE_INVALID")
        receipt_sha=None
        if mode=="freeform":
            receipt={"source_sha256":sha,"copy_sha":job["copy_sha"],
                     "generation":job["generation"],"owner_receipt":output.receipt}
            receipt_bytes=json.dumps(receipt,sort_keys=True,ensure_ascii=False).encode("utf-8")
            receipt_sha=hashlib.sha256(receipt_bytes).hexdigest()
            atomic_write(self.root/"outputs"/job_id/"owner_candidate_receipt.json",
                         receipt_bytes)
        atomic_write(self.image_path(job_id),output.image_bytes)
        provider_id=output.receipt.get("attempt_id")
        if provider_id is not None and not isinstance(provider_id,str):
            raise LiveGateError("IMAGE_PROVIDER_ATTEMPT_INVALID")
        return self.state.store_image_candidate(actor,job_id,sha,
                provider_attempt_id=provider_id,candidate_receipt_sha=receipt_sha)

    def image_path(self,job_id):
        if not len(job_id)==32 or not all(x in "0123456789abcdef" for x in job_id):
            raise LiveGateError("JOB_ID_INVALID")
        return self.root/"outputs"/job_id/"image.png"

    def validate_final_artifacts(self,actor,job_id):
        """Owner-scoped fail-closed GET validation including manifest if present."""
        job=self.state.get(actor,job_id)
        if job["state"]!="COMPLETED":
            raise LiveGateError("LIVE_OUTPUT_NOT_COMPLETED")
        files=self.root/"outputs"/job_id
        if not job["final_sha"] or not job["caption_sha"]:
            raise LiveGateError("FINAL_IDENTITY_MISSING")
        for filename,expected in (("final.png",job["final_sha"]),
                                  ("caption.txt",job["caption_sha"])):
            path=files/filename
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                    raise ValueError
            except (OSError,ValueError):
                raise LiveGateError("FINAL_ARTIFACT_INTEGRITY_FAILED") from None
        manifest=self.state.read_manifest(actor,job_id)
        if manifest is not None:
            path=files/"receipt.json"
            try:
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=manifest["receipt_sha"]:
                    raise ValueError
                if json.loads(data)!=manifest["receipt"]:
                    raise ValueError
            except (OSError,ValueError):
                raise LiveGateError("COMPOSITION_RECEIPT_INTEGRITY_FAILED") from None
        return job

    def compose(self,actor,job_id,*,layout=None,font_path):
        from src.image_generation import compose_ad_png,CompositionInput
        from .template_contract import canonical
        before=self.state.get(actor,job_id)
        selected_mode=json.loads(before["input_json"]).get("generation_mode","composed")
        if selected_mode=="freeform" and layout is not None:
            raise LiveGateError("FREEFORM_MUST_NOT_COMPOSE_TEXT")
        font=Path(font_path) if font_path is not None else None
        if selected_mode=="freeform":
            # No font is loaded: this digest marks the ABSENCE of any overlay.
            font_hash=digest({"generation_mode":"freeform","font":None,"version":1})
        else:
            try:
                font_hash=hashlib.sha256(font.read_bytes()).hexdigest()
            except (OSError,AttributeError):
                raise LiveGateError("COMPOSITION_FONT_UNAVAILABLE") from None
        directory=self.root/"outputs"/job_id
        # An unsigned proposal may be exercised with synthetic offline data
        # but can NEVER consume a real Provider image or go LIVE.
        prior_template=self.state.template(actor,job_id)
        from .a5_beta_profile_v3 import PROFILE_PREFIX
        if prior_template and prior_template["profile_id"].startswith(PROFILE_PREFIX):
            from .a5_beta_profile_v3 import PRETENDARD_139_SHA
            if (before["mode"]!="OFFLINE_FIXTURE" or self.live_enabled
                    or font_hash!=PRETENDARD_139_SHA):
                raise LiveGateError("A5_V3_PROPOSAL_LIVE_OR_FONT_NOT_APPROVED")
        plan=self.state.plan_compose(actor,job_id,layout,font_hash,has_prior_files=any(
            (directory/name).exists() for name in ("final.png","caption.txt","receipt.json")))
        # Only this Job may complete while the SQLite write transaction is held.
        # A competing call waits, then observes the COMPLETED state and cannot overwrite.
        with self.state.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self.state._read(c,job_id,actor)
            if job["state"]!="IMAGE_APPROVED":
                raise LiveGateError("FINAL_REQUIRES_IMAGE_APPROVAL")
            self.state._approved(job)
            snapshot=self.state.template(actor,job_id)
            if (not snapshot or snapshot["layout_sha"]!=plan["layout_sha"] or
                snapshot["bound_context_sha"]!=plan["context_sha"] or
                snapshot["bound_font_sha"]!=font_hash):
                raise LiveGateError("COMPOSITION_FROZEN_INPUT_CONFLICT")
            path=self.image_path(job_id)
            try:
                raw=path.read_bytes()
            except OSError:
                raise LiveGateError("IMAGE_BYTES_UNAVAILABLE") from None
            image_sha=hashlib.sha256(raw).hexdigest()
            if image_sha!=job["image_sha"]:
                raise LiveGateError("IMAGE_BYTES_CHANGED")
            cp=json.loads(job["copy_json"])
            from src.image_generation.errors import GatewayError
            if selected_mode=="freeform":
                from src.image_generation.backend_adapter import BackendGeneratedImage
                from src.image_generation.candidate_export import export_candidate
                from PIL import Image as PILImage
                try:
                    receipt_bytes=(directory/"owner_candidate_receipt.json").read_bytes()
                    current=self.state.current_image_attempt(actor,job_id)
                    if (current is None or current["candidate_receipt_sha"] is None or
                        hashlib.sha256(receipt_bytes).hexdigest()!=current["candidate_receipt_sha"]):
                        raise ValueError
                    binding=json.loads(receipt_bytes)
                    if (binding["source_sha256"]!=image_sha or
                        binding["copy_sha"]!=job["copy_sha"] or
                        binding["generation"]!=job["generation"] or
                        binding["owner_receipt"].get("state")!="succeeded" or
                        binding["owner_receipt"].get("generation_mode")!="freeform"):
                        raise ValueError
                    with PILImage.open(BytesIO(raw)) as decoded:
                        native=decoded.size
                    candidate=BackendGeneratedImage(
                        image_bytes=raw,mime_type="image/png",width=native[0],
                        height=native[1],sha256=image_sha,job_id=job_id,
                        copy_revision=job["generation"],copy_hash=job["copy_sha"],
                        mock=job["mode"]=="OFFLINE_FIXTURE",
                        receipt=binding["owner_receipt"])
                    # This owner function RESIZES only; NO text overlay/font.
                    result=export_candidate(candidate,copy_output=cp)
                except (OSError,KeyError,TypeError,ValueError,GatewayError):
                    raise LiveGateError("FREEFORM_CANDIDATE_EXPORT_INVALID") from None
            else:
                from src.image_generation.composition import CompositionLayout
                # Preserve the historical immutable Layout and Font contract.
                layout_obj=CompositionLayout.model_validate_json(
                    json.dumps(plan["layout"],ensure_ascii=False))
                input_obj=CompositionInput(
                    job_id=job_id,image_bytes=raw,image_sha256=image_sha,
                    copy_revision=job["generation"],copy_hash=job["copy_sha"],
                    copy_output=cp,layout=layout_obj)
                try:
                    result=compose_ad_png(input_obj,font_path=font)
                except (GatewayError,ValueError):
                    raise LiveGateError("COMPOSITION_RENDER_FAILED") from None
            receipt=result.receipt
            if plan["profile_id"].startswith(PROFILE_PREFIX):
                from .a5_beta_profile_v3 import verify_receipt_for_v3
                receipt=verify_receipt_for_v3(receipt,plan=plan,
                                               font_sha=font_hash,copy_json=cp)
            expected_size=(tuple(snapshot["safe_zone"]["final_size"])
               if snapshot and snapshot["profile_id"].startswith("OWNER_IMAGE_SIZE_")
               else (1080,1350))
            if (result.copy_hash!=job["copy_sha"] or
                result.copy_revision!=job["generation"] or
                result.source_image_sha256!=image_sha or
                hashlib.sha256(result.image_bytes).hexdigest()!=result.sha256 or
                (result.width,result.height)!=expected_size or
                not isinstance(receipt,dict) or
                (receipt.get("font_sha256")!=font_hash if selected_mode=="composed"
                 else receipt.get("generation_mode")!="freeform" or
                      receipt.get("rendering")!="provider_drawn_text" or
                      receipt.get("font_sha256") is not None) or
                receipt.get("provider_calls")!=0):
                raise LiveGateError("COMPOSED_RESULT_BINDING_FAILED")
            caption_sha=hashlib.sha256(result.caption_bytes).hexdigest()
            receipt_bytes=canonical(receipt).encode("utf-8")
            # All three are safely prepared; DB COMPLETED is only committed
            # AFTER files are fsync'ed and atomically moved into place.
            atomic_write(directory/"final.png",result.image_bytes)
            atomic_write(directory/"caption.txt",result.caption_bytes)
            atomic_write(directory/"receipt.json",receipt_bytes)
            return self.state.commit_composition(c,actor,job_id,plan,receipt,
                                                 result.sha256,caption_sha)
