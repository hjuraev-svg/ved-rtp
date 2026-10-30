"""Lightweight forward-only schema migration.

`Base.metadata.create_all` adds missing *tables* but never missing *columns*,
so new columns on existing tables are applied here. Postgres supports
`ADD COLUMN IF NOT EXISTS`, which makes every statement idempotent — running
this on an already-migrated database is a no-op.

Kept deliberately small; if the schema starts changing often, replace this with
Alembic rather than growing the list.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .reference import IMPORT_STAGE_REMAP, STAGES

log = logging.getLogger("ved.migrate")

STATEMENTS = [
    # 2026-08: three deal types (import / local / service)
    "ALTER TABLE stages ADD COLUMN IF NOT EXISTS pipeline VARCHAR(16) NOT NULL DEFAULT 'import'",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS pipeline VARCHAR(16) NOT NULL DEFAULT 'import'",
    "ALTER TABLE checklist_templates ADD COLUMN IF NOT EXISTS pipeline VARCHAR(16) NOT NULL DEFAULT 'import'",
    "ALTER TABLE doc_types ADD COLUMN IF NOT EXISTS pipeline VARCHAR(16) NOT NULL DEFAULT 'import'",
    "CREATE INDEX IF NOT EXISTS ix_stages_pipeline ON stages (pipeline)",
    "CREATE INDEX IF NOT EXISTS ix_deals_pipeline ON deals (pipeline)",
    # 2026-09: one Telegram conversation per supplier (optional).
    "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(80) NOT NULL DEFAULT ''",
    # 2026-09: product category per supplier (Парфюмерия, Оборудование, …).
    "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS category VARCHAR(80) NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS ix_suppliers_category ON suppliers (category)",
    # 2026-09: номенклатура — тип позиции, единица измерения, артикул поставщика.
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS kind VARCHAR(80) NOT NULL DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS unit VARCHAR(24) NOT NULL DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_code VARCHAR(80) NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS ix_products_kind ON products (kind)",
    # 2026-09: срок действия у документа сделки (сертификаты, заключения).
    "ALTER TABLE deal_documents ADD COLUMN IF NOT EXISTS valid_until DATE",
    # 2026-09: себестоимость поставки — пошлина, брокер, прочие расходы.
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS customs_duty NUMERIC(16,2)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS broker_fee NUMERIC(16,2)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS other_costs NUMERIC(16,2)",
    # 2026-10: название позиции у поставщика рядом с внутренним названием.
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(300) NOT NULL DEFAULT ''",
    "ALTER TABLE deal_items ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(300) NOT NULL DEFAULT ''",
]


async def remap_import_stages(conn: AsyncConnection) -> None:
    """2026-10: воронка импорта сокращена с 19 этапов до 12.

    Сделки, история переходов и чек-лист переносятся на новые номера по
    IMPORT_STAGE_REMAP, лишние этапы удаляются. Признак старой схемы — этап 13
    у импорта; после переноса его нет, так что повторный запуск ничего не делает.
    Ошибка здесь не глотается: недоперенесённые сделки хуже, чем неподнявшийся
    сервис, который откатит деплой.
    """
    old = (
        await conn.execute(text("SELECT 1 FROM stages WHERE id = 13 AND pipeline = 'import'"))
    ).first()
    if old is None:
        return

    def case(col: str) -> str:
        whens = " ".join(f"WHEN {a} THEN {b}" for a, b in IMPORT_STAGE_REMAP.items())
        return f"CASE {col} {whens} ELSE {col} END"

    # «Завершено / на складе» больше нет: такие сделки уже прошли воронку —
    # закрываем их, а не оставляем висеть на акте входного контроля.
    await conn.execute(
        text(
            "UPDATE deals SET status = 'done', closed_at = COALESCE(closed_at, stage_entered_at) "
            "WHERE pipeline = 'import' AND stage_id = 19 AND status IN ('active', 'on_hold')"
        )
    )
    await conn.execute(text(f"UPDATE deals SET stage_id = {case('stage_id')} WHERE stage_id <= 19"))
    await conn.execute(
        text(
            f"UPDATE stage_events SET from_stage_id = {case('from_stage_id')}, "
            f"to_stage_id = {case('to_stage_id')} WHERE to_stage_id <= 19 OR from_stage_id <= 19"
        )
    )
    await conn.execute(
        text(f"UPDATE checklist_templates SET stage_id = {case('stage_id')} WHERE stage_id <= 19")
    )
    # Сохранённые раскладки плиток ссылаются на старые номера — сбрасываем.
    await conn.execute(text("DELETE FROM user_dashboard"))
    await conn.execute(text("DELETE FROM stages WHERE pipeline = 'import' AND id > 12"))

    # Код этапа уникален, а новые коды частично совпадают со старыми у соседей,
    # поэтому сначала временные, потом окончательные. Нормативы тоже ставим
    # заново: смысл этапа сменился, и старое значение к нему не относится.
    await conn.execute(text("UPDATE stages SET code = 'tmp_' || id WHERE pipeline = 'import'"))
    for row in STAGES:
        if row["pipeline"] != "import":
            continue
        await conn.execute(
            text(
                "UPDATE stages SET code = :code, name = :name, sla_days = :sla, "
                "frequency = :frequency, responsible = :responsible WHERE id = :id"
            ),
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "sla": row["sla_days"],
                "frequency": row["frequency"],
                "responsible": row["responsible"],
            },
        )
    log.info("import pipeline remapped from 19 to 12 stages")


async def run(conn: AsyncConnection) -> None:
    # Local development uses SQLite and always creates its schema from current
    # models. These forward-only ALTER statements are only for PostgreSQL.
    if conn.dialect.name != "postgresql":
        log.info("schema migration skipped for %s", conn.dialect.name)
        await remap_import_stages(conn)
        return
    for stmt in STATEMENTS:
        try:
            await conn.execute(text(stmt))
        except Exception as exc:  # pragma: no cover - surfaced in logs
            log.warning("migration statement failed (%s): %s", stmt.split(" ADD")[0], exc)
    log.info("schema migration applied (%d statements)", len(STATEMENTS))
    await remap_import_stages(conn)
