"""Single-writer durable Live state: owner artifacts and approvals never masquerade as Mock.

All mutation is transactional; image attempts and provider receipts reside in
the existing Owner image ledger / an independent aggregate attempt ledger.
"""
from __future__ import annotations

import fcntl
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .contracts import LiveGateError, digest, validate_input, strict_review, live_prompt, owner_text_snapshots
from .review_policy import (enabled as policy_enabled, current as current_policy,
    review_digest, sources_fingerprint, llm_required)
from .template_contract import (A_ID,A_VERSION,LEGACY_ID,LEGACY_VERSION,SIZE_PREFIX,BP18_PREFIX,
    owner_a_policy,owner_size_policy,bp18_provisional_4x5_policy,historical_a_v1_layout,
    normalize_layout,verify_policy,canonical,DUAL_CTA_PREFIX,dual_image_cta_policy)


class LiveStore:
    @classmethod
    def open_existing(cls, filename: Path):
        """Open an explicitly migrated runtime without startup DDL or activation.

        Local derived workers share approval transactions with this store. They
        must never create a missing database or silently activate a new policy.
        """
        filename=Path(filename).absolute()
        if filename.is_symlink() or not filename.is_file():
            raise LiveGateError("LIVE_EXISTING_DATABASE_REQUIRED")
        instance=cls.__new__(cls)
        instance.filename=filename
        instance._open_existing_only=True
        required={
            "live_jobs":{"job_id","actor","state","mode","generation","input_json","input_sha",
                         "copy_json","copy_sha","compliance_json","review_sha","approval_sha",
                         "approved_generation","prompt_json","image_sha","image_approval_sha"},
            "live_events":{"id","job_id","generation","event","status","payload_sha"},
            "live_job_templates":{"job_id","profile_id","profile_version","safe_zone_json",
                                  "safe_zone_sha","layout_json","layout_sha","bound_font_sha","bound_context_sha"},
            "live_compose_manifests":{"job_id","receipt_json","envelope_json","receipt_sha","final_sha"},
            "live_copy_previous":{"job_id","copy_json","copy_sha","origin_generation","reason_sha"},
            "live_copy_revision_feedback":{"job_id","generation","request_context_sha","source"},
            "live_image_attempts":{"job_id","attempt_version","attempt_id","request_key","state"},
            "live_review_policy":{"job_id","generation","policy_sha","review_sha","activation_epoch"},
            "live_policy_activation":{"singleton","epoch","policy_version","policy_sha"},
            "live_queue":{"job_id","stage","context_sha","state","attempt_id"},
            "live_dual_groups":{"parent_job_id","actor","child_job_id","approval_sha"},
            "live_paid_dual_groups":{"parent_job_id","actor","child_job_id","authority_json","authority_sha"},
            "live_paid_dual_intents":{"parent_job_id","actor","job_id","stage","context_sha","state"},
            "live_paid_dual_visual_reviews":{"job_id","record_json","record_sha"},
            "live_dual_variants":{"job_id","parent_job_id","dispatch_state","visual_review_sha"},
        }
        try:
            with instance.db() as c:
                for table,columns in required.items():
                    kind=c.execute("SELECT type FROM sqlite_master WHERE name=?",(table,)).fetchone()
                    actual={row["name"] for row in c.execute(f"PRAGMA table_info({table})")}
                    if kind is None or kind["type"]!="table" or not columns <= actual:
                        raise LiveGateError("LIVE_EXISTING_SCHEMA_REQUIRED")
        except sqlite3.Error:
            raise LiveGateError("LIVE_EXISTING_SCHEMA_REQUIRED") from None
        instance._source_at_init=sources_fingerprint() if policy_enabled() else None
        instance._policy_at_init=current_policy() if policy_enabled() else None
        return instance

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
            CREATE TABLE IF NOT EXISTS live_review_policy (
                job_id TEXT NOT NULL, generation INTEGER NOT NULL,
                policy_version TEXT NOT NULL, policy_sha TEXT NOT NULL,
                review_sha TEXT NOT NULL,
                PRIMARY KEY(job_id,generation)
            );
            CREATE TABLE IF NOT EXISTS live_policy_activation (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                epoch INTEGER NOT NULL,
                policy_version TEXT NOT NULL, policy_sha TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_queue (
                job_id TEXT NOT NULL, stage TEXT NOT NULL,
                context_sha TEXT NOT NULL, state TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                UNIQUE(job_id,stage,context_sha)
            );
            CREATE TABLE IF NOT EXISTS live_dual_groups (
                parent_job_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                child_job_id TEXT UNIQUE, generation INTEGER, input_sha TEXT,
                copy_sha TEXT, review_sha TEXT, approval_sha TEXT,
                preferred_mode TEXT, preferred_final_sha TEXT
            );
            CREATE TABLE IF NOT EXISTS live_paid_dual_groups (
                parent_job_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                child_job_id TEXT UNIQUE, approval_sha TEXT, copy_sha TEXT,
                authority_json TEXT, authority_sha TEXT, prompt_sha TEXT, hold_code TEXT,
                preferred_mode TEXT, preferred_final_sha TEXT
            );
            CREATE TABLE IF NOT EXISTS live_paid_dual_intents (
                parent_job_id TEXT NOT NULL, actor TEXT NOT NULL, job_id TEXT NOT NULL,
                stage TEXT NOT NULL, context_sha TEXT NOT NULL, state TEXT NOT NULL,
                queue_task_id TEXT UNIQUE, result_sha TEXT, error_code TEXT,
                PRIMARY KEY (job_id,stage)
            );
            CREATE TABLE IF NOT EXISTS live_paid_dual_visual_reviews (
                job_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, record_sha TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_dual_variants (
                job_id TEXT PRIMARY KEY, parent_job_id TEXT NOT NULL,
                dispatch_state TEXT NOT NULL, dispatch_error TEXT,
                visual_review_json TEXT, visual_review_sha TEXT
            );
            """)
            if "activation_epoch" not in {
                    row["name"] for row in cx.execute(
                        "PRAGMA table_info(live_review_policy)").fetchall()}:
                cx.execute("ALTER TABLE live_review_policy ADD COLUMN activation_epoch INTEGER")
        self._source_at_init=sources_fingerprint() if policy_enabled() else None
        self._policy_at_init=current_policy() if policy_enabled() else None
        if policy_enabled():
            with self.db() as c:
                c.execute("BEGIN IMMEDIATE")
                # Deployment startup is the only legal policy activation
                # event. Old workers can never reactivate an earlier epoch
                # simply by inspecting or approving an old Job.
                self._active_policy(c,activate=True)
                c.commit()

    def db(self):
        target=(self.filename.as_uri()+"?mode=rw" if getattr(self,"_open_existing_only",False)
                else str(self.filename))
        c=sqlite3.connect(target,timeout=15,uri=getattr(self,"_open_existing_only",False))
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

    def create(self,actor,job_id,input_body,assets,*,template_profile="LEGACY",dual=False,live_dual=False):
        if template_profile not in ("LEGACY","A"):
            raise LiveGateError("TEMPLATE_PROFILE_INVALID")
        # Validate the complete Owner policy before opening the DB transaction.
        snapshot,sha=validate_input(input_body,assets)
        # No migration/overwrite of stored A v1 Jobs. Explicit new FE input
        # selects an Owner #23 size profile before the immutable Job is saved.
        new_size=snapshot.get("image_size")
        if live_dual:
            from .dual_ratio_policy import ratio_admission
            cta_sha=ratio_admission(new_size)
            if dual or template_profile!="A" or snapshot.get("generation_mode")!="composed":
                raise LiveGateError("LIVE_DUAL_REQUIRES_COMPOSED_4X5")
        if dual and (template_profile!="A" or new_size is None or
                     snapshot.get("generation_mode")!="composed"):
            raise LiveGateError("DUAL_REQUIRES_COMPOSED_SIZE")
        if template_profile=="LEGACY" and new_size is not None:
            raise LiveGateError("OWNER_SIZE_REQUIRES_VERSIONED_PROFILE")
        a_policy=(owner_size_policy(new_size) if new_size is not None
                  else owner_a_policy()) if template_profile=="A" else None
        if (dual or live_dual) and new_size=="4:5":
            a_policy=bp18_provisional_4x5_policy()
        if live_dual and new_size=="9:16":
            a_policy=dual_image_cta_policy(cta_sha)
        if live_dual:
            import os
            if os.environ.get("IT_TEM_BP18_BETA_TYPOGRAPHY_ENABLED")=="YES":
                from .beta_typography import build_policy
                a_policy=build_policy(new_size,cta_policy_sha=cta_sha)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            existing=c.execute("SELECT * FROM live_jobs WHERE job_id=?",(job_id,)).fetchone()
            if existing:
                if existing["actor"]!=actor:
                    raise LiveGateError("LIVE_JOB_NOT_FOUND")
                if existing["input_sha"]!=sha:
                    raise LiveGateError("LIVE_INPUT_CONFLICT")
                if (dual!=bool(self._dual_row(c,actor,job_id)) or
                    live_dual!=bool(self._live_dual_row(c,actor,job_id))):
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
            if dual:
                c.execute("INSERT INTO live_dual_groups(parent_job_id,actor) VALUES (?,?)",
                          (job_id,actor))
                self._event(c,r,"dual_input_committed",r["state"],sha)
            if live_dual:
                c.execute("INSERT INTO live_paid_dual_groups(parent_job_id,actor) VALUES (?,?)",
                          (job_id,actor))
                self._event(c,r,"live_dual_input_committed",r["state"],sha)
            if template_profile=="A":
                # Owner Image size v2 and frozen A v1 use distinct immutable
                # marker events. Neither may be silently imported into the other.
                self._event(c,r,("template_bp18_beta_editorial_ingress_v1"
                    if a_policy["profile_id"].startswith("BP18_BETA_EDITORIAL_")
                    else "template_bp18_image_cta_ingress_v1"
                    if a_policy["profile_id"].startswith(DUAL_CTA_PREFIX)
                    else "template_bp18_provisional_v3_ingress"
                    if a_policy["profile_id"].startswith(BP18_PREFIX)
                    else "template_owner_size_ingress_v2" if new_size
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

    @staticmethod
    def _live_dual_row(c,actor,job_id):
        return c.execute("""SELECT * FROM live_paid_dual_groups WHERE actor=?
            AND (parent_job_id=? OR child_job_id=?)""",(actor,job_id,job_id)).fetchone()

    def live_dual_membership(self,actor,job_id):
        with self.db() as c:
            row=self._live_dual_row(c,actor,job_id)
            return row["parent_job_id"] if row else None

    def _live_dual_group(self,c,actor,parent_id):
        self._read(c,parent_id,actor)
        group=self._live_dual_row(c,actor,parent_id)
        if group is None or group["parent_job_id"]!=parent_id:
            return None
        intents=[dict(row) for row in c.execute("""SELECT * FROM live_paid_dual_intents
            WHERE parent_job_id=? ORDER BY stage,job_id""",(parent_id,))]
        reviews={row["job_id"]:row["record_sha"] for row in c.execute("""
            SELECT job_id,record_sha FROM live_paid_dual_visual_reviews
            WHERE job_id IN (?,?)""",(parent_id,group["child_job_id"]))}
        dispatch={row["job_id"]:{"state":row["state"],"error_code":row["error_code"],
            "visual_review_sha":reviews.get(row["job_id"])}
            for row in intents if row["stage"]=="image"}
        return {**dict(group),"intents":intents,"dispatch":dispatch,
                "execution_profile":json.loads(group["authority_json"])["execution_profile"]
                    if group["authority_json"] else None}

    def live_dual_group(self,actor,parent_id):
        with self.db() as c:
            return self._live_dual_group(c,actor,parent_id)

    def _live_dual_f09_proof(self,parent):
        """Cross-check actual F09 evidence without opening an attempt for dispatch."""
        proof=json.loads(parent["compliance_json"]).get("llm_review")
        try:
            with sqlite3.connect((self.filename.parent/"cost.sqlite").resolve().as_uri()
                                 +"?mode=ro",uri=True) as c:
                c.row_factory=sqlite3.Row
                attempt=c.execute("""SELECT actor,job_id,stage,status,receipt,payload_hash
                    FROM attempts WHERE id=?""",(proof["attempt_id"],)).fetchone()
            if (attempt is None or attempt["actor"]!=parent["actor"] or
                attempt["job_id"]!=parent["job_id"] or attempt["stage"]!="copy_review" or
                attempt["status"] not in ("SUCCEEDED_USAGE_UNPRICED","SUCCEEDED")):
                raise ValueError
            context={key:proof[key] for key in ("job_id","input_sha","copy_sha","generation",
                "source_review_sha","model","policy_version","policy_sha","policy_epoch")}
            if attempt["payload_hash"]!=digest(context):
                raise ValueError
            receipt=json.loads(attempt["receipt"])
            if digest(receipt)!=proof["receipt_sha"] or receipt["model"]!=proof["response_model"]:
                raise ValueError
        except (KeyError,ValueError,TypeError,sqlite3.Error):
            raise LiveGateError("LIVE_DUAL_F09_RECEIPT_UNVERIFIED") from None
        return {"job_id":parent["job_id"],"review_sha":parent["review_sha"],
                "attempt_id":proof["attempt_id"],"receipt_sha":proof["receipt_sha"]}

    @staticmethod
    def _live_dual_child_report(parent,proof):
        report=json.loads(parent["compliance_json"])
        del report["llm_review"]
        report["live_dual_f09_parent"]=proof
        return report

    def _live_dual_authority(self,c,parent,child,execution_profile):
        self._validate_live_dual_profile(execution_profile)
        ratio=json.loads(parent["input_json"]).get("image_size")
        if execution_profile["image_size"]!=ratio:
            raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_CHANGED")
        expected_profile={"4:5":BP18_PREFIX+"4_5","3:4":SIZE_PREFIX+"3_4",
                          "9:16":DUAL_CTA_PREFIX+"9_16"}.get(ratio)
        profiles=[]
        for job in (parent,child):
            template=verify_policy(c.execute("""SELECT * FROM live_job_templates WHERE job_id=?""",
                                             (job["job_id"],)).fetchone())
            beta=(template is not None and template["profile_id"].startswith("BP18_BETA_EDITORIAL_")
                  and template["safe_zone"].get("size")==ratio)
            if template is None or (template["profile_id"]!=expected_profile and not beta):
                raise LiveGateError("LIVE_DUAL_TEMPLATE_REQUIRED")
            if ratio=="9:16" and template["safe_zone"]["cta_policy_sha"]!=execution_profile["cta_policy_sha"]:
                raise LiveGateError("LIVE_DUAL_CTA_POLICY_CHANGED")
            profiles.append({"layout_sha":template["layout_sha"],
                             "safe_zone_sha":template["safe_zone_sha"]})
        if profiles[0]!=profiles[1]:
            raise LiveGateError("LIVE_DUAL_TEMPLATE_CHANGED")
        return {"protocol":execution_profile["protocol"],"actor":parent["actor"],
                "acknowledge_two_images":True,"planned_image_attempts":2,
                "parent_job_id":parent["job_id"],"child_job_id":child["job_id"],
                "generation":parent["generation"],"copy_sha":parent["copy_sha"],
                "parent_input_sha":parent["input_sha"],"child_input_sha":child["input_sha"],
                "parent_approval_sha":parent["approval_sha"],"child_approval_sha":child["approval_sha"],
                "child_review_sha":child["review_sha"],"f09":self._live_dual_f09_proof(parent),
                "template":profiles[0],"execution_profile":execution_profile}

    @staticmethod
    def _validate_live_dual_profile(profile):
        base={"protocol","release_sha","policy_sha","text_model","image_profile","image_size"}
        if not isinstance(profile,dict):
            raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_REQUIRED")
        ratio=profile.get("image_size")
        expected_keys=base if ratio=="4:5" else base|{"cta_policy_sha"}
        protocol="LIVE_DUAL_V1" if ratio=="4:5" else "LIVE_DUAL_V2"
        cta=profile.get("cta_policy_sha")
        if (ratio not in {"3:4","4:5","9:16"} or set(profile)!=expected_keys or
            profile.get("protocol")!=protocol or
            not isinstance(profile.get("release_sha"),str) or
            re.fullmatch(r"[0-9a-f]{40}",profile["release_sha"]) is None or
            not isinstance(profile.get("policy_sha"),str) or
            re.fullmatch(r"[0-9a-f]{64}",profile["policy_sha"]) is None or
            not isinstance(profile.get("text_model"),str) or
            not isinstance(profile.get("image_profile"),dict) or
            (ratio=="3:4" and cta is not None) or
            (ratio=="9:16" and (not isinstance(cta,str) or re.fullmatch(r"[0-9a-f]{64}",cta) is None))):
            raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_REQUIRED")

    def start_live_dual(self,actor,parent_id,*,expected_generation,expected_review_sha,
                        acknowledge_evidence=False,acknowledge_two_images=False,execution_profile):
        """Commit canonical approval, derived authority, and the first queue intent together."""
        if type(expected_generation) is not int:
            raise LiveGateError("REVISION_TYPE_INVALID")
        if acknowledge_two_images is not True:
            raise LiveGateError("LIVE_DUAL_TWO_IMAGES_ACKNOWLEDGEMENT_REQUIRED")
        self._validate_live_dual_profile(execution_profile)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            parent=self._read(c,parent_id,actor)
            group=self._live_dual_row(c,actor,parent_id)
            if not group or group["parent_job_id"]!=parent_id:
                raise LiveGateError("LIVE_DUAL_GROUP_NOT_FOUND")
            if parent["mode"]!="LIVE" or not llm_required("LIVE") or not policy_enabled():
                raise LiveGateError("LIVE_DUAL_F09_POLICY_REQUIRED")
            if parent["generation"]!=expected_generation or parent["review_sha"]!=expected_review_sha:
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            if group["child_job_id"]:
                self._approved(parent,c,allow_completed=True)
                result=self._live_dual_group(c,actor,parent_id)
                if result["execution_profile"]!=execution_profile:
                    raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_CHANGED")
                return result
            if group["hold_code"]:
                raise LiveGateError("LIVE_DUAL_GROUP_HELD")
            source=json.loads(parent["input_json"])
            if (source.get("generation_mode")!="composed" or source.get("image_size")!=execution_profile["image_size"]
                    or digest(source)!=parent["input_sha"]
                    or digest(json.loads(parent["copy_json"]))!=parent["copy_sha"]):
                raise LiveGateError("LIVE_DUAL_SOURCE_INPUT_CHANGED")
            parent=self._approve_copy_locked(c,parent,expected_generation,expected_review_sha,
                                            acknowledge_evidence=acknowledge_evidence)
            policy=self._ensure_current_review_policy(c,parent)
            report=self._live_dual_child_report(parent,self._live_dual_f09_proof(parent))
            snapshot={**source,"generation_mode":"freeform"}
            input_sha=digest(snapshot)
            review_sha=review_digest(input_sha,json.loads(parent["analysis_json"]),
                json.loads(parent["copy_json"]),report,expected_generation,policy)
            child_id=uuid4().hex
            child={**parent,"job_id":child_id,"input_sha":input_sha,"review_sha":review_sha}
            approval_sha=self.approval_binding(child,c)
            c.execute("""INSERT INTO live_jobs (job_id,actor,state,mode,generation,input_json,
                input_sha,analysis_json,research_json,research_display_json,copy_json,copy_sha,
                compliance_json,review_sha,approval_sha,approved_generation,evidence_acknowledged)
                VALUES (?,?,'COPY_APPROVED','LIVE',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (child_id,actor,expected_generation,canonical(snapshot),input_sha,
                 parent["analysis_json"],parent["research_json"],parent["research_display_json"],
                 parent["copy_json"],parent["copy_sha"],canonical(report),review_sha,
                 approval_sha,expected_generation,parent["evidence_acknowledged"]))
            self._bind_review_policy(c,child_id,expected_generation,review_sha,policy)
            c.execute("""INSERT INTO live_job_templates (job_id,profile_id,profile_version,
                safe_zone_json,safe_zone_sha,layout_json,layout_sha)
                SELECT ?,profile_id,profile_version,safe_zone_json,safe_zone_sha,layout_json,layout_sha
                FROM live_job_templates WHERE job_id=?""",(child_id,parent_id))
            child=self._read(c,child_id,actor)
            authority=self._live_dual_authority(c,parent,child,execution_profile)
            authority_sha=digest(authority)
            c.execute("""UPDATE live_paid_dual_groups SET child_job_id=?,approval_sha=?,
                copy_sha=?,authority_json=?,authority_sha=? WHERE parent_job_id=?""",
                (child_id,parent["approval_sha"],parent["copy_sha"],canonical(authority),
                 authority_sha,parent_id))
            self._event(c,parent,"live_dual_authority_committed",parent["state"],authority_sha)
            self._event(c,child,"live_dual_copy_derived",child["state"],authority_sha)
            self._insert_live_dual_intent(c,parent_id,parent,"image_prompt",authority_sha)
            result=self._live_dual_group(c,actor,parent_id)
            c.commit()
            return result

    @staticmethod
    def _insert_live_dual_intent(c,parent_id,job,stage,authority_sha,prompt_sha=None):
        context_sha=digest({"authority_sha":authority_sha,"prompt_sha":prompt_sha,
                            "job_id":job["job_id"],"stage":stage,"approval_sha":job["approval_sha"]})
        c.execute("""INSERT INTO live_paid_dual_intents
            (parent_job_id,actor,job_id,stage,context_sha,state) VALUES (?,?,?,?,?,'PENDING')""",
            (parent_id,job["actor"],job["job_id"],stage,context_sha))

    def share_live_dual_prompt(self,actor,parent_id):
        """Bind one committed Text Owner prompt to both independently authorized inputs."""
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            parent=self._read(c,parent_id,actor)
            group=self._live_dual_row(c,actor,parent_id)
            if not group or group["parent_job_id"]!=parent_id or not group["child_job_id"]:
                raise LiveGateError("LIVE_DUAL_GROUP_NOT_FOUND")
            if group["hold_code"]:
                raise LiveGateError("LIVE_DUAL_GROUP_HELD")
            self._approved(parent,c,allow_completed=True)
            if not parent["prompt_json"]:
                raise LiveGateError("LIVE_DUAL_PROMPT_NOT_COMMITTED")
            child=self._read(c,group["child_job_id"],actor)
            self._approved(child,c,allow_completed=True)
            prompt_sha=digest(json.loads(parent["prompt_json"]))
            if group["prompt_sha"]:
                if (group["prompt_sha"]!=prompt_sha or
                    digest(json.loads(child["prompt_json"]))!=prompt_sha):
                    raise LiveGateError("LIVE_DUAL_PROMPT_CHANGED")
                return prompt_sha
            if child["state"]!="COPY_APPROVED":
                raise LiveGateError("LIVE_DUAL_PROMPT_STATE_CONFLICT")
            c.execute("UPDATE live_jobs SET state='PROMPT_READY',prompt_json=? WHERE job_id=?",
                      (parent["prompt_json"],child["job_id"]))
            c.execute("UPDATE live_paid_dual_groups SET prompt_sha=? WHERE parent_job_id=?",
                      (prompt_sha,parent_id))
            for job in (parent,child):
                self._insert_live_dual_intent(c,parent_id,job,"image",group["authority_sha"],prompt_sha)
            self._event(c,child,"live_dual_prompt_derived","PROMPT_READY",prompt_sha)
            c.commit()
            return prompt_sha

    def live_dual_intents(self):
        with self.db() as c:
            return [dict(row) for row in c.execute("""SELECT i.* FROM live_paid_dual_intents i
                JOIN live_paid_dual_groups g ON g.parent_job_id=i.parent_job_id AND g.actor=i.actor
                WHERE i.state='PENDING' AND g.hold_code IS NULL ORDER BY i.rowid""")]

    def attach_live_dual_task(self,intent,task_id):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            changed=c.execute("""UPDATE live_paid_dual_intents SET queue_task_id=?,state='QUEUED'
                WHERE job_id=? AND actor=? AND stage=? AND context_sha=? AND parent_job_id=?
                AND ((state='PENDING' AND queue_task_id IS NULL) OR
                     (state='QUEUED' AND queue_task_id=?))""",
                (task_id,intent["job_id"],intent["actor"],intent["stage"],intent["context_sha"],
                 intent["parent_job_id"],task_id)).rowcount
            if changed!=1:
                raise LiveGateError("LIVE_DUAL_QUEUE_IDENTITY_CONFLICT")
            c.commit()

    def _live_dual_task_row(self,c,item):
        row=c.execute("""SELECT * FROM live_paid_dual_intents WHERE queue_task_id=?
            AND actor=? AND job_id=? AND stage=? AND context_sha=?""",
            (item["id"],item["actor"],item["job_id"],item["stage"],item["context_sha"])).fetchone()
        if row is None:
            raise LiveGateError("LIVE_DUAL_QUEUE_IDENTITY_CONFLICT")
        return row

    def live_dual_intent_by_task(self,item):
        with self.db() as c:
            return dict(self._live_dual_task_row(c,item))

    def live_dual_task(self,item,execution_profile):
        with self.db() as c:
            row=self._live_dual_task_row(c,item)
            job=self._read(c,item["job_id"],item["actor"])
            group=self._live_dual_group(c,item["actor"],row["parent_job_id"])
            if not group or group["hold_code"] or row["state"]!="QUEUED":
                raise LiveGateError("LIVE_DUAL_GROUP_HELD")
            if group["execution_profile"]!=execution_profile:
                raise LiveGateError("LIVE_DUAL_EXECUTION_PROFILE_CHANGED")
            self._approved(job,c,allow_completed=True)
            prompt_sha=group["prompt_sha"] if item["stage"]=="image" else None
            context=digest({"authority_sha":group["authority_sha"],"prompt_sha":prompt_sha,
                            "job_id":job["job_id"],"stage":item["stage"],"approval_sha":job["approval_sha"]})
            if row["context_sha"]!=context:
                raise LiveGateError("LIVE_DUAL_QUEUE_CONTEXT_CHANGED")
            return group

    def hold_live_dual(self,parent_job_id,code):
        with self.db() as c:
            c.execute("""UPDATE live_paid_dual_groups SET hold_code=COALESCE(hold_code,?)
                         WHERE parent_job_id=?""",(code,parent_job_id))

    def finish_live_dual_intent(self,item,state,result_sha=None,error_code=None):
        if state not in ("SUCCEEDED","FAILED","BILLING_UNKNOWN"):
            raise LiveGateError("LIVE_DUAL_INTENT_STATE_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=self._live_dual_task_row(c,item)
            if row["state"]!="QUEUED":
                if (row["state"],row["result_sha"],row["error_code"])==(state,result_sha,error_code):
                    return
                raise LiveGateError("LIVE_DUAL_INTENT_STATE_CONFLICT")
            if state=="SUCCEEDED":
                job=self._read(c,item["job_id"],item["actor"])
                field="prompt_json" if row["stage"]=="image_prompt" else "image_sha"
                actual=digest(json.loads(job[field])) if field=="prompt_json" else job[field]
                if not actual or actual!=result_sha:
                    raise LiveGateError("LIVE_DUAL_INTENT_RESULT_CHANGED")
            c.execute("""UPDATE live_paid_dual_intents SET state=?,result_sha=?,error_code=?
                         WHERE queue_task_id=?""",(state,result_sha,error_code,row["queue_task_id"]))
            if state=="BILLING_UNKNOWN":
                c.execute("""UPDATE live_paid_dual_groups SET hold_code=COALESCE(hold_code,?)
                             WHERE parent_job_id=?""",(error_code or state,row["parent_job_id"]))
            c.commit()

    @staticmethod
    def _dual_row(c,actor,job_id):
        return c.execute("""SELECT * FROM live_dual_groups WHERE actor=?
            AND (parent_job_id=? OR child_job_id=?)""",(actor,job_id,job_id)).fetchone()

    def dual_membership(self,actor,job_id):
        with self.db() as c:
            row=self._dual_row(c,actor,job_id)
            return row["parent_job_id"] if row else None

    def _dual_group(self,c,actor,parent_id):
        self._read(c,parent_id,actor)
        group=self._dual_row(c,actor,parent_id)
        if group is None or group["parent_job_id"]!=parent_id:
            return None
        rows=c.execute("""SELECT job_id,dispatch_state,dispatch_error,visual_review_sha
            FROM live_dual_variants WHERE parent_job_id=?""",(parent_id,))
        return {**dict(group),"dispatch":{row["job_id"]:{
            "state":row["dispatch_state"],"error_code":row["dispatch_error"],
            "visual_review_sha":row["visual_review_sha"]} for row in rows}}

    def dual_group(self,actor,parent_id):
        with self.db() as c:
            return self._dual_group(c,actor,parent_id)

    def start_dual(self,actor,parent_id,*,expected_generation,expected_review_sha,
                   acknowledge_evidence=False):
        """Approve the source Copy once and derive an isolated fixture sibling."""
        if type(expected_generation) is not int:
            raise LiveGateError("REVISION_TYPE_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            parent=self._read(c,parent_id,actor)
            group=self._dual_row(c,actor,parent_id)
            if group is None or group["parent_job_id"]!=parent_id:
                raise LiveGateError("DUAL_GROUP_NOT_FOUND")
            if parent["mode"]!="OFFLINE_FIXTURE":
                raise LiveGateError("DUAL_REQUIRES_OFFLINE_FIXTURE")
            if parent["generation"]!=expected_generation or parent["review_sha"]!=expected_review_sha:
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            if group["child_job_id"]:
                self._approved(parent,c,allow_completed=True)
                return self._dual_group(c,actor,parent_id)
            if parent["state"]!="COPY_REVIEW_REQUIRED":
                raise LiveGateError("COPY_APPROVAL_STATE_CONFLICT")

            source=json.loads(parent["input_json"])
            if source.get("generation_mode")!="composed" or digest(source)!=parent["input_sha"]:
                raise LiveGateError("DUAL_SOURCE_INPUT_CHANGED")
            snapshot={**source,"generation_mode":"freeform"}
            input_sha=digest(snapshot)
            child_id=uuid4().hex
            policy=self._ensure_current_review_policy(c,parent)
            copy=json.loads(parent["copy_json"])
            analysis=json.loads(parent["analysis_json"])
            report=json.loads(parent["compliance_json"])
            if (digest(copy)!=parent["copy_sha"] or
                review_digest(parent["input_sha"],analysis,copy,report,
                              expected_generation,policy)!=expected_review_sha):
                raise LiveGateError("DUAL_SOURCE_REVIEW_CHANGED")
            review_sha=review_digest(input_sha,analysis,copy,report,expected_generation,policy)
            parent=self._approve_copy_locked(c,parent,expected_generation,expected_review_sha,
                                              acknowledge_evidence=acknowledge_evidence)
            child={**parent,"job_id":child_id,"input_sha":input_sha,"review_sha":review_sha}
            approval_sha=self.approval_binding(child,c)
            c.execute("""INSERT INTO live_jobs (job_id,actor,state,mode,generation,input_json,
                input_sha,analysis_json,research_json,research_display_json,copy_json,copy_sha,
                compliance_json,review_sha,approval_sha,approved_generation,evidence_acknowledged)
                VALUES (?,?,'COPY_APPROVED','OFFLINE_FIXTURE',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (child_id,actor,expected_generation,canonical(snapshot),input_sha,
                 parent["analysis_json"],parent["research_json"],parent["research_display_json"],
                 parent["copy_json"],parent["copy_sha"],parent["compliance_json"],review_sha,
                 approval_sha,expected_generation,parent["evidence_acknowledged"]))
            self._bind_review_policy(c,child_id,expected_generation,review_sha,policy)
            template=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",(parent_id,)).fetchone()
            if verify_policy(template) is None:
                raise LiveGateError("DUAL_SOURCE_TEMPLATE_REQUIRED")
            c.execute("""INSERT INTO live_job_templates (job_id,profile_id,profile_version,
                safe_zone_json,safe_zone_sha,layout_json,layout_sha)
                SELECT ?,profile_id,profile_version,safe_zone_json,safe_zone_sha,layout_json,layout_sha
                FROM live_job_templates WHERE job_id=?""",(child_id,parent_id))
            c.execute("""UPDATE live_dual_groups SET child_job_id=?,generation=?,input_sha=?,
                copy_sha=?,review_sha=?,approval_sha=? WHERE parent_job_id=?""",
                (child_id,expected_generation,parent["input_sha"],parent["copy_sha"],
                 parent["review_sha"],parent["approval_sha"],parent_id))
            c.executemany("""INSERT INTO live_dual_variants (job_id,parent_job_id,dispatch_state)
                VALUES (?,?,'PENDING')""",((parent_id,parent_id),(child_id,parent_id)))
            self._event(c,parent,"dual_approval_bound",parent["state"],parent["approval_sha"])
            self._event(c,child,"dual_copy_derived",child["state"],parent["approval_sha"])
            result=self._dual_group(c,actor,parent_id)
            c.commit()
            return result

    @contextmanager
    def dual_dispatch_lock(self,actor,parent_id,variant_job_id):
        """Hold an exclusive local fixture claim through candidate commit."""
        with self.db() as c:
            self._dual_variant_job(c,actor,parent_id,variant_job_id)
        lock_dir=self.filename.parent/"dual-dispatch-locks"
        lock_dir.mkdir(mode=0o700,exist_ok=True)
        with (lock_dir/digest(variant_job_id)).open("a") as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield self._claim_dual_dispatch(actor,parent_id,variant_job_id)

    def _claim_dual_dispatch(self,actor,parent_id,variant_job_id):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._dual_variant_job(c,actor,parent_id,variant_job_id)
            variant=c.execute("SELECT dispatch_state FROM live_dual_variants WHERE job_id=?",
                              (variant_job_id,)).fetchone()
            if variant is None:
                raise LiveGateError("DUAL_VARIANT_NOT_FOUND")
            if variant["dispatch_state"]=="RUNNING":
                # Only the previous lock holder could have left RUNNING. A
                # new explicit request exposes the failure without rerendering.
                self._record_dual_dispatch_failure(c,job,"DUAL_FIXTURE_DISPATCH_INTERRUPTED")
                c.commit()
                return False
            if variant["dispatch_state"]!="PENDING":
                return False
            if job["state"]!="COPY_APPROVED":
                return False
            self._approved(job,c)
            changed=c.execute("""UPDATE live_dual_variants SET dispatch_state='RUNNING'
                WHERE job_id=? AND dispatch_state='PENDING'""",(variant_job_id,)).rowcount
            c.commit()
            return bool(changed)

    def finish_dual_dispatch(self,actor,parent_id,variant_job_id,error_code=None):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._dual_variant_job(c,actor,parent_id,variant_job_id)
            variant=c.execute("SELECT dispatch_state FROM live_dual_variants WHERE job_id=?",
                              (variant_job_id,)).fetchone()
            if variant and variant["dispatch_state"]=="SUCCEEDED":
                return  # The candidate and successful dispatch are committed together.
            if not error_code:
                raise LiveGateError("DUAL_CANDIDATE_NOT_COMMITTED")
            self._record_dual_dispatch_failure(c,job,error_code)
            c.commit()

    def _record_dual_dispatch_failure(self,c,job,error_code):
        changed=c.execute("""UPDATE live_dual_variants SET dispatch_state='FAILED',dispatch_error=?
            WHERE job_id=? AND dispatch_state='RUNNING'""",
            (error_code,job["job_id"])).rowcount
        if changed!=1:
            raise LiveGateError("DUAL_DISPATCH_STATE_CONFLICT")
        self._event(c,job,"dual_dispatch_finished","FAILED",digest(error_code))

    def _dual_variant_job(self,c,actor,parent_id,variant_job_id):
        group=self._dual_row(c,actor,parent_id)
        if (not group or group["parent_job_id"]!=parent_id or not group["child_job_id"] or
            variant_job_id not in (parent_id,group["child_job_id"])):
            raise LiveGateError("DUAL_VARIANT_NOT_FOUND")
        job=self._read(c,variant_job_id,actor)
        if job["mode"]!="OFFLINE_FIXTURE":
            raise LiveGateError("DUAL_REQUIRES_OFFLINE_FIXTURE")
        return job

    def select_dual_variant(self,actor,parent_id,mode,expected_final_sha):
        if mode not in ("composed","freeform"):
            raise LiveGateError("DUAL_VARIANT_NOT_FOUND")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            group=self._dual_row(c,actor,parent_id)
            if group is None:
                raise LiveGateError("DUAL_GROUP_NOT_FOUND")
            variant_job_id=parent_id if mode=="composed" else group["child_job_id"]
            job=self._dual_variant_job(c,actor,parent_id,variant_job_id)
            if (job["state"]!="COMPLETED" or not job["final_sha"] or
                job["final_sha"]!=expected_final_sha):
                raise LiveGateError("DUAL_FINAL_SELECTION_STALE")
            self._approved(job,c,allow_completed=True)
            self._dual_visual_sha(c,job)
            c.execute("""UPDATE live_dual_groups SET preferred_mode=?,preferred_final_sha=?
                WHERE parent_job_id=?""",(mode,expected_final_sha,parent_id))
            self._event(c,job,"dual_variant_selected",job["state"],expected_final_sha)
            result=self._dual_group(c,actor,parent_id)
            c.commit()
            return result

    def _active_policy(self,c,*,activate=False):
        """Fail-closed runtime checks; only constructor can change DB epoch.

        Old worker cannot downgrade the activation ledger on a routine GET.
        Version changes require new process startup, immutable release and
        no conflicting active workers.
        """
        if not policy_enabled() or self._policy_at_init is None:
            raise LiveGateError("REVIEW_POLICY_RUNTIME_VERSION_CHANGED")
        if self._source_at_init!=sources_fingerprint():
            raise LiveGateError("REVIEW_POLICY_RUNTIME_SOURCE_CHANGED")
        actual=current_policy()
        if actual!=self._policy_at_init:
            raise LiveGateError("REVIEW_POLICY_RUNTIME_VERSION_CHANGED")
        row=c.execute("""SELECT epoch,policy_version,policy_sha FROM
                         live_policy_activation WHERE singleton=1""").fetchone()
        if row is None:
            if not activate:
                raise LiveGateError("REVIEW_POLICY_ACTIVATION_REQUIRED")
            epoch=1
            c.execute("""INSERT INTO live_policy_activation VALUES (1,?,?,?)""",
                      (epoch,actual["version"],actual["sha"]))
        elif (row["policy_version"]!=actual["version"]
              or row["policy_sha"]!=actual["sha"]):
            if not activate:
                raise LiveGateError("REVIEW_POLICY_ACTIVATION_REQUIRED")
            epoch=row["epoch"]+1
            c.execute("""UPDATE live_policy_activation SET
                         epoch=?,policy_version=?,policy_sha=? WHERE singleton=1""",
                      (epoch,actual["version"],actual["sha"]))
        else:
            epoch=row["epoch"]
        return {**actual,"epoch":epoch}

    @staticmethod
    def _bind_review_policy(c,job_id,generation,review_sha,policy):
        if policy is None:return
        c.execute("""INSERT INTO live_review_policy
             (job_id,generation,policy_version,policy_sha,review_sha,activation_epoch)
             VALUES (?,?,?,?,?,?)""",
             (job_id,generation,policy["version"],policy["sha"],
              review_sha,policy["epoch"]))

    def _ensure_current_review_policy(self,c,job):
        if not policy_enabled():return None
        actual=self._active_policy(c)
        stored=c.execute("""SELECT policy_version,policy_sha,review_sha,activation_epoch
             FROM live_review_policy WHERE job_id=? AND generation=?""",
             (job["job_id"],job["generation"])).fetchone()
        if stored is None:
            raise LiveGateError("REVIEW_POLICY_REVALIDATION_REQUIRED")
        bound={"version":stored["policy_version"],"sha":stored["policy_sha"]}
        if stored["activation_epoch"] is not None:
            bound["epoch"]=stored["activation_epoch"]
        proof=review_digest(job["input_sha"],json.loads(job["analysis_json"]),
                            json.loads(job["copy_json"]),json.loads(job["compliance_json"]),
                            job["generation"],bound)
        if stored["review_sha"]!=job["review_sha"] or proof!=job["review_sha"]:
            raise LiveGateError("REVIEW_POLICY_BINDING_TAMPERED")
        if "epoch" not in bound or bound!=actual:
            raise LiveGateError("REVIEW_POLICY_REVALIDATION_REQUIRED")
        return bound

    def ensure_policy_current(self,actor,job_id):
        with self.db() as c:
            return self._ensure_current_review_policy(c,self._read(c,job_id,actor))

    def active_review_policy(self):
        with self.db() as c:
            return self._active_policy(c)

    @staticmethod
    def _require_llm_review(job,policy):
        if not llm_required(job["mode"]):
            return
        proof=json.loads(job["compliance_json"]).get("llm_review")
        if not proof:
            raise LiveGateError("LLM_REVIEW_REQUIRED")
        analysis=json.loads(job["analysis_json"])
        copy=json.loads(job["copy_json"])
        rule_report=strict_review(copy,json.loads(job["input_json"])["product"],analysis)
        expected={"job_id":job["job_id"],"input_sha":job["input_sha"],
                  "copy_sha":job["copy_sha"],"generation":job["generation"],
                  "policy_version":policy["version"] if policy else None,
                  "policy_sha":policy["sha"] if policy else None,
                  "policy_epoch":policy["epoch"] if policy else None,
                  "model":__import__("os").environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"),
                  "source_review_sha":review_digest(
                      job["input_sha"],analysis,copy,rule_report,job["generation"],policy)}
        if (any(proof.get(key)!=value for key,value in expected.items()) or
                not all(isinstance(proof.get(key),str) and len(proof[key])==64
                        for key in ("receipt_sha","result_sha")) or
                not proof.get("attempt_id") or not proof.get("response_model")):
            raise LiveGateError("LLM_REVIEW_BINDING_INVALID")

    def _copy_review_context(self,c,job,expected_generation,expected_review_sha,*,text_model):
        if not llm_required(job["mode"]):
            raise LiveGateError("LLM_REVIEW_NOT_ENABLED")
        if (type(expected_generation) is not int or job["state"]!="COPY_REVIEW_REQUIRED" or
                job["generation"]!=expected_generation or job["review_sha"]!=expected_review_sha):
            raise LiveGateError("STALE_REVIEW_OR_REVISION")
        policy=self._ensure_current_review_policy(c,job)
        if policy is None:
            raise LiveGateError("LLM_REVIEW_POLICY_REQUIRED")
        if text_model!=__import__("os").environ.get("IT_TEM_TEXT_MODEL","gpt-6-luna"):
            raise LiveGateError("LLM_REVIEW_MODEL_MISMATCH")
        if digest(json.loads(job["copy_json"]))!=job["copy_sha"]:
            raise LiveGateError("LLM_REVIEW_COPY_INTEGRITY_FAILED")
        if json.loads(job["compliance_json"]).get("llm_review"):
            self._require_llm_review(job,policy)
            raise LiveGateError("LLM_REVIEW_ALREADY_CURRENT")
        return {"job_id":job["job_id"],"input_sha":job["input_sha"],
                "copy_sha":job["copy_sha"],"generation":job["generation"],
                "source_review_sha":job["review_sha"],"model":text_model,
                "policy_version":policy["version"],"policy_sha":policy["sha"],
                "policy_epoch":policy["epoch"]}

    def copy_review_context(self,actor,job_id,expected_generation,expected_review_sha,*,text_model):
        with self.db() as c:
            return self._copy_review_context(c,self._read(c,job_id,actor),
                expected_generation,expected_review_sha,text_model=text_model)

    def complete_copy_review(self,actor,job_id,context,result,receipt):
        from src.text_generation.schemas import AdCopyOutput,ProductInput
        from .copy_review import complete_report
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            current=self._copy_review_context(c,job,context["generation"],
                context["source_review_sha"],text_model=context["model"])
            if current!=context:
                raise LiveGateError("LLM_REVIEW_CONTEXT_STALE")
            copy=AdCopyOutput.model_validate(json.loads(job["copy_json"]),strict=True)
            product=ProductInput.model_validate(json.loads(job["input_json"])["product"],strict=True)
            report=complete_report(json.loads(job["compliance_json"]),copy,product,result,context,receipt)
            policy=self._active_policy(c)
            bound=review_digest(job["input_sha"],json.loads(job["analysis_json"]),copy.model_dump(mode="json"),
                                report,job["generation"],policy)
            c.execute("UPDATE live_jobs SET compliance_json=?,review_sha=? WHERE job_id=?",
                      (json.dumps(report,ensure_ascii=False),bound,job_id))
            c.execute("UPDATE live_review_policy SET review_sha=? WHERE job_id=? AND generation=?",
                      (bound,job_id,job["generation"]))
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"real_llm_compliance_reviewed",updated["state"],bound)
            c.commit()
            return updated

    def policy_status(self,actor,job_id):
        with self.db() as c:
            job=self._read(c,job_id,actor)
            if not policy_enabled():
                return {"status":"LEGACY_POLICY_MODE","version":None,"sha":None}
            try:
                policy=self._active_policy(c)
            except LiveGateError as exc:
                if exc.code in ("REVIEW_POLICY_RUNTIME_SOURCE_CHANGED",
                                "REVIEW_POLICY_RUNTIME_VERSION_CHANGED",
                                "REVIEW_POLICY_ACTIVATION_REQUIRED"):
                    return {"status":"RESTART_REQUIRED","version":None,"sha":None}
                raise
            row=c.execute("""SELECT policy_version,policy_sha,review_sha,activation_epoch
                       FROM live_review_policy WHERE job_id=? AND generation=?""",
                       (job_id,job["generation"])).fetchone()
            if row is None:
                return {"status":"LEGACY_UNBOUND","version":None,"sha":None}
            actual={"version":row["policy_version"],"sha":row["policy_sha"]}
            try:self._ensure_current_review_policy(c,job)
            except LiveGateError as exc:
                return {"status":("REVALIDATION_REQUIRED" if
                    exc.code=="REVIEW_POLICY_REVALIDATION_REQUIRED" else
                    "BINDING_TAMPERED"),**actual}
            return {"status":"CURRENT",**actual}

    def revalidate_review_policy(self,actor,job_id,expected_generation,expected_review_sha):
        """Explicit compare-and-swap policy re-review; never revives old approval."""
        if not policy_enabled():
            raise LiveGateError("REVIEW_POLICY_FEATURE_NOT_ENABLED")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            policy=self._active_policy(c)
            job=self._read(c,job_id,actor)
            dual=self._dual_row(c,actor,job_id) or self._live_dual_row(c,actor,job_id)
            if dual and dual["child_job_id"]:
                raise LiveGateError("DUAL_APPROVED_COPY_IMMUTABLE")
            if job["state"] not in ("COPY_REVIEW_REQUIRED","COPY_APPROVED",
                                    "COPY_REJECTED","PROMPT_READY",
                                    "IMAGE_REVIEW_REQUIRED","IMAGE_REJECTED",
                                    "IMAGE_APPROVED"):
                raise LiveGateError("REVIEW_POLICY_REVALIDATION_STATE_CONFLICT")
            if (type(expected_generation) is not int or
                expected_generation!=job["generation"] or
                expected_review_sha!=job["review_sha"]):
                raise LiveGateError("STALE_REVIEW_OR_REVISION")
            old=c.execute("""SELECT policy_version,policy_sha,review_sha,activation_epoch
                   FROM live_review_policy WHERE job_id=? AND generation=?""",
                   (job_id,job["generation"])).fetchone()
            if old is not None:
                prior={"version":old["policy_version"],"sha":old["policy_sha"]}
                if old["activation_epoch"] is not None:
                    prior["epoch"]=old["activation_epoch"]
                if (old["review_sha"]!=job["review_sha"] or
                    review_digest(job["input_sha"],json.loads(job["analysis_json"]),
                      json.loads(job["copy_json"]),json.loads(job["compliance_json"]),
                      job["generation"],prior)!=job["review_sha"]):
                    raise LiveGateError("REVIEW_POLICY_BINDING_TAMPERED")
                if prior==policy:
                    raise LiveGateError("REVIEW_POLICY_ALREADY_CURRENT")
            else:
                # Pre-F11 historical pending jobs have the former digest format.
                legacy=review_digest(job["input_sha"],json.loads(job["analysis_json"]),
                            json.loads(job["copy_json"]),json.loads(job["compliance_json"]),
                            job["generation"])
                if legacy!=job["review_sha"]:
                    raise LiveGateError("REVIEW_POLICY_LEGACY_BINDING_INVALID")
            product=json.loads(job["input_json"])["product"]
            analysis=json.loads(job["analysis_json"])
            copy=json.loads(job["copy_json"])
            report=strict_review(copy,product,analysis)
            generation=job["generation"]+1
            bound=review_digest(job["input_sha"],analysis,copy,report,generation,policy)
            c.execute("""UPDATE live_jobs SET state='COPY_REVIEW_REQUIRED',
                generation=?,compliance_json=?,review_sha=?,approval_sha=NULL,
                approved_generation=NULL,evidence_acknowledged=0,
                prompt_json=NULL,image_sha=NULL,image_approval_sha=NULL,
                final_sha=NULL,caption_sha=NULL WHERE job_id=?""",
                (generation,json.dumps(report,ensure_ascii=False),bound,job_id))
            c.execute("DELETE FROM live_copy_previous WHERE job_id=?",(job_id,))
            c.execute("DELETE FROM live_copy_revision_feedback WHERE job_id=?",(job_id,))
            self._bind_review_policy(c,job_id,generation,bound,policy)
            updated=self._read(c,job_id,actor)
            self._event(c,updated,"bp18_policy_revalidated_old_approval_invalidated",
                        updated["state"],bound)
            c.commit()
            return updated

    def store_text(self,actor,job_id,analysis,research,copy,*,mode="OFFLINE_FIXTURE"):
        if mode not in ("OFFLINE_FIXTURE","LIVE"):
            raise LiveGateError("INVALID_PROVENANCE")
        a,r,display,candidate,sha=owner_text_snapshots(analysis,research,copy)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if mode!="LIVE" and self._live_dual_row(c,actor,job_id):
                raise LiveGateError("LIVE_DUAL_REQUIRES_LIVE")
            if mode=="LIVE" and self._dual_row(c,actor,job_id):
                raise LiveGateError("DUAL_REQUIRES_OFFLINE_FIXTURE")
            if job["state"]!="INPUT_STORED" or job["mode"]!="INPUT_ONLY":
                raise LiveGateError("LIVE_TEXT_STATE_CONFLICT")
            context=json.loads(job["input_json"])
            report=strict_review(candidate,context["product"],a)
            policy=self._active_policy(c) if policy_enabled() else None
            report_sha=review_digest(job["input_sha"],a,candidate,report,
                         job["generation"]+1,policy)
            c.execute("""UPDATE live_jobs SET state='COPY_REVIEW_REQUIRED',mode=?,generation=generation+1,
               analysis_json=?,research_json=?,research_display_json=?,
               copy_json=?,copy_sha=?,compliance_json=?,review_sha=? WHERE job_id=?""",
               (mode,json.dumps(a,ensure_ascii=False),json.dumps(r,ensure_ascii=False),
                json.dumps(display,ensure_ascii=False),
                json.dumps(candidate,ensure_ascii=False),sha,
                json.dumps(report,ensure_ascii=False),report_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._bind_review_policy(c,job_id,updated["generation"],report_sha,policy)
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
            dual=self._dual_row(c,actor,job_id) or self._live_dual_row(c,actor,job_id)
            if dual and dual["child_job_id"]:
                raise LiveGateError("DUAL_APPROVED_COPY_IMMUTABLE")
            if job["state"] not in ("COPY_REVIEW_REQUIRED","COPY_APPROVED","COPY_REJECTED"):
                raise LiveGateError("COPY_EDIT_STATE_CONFLICT")
            if parsed.sha256==job["copy_sha"]:
                raise LiveGateError("COPY_EDIT_UNCHANGED")
            context=json.loads(job["input_json"])
            analysis=json.loads(job["analysis_json"])
            report=strict_review(parsed.output,context["product"],analysis)
            generation=job["generation"]+1
            policy=self._active_policy(c) if policy_enabled() else None
            report_sha=review_digest(job["input_sha"],analysis,parsed.output,report,generation,policy)
            if llm_required(job["mode"]):
                c.execute("""INSERT INTO live_copy_previous
                    (job_id,copy_json,copy_sha,origin_generation,reason_sha)
                    VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
                    copy_json=excluded.copy_json,copy_sha=excluded.copy_sha,
                    origin_generation=excluded.origin_generation,reason_sha=excluded.reason_sha""",
                    (job_id,job["copy_json"],job["copy_sha"],job["generation"],
                     digest({"source":"manual_edit","copy_sha":parsed.sha256})))
            else:
                c.execute("DELETE FROM live_copy_previous WHERE job_id=?",(job_id,))
            c.execute("DELETE FROM live_copy_revision_feedback WHERE job_id=?",(job_id,))
            c.execute("""UPDATE live_jobs SET generation=?,state='COPY_REVIEW_REQUIRED',copy_json=?,
              copy_sha=?,compliance_json=?,review_sha=?,approval_sha=NULL,
              approved_generation=NULL,evidence_acknowledged=0,prompt_json=NULL,image_sha=NULL,
              image_approval_sha=NULL,final_sha=NULL,caption_sha=NULL WHERE job_id=?""",
              (generation,json.dumps(parsed.output,ensure_ascii=False),parsed.sha256,
               json.dumps(report,ensure_ascii=False),report_sha,job_id))
            updated=self._read(c,job_id,actor)
            self._bind_review_policy(c,job_id,generation,report_sha,policy)
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
            self._ensure_current_review_policy(c,job)
            original=json.loads(job["copy_json"])
            context=json.loads(job["input_json"])
            analysis=json.loads(job["analysis_json"])
            report=strict_review(parsed.output,context["product"],analysis)
            previous_report=json.loads(job["compliance_json"])
            if parsed.sha256==job["copy_sha"] and previous_report.get("llm_review"):
                self._require_llm_review(job,self._active_policy(c))
                report=previous_report
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
            policy=self._active_policy(c) if policy_enabled() else None
            report_sha=review_digest(job["input_sha"],analysis,parsed.output,report,generation,policy)
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
            self._bind_review_policy(c,job_id,generation,report_sha,policy)
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
            self._ensure_current_review_policy(c,job)
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
            policy=self._active_policy(c) if policy_enabled() else None
            report_sha=review_digest(job["input_sha"],analysis,parsed.output,report,generation,policy)
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
            self._bind_review_policy(c,job_id,generation,report_sha,policy)
            self._event(c,updated,"copy_previous_restored_review_started",
                        updated["state"],report_sha)
            c.commit()
            return updated

    def approval_binding(self,job,c=None):
        payload={"input_sha":job["input_sha"],"analysis":json.loads(job["analysis_json"]),
                 "copy_sha":job["copy_sha"],"review_sha":job["review_sha"],
                 "generation":job["generation"],
                 "evidence_acknowledged":bool(job["evidence_acknowledged"])}
        if policy_enabled():
            if c is None:
                with self.db() as opened:
                    policy=self._active_policy(opened)
            else:
                policy=self._active_policy(c)
            payload.update(review_policy_version=policy["version"],
                           review_policy_sha=policy["sha"],
                           review_policy_epoch=policy["epoch"])
        return digest(payload)

    def approve_copy(self,actor,job_id,expected_generation,expected_review_sha,*,acknowledge_evidence=False):
        if type(expected_generation) is not int:
            raise LiveGateError("REVISION_TYPE_INVALID")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if self._dual_row(c,actor,job_id) or self._live_dual_row(c,actor,job_id):
                raise LiveGateError("DUAL_COPY_APPROVAL_REQUIRED")
            updated=self._approve_copy_locked(c,job,expected_generation,expected_review_sha,
                                              acknowledge_evidence=acknowledge_evidence)
            c.commit()
            return updated

    def _approve_copy_locked(self,c,job,expected_generation,expected_review_sha,*,acknowledge_evidence):
        if job["state"]!="COPY_REVIEW_REQUIRED":
            raise LiveGateError("COPY_APPROVAL_STATE_CONFLICT")
        if job["generation"]!=expected_generation or job["review_sha"]!=expected_review_sha:
            raise LiveGateError("STALE_REVIEW_OR_REVISION")
        policy=self._ensure_current_review_policy(c,job)
        self._require_llm_review(job,policy)
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
        job_id,actor=job["job_id"],job["actor"]
        # Persist the user declaration BEFORE binding an approval.
        c.execute("UPDATE live_jobs SET evidence_acknowledged=? WHERE job_id=?",
                  (int(acknowledge_evidence is True),job_id))
        bound=self._read(c,job_id,actor)
        binding=self.approval_binding(bound,c)
        c.execute("""UPDATE live_jobs SET state='COPY_APPROVED',approval_sha=?,
            approved_generation=? WHERE job_id=?""",
            (binding,expected_generation,job_id))
        updated=self._read(c,job_id,actor)
        self._event(c,updated,"real_copy_approved",updated["state"],binding)
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

    def _approved(self,job,c=None,*,allow_completed=False):
        if c is None:
            with self.db() as opened:
                return self._approved(job,opened,allow_completed=allow_completed)
        live_group=self._live_dual_row(c,job["actor"],job["job_id"])
        if live_group is not None:
            if not llm_required("LIVE") or not policy_enabled():
                raise LiveGateError("LIVE_DUAL_F09_POLICY_REQUIRED")
            parent=self._assert_live_dual_binding(c,job,live_group)
            if parent["job_id"]!=job["job_id"]:
                self._check_approval(c,parent,allow_completed=True)
                return self._check_approval(c,job,allow_completed=allow_completed,derived_f09=True)
            return self._check_approval(c,job,allow_completed=allow_completed)
        group=self._dual_row(c,job["actor"],job["job_id"])
        if group is not None:
            parent=self._assert_dual_binding(c,job,group)
            if parent["job_id"]!=job["job_id"]:
                self._check_approval(c,parent,allow_completed=True)
        elif c.execute("""SELECT 1 FROM live_events WHERE job_id=?
                           AND event IN ('dual_input_committed','dual_copy_derived',
                                         'live_dual_input_committed','live_dual_copy_derived')""",
                        (job["job_id"],)).fetchone():
            raise LiveGateError("DUAL_GROUP_BINDING_MISSING")
        self._check_approval(c,job,allow_completed=allow_completed)

    def _check_approval(self,c,job,*,allow_completed=False,derived_f09=False):
        policy=self._ensure_current_review_policy(c,job)
        if not derived_f09:
            self._require_llm_review(job,policy)
        states={"COPY_APPROVED","PROMPT_READY","IMAGE_REVIEW_REQUIRED","IMAGE_APPROVED","IMAGE_REJECTED"}
        if allow_completed:
            states.add("COMPLETED")
        if not (job["state"] in states
                and job["approval_sha"] and job["approved_generation"]==job["generation"]
                and job["approval_sha"]==self.approval_binding(job,c)
                and json.loads(job["compliance_json"])["passed"]):
            raise LiveGateError("APPROVAL_CONTEXT_NOT_CURRENT")

    def _assert_live_dual_binding(self,c,job,group):
        try:
            parent=self._read(c,group["parent_job_id"],job["actor"])
            child=self._read(c,group["child_job_id"],job["actor"])
            if job["job_id"] not in (parent["job_id"],child["job_id"]):
                raise ValueError
            authority=json.loads(group["authority_json"])
            snapshot=json.loads(parent["input_json"])
            expected_child={**snapshot,"generation_mode":"freeform"}
            if (parent["mode"]!="LIVE" or child["mode"]!="LIVE" or
                snapshot.get("generation_mode")!="composed" or snapshot.get("image_size") not in {"3:4","4:5","9:16"} or
                digest(snapshot)!=parent["input_sha"] or digest(expected_child)!=child["input_sha"] or
                expected_child!=json.loads(child["input_json"]) or
                digest(json.loads(parent["copy_json"]))!=parent["copy_sha"] or
                group["copy_sha"]!=parent["copy_sha"] or group["approval_sha"]!=parent["approval_sha"] or
                any(child[key]!=parent[key] for key in ("generation","copy_json","copy_sha","analysis_json",
                    "research_json","research_display_json","evidence_acknowledged")) or
                digest(authority)!=group["authority_sha"] or
                authority!=self._live_dual_authority(c,parent,child,authority["execution_profile"]) or
                json.loads(child["compliance_json"])!=self._live_dual_child_report(parent,authority["f09"])):
                raise ValueError
            marker=c.execute("""SELECT 1 FROM live_events WHERE job_id=? AND event=?
                AND generation=? AND payload_sha=?""",(job["job_id"],
                "live_dual_authority_committed" if job["job_id"]==parent["job_id"] else "live_dual_copy_derived",
                parent["generation"],group["authority_sha"])).fetchone()
            if marker is None:
                raise ValueError
            if group["prompt_sha"] and any(digest(json.loads(member["prompt_json"]))!=group["prompt_sha"]
                                          for member in (parent,child)):
                raise ValueError
            self._assert_dual_review_digest(c,parent)
            self._assert_dual_review_digest(c,child)
        except (ValueError,KeyError,TypeError):
            raise LiveGateError("LIVE_DUAL_AUTHORITY_BINDING_INVALID") from None
        return parent

    def _assert_dual_binding(self,c,job,group):
        parent_id=group["parent_job_id"]
        child_id=group["child_job_id"]
        parent=job if job["job_id"]==parent_id else self._read(c,parent_id,job["actor"])
        if (not child_id or parent["mode"]!="OFFLINE_FIXTURE" or job["mode"]!="OFFLINE_FIXTURE" or
            any(parent[key]!=group[key] for key in ("generation","input_sha","copy_sha","review_sha","approval_sha"))):
            raise LiveGateError("DUAL_SOURCE_APPROVAL_CHANGED")
        source=json.loads(parent["input_json"])
        if (source.get("generation_mode")!="composed" or digest(source)!=parent["input_sha"] or
            digest(json.loads(parent["copy_json"]))!=parent["copy_sha"]):
            raise LiveGateError("DUAL_SOURCE_APPROVAL_CHANGED")
        self._assert_dual_review_digest(c,parent)
        if job["job_id"]==child_id:
            expected={**source,"generation_mode":"freeform"}
            if (json.loads(job["input_json"])!=expected or job["input_sha"]!=digest(expected) or
                any(job[key]!=parent[key] for key in ("generation","copy_json","copy_sha","analysis_json",
                    "research_json","research_display_json","compliance_json","evidence_acknowledged"))):
                raise LiveGateError("DUAL_VARIANT_COPY_CHANGED")
            self._assert_dual_review_digest(c,job)
        return parent

    @staticmethod
    def _assert_dual_review_digest(c,job):
        row=c.execute("""SELECT policy_version,policy_sha,activation_epoch,review_sha
            FROM live_review_policy WHERE job_id=? AND generation=?""",
            (job["job_id"],job["generation"])).fetchone()
        policy=None
        if row:
            if row["review_sha"]!=job["review_sha"]:
                raise LiveGateError("DUAL_REVIEW_BINDING_CHANGED")
            policy={"version":row["policy_version"],"sha":row["policy_sha"]}
            if row["activation_epoch"] is not None:
                policy["epoch"]=row["activation_epoch"]
        proof=review_digest(job["input_sha"],json.loads(job["analysis_json"]),
                            json.loads(job["copy_json"]),json.loads(job["compliance_json"]),
                            job["generation"],policy)
        if proof!=job["review_sha"]:
            raise LiveGateError("DUAL_REVIEW_BINDING_CHANGED")

    def store_prompt(self,actor,job_id,prompt,*,expected_approval_sha=None):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="COPY_APPROVED":
                raise LiveGateError("PROMPT_REQUIRES_COPY_APPROVAL")
            if expected_approval_sha is not None and job["approval_sha"]!=expected_approval_sha:
                raise LiveGateError("PROMPT_APPROVAL_STALE")
            self._approved(job,c)
            if self._dual_row(c,actor,job_id):
                dispatch=c.execute("SELECT dispatch_state FROM live_dual_variants WHERE job_id=?",
                                   (job_id,)).fetchone()
                if not dispatch or dispatch["dispatch_state"]!="RUNNING":
                    raise LiveGateError("DUAL_DISPATCH_NOT_CLAIMED")
            if self._live_dual_row(c,actor,job_id) and not c.execute("""
                SELECT 1 FROM live_paid_dual_intents WHERE job_id=? AND stage='image_prompt'
                AND state='QUEUED'""",(job_id,)).fetchone():
                raise LiveGateError("LIVE_DUAL_PROMPT_INTENT_REQUIRED")
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
            if self._live_dual_row(c,actor,job_id):
                raise LiveGateError("LIVE_DUAL_REGENERATION_NOT_ENABLED")
            previous=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
                ORDER BY attempt_version DESC LIMIT 1""",(job_id,)).fetchone()
            if (job["state"]=="PROMPT_READY" and previous is not None
                    and previous["request_key"]==request_key
                    and previous["state"]=="REQUESTED"):
                return dict(previous)
            if job["state"]!="IMAGE_REJECTED" or job["image_sha"]!=expected_sha:
                raise LiveGateError("IMAGE_RETRY_STALE_REJECTION")
            self._approved(job,c)
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

    def image_request(self,actor,job_id,images,references,*,expected_approval_sha=None):
        from src.image_generation import BackendImageInput
        from src.image_generation.contracts import content_hash
        with self.db() as c:
            job=self._read(c,job_id,actor)
            if job["state"]!="PROMPT_READY":
                raise LiveGateError("IMAGE_REQUIRES_PROMPT")
            if expected_approval_sha is not None and job["approval_sha"]!=expected_approval_sha:
                raise LiveGateError("IMAGE_QUEUE_CONTEXT_STALE")
            self._approved(job,c)
            profile_row=c.execute("SELECT * FROM live_job_templates WHERE job_id=?",
                                  (job_id,)).fetchone()
            policy=verify_policy(profile_row)
            metadata={}
            if policy is not None and (policy["profile_id"].startswith(SIZE_PREFIX) or
                policy["profile_id"].startswith(BP18_PREFIX) or policy["profile_id"].startswith(DUAL_CTA_PREFIX)
                or policy["profile_id"].startswith("BP18_BETA_EDITORIAL_")):
                from src.image_generation.size_selection import resolve_size_choice
                size=json.loads(job["input_json"]).get("image_size")
                if size!=policy["safe_zone"]["size"]:
                    raise LiveGateError("OWNER_IMAGE_SIZE_CONTEXT_CONFLICT")
                selection,_=resolve_size_choice(size)
                if policy["profile_id"].startswith(BP18_PREFIX):
                    from src.image_generation.contracts import BP18_V3_LAYOUT_VERSION
                    selection=type(selection).model_validate({
                        **selection.model_dump(mode="json"),
                        "version":BP18_V3_LAYOUT_VERSION},strict=True)
                if policy["profile_id"].startswith(DUAL_CTA_PREFIX):
                    from src.image_generation.contracts import BP18_DUAL_IMAGE_CTA_VERSION
                    selection=type(selection).model_validate({
                        **selection.model_dump(mode="json"),"version":BP18_DUAL_IMAGE_CTA_VERSION},strict=True)
                if policy["profile_id"].startswith("BP18_BETA_EDITORIAL_"):
                    selection=type(selection).model_validate(policy["safe_zone"]["layout_selection"],strict=True)
                metadata["layout_selection"]=selection.model_dump(mode="json")
            elif policy is not None:
                metadata["safe_zone"]=policy["safe_zone"]
            saved=json.loads(job["input_json"])
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
                              candidate_receipt_sha=None,expected_approval_sha=None):
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
            if expected_approval_sha is not None and job["approval_sha"]!=expected_approval_sha:
                raise LiveGateError("IMAGE_APPROVAL_STALE")
            self._approved(job,c)
            dual=self._dual_row(c,actor,job_id)
            if self._live_dual_row(c,actor,job_id) and (
                not provider_attempt_id or not candidate_receipt_sha or not c.execute("""
                    SELECT 1 FROM live_paid_dual_intents WHERE job_id=? AND stage='image'
                    AND state='QUEUED'""",(job_id,)).fetchone()):
                raise LiveGateError("LIVE_DUAL_IMAGE_INTENT_OR_RECEIPT_REQUIRED")
            prior=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
                ORDER BY attempt_version DESC LIMIT 1""",(job_id,)).fetchone()
            if prior is None:
                if dual:
                    changed=c.execute("""UPDATE live_dual_variants SET dispatch_state='SUCCEEDED'
                        WHERE job_id=? AND dispatch_state='RUNNING'""",(job_id,)).rowcount
                    if changed!=1:
                        raise LiveGateError("DUAL_DISPATCH_NOT_CLAIMED")
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

    def approve_image(self,actor,job_id,expected_sha,*,visual_review=None,reviewer_role=None):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_REVIEW_REQUIRED" or expected_sha!=job["image_sha"]:
                raise LiveGateError("IMAGE_APPROVAL_MISMATCH")
            self._approved(job,c)
            if self._dual_row(c,actor,job_id):
                record=self._dual_visual_record(job,visual_review)
                visual_sha=digest(record)
                changed=c.execute("""UPDATE live_dual_variants SET visual_review_json=?,visual_review_sha=?
                    WHERE job_id=? AND dispatch_state='SUCCEEDED'""",
                    (canonical(record),visual_sha,job_id)).rowcount
                if changed!=1:
                    raise LiveGateError("DUAL_CANDIDATE_NOT_COMMITTED")
                self._event(c,job,"dual_fixture_visual_attested",job["state"],visual_sha)
            elif self._live_dual_row(c,actor,job_id):
                attempt=self._live_dual_candidate(c,job)
                record=self._live_dual_visual_record(
                    job,visual_review,attempt,reviewer_role=reviewer_role,
                    reviewed_utc=datetime.now(timezone.utc).isoformat())
                visual_sha=digest(record)
                c.execute("""INSERT INTO live_paid_dual_visual_reviews (job_id,record_json,record_sha)
                    VALUES (?,?,?)""",(job_id,canonical(record),visual_sha))
                self._event(c,job,"live_dual_visual_attested",job["state"],visual_sha)
            elif visual_review is not None:
                raise LiveGateError("DUAL_VARIANT_NOT_FOUND")
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

    @staticmethod
    def _dual_visual_record(job,visual_review):
        mode=json.loads(job["input_json"])["generation_mode"]
        required={"product_matches"}
        if mode=="freeform":
            required.update(("copy_matches","no_duplicate_text"))
        if (not isinstance(visual_review,dict) or set(visual_review)!=required or
            any(value is not True for value in visual_review.values())):
            raise LiveGateError("DUAL_VISUAL_REVIEW_REQUIRED")
        return {"source":"OFFLINE_FIXTURE_MANUAL_ATTESTATION","mode":mode,
                "actor":job["actor"],"job_id":job["job_id"],"image_sha":job["image_sha"],
                "copy_sha":job["copy_sha"],"approval_sha":job["approval_sha"],
                "checks":visual_review}

    def _dual_visual_sha(self,c,job):
        group=self._dual_row(c,job["actor"],job["job_id"])
        if not group:
            return None
        row=c.execute("""SELECT visual_review_json,visual_review_sha FROM live_dual_variants
            WHERE job_id=? AND parent_job_id=? AND dispatch_state='SUCCEEDED'""",
            (job["job_id"],group["parent_job_id"])).fetchone()
        if row is None or row["visual_review_json"] is None:
            raise LiveGateError("DUAL_VISUAL_REVIEW_REQUIRED")
        try:
            record=json.loads(row["visual_review_json"])
            if (record!=self._dual_visual_record(job,record["checks"]) or
                digest(record)!=row["visual_review_sha"]):
                raise ValueError
        except (KeyError,TypeError,ValueError):
            raise LiveGateError("DUAL_VISUAL_REVIEW_BINDING_INVALID") from None
        return row["visual_review_sha"]

    @staticmethod
    def _live_dual_visual_record(job,checks,attempt,*,reviewer_role,reviewed_utc):
        if reviewer_role not in ("admin","evaluator"):
            raise LiveGateError("LIVE_DUAL_REVIEWER_ROLE_REQUIRED")
        try:
            timestamp=datetime.fromisoformat(reviewed_utc)
            if (timestamp.tzinfo!=timezone.utc or timestamp.isoformat()!=reviewed_utc):
                raise ValueError
        except (ValueError,TypeError):
            raise LiveGateError("LIVE_DUAL_REVIEW_TIMESTAMP_INVALID") from None
        mode=json.loads(job["input_json"])["generation_mode"]
        required={"product_matches","label_matches","cta_policy_matches"}
        if mode=="freeform":
            required.add("no_extra_text")
        expected_keys=required|({"observed_copy"} if mode=="freeform" else set())
        if (not isinstance(checks,dict) or set(checks)!=expected_keys or
            any(checks[field] is not True for field in required) or
            (mode=="freeform" and checks["observed_copy"]!=json.loads(job["copy_json"])["ad_copy"])):
            raise LiveGateError("LIVE_DUAL_VISUAL_REVIEW_REQUIRED")
        return {"source":"LIVE_DUAL_MANUAL_ATTESTATION","actor":job["actor"],
                "reviewer_role":reviewer_role,"reviewed_utc":reviewed_utc,
                "job_id":job["job_id"],"mode":mode,"image_sha":job["image_sha"],
                "copy_sha":job["copy_sha"],"approval_sha":job["approval_sha"],
                "candidate_receipt_sha":attempt["candidate_receipt_sha"],"checks":checks}

    @staticmethod
    def _live_dual_candidate(c,job):
        attempt=c.execute("""SELECT * FROM live_image_attempts WHERE job_id=?
            ORDER BY attempt_version DESC LIMIT 1""",(job["job_id"],)).fetchone()
        if (attempt is None or not attempt["candidate_receipt_sha"] or not attempt["provider_attempt_id"] or
            attempt["candidate_sha"]!=job["image_sha"] or attempt["actor"]!=job["actor"] or
            attempt["approval_sha"]!=job["approval_sha"] or
            attempt["prompt_sha"]!=digest(json.loads(job["prompt_json"]))):
            raise LiveGateError("LIVE_DUAL_CANDIDATE_BINDING_INVALID")
        return attempt

    def _live_dual_artifact_binding(self,c,job,group):
        attempt=self._live_dual_candidate(c,job)
        visual=c.execute("""SELECT record_json,record_sha FROM live_paid_dual_visual_reviews
            WHERE job_id=?""",(job["job_id"],)).fetchone()
        try:
            record=json.loads(visual["record_json"])
            expected=self._live_dual_visual_record(
                job,record["checks"],attempt,reviewer_role=record["reviewer_role"],
                reviewed_utc=record["reviewed_utc"])
            if (record!=expected or
                digest(record)!=visual["record_sha"] or not group["prompt_sha"]):
                raise ValueError
        except (KeyError,ValueError,TypeError):
            raise LiveGateError("LIVE_DUAL_VISUAL_BINDING_INVALID") from None
        return {"live_dual_authority_sha":group["authority_sha"],
                "live_dual_prompt_sha":group["prompt_sha"],
                "live_dual_visual_review_sha":visual["record_sha"],
                "owner_candidate_receipt_sha":attempt["candidate_receipt_sha"]}

    def select_live_dual_variant(self,actor,parent_id,mode,expected_final_sha):
        if mode not in ("composed","freeform"):
            raise LiveGateError("LIVE_DUAL_VARIANT_NOT_FOUND")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            group=self._live_dual_row(c,actor,parent_id)
            if not group or group["parent_job_id"]!=parent_id or not group["child_job_id"]:
                raise LiveGateError("LIVE_DUAL_GROUP_NOT_FOUND")
            variant_id=parent_id if mode=="composed" else group["child_job_id"]
            job=self._read(c,variant_id,actor)
            if job["state"]!="COMPLETED" or not job["final_sha"] or job["final_sha"]!=expected_final_sha:
                raise LiveGateError("LIVE_DUAL_SELECTION_STALE")
            self._approved(job,c,allow_completed=True)
            self._live_dual_artifact_binding(c,job,group)
            c.execute("""UPDATE live_paid_dual_groups SET preferred_mode=?,preferred_final_sha=?
                WHERE parent_job_id=?""",(mode,expected_final_sha,parent_id))
            self._event(c,job,"live_dual_variant_selected",job["state"],expected_final_sha)
            result=self._live_dual_group(c,actor,parent_id)
            c.commit()
            return result

    def reject_image(self,actor,job_id,expected_sha):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            job=self._read(c,job_id,actor)
            if job["state"]!="IMAGE_REVIEW_REQUIRED" or expected_sha!=job["image_sha"]:
                raise LiveGateError("IMAGE_REJECTION_STATE_CONFLICT")
            self._approved(job,c)
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
            self._approved(job,c)
            self._dual_visual_sha(c,job)
            live_group=self._live_dual_row(c,actor,job_id)
            if live_group is not None:
                self._live_dual_artifact_binding(c,job,live_group)
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
                if (policy["profile_id"].startswith("BP18_BETA_EDITORIAL_")
                    and json.loads(job["input_json"]).get("generation_mode","composed")=="composed"
                    and font_sha!=policy["safe_zone"]["required_font_sha"]):
                    raise LiveGateError("BETA_TYPOGRAPHY_FONT_SHA_MISMATCH")
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
        self._approved(job,connection)
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
        visual_sha=self._dual_visual_sha(connection,job)
        if visual_sha is not None:
            group=self._dual_row(connection,actor,job_id)
            envelope.update(dual_parent_job_id=group["parent_job_id"],
                            dual_source_approval_sha=group["approval_sha"],
                            dual_visual_review_sha=visual_sha)
        live_group=self._live_dual_row(connection,actor,job_id)
        if live_group is not None:
            binding=self._live_dual_artifact_binding(connection,job,live_group)
            if receipt.get("owner_candidate_receipt_sha")!=binding["owner_candidate_receipt_sha"]:
                raise LiveGateError("LIVE_DUAL_CANDIDATE_RECEIPT_CHANGED")
            envelope.update(binding)
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
                              'template_bp18_beta_editorial_ingress_v1',
                              'template_bp18_image_cta_ingress_v1',
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
                group=self._dual_row(c,actor,job_id)
                if group is not None:
                    self._assert_dual_binding(c,job,group)
                if (envelope.get("dual_parent_job_id")!=(group["parent_job_id"] if group else None) or
                    envelope.get("dual_source_approval_sha")!=(group["approval_sha"] if group else None) or
                    envelope.get("dual_visual_review_sha")!=self._dual_visual_sha(c,job)):
                    raise ValueError
                live_group=self._live_dual_row(c,actor,job_id)
                if live_group is not None:
                    self._assert_live_dual_binding(c,job,live_group)
                    binding=self._live_dual_artifact_binding(c,job,live_group)
                    if (any(envelope.get(key)!=value for key,value in binding.items()) or
                        receipt.get("owner_candidate_receipt_sha")!=binding["owner_candidate_receipt_sha"]):
                        raise ValueError
                elif "live_dual_authority_sha" in envelope:
                    raise ValueError
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
            self._approved(job,c)
            if self._dual_row(c,actor,job_id) or self._live_dual_row(c,actor,job_id):
                raise LiveGateError("DUAL_REQUIRES_COMPOSITION_RECEIPT")
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
