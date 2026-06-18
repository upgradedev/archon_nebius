import re
import unicodedata
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from services import storage

router = APIRouter()

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx",
    "jpg", "jpeg", "png", "tiff", "tif", "webp",
}

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


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
    files: list[UploadedFile]


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    period: str = Form(..., pattern=_PERIOD_PATTERN),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files per upload")

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
        storage.upload_file(key, data, f.content_type or "application/octet-stream")

        uploaded.append(UploadedFile(
            id=uuid.uuid4().hex,
            filename=safe_name,
            sizeBytes=len(data),
            uploadedAt=datetime.now(timezone.utc).isoformat(),
        ))

    # Write manifest so the extraction job knows what to process
    storage.put_json(
        f"raw-docs/{period}/{upload_id}/manifest.json",
        {
            "uploadId": upload_id,
            "period": period,
            "files": [u.model_dump() for u in uploaded],
        },
    )

    return UploadResponse(uploadId=upload_id, files=uploaded)
