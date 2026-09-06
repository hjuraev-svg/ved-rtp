import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..models import DealDocument, User
from ..realtime import hub
from ..security import can_edit, current_user

router = APIRouter(prefix="/api/deals", tags=["files"])

_SAFE = re.compile(r"[^A-Za-z0-9А-Яа-яЁё._-]+")
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".zip", ".rar", ".txt"}


def _safe_name(name: str) -> str:
    base = os.path.basename(name or "file")
    cleaned = _SAFE.sub("_", base).strip("._") or "file"
    return cleaned[:120]


@router.post("/{deal_id}/documents/{doc_id}/file")
async def upload_document_file(
    deal_id: int,
    doc_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    row = await db.get(DealDocument, doc_id)
    if not row or row.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")

    original = _safe_name(file.filename or "file")
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Тип файла {ext or '—'} не разрешён",
        )

    deal_dir = os.path.join(settings.upload_dir, str(deal_id))
    os.makedirs(deal_dir, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(deal_dir, stored)

    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    with open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                out.close()
                os.remove(path)
                raise HTTPException(413, f"Файл больше {settings.max_upload_mb} МБ")
            out.write(chunk)

    # Replace any previously attached file.
    if row.file_path and os.path.isfile(row.file_path) and row.file_path != path:
        try:
            os.remove(row.file_path)
        except OSError:
            pass

    row.file_name = original
    row.file_path = path
    if not row.is_received:
        row.is_received = True
        row.received_at = datetime.now(timezone.utc).date()

    await db.commit()
    await hub.broadcast("document.updated", {"deal_id": deal_id})
    return {"ok": True, "file_name": original, "size": written}


@router.get("/{deal_id}/documents/{doc_id}/file")
async def download_document_file(
    deal_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    row = await db.get(DealDocument, doc_id)
    if not row or row.deal_id != deal_id or not row.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    if not os.path.isfile(row.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл отсутствует на диске")
    return FileResponse(row.file_path, filename=row.file_name or "document")


@router.delete("/{deal_id}/documents/{doc_id}/file", status_code=204)
async def delete_document_file(
    deal_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    row = await db.get(DealDocument, doc_id)
    if not row or row.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    if row.file_path and os.path.isfile(row.file_path):
        try:
            os.remove(row.file_path)
        except OSError:
            pass
    row.file_name = ""
    row.file_path = ""
    await db.commit()
    await hub.broadcast("document.updated", {"deal_id": deal_id})
