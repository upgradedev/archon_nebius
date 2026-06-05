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
    period: str = Form(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files per upload")

    upload_id = uuid.uuid4().hex
    uploaded: list[UploadedFile] = []

    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

        data = await f.read()
        key = f"raw-docs/{period}/{upload_id}/{f.filename}"
        storage.upload_file(key, data, f.content_type or "application/octet-stream")

        uploaded.append(UploadedFile(
            id=uuid.uuid4().hex,
            filename=f.filename or "unknown",
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
