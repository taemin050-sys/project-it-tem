"""BeautyAI image MVP, extracted from beauty-ai-models 93faaa8.

Python >= 3.11; dependencies: pydantic>=2.7,<3, httpx>=0.27,<1, Pillow>=10,
fonttools>=4,<5. Composition also needs a licensed Korean font installed on
the server; supply its trusted path explicitly. Font files are not bundled.
Import from src.image_generation at repository root, or image_generation with
PYTHONPATH=src. No API call or environment lookup occurs on import.

Serving owns authentication, approval, JobStore and the shared team budget.
Construct LocalAssetStore / ProviderAttemptStore with stable private paths,
then inject OpenAIImagesAdapter into ExternalImageProcessor and pass it to
BackendImageAdapter. Live calls are disabled by default; inject credentials
and an approved budget explicitly. Never store runtime files inside src/.

Call generate(BackendImageInput(...), project_id=server_resolved_uuid).
image_prompt accepts a Korean string, {"prompt": "..."}, or
{"concept": "...", "prompt": "...", "mood": ["..."]}. Optional concept/mood
are not invented. Korean input is preserved and fixed image policies appended.
copy_revision accepts an opaque nonblank string (up to 128 characters, no
control characters) or a legacy positive integer, without type coercion.
Use the SAME type/value for generation, approval snapshot and composition;
integer 1 and string "1" are different identities. Never cast revision labels.
The result is a generated image candidate for user review, not a final ad.
A matching saved success replays without a new provider call even when new
live calls are disabled. Failed/uncertain attempts are never automatically retried.
resize_ad_png defaults to a separate 1080x1350 PNG; it does not compose Korean copy.
After serving verifies approval, call compose_ad_png(CompositionInput(...),
font_path=server_font_path). Pass the approved image bytes/SHA-256, complete
AdCopyOutput snapshot/canonical hash, copy revision and explicit text regions.
It returns the selected canvas PNG and UTF-8 caption/hashtags without a model call.
Optional layout_selection supports feed 3:4/4:5 and reels/story 9:16. Use the
same selection for generation and make_placement_layout() during composition.
Omitting it preserves the historical 4:5 generation path. Placement coordinates
are targets; review actual product bounds before passing protected_regions.
Use make_a_template() for paired upper safe-zone / centered A layout settings.
Layout coordinates use the final canvas. Supply product protection regions
to prevent text overlap; absent regions require manual product/layout review.
The full copy hash includes plan, ad_copy, caption and hashtags. Hash matching
does not establish approval. Serving owns approved snapshots and downloads;
live serving E2E and human layout acceptance remain separate checks.
The source project's historical English/experiment request databases are not
migrated; use a separate persistent runtime directory for this MVP package.
"""
# Resolve public conveniences only when requested. Deterministic local renderers
# can import their modules without loading the Provider adapter dependency graph.
from importlib import import_module

_EXPORTS = {
    "make_a_template": "a_template", "resize_ad_png": "ad_resize",
    "BackendGeneratedImage": "backend_adapter", "BackendImageAdapter": "backend_adapter",
    "BackendImageInput": "backend_adapter", "ExternalImageRequest": "contracts",
    "ImagePrompt": "contracts", "LayoutSelection": "contracts",
    "ComposedAd": "composition", "CompositionInput": "composition",
    "CompositionLayout": "composition", "CompositionRect": "composition",
    "CompositionTextRegion": "composition", "compose_ad_png": "composition",
    "ProductAnalysis": "product_analysis", "ProductAnalysisResult": "product_analysis",
    "get_layout": "layout_profiles", "make_placement_layout": "layout_profiles",
    "export_candidate": "candidate_export",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
