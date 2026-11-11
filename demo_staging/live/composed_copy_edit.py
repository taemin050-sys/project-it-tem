"""Independent, approval-invalidating manual Composed copy revisions.

HTTP never invokes a model. Only the credential Worker reviews changed copy.
The immutable source candidate, Dual sibling and their ledgers are never updated.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .contracts import LiveGateError, digest, strict_review
from .pipeline import atomic_write

PROTOCOL = "COMPOSED_COPY_EDIT_V1"
FLAG = "IT_TEM_COMPOSED_COPY_EDIT_ENABLED"
WORKER_FLAG = "IT_TEM_COMPOSED_COPY_EDIT_WORKER_PROTOCOL"
SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[0-9a-f]{32}$")


def enabled():
    return os.environ.get(FLAG) == "YES" and os.environ.get(WORKER_FLAG) == PROTOCOL


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ComposedCopyEdits:
    def __init__(self, flow):
        self.flow = flow
        self.file = flow.root / "composed_copy_edits.sqlite"
        self.root = flow.root / "composed_copy_edits"

    @contextmanager
    def db(self, *, create=False):
        if not self.file.exists() and not create:
            raise LiveGateError("COMPOSED_EDIT_NOT_FOUND")
        connection = sqlite3.connect(self.file, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=20000")
        try:
            if create:
                connection.execute("""CREATE TABLE IF NOT EXISTS composed_copy_edits (
                    edit_id TEXT PRIMARY KEY, actor TEXT NOT NULL, job_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, request_sha TEXT NOT NULL,
                    state TEXT NOT NULL, record_json TEXT NOT NULL,
                    UNIQUE(actor,job_id,request_key))""")
                connection.commit()
                self.file.chmod(0o600)
            yield connection
        finally:
            connection.close()

    def context(self, actor, job_id, connection):
        job = self.flow.state._read(connection, job_id, actor)
        if job["state"] == "IMAGE_REJECTED":
            raise LiveGateError("COMPOSED_EDIT_SOURCE_IMAGE_REJECTED")
        self.flow.state._approved(job, connection, allow_completed=True)
        if (job["mode"] != "LIVE" or not job["image_sha"] or
                json.loads(job["input_json"]).get("generation_mode", "composed") != "composed"):
            raise LiveGateError("COMPOSED_EDIT_SOURCE_REQUIRED")
        parent = self.flow.state.live_dual_membership(actor, job_id)
        if not parent:
            raise LiveGateError("COMPOSED_EDIT_DUAL_SOURCE_REQUIRED")
        self.flow.verify_live_dual_f09(actor, parent)
        binding = self.flow.live_dual_candidate_receipt(actor, job_id)
        template = self.flow.state.template(actor, job_id)
        if not template or not template.get("layout"):
            raise LiveGateError("COMPOSED_EDIT_TEMPLATE_REQUIRED")
        context = {"protocol": PROTOCOL, "actor": actor, "job_id": job_id,
            "generation": job["generation"], "image_sha": job["image_sha"],
            "copy_sha": job["copy_sha"], "approval_sha": job["approval_sha"],
            "review_sha": job["review_sha"], "template_sha": digest(template),
            "owner_candidate_receipt_sha": binding["owner_candidate_receipt_sha"]}
        return job, template, context, digest(context)

    @contextmanager
    def source_lock(self, actor, job_id):
        with self.flow.state.db() as db:
            db.execute("BEGIN IMMEDIATE")
            yield self.context(actor, job_id, db)

    @staticmethod
    def _read(c, actor, job_id, edit_id):
        if not ID.fullmatch(edit_id):
            raise LiveGateError("COMPOSED_EDIT_NOT_FOUND")
        row = c.execute("SELECT * FROM composed_copy_edits WHERE edit_id=? AND actor=? AND job_id=?",
                        (edit_id, actor, job_id)).fetchone()
        if row is None:
            raise LiveGateError("COMPOSED_EDIT_NOT_FOUND")
        record = json.loads(row["record_json"])
        if (record["actor"] != actor or record["job_id"] != job_id or
                record["edit_id"] != edit_id or record["state"] != row["state"] or
                record["request_sha"] != row["request_sha"] or
                record["request_key"] != row["request_key"]):
            raise LiveGateError("COMPOSED_EDIT_STORAGE_INTEGRITY")
        source = record["source_context"]
        request = {"expected_image_sha": source["image_sha"], "expected_copy_sha": source["copy_sha"],
                   "expected_approval_sha": source["approval_sha"], "ad_copy": record["copy"]["ad_copy"],
                   "request_key": record["request_key"]}
        if (digest(source) != record["source_context_sha"] or digest(record["copy"]) != record["copy_sha"]
                or digest(request) != record["request_sha"]):
            raise LiveGateError("COMPOSED_EDIT_STORAGE_INTEGRITY")
        model = record.get("review_model")
        if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", model)
                or record.get("review_model_sha") != digest({"request_sha": record["request_sha"], "model": model})):
            raise LiveGateError("COMPOSED_EDIT_REVIEW_MODEL_INTEGRITY")
        if record["review_sha"] and record["review_sha"] != digest({"protocol": PROTOCOL,
                "source": record["source_context_sha"], "copy_sha": record["copy_sha"], "report": record["report"]}):
            raise LiveGateError("COMPOSED_EDIT_REVIEW_INTEGRITY")
        if record["approval_sha"]:
            approval = record.get("copy_approval_record")
            if (not isinstance(approval, dict) or digest(approval) != record["approval_sha"] or
                    approval["copy_sha"] != record["copy_sha"] or approval["review_sha"] != record["review_sha"] or
                    approval["source_context_sha"] != record["source_context_sha"] or approval["edit_id"] != edit_id or
                    approval["actor"] != actor):
                raise LiveGateError("COMPOSED_EDIT_APPROVAL_INTEGRITY")
        return record

    @staticmethod
    def _save(c, record):
        c.execute("UPDATE composed_copy_edits SET state=?,record_json=? WHERE edit_id=?",
                  (record["state"], _canonical(record), record["edit_id"]))

    def _source_matches(self, record, context_sha):
        if record["source_context_sha"] != context_sha:
            raise LiveGateError("COMPOSED_EDIT_SOURCE_APPROVAL_STALE")

    def _review_binding(self, row):
        if row["review_origin"] == "SOURCE_F09_EXACT_COPY":
            if row["copy_sha"] != row["source_context"]["copy_sha"]:
                raise LiveGateError("COMPOSED_EDIT_REVIEW_INTEGRITY")
            return
        if not row["review_sha"]:
            raise LiveGateError("COMPOSED_EDIT_F09_REQUIRED")
        from .revision_receipts import verify_revision_cost
        llm = row["report"].get("llm_review") or {}
        fingerprint = {"protocol": PROTOCOL, "edit_id": row["edit_id"],
            "source_context_sha": row["source_context_sha"], "copy_sha": row["copy_sha"], "model": llm.get("model")}
        evidence = row["cost_receipt"]
        verify_revision_cost(self.flow, evidence, row["actor"], row["job_id"], "copy_review", fingerprint)
        if any(llm.get(key) != evidence.get(key) for key in ("attempt_id", "receipt_sha", "response_model")):
            raise LiveGateError("COMPOSED_EDIT_REVIEW_INTEGRITY")

    def _artifact_path(self, record, kind):
        return self.root / record["edit_id"] / {"preview": "preview.png", "final": "final.png",
            "caption": "caption.txt", "receipt": "receipt.json"}[kind]

    def public(self, record, current_context_sha):
        out = {key: record.get(key) for key in ("edit_id", "state", "revision", "copy", "copy_sha",
            "review_sha", "approval_sha", "preview_sha", "final_sha", "caption_sha", "receipt_sha",
            "report", "error_code", "review_origin", "cost_receipt", "source_context_sha")}
        out.update(protocol=PROTOCOL, rendering="composed_manual_copy_revision_v1", image_provider_calls=0,
                   actual_usd=None, cost_status="UNPRICED" if record.get("cost_receipt") else "NOT_DISPATCHED")
        current = record["source_context_sha"] == current_context_sha
        if not current:
            out.update(state="HOLD", error_code="COMPOSED_EDIT_SOURCE_APPROVAL_STALE")
        artifacts = {}
        if current and record["state"] in ("IMAGE_REVIEW_REQUIRED", "COMPLETED"):
            kinds = ("preview", "final", "caption", "receipt") if record["state"] == "COMPLETED" else ("preview",)
            for kind in kinds:
                value = record.get(kind+"_sha")
                if value:
                    artifacts[kind] = (f"/demo/api/live/jobs/{record['job_id']}/composed-copy-edits/"
                        f"{record['edit_id']}/artifacts/{kind}?sha256={value}")
        out["artifacts"] = artifacts
        return out

    def snapshot(self, actor, job_id):
        with self.source_lock(actor, job_id) as (job, _, _, context_sha):
            records = []
            if self.file.exists():
                with self.db() as c:
                    records = [self._read(c, actor, job_id, row[0]) for row in c.execute(
                        "SELECT edit_id FROM composed_copy_edits WHERE actor=? AND job_id=? ORDER BY rowid DESC",
                        (actor, job_id))]
            from .revision_costs import revision_cost_summary
            return {"available": enabled(), "protocol": PROTOCOL, "job_id": job_id,
                "cost_summary": revision_cost_summary(self.flow, actor, job_id),
                "approved_copy": json.loads(job["copy_json"])["ad_copy"],
                "source_image_sha": job["image_sha"], "source_copy_sha": job["copy_sha"],
                "source_approval_sha": job["approval_sha"], "copy_sha": job["copy_sha"],
                "approval_sha": job["approval_sha"], "context_sha": context_sha,
                "edits": [self.public(row, context_sha) for row in records]}

    def _unknown(self):
        with self.flow.cost.connect() as c:
            return c.execute("SELECT 1 FROM attempts WHERE billing_unknown=1 OR status IN ('DISPATCHED','BILLING_UNKNOWN') LIMIT 1").fetchone() is not None

    def create(self, actor, job_id, payload):
        from src.text_generation.schemas import AdCopyOutput
        from src.serving.text_v08_mapper import verify_copy
        if not enabled():
            raise LiveGateError("COMPOSED_EDIT_DISABLED")
        self.flow.require_live_actor(actor)
        request_sha = digest(payload)
        with self.source_lock(actor, job_id) as (job, _, context, context_sha):
            if any(payload["expected_"+field] != job[field] for field in ("image_sha", "copy_sha", "approval_sha")):
                raise LiveGateError("COMPOSED_EDIT_SOURCE_APPROVAL_STALE")
            original = json.loads(job["copy_json"])
            proposed = {**original, "ad_copy": payload["ad_copy"]}
            verified = verify_copy(proposed, model=AdCopyOutput)
            report = strict_review(verified.output, json.loads(job["input_json"])["product"],
                                   json.loads(job["analysis_json"]))
            same = verified.sha256 == job["copy_sha"]
            review_model = os.environ.get("IT_TEM_TEXT_MODEL", "gpt-6-luna") if not same else None
            if review_model is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", review_model):
                raise LiveGateError("COMPOSED_EDIT_REVIEW_MODEL_INVALID")
            if same:
                report = json.loads(job["compliance_json"])
            with self.db(create=True) as c:
                c.execute("BEGIN IMMEDIATE")
                old = c.execute("SELECT edit_id,request_sha FROM composed_copy_edits WHERE actor=? AND job_id=? AND request_key=?",
                    (actor, job_id, payload["request_key"])).fetchone()
                if old:
                    if old["request_sha"] != request_sha:
                        raise LiveGateError("COMPOSED_EDIT_IDEMPOTENCY_CONFLICT")
                    return self.public(self._read(c, actor, job_id, old["edit_id"]), context_sha)
                if self._unknown() or c.execute("SELECT 1 FROM composed_copy_edits WHERE state IN ('RUNNING','BILLING_UNKNOWN') LIMIT 1").fetchone():
                    raise LiveGateError("COMPOSED_EDIT_BILLING_UNKNOWN_OR_RUNNING")
                row = {"edit_id": uuid4().hex, "actor": actor, "job_id": job_id,
                    "protocol": PROTOCOL, "request_sha": request_sha, "request_key": payload["request_key"],
                    "review_model": review_model,
                    "review_model_sha": digest({"request_sha": request_sha, "model": review_model}) if review_model else None,
                    "source_context": context, "source_context_sha": context_sha,
                    "copy": verified.output, "copy_sha": verified.sha256, "report": report,
                    "state": ("COPY_REVIEW_REQUIRED" if same else "QUEUED_REVIEW") if report["passed"] else "RULE_BLOCKED",
                    "revision": 0, "review_origin": "SOURCE_F09_EXACT_COPY" if same else "MANUAL_EDIT_REQUIRES_NEW_F09",
                    "review_sha": digest({"protocol": PROTOCOL, "source": context_sha,
                        "copy_sha": verified.sha256, "report": report}) if same else None,
                    "approval_sha": None, "preview_sha": None, "final_sha": None,
                    "caption_sha": None, "receipt_sha": None, "cost_receipt": None, "error_code": None}
                c.execute("INSERT INTO composed_copy_edits VALUES(?,?,?,?,?,?,?)",
                    (row["edit_id"], actor, job_id, payload["request_key"], request_sha, row["state"], _canonical(row)))
                c.commit()
                return self.public(row, context_sha)

    def _render(self, record, template):
        from src.image_generation import CompositionInput, compose_ad_png
        from src.image_generation.composition import CompositionLayout
        font = Path(os.environ.get("IT_TEM_LIVE_KOREAN_FONT", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))
        font_sha = sha256(font.read_bytes()).hexdigest()
        required = template["safe_zone"].get("required_font_sha") or template.get("bound_font_sha")
        if required and font_sha != required:
            raise LiveGateError("COMPOSED_EDIT_FONT_CHANGED")
        source = self.flow.image_path(record["job_id"]).read_bytes()
        if sha256(source).hexdigest() != record["source_context"]["image_sha"]:
            raise LiveGateError("COMPOSED_EDIT_SOURCE_BYTES_CHANGED")
        result = compose_ad_png(CompositionInput(job_id=record["job_id"], image_bytes=source,
            image_sha256=record["source_context"]["image_sha"], copy_revision=record["edit_id"],
            copy_hash=record["copy_sha"], copy_output=record["copy"],
            layout=CompositionLayout.model_validate_json(_canonical(template["layout"]))), font_path=font)
        record["preview_sha"] = result.sha256
        record["composition_receipt"] = result.receipt
        record["font_sha"] = font_sha
        license_sha = template["safe_zone"].get("font_license_sha")
        if license_sha:
            license_file = Path(os.environ.get("IT_TEM_DERIVED_FONT_LICENSE", ""))
            if sha256(license_file.read_bytes()).hexdigest() != license_sha:
                raise LiveGateError("COMPOSED_EDIT_FONT_LICENSE_CHANGED")
        record["font_license_sha"] = license_sha
        atomic_write(self._artifact_path(record, "preview"), result.image_bytes)
        return result

    def approve_copy(self, actor, job_id, edit_id, body):
        with self.source_lock(actor, job_id) as (_, template, _, context_sha), self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = self._read(c, actor, job_id, edit_id)
            self._source_matches(row, context_sha)
            self._review_binding(row)
            if row["revision"] != body["expected_revision"] or row["copy_sha"] != body["expected_copy_sha"] or row["review_sha"] != body["expected_review_sha"]:
                raise LiveGateError("COMPOSED_EDIT_COPY_APPROVAL_STALE")
            if row["state"] != "COPY_REVIEW_REQUIRED" or not row["report"]["passed"] or body["acknowledge_evidence"] is not True:
                raise LiveGateError("COMPOSED_EDIT_F09_OR_ACK_REQUIRED")
            row["copy_approval_record"] = {"protocol": PROTOCOL, "edit_id": edit_id, "actor": actor,
                "copy_sha": row["copy_sha"], "review_sha": row["review_sha"], "source_context_sha": context_sha,
                "revision": row["revision"], "acknowledge_evidence": True}
            row["approval_sha"] = digest(row["copy_approval_record"])
            self._render(row, template)
            row.update(state="IMAGE_REVIEW_REQUIRED", revision=row["revision"]+1)
            self._save(c, row); c.commit()
            return self.public(row, context_sha)

    def decide(self, actor, job_id, edit_id, body):
        with self.source_lock(actor, job_id) as (_, _, _, context_sha), self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = self._read(c, actor, job_id, edit_id)
            self._source_matches(row, context_sha)
            self._review_binding(row)
            if row["state"] != "IMAGE_REVIEW_REQUIRED" or row["revision"] != body["expected_revision"] or row["preview_sha"] != body["expected_preview_sha"]:
                raise LiveGateError("COMPOSED_EDIT_IMAGE_APPROVAL_STALE")
            if not body["approve"]:
                row.update(state="REJECTED", revision=row["revision"]+1)
            else:
                checks = body.get("visual_review") or {}
                if (set(checks) != {"product_matches", "label_matches", "cta_policy_matches", "observed_copy", "no_extra_text"}
                        or any(checks[key] is not True for key in ("product_matches", "label_matches", "cta_policy_matches", "no_extra_text"))
                        or checks["observed_copy"] != row["copy"]["ad_copy"]):
                    raise LiveGateError("COMPOSED_EDIT_VISUAL_REVIEW_REQUIRED")
                preview = self._artifact_path(row, "preview").read_bytes()
                if sha256(preview).hexdigest() != row["preview_sha"]:
                    raise LiveGateError("COMPOSED_EDIT_ARTIFACT_INTEGRITY")
                cp = row["copy"]
                caption = (cp["caption"] + ("\n\n" if cp["caption"] and cp["hashtags"] else "") + " ".join(cp["hashtags"])).encode("utf-8")
                receipt = {"schema": "bp18-composed-manual-copy-edit-v1", "protocol": PROTOCOL,
                    "rendering": "server_composed_manual_copy", "edit_id": edit_id, "actor": actor,
                    "job_id": job_id, "source_context": row["source_context"],
                    "source_context_sha": context_sha, "copy_sha": row["copy_sha"],
                    "f09_review_sha": row["review_sha"], "copy_approval_sha": row["approval_sha"],
                    "preview_sha": row["preview_sha"], "final_sha": row["preview_sha"],
                    "caption_sha": sha256(caption).hexdigest(), "visual_review": checks,
                    "composition": row["composition_receipt"], "font_license_sha": row["font_license_sha"], "image_provider_calls": 0,
                    "text_provider_calls": 1 if row["cost_receipt"] else 0,
                    "cost_receipt": row["cost_receipt"], "actual_usd": None,
                    "billing_status": "UNPRICED" if row["cost_receipt"] else "NO_NEW_PROVIDER_CALL",
                    "source_image_approval_inherited": False, "label_human_attestation": True,
                    "literal_label_ground_truth": "NOT_INDEPENDENTLY_ESTABLISHED"}
                data = _canonical(receipt).encode()
                atomic_write(self._artifact_path(row, "final"), preview)
                atomic_write(self._artifact_path(row, "caption"), caption)
                atomic_write(self._artifact_path(row, "receipt"), data)
                row.update(state="COMPLETED", final_sha=row["preview_sha"], caption_sha=sha256(caption).hexdigest(),
                           receipt_sha=sha256(data).hexdigest(), revision=row["revision"]+1)
            self._save(c, row); c.commit()
            return self.public(row, context_sha)

    def artifact(self, actor, job_id, edit_id, kind, expected_sha):
        if kind not in ("preview", "final", "caption", "receipt"):
            raise LiveGateError("COMPOSED_EDIT_ARTIFACT_NOT_FOUND")
        with self.source_lock(actor, job_id) as (_, _, _, context_sha), self.db() as c:
            row = self._read(c, actor, job_id, edit_id)
            self._source_matches(row, context_sha)
            self._review_binding(row)
            if row["state"] not in ("IMAGE_REVIEW_REQUIRED", "COMPLETED") or (kind != "preview" and row["state"] != "COMPLETED"):
                raise LiveGateError("COMPOSED_EDIT_FINAL_APPROVAL_REQUIRED")
            if not expected_sha or row.get(kind+"_sha") != expected_sha:
                raise LiveGateError("COMPOSED_EDIT_ARTIFACT_SHA_STALE")
            data = self._artifact_path(row, kind).read_bytes()
            if sha256(data).hexdigest() != expected_sha:
                raise LiveGateError("COMPOSED_EDIT_ARTIFACT_INTEGRITY")
            return data


def run_composed_copy_edit_once(flow, *, recover_only=False):
    """Called under the existing exclusive paid Worker lock; never auto-retry."""
    if not enabled():
        return "NO_COMPOSED_COPY_EDIT"
    service = ComposedCopyEdits(flow)
    if not service.file.exists():
        return "NO_COMPOSED_COPY_EDIT"
    with service.db() as c:
        c.execute("BEGIN IMMEDIATE")
        running = c.execute("SELECT record_json FROM composed_copy_edits WHERE state='RUNNING'").fetchall()
        for record in running:
            row = json.loads(record[0]); row.update(state="BILLING_UNKNOWN", error_code="COMPOSED_EDIT_INTERRUPTED_NO_AUTOMATIC_RETRY")
            service._save(c, row)
        if running or service._unknown() or c.execute("SELECT 1 FROM composed_copy_edits WHERE state='BILLING_UNKNOWN' LIMIT 1").fetchone():
            c.commit()
            return "COMPOSED_COPY_EDIT_BILLING_UNKNOWN"
        if recover_only:
            c.commit()
            return "NO_COMPOSED_COPY_EDIT"
        record = c.execute("SELECT record_json FROM composed_copy_edits WHERE state='QUEUED_REVIEW' ORDER BY rowid LIMIT 1").fetchone()
        if record is None:
            return "NO_COMPOSED_COPY_EDIT"
        raw_record = json.loads(record[0])
        row = service._read(c, raw_record["actor"], raw_record["job_id"], raw_record["edit_id"])
        row.update(state="RUNNING")
        service._save(c, row); c.commit()
    actor, job_id = row["actor"], row["job_id"]
    receipt = None
    fingerprint = None
    try:
        flow.require_live_actor(actor)
        with service.source_lock(actor, job_id) as (job, _, _, context_sha):
            service._source_matches(row, context_sha)
            product = json.loads(job["input_json"])["product"]
        from . import pipeline
        from .copy_review import complete_report
        from src.text_generation.schemas import AdCopyOutput, ProductInput
        configured_model = os.environ.get("IT_TEM_TEXT_MODEL", "gpt-6-luna")
        # Historical records without this field preserve their original format.
        # New requests freeze the model before queueing and may not drift across
        # a policy change, restart, or accounting reconciliation.
        model = row.get("review_model") or configured_model
        if model != configured_model:
            raise LiveGateError("COMPOSED_EDIT_REVIEW_MODEL_CHANGED")
        cp, product = AdCopyOutput.model_validate(row["copy"], strict=True), ProductInput.model_validate(product, strict=True)
        fingerprint = {"protocol": PROTOCOL, "edit_id": row["edit_id"], "source_context_sha": context_sha,
                       "copy_sha": row["copy_sha"], "model": model}
        result, receipt = flow._guarded(actor, job_id, "copy_review", fingerprint,
            lambda: pipeline.OfficialTextProvider(model, model).review_copy(cp, product, row["report"]), include_receipt=True)
        report = complete_report(row["report"], cp, product, result, fingerprint, receipt)
        with service.source_lock(actor, job_id) as (_, _, _, fresh_context_sha), service.db() as c:
            c.execute("BEGIN IMMEDIATE")
            current = service._read(c, actor, job_id, row["edit_id"])
            if current["state"] != "RUNNING":
                raise LiveGateError("COMPOSED_EDIT_WORKER_STATE_CONFLICT")
            service._source_matches(row, fresh_context_sha)
            row.update(state="COPY_REVIEW_REQUIRED", report=report, cost_receipt=receipt, revision=row["revision"]+1,
                       review_origin="MANUAL_EDIT_NEW_RULE_AND_LLM_F09",
                       review_sha=digest({"protocol": PROTOCOL, "source": context_sha, "copy_sha": row["copy_sha"], "report": report}))
            service._save(c, row); c.commit()
        return "COMPOSED_COPY_EDIT_REVIEW_COMMITTED"
    except BaseException as error:
        with service.db() as c:
            c.execute("BEGIN IMMEDIATE")
            current = service._read(c, actor, job_id, row["edit_id"])
            unknown = service._unknown()
            if receipt:
                current["cost_receipt"] = receipt
            elif fingerprint:
                with flow.cost.connect() as cost_db:
                    paid = cost_db.execute("SELECT id,receipt FROM attempts WHERE actor=? AND job_id=? AND stage='copy_review' AND payload_hash=?",
                        (actor, job_id, digest(fingerprint))).fetchone()
                if paid and paid["receipt"]:
                    usage = json.loads(paid["receipt"])
                    current["cost_receipt"] = {"attempt_id": paid["id"], "receipt_sha": digest(usage), "response_model": usage.get("model")}
            code = error.code if isinstance(error, LiveGateError) else "COMPOSED_EDIT_WORKER_FAILED"
            current.update(state="BILLING_UNKNOWN" if unknown else "HOLD", error_code=code, revision=current["revision"]+1)
            service._save(c, current); c.commit()
        if not isinstance(error, Exception):
            raise
        return "COMPOSED_COPY_EDIT_BILLING_UNKNOWN" if unknown else "COMPOSED_COPY_EDIT_HELD"
