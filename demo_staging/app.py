"""Isolated IT-TEM remote-demo staging, NOT approved canonical HTTP contract.

B0 API is unchanged. Demo-only routes are expressly provisional.
Cloudflare OTP is an OUTER gate, never a substitute for this app's job ACL.
Run one worker on a private loopback socket. Mock only, no provider imports.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.serving.main import create_app as create_b0_app
from src.serving.job_store import get_mock_artifact

_ID = re.compile(r"^[0-9a-f]{32}$")
_STEP = re.compile(r"^/api/v1/jobs(?:/([0-9a-f]{32})(?:/(.*))?)?$")
_CATEGORIES = {
    "product_recognition", "plan_copy_compliance", "image_fidelity",
    "final_layout_korean", "speed_reliability", "ui_ux",
}
_COOKIE = "__Host-ittem_demo"
_NOW = lambda: datetime.now(timezone.utc).isoformat()


class DemoLedger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init()

    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS invites (
                    actor TEXT PRIMARY KEY, secret_digest TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('evaluator','admin'))
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, actor TEXT NOT NULL,
                    expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL, actor TEXT NOT NULL,
                    step TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'MOCK',
                    start_utc TEXT NOT NULL, end_utc TEXT NOT NULL,
                    duration_ms REAL NOT NULL, http_status INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    server_status TEXT, code_sha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
                    job_id TEXT NOT NULL, scenario_id TEXT NOT NULL,
                    category TEXT NOT NULL, score INTEGER NOT NULL,
                    needs_improvement INTEGER NOT NULL, comment TEXT NOT NULL,
                    artifact_sha256 TEXT, submitted_at TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('submit','update','cancel')),
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_failures (
                    digest TEXT NOT NULL, timestamp INTEGER NOT NULL
                );
            """)

    def register_invites(self, json_file: Path):
        # hashed only; neither PIN nor email is stored in the DB.
        invites = json.loads(json_file.read_text(encoding="utf-8"))
        with self.connect() as db:
            for actor, data in invites.items():
                if not re.fullmatch(r"[a-zA-Z0-9_-]{3,40}", actor):
                    raise ValueError("Invalid evaluator pseudonym")
                if data.get("role") not in {"admin", "evaluator"} or not re.fullmatch(r"[0-9a-f]{64}", data.get("digest", "")):
                    raise ValueError("Invite record invalid")
                db.execute("INSERT OR REPLACE INTO invites VALUES (?,?,?)",
                           (actor, data["digest"], data["role"]))

    def login(self, code: str):
        if not isinstance(code, str) or len(code) > 200:
            return None
        digest = hashlib.sha256(code.encode()).hexdigest()
        cutoff = int(time.time()) - 300
        with self.connect() as db:
            db.execute("DELETE FROM login_failures WHERE timestamp < ?", (cutoff,))
            recent = db.execute("SELECT COUNT(*) FROM login_failures").fetchone()[0]
            if recent >= 50:
                return None
            row = db.execute("SELECT actor,role FROM invites WHERE secret_digest=?", (digest,)).fetchone()
            if row:
                return row["actor"], row["role"]
            db.execute("INSERT INTO login_failures VALUES (?,?)", (digest, int(time.time())))
        return None

    def new_session(self, actor):
        raw = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?)",
                       (hashlib.sha256(raw.encode()).hexdigest(), actor, int(time.time())+8*3600))
        return raw

    def identity(self, cookie):
        if not cookie:
            return None
        digest = hashlib.sha256(cookie.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("""SELECT s.actor,i.role FROM sessions s
                JOIN invites i ON i.actor=s.actor WHERE s.digest=? AND s.expires>?""",
                (digest,int(time.time()))).fetchone()
        return (row["actor"],row["role"]) if row else None

    def logout(self, cookie):
        if cookie:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE digest=?",
                           (hashlib.sha256(cookie.encode()).hexdigest(),))

    def owns(self, actor, job_id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM jobs WHERE job_id=? AND actor=?",
                              (job_id,actor)).fetchone() is not None

    def claim(self, actor, job_id):
        if not _ID.fullmatch(job_id):
            raise ValueError("Invalid created job id")
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?)",(job_id,actor,_NOW()))

    def event(self, actor, job_id, step, start, elapsed, status, server_status, sha):
        if not job_id or not _ID.fullmatch(job_id):
            return
        with self.connect() as db:
            db.execute("""INSERT INTO steps(job_id,actor,step,mode,start_utc,end_utc,duration_ms,
                http_status,outcome,server_status,code_sha) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id,actor,step,"MOCK",start,_NOW(),round(elapsed,3),status,
                 "PASS" if 200<=status<300 else "ERROR",server_status,sha))

    def events(self, actor, job_id):
        with self.connect() as db:
            return [dict(x) for x in db.execute(
                "SELECT step,mode,start_utc,end_utc,duration_ms,http_status,outcome,server_status,code_sha FROM steps WHERE job_id=? AND actor=? ORDER BY id",
                (job_id,actor))]

    def review(self, actor, job_id, data, sha, action):
        with self.connect() as db:
            row = db.execute("""SELECT revision FROM reviews WHERE actor=? AND job_id=?
                AND scenario_id=? AND category=? ORDER BY id DESC LIMIT 1""",
                (actor,job_id,data.scenario_id,data.category)).fetchone()
            revision=(row["revision"]+1) if row else 1
            db.execute("""INSERT INTO reviews(actor,job_id,scenario_id,category,score,
                needs_improvement,comment,artifact_sha256,submitted_at,action,revision)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (actor,job_id,data.scenario_id,data.category,data.score,
                 int(data.needs_improvement),data.comment,sha,_NOW(),action,revision))
            return revision

    def reviews(self,actor,job_id):
        with self.connect() as db:
            return [dict(x) for x in db.execute("""SELECT scenario_id,category,score,
                needs_improvement,comment,artifact_sha256,submitted_at,action,revision
                FROM reviews WHERE actor=? AND job_id=? ORDER BY id""",(actor,job_id))]

    def admin_summary(self):
        with self.connect() as db:
            rows=[dict(x) for x in db.execute("""WITH latest AS (
              SELECT *, ROW_NUMBER() OVER(PARTITION BY actor,job_id,scenario_id,category ORDER BY id DESC) AS rn
              FROM reviews
            ) SELECT actor,scenario_id,category,score,needs_improvement,artifact_sha256
              FROM latest WHERE rn=1 AND action!='cancel' ORDER BY category,actor""")]
        return rows


    def timing_summary(self):
        # Per-step empirical distributions: report n with P50/P95.
        import math
        with self.connect() as db:
            rows=[dict(x) for x in db.execute(
                "SELECT step,duration_ms,http_status FROM steps ORDER BY id")]
        groups={}
        for item in rows:
            values=groups.setdefault(item["step"],[])
            values.append(item["duration_ms"])
        return {step:{"n":len(times),
                      "p50_ms":round(sorted(times)[math.ceil(.50*len(times))-1],1),
                      "p95_ms":round(sorted(times)[math.ceil(.95*len(times))-1],1)}
                for step,times in groups.items()}


class InviteLogin(BaseModel):
    invite_code: str = Field(min_length=20,max_length=200)


class ReviewBody(BaseModel):
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,40}$")
    category: str
    score: int = Field(ge=1,le=5)
    needs_improvement: bool = False
    comment: str = Field(default="",max_length=1800)


def make_demo_app(root: Path, invite_file: Path, frontend: Path,
                  *, secure_cookie: bool = True, code_sha: str = "UNPINNED"):
    root = Path(root)
    cookie_name=_COOKIE if secure_cookie else "ittem_demo_local"
    ledger=DemoLedger(root/"demo.sqlite3")
    ledger.register_invites(invite_file)
    app=create_b0_app(root/"jobs")
    app.state.demo_ledger=ledger
    app.state.demo_mode="MOCK_ONLY"
    app.state.demo_code_sha=code_sha

    @app.middleware("http")
    async def guarded(request: Request, call_next):
        path=request.url.path
        is_b0=path=="/api/v1/jobs" or path.startswith("/api/v1/jobs/")
        is_demo=path.startswith("/demo/api/")
        if not (is_b0 or is_demo):
            response=await call_next(request)
            response.headers["Cache-Control"]="no-store" if path=="/health" else "no-cache"
            return response
        identity=ledger.identity(request.cookies.get(cookie_name))
        is_login=path=="/demo/api/session" and request.method=="POST"
        if not is_login and not identity and not (path=="/demo/api/session" and request.method=="GET"):
            return JSONResponse({"detail":"Login required"},status_code=401,
                                headers={"Cache-Control":"no-store"})
        if request.method not in ("GET","HEAD","OPTIONS"):
            origin=request.headers.get("origin","")
            host=request.headers.get("host","")
            parsed=urlsplit(origin)
            valid_scheme={"https"} if secure_cookie else {"http","https"}
            if not (parsed.scheme in valid_scheme and parsed.netloc==host and
                    not parsed.path and not parsed.query and not parsed.fragment):
                return JSONResponse({"detail":"Origin verification failed"},status_code=403,
                                    headers={"Cache-Control":"no-store"})
        actor=identity[0] if identity else None
        job_id=None
        if is_b0:
            match=_STEP.fullmatch(path)
            if not match:
                return JSONResponse({"detail":"Not found"},status_code=404)
            job_id=match.group(1)
            if job_id and not ledger.owns(actor,job_id):
                return JSONResponse({"detail":"Not found"},status_code=404,
                                    headers={"Cache-Control":"no-store"})
        started=time.perf_counter()
        when=_NOW()
        response=await call_next(request)
        if is_b0 and not job_id and request.method=="POST" and response.status_code==201:
            # Capture the response without letting the new job ID escape before
            # the owner assignment is durably committed.
            chunks=[c async for c in response.body_iterator]
            data=b"".join(chunks)
            try:
                created_id=json.loads(data)["job_id"]
                ledger.claim(actor,created_id)
            except (ValueError,KeyError,TypeError,sqlite3.Error):
                return JSONResponse({"detail":"Job ownership commit failed"},status_code=503)
            job_id=created_id
            headers={k:v for k,v in response.headers.items() if k.lower() not in
                     {"content-length","transfer-encoding"}}
            response=Response(data,status_code=201,headers=headers,
                              media_type="application/json")
        if is_b0 and request.method=="POST" and actor and job_id:
            server_status=None
            try:
                server_status=app.state.job_store.get_job(job_id).get("status")
            except Exception:
                pass
            step="upload" if path=="/api/v1/jobs" else path.rsplit(f"/{job_id}/",1)[-1]
            ledger.event(actor,job_id,step,when,(time.perf_counter()-started)*1000,
                         response.status_code,server_status,code_sha)
        response.headers["Cache-Control"]="private, no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        return response

    @app.get("/demo/api/session")
    def session(request: Request):
        actor=ledger.identity(request.cookies.get(cookie_name))
        if not actor:
            return JSONResponse({"authenticated":False},status_code=401)
        return {"authenticated":True,"evaluator_id":actor[0],"role":actor[1],
                "mode":"MOCK","live_enabled":False}

    @app.post("/demo/api/session")
    def login(payload: InviteLogin):
        identity=ledger.login(payload.invite_code)
        if identity is None:
            raise HTTPException(status_code=401,detail="Invalid invitation or rate limit")
        raw=ledger.new_session(identity[0])
        response=JSONResponse({"authenticated":True,"evaluator_id":identity[0],
                               "role":identity[1],"mode":"MOCK","live_enabled":False})
        response.set_cookie(cookie_name,raw,max_age=8*3600,httponly=True,
                            secure=secure_cookie,samesite="lax",path="/")
        response.headers["Cache-Control"]="no-store"
        return response

    @app.delete("/demo/api/session")
    def logout(request: Request):
        ledger.logout(request.cookies.get(cookie_name))
        response=JSONResponse({"authenticated":False})
        response.delete_cookie(cookie_name,path="/",secure=secure_cookie,httponly=True,samesite="lax")
        return response

    def authorize(request,job_id):
        actor=ledger.identity(request.cookies.get(cookie_name))
        if not actor:
            raise HTTPException(401,"Login required")
        if not ledger.owns(actor[0],job_id):
            raise HTTPException(404,"Not found")
        return actor[0]

    @app.get("/demo/api/jobs/{job_id}/events")
    def get_events(job_id: str,request: Request):
        actor=authorize(request,job_id)
        return {"job_id":job_id,"mode":"MOCK","provider_elapsed_ms":None,
                "queue_wait_ms":None,"events":ledger.events(actor,job_id)}

    def final_hash(job_id):
        try:
            p,_=get_mock_artifact(app.state.job_store,job_id,"final")
            return hashlib.sha256(Path(p).read_bytes()).hexdigest()
        except Exception:
            return None

    @app.post("/demo/api/evaluations")
    def add_review(payload: ReviewBody,request: Request):
        actor=authorize(request,payload.job_id)
        if payload.category not in _CATEGORIES:
            raise HTTPException(422,"Unknown category")
        job=app.state.job_store.get_job(payload.job_id)
        if job.get("status")!="COMPLETED":
            raise HTTPException(409,"Job not yet completed")
        sha=final_hash(payload.job_id)
        revision=ledger.review(actor,payload.job_id,payload,sha,"submit" if not
                               any(x["category"]==payload.category and x["scenario_id"]==payload.scenario_id
                                   for x in ledger.reviews(actor,payload.job_id)) else "update")
        return {"saved":True,"revision":revision,"artifact_sha256":sha,"mode":"MOCK"}

    @app.get("/demo/api/jobs/{job_id}/evaluations")
    def get_reviews(job_id: str,request: Request):
        actor=authorize(request,job_id)
        return {"job_id":job_id,"reviews":ledger.reviews(actor,job_id)}

    @app.get("/demo/api/admin/evaluations")
    def admin_summary(request: Request):
        actor=ledger.identity(request.cookies.get(cookie_name))
        if not actor or actor[1]!="admin":
            raise HTTPException(403,"Admin only")
        rows=ledger.admin_summary()
        return {"mode":"MOCK","n":len(rows),"results":rows}

    @app.get("/demo/api/admin/timings")
    def admin_timings(request: Request):
        actor=ledger.identity(request.cookies.get(cookie_name))
        if not actor or actor[1]!="admin":
            raise HTTPException(403,"Admin only")
        return {"mode":"MOCK","units":"ms","provider_elapsed_ms":None,
                "queue_wait_ms":None,"stages":ledger.timing_summary()}

    @app.get("/demo/api/admin/evaluations.csv")
    def admin_csv(request: Request):
        actor=ledger.identity(request.cookies.get(cookie_name))
        if not actor or actor[1]!="admin":
            raise HTTPException(403,"Admin only")
        rows=ledger.admin_summary()
        buf=io.StringIO()
        writer=csv.DictWriter(buf,fieldnames=["actor","scenario_id","category","score",
                                              "needs_improvement","artifact_sha256"])
        writer.writeheader();writer.writerows(rows)
        return Response(buf.getvalue(),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":"attachment; filename=ittem-evaluation.csv",
                                 "Cache-Control":"no-store"})

    @app.get("/demo/api/capabilities")
    def capabilities():
        return {"mode":"MOCK","live_enabled":False,"replay_enabled":False,
                "provider_calls":0,"contract_status":"STAGING_PROVISIONAL"}

    frontend=Path(frontend)
    app.mount("/assets",StaticFiles(directory=frontend/"assets"),name="frontend-assets")
    @app.get("/{route:path}",include_in_schema=False)
    def spa(route: str):
        if route.startswith(("api/","demo/api/")) or "." in route:
            raise HTTPException(404,"Not found")
        response=FileResponse(frontend/"index.html",media_type="text/html")
        response.headers["Cache-Control"]="no-cache"
        return response
    return app
