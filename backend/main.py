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
        extra = "ignore"


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


# Public liveness probe reachable THROUGH the Firebase BFF (which only rewrites
# /api/** to the backend). The frontend cold-start recovery polls this to detect
# when the Nebius endpoint has finished cold-starting: while the endpoint is cold
# the BFF returns 502/503, and this returns 200 the moment it is warm. Kept
# unauthenticated (outside the _auth routers) so it is a pure liveness signal.
@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "archon-backend"}


def _db_health() -> dict:
    """Report live PostgreSQL reachability from THIS process (the backend Endpoint).

    Exists because the read-model mirror (services/pg_sync.py) is best-effort and
    silently no-ops when it cannot reach PG — which hid, for a long time, that the
    Endpoint could not connect at all (first: DATABASE_URL never injected; then: the
    public PG host blocked the Endpoint's egress). This turns that invisible
    condition into an explicit signal a deploy pipeline can gate on. Returns a
    reachable flag rather than raising, so it is a pure probe. No data is exposed.
    """
    try:
        from db.client import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return {"db": "ok", "reachable": True}
    except Exception as exc:
        return {"db": "unreachable", "reachable": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}


@app.get("/health/db")
def health_db():
    return _db_health()


@app.get("/api/health/db")
def api_health_db():
    return _db_health()
