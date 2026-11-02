"""Single-writer durable Live state: owner artifacts and approvals never masquerade as Mock.

All mutation is transactional; image attempts and provider receipts reside in
the existing Owner image ledger / an independent aggregate attempt ledger.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import LiveGateError, digest, validate_input, strict_review, live_prompt, owner_text_snapshots


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

    def create(self,actor,job_id,input_body,assets):
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
            r=self._read(c,job_id,actor)
            self._event(c,r,"input_committed",r["state"],sha)
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

    def image_request(self,actor,job_id,images,references):
        from src.image_generation import BackendImageInput
        from src.image_generation.contracts import content_hash
        with self.db() as c:
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_REQUIRES_PROMPT")
            self._approved(job)
            owner=BackendImageInput.model_validate({
                "job_id":job_id,"copy_revision":job["generation"],
                "copy_hash":job["copy_sha"],
                "product_analysis":json.loads(job["analysis_json"]),
                "image_prompt":json.loads(job["prompt_json"]),
                "ad_copy":json.loads(job["copy_json"])["ad_copy"],
                "caption":json.loads(job["copy_json"])["caption"],
                "hashtags":json.loads(job["copy_json"])["hashtags"],
                "product_images":images,"reference_images":references,
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

    def composed(self,actor,job_id,output_sha,caption_sha):
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
            c.execute("""UPDATE live_jobs SET state='COMPLETED',final_sha=?,caption_sha=?
                WHERE job_id=?""",(output_sha,caption_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"composed",updated["state"],output_sha)
            c.commit()
            return updated
