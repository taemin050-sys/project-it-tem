from pathlib import Path

from fastapi import FastAPI

from .job_api import router as jobs_router
from .job_store import JobStore

def create_app(storage_root: Path | None = None) -> FastAPI:
    """Construct a testable app with an isolated, persistent local job store."""
    application = FastAPI(
        title="IT-TEM Backend API",
        description="Cosmetics Instagram Ad Generation Service",
        version="0.1.0",
    )
    root = storage_root or Path(__file__).resolve().parents[2] / ".runtime" / "jobs"
    application.state.job_store = JobStore(root)
    application.include_router(jobs_router)

    @application.get("/health", tags=["System"])
    def health_check():
        return {
            "status": "ok",
            "service": "it-tem-backend",
            "version": "0.1.0",
        }

    return application


app = create_app()
