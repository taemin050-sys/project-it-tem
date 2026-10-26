from fastapi import FastAPI

app = FastAPI(
    title="IT-TEM Backend API",
    description="Cosmetics Instagram Ad Generation Service",
    version="0.1.0",
)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "it-tem-backend",
        "version": "0.1.0",
    }
