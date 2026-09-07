import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import Base, SessionLocal, engine
from .migrate import run as run_migrations
from .models import *  # noqa: F401,F403  (registers all tables on Base.metadata)
from .integrations import sync_gmail
from .realtime import hub
from .routers import auth, catalog, communications, dashboard, deals, export, files, ws
from .seed import run_seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ved")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all never ALTERs existing tables — add new columns here.
        await run_migrations(conn)
    async with SessionLocal() as db:
        await run_seed(db)
    async def inbox_worker():
        # Gmail push needs additional Google Cloud Pub/Sub infrastructure. A
        # short, configurable poll is reliable for one mailbox and continues
        # to work on the user's local Docker installation.
        while True:
            await asyncio.sleep(max(1, settings.gmail_poll_interval_minutes) * 60)
            if settings.gmail_poll_interval_minutes <= 0:
                continue
            try:
                async with SessionLocal() as db:
                    await sync_gmail(db, limit=50)
            except Exception as exc:  # never take down the API for a mail outage
                log.warning("Gmail background sync skipped: %s", exc)

    worker = asyncio.create_task(inbox_worker(), name="gmail-inbox-sync")
    log.info("%s API ready", settings.app_name)
    try:
        yield
    finally:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
    await engine.dispose()


app = FastAPI(
    title=f"{settings.app_name} API",
    description="Оперативная система контроля ВЭД — 18 блоков дашборда в реальном времени.",
    version="1.0.0",
    lifespan=lifespan,
)

# The web container proxies same-origin, so CORS only matters when you run the
# Vite dev server on 5173 against this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(deals.router)
app.include_router(files.router)
app.include_router(dashboard.router)
app.include_router(catalog.router)
app.include_router(export.router)
app.include_router(ws.router)
app.include_router(communications.router)


@app.get("/api/health", tags=["system"])
async def health(response: Response):
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # pragma: no cover - surfaced in the healthcheck
        log.warning("health: db unreachable: %s", exc)
        db_ok = False
        response.status_code = 503
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "realtime_clients": hub.client_count,
        "app": settings.app_name,
    }
