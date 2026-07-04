import asyncio
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from services import storage

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx",
    "jpg", "jpeg", "png", "tiff", "tif", "webp",
}

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def _detect_period(filenames: list[str]) -> str | None:
    """Best-effort: derive the YYYY-MM period from the uploaded filenames.

    Recognises forms like ``..._202601.pdf`` or ``..._2026-01.pdf``. Returns the
    most frequent match so the user does not have to pick the period manually.
    """
    counts: dict[str, int] = {}
    for name in filenames:
        for m in re.finditer(r"(20\d{2})[-_]?(0[1-9]|1[0-2])(?!\d)", name or ""):
            period = f"{m.group(1)}-{m.group(2)}"
            counts[period] = counts.get(period, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)   # drop control chars
    name = re.sub(r"[/\\]", "_", name)                   # no path separators
    name = name.lstrip("._")                              # no hidden-file prefix or traversal
    name = re.sub(r"[^\w\-. ]", "_", name)               # keep only safe chars
    name = re.sub(r"_+", "_", name).strip()
    return name[:200] or "file"


class UploadedFile(BaseModel):
    id: str
    filename: str
    sizeBytes: int
    uploadedAt: str


class UploadResponse(BaseModel):
    uploadId: str
    period: str
    files: list[UploadedFile]


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    period: str | None = Form(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files per upload")

    # Period: use the supplied value if valid, else auto-detect it from the
    # filenames, else fall back to the current month. The client no longer has
    # to ask the user to pick a period manually.
    if period:
        if not re.match(_PERIOD_PATTERN, period):
            # 422 preserves the prior validation contract (was a Form pattern check).
            raise HTTPException(status_code=422, detail="period must be in YYYY-MM format")
    else:
        period = (_detect_period([f.filename or "" for f in files])
                  or datetime.now(timezone.utc).strftime("%Y-%m"))

    upload_id = uuid.uuid4().hex
    uploaded: list[UploadedFile] = []

    for f in files:
        raw_name = f.filename or "file"
        ext = raw_name.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {raw_name} ({len(data) // (1024 * 1024)} MB). Maximum is 50 MB.",
            )

        safe_name = _sanitize_filename(raw_name)
        key = f"raw-docs/{period}/{upload_id}/{safe_name}"
        try:
            await asyncio.to_thread(storage.upload_file, key, data, f.content_type or "application/octet-stream")
        except Exception as exc:  # surface storage failures clearly, not as a bare 500
            logger.exception("Storage upload failed for key %s", key)
            raise HTTPException(
                status_code=502,
                detail=f"Storage upload failed for '{safe_name}': {type(exc).__name__}",
            ) from exc

        uploaded.append(UploadedFile(
            id=uuid.uuid4().hex,
            filename=safe_name,
            sizeBytes=len(data),
            uploadedAt=datetime.now(timezone.utc).isoformat(),
        ))

    # Write manifest so the extraction job knows what to process
    try:
        await asyncio.to_thread(
            storage.put_json,
            f"raw-docs/{period}/{upload_id}/manifest.json",
            {
                "uploadId": upload_id,
                "period": period,
                "files": [u.model_dump() for u in uploaded],
            },
        )
    except Exception as exc:
        logger.exception("Storage manifest write failed for upload %s", upload_id)
        raise HTTPException(
            status_code=502,
            detail=f"Storage manifest write failed: {type(exc).__name__}",
        ) from exc

    return UploadResponse(uploadId=upload_id, period=period, files=uploaded)
