"""B-only local-render schema compatibility evidence and startup guard.

Run the reviewed control copy with ``python -I -S``. Candidate Python is parsed
as data and never imported. This tool emits evidence/contracts; it does not
install them, migrate SQLite, start workers, or contact a Provider.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys


def _sibling(name, filenames):
    for filename in filenames:
        path = Path(__file__).absolute().with_name(filename)
        if path.is_file() and not path.is_symlink():
            module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(name, path))
            exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
            return module
    raise RuntimeError("DERIVED_TRUSTED_CONTROL_REQUIRED")


if __package__:
    from . import bp18_b5_release_prestart as _guard
else:
    _guard = _sibling("bp18_derived_trusted_guard", ("bp18_b5_release_prestart.py", "bp18_release_prestart.py"))

ReleaseUnsafe = _guard.ReleaseUnsafe
EXIT_DENY = _guard.EXIT_DENY
DERIVED_CONTRACT_FILE = "config/bp18_required_derived_contract.json"
DERIVED_PROTOCOL = "LOCAL_PROTECTED_RENDER_V1"
DERIVED_SCHEMA = "bp18-derived-store-v1"
ROLES = ("forward", "rollback")
SOURCE_FIELDS = {"release_sha", "tree_sha", "inventory_sha256", "protocol_sha256", "schema_sha256"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_MARKERS = {
    "demo_staging/live/derived_store.py": (b"LOCAL_PROTECTED_RENDER_V1", b"DERIVED_EVENT_IMMUTABLE"),
    "demo_staging/live/derived_assets.py": (b"class DerivedAssetRegistry",),
    "demo_staging/live/derived_approval.py": (b"current_derived_context", b"authority_policy_sha"),
    "demo_staging/live/derived_service.py": (b"renderer_fingerprints", b"USD_UNRECONCILED"),
    "demo_staging/live/derived_worker.py": (b"DERIVED_WORKER_CREDENTIALS_FORBIDDEN", b"renderer_fingerprints"),
    "demo_staging/live/derived_api.py": (b"IT_TEM_TAILNET_SSO_ONLY", b"DERIVED_ARTIFACT_STALE"),
    "src/image_generation/protected_recipe.py": (b"bp18-portable-render-recipe-v1",),
    "src/image_generation/protected_product.py": (b"freeform_protected_product_hybrid",),
    "src/image_generation/composition.py": (),
    "src/image_generation/typography.py": (),
    "src/image_generation/ad_resize.py": (),
}
TABLES = frozenset({"live_derived_recipe_admissions", "live_derived_renders", "live_derived_reviews"})


def _sha(document):
    return _guard.canonical_sha(document)


def _sql(value):
    return " ".join(value.strip().split()).lower()


def _file(root, relative):
    path = Path(root)
    for part in Path(relative).parts:
        if part in ("", ".", ".."):
            raise ReleaseUnsafe("DERIVED_CONTROL_PATH_INVALID")
        path /= part
        if path.is_symlink():
            raise ReleaseUnsafe("DERIVED_CONTROL_PATH_INVALID")
    return _guard._regular(path, trusted=True)


def _document(path):
    raw = _guard._regular(path, trusted=True)
    if raw.stat().st_size > 8*1024*1024:
        raise ReleaseUnsafe("DERIVED_CONTROL_DOCUMENT_LIMIT")
    try:
        return json.loads(raw.read_text(encoding="utf-8"), object_pairs_hook=_guard.unique_json_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ReleaseUnsafe("DERIVED_CONTROL_DOCUMENT_INVALID") from error


def schema_from_source(raw):
    """Extract only literal SQL and the reviewed immutable-trigger expression."""
    try:
        tree = ast.parse(raw)
        assignments = {node.targets[0].id: node.value for node in tree.body
                       if isinstance(node, ast.Assign) and len(node.targets) == 1
                       and isinstance(node.targets[0], ast.Name)}
        protocol = ast.literal_eval(assignments["LOCAL_RENDER_PROTOCOL"])
        version = ast.literal_eval(assignments["DERIVED_SCHEMA_VERSION"])
        table_node = assignments["_TABLES"]
        if not isinstance(table_node, ast.Dict):
            raise ValueError
        tables = {ast.literal_eval(assignments[key.id]) if isinstance(key, ast.Name) else ast.literal_eval(key): ast.literal_eval(value)
                  for key, value in zip(table_node.keys, table_node.values)}
        indexes = ast.literal_eval(assignments["_INDEXES"])
        trigger_expression = ast.parse('''{
 f"{table}_{operation.lower()}_denied": (
 f"CREATE TRIGGER {table}_{operation.lower()}_denied BEFORE {operation} ON {table} "
 "BEGIN SELECT RAISE(ABORT,'DERIVED_EVENT_IMMUTABLE'); END")
 for table in (ADMISSIONS, REVIEWS) for operation in ("UPDATE", "DELETE")
}''', mode="eval").body
        if (protocol != DERIVED_PROTOCOL or version != DERIVED_SCHEMA or set(tables) != TABLES
                or not isinstance(indexes, dict) or len(indexes) != 4
                or ast.dump(assignments["_TRIGGERS"], include_attributes=False) != ast.dump(trigger_expression, include_attributes=False)
                or ast.literal_eval(assignments["ADMISSIONS"]) != "live_derived_recipe_admissions"
                or ast.literal_eval(assignments["REVIEWS"]) != "live_derived_reviews"):
            raise ValueError
        triggers = {f"{table}_{operation.lower()}_denied":
            f"CREATE TRIGGER {table}_{operation.lower()}_denied BEFORE {operation} ON {table} "
            "BEGIN SELECT RAISE(ABORT,'DERIVED_EVENT_IMMUTABLE'); END"
            for table in ("live_derived_recipe_admissions", "live_derived_reviews") for operation in ("UPDATE", "DELETE")}
        objects = {}
        for kind, values in (("table", tables), ("index", indexes), ("trigger", triggers)):
            for name, sql in values.items():
                if not isinstance(name, str) or not name.startswith("live_derived_") or not isinstance(sql, str):
                    raise ValueError
                objects[name] = {"type": kind, "sql": _sql(sql)}
        return {"schema": version, "protocol": protocol, "objects": objects}
    except (SyntaxError, ValueError, TypeError, KeyError) as error:
        raise ReleaseUnsafe("DERIVED_SOURCE_SCHEMA_UNSUPPORTED") from error


def source_protocol(release):
    files = {}
    for name, markers in SOURCE_MARKERS.items():
        raw = _file(release, name).read_bytes()
        if any(marker not in raw for marker in markers):
            raise ReleaseUnsafe("DERIVED_REQUIRED_PROTOCOL_CODE_MISSING")
        files[name] = hashlib.sha256(raw).hexdigest()
    schema = schema_from_source(_file(release, "demo_staging/live/derived_store.py").read_bytes())
    value = {"required_mode": DERIVED_PROTOCOL, "schema_sha256": _sha(schema), "files": files}
    return value, schema


def _runtime_schema(root):
    path = Path(root) / "runtime/live/live.sqlite"
    if not path.exists():
        return None
    path = _file(root, "runtime/live/live.sqlite")
    try:
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=2) as c:
            c.execute("PRAGMA query_only=ON")
            records = c.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'live_derived_%' OR tbl_name LIKE 'live_derived_%'").fetchall()
        objects = {name: {"type": kind, "sql": _sql(sql)} for kind, name, table, sql in records if sql is not None}
        if not objects:
            return None
        if {name for name, obj in objects.items() if obj["type"] == "table"} != TABLES:
            raise ReleaseUnsafe("DERIVED_RUNTIME_SCHEMA_PARTIAL")
        return {"schema": DERIVED_SCHEMA, "protocol": DERIVED_PROTOCOL, "objects": objects}
    except (OSError, sqlite3.Error, AttributeError) as error:
        raise ReleaseUnsafe("DERIVED_RUNTIME_SCHEMA_UNREADABLE") from error


def required_derived_contract(root, target, *, activating=False):
    """A migrated schema requires a reviewed reader, even with zero derived rows."""
    root = Path(root)
    if not isinstance(target, str) or not _guard.SHA_RE.fullmatch(target):
        raise ReleaseUnsafe("DERIVED_RELEASE_TARGET_INVALID")
    path = root / DERIVED_CONTRACT_FILE
    actual_schema = _runtime_schema(root)
    if not activating and not path.exists() and actual_schema is None:
        return None
    try:
        document = _document(path)
        if (not isinstance(document, dict) or set(document) != {"version", "required_mode", "schema", "schema_sha256", "approval_reference", "verified_sources", "release_inventories"}
                or type(document["version"]) is not int or document["version"] != 1
                or document["required_mode"] != DERIVED_PROTOCOL
                or not isinstance(document["approval_reference"], str) or not document["approval_reference"].strip()
                or not isinstance(document["verified_sources"], dict) or len(document["verified_sources"]) != 2
                or set(document["verified_sources"]) != set(document["release_inventories"])
                or _sha(document["schema"]) != document["schema_sha256"]):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError, ReleaseUnsafe) as error:
        raise ReleaseUnsafe("DERIVED_REQUIRED_CONTRACT_INVALID") from error
    verified = document["verified_sources"].get(target)
    if verified is None:
        raise ReleaseUnsafe("DERIVED_INCOMPATIBLE_RELEASE_DENIED")
    release = root / "releases" / target
    try:
        protocol, schema = source_protocol(release)
    except (OSError, ReleaseUnsafe) as error:
        raise ReleaseUnsafe("DERIVED_SOURCE_PROVENANCE_INVALID") from error
    if verified != protocol or schema != document["schema"]:
        raise ReleaseUnsafe("DERIVED_SOURCE_PROVENANCE_INVALID")
    if actual_schema is None or actual_schema != schema:
        raise ReleaseUnsafe("DERIVED_RUNTIME_SCHEMA_INCOMPATIBLE")
    _guard.verify_release_inventory(release, document["release_inventories"][target], target)
    return document


def inspect_source(repo, root, release_sha, frontend_build=None):
    # Reuse the independently reviewed exact Git/whole-inventory checker.
    if __package__:
        from . import bp18_b5_dual_contract as dual
    else:
        dual = _sibling("bp18_derived_trusted_dual", ("bp18_b5_dual_contract.py",))
    record, _, inventory = dual._source_evidence(Path(repo), Path(root), release_sha, frontend_build)
    protocol, schema = source_protocol(Path(root)/"releases"/release_sha)
    record["protocol_sha256"] = _sha(protocol)
    record["schema_sha256"] = _sha(schema)
    return record, protocol, schema, inventory


def prepare_contract(repo, root, approval, builds=None):
    builds = builds or {}
    if (not isinstance(approval, dict) or set(approval) != {"version", "required_mode", "approval_reference", *ROLES}
            or type(approval["version"]) is not int or approval["version"] != 1
            or approval["required_mode"] != DERIVED_PROTOCOL
            or not isinstance(approval["approval_reference"], str) or not approval["approval_reference"].strip()
            or len(approval["approval_reference"]) > 200):
        raise ReleaseUnsafe("DERIVED_OPERATOR_APPROVAL_INVALID")
    evidence, protocols, schemas, inventories = {}, {}, {}, {}
    for role in ROLES:
        record = approval[role]
        if (not isinstance(record, dict) or set(record) != SOURCE_FIELDS
                or not _guard.SHA_RE.fullmatch(record["release_sha"])
                or not _guard.SHA_RE.fullmatch(record["tree_sha"])
                or any(not SHA256.fullmatch(record[key]) for key in SOURCE_FIELDS-{"release_sha", "tree_sha"})):
            raise ReleaseUnsafe("DERIVED_OPERATOR_APPROVAL_INVALID")
        sha = record["release_sha"]
        evidence[role], protocols[sha], schemas[sha], inventories[sha] = inspect_source(repo, root, sha, builds.get(sha))
        if evidence[role] != record:
            raise ReleaseUnsafe("DERIVED_APPROVED_SOURCE_EVIDENCE_MISMATCH")
    if len(protocols) != 2:
        raise ReleaseUnsafe("DERIVED_DISTINCT_SOURCE_PAIR_REQUIRED")
    if len({_sha(schema) for schema in schemas.values()}) != 1 or set(builds)-set(protocols):
        raise ReleaseUnsafe("DERIVED_SOURCE_PAIR_INCOMPATIBLE")
    schema = next(iter(schemas.values()))
    return {"version": 1, "required_mode": DERIVED_PROTOCOL, "schema": schema, "schema_sha256": _sha(schema),
            "approval_reference": approval["approval_reference"], "verified_sources": protocols, "release_inventories": inventories}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-repo", type=Path)
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--target", help="fixed production-root prestart target (no subcommand)")
    parser.add_argument("--activating", action="store_true")
    parser.add_argument("--frontend-build", type=Path, action="append", default=[])
    commands=parser.add_subparsers(dest="command")
    inspect=commands.add_parser("inspect")
    inspect.add_argument("--forward", required=True); inspect.add_argument("--rollback", required=True)
    prepare=commands.add_parser("prepare");prepare.add_argument("--approval", required=True, type=Path)
    verify=commands.add_parser("verify");verify.add_argument("--target", required=True)
    args=parser.parse_args(argv)
    try:
        if args.command is None:
            if not args.target or args.git_repo or args.staging_root or args.frontend_build:
                raise ReleaseUnsafe("DERIVED_FIXED_RUNTIME_ROOT_REQUIRED")
            required_derived_contract(_guard.PRODUCTION_ROOT,args.target,activating=args.activating)
            print("BP18_DERIVED_PRESTART_PASS release="+args.target)
            return 0
        if not args.git_repo or not args.staging_root or args.activating:
            raise ReleaseUnsafe("DERIVED_SOURCE_REVIEW_ARGUMENTS_REQUIRED")
        builds={}
        for path in args.frontend_build:
            value=_document(path)
            if not isinstance(value, dict) or value.get("release_sha") in builds:
                raise ReleaseUnsafe("DERIVED_FRONTEND_BUILD_INVALID")
            builds[value["release_sha"]]=value
        if args.command=="inspect":
            records={role:inspect_source(args.git_repo,args.staging_root,getattr(args,role),builds.get(getattr(args,role)))[0] for role in ROLES}
            output={"version":1,"required_mode":DERIVED_PROTOCOL,"evidence_only":True,**records}
        elif args.command=="prepare":
            output=prepare_contract(args.git_repo,args.staging_root,_document(args.approval),builds)
        else:
            required_derived_contract(args.staging_root,args.target,activating=True)
            print("BP18_DERIVED_CONTRACT_VERIFIED "+args.target);return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print("BP18_DERIVED_CONTRACT_DENIED:"+getattr(error,"code","DERIVED_CONTRACT_INPUT_INVALID"),file=sys.stderr)
        return EXIT_DENY
    print(json.dumps(output,sort_keys=True,indent=2));return 0


if __name__=="__main__":
    sys.exit(main())
