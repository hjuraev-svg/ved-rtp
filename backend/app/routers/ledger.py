"""Финансовый реестр: инвойсы поставщиков, оплаты, долги — и отчёт по ним.

Отчёт построен как расчёты с поставщиками в бухгалтерии: кредит — сколько
поставщики выставили (инвойсы), дебет — сколько мы им заплатили, сальдо —
наш долг. Валюты не сводятся в одну: курса на дату у строки нет.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import FinanceRecord, Supplier, User
from ..realtime import hub
from ..schemas import FinanceRecordIn, FinanceRecordOut
from ..security import can_edit, current_user

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

STATUS_LABELS = {
    "paid": "Оплачено",
    "partial": "Частично оплачено",
    "unpaid": "Не оплачено",
    "overdue": "Просрочено",
}


def _figures(rec: FinanceRecord) -> tuple[Decimal, str, int | None]:
    """Долг, статус и дни просрочки — всегда из текущих цифр строки."""
    debt = Decimal(rec.invoice_amount or 0) - Decimal(rec.paid_amount or 0)
    late = (date.today() - rec.due_date).days if rec.due_date else None
    if debt <= 0:
        return debt, "paid", None
    if late is not None and late > 0:
        return debt, "overdue", late
    return debt, ("partial" if rec.paid_amount else "unpaid"), None


def _out(rec: FinanceRecord) -> FinanceRecordOut:
    debt, status_, late = _figures(rec)
    return FinanceRecordOut(
        id=rec.id,
        supplier_id=rec.supplier_id,
        supplier_name=rec.supplier.name if rec.supplier else "—",
        product_name=rec.product_name,
        quantity=rec.quantity,
        unit=rec.unit,
        invoice_number=rec.invoice_number,
        invoice_amount=rec.invoice_amount,
        currency=rec.currency,
        payment_terms=rec.payment_terms,
        paid_amount=rec.paid_amount,
        due_date=rec.due_date,
        note=rec.note,
        debt=debt,
        status=status_,
        days_overdue=late,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


async def _get(db: AsyncSession, record_id: int) -> FinanceRecord:
    rec = await db.get(FinanceRecord, record_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")
    return rec


async def _check_supplier(db: AsyncSession, supplier_id: int) -> None:
    if not await db.get(Supplier, supplier_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Поставщик не найден")


@router.get("", response_model=list[FinanceRecordOut])
async def list_records(db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    rows = (
        (
            await db.execute(
                select(FinanceRecord).order_by(
                    FinanceRecord.due_date.nulls_last(), FinanceRecord.id.desc()
                )
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [_out(r) for r in rows]


@router.post("", response_model=FinanceRecordOut, status_code=201)
async def create_record(
    payload: FinanceRecordIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    await _check_supplier(db, payload.supplier_id)
    rec = FinanceRecord(**payload.model_dump(), created_by_id=user.id)
    db.add(rec)
    await db.commit()
    await db.refresh(rec, attribute_names=["supplier"])
    await hub.broadcast("ledger.changed", {"record_id": rec.id})
    return _out(rec)


@router.patch("/{record_id}", response_model=FinanceRecordOut)
async def update_record(
    record_id: int,
    payload: FinanceRecordIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    rec = await _get(db, record_id)
    await _check_supplier(db, payload.supplier_id)
    for key, value in payload.model_dump().items():
        setattr(rec, key, value)
    await db.commit()
    await db.refresh(rec, attribute_names=["supplier"])
    await hub.broadcast("ledger.changed", {"record_id": rec.id})
    return _out(rec)


@router.delete("/{record_id}", status_code=204)
async def delete_record(
    record_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(can_edit)
):
    rec = await _get(db, record_id)
    await db.delete(rec)
    await db.commit()
    await hub.broadcast("ledger.changed", {"record_id": record_id})


@router.get("/report")
async def report(db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    """Дебет / кредит по поставщикам и итоги по каждой валюте."""
    rows = (await db.execute(select(FinanceRecord))).unique().scalars().all()

    def blank() -> dict:
        return {"credit": Decimal(0), "debit": Decimal(0), "balance": Decimal(0),
                "overdue": Decimal(0), "records": 0, "overdue_records": 0}

    by_supplier: dict[tuple[int, str], dict] = {}
    totals: dict[str, dict] = {}
    for rec in rows:
        debt, status_, _late = _figures(rec)
        cur = rec.currency or "USD"
        line = by_supplier.setdefault(
            (rec.supplier_id, cur),
            {"supplier_id": rec.supplier_id,
             "supplier": rec.supplier.name if rec.supplier else "—",
             "currency": cur, **blank()},
        )
        total = totals.setdefault(cur, {"currency": cur, **blank()})
        for acc in (line, total):
            acc["credit"] += Decimal(rec.invoice_amount or 0)
            acc["debit"] += Decimal(rec.paid_amount or 0)
            acc["balance"] += debt
            acc["records"] += 1
            if status_ == "overdue":
                acc["overdue"] += debt
                acc["overdue_records"] += 1

    suppliers = sorted(by_supplier.values(), key=lambda r: (-r["overdue"], -r["balance"]))
    status_counts = {key: 0 for key in STATUS_LABELS}
    for rec in rows:
        status_counts[_figures(rec)[1]] += 1
    return {
        "totals": sorted(totals.values(), key=lambda t: -t["credit"]),
        "suppliers": suppliers,
        "statuses": [
            {"key": key, "name": name, "count": status_counts[key]}
            for key, name in STATUS_LABELS.items()
        ],
    }
