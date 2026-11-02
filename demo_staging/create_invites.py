"""Generate per-evaluator one-time onboarding secrets, never commit or print them.

Usage: python -m demo_staging.create_invites /secure/runtime/config admin:admin eval01:evaluator ...
Outputs 0600 sha256 invite registry and 0600 separately distributable invitation codes.
Codes MUST be delivered out of band, 1:1; do not post in logs/chat.
"""
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

def create(directory, actors):
    folder=Path(directory)
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    registry={}; plaintext={}
    for actor,role in actors:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{3,40}",actor) or role not in ("admin","evaluator"):
            raise ValueError("Invalid pseudonymous user or role")
        code=secrets.token_urlsafe(36)
        registry[actor]={"role":role,"digest":hashlib.sha256(code.encode()).hexdigest()}
        plaintext[actor]=code
    for filename,data in (("invites.sha256.json",registry),("invites.deliver-securely.json",plaintext)):
        path=folder/filename
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as output:
            json.dump(data,output,indent=2)
    return folder/"invites.sha256.json"

if __name__=="__main__":
    if len(sys.argv)<4: raise SystemExit("Expected directory and at least two actor:role pairs")
    users=[tuple(x.split(":",1)) for x in sys.argv[2:]]
    create(sys.argv[1],users)
    print("INVITE_REGISTRY_CREATED_WITH_SEPARATE_PRIVATE_CODE_FILE; NO_CODES_PRINTED")
