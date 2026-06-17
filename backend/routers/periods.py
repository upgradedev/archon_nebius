from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import storage

router = APIRouter()


class CompanyProfile(BaseModel):
    company_name: str = ""
    company_tax_id: str = ""


@router.get("/periods")
def list_periods():
    """List periods derived from uploaded raw-docs, with extraction/report status."""
    raw_keys = storage.list_keys("raw-docs/")
    extracted_keys = storage.list_keys("extracted/")
    report_keys = storage.list_keys("reports/")

    def _period_set(keys: list[str], prefix: str) -> set[str]:
        periods: set[str] = set()
        for key in keys:
            # key = "{prefix}/{period}/..."
            rest = key[len(prefix):]
            segment = rest.split("/")[0]
            if segment:
                periods.add(segment)
        return periods

    raw_periods = _period_set(raw_keys, "raw-docs/")
    extracted_periods = _period_set(extracted_keys, "extracted/")
    report_periods = {
        k.split("/")[1]
        for k in report_keys
        if k.endswith("report.json") and len(k.split("/")) >= 3
    }

    all_periods = sorted(raw_periods | extracted_periods | report_periods, reverse=True)
    return [
        {
            "period": p,
            "hasReport": p in report_periods,
            "hasExtraction": p in extracted_periods,
        }
        for p in all_periods
    ]


@router.delete("/periods/{period}")
def delete_period(period: str):
    """Delete all Object Storage data for a period."""
    count = storage.delete_prefix(f"raw-docs/{period}/")
    count += storage.delete_prefix(f"extracted/{period}/")
    count += storage.delete_prefix(f"reports/{period}/")
    return {"deleted": count, "period": period}


@router.get("/documents/{period}")
def get_documents(period: str):
    """Return the extraction documents.json for a period."""
    try:
        return storage.download_json(f"extracted/{period}/documents.json")
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            raise HTTPException(
                status_code=404,
                detail=f"No extracted documents for period {period}",
            ) from exc
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/company-profile")
def get_company_profile():
    """Return company profile from Object Storage (empty object if not set yet)."""
    try:
        return storage.download_json("company/profile.json")
    except ClientError:
        return {"company_name": "", "company_tax_id": ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/company-profile")
def update_company_profile(profile: CompanyProfile):
    """Persist company profile to Object Storage."""
    try:
        storage.put_json("company/profile.json", profile.model_dump())
        return profile
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
