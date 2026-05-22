from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import HOST
from payload_sender import DEFAULT_ELF_PORT, DEFAULT_JAR_PORT, DEFAULT_LUA_PORT
from websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await ws.send_text(json.dumps({
        "type": "config",
        "ps5_ip": HOST,
        "lua_port": DEFAULT_LUA_PORT,
        "elf_port": DEFAULT_ELF_PORT,
        "jar_port": DEFAULT_JAR_PORT,
    }))
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)
