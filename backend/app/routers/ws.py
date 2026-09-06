import asyncio
import contextlib

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..db import SessionLocal
from ..realtime import hub
from ..security import user_from_token

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def realtime(ws: WebSocket, token: str = Query(...)):
    """Push channel for live dashboard updates.

    The browser cannot set headers on a WebSocket handshake, so the JWT arrives
    as a query param — it is verified before the socket is accepted.
    """
    async with SessionLocal() as db:
        user = await user_from_token(token, db)
    if not user:
        await ws.close(code=4401)
        return

    await hub.connect(ws)
    try:
        await ws.send_json({"event": "hello", "payload": {"user": user.full_name, "role": user.role}})
        while True:
            # Keep the connection alive; a client ping resets the idle timeout.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(ws.receive_text(), timeout=30)
                continue
            await ws.send_json({"event": "ping", "payload": {}})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(ws)
