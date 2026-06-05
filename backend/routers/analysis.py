import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ANALYSIS_ENDPOINT_URL = os.getenv("ANALYSIS_ENDPOINT_URL", "http://analysis:8001")


class AnalyzeRequest(BaseModel):
    period: str


@router.post("/analyze")
async def trigger_analysis(req: AnalyzeRequest):
    """Call the Nebius AI Endpoint (financial analysis agent)."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{ANALYSIS_ENDPOINT_URL}/analyze",
                json={"period": req.period},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Analysis endpoint error: {exc}") from exc


@router.get("/reports/{period}")
async def get_report(period: str):
    """Fetch a completed financial report for a period."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{ANALYSIS_ENDPOINT_URL}/reports/{period}",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Analysis endpoint error: {exc}") from exc
