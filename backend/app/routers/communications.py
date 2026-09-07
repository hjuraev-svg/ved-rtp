from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..integrations import (
    complete_gmail_authorization,
    connection,
    gmail_authorization_url,
    receive_telegram_update,
    send_gmail,
    send_telegram,
    sync_gmail,
    telegram_status,
)
from ..models import CommunicationMessage, Deal, IntegrationConnection, User
from ..realtime import hub
from ..schemas import CommunicationMessageOut, CommunicationSend, IntegrationOut
from ..security import can_edit, current_user, require_roles

router = APIRouter(prefix="/api", tags=["communications"])


def integration_out(row: IntegrationConnection, provider: str) -> IntegrationOut:
    config = row.config or {}
    return IntegrationOut(
        provider=provider, status=row.status, configured=bool(row.encrypted_token) if provider == "gmail" else bool(settings.telegram_bot_token),
        label=config.get("email", "") if provider == "gmail" else config.get("bot_username", ""),
        last_synced_at=row.last_synced_at, last_error=row.last_error,
    )


@router.get("/integrations", response_model=list[IntegrationOut])
async def integrations(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("admin"))):
    gmail = await connection(db, "gmail")
    telegram = await connection(db, "telegram")
    return [integration_out(gmail, "gmail"), integration_out(telegram, "telegram")]


@router.post("/integrations/gmail/authorize")
async def gmail_authorize(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return {"authorization_url": await gmail_authorization_url(db)}


@router.get("/integrations/gmail/callback", response_class=HTMLResponse)
async def gmail_callback(code: str = "", state: str = "", error: str = "", db: AsyncSession = Depends(get_db)):
    if error:
        return HTMLResponse("<h2>Gmail ulanmay qoldi</h2><p>Ruxsat berilmadi yoki xatolik yuz berdi.</p>", status_code=400)
    try:
        email = await complete_gmail_authorization(db, code, state)
    except HTTPException as exc:
        return HTMLResponse(f"<h2>Gmail ulanmay qoldi</h2><p>{exc.detail}</p>", status_code=exc.status_code)
    return HTMLResponse(f"<h2>Gmail ulandi</h2><p>{email} manzili VED RTP bilan xavfsiz bog‘landi. Bu oynani yopishingiz mumkin.</p>")


@router.post("/integrations/gmail/sync")
async def gmail_sync(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("admin")), limit: int = Query(50, ge=1, le=200)):
    imported = await sync_gmail(db, limit)
    if imported:
        await hub.broadcast("message.synced", {"provider": "gmail", "count": imported})
    return {"imported": imported}


@router.post("/integrations/telegram/test")
async def telegram_test(db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return await telegram_status(db)


@router.post("/integrations/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.telegram_webhook_secret or not secrets_compare(secret, settings.telegram_webhook_secret):
        raise HTTPException(status_code=404, detail="Not found")
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if header and not secrets_compare(header, settings.telegram_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")
    stored = await receive_telegram_update(db, await request.json())
    if stored:
        await hub.broadcast("message.received", {"deal_id": stored.deal_id, "provider": "telegram"})
    return {"ok": True}


def secrets_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)


@router.get("/deals/{deal_id}/messages", response_model=list[CommunicationMessageOut])
async def deal_messages(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    if not await db.get(Deal, deal_id):
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    return (await db.execute(select(CommunicationMessage).where(CommunicationMessage.deal_id == deal_id).order_by(CommunicationMessage.created_at.desc()))).scalars().all()


@router.post("/deals/{deal_id}/messages", response_model=CommunicationMessageOut, status_code=201)
async def send_message(deal_id: int, payload: CommunicationSend, db: AsyncSession = Depends(get_db), _: User = Depends(can_edit)):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if payload.provider == "gmail":
        recipient = payload.recipient or (deal.supplier.email if deal.supplier else "")
        if not recipient:
            raise HTTPException(status_code=422, detail="Gmail uchun qabul qiluvchi email manzilini kiriting.")
        stored = await send_gmail(db, deal=deal, to=recipient, subject=payload.subject, body=payload.body)
        await hub.broadcast("message.sent", {"deal_id": deal.id, "provider": "gmail"})
        return stored
    if payload.provider == "telegram":
        recipient = payload.recipient or (deal.supplier.telegram_chat_id if deal.supplier else "")
        if not recipient:
            raise HTTPException(status_code=422, detail="Telegram uchun supplier telegram_chat_id ni yoki chat ID ni kiriting.")
        stored = await send_telegram(db, deal=deal, chat_id=recipient, body=payload.body)
        await hub.broadcast("message.sent", {"deal_id": deal.id, "provider": "telegram"})
        return stored
    raise HTTPException(status_code=422, detail="Noma’lum aloqa kanali")
