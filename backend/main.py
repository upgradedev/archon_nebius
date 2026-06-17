from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from auth import verify_firebase_token
from routers import upload, jobs, analysis, periods


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


settings = Settings()

app = FastAPI(
    title="Archon API",
    description="Orchestration backend for the Archon financial intelligence platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth = [Depends(verify_firebase_token)]
app.include_router(upload.router, prefix="/api", dependencies=_auth)
app.include_router(jobs.router, prefix="/api", dependencies=_auth)
app.include_router(analysis.router, prefix="/api", dependencies=_auth)
app.include_router(periods.router, prefix="/api", dependencies=_auth)


@app.get("/health")
def health():
    return {"status": "ok", "service": "archon-backend"}
