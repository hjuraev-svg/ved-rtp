"""Provider adapters for the single Gmail mailbox and Telegram Bot.

This module intentionally keeps credentials out of source code and API
responses. Gmail's refresh token is encrypted with Fernet before it reaches
PostgreSQL; the Telegram bot token stays in the server environment only.
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import CommunicationMessage, Deal, IntegrationConnection, Supplier

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def _fernet() -> Fernet:
    if not settings.integration_encryption_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "INTEGRATION_ENCRYPTION_KEY sozlanmagan. Avval .env faylini to‘ldiring.",
        )
    try:
        return Fernet(settings.integration_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "INTEGRATION_ENCRYPTION_KEY noto‘g‘ri. U Fernet kaliti bo‘lishi kerak.",
        ) from exc


def encrypt_token(payload: dict) -> str:
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def decrypt_token(value: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Saqlangan Gmail tokenini o‘qib bo‘lmadi. Gmail’ni qayta ulang.") from exc


async def connection(db: AsyncSession, provider: str) -> IntegrationConnection:
    row = (await db.execute(select(IntegrationConnection).where(IntegrationConnection.provider == provider))).scalar_one_or_none()
    if row is None:
        row = IntegrationConnection(provider=provider)
        db.add(row)
        await db.flush()
    return row


def gmail_redirect_uri() -> str:
    return settings.gmail_redirect_uri or f"{settings.public_base_url.rstrip('/')}/api/integrations/gmail/callback"


def gmail_flow(state: str | None = None) -> Flow:
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "GMAIL_CLIENT_ID va GMAIL_CLIENT_SECRET .env ichida sozlanmagan.",
        )
    client_config = {
        "web": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [gmail_redirect_uri()],
        }
    }
    return Flow.from_client_config(client_config, scopes=GMAIL_SCOPES, state=state, redirect_uri=gmail_redirect_uri())


async def gmail_authorization_url(db: AsyncSession) -> str:
    row = await connection(db, "gmail")
    state = secrets.token_urlsafe(32)
    row.config = {**(row.config or {}), "oauth_state": state}
    row.status = "authorizing"
    row.last_error = ""
    await db.commit()
    flow = gmail_flow(state)
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return url


async def complete_gmail_authorization(db: AsyncSession, code: str, state: str) -> str:
    row = await connection(db, "gmail")
    if not state or state != (row.config or {}).get("oauth_state"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gmail OAuth holati yaroqsiz yoki muddati tugagan.")
    flow = gmail_flow(state)
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        from googleapiclient.discovery import build

        profile = build("gmail", "v1", credentials=credentials, cache_discovery=False).users().getProfile(userId="me").execute()
    except Exception as exc:
        row.status = "error"
        row.last_error = str(exc)[:1000]
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Gmail ulanishi tasdiqlanmadi.") from exc

    token = json.loads(credentials.to_json())
    config = dict(row.config or {})
    config.pop("oauth_state", None)
    config["email"] = profile.get("emailAddress", "")
    config["history_id"] = profile.get("historyId", "")
    row.config = config
    row.encrypted_token = encrypt_token(token)
    row.status = "connected"
    row.last_error = ""
    await db.commit()
    return config["email"]


async def gmail_credentials(db: AsyncSession) -> tuple[IntegrationConnection, Credentials]:
    row = await connection(db, "gmail")
    if row.status != "connected" or not row.encrypted_token:
        raise HTTPException(status.HTTP_409_CONFLICT, "Gmail hali ulanmagan.")
    data = decrypt_token(row.encrypted_token)
    credentials = Credentials.from_authorized_user_info(data, GMAIL_SCOPES)
    if not credentials.valid:
        if not credentials.refresh_token:
            raise HTTPException(status.HTTP_409_CONFLICT, "Gmail refresh tokeni yo‘q. Gmail’ni qayta ulang.")
        try:
            credentials.refresh(Request())
        except Exception as exc:
            row.status = "error"
            row.last_error = str(exc)[:1000]
            await db.commit()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Gmail tokenini yangilab bo‘lmadi.") from exc
        row.encrypted_token = encrypt_token(json.loads(credentials.to_json()))
        await db.commit()
    return row, credentials


def _gmail_service(credentials: Credentials):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _header(headers: list[dict], name: str) -> str:
    wanted = name.lower()
    return next((item.get("value", "") for item in headers if item.get("name", "").lower() == wanted), "")


def _plain_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}).get("data")
    if body and mime_type.startswith("text/plain"):
        return base64.urlsafe_b64decode(body + "===").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        found = _plain_body(part)
        if found:
            return found
    return ""


async def deal_for_email(db: AsyncSession, email: str) -> int | None:
    address = parseaddr(email)[1].lower()
    if not address:
        return None
    stmt = (
        select(Deal.id)
        .join(Supplier, Deal.supplier_id == Supplier.id)
        .where(Supplier.email.ilike(address), Deal.status.in_(["active", "on_hold"]))
        .order_by(Deal.updated_at.desc())
    )
    return (await db.execute(stmt)).scalars().first()


async def store_message(db: AsyncSession, *, provider: str, external_id: str, direction: str, sender: str, recipients: list[str], subject: str, body: str, deal_id: int | None, message_status: str, sent_at: datetime | None = None, received_at: datetime | None = None, metadata: dict | None = None) -> CommunicationMessage:
    existing = (await db.execute(select(CommunicationMessage).where(CommunicationMessage.provider == provider, CommunicationMessage.external_id == external_id))).scalar_one_or_none()
    if existing:
        return existing
    row = CommunicationMessage(
        provider=provider, external_id=external_id, direction=direction, sender=sender,
        recipients=recipients, subject=subject[:500], body=body, deal_id=deal_id,
        status=message_status, sent_at=sent_at, received_at=received_at,
        metadata_json=metadata or {},
    )
    db.add(row)
    await db.flush()
    return row


async def send_gmail(db: AsyncSession, *, deal: Deal, to: str, subject: str, body: str) -> CommunicationMessage:
    row, credentials = await gmail_credentials(db)
    message = EmailMessage()
    message["To"] = to
    message["From"] = (row.config or {}).get("email", "me")
    message["Subject"] = subject or f"{deal.code}: {deal.title}"
    message["X-VED-Deal"] = str(deal.id)
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        result = _gmail_service(credentials).users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as exc:
        row.last_error = str(exc)[:1000]
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Gmail xabari yuborilmadi.") from exc
    stored = await store_message(
        db, provider="gmail", external_id=result["id"], direction="outgoing", sender=message["From"],
        recipients=[to], subject=message["Subject"], body=body, deal_id=deal.id,
        message_status="sent", sent_at=now(), metadata={"thread_id": result.get("threadId", "")},
    )
    await db.commit()
    return stored


async def sync_gmail(db: AsyncSession, limit: int = 50) -> int:
    row, credentials = await gmail_credentials(db)
    try:
        service = _gmail_service(credentials)
        listing = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=limit).execute()
        count = 0
        for item in listing.get("messages", []):
            external_id = item["id"]
            already = (await db.execute(select(CommunicationMessage.id).where(CommunicationMessage.provider == "gmail", CommunicationMessage.external_id == external_id))).scalar_one_or_none()
            if already:
                continue
            raw = service.users().messages().get(userId="me", id=external_id, format="full").execute()
            headers = raw.get("payload", {}).get("headers", [])
            sender = _header(headers, "From")
            recipients = [value for value in [_header(headers, "To"), _header(headers, "Cc")] if value]
            deal_header = _header(headers, "X-VED-Deal")
            deal_id = int(deal_header) if deal_header.isdigit() else await deal_for_email(db, sender)
            await store_message(
                db, provider="gmail", external_id=external_id, direction="incoming", sender=sender,
                recipients=recipients, subject=_header(headers, "Subject"), body=_plain_body(raw.get("payload", {})),
                deal_id=deal_id, message_status="received", received_at=now(),
                metadata={"thread_id": raw.get("threadId", ""), "snippet": raw.get("snippet", "")},
            )
            count += 1
        row.last_synced_at = now()
        row.last_error = ""
        await db.commit()
        return count
    except HTTPException:
        raise
    except Exception as exc:
        row.status = "error"
        row.last_error = str(exc)[:1000]
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Gmail inbox sinxronlanmadi.") from exc


async def send_telegram(db: AsyncSession, *, deal: Deal, chat_id: str, body: str) -> CommunicationMessage:
    if not settings.telegram_bot_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "TELEGRAM_BOT_TOKEN .env ichida sozlanmagan.")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": body})
            data = response.json()
        if not response.is_success or not data.get("ok"):
            raise ValueError(data.get("description", "Telegram API xatosi"))
    except Exception as exc:
        row = await connection(db, "telegram")
        row.status = "error"
        row.last_error = str(exc)[:1000]
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Telegram xabari yuborilmadi.") from exc
    result = data["result"]
    row = await connection(db, "telegram")
    row.status = "connected"
    row.config = {**(row.config or {}), "bot_username": (row.config or {}).get("bot_username", "")}
    stored = await store_message(
        db, provider="telegram", external_id=f"{chat_id}:{result['message_id']}", direction="outgoing", sender="bot",
        recipients=[str(chat_id)], subject="", body=body, deal_id=deal.id, message_status="sent", sent_at=now(),
        metadata={"chat_id": str(chat_id)},
    )
    await db.commit()
    return stored


async def telegram_status(db: AsyncSession) -> dict:
    row = await connection(db, "telegram")
    configured = bool(settings.telegram_bot_token)
    if not configured:
        return {"configured": False, "status": row.status, "bot_username": "", "error": row.last_error}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe")
            data = response.json()
        if not response.is_success or not data.get("ok"):
            raise ValueError(data.get("description", "Telegram API xatosi"))
        bot = data["result"]
        webhook_url = ""
        if settings.public_base_url.startswith("https://") and settings.telegram_webhook_secret:
            webhook_url = f"{settings.public_base_url.rstrip('/')}/api/integrations/telegram/webhook/{settings.telegram_webhook_secret}"
            async with httpx.AsyncClient(timeout=12) as client:
                hook = await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                    json={"url": webhook_url, "secret_token": settings.telegram_webhook_secret, "allowed_updates": ["message", "edited_message"]},
                )
                hook_data = hook.json()
            if not hook.is_success or not hook_data.get("ok"):
                raise ValueError(hook_data.get("description", "Telegram webhook xatosi"))
        row.status = "connected"
        row.config = {**(row.config or {}), "bot_username": bot.get("username", ""), "bot_name": bot.get("first_name", ""), "webhook_url": webhook_url}
        row.last_error = ""
        await db.commit()
    except Exception as exc:
        row.status = "error"
        row.last_error = str(exc)[:1000]
        await db.commit()
    return {"configured": configured, "status": row.status, "bot_username": (row.config or {}).get("bot_username", ""), "error": row.last_error}


async def receive_telegram_update(db: AsyncSession, update: dict) -> CommunicationMessage | None:
    message = update.get("message") or update.get("edited_message")
    if not message or not message.get("text"):
        return None
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return None
    sender_obj = message.get("from", {})
    sender = " ".join(filter(None, [sender_obj.get("first_name", ""), sender_obj.get("last_name", "")])) or sender_obj.get("username", "")
    supplier = (await db.execute(select(Supplier).where(Supplier.telegram_chat_id == chat_id))).scalar_one_or_none()
    deal_id = None
    if supplier:
        deal_id = (await db.execute(select(Deal.id).where(Deal.supplier_id == supplier.id, Deal.status.in_(["active", "on_hold"])).order_by(Deal.updated_at.desc()))).scalars().first()
    row = await store_message(
        db, provider="telegram", external_id=f"{chat_id}:{message['message_id']}", direction="incoming", sender=sender,
        recipients=[chat_id], subject="", body=message["text"], deal_id=deal_id, message_status="received",
        received_at=now(), metadata={"chat_id": chat_id, "update_id": update.get("update_id")},
    )
    await db.commit()
    return row
