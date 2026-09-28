"""Загрузка справочников из Excel.

Принимается не файл, а текст, скопированный из Excel: Ctrl+C в таблице даёт
строки с табуляцией. Это покрывает рабочий сценарий целиком и не тянет в
образ парсер xlsx — а заодно работает с Google Sheets и с CSV.

Любая загрузка сначала прогоняется вхолостую: сервер возвращает разбор и
список ошибок, и только по отдельному запросу пишет в базу.
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Product, Supplier, User
from ..realtime import hub
from ..security import can_edit

router = APIRouter(prefix="/api/import", tags=["import"])

# Заголовок → поле. Ключи сравниваются в нижнем регистре без пробелов, поэтому
# «Ед. изм.» и «ед изм» попадают в одно и то же поле.
PRODUCT_COLUMNS: dict[str, str] = {
    "код": "code",
    "кодпродукции": "code",
    "артикул": "code",
    "наименование": "name",
    "название": "name",
    "номенклатура": "name",
    "тип": "kind",
    "категория": "kind",
    "единица": "unit",
    "единицаизмерения": "unit",
    "едизм": "unit",
    "ед": "unit",
    "артикулпоставщика": "supplier_code",
    "кодпоставщика": "supplier_code",
    "поставщик": "supplier",
    "назначение": "usage",
    "длячегоиспользуется": "usage",
    "применение": "usage",
    "примечание": "usage",
}


def _norm(header: str) -> str:
    return "".join(ch for ch in header.lower().strip() if ch.isalnum())


def parse_table(text: str) -> list[list[str]]:
    """Разбор вставки из Excel: таб, точка с запятой или запятая."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        return []
    first = text.split("\n", 1)[0]
    delimiter = "\t" if "\t" in first else (";" if first.count(";") > first.count(",") else ",")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return [r for r in rows if any(c.strip() for c in r)]


class ImportIn(BaseModel):
    text: str
    apply: bool = False


@router.post("/products")
async def import_products(
    payload: ImportIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    rows = parse_table(payload.text)
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустая таблица")

    header = [_norm(c) for c in rows[0]]
    mapping = {i: PRODUCT_COLUMNS[h] for i, h in enumerate(header) if h in PRODUCT_COLUMNS}
    if "name" not in mapping.values():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "В первой строке нужен заголовок со столбцом «Наименование». "
            "Распознаются: код, наименование, тип, единица, артикул поставщика, поставщик, назначение.",
        )

    suppliers = (await db.execute(select(Supplier))).scalars().all()
    by_name = {s.name.strip().lower(): s for s in suppliers}

    # Существующие коды и наименования — чтобы не плодить дубли при повторной вставке.
    existing_codes = {
        (c or "").strip().lower()
        for c in (await db.execute(select(Product.code).where(Product.code != ""))).scalars()
    }
    existing_names = {
        (n or "").strip().lower()
        for n in (await db.execute(select(Product.name))).scalars()
    }

    parsed: list[dict] = []
    problems: list[dict] = []
    seen_in_batch: set[str] = set()

    for line_no, row in enumerate(rows[1:], start=2):
        rec = {"code": "", "name": "", "kind": "", "unit": "", "supplier_code": "", "usage": ""}
        supplier_name = ""
        for idx, field in mapping.items():
            value = row[idx].strip() if idx < len(row) else ""
            if field == "supplier":
                supplier_name = value
            else:
                rec[field] = value

        if not rec["name"]:
            problems.append({"line": line_no, "text": " · ".join(row[:3]), "reason": "нет наименования"})
            continue

        key = (rec["code"] or rec["name"]).strip().lower()
        if key in seen_in_batch:
            problems.append({"line": line_no, "text": rec["name"], "reason": "повтор внутри вставки"})
            continue
        seen_in_batch.add(key)

        dup = (rec["code"] and rec["code"].lower() in existing_codes) or (
            not rec["code"] and rec["name"].lower() in existing_names
        )
        if dup:
            problems.append({"line": line_no, "text": rec["name"], "reason": "уже есть в справочнике"})
            continue

        supplier = by_name.get(supplier_name.strip().lower()) if supplier_name else None
        if supplier_name and not supplier:
            problems.append({"line": line_no, "text": rec["name"], "reason": f"поставщик «{supplier_name}» не найден"})
            continue

        parsed.append({**rec, "supplier_id": supplier.id if supplier else None,
                       "supplier_name": supplier.name if supplier else ""})

    if payload.apply and parsed:
        for rec in parsed:
            db.add(Product(
                code=rec["code"][:80], supplier_code=rec["supplier_code"][:80],
                name=rec["name"][:300], kind=rec["kind"][:80], unit=rec["unit"][:24],
                usage=rec["usage"], supplier_id=rec["supplier_id"], is_active=True,
            ))
        await db.commit()
        await hub.broadcast("product.created", {"imported": len(parsed)})

    return {
        "applied": bool(payload.apply and parsed),
        "recognised_columns": sorted(set(mapping.values())),
        "total_rows": len(rows) - 1,
        "ready": len(parsed),
        "skipped": len(problems),
        "preview": parsed[:25],
        "problems": problems[:50],
    }


@router.get("/products/template")
async def products_template(_: User = Depends(can_edit)):
    """Готовая шапка — чтобы не угадывать названия столбцов."""
    return {
        "header": ["Код", "Наименование", "Тип", "Единица", "Артикул поставщика", "Поставщик", "Назначение"],
        "example": ["JNS 101", "Отдушка лаванда", "Сырьё", "кг", "GF-2201", "", "Парфюмерная композиция"],
    }
