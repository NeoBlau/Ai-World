"""WebSocket: real-time world stream.

Every API process subscribes once to the Redis channel and fans events out to
its connected clients. Clients may send {"type":"filter","rooms":[...]} to
narrow the stream. The stream is read-only; it carries no private DMs.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.database.session import session_scope
from app.world.clock import get_clock
from app.world.event_bus import CHANNEL

router = APIRouter()
log = get_logger("aiworld.ws")
MAX_CLIENTS = 500


class Hub:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, set[str] | None] = {}
        self._task: asyncio.Task | None = None
        self._clock_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._pump())
            self._clock_task = asyncio.create_task(self._clock())

    async def stop(self) -> None:
        for t in (self._task, self._clock_task):
            if t:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        self._task = self._clock_task = None

    async def _pump(self) -> None:
        while True:
            try:
                pubsub = get_redis().pubsub()
                await pubsub.subscribe(CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    await self.broadcast(msg["data"])
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.warning("ws pubsub error, reconnecting", exc_info=True)
                await asyncio.sleep(2)

    async def _clock(self) -> None:
        while True:
            await asyncio.sleep(10)
            if not self.clients:
                continue
            try:
                async with session_scope() as s:
                    snap = (await get_clock(s)).snapshot()
                await self.broadcast(json.dumps({"type": "world.clock", "payload": snap}), room_filtered=False)
            except Exception:  # noqa: BLE001
                log.debug("clock broadcast failed", exc_info=True)

    async def broadcast(self, raw: str, room_filtered: bool = True) -> None:
        room_id = None
        if room_filtered:
            with contextlib.suppress(ValueError, TypeError):
                room_id = json.loads(raw).get("room_id")
        dead = []
        for ws, rooms in list(self.clients.items()):
            if rooms and room_id and room_id not in rooms:
                continue
            try:
                await asyncio.wait_for(ws.send_text(raw), timeout=2)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)


hub = Hub()


@router.websocket("/ws")
async def world_stream(ws: WebSocket) -> None:
    if len(hub.clients) >= MAX_CLIENTS:
        await ws.close(code=1013)
        return
    await ws.accept()
    hub.clients[ws] = None
    await ws.send_text(json.dumps({"type": "hello", "payload": {"message": "connected to AI WORLD"}}))
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > 4000:
                continue
            with contextlib.suppress(ValueError, TypeError, AttributeError):
                msg = json.loads(raw)
                if msg.get("type") == "filter":
                    rooms = msg.get("rooms")
                    hub.clients[ws] = {str(r) for r in rooms[:50]} if isinstance(rooms, list) and rooms else None
                elif msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.pop(ws, None)
