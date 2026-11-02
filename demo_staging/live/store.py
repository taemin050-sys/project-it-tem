"""Single-writer durable Live state: owner artifacts and approvals never masquerade as Mock.

All mutation is transactional; image attempts and provider receipts reside in
the existing Owner image ledger / an independent aggregate attempt ledger.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import LiveGateError, digest, validate_input, strict_review, live_prompt, owner_text_snapshots
from .template_contract import (A_ID,A_VERSION,LEGACY_ID,LEGACY_VERSION,
    owner_a_policy,normalize_layout,verify_policy,canonical)


class LiveStore:
    def __init__(self, filename: Path):
        self.filename=Path(filename)
        self.filename.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as cx:
            cx.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS live_jobs (
                job_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                state TEXT NOT NULL, mode TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0,
                input_json TEXT NOT NULL, input_sha TEXT NOT NULL,
                analysis_json TEXT, research_json TEXT, research_display_json TEXT,
                copy_json TEXT, copy_sha TEXT,
                compliance_json TEXT, review_sha TEXT,
                approval_sha TEXT, approved_generation INTEGER,
                evidence_acknowledged INTEGER NOT NULL DEFAULT 0,
                prompt_json TEXT, image_sha TEXT,
                image_approval_sha TEXT, final_sha TEXT, caption_sha TEXT,
                last_error_code TEXT
            );
            CREATE TABLE IF NOT EXISTS live_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                generation INTEGER NOT NULL, event TEXT NOT NULL,
                status TEXT NOT NULL, payload_sha TEXT, recorded_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS live_job_templates (
                job_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL, profile_version TEXT NOT NULL,
                safe_zone_json TEXT, safe_zone_sha TEXT NOT NULL,
                layout_json TEXT NOT NULL, layout_sha TEXT NOT NULL,
                bound_font_sha TEXT, bound_context_sha TEXT,
                created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS live_compose_manifests (
                job_id TEXT PRIMARY KEY,
                receipt_json TEXT NOT NULL, envelope_json TEXT NOT NULL,
                receipt_sha TEXT NOT NULL, envelope_sha TEXT NOT NULL,
                final_sha TEXT NOT NULL, caption_sha TEXT NOT NULL,
                created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS live_queue (
                job_id TEXT NOT NULL, stage TEXT NOT NULL,
                context_sha TEXT NOT NULL, state TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                UNIQUE(job_id,stage,context_sha)
            );
            """)

    def db(self):
        c=sqlite3.connect(str(self.filename),timeout=15)
        c.execute("PRAGMA busy_timeout=15000")
        c.row_factory=sqlite3.Row
        return c

    def _read(self,c,job_id,actor):
        r=c.execute("SELECT * FROM live_jobs WHERE job_id=? AND actor=?",(job_id,actor)).fetchone()
        if not r:
            raise LiveGateError("LIVE_JOB_NOT_FOUND")
        return dict(r)

    @staticmethod
    def _event(c,job,ev,status,sha=None):
        c.execute("""INSERT INTO live_events(job_id,generation,event,status,payload_sha)
            VALUES (?,?,?,?,?)""",(job["job_id"],job["generation"],ev,status,sha))

    def create(self,actor,job_id,input_body,assets,*,template_profile="LEGACY"):
        if template_profile not in ("LEGACY","A"):
            raise LiveGateError("TEMPLATE_PROFILE_INVALID")
        # Validate the complete Owner policy before opening the DB transaction.
        a_policy=owner_a_policy() if template_profile=="A" else None
        snapshot,sha=validate_input(input_body,assets)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            existing=c.execute("SELECT * FROM live_jobs WHERE job_id=?",(job_id,)).fetchone()
            if existing:
                if existing["actor"]!=actor:
                    raise LiveGateError("LIVE_JOB_NOT_FOUND")
                if existing["input_sha"]!=sha:
                    raise LiveGateError("LIVE_INPUT_CONFLICT")
                return self._read(c,job_id,actor)
            c.execute("""INSERT INTO live_jobs
                (job_id,actor,state,mode,input_json,input_sha)
                VALUES (?,?,?,'INPUT_ONLY',?,?)""",
                (job_id,actor,"INPUT_STORED",json.dumps(snapshot,ensure_ascii=False),sha))
            if a_policy is not None:
                zone,layout=a_policy["safe_zone"],a_policy["layout"]
                c.execute("""INSERT INTO live_job_templates
                    (job_id,profile_id,profile_version,safe_zone_json,safe_zone_sha,
                     layout_json,layout_sha) VALUES (?,?,?,?,?,?,?)""",
                    (job_id,A_ID,A_VERSION,canonical(zone),digest(zone),
                     canonical(layout),digest(layout)))
            r=self._read(c,job_id,actor)
            self._event(c,r,"input_committed",r["state"],sha)
            if template_profile=="A":
                # Durable ingress provenance in the existing append-only event log.
                # A deleted template row must not disguise an A Job as old legacy.
                self._event(c,r,"template_a_ingress_contract_v1",r["state"],digest({
                    "profile_id":A_ID,"profile_version":A_VERSION,
                    "input_sha":sha,"safe_zone_sha":digest(zone),
                    "layout_sha":digest(layout)}))
            if template_profile=="LEGACY":
                # Distinguish known new internal legacy fixtures from old,
                # pre-policy IMAGE_APPROVED jobs whose original compose layout
                # cannot be reconstructed. Never silently import old layouts.
                self._event(c,r,"legacy_ingress_contract_v1",r["state"],sha)
            c.commit()
            return r

    def get(self,actor,job_id):
        with self.db() as c:
            return self._read(c,job_id,actor)

    def store_text(self,actor,job_id,analysis,research,copy,*,mode="OFFLINE_FIXTURE"):
        if mode not in ("OFFLINE_FIXTURE","LIVE"):
            raise LiveGateError("INVALID_PROVENANCE")
        a,r,display,candidate,sha=owner_text_snapshots(analysis,research,copy)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="INPUT_STORED":
                raise LiveGateError("LIVE_TEXT_STATE_CONFLICT")
            context=json.loads(job["input_json"])
            report=strict_review(candidate,context["product"],a)
            report_sha=digest({"input_sha":job["input_sha"],"analysis":a,
                              "copy":candidate,"report":report,"generation":job["generation"]+1})
            c.execute("""UPDATE live_jobs SET state='COPY_REVIEW_REQUIRED',mode=?,generation=generation+1,
               analysis_json=?,research_json=?,research_display_json=?,
               copy_json=?,copy_sha=?,compliance_json=?,review_sha=? WHERE job_id=?""",
               (mode,json.dumps(a,ensure_ascii=False),json.dumps(r,ensure_ascii=False),
                json.dumps(display,ensure_ascii=False),
                json.dumps(candidate,ensure_ascii=False),sha,
                json.dumps(report,ensure_ascii=False),report_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"real_review_evaluated",updated["state"],report_sha)
            c.commit()
            return updated

    def edit_copy(self,actor,job_id,new_copy):
        from src.serving.text_v08_mapper import verify_copy
        from src.text_generation.schemas import AdCopyOutput
        parsed=verify_copy(new_copy,model=AdCopyOutput)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"] not in ("COPY_REVIEW_REQUIRED","COPY_APPROVED","COPY_REJECTED"):
                raise LiveGateError("COPY_EDIT_STATE_CONFLICT")
            if parsed.sha256==job["copy_sha"]:
                raise LiveGateError("COPY_EDIT_UNCHANGED")
            context=json.loads(job["input_json"])
            analysis=json.loads(job["analysis_json"])
            report=strict_review(parsed.output,context["product"],analysis)
            generation=job["generation"]+1
            report_sha=digest({"input_sha":job["input_sha"],"analysis":analysis,
                              "copy":parsed.output,"report":report,"generation":generation})
            c.execute("""UPDATE live_jobs SET generation=?,state='COPY_REVIEW_REQUIRED',copy_json=?,
              copy_sha=?,compliance_json=?,review_sha=?,approval_sha=NULL,
              approved_generation=NULL,evidence_acknowledged=0,prompt_json=NULL,image_sha=NULL,
              image_approval_sha=NULL,final_sha=NULL,caption_sha=NULL WHERE job_id=?""",
              (generation,json.dumps(parsed.output,ensure_ascii=False),parsed.sha256,
               json.dumps(report,ensure_ascii=False),report_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"copy_edited_review_restarted",updated["state"],report_sha)
            c.commit()
            return updated

    def approval_binding(self,job):
        return digest({"input_sha":job["input_sha"],"analysis":json.loads(job["analysis_json"]),
                       "copy_sha":job["copy_sha"],"review_sha":job["review_sha"],
                       "generation":job["generation"],
                       "evidence_acknowledged":bool(job["evidence_acknowledged"])})

    def approve_copy(self,actor,job_id,expected_generation,expected_review_sha,*,acknowledge_evidence=False):
        if type(expected_generation) is not int:
            raise LiveGateError("REVISION_TYPE_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_APPROVAL_STATE_CONFLICT")
            if job["generation"]!=expected_generation or job["review_sha"]!=expected_review_sha:
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            review=json.loads(job["compliance_json"])
            if not review["passed"]:
                raise LiveGateError("REAL_COMPLIANCE_BLOCKED")
            if (any(x["risk_level"]=="근거 확인 필요" for x in review["issues"])
                    and acknowledge_evidence is not True):
                raise LiveGateError("EVIDENCE_ACKNOWLEDGEMENT_REQUIRED")
            # Persist the user declaration BEFORE binding an approval.
            c.execute("UPDATE live_jobs SET evidence_acknowledged=? WHERE job_id=?",
                      (int(acknowledge_evidence is True),job_id))
            bound=self._read(c,job_id,actor)
            binding=self.approval_binding(bound)
            c.execute("""UPDATE live_jobs SET state='COPY_APPROVED',approval_sha=?,
                approved_generation=? WHERE job_id=?""",
                (binding,expected_generation,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"real_copy_approved",updated["state"],binding)
            c.commit()
            return updated

    def reject_copy(self,actor,job_id):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_REJECTION_STATE_CONFLICT")
            c.execute("""UPDATE live_jobs SET state='COPY_REJECTED',
              approval_sha=NULL,approved_generation=NULL,evidence_acknowledged=0
              WHERE job_id=?""",(job_id,))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"copy_rejected",updated["state"],job["review_sha"])
            c.commit()
            return updated

    def _approved(self,job):
        if not (job["state"] in {"COPY_APPROVED","PROMPT_READY","IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED"}
                and job["approval_sha"] and job["approved_generation"]==job["generation"]
                and job["approval_sha"]==self.approval_binding(job)
                and json.loads(job["compliance_json"])["passed"]):
            raise LiveGateError("APPROVAL_CONTEXT_NOT_CURRENT")

    def store_prompt(self,actor,job_id,prompt):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_APPROVED":
                raise LiveGateError("PROMPT_REQUIRES_COPY_APPROVAL")
            self._approved(job)
            cp=json.loads(job["copy_json"])
            parsed=live_prompt(prompt,cp)
            c.execute("UPDATE live_jobs SET state='PROMPT_READY',prompt_json=? WHERE job_id=?",
                     (json.dumps(parsed,ensure_ascii=False),job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"image_prompt_committed",updated["state"],digest(parsed))
            c.commit()
            return updated

    def template(self,actor,job_id):
        with self.db() as c:
            self._read(c,job_id,actor)
            row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",(job_id,)).fetchone()
            return verify_policy(row)

    def image_request(self,actor,job_id,images,references):
        from src.image_generation import BackendImageInput
        from src.image_generation.contracts import content_hash
        with self.db() as c:
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_REQUIRES_PROMPT")
            self._approved(job)
            profile_row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                                  (job_id,)).fetchone()
            policy=verify_policy(profile_row)
            owner=BackendImageInput.model_validate({
                "job_id":job_id,"copy_revision":job["generation"],
                "copy_hash":job["copy_sha"],
                "product_analysis":json.loads(job["analysis_json"]),
                "image_prompt":json.loads(job["prompt_json"]),
                "ad_copy":json.loads(job["copy_json"])["ad_copy"],
                "caption":json.loads(job["copy_json"])["caption"],
                "hashtags":json.loads(job["copy_json"])["hashtags"],
                "product_images":images,"reference_images":references,
                "safe_zone":policy["safe_zone"] if policy else None,
            })
            if content_hash(json.loads(job["copy_json"])) != job["copy_sha"]:
                raise LiveGateError("APPROVED_COPY_CHANGED")
            return owner

    def store_image_candidate(self,actor,job_id,sha):
        if not isinstance(sha,str) or len(sha)!=64:
            raise LiveGateError("IMAGE_HASH_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_STATE_CONFLICT")
            self._approved(job)
            c.execute("UPDATE live_jobs SET state='IMAGE_REVIEW_REQUIRED',image_sha=? WHERE job_id=?",
                     (sha,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"image_candidate_committed",updated["state"],sha)
            c.commit()
            return updated

    def approve_image(self,actor,job_id,expected_sha):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_REVIEW_REQUIRED" or expected_sha!=job["image_sha"]:
                raise LiveGateError("IMAGE_APPROVAL_MISMATCH")
            self._approved(job)
            bind=digest({"image_sha":job["image_sha"],"approval_sha":job["approval_sha"],
                         "generation":job["generation"],
                       "evidence_acknowledged":bool(job["evidence_acknowledged"])})
            c.execute("""UPDATE live_jobs SET state='IMAGE_APPROVED',image_approval_sha=?
                WHERE job_id=?""",(bind,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"real_image_approved",updated["state"],bind)
            c.commit()
            return updated

    def reject_image(self,actor,job_id,expected_sha):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_REVIEW_REQUIRED" or expected_sha!=job["image_sha"]:
                raise LiveGateError("IMAGE_REJECTION_STATE_CONFLICT")
            self._approved(job)
            c.execute("""UPDATE live_jobs SET state='IMAGE_REJECTED',
              image_approval_sha=NULL WHERE job_id=?""",(job_id,))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"image_rejected",updated["state"],expected_sha)
            c.commit()
            return updated

    def plan_compose(self,actor,job_id,provided_layout,font_sha,*,has_prior_files=False):
        """Freeze layout/font/approval context. Reattempts cannot change contract."""
        if not isinstance(font_sha,str) or len(font_sha)!=64:
            raise LiveGateError("COMPOSITION_FONT_HASH_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_APPROVED":
                raise LiveGateError("FINAL_REQUIRES_IMAGE_APPROVAL")
            self._approved(job)
            expected=digest({"image_sha":job["image_sha"],
                 "approval_sha":job["approval_sha"],"generation":job["generation"],
                 "evidence_acknowledged":bool(job["evidence_acknowledged"])})
            if expected!=job["image_approval_sha"]:
                raise LiveGateError("IMAGE_APPROVAL_STALE")
            row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                          (job_id,)).fetchone()
            policy=verify_policy(row)
            if policy is None:
                # Pre-policy, never infer and assign A to existing jobs.
                # Only Jobs explicitly marked as new internal legacy fixtures
                # can pin a fresh caller layout. Older unversioned Jobs require
                # an approved manual recovery/import (not implemented here).
                marker=c.execute("""SELECT 1 FROM live_events
                     WHERE job_id=? AND event='legacy_ingress_contract_v1'
                     LIMIT 1""",(job_id,)).fetchone()
                if not marker or provided_layout is None or has_prior_files:
                    raise LiveGateError("LEGACY_LAYOUT_MANUAL_RECONCILIATION_REQUIRED")
                layout=normalize_layout(provided_layout)
                c.execute("""INSERT INTO live_job_templates
                    (job_id,profile_id,profile_version,safe_zone_json,safe_zone_sha,
                     layout_json,layout_sha) VALUES (?,?,?,?,?,?,?)""",
                    (job_id,LEGACY_ID,LEGACY_VERSION,None,digest(None),
                     canonical(layout),digest(layout)))
                row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                              (job_id,)).fetchone()
                policy=verify_policy(row)
            else:
                layout=policy["layout"]
                if provided_layout is not None and digest(normalize_layout(provided_layout))!=policy["layout_sha"]:
                    raise LiveGateError("COMPOSITION_LAYOUT_CONFLICT")
            context_sha=digest({"input_sha":job["input_sha"],
                "copy_sha":job["copy_sha"],"copy_revision":job["generation"],
                "approval_sha":job["approval_sha"],"image_sha":job["image_sha"],
                "image_approval_sha":job["image_approval_sha"],
                "layout_sha":policy["layout_sha"],"safe_zone_sha":policy["safe_zone_sha"]})
            if row["bound_font_sha"] is not None and (
                row["bound_font_sha"]!=font_sha or row["bound_context_sha"]!=context_sha):
                raise LiveGateError("COMPOSITION_FROZEN_INPUT_CONFLICT")
            if row["bound_font_sha"] is None:
                c.execute("""UPDATE live_job_templates
                    SET bound_font_sha=?,bound_context_sha=? WHERE job_id=?""",
                    (font_sha,context_sha,job_id))
                # A separate event remains when a policy/manifest record is lost.
                self._event(c,job,"compose_contract_frozen_v1",job["state"],context_sha)
            c.commit()
            return {"layout":layout,"layout_sha":policy["layout_sha"],
                    "font_sha":font_sha,"context_sha":context_sha,
                    "profile_id":policy["profile_id"],"profile_version":policy["profile_version"],
                    "manual_review_required":True}

    def commit_composition(self,connection,actor,job_id,plan,receipt,final_sha,caption_sha):
        """Called under an existing BEGIN IMMEDIATE lock after files are promoted."""
        job=self._read(connection,job_id,actor)
        if job["state"]!="IMAGE_APPROVED":
            raise LiveGateError("FINAL_REQUIRES_IMAGE_APPROVAL")
        self._approved(job)
        profile=verify_policy(connection.execute(
            "SELECT * FROM live_job_templates WHERE job_id=?",(job_id,)).fetchone())
        if (not profile or profile["layout_sha"]!=plan["layout_sha"] or
            profile["bound_font_sha"]!=plan["font_sha"] or
            profile["bound_context_sha"]!=plan["context_sha"]):
            raise LiveGateError("COMPOSITION_FROZEN_INPUT_CONFLICT")
        if connection.execute("SELECT 1 FROM live_compose_manifests WHERE job_id=?",
                              (job_id,)).fetchone():
            raise LiveGateError("COMPOSITION_ALREADY_FINALIZED")
        # Receipt is Owner output; envelope is Serving-only immutable binding.
        envelope={"job_id":job_id,"profile_id":plan["profile_id"],
            "profile_version":plan["profile_version"],"layout_sha":plan["layout_sha"],
            "font_sha":plan["font_sha"],"context_sha":plan["context_sha"],
            "copy_sha":job["copy_sha"],"generation":job["generation"],
            "image_sha":job["image_sha"],"approval_sha":job["approval_sha"],
            "image_approval_sha":job["image_approval_sha"],
            "final_sha":final_sha,"caption_sha":caption_sha}
        receipt_sha=digest(receipt)
        connection.execute("""INSERT INTO live_compose_manifests
            (job_id,receipt_json,envelope_json,receipt_sha,envelope_sha,final_sha,caption_sha)
            VALUES (?,?,?,?,?,?,?)""",
            (job_id,canonical(receipt),canonical(envelope),receipt_sha,digest(envelope),
             final_sha,caption_sha))
        connection.execute("""UPDATE live_jobs SET state='COMPLETED',final_sha=?,
            caption_sha=? WHERE job_id=? AND state='IMAGE_APPROVED'""",
            (final_sha,caption_sha,job_id))
        updated=self._read(connection,job_id,actor)
        self._event(connection,updated,"composed",updated["state"],final_sha)
        return updated

    def read_manifest(self,actor,job_id):
        with self.db() as c:
            job=self._read(c,job_id,actor)
            r=c.execute("SELECT * FROM live_compose_manifests WHERE job_id=?",
                        (job_id,)).fetchone()
            policy_row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                                 (job_id,)).fetchone()
            managed_marker=c.execute("""SELECT 1 FROM live_events WHERE job_id=?
                AND event IN ('template_a_ingress_contract_v1',
                              'compose_contract_frozen_v1') LIMIT 1""",
                (job_id,)).fetchone()
            if r is None:
                # A/LEGACY_PINNED finalized with this contract always requires its
                # durable receipt; only true pre-policy COMPLETED rows may omit it.
                # Retained events also catch a policy row deleted along with receipt.
                if job["state"]=="COMPLETED" and (
                        policy_row is not None or managed_marker is not None):
                    raise LiveGateError("COMPOSITION_MANIFEST_REQUIRED")
                return None
            try:
                receipt=json.loads(r["receipt_json"])
                envelope=json.loads(r["envelope_json"])
                profile=verify_policy(policy_row)
                if (not profile or digest(receipt)!=r["receipt_sha"] or
                    digest(envelope)!=r["envelope_sha"] or
                    envelope["job_id"]!=job_id or
                    envelope["layout_sha"]!=profile["layout_sha"] or
                    envelope["font_sha"]!=profile["bound_font_sha"] or
                    envelope["context_sha"]!=profile["bound_context_sha"] or
                    envelope["copy_sha"]!=job["copy_sha"] or
                    envelope["generation"]!=job["generation"] or
                    envelope["image_sha"]!=job["image_sha"] or
                    envelope["approval_sha"]!=job["approval_sha"] or
                    envelope["image_approval_sha"]!=job["image_approval_sha"] or
                    receipt["font_sha256"]!=profile["bound_font_sha"] or
                    job["state"]!="COMPLETED" or
                    job["final_sha"]!=r["final_sha"] or job["caption_sha"]!=r["caption_sha"] or
                    envelope["final_sha"]!=r["final_sha"] or
                    envelope["caption_sha"]!=r["caption_sha"]):
                    raise ValueError
            except (KeyError,ValueError,TypeError):
                raise LiveGateError("COMPOSITION_MANIFEST_INTEGRITY_FAILED") from None
            return {"receipt":receipt,"envelope":envelope,
                    "receipt_sha":r["receipt_sha"],"envelope_sha":r["envelope_sha"]}

    def composed(self,actor,job_id,output_sha,caption_sha):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_APPROVED":
                raise LiveGateError("FINAL_REQUIRES_IMAGE_APPROVAL")
            self._approved(job)
            policy=c.execute("SELECT profile_id FROM live_job_templates WHERE job_id=?",
                             (job_id,)).fetchone()
            if policy and policy["profile_id"]==A_ID:
                raise LiveGateError("A_TEMPLATE_REQUIRES_COMPOSITION_RECEIPT")
            expected=digest({"image_sha":job["image_sha"],
                "approval_sha":job["approval_sha"],"generation":job["generation"],
                       "evidence_acknowledged":bool(job["evidence_acknowledged"])})
            if expected!=job["image_approval_sha"]:
                raise LiveGateError("IMAGE_APPROVAL_STALE")
            c.execute("""UPDATE live_jobs SET state='COMPLETED',final_sha=?,caption_sha=?
                WHERE job_id=?""",(output_sha,caption_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"composed",updated["state"],output_sha)
            c.commit()
            return updated
