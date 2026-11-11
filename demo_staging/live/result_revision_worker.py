"""Coordinate explicit correction queues under the existing paid Worker lock.

Recover BOTH namespaces before choosing any new work. An uncertain send in one
namespace must also stop the other and the ordinary Dual queue.
"""
from .image_correction import run_image_correction_once
from .composed_copy_edit import run_composed_copy_edit_once


def run_result_revision_once(flow):
    hooks = ((run_image_correction_once, "NO_IMAGE_CORRECTION_TASK"),
             (run_composed_copy_edit_once, "NO_COMPOSED_COPY_EDIT"))
    held = None
    for hook, empty in hooks:
        result = hook(flow, recover_only=True)
        if result != empty:
            held = result
    if held:
        return held
    for hook, empty in hooks:
        result = hook(flow)
        if result != empty:
            return result
    return "NO_RESULT_REVISION_TASK"
