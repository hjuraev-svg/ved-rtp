import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Deal, User
from ..reference import TRANSPORT_MODES
from ..security import current_user
from ..services import OPEN_STATUSES, bulk_progress, days_since, is_overdue

router = APIRouter(prefix="/api/export", tags=["export"])

COLUMNS = [
    ("code", "Код"),
    ("title", "Наименование"),
    ("stage_name", "Этап"),
    ("stage_group", "Группа"),
    ("status", "Статус"),
    ("priority", "Приоритет"),
    ("supplier_name", "Поставщик"),
    ("country", "Страна"),
    ("incoterms", "Инкотермс"),
    ("contract_number", "Контракт №"),
    ("contract_date", "Дата контракта"),
    ("contract_amount", "Сумма"),
    ("currency", "Валюта"),
    ("unk_number", "УНК"),
    ("payment_confirmed_at", "Оплата подтверждена"),
    ("transport_mode", "Транспорт"),
    ("etd", "ETD"),
    ("eta", "ETA"),
    ("actual_arrival", "Факт. прибытие"),
    ("gtd_number", "ГТД №"),
    ("gtd_submitted_at", "ГТД подана"),
    ("gtd_released_at", "ГТД выпущена"),
    ("act_number", "Акт ВК №"),
    ("days_in_stage", "Дней на этапе"),
    ("sla_days", "Норма, дней"),
    ("is_overdue", "Красная зона"),
    ("docs_pct", "Документы, %"),
    ("checklist_pct", "Чек-лист, %"),
]


@router.get("/deals.csv")
async def export_deals(
    all_statuses: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(Deal).order_by(Deal.stage_id, Deal.code)
    if not all_statuses:
        stmt = stmt.where(Deal.status.in_(OPEN_STATUSES))
    deals = (await db.execute(stmt)).unique().scalars().all()
    progress = await bulk_progress(db, [d.id for d in deals])

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow([label for _, label in COLUMNS])

    for d in deals:
        docs_pct, chk_pct = progress.get(d.id, (0, 0))
        sla = d.stage.sla_days if d.stage else None
        row = {
            "code": d.code,
            "title": d.title,
            "stage_name": d.stage.name if d.stage else "",
            "stage_group": d.stage.group_name if d.stage else "",
            "status": d.status,
            "priority": d.priority,
            "supplier_name": d.supplier.name if d.supplier else "",
            "country": d.country,
            "incoterms": d.incoterms,
            "contract_number": d.contract_number,
            "contract_date": d.contract_date or "",
            "contract_amount": d.contract_amount if d.contract_amount is not None else "",
            "currency": d.currency,
            "unk_number": d.unk_number,
            "payment_confirmed_at": d.payment_confirmed_at or "",
            "transport_mode": TRANSPORT_MODES.get(d.transport_mode, d.transport_mode),
            "etd": d.etd or "",
            "eta": d.eta or "",
            "actual_arrival": d.actual_arrival or "",
            "gtd_number": d.gtd_number,
            "gtd_submitted_at": d.gtd_submitted_at or "",
            "gtd_released_at": d.gtd_released_at or "",
            "act_number": d.act_number,
            "days_in_stage": f"{days_since(d.stage_entered_at):.1f}",
            "sla_days": sla if sla is not None else "",
            "is_overdue": "да" if is_overdue(d, sla) else "нет",
            "docs_pct": docs_pct,
            "checklist_pct": chk_pct,
        }
        writer.writerow([row[key] for key, _ in COLUMNS])

    # BOM so Excel opens Cyrillic correctly on a double-click.
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ved_deals_{stamp}.csv"'},
    )
