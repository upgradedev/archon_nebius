import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from auth import verify_firebase_token
from routers import upload, jobs, analysis, periods
from services import nebius as nebius_service

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run sync SDK call in a thread so it doesn't conflict with the running event loop
    result = await asyncio.to_thread(nebius_service.check_nebius_permissions)
    if result.get("ok"):
        logger.info("Nebius SDK check: OK (backend=%s)", result.get("backend", "nebius"))
    else:
        logger.error("Nebius SDK check FAILED — jobs will return 500: %s", result.get("error"))
    yield


app = FastAPI(
    lifespan=lifespan,
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
