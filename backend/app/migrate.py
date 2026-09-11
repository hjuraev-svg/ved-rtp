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
]


async def run(conn: AsyncConnection) -> None:
    # Local development uses SQLite and always creates its schema from current
    # models. These forward-only ALTER statements are only for PostgreSQL.
    if conn.dialect.name != "postgresql":
        log.info("schema migration skipped for %s", conn.dialect.name)
        return
    for stmt in STATEMENTS:
        try:
            await conn.execute(text(stmt))
        except Exception as exc:  # pragma: no cover - surfaced in logs
            log.warning("migration statement failed (%s): %s", stmt.split(" ADD")[0], exc)
    log.info("schema migration applied (%d statements)", len(STATEMENTS))
