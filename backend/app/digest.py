"""Ежедневная сводка: что требует внимания сегодня.

Собирается из тех же данных, что и дашборд, и отправляется в Telegram, чтобы
система напоминала сама, а не ждала, пока кто-то откроет вкладку.

Отправка не роняет приложение: не настроен бот или не отвечает Telegram —
пишем в лог и живём дальше.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Deal, Payment, Permit, Supplier
from .services import OPEN_STATUSES, build_dashboard

log = logging.getLogger("ved.digest")

PERMIT_HORIZON_DAYS = 60
ARRIVAL_HORIZON_DAYS = 7


async def collect(db: AsyncSession) -> dict:
    today = date.today()

    # Красная зона по всем типам сделок сразу.
    red_total = 0
    alerts: list[dict] = []
    for pipeline in ("import", "local", "service", "export"):
        data = await build_dashboard(db, pipeline)
        red_total += data["kpi"]["overdue_deals"]
        alerts.extend(data["alerts"][:5])

    arriving = (
        await db.execute(
            select(Deal.code, Deal.title, Deal.eta, Supplier.name)
            .outerjoin(Supplier, Supplier.id == Deal.supplier_id)
            .where(
                Deal.status.in_(OPEN_STATUSES),
                Deal.eta.is_not(None),
                Deal.actual_arrival.is_(None),
                Deal.eta >= today,
                Deal.eta <= today + timedelta(days=ARRIVAL_HORIZON_DAYS),
            )
            .order_by(Deal.eta)
        )
    ).all()

    due = (
        await db.execute(
            select(Payment.amount, Payment.currency, Payment.due_date, Payment.direction, Deal.code)
            .join(Deal, Deal.id == Payment.deal_id)
            .where(
                Payment.status == "planned",
                Payment.due_date.is_not(None),
                Payment.due_date <= today + timedelta(days=ARRIVAL_HORIZON_DAYS),
                Deal.status.in_(OPEN_STATUSES),
            )
            .order_by(Payment.due_date)
        )
    ).all()

    permits = (
        await db.execute(
            select(Permit.name, Permit.valid_until)
            .where(
                Permit.is_active.is_(True),
                Permit.valid_until.is_not(None),
                Permit.valid_until <= today + timedelta(days=PERMIT_HORIZON_DAYS),
            )
            .order_by(Permit.valid_until)
        )
    ).all()

    return {
        "date": today,
        "red_zone": red_total,
        "alerts": alerts[:8],
        "arriving": [{"code": c, "title": t, "eta": e, "supplier": s or "—"} for c, t, e, s in arriving],
        "payments_due": [
            {"amount": a, "currency": cur, "due": d, "direction": dr, "code": code}
            for a, cur, d, dr, code in due
        ],
        "permits_expiring": [{"name": n, "until": u} for n, u in permits],
    }


def render(data: dict) -> str:
    """Короткий текст для Telegram. Пустые разделы не печатаются вовсе."""
    today = data["date"].strftime("%d.%m.%Y")
    lines = [f"<b>ВЭД · сводка на {today}</b>"]

    if data["red_zone"]:
        lines.append(f"\n🔴 <b>Красная зона: {data['red_zone']}</b>")
        for a in data["alerts"]:
            lines.append(f"  • {a['code']} — {a['detail']}")

    if data["arriving"]:
        lines.append(f"\n📦 <b>Прибывает за неделю: {len(data['arriving'])}</b>")
        for r in data["arriving"][:8]:
            lines.append(f"  • {r['eta'].strftime('%d.%m')} {r['code']} — {r['supplier']}")

    if data["payments_due"]:
        overdue = [p for p in data["payments_due"] if p["due"] < data["date"]]
        lines.append(f"\n💰 <b>Платежи: {len(data['payments_due'])}</b>"
                     + (f", просрочено {len(overdue)}" if overdue else ""))
        for p in data["payments_due"][:8]:
            mark = "‼️" if p["due"] < data["date"] else " "
            arrow = "←" if p["direction"] == "in" else "→"
            lines.append(f"  {mark} {p['due'].strftime('%d.%m')} {arrow} {p['amount']} {p['currency']} · {p['code']}")

    if data["permits_expiring"]:
        lines.append(f"\n📄 <b>Документы на исходе: {len(data['permits_expiring'])}</b>")
        for p in data["permits_expiring"][:6]:
            lines.append(f"  • до {p['until'].strftime('%d.%m.%Y')} — {p['name']}")

    if len(lines) == 1:
        lines.append("\nВсё спокойно: просрочек, платежей и истекающих документов нет.")

    lines.append(f"\n{settings.public_base_url.rstrip('/')}")
    return "\n".join(lines)


async def send(db: AsyncSession, chat_id: str = "") -> dict:
    """Собрать и отправить. Возвращает текст даже когда отправить некуда."""
    data = await collect(db)
    text = render(data)
    target = chat_id or settings.telegram_digest_chat_id

    if not settings.telegram_bot_token or not target:
        log.info("Дайджест собран, но не отправлен: не настроен бот или чат")
        return {"sent": False, "reason": "не настроен TELEGRAM_BOT_TOKEN или чат получателя", "text": text}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": target, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
        if r.status_code != 200:
            log.warning("Telegram отказал: %s %s", r.status_code, r.text[:200])
            return {"sent": False, "reason": f"Telegram: {r.status_code}", "text": text}
    except Exception as exc:  # сеть может лежать — сводка не повод падать
        log.warning("Дайджест не ушёл: %s", exc)
        return {"sent": False, "reason": str(exc)[:200], "text": text}

    return {"sent": True, "chat_id": target, "text": text}


def due_now(now: datetime | None = None) -> bool:
    """Час отправки задан в DIGEST_HOUR по времени TZ приложения."""
    now = now or datetime.now(timezone.utc) + timedelta(hours=5)  # Asia/Tashkent
    return now.hour == settings.digest_hour
