from pathlib import Path

from fastapi import FastAPI

from .job_api import router as jobs_router
from .job_store import JobStore
from .mock_workflow import router as mock_router

def create_app(storage_root: Path | None = None, *, enable_b1_fake_compliance: bool = False) -> FastAPI:
    """Construct a testable app with an isolated, persistent local job store."""
    application = FastAPI(
        title="IT-TEM Backend API",
        description="Cosmetics Instagram Ad Generation Service",
        version="0.1.0",
    )
    root = storage_root or Path(__file__).resolve().parents[2] / ".runtime" / "jobs"
    application.state.job_store = JobStore(root)
    if enable_b1_fake_compliance:
        # Deliberately opt-in for isolated local B1-R Fake tests. The normal
        # B0 app stays unchanged, with the same 11 OpenAPI operations.
        from .b1_fake_review import FakeComplianceGate
        application.state.b1_fake_gate = FakeComplianceGate(application.state.job_store)
        application.state.job_store._b1_observe_mutation = (
            application.state.b1_fake_gate.observe_transition
        )
    application.include_router(jobs_router)
    application.include_router(mock_router)

    @application.get("/health", tags=["System"])
    def health_check():
        return {
            "status": "ok",
            "service": "it-tem-backend",
            "version": "0.1.0",
        }

    return application


app = create_app()
