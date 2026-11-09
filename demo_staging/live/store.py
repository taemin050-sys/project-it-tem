"""Single-writer durable Live state: owner artifacts and approvals never masquerade as Mock.

All mutation is transactional; image attempts and provider receipts reside in
the existing Owner image ledger / an independent aggregate attempt ledger.
"""
from __future__ import annotations

import json
import os
import hashlib
import sqlite3
from pathlib import Path
from uuid import uuid4

from .contracts import (LiveGateError,digest,validate_input,assert_single_image_scope,
                        strict_review,live_prompt,owner_text_snapshots)
from .template_contract import (A_ID,A_VERSION,LEGACY_ID,LEGACY_VERSION,SIZE_PREFIX,
    owner_a_policy,owner_size_policy,historical_a_v1_layout,normalize_layout,verify_policy,canonical)


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
            CREATE TABLE IF NOT EXISTS live_copy_previous (
                job_id TEXT PRIMARY KEY,
                copy_json TEXT NOT NULL, copy_sha TEXT NOT NULL,
                origin_generation INTEGER NOT NULL,
                reason_sha TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_copy_revision_feedback (
                job_id TEXT PRIMARY KEY,
                generation INTEGER NOT NULL,
                note TEXT, changed_fields_json TEXT NOT NULL,
                request_context_sha TEXT NOT NULL,
                source TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_image_attempts (
                job_id TEXT NOT NULL, attempt_version INTEGER NOT NULL,
                attempt_id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL,
                actor TEXT NOT NULL, approval_sha TEXT NOT NULL,
                prompt_sha TEXT NOT NULL, state TEXT NOT NULL,
                candidate_sha TEXT, provider_attempt_id TEXT,
                candidate_receipt_sha TEXT,
                created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(job_id,attempt_version), UNIQUE(job_id,request_key)
            );
            CREATE TABLE IF NOT EXISTS live_queue (
                job_id TEXT NOT NULL, stage TEXT NOT NULL,
                context_sha TEXT NOT NULL, state TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                UNIQUE(job_id,stage,context_sha)
            );
            -- Append-only CAS evidence, one row per immutable approved context.
            -- Never reuse a prior Prompt across approval/policy revisions.
            CREATE TABLE IF NOT EXISTS live_prompt_context_bindings (
                job_id TEXT NOT NULL, context_sha TEXT NOT NULL,
                actor TEXT NOT NULL, mode TEXT NOT NULL,
                prompt_sha TEXT NOT NULL, context_json TEXT NOT NULL,
                created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(job_id,context_sha)
            );
            CREATE TABLE IF NOT EXISTS live_copy_policy_bindings (
                job_id TEXT NOT NULL, approval_sha TEXT NOT NULL,
                policy_epoch TEXT NOT NULL,
                recorded_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(job_id,approval_sha)
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
        snapshot,sha=validate_input(input_body,assets)
        # No migration/overwrite of stored A v1 Jobs. Explicit new FE input
        # selects an Owner #23 size profile before the immutable Job is saved.
        new_size=snapshot.get("image_size")
        if template_profile=="LEGACY" and new_size is not None:
            raise LiveGateError("OWNER_SIZE_REQUIRES_VERSIONED_PROFILE")
        a_policy=(owner_size_policy(new_size) if new_size is not None
                  else owner_a_policy()) if template_profile=="A" else None
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
                    (job_id,a_policy["profile_id"],a_policy["profile_version"],
                     canonical(zone),digest(zone),canonical(layout),digest(layout)))
            r=self._read(c,job_id,actor)
            self._event(c,r,"input_committed",r["state"],sha)
            if template_profile=="A":
                # Owner Image size v2 and frozen A v1 use distinct immutable
                # marker events. Neither may be silently imported into the other.
                self._event(c,r,("template_owner_size_ingress_v2" if new_size
                    else "template_a_ingress_contract_v1"),r["state"],digest({
                    "profile_id":a_policy["profile_id"],
                    "profile_version":a_policy["profile_version"],
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
            # A legacy manual edit is a different edit path. Prevent a stale
            # QA previous-copy row from surviving an unrelated direct edit.
            c.execute("DELETE FROM live_copy_previous WHERE job_id=?",(job_id,))
            c.execute("DELETE FROM live_copy_revision_feedback WHERE job_id=?",(job_id,))
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

    def previous_copy_available(self,actor,job_id):
        with self.db() as c:
            self._read(c,job_id,actor)
            return c.execute("SELECT 1 FROM live_copy_previous WHERE job_id=?",
                (job_id,)).fetchone() is not None

    def revision_feedback(self,actor,job_id):
        with self.db() as c:
            job=self._read(c,job_id,actor)
            r=c.execute("""SELECT * FROM live_copy_revision_feedback
                WHERE job_id=? AND generation=?""",(job_id,job["generation"])).fetchone()
            if not r:return None
            return {"note":r["note"],"changed_fields":json.loads(r["changed_fields_json"]),
                    "source":r["source"]}

    def apply_copy_revision(self,actor,job_id,proposed_copy,instruction,
                            expected_generation,expected_review_sha,*,owner_feedback=None):
        """Atomic, approval-invalidating QA revision.

        Caller MUST independently authorize the provider/QA mode before this
        method; it is not a model invocation or a paid-provider substitute.
        """
        from src.serving.text_v08_mapper import verify_copy
        from src.text_generation.schemas import AdCopyOutput
        if type(expected_generation) is not int or not isinstance(expected_review_sha,str):
            raise LiveGateError("REVISION_TYPE_INVALID")
        if not isinstance(instruction,str) or not 1<=len(instruction.strip())<=500:
            raise LiveGateError("REVISION_INSTRUCTION_INVALID")
        parsed=verify_copy(proposed_copy,model=AdCopyOutput)
        if owner_feedback is not None:
            from src.text_generation.schemas import RevisableField
            from pydantic import TypeAdapter
            if (type(owner_feedback) is not dict or
                set(owner_feedback)!={"note","changed_fields","context_sha","source"} or
                owner_feedback["source"] not in ("OWNER_TEXT_V010_LIVE",
                                                 "OWNER_TEXT_V010_OFFLINE") or
                type(owner_feedback["context_sha"]) is not str or
                len(owner_feedback["context_sha"])!=64 or
                owner_feedback["note"] is not None and
                (type(owner_feedback["note"]) is not str or
                 len(owner_feedback["note"])>500)):
                raise LiveGateError("REVISION_FEEDBACK_INVALID")
            changed=TypeAdapter(list[RevisableField]).validate_python(
                owner_feedback["changed_fields"],strict=True)
            if len(changed)!=len(set(changed)):
                raise LiveGateError("REVISION_FEEDBACK_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_REVISION_STATE_CONFLICT")
            if job["generation"]!=expected_generation or job["review_sha"]!=expected_review_sha:
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            original=json.loads(job["copy_json"])
            context=json.loads(job["input_json"])
            analysis=json.loads(job["analysis_json"])
            report=strict_review(parsed.output,context["product"],analysis)
            previous_report=json.loads(job["compliance_json"])
            if (parsed.sha256==job["copy_sha"] and
                    digest(report)==digest(previous_report)):
                # Owner note does not create a new copy/review. Keep approval,
                # evidence acknowledgement and previous-copy pointer intact.
                # CAS, ownership and review-policy equivalence are checked
                # inside the *same* SQLite write transaction.
                if owner_feedback is not None:
                    note=owner_feedback["note"] or "수정된 항목이 없습니다. 기존 카피를 유지합니다."
                    c.execute("""INSERT INTO live_copy_revision_feedback
                        (job_id,generation,note,changed_fields_json,request_context_sha,source)
                        VALUES (?,?,?,?,?,?)
                        ON CONFLICT(job_id) DO UPDATE SET
                          generation=excluded.generation,note=excluded.note,
                          changed_fields_json=excluded.changed_fields_json,
                          request_context_sha=excluded.request_context_sha,
                          source=excluded.source""",
                        (job_id,job["generation"],note,"[]",
                         owner_feedback["context_sha"],owner_feedback["source"]))
                self._event(c,job,"copy_revision_no_change",job["state"],
                            digest({"request":instruction,"copy_sha":job["copy_sha"]}))
                c.commit()
                return self._read(c,job_id,actor)
            generation=job["generation"]+1
            report_sha=digest({"input_sha":job["input_sha"],"analysis":analysis,
                               "copy":parsed.output,"report":report,"generation":generation})
            # One-step undo: retain the exact last approved-for-review content;
            # restoring never recreates an approval or external provider receipt.
            if parsed.sha256!=job["copy_sha"]:
                # A no-change Owner refusal with a meaningful note advances
                # review generation but cannot fabricate a prior DIFFERENT copy.
                # Preserve any existing genuine earlier-version pointer.
                c.execute("""INSERT INTO live_copy_previous
                    (job_id,copy_json,copy_sha,origin_generation,reason_sha)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET
                      copy_json=excluded.copy_json,copy_sha=excluded.copy_sha,
                      origin_generation=excluded.origin_generation,
                      reason_sha=excluded.reason_sha""",
                    (job_id,json.dumps(original,ensure_ascii=False),job["copy_sha"],
                     job["generation"],digest({"instruction":instruction})))
            c.execute("""UPDATE live_jobs SET generation=?,state='COPY_REVIEW_REQUIRED',
                copy_json=?,copy_sha=?,compliance_json=?,review_sha=?,
                approval_sha=NULL,approved_generation=NULL,evidence_acknowledged=0,
                prompt_json=NULL,image_sha=NULL,image_approval_sha=NULL,
                final_sha=NULL,caption_sha=NULL WHERE job_id=?""",
                (generation,json.dumps(parsed.output,ensure_ascii=False),
                 parsed.sha256,json.dumps(report,ensure_ascii=False),report_sha,job_id))
            updated=self._read(c,job_id,actor)
            if owner_feedback is None:
                c.execute("DELETE FROM live_copy_revision_feedback WHERE job_id=?",(job_id,))
            else:
                c.execute("""INSERT INTO live_copy_revision_feedback
                    (job_id,generation,note,changed_fields_json,request_context_sha,source)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET
                      generation=excluded.generation,note=excluded.note,
                      changed_fields_json=excluded.changed_fields_json,
                      request_context_sha=excluded.request_context_sha,
                      source=excluded.source""",(
                        job_id,generation,owner_feedback["note"],
                        json.dumps(owner_feedback["changed_fields"],ensure_ascii=False),
                        owner_feedback["context_sha"],owner_feedback["source"]))
            self._event(c,updated,("copy_revision_owner_committed_v010"
                if owner_feedback is not None else "copy_revision_review_started"),
                updated["state"],digest({
                    "instruction_sha":digest(instruction),
                    "new_copy_sha":parsed.sha256,
                    "feedback_sha":digest(owner_feedback) if owner_feedback else None}))
            c.commit()
            return updated

    def restore_previous_copy(self,actor,job_id,expected_generation,expected_review_sha):
        """Toggle one previous copy inside a CAS transaction; never restore approval."""
        from src.serving.text_v08_mapper import verify_copy
        from src.text_generation.schemas import AdCopyOutput
        if type(expected_generation) is not int or not isinstance(expected_review_sha,str):
            raise LiveGateError("REVISION_TYPE_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_RESTORE_STATE_CONFLICT")
            if job["generation"]!=expected_generation or job["review_sha"]!=expected_review_sha:
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            old=c.execute("SELECT * FROM live_copy_previous WHERE job_id=?",
                         (job_id,)).fetchone()
            if old is None:raise LiveGateError("COPY_PREVIOUS_UNAVAILABLE")
            parsed=verify_copy(json.loads(old["copy_json"]),model=AdCopyOutput)
            if old["copy_sha"]!=parsed.sha256 or old["copy_sha"]==job["copy_sha"]:
                raise LiveGateError("COPY_PREVIOUS_SHA_INVALID")
            context=json.loads(job["input_json"])
            analysis=json.loads(job["analysis_json"])
            report=strict_review(parsed.output,context["product"],analysis)
            generation=job["generation"]+1
            report_sha=digest({"input_sha":job["input_sha"],"analysis":analysis,
                               "copy":parsed.output,"report":report,"generation":generation})
            c.execute("""UPDATE live_copy_previous SET copy_json=?,copy_sha=?,
                origin_generation=?,reason_sha=? WHERE job_id=?""",
                (job["copy_json"],job["copy_sha"],job["generation"],
                 digest({"previous_sha":old["copy_sha"],"return_sha":job["copy_sha"]}),job_id))
            c.execute("""UPDATE live_jobs SET generation=?,state='COPY_REVIEW_REQUIRED',
                copy_json=?,copy_sha=?,compliance_json=?,review_sha=?,
                approval_sha=NULL,approved_generation=NULL,evidence_acknowledged=0,
                prompt_json=NULL,image_sha=NULL,image_approval_sha=NULL,
                final_sha=NULL,caption_sha=NULL WHERE job_id=?""",
                (generation,json.dumps(parsed.output,ensure_ascii=False),parsed.sha256,
                 json.dumps(report,ensure_ascii=False),report_sha,job_id))
            c.execute("DELETE FROM live_copy_revision_feedback WHERE job_id=?",(job_id,))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"copy_previous_restored_review_started",
                        updated["state"],report_sha)
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
            # FE Owner #22 length policy is also an authoritative approval
            # boundary: a non-browser caller cannot bypass disabled FE controls.
            current=json.loads(job["copy_json"])["ad_copy"]
            if (len(current["headline"])>15 or
                len(current["subline"].replace("\n",""))>25 or
                len(current["cta"])>10):
                raise LiveGateError("COPY_LENGTH_LIMIT_EXCEEDED")
            if (any(x["risk_level"]=="근거 확인 필요" for x in review["issues"])
                    and acknowledge_evidence is not True):
                raise LiveGateError("EVIDENCE_ACKNOWLEDGEMENT_REQUIRED")
            # Persist the user declaration BEFORE binding an approval.
            c.execute("UPDATE live_jobs SET evidence_acknowledged=? WHERE job_id=?",
                      (int(acknowledge_evidence is True),job_id))
            bound=self._read(c,job_id,actor)
            binding=self.approval_binding(bound)
            policy_epoch=self._review_policy_epoch_in_tx(c,bound)
            c.execute("""INSERT OR IGNORE INTO live_copy_policy_bindings
                (job_id,approval_sha,policy_epoch) VALUES (?,?,?)""",
                (job_id,binding,policy_epoch))
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
        if not (job["state"] in {"COPY_APPROVED","PROMPT_READY","IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED","IMAGE_REJECTED"}
                and job["approval_sha"] and job["approved_generation"]==job["generation"]
                and job["approval_sha"]==self.approval_binding(job)
                and json.loads(job["compliance_json"])["passed"]):
            raise LiveGateError("APPROVAL_CONTEXT_NOT_CURRENT")

    def _review_policy_epoch_in_tx(self,c,job):
        """Pin the actual rule and checker bytes at human Copy approval."""
        from src.text_generation.compliance.rule_checker import RULES_PATH
        revision=os.environ.get("IT_TEM_REVIEW_POLICY_EPOCH","BP13_REVIEW_V1")
        if (not revision or len(revision)>128 or
                any(ord(ch)<33 or ord(ch)>126 for ch in revision)):
            raise LiveGateError("PROMPT_POLICY_EPOCH_INVALID")
        try:
            files=(RULES_PATH,RULES_PATH.with_name("rule_checker.py"),
                   RULES_PATH.with_name("report_builder.py"))
            source={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in files}
            template=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                               (job["job_id"],)).fetchone()
            return digest({
                "review_policy":revision,"rule_sources":source,
                "template":({field:template[field] for field in
                    ("profile_id","profile_version","safe_zone_sha","layout_sha",
                     "bound_font_sha","bound_context_sha")} if template else None),
            })
        except OSError:
            raise LiveGateError("PROMPT_POLICY_SOURCE_UNAVAILABLE") from None

    def _prompt_context_in_tx(self,c,job):
        """Canonical approval/version/provenance snapshot while DB lock held."""
        if job["state"] not in ("COPY_APPROVED","PROMPT_READY","IMAGE_REVIEW_REQUIRED",
                                "IMAGE_APPROVED","IMAGE_REJECTED"):
            raise LiveGateError("PROMPT_REQUIRES_COPY_APPROVAL")
        self._approved(job)
        if job["mode"] not in ("LIVE","OFFLINE_FIXTURE"):
            raise LiveGateError("PROMPT_PROVENANCE_INVALID")
        from src.image_generation.contracts import content_hash
        try:
            cp=json.loads(job["copy_json"])
            report=json.loads(job["compliance_json"])
            analysis=json.loads(job["analysis_json"])
            research=json.loads(job["research_json"])
            if (content_hash(cp)!=job["copy_sha"] or
                    digest({"input_sha":job["input_sha"],"analysis":analysis,
                            "copy":cp,"report":report,
                            "generation":job["generation"]})!=job["review_sha"]):
                raise LiveGateError("PROMPT_REVIEW_SNAPSHOT_CHANGED")
            policy_epoch=self._review_policy_epoch_in_tx(c,job)
            binding=c.execute("""SELECT policy_epoch FROM live_copy_policy_bindings
                WHERE job_id=? AND approval_sha=?""",
                (job["job_id"],job["approval_sha"])).fetchone()
            if binding is None and job["mode"]=="LIVE":
                raise LiveGateError("PROMPT_APPROVAL_POLICY_BINDING_MISSING")
            if binding is not None and binding["policy_epoch"]!=policy_epoch:
                raise LiveGateError("PROMPT_APPROVAL_POLICY_EPOCH_CHANGED")
            return {
                "job_id":job["job_id"],"mode":job["mode"],"input_sha":job["input_sha"],
                "generation":job["generation"],"copy_sha":job["copy_sha"],
                "review_sha":job["review_sha"],"approval_sha":job["approval_sha"],
                "policy_epoch":policy_epoch,"analysis_sha":digest(analysis),
                "research_sha":digest(research),"compliance_sha":digest(report),
                "plan_sha":digest(cp["plan"]),
                "approved_generation":job["approved_generation"],
            }
        except LiveGateError:
            raise
        except (TypeError,KeyError,ValueError):
            raise LiveGateError("PROMPT_CONTEXT_UNVERIFIABLE") from None

    def prompt_context(self,actor,job_id):
        with self.db() as c:
            job=self._read(c,job_id,actor)
            return self._prompt_context_in_tx(c,job)

    def _verify_prompt_binding_in_tx(self,c,job):
        """Fail closed on stale approval, changed policy or unknown LIVE Prompt."""
        if job["prompt_json"] is None:
            raise LiveGateError("PROMPT_BINDING_MISSING")
        current=self._prompt_context_in_tx(c,job)
        ctx_sha=digest(current)
        row=c.execute("""SELECT * FROM live_prompt_context_bindings
                         WHERE job_id=? AND context_sha=?""",
                      (job["job_id"],ctx_sha)).fetchone()
        if row is None:
            any_bound=c.execute("""SELECT 1 FROM live_prompt_context_bindings
                WHERE job_id=? LIMIT 1""",(job["job_id"],)).fetchone()
            if job["mode"]=="OFFLINE_FIXTURE" and any_bound is None:
                # Old isolated QA fixtures remain usable, never as LIVE.
                return
            raise LiveGateError("PROMPT_BINDING_NOT_FOUND_OR_POLICY_CHANGED")
        if (row["actor"]!=job["actor"] or row["mode"]!=job["mode"] or
                row["context_json"]!=json.dumps(current,sort_keys=True,
                    ensure_ascii=False,separators=(",",":")) or
                row["prompt_sha"]!=digest(json.loads(job["prompt_json"]))):
            raise LiveGateError("PROMPT_BINDING_INTEGRITY_FAILED")

    def store_prompt(self,actor,job_id,prompt,*,expected_context=None):
        """Commit exactly one prompt against original approval within SQLite CAS.

        All production pipeline calls MUST pass expected_context. Existing
        offline-only direct store fixtures may omit it, but LIVE never can.
        """
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_APPROVED":
                raise LiveGateError("PROMPT_REQUIRES_COPY_APPROVAL")
            current=self._prompt_context_in_tx(c,job)
            if expected_context is None:
                if job["mode"]!="OFFLINE_FIXTURE":
                    raise LiveGateError("PROMPT_EXPECTED_CONTEXT_REQUIRED")
            elif (type(expected_context) is not dict or expected_context!=current):
                raise LiveGateError("PROMPT_APPROVAL_CONTEXT_CAS_FAILED")
            cp=json.loads(job["copy_json"])
            parsed=live_prompt(prompt,cp)
            c.execute("UPDATE live_jobs SET state='PROMPT_READY',prompt_json=? WHERE job_id=?",
                     (json.dumps(parsed,ensure_ascii=False),job_id))
            canonical=json.dumps(current,sort_keys=True,ensure_ascii=False,
                                 separators=(",",":"))
            c.execute("""INSERT INTO live_prompt_context_bindings
                (job_id,context_sha,actor,mode,prompt_sha,context_json)
                VALUES (?,?,?,?,?,?)""",(job_id,digest(current),actor,
                    job["mode"],digest(parsed),canonical))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"image_prompt_committed",updated["state"],
                        digest({"prompt":parsed,"approval_context":current}))
            c.commit()
            return updated

    def template(self,actor,job_id):
        with self.db() as c:
            self._read(c,job_id,actor)
            row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",(job_id,)).fetchone()
            return verify_policy(row)

    def current_image_attempt(self,actor,job_id):
        """An additive per-Job attempt view; legacy jobs have no attempt row."""
        with self.db() as c:
            self._read(c,job_id,actor)
            row=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
                ORDER BY attempt_version DESC LIMIT 1""",(job_id,)).fetchone()
            return dict(row) if row is not None else None

    def begin_image_retry(self,actor,job_id,expected_sha,request_key):
        """User-driven CAS from rejected candidate to ONE new attempt.

        Preserve approved copy, analysis, research, and Image Prompt. The
        original image file must already be archived by the pipeline.
        """
        if (type(expected_sha) is not str or len(expected_sha)!=64 or
            type(request_key) is not str or len(request_key)!=32 or
            any(x not in "0123456789abcdef" for x in request_key)):
            raise LiveGateError("IMAGE_RETRY_INPUT_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            previous=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
                ORDER BY attempt_version DESC LIMIT 1""",(job_id,)).fetchone()
            if (job["state"]=="PROMPT_READY" and previous is not None
                    and previous["request_key"]==request_key
                    and previous["state"]=="REQUESTED"):
                return dict(previous)
            if job["state"]!="IMAGE_REJECTED" or job["image_sha"]!=expected_sha:
                raise LiveGateError("IMAGE_RETRY_STALE_REJECTION")
            self._approved(job)
            self._verify_prompt_binding_in_tx(c,job)
            if previous is None:
                # Old Jobs made before the new audit table are not rewritten.
                c.execute("""INSERT INTO live_image_attempts
                    (job_id,attempt_version,attempt_id,request_key,actor,
                    approval_sha,prompt_sha,state,candidate_sha)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (job_id,1,uuid4().hex,"historical-v1",actor,
                     job["approval_sha"],digest(json.loads(job["prompt_json"])),
                     "REJECTED",job["image_sha"]))
                next_version=2
            else:
                if previous["state"]!="REJECTED" or previous["candidate_sha"]!=expected_sha:
                    raise LiveGateError("IMAGE_RETRY_LEDGER_MISMATCH")
                next_version=previous["attempt_version"]+1
            attempt_id=uuid4().hex
            c.execute("""INSERT INTO live_image_attempts
                (job_id,attempt_version,attempt_id,request_key,actor,
                 approval_sha,prompt_sha,state)
                VALUES (?,?,?,?,?,?,?,?)""",
                (job_id,next_version,attempt_id,request_key,actor,
                 job["approval_sha"],digest(json.loads(job["prompt_json"])),"REQUESTED"))
            c.execute("""UPDATE live_jobs SET state='PROMPT_READY',image_sha=NULL,
                image_approval_sha=NULL WHERE job_id=?""",(job_id,))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"image_retry_explicit_requested",updated["state"],
                        digest({"attempt_id":attempt_id,"prior_sha":expected_sha}))
            c.commit()
            return dict(c.execute("SELECT * FROM live_image_attempts WHERE attempt_id=?",
                                  (attempt_id,)).fetchone())

    def image_request(self,actor,job_id,images,references):
        from src.image_generation import BackendImageInput
        from src.image_generation.contracts import content_hash
        with self.db() as c:
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_REQUIRES_PROMPT")
            self._approved(job)
            self._verify_prompt_binding_in_tx(c,job)
            profile_row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                                  (job_id,)).fetchone()
            policy=verify_policy(profile_row)
            metadata={}
            if policy is not None and policy["profile_id"].startswith(SIZE_PREFIX):
                from src.image_generation.size_selection import resolve_size_choice
                size=json.loads(job["input_json"]).get("image_size")
                if size!=policy["safe_zone"]["size"]:
                    raise LiveGateError("OWNER_IMAGE_SIZE_CONTEXT_CONFLICT")
                selection,_=resolve_size_choice(size)
                metadata["layout_selection"]=selection.model_dump(mode="json")
            elif policy is not None:
                metadata["safe_zone"]=policy["safe_zone"]
            saved=json.loads(job["input_json"])
            assert_single_image_scope(saved)
            selected_mode=saved.get("generation_mode","composed")
            if selected_mode=="freeform":
                metadata["generation_mode"]="freeform"
                metadata["copy_output"]=json.loads(job["copy_json"])
                # Neither a composed copy region nor automatic text overlay
                # may be attached to a freeform Owner request.
                metadata.pop("safe_zone",None)
            owner=BackendImageInput.model_validate({
                **metadata,
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

    def store_image_candidate(self,actor,job_id,sha,*,provider_attempt_id=None,
                              candidate_receipt_sha=None):
        if not isinstance(sha,str) or len(sha)!=64:
            raise LiveGateError("IMAGE_HASH_INVALID")
        if candidate_receipt_sha is not None and (
                type(candidate_receipt_sha) is not str or
                len(candidate_receipt_sha)!=64):
            raise LiveGateError("CANDIDATE_RECEIPT_SHA_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_STATE_CONFLICT")
            self._approved(job)
            self._verify_prompt_binding_in_tx(c,job)
            prior=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
                ORDER BY attempt_version DESC LIMIT 1""",(job_id,)).fetchone()
            if prior is None:
                c.execute("""INSERT INTO live_image_attempts
                    (job_id,attempt_version,attempt_id,request_key,actor,
                     approval_sha,prompt_sha,state,candidate_sha,provider_attempt_id,
                     candidate_receipt_sha)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id,1,uuid4().hex,"baseline",actor,job["approval_sha"],
                     digest(json.loads(job["prompt_json"])),"IMAGE_REVIEW_REQUIRED",
                     sha,provider_attempt_id,candidate_receipt_sha))
            elif (prior["state"]=="REQUESTED" and prior["approval_sha"]==job["approval_sha"]
                  and prior["prompt_sha"]==digest(json.loads(job["prompt_json"]))
                  and prior["actor"]==actor):
                c.execute("""UPDATE live_image_attempts SET state='IMAGE_REVIEW_REQUIRED',
                    candidate_sha=?,provider_attempt_id=?,candidate_receipt_sha=?
                    WHERE attempt_id=?""",
                    (sha,provider_attempt_id,candidate_receipt_sha,prior["attempt_id"]))
            else:
                raise LiveGateError("IMAGE_ATTEMPT_LEDGER_CONFLICT")
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
            c.execute("""UPDATE live_image_attempts SET state='APPROVED'
                WHERE job_id=? AND candidate_sha=? AND state='IMAGE_REVIEW_REQUIRED'""",
                (job_id,expected_sha))
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
            c.execute("""UPDATE live_image_attempts SET state='REJECTED'
                WHERE job_id=? AND candidate_sha=? AND state='IMAGE_REVIEW_REQUIRED'""",
                (job_id,expected_sha))
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
                if provided_layout is not None:
                    normalized=(historical_a_v1_layout(provided_layout)
                        if policy["profile_id"]==A_ID
                        else normalize_layout(provided_layout))
                    if digest(normalized)!=policy["layout_sha"]:
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
        connection.execute("""UPDATE live_image_attempts SET state='COMPLETED'
            WHERE job_id=? AND candidate_sha=? AND state='APPROVED'""",
            (job_id,job["image_sha"]))
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
                              'template_owner_size_ingress_v2',
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
                    (receipt.get("font_sha256")!=profile["bound_font_sha"]
                      if receipt.get("generation_mode")!="freeform" else
                      receipt.get("rendering")!="provider_drawn_text" or
                      receipt.get("font_sha256") is not None or
                      profile["bound_font_sha"]!=digest({
                          "generation_mode":"freeform","font":None,"version":1})) or
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
