"""A51J isolated candidate: minimal, independently signed paid Job permit.

Paid execution permission is orthogonal to existing Owner visual profiles.
This validator does not enable a Worker, override Frozen v3 false fields, or
substitute for A51F rights/mask and A51C cost verification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import sqlite3
import re
from pathlib import Path

from .a51b_signed_beta_contract import (
    BETA_PREFIX, KEYS, _sealed_dir, _regular, _verify_signature,
    _verify_trust_anchor,
)
from .contracts import LiveGateError

CONTRACT = "IT_TEM_P03_A51J_PAID_JOB_SCOPE_V1"
MODES = frozenset(("freeform", "composed"))
RATIOS = frozenset(("3:4", "4:5", "9:16"))
MODEL = "gpt-image-2.6-sunburst"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
JID = re.compile(r"^[0-9a-f]{32}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
BASE = frozenset((
    "job_id","actor","product_sku","source_commit","ordered_assets_sha256",
    "mode","ratio","provider","model","policy_epoch",
    "owner_design_profile","owner_design_sha256","source_rights_decision_sha256",
    "source_protection_plan_sha256","pm_cost_policy_sha256",
))
FIELDS = BASE | {"contract", "valid_from_utc", "expires_utc"}


def _deny(code: str):
    raise LiveGateError("A51J_" + code)


def owner_visual_contract(mode: str, ratio: str, profile_id: str) -> dict:
    """Select only previously existing Owner visual semantics; never authorize pay."""
    if mode not in MODES or ratio not in RATIOS:
        _deny("MODE_RATIO_INVALID")
    if type(profile_id) is not str:
        _deny("PROFILE_INVALID")
    size = "OWNER_IMAGE_SIZE_" + ratio.replace(":", "_")
    if mode == "composed" and ratio == "4:5":
        if profile_id not in (BETA_PREFIX + "A", BETA_PREFIX + "C"):
            _deny("COMPOSED45_REQUIRES_SIGNED_OWNER_DESIGN")
        return {"mode": mode, "ratio": ratio, "owner_profile": profile_id,
                "rendering": "owner_v3_a_c_reflow", "text_overlay": True,
                "one_candidate": True}
    if profile_id != size:
        _deny("OWNER_SIZE_PROFILE_MISMATCH")
    return {"mode": mode, "ratio": ratio, "owner_profile": size,
            "rendering": "provider_text_single_image" if mode == "freeform"
                         else "owner_ratio_composition",
            "text_overlay": mode == "composed",
            "one_candidate": True}


def verify_paid_job_permit(*, policy_root: str, trust_root: str,
                           trusted_sha: dict[str, str],
                           expected: dict, now: datetime | None = None) -> dict:
    """Check exact signed Job authority; upstream supplies DB-derived expectations.

    This gate binds decisions, but cannot prove their human/legal merits and
    does not replace existing A51F/A51B/A51C verifiers.
    """
    if type(expected) is not dict or set(expected) != BASE:
        _deny("AUTHORITATIVE_CONTEXT_REQUIRED")
    if (type(trusted_sha) is not dict or set(trusted_sha) != set(KEYS)
            or trusted_sha["pm"] == trusted_sha["image_owner"]):
        _deny("DISTINCT_OWNER_PM_TRUST_REQUIRED")
    for field in ("ordered_assets_sha256", "owner_design_sha256",
                  "source_rights_decision_sha256",
                  "source_protection_plan_sha256", "pm_cost_policy_sha256"):
        if type(expected[field]) is not str or HEX64.fullmatch(expected[field]) is None:
            _deny("AUTHORITATIVE_SHA_INVALID")
    if (type(expected["job_id"]) is not str or JID.fullmatch(expected["job_id"]) is None
            or type(expected["source_commit"]) is not str
            or SHA40.fullmatch(expected["source_commit"]) is None
            or expected["provider"] != "openai" or expected["model"] != MODEL):
        _deny("SOURCE_JOB_MODEL_CONTEXT_INVALID")
    for field in ("actor", "product_sku", "policy_epoch"):
        if (type(expected[field]) is not str or not
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", expected[field])):
            _deny("PRINCIPAL_OR_EPOCH_INVALID")
    visual = owner_visual_contract(
        expected["mode"], expected["ratio"], expected["owner_design_profile"])
    policy = _sealed_dir(policy_root)
    trust = _sealed_dir(trust_root)
    if policy == trust:
        _deny("POLICY_TRUST_ROOT_MUST_DIFFER")
    keys = {role: _verify_trust_anchor(trust, role, trusted_sha[role]) for role in KEYS}
    filename = expected["job_id"] + ".paid_job.json"
    path = _regular(policy, filename)
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError):
        _deny("PAID_DECISION_JSON_INVALID")
    if type(doc) is not dict or set(doc) != FIELDS or doc["contract"] != CONTRACT:
        _deny("PAID_DECISION_SCHEMA_INVALID")
    if any(doc[k] != v or type(doc[k]) is not type(v) for k, v in expected.items()):
        _deny("PAID_DECISION_JOB_CONTEXT_MISMATCH")
    try:
        start = datetime.fromisoformat(doc["valid_from_utc"].replace("Z","+00:00"))
        end = datetime.fromisoformat(doc["expires_utc"].replace("Z","+00:00"))
    except (ValueError, TypeError, AttributeError):
        _deny("PAID_DECISION_TIME_INVALID")
    instant = datetime.now(timezone.utc) if now is None else now
    if (start.tzinfo is None or end.tzinfo is None or instant.tzinfo is None
            or start.utcoffset() != timedelta(0)
            or end.utcoffset() != timedelta(0)
            or instant.utcoffset() != timedelta(0)
            or not start <= instant <= end or not timedelta(0) < end - start <= timedelta(days=2)):
        _deny("PAID_DECISION_EXPIRED_OR_INVALID")
    for role, key in keys.items():
        _verify_signature(raw, _regular(policy, expected["job_id"]+"."+role+".sig"),
                          key, path)
    return {
        "contract": CONTRACT,
        "decision_sha256": sha256(raw).hexdigest(),
        "job_id": expected["job_id"], "actor": expected["actor"],
        "mode": visual["mode"], "ratio": visual["ratio"],
        "owner_profile": visual["owner_profile"],
        "rendering": visual["rendering"],
        "verified_signers": list(KEYS),
        "paid_scope_signature_verified": True,
        "rights_mask_cost_verification_still_required": True,
        "actual_paid_worker_activation": False,
    }


def derive_server_job_context(*, flow, actor: str, job_id: str,
                              deployed_source_sha: str) -> dict:
    """Actual B0/LiveStore + Owner snapshot source; caller cannot supply fields.

    Returns only facts already confirmed by durable application authority,
    never a paid authorization. Source rights, license, genuine signatures,
    post-output Candidate QA and Cost are later independent hard gates.
    """
    from .a51f_product_rights_authority import _assets_hash
    from .contracts import assert_single_image_scope, digest
    if (type(deployed_source_sha) is not str or
            SHA40.fullmatch(deployed_source_sha) is None or
            type(actor) is not str or not actor or
            type(job_id) is not str or JID.fullmatch(job_id) is None):
        _deny("SERVER_IDENTITY_OR_SOURCE_INVALID")
    try:
        # B0 Actor ownership is NOT inferred from the client or Queue ticket.
        database = flow.root.parent / "demo.sqlite3"
        if database.is_symlink() or not database.is_file():
            _deny("SERVER_ACTOR_LEDGER_UNAVAILABLE")
        with sqlite3.connect(
                database.as_uri()+"?mode=ro", uri=True, timeout=5) as conn:
            row = conn.execute(
                "SELECT actor FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row or row[0] != actor:
            _deny("SERVER_ACTOR_JOB_NOT_OWNED")
        original = flow.jobs.get_job(job_id)
        if (original.get("job_id") != job_id or
                original.get("status") in
                ("CANCELLED","CANCELED","DELETED","FAILED")):
            _deny("B0_JOB_UNAVAILABLE")
        current = flow.state.get(actor,job_id)
        if (current["actor"] != actor or current["job_id"] != job_id):
            _deny("LIVESTORE_ACTOR_CONFLICT")
        snapshot = json.loads(current["input_json"])
        # Actual persisted source input SHA comes from LiveStore, not client.
        if digest(snapshot) != current["input_sha"]:
            _deny("LIVESTORE_INPUT_HASH_CHANGED")
        assert_single_image_scope(snapshot)
        mode = snapshot["generation_mode"]
        ratio = snapshot["image_size"]
        template = flow.state.template(actor,job_id)
        if template is None:
            _deny("OWNER_VISUAL_PROFILE_MISSING")
        visual = owner_visual_contract(mode, ratio, template["profile_id"])
        if (type(template["layout_sha"]) is not str or
                HEX64.fullmatch(template["layout_sha"]) is None):
            _deny("OWNER_LAYOUT_SHA_INVALID")
        assets_sha = _assets_hash(flow.jobs,original)
    except LiveGateError:
        raise
    except (KeyError,TypeError,ValueError,sqlite3.Error,OSError) as exc:
        _deny("SERVER_JOB_SOURCE_INTEGRITY_FAILED")
    except Exception as exc:
        _deny("SERVER_JOB_LOOKUP_FAILED")
    return {
        "job_id": job_id, "actor": actor, "source_commit": deployed_source_sha,
        "ordered_assets_sha256": assets_sha,
        "mode": mode, "ratio": ratio,
        "owner_design_profile": visual["owner_profile"],
        "owner_design_sha256": template["layout_sha"],
        "rendering": visual["rendering"],
        "one_candidate": True,
        "current_state": current["state"], "current_provenance": current["mode"],
        "original_source_input_sha256": current["input_sha"],
    }


def select_new_paid_visual(snapshot: dict, *, template_profile: str) -> dict | None:
    """New Job visual selector only. Never grants paid Provider authority.

    Existing signed v3 selector is intentionally unchanged. A51J selects the
    authentic Owner visual plan; separate per-Job Paid Scope, Rights, Mask, and
    PM Cost decisions MUST still pass at Worker dispatch.
    """
    if os.environ.get("IT_TEM_A51J_NEW_JOB_ENABLE") != "YES":
        return None
    if template_profile != "A":
        _deny("NEW_PAID_JOB_REQUIRES_OWNER_A")
    if (os.environ.get("IT_TEM_A51B_PROFILE") or
            os.environ.get("IT_TEM_A5_V3_BETA_PROFILE")):
        _deny("NEW_PAID_AND_LEGACY_SELECTOR_CONFLICT")
    if (type(snapshot) is not dict or
            snapshot.get("image_size") not in RATIOS or
            snapshot.get("generation_mode") not in MODES):
        _deny("NEW_PAID_MODE_RATIO_REQUIRED")
    mode, ratio = snapshot["generation_mode"], snapshot["image_size"]
    if mode == "composed" and ratio == "4:5":
        choice = os.environ.get("IT_TEM_A51J_COMPOSED45_CHOICE")
        if choice not in ("A","C"):
            _deny("SIGNED_COMPOSED45_DESIGN_CHOICE_REQUIRED")
        from .a51b_signed_beta_contract import verify_activation
        try:
            verified = verify_activation(
                choice=choice,
                policy_root=os.environ["IT_TEM_A51B_POLICY_ROOT"],
                trust_root=os.environ["IT_TEM_A51B_TRUST_ROOT"],
                trusted_sha={
                    role:os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"]
                    for role in KEYS})
        except KeyError:
            _deny("SIGNED_OWNER_VISUAL_TRUST_MISSING")
        owner_visual_contract(mode,ratio,verified["profile_id"])
        return verified
    from .template_contract import owner_size_policy
    visual = owner_size_policy(ratio)
    owner_visual_contract(mode,ratio,visual["profile_id"])
    return visual


def verify_worker_paid_scope(*, flow, actor: str, job_id: str) -> dict:
    """Pre-provider, DB-derived, dual-signed per-Job authorization.

    No input to this function comes from HTTP/Queue as an entitlement:
    Job, assets and design originate in B0/LiveStore; money from genuine
    signed A51C PM policy; SKU/rights from A51F signed Owner+PM materials;
    protection plan from operator-private files; and final Paid Scope has
    two actual Owner/PM signatures. Candidate quality review is LATER.
    """
    from .a51c_signed_cost_authority import signed_hard_cap_policy
    from .a51f_product_rights_authority import validate_signed_source_rights
    from .a51b_signed_beta_contract import verify_frozen_runtime_activation
    if os.environ.get("IT_TEM_A51J_PAID_SCOPE_RUNTIME") != "YES":
        _deny("SIGNED_PAID_SCOPE_RUNTIME_DISABLED")
    cost = signed_hard_cap_policy(flow.root.parent)
    context = derive_server_job_context(
        flow=flow, actor=actor, job_id=job_id,
        deployed_source_sha=cost["source_commit"])
    if actor not in cost["approved_actors"]:
        _deny("PM_COST_ACTOR_NOT_APPROVED")
    try:
        policy_root = os.environ["IT_TEM_A51J_PAID_POLICY_ROOT"]
        trust_root = os.environ["IT_TEM_A51J_PAID_TRUST_ROOT"]
        plan_root = _sealed_dir(os.environ["IT_TEM_A51J_SOURCE_PLAN_ROOT"])
        rights_root = _sealed_dir(os.environ["IT_TEM_A51F_RIGHTS_ROOT"])
        sku_root = _sealed_dir(os.environ["IT_TEM_A51F_SKU_BINDING_ROOT"])
        trusted = {
            role: os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"]
            for role in KEYS
        }
    except KeyError:
        _deny("OPERATOR_SIGNING_CONFIGURATION_MISSING")
    # Immutable source-plan evidence exists BEFORE generation, unlike a
    # candidate/mask review which cannot exist before Provider submission.
    plan_file = _regular(plan_root, job_id+".source_protection_plan")
    plan_sha = sha256(plan_file.read_bytes()).hexdigest()
    rights_file = _regular(rights_root, job_id+".source_rights.json")
    rights_sha = sha256(rights_file.read_bytes()).hexdigest()
    binding_file = _regular(sku_root, job_id+".sku_binding.json")
    try:
        sku_doc = json.loads(binding_file.read_bytes())
        product_sku = sku_doc["product_sku"]
    except (UnicodeError,ValueError,KeyError,TypeError):
        _deny("SIGNED_SKU_BINDING_NOT_READABLE")
    if not isinstance(product_sku,str):
        _deny("SIGNED_SKU_BINDING_INVALID")
    current = flow.state.template(actor,job_id)
    if context["rendering"] == "owner_v3_a_c_reflow":
        # Genuine historical Signed visual source; all old FALSE flags remain
        # immutable. Paid authority comes ONLY from independent A51J + A51F.
        verified = verify_frozen_runtime_activation(current)
        profile_epoch = verified["safe_zone"]["policy_epoch"]
        design_decision_sha = verified["safe_zone"][
            "signed_owner_pm_decision_sha256"]
        if cost["policy_epoch"] != profile_epoch:
            _deny("SIGNED_OWNER_PM_POLICY_EPOCH_MISMATCH")
    else:
        # Existing size Owner layout is not retrospectively made a signed v3.
        # Only the exact job's TWO-SIGNED new A51J permit can grant paid scope.
        profile_epoch = cost["policy_epoch"]
        design_decision_sha = context["owner_design_sha256"]
    expected = {
        "job_id": job_id, "actor": actor,
        "product_sku": product_sku, "source_commit": context["source_commit"],
        "ordered_assets_sha256": context["ordered_assets_sha256"],
        "mode": context["mode"], "ratio": context["ratio"],
        "provider": "openai", "model": MODEL,
        "policy_epoch": profile_epoch,
        "owner_design_profile": context["owner_design_profile"],
        "owner_design_sha256": context["owner_design_sha256"],
        "source_rights_decision_sha256": rights_sha,
        "source_protection_plan_sha256": plan_sha,
        "pm_cost_policy_sha256": cost["approval_sha256"],
    }
    # This cryptographic check happens BEFORE the paid API request and cannot
    # be replaced by browser consent, unsigned Job metadata or cost env vars.
    permit = verify_paid_job_permit(
        policy_root=policy_root, trust_root=trust_root,
        trusted_sha=trusted, expected=expected)
    rights = validate_signed_source_rights(
        store=flow.jobs, job=flow.jobs.get_job(job_id), actor=actor,
        generation_mode=context["mode"], image_size=context["ratio"],
        expected_policy_epoch=profile_epoch,
        expected_profile_decision_sha=design_decision_sha)
    if (rights["decision_sha256"] != rights_sha or
            rights["assets_sha256"] != context["ordered_assets_sha256"] or
            rights["product_sku_binding_sha256"] != sha256(
                binding_file.read_bytes()).hexdigest() or
            rights["source_commit"] != context["source_commit"]):
        _deny("INDEPENDENT_RIGHTS_LEDGER_DIVERGENCE")
    return {
        "job_id": job_id, "actor": actor,
        "scope_sha256": permit["decision_sha256"],
        "source_rights_sha256": rights_sha,
        "source_protection_plan_sha256": plan_sha,
        "pm_cost_policy_sha256": cost["approval_sha256"],
        "verified_signers": permit["verified_signers"],
        "visual_rendering": context["rendering"],
        "candidate_review_required_after_generation": True,
        "signed_paid_preflight_verified": True,
        "post_generation_quality_approved": False,
    }


def verify_post_candidate_signed_review(*, flow, actor: str,
                                        job_id: str, now: datetime | None = None) -> dict:
    """Release-side signed HUMAN review of actual output, never a pre-call fact.

    Existing A51B Composed 4:5 final-mask geometry gate remains additional and
    independent; this does not claim pixel identity automatically. Every
    non-4:5 mode uses its existing Owner native size, NOT a 1080x1350 mask.
    """
    from io import BytesIO
    from PIL import Image
    from src.image_generation.size_selection import resolve_size_choice
    from .a51c_signed_cost_authority import signed_hard_cap_policy
    from .a51b_signed_beta_contract import _verify_trust_anchor
    job = flow.state.get(actor,job_id)
    if job["state"] != "IMAGE_APPROVED" or not job.get("image_approval_sha"):
        _deny("POST_REVIEW_REQUIRES_IMAGE_APPROVAL")
    cost = signed_hard_cap_policy(flow.root.parent)
    identity = derive_server_job_context(
        flow=flow, actor=actor, job_id=job_id,
        deployed_source_sha=cost["source_commit"])
    try:
        private = _sealed_dir(os.environ["IT_TEM_A51J_POST_REVIEW_ROOT"])
        plan_root = _sealed_dir(os.environ["IT_TEM_A51J_SOURCE_PLAN_ROOT"])
        trust = _sealed_dir(os.environ["IT_TEM_A51J_PAID_TRUST_ROOT"])
        trusted = {
            role:os.environ["IT_TEM_A51B_"+role.upper()+"_PUB_SHA"]
            for role in KEYS
        }
    except KeyError:
        _deny("POST_REVIEW_OPERATOR_CONFIG_MISSING")
    if private == trust or private == plan_root:
        _deny("POST_REVIEW_ROOT_NOT_INDEPENDENT")
    if trusted["image_owner"]==trusted["pm"]:
        _deny("POST_REVIEW_SIGNERS_NOT_DISTINCT")
    keys={role:_verify_trust_anchor(trust,role,trusted[role]) for role in KEYS}
    review_file = _regular(private,job_id+".candidate_review.json")
    raw = review_file.read_bytes()
    try:
        doc=json.loads(raw)
    except (UnicodeError,ValueError):
        _deny("POST_REVIEW_RECORD_INVALID")
    fields = {
        "contract","job_id","actor","source_commit","mode","ratio",
        "candidate_png_sha256","copy_sha256","image_approval_sha256",
        "owner_layout_sha256","source_protection_plan_sha256",
        "candidate_protected_mask_sha256","product_form_accepted",
        "product_color_accepted","logo_accepted","label_accepted",
        "approved_copy_text_accepted","review_decision","review_time_utc",
    }
    if type(doc) is not dict or set(doc)!=fields:
        _deny("POST_REVIEW_SCHEMA_INVALID")
    image_path=flow.image_path(job_id)
    if image_path.is_symlink() or not image_path.is_file():
        _deny("CANDIDATE_IMAGE_UNAVAILABLE")
    pixels=image_path.read_bytes()
    actual_sha=sha256(pixels).hexdigest()
    plan_sha=sha256(_regular(
        plan_root,job_id+".source_protection_plan").read_bytes()).hexdigest()
    expected={
        "contract":"IT_TEM_P03_A51J_POST_CANDIDATE_HUMAN_QA_V1",
        "job_id":job_id,"actor":actor,
        "source_commit":identity["source_commit"],
        "mode":identity["mode"],"ratio":identity["ratio"],
        "candidate_png_sha256":actual_sha,
        "copy_sha256":job["copy_sha"],
        "image_approval_sha256":job["image_approval_sha"],
        "owner_layout_sha256":identity["owner_design_sha256"],
        "source_protection_plan_sha256":plan_sha,
        "candidate_protected_mask_sha256":sha256(_regular(
            private,job_id+".candidate_mask.png",max_bytes=12*1024*1024
        ).read_bytes()).hexdigest(),
        "product_form_accepted":True,"product_color_accepted":True,
        "logo_accepted":True,"label_accepted":True,
        "approved_copy_text_accepted":True,
        "review_decision":"OWNER_PM_HUMAN_ACCEPT_AFTER_PROVIDER_OUTPUT",
    }
    if any(type(doc.get(k)) is not type(v) or doc.get(k)!=v
           for k,v in expected.items()):
        _deny("POST_REVIEW_CONTEXT_OR_HUMAN_DECISION_MISMATCH")
    try:
        reviewed=datetime.fromisoformat(doc["review_time_utc"].replace("Z","+00:00"))
    except (TypeError,ValueError,AttributeError):
        _deny("POST_REVIEW_TIMESTAMP_INVALID")
    instant=datetime.now(timezone.utc) if now is None else now
    uploaded=datetime.fromtimestamp(image_path.stat().st_mtime,timezone.utc)
    if (reviewed.tzinfo is None or reviewed.utcoffset()!=timedelta(0) or
            instant.tzinfo is None or instant.utcoffset()!=timedelta(0) or
            not uploaded-timedelta(seconds=30)<=reviewed<=instant or
            instant-reviewed>timedelta(days=2)):
        _deny("POST_REVIEW_MUST_FOLLOW_REAL_CANDIDATE")
    from .a51b_signed_beta_contract import _verify_signature
    for role,key in keys.items():
        _verify_signature(raw,_regular(private,job_id+"."+role+".review.sig"),
                          key,review_file)
    selection, owner_profile=resolve_size_choice(identity["ratio"])
    native=tuple(owner_profile.native)
    mask_file=_regular(private,job_id+".candidate_mask.png",max_bytes=12*1024*1024)
    try:
        with Image.open(BytesIO(pixels)) as img:
            img.load()
            if img.format!="PNG" or img.size!=native:
                _deny("POST_REVIEW_OWNER_NATIVE_SIZE_MISMATCH")
        with Image.open(mask_file) as mask:
            mask.load()
            if mask.format!="PNG" or mask.mode!="L" or mask.size!=native:
                _deny("POST_REVIEW_RATIO_MASK_GEOMETRY_INVALID")
            hist=mask.histogram()
            coverage=hist[255]
            if (any(hist[i] for i in range(1,255)) or
                    coverage<100 or coverage>=native[0]*native[1]*0.85):
                _deny("POST_REVIEW_BINARY_PROTECTED_MASK_INVALID")
    except (OSError,ValueError):
        _deny("POST_REVIEW_IMAGE_DECODE_FAILED")
    return {
        "signed_review_sha256":sha256(raw).hexdigest(),
        "candidate_png_sha256":actual_sha,
        "candidate_protected_mask_sha256":expected[
            "candidate_protected_mask_sha256"],
        "native_size":list(native),
        "human_owner_pm_visual_acceptance":True,
        "actual_computer_vision_product_identity_certified":False,
        "post_generation_timing_verified":True,
        "separately_signed_owner_pm_review":list(KEYS),
    }
