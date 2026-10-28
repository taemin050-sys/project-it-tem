"""BeautyAI image MVP, extracted from beauty-ai-models 93faaa8.

Python >= 3.11; dependencies: pydantic>=2.7,<3, httpx>=0.27,<1, Pillow>=10.
Import from src.image_generation at repository root, or image_generation with
PYTHONPATH=src. No API call or environment lookup occurs on import.

Serving owns authentication, approval, JobStore and the shared team budget.
Construct LocalAssetStore / ProviderAttemptStore with stable private paths,
then inject OpenAIImagesAdapter into ExternalImageProcessor and pass it to
BackendImageAdapter. Live calls are disabled by default; inject credentials
and an approved budget explicitly. Never store runtime files inside src/.

Call generate(BackendImageInput(...), project_id=server_resolved_uuid).
The result is a generated image candidate for user review, not a final ad.
resize_ad_png creates a separate 1080x1350 PNG; it does not compose Korean copy.
Final Korean composition and serving E2E are not implemented by this package.
The source project's historical English/experiment request databases are not
migrated; use a separate persistent runtime directory for this MVP package.
"""
from .ad_resize import resize_ad_png
from .backend_adapter import BackendGeneratedImage, BackendImageAdapter, BackendImageInput
from .contracts import ExternalImageRequest, ImagePrompt
from .product_analysis import ProductAnalysis, ProductAnalysisResult

__all__ = ["BackendGeneratedImage", "BackendImageAdapter", "BackendImageInput",
           "ExternalImageRequest", "ImagePrompt", "ProductAnalysis",
           "ProductAnalysisResult", "resize_ad_png"]
