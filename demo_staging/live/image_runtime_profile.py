"""Single source for image model configuration read by Worker AND cost UI.
No client import, credentials, network or charge. Invalid profiles fail closed.
"""
from __future__ import annotations
import os
from src.image_generation.contracts import resolve_image_complexity
from .contracts import LiveGateError

ALLOWED_MODELS=frozenset({
 "gpt-image-2.6-sunburst",
 "gpt-image-2.5-sunburst-2026-09-08",
 "gpt-image-2-2026-04-21",
})

def effective_image_profile() -> dict[str,str|None]:
    model=os.environ.get("IT_TEM_IMAGE_MODEL","gpt-image-2.6-sunburst")
    quality=os.environ.get("IT_TEM_IMAGE_QUALITY","medium")
    complexity=os.environ.get("IT_TEM_IMAGE_COMPLEXITY") or None
    if model not in ALLOWED_MODELS:raise LiveGateError("UNAPPROVED_IMAGE_MODEL")
    if quality not in ("low","medium","high"):raise LiveGateError("UNAPPROVED_IMAGE_QUALITY")
    try:effective=resolve_image_complexity(model,complexity)
    except ValueError:
        raise LiveGateError("UNAPPROVED_IMAGE_COMPLEXITY") from None
    return {"model":model,"quality":quality,"complexity":effective}
