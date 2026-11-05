"""Owner 23 size-only bridge: placement and pixel geometry are internal.

New Jobs explicitly choose a final size; historical A v1 Jobs retain their
frozen original policy. Never accept client coordinates or a placement flag.
"""
from __future__ import annotations
from typing import Literal

from .contracts import LayoutSelection
from .layout_profiles import LAYOUT_VERSION, get_layout, make_placement_layout

SizeChoice=Literal["3:4","4:5","9:16"]
DEFAULT_PLACEMENT={"3:4":"feed","4:5":"feed","9:16":"reels"}

def resolve_size_choice(choice: SizeChoice):
    if type(choice) is not str or choice not in DEFAULT_PLACEMENT:
        raise ValueError("Unsupported final image ratio")
    selected=LayoutSelection(aspect_ratio=choice,placement=DEFAULT_PLACEMENT[choice])
    profile=get_layout(selected.aspect_ratio,selected.placement)
    return selected,profile

def size_composition_policy(choice: SizeChoice):
    """Server stores the result at ingress; no FE/Serving coordinate choices."""
    selected,profile=resolve_size_choice(choice)
    layout=make_placement_layout(selected.aspect_ratio,selected.placement)
    return {
        "profile_id":"OWNER_IMAGE_SIZE_"+choice.replace(":","_"),
        "profile_version":LAYOUT_VERSION,
        "selection":selected.model_dump(mode="json"),
        "native_size":list(profile.native),
        "final_size":list(profile.final),
        "layout":layout.model_dump(mode="json"),
    }
