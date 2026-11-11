"""Derived recipes and review use existing authenticated Job/Copy authority.

Only local content publication and the explicitly migrated derived tables are
written. Raw images, approvals, Provider queues and cost rows are read-only.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sqlite3

from PIL import Image

from src.image_generation.contracts import content_hash
from src.image_generation.protected_recipe import content_ref, checked_recipe, recipe_content_sha, result_binding_sha
from src.image_generation.protected_product import professional_layout
from .contracts import LiveGateError, digest
from .derived_approval import current_derived_context, require_same_context
from .derived_assets import DerivedAssetRegistry
from .derived_store import DerivedStore


RATIOS = {"3:4": (1080, 1440), "4:5": (1080, 1350), "9:16": (1080, 1920)}
VISUAL_CHECKS = frozenset({"source_pixels_preserved", "edges_acceptable", "no_duplicate_product",
    "no_ghost_product", "no_copy_occlusion", "cta_policy_matches", "label_ground_truth_confirmed", "mobile_readable"})


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _mask(size):
    stream = BytesIO()
    Image.new("L", size, 255).save(stream, "PNG")
    return stream.getvalue()


def renderer_fingerprints(mode):
    root = Path(__file__).resolve().parents[2]
    files = {"study_adapter": "src/image_generation/protected_product.py", "resize": "src/image_generation/ad_resize.py"}
    if mode == "composed_protected_product":
        files.update(base_adapter="src/image_generation/protected_recipe.py",
                     composition="src/image_generation/composition.py", typography="src/image_generation/typography.py")
    else:
        files["color_management"] = "src/image_generation/protected_product.py"
    return {name: sha256((root / path).read_bytes()).hexdigest() for name, path in files.items()}


class DerivedService:
    def __init__(self, live_state, jobs, owns, *, root, authority, font_path, license_path, source_tree_sha):
        self.state = live_state
        self.jobs = jobs
        self.owns = owns
        self.store = DerivedStore(live_state.filename)
        self.root = Path(root)
        self.authority = authority
        self.font_path = Path(font_path)
        self.license_path = Path(license_path)
        self.source_tree_sha = source_tree_sha
        self.registry = DerivedAssetRegistry(self.root / "assets", jobs, self.owns_job,
                                             source_job_resolver=self.source_job)

    def source_job(self, actor, job_id, connection=None):
        """Resolve only the server-validated Live Dual parent, never client paths."""
        if connection is None:
            with self.store.connection(readonly=True) as c:
                return self.source_job(actor, job_id, c)
        job = self.state._read(connection, job_id, actor)
        group = self.state._live_dual_row(connection, actor, job_id)
        parent = self.state._assert_live_dual_binding(connection, job, group) if group else job
        if not self.owns(actor, parent["job_id"]):
            raise LiveGateError("DERIVED_JOB_NOT_FOUND")
        return parent["job_id"]

    def owns_job(self, actor, job_id):
        try:
            self.source_job(actor, job_id)
            return True
        except LiveGateError:
            return False

    def owner(self, job_id, connection):
        row = connection.execute("SELECT actor FROM live_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise LiveGateError("DERIVED_JOB_NOT_FOUND")
        return row[0]

    def context(self, connection, actor, auth_role, job_id, scope):
        owner = self.owner(job_id, connection)
        policy = self.authority.authorize(actor, auth_role, owner, job_id, scope)
        job, binding, _ = current_derived_context(self.state, connection, owner, job_id)
        if self.source_job(owner, job_id, connection) != binding["source_upload_job_id"]:
            raise LiveGateError("DERIVED_SOURCE_PARENT_CHANGED")
        # Business-role/delegation revision is effective authority and belongs
        # in approval context. Content recipes remain location/actor independent.
        binding["authority_policy_sha"] = policy["authority_policy_sha"]
        return owner, job, binding, digest(binding), policy

    def billing_unknown(self):
        filename = self.state.filename.parent / "cost.sqlite"
        if not filename.is_file() or filename.is_symlink():
            raise LiveGateError("DERIVED_COST_LEDGER_UNAVAILABLE")
        try:
            with sqlite3.connect(filename.resolve().as_uri()+"?mode=ro", uri=True) as c:
                return bool(c.execute("SELECT 1 FROM attempts WHERE billing_unknown=1 OR status='BILLING_UNKNOWN' LIMIT 1").fetchone())
        except sqlite3.Error:
            raise LiveGateError("DERIVED_COST_LEDGER_UNAVAILABLE") from None

    def raw_candidate(self, job, binding):
        folder = self.state.filename.parent / "outputs" / job["job_id"]
        path = folder / "image.png"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32*1024*1024:
            raise LiveGateError("DERIVED_RAW_CANDIDATE_UNAVAILABLE")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != binding["raw_candidate_sha"]:
            raise LiveGateError("DERIVED_RAW_CANDIDATE_CHANGED")
        receipt_sha = binding["owner_candidate_receipt_sha"]
        if receipt_sha:
            receipt = folder / "owner_candidate_receipt.json"
            if receipt.is_symlink() or not receipt.is_file() or sha256(receipt.read_bytes()).hexdigest() != receipt_sha:
                raise LiveGateError("DERIVED_RAW_RECEIPT_CHANGED")
        return raw

    def _default_geometry(self, width, height, output):
        # A registered crop keeps an exact rational scale with integer output.
        # All crop coordinates are shown in the recipe before human admission.
        cw, ch = width-width % 16, height-height % 16
        if not cw or not ch:
            raise LiveGateError("DERIVED_SOURCE_TOO_SMALL")
        unit = math.gcd(cw, ch)
        factor = min(unit, int(output[0]*.58*unit/cw), int(output[1]*.55*unit/ch))
        if factor < 1:
            raise LiveGateError("DERIVED_REGISTRATION_REQUIRED")
        size = [cw//unit*factor, ch//unit*factor]
        offset = [(output[0]-size[0])//2, round(output[1]*.28)]
        return [0, 0, cw, ch], size, offset

    def proposal(self, owner, job, binding, options=None):
        options = options or {}
        inputs = json.loads(job["input_json"])
        photos = [a for a in self.jobs.get_job(binding["source_upload_job_id"])["assets"] if a["role"] == "product"]
        source_id = options.get("source_asset_id") or photos[0]["asset_id"]
        expected = next((a for a in inputs["ordered_asset_hashes"] if a["asset_id"] == source_id and a["role"] == "product"), None)
        if expected is None:
            raise LiveGateError("DERIVED_SOURCE_NOT_IN_APPROVED_INPUT")
        source = self.registry.resolve_upload(owner, job["job_id"], source_id, expected_sha256=expected["sha256"])
        output = RATIOS[binding["image_size"]]
        source_width, source_height = source.image.upright_size
        crop, size, offset = self._default_geometry(source_width, source_height, output)
        crop = options.get("source_crop") or crop
        size = options.get("registered_size") or size
        offset = options.get("output_offset") or offset
        mask_ref = options.get("mask_ref")
        mask_data = self.registry.read_content(owner, job["job_id"], mask_ref).data if mask_ref else _mask((source_width, source_height))
        rois = options.get("protected_rois") or {"original_photo": crop}
        mode = "freeform_protected_product_hybrid" if binding["generation_mode"] == "freeform" else "composed_protected_product"
        copy = json.loads(job["copy_json"])
        raw = self.raw_candidate(job, binding)
        layer = {"schema": "bp18-protected-layers-v1", "raw_candidate_sha": sha256(raw).hexdigest(),
                 "source_orientation": source.image.orientation,
                 "model_regions": options.get("model_regions", []), "copy_exclusions": options.get("copy_exclusions", []),
                 "layer_order": ["model_scene", "original_product", "approved_copy"] if mode == "composed_protected_product" else ["model_scene_with_copy", "original_product"]}
        assets = {"source_photo": (source.data, source.ref.media_type), "product_mask": (mask_data, "image/png"),
                  "copy_snapshot": (_json(copy), "application/json")}
        if mode == "composed_protected_product":
            layout = professional_layout(copy, output)
            assets.update(font=(self.font_path.read_bytes(), "font/ttf"), font_license=(self.license_path.read_bytes(), "text/plain"),
                          layout=(_json(layout.model_dump(mode="json")), "application/json"))
        else:
            scene = {"schema": "bp18-hybrid-scene-review-v1", "candidate_sha256": sha256(raw).hexdigest(),
                     "reviewed": options.get("acknowledge_regions") is True,
                     "model_regions": layer["model_regions"], "copy_exclusions": layer["copy_exclusions"]}
            layer["scene_review_sha"] = content_hash(scene)
            assets.update(raw_candidate=(raw, "image/png"), scene_review_spec=(_json(scene), "application/json"))
        recipe = checked_recipe({"schema": "bp18-portable-render-recipe-v1", "render_mode": mode,
            "assets": {name: content_ref(data, media).model_dump() for name, (data, media) in assets.items()},
            "code_sha256": renderer_fingerprints(mode), "source_tree_sha": self.source_tree_sha,
            "source_icc_sha256": source.image.icc_sha256, "roi_spec_sha256": content_hash(rois), "copy_sha256": job["copy_sha"],
            "geometry": {"source_size": [source_width, source_height], "source_crop": crop,
                "registered_size": size, "output_offset": offset, "output_size": list(output),
                "resampler": "NONE" if size == [crop[2]-crop[0], crop[3]-crop[1]] else "LANCZOS_RGB_AND_ALPHA"},
            "design_id": "editorial-original-photo-v1", "layer_spec_sha256": content_hash(layer),
            "alpha_rule": "combined_single_pass_photo_v1"})
        hold = None
        if mode == "freeform_protected_product_hybrid" and (not options.get("acknowledge_regions") or not layer["model_regions"] or not layer["copy_exclusions"]):
            hold = "HYBRID_SCENE_REGISTRATION_REQUIRED"
        payload = {"recipe": recipe, "layer_spec": layer, "roi_spec": rois, "upload_bindings": {"source_photo": source_id},
                   "background_ref": content_ref(raw, "image/png").model_dump(), "options": options}
        sha = recipe_content_sha(recipe)
        return {"proposal_id": sha, "recipe_sha": sha, "render_mode": mode,
                "title": "원본 사진과 승인 카피로 보호 합성" if mode == "composed_protected_product" else "모델 장면·문구와 원본 제품 보호 합성",
                "source_asset_id": source_id, "requires_ground_truth": True, "hold_code": hold,
                "payload": payload, "content": assets, "raw": raw}

    def publish_proposal(self, owner, job_id, proposal):
        self.registry.register_upload(owner, job_id, proposal["payload"]["upload_bindings"]["source_photo"])
        for role, (raw, media) in proposal["content"].items():
            self.registry.put_content(owner, job_id, raw, media, kind=role)
        self.registry.put_content(owner, job_id, proposal["raw"], "image/png", kind="raw_candidate")

    def save_proposal(self, actor, role, job_id, options):
        with self.store.transaction() as c:
            owner, job, binding, context_sha, _ = self.context(c, actor, role, job_id, "admit")
            value = self.proposal(owner, job, binding, options)
            self.publish_proposal(owner, job_id, value)
            name = f"proposal.{context_sha}.{value['recipe_sha']}.json"
            self.registry._publish(self.registry.root/job_id, name,
                _json({"context_sha": context_sha, "recipe_sha": value["recipe_sha"], "options": options}))
        return self.public_proposal(value)

    def stored_options(self, owner, job_id, context_sha):
        directory = self.registry.root/job_id
        if directory.is_symlink():
            raise LiveGateError("DERIVED_PROPOSAL_STORAGE_CHANGED")
        values = []
        for path in sorted(directory.glob(f"proposal.{context_sha}.*.json")):
            raw = self.registry._read_regular(self.registry.root, path, limit=128*1024)
            value = json.loads(raw)
            if (value["context_sha"] != context_sha or
                    path.name != f"proposal.{context_sha}.{value['recipe_sha']}.json"):
                raise LiveGateError("DERIVED_PROPOSAL_STORAGE_CHANGED")
            values.append(value)
        return values

    def snapshot(self, actor, role, job_id):
        with self.store.transaction() as c:
            owner, job, binding, context_sha, policy = self.context(c, actor, role, job_id, "read")
            can_admit = policy["business_role"] in ("owner", "pm")
            rows = self.store.list_renders(owner, job_id, c=c)
            try:
                default = self.proposal(owner, job, binding)
                proposals = [self.public_proposal(default)]
            except (OSError, ValueError):
                proposals = []
            for stored in self.stored_options(owner, job_id, context_sha):
                custom = self.proposal(owner, job, binding, stored["options"])
                if custom["recipe_sha"] != stored["recipe_sha"]:
                    raise LiveGateError("DERIVED_PROPOSAL_CHANGED")
                if not any(p["proposal_id"] == custom["proposal_id"] for p in proposals):
                    proposals.append(self.public_proposal(custom))
            hold = "BILLING_UNKNOWN" if self.billing_unknown() else None
            return {"job_id": job_id, "available": True, "can_admit": can_admit,
                    "can_review": can_admit, "context_sha": context_sha, "revision": job["generation"],
                    "hold_code": hold, "proposals": proposals, "renders": [self.public_render(row, context_sha) for row in rows],
                    "selected_derived_id": next((r["derived_id"] for r in rows if r["selected"]), None),
                    "source_assets": [{k: a[k] for k in ("asset_id", "sha256", "width", "height")} for a in self.jobs.get_job(binding["source_upload_job_id"])["assets"] if a["role"] == "product"]}

    @staticmethod
    def public_proposal(value):
        return {key: value[key] for key in ("proposal_id", "recipe_sha", "render_mode", "title", "source_asset_id", "requires_ground_truth", "hold_code")}

    def public_render(self, row, current_context=None):
        payload = row["payload"]
        admission = self.store.get_admission(row["actor"], row["job_id"], row["grant_id"])
        mode = payload["recipe"]["render_mode"]
        state = row["state"]
        if state == "REVOKED" or current_context and row["context_sha"] != current_context:
            state = "STALE"
        artifacts = {}
        for kind in ("preview", "final", "caption", "receipt"):
            h = row.get(kind+"_sha")
            if h and kind in row["artifacts"]:
                artifacts[kind] = f"/demo/api/live/jobs/{row['job_id']}/derived/renders/{row['derived_id']}/artifacts/{kind}?sha256={h}"
        size = payload["recipe"]["geometry"]["output_size"]
        return {"derived_id": row["derived_id"], "job_id": row["job_id"], "render_mode": mode,
                "state": state, "revision": row["revision"], "recipe_sha": row["recipe_sha"],
                "context_sha": row["context_sha"], "admission_sha": admission["record_sha"],
                **{kind+"_sha": row.get(kind+"_sha") for kind in ("preview", "approval", "final", "caption", "receipt")},
                "output_size": {"width": size[0], "height": size[1]}, "artifacts": artifacts,
                "hold_code": row["error_code"], "checks": {"literal_label_ground_truth": "PENDING"}}

    def admit(self, actor, role, job_id, body):
        with self.store.transaction() as c:
            owner, job, binding, context_sha, policy = self.context(c, actor, role, job_id, "admit")
            require_same_context(context_sha, body["expected_context_sha"])
            if job["generation"] != body["expected_revision"] or body["acknowledge_source"] is not True:
                raise LiveGateError("DERIVED_ADMISSION_STALE")
            if self.billing_unknown():
                raise LiveGateError("BILLING_UNKNOWN")
            stored = next((v for v in self.stored_options(owner, job_id, context_sha)
                           if v["recipe_sha"] == body["expected_recipe_sha"]), None)
            proposal = self.proposal(owner, job, binding, stored["options"] if stored else None)
            if proposal["recipe_sha"] != body["expected_recipe_sha"] or proposal["proposal_id"] != body["proposal_id"]:
                raise LiveGateError("DERIVED_PROPOSAL_CHANGED")
            if proposal["hold_code"]:
                raise LiveGateError(proposal["hold_code"])
            self.publish_proposal(owner, job_id, proposal)
            record = {**proposal["payload"], "context": binding, "reviewer": policy,
                      "source_acknowledged": True, "scope": "DERIVED_RECIPE_ONLY"}
            key = digest({"proposal": proposal["recipe_sha"], "context": context_sha, "reviewer": actor})
            grant = self.store.append_admission(actor=owner, job_id=job_id, recipe_sha=proposal["recipe_sha"],
                context_sha=context_sha, record=record, reviewer_actor=actor, reviewer_role=role,
                scope="DERIVED_RECIPE", idempotency_key=key, c=c)
            return {"admission_sha": grant["record_sha"], "recipe_sha": grant["recipe_sha"],
                    "context_sha": context_sha, "revision": grant["revision"]}

    def prepare(self, actor, role, job_id, body):
        with self.store.transaction() as c:
            owner, job, binding, context_sha, _ = self.context(c, actor, role, job_id, "render")
            require_same_context(context_sha, body["expected_context_sha"])
            if self.billing_unknown():
                raise LiveGateError("BILLING_UNKNOWN")
            grants = self.store.list_admissions(owner, job_id, c=c)
            grant = next((g for g in grants if g["record_sha"] == body["admission_sha"]), None)
            if grant is None or grant["recipe_sha"] != body["expected_recipe_sha"] or grant["context_sha"] != context_sha:
                raise LiveGateError("DERIVED_ADMISSION_CONTEXT_MISMATCH")
            payload = grant["record"]["payload"]
            row, _ = self.store.enqueue_render(actor=owner, job_id=job_id, grant_id=grant["grant_id"],
                expected_grant_revision=grant["revision"], recipe_sha=grant["recipe_sha"], context_sha=context_sha,
                payload=payload, idempotency_key=body["idempotency_key"], c=c)
        return self.public_render(row, context_sha)

    def decide(self, actor, role, job_id, derived_id, body):
        with self.store.transaction() as c:
            owner, job, _, current_sha, policy = self.context(c, actor, role, job_id, "review")
            require_same_context(current_sha, body["expected_context_sha"])
            row = self.store.get_render(owner, job_id, derived_id, c=c)
            self.read_artifact(owner, job_id, row, "preview")
            checks = body["visual_review"]
            if body["approve"] and (set(checks) != VISUAL_CHECKS | {"observed_copy"}
                    or any(checks[name] is not True for name in VISUAL_CHECKS)
                    or checks["observed_copy"] != json.loads(job["copy_json"])["ad_copy"]):
                raise LiveGateError("DERIVED_VISUAL_REVIEW_REQUIRED")
            record = {"checks": checks, "authority": policy, "context_sha": current_sha,
                      "recipe_sha": row["recipe_sha"], "preview_sha": row["preview_sha"]}
            updated = self.store.append_review(actor=owner, job_id=job_id, derived_id=derived_id,
                expected_revision=body["expected_revision"], preview_sha=body["expected_preview_sha"],
                recipe_sha=body["expected_recipe_sha"], context_sha=current_sha,
                decision="APPROVE" if body["approve"] else "REJECT", record=record,
                reviewer_actor=actor, reviewer_role=role, idempotency_key=digest({"body": body, "actor": actor}), c=c)
        return self.public_render(updated, current_sha)

    def read_artifact(self, owner, job_id, row, kind):
        ref = row["artifacts"].get(kind)
        if ref is None:
            raise LiveGateError("DERIVED_ARTIFACT_NOT_AVAILABLE")
        data = self.registry.read_content(owner, job_id, ref).data
        expected = row.get(kind+"_sha")
        if expected and sha256(data).hexdigest() != expected:
            raise LiveGateError("DERIVED_ARTIFACT_CHANGED")
        return data

    def revoke(self, actor, role, job_id, derived_id, body):
        """Explicitly retire a recipe grant without reviving previous approvals."""
        with self.store.transaction() as c:
            owner, _, _, context_sha, policy = self.context(c, actor, role, job_id, "admit")
            require_same_context(context_sha, body["expected_context_sha"])
            row = self.store.get_render(owner, job_id, derived_id, c=c)
            grant = self.store.active_admission(owner, job_id, row["grant_id"],
                expected_revision=row["grant_revision"], c=c)
            if row["revision"] != body["expected_revision"] or grant["record_sha"] != body["expected_admission_sha"]:
                raise LiveGateError("DERIVED_REVOCATION_STALE")
            self.store.revoke_admission(actor=owner, job_id=job_id, grant_id=row["grant_id"],
                expected_revision=grant["revision"], reviewer_actor=actor, reviewer_role=role,
                record={"reason": "EXPLICIT_RECIPE_ADMISSION_REVOKED", "authority": policy},
                idempotency_key=digest({"body": body, "actor": actor, "derived_id": derived_id}), c=c)
            updated = self.store.get_render(owner, job_id, derived_id, c=c)
        return self.public_render(updated, context_sha)

    def finalize(self, actor, role, job_id, derived_id, body):
        with self.store.transaction() as c:
            owner, job, binding, current_sha, policy = self.context(c, actor, role, job_id, "finalize")
            row = self.store.require_approval(owner, job_id, derived_id, c=c)
            require_same_context(current_sha, row["context_sha"])
            preview = self.read_artifact(owner, job_id, row, "preview")
            caption = self.registry.read_content(owner, job_id, row["artifacts"]["draft_caption"]).data
            local_receipt = self.registry.read_content(owner, job_id, row["artifacts"]["local_receipt"]).data
            receipt = {"schema": "bp18-derived-download-receipt-v1", "job_id": job_id, "derived_id": derived_id,
                       "render_mode": row["payload"]["recipe"]["render_mode"], "recipe_content_sha": row["recipe_sha"],
                       "result_binding_sha": row["result_sha"], "admission_context_sha": current_sha,
                       "admission_event_id": row["admission_event_id"], "grant_revision": row["grant_revision"],
                       "derived_approval_sha": row["approval_sha"], "preview_sha": row["preview_sha"],
                       "final_sha": sha256(preview).hexdigest(), "caption_sha": sha256(caption).hexdigest(),
                       "local_receipt_sha": sha256(local_receipt).hexdigest(), "raw_provider_reference": binding,
                       "provider_calls": 0, "provider_attempt_ids_are_references": True,
                       "actual_provider_usd": None, "billing_status": "USD_UNRECONCILED", "finalizer": policy}
            receipt_bytes = _json(receipt)
            receipt_ref = self.registry.put_content(owner, job_id, receipt_bytes, "application/json", kind="receipt")
            artifacts = {**row["artifacts"], "final": row["artifacts"]["preview"],
                         "caption": row["artifacts"]["draft_caption"], "receipt": receipt_ref.model_dump()}
            updated = self.store.finalize_render(actor=owner, job_id=job_id, derived_id=derived_id,
                expected_revision=body["expected_revision"], approval_sha=body["expected_approval_sha"],
                preview_sha=body["expected_preview_sha"], final_sha=sha256(preview).hexdigest(),
                caption_sha=sha256(caption).hexdigest(), receipt_sha=receipt_ref.sha256, artifacts=artifacts, c=c)
        return self.public_render(updated, current_sha)

    def select(self, actor, role, job_id, body):
        with self.store.transaction() as c:
            owner, _, _, current_sha, _ = self.context(c, actor, role, job_id, "select")
            row = self.store.require_approval(owner, job_id, body["derived_id"], c=c)
            require_same_context(current_sha, row["context_sha"])
            if row["approval_sha"] != body["expected_approval_sha"]:
                raise LiveGateError("DERIVED_SELECTION_STALE")
            self.read_artifact(owner, job_id, row, "final")
            row = self.store.select_render(actor=owner, job_id=job_id, derived_id=row["derived_id"],
                expected_revision=row["revision"], expected_final_sha=body["expected_final_sha"], c=c)
        return self.public_render(row, current_sha)
