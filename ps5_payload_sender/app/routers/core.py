from __future__ import annotations

import asyncio
import re

import aiofiles
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import (
    APP_VERSION,
    CONFIG_BASE,
    HOST,
    PORT_CHECK_INTERVAL,
    PORT_CHECK_TIMEOUT,
    STATIC_DIR,
)
from exec_engine import executor
from ha_client import get_remote_version
from payload_sender import DEFAULT_ELF_PORT, DEFAULT_JAR_PORT, DEFAULT_JS_PORT, DEFAULT_LUA_PORT
from storage import load_ui_state, save_ui_state

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    inject = f'<script>window.PS5_BASE="{ingress_path}";</script>'
    html = html.replace("</head>", inject + "\n</head>", 1)
    # Append ?v=APP_VERSION to all static asset URLs so browsers re-fetch
    # them after every add-on upgrade (HA OS aggressively caches JS/CSS).
    html = re.sub(
        r'(static/(?:js|css)/[^"\']+\.(?:js|css))',
        rf'\1?v={APP_VERSION}',
        html,
    )
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/api/version")
async def api_get_version():
    return {"version": APP_VERSION}


@router.get("/api/version/check")
async def api_check_version():
    loop = asyncio.get_running_loop()
    remote = await loop.run_in_executor(executor, get_remote_version)
    up_to_date = (not remote) or (remote == APP_VERSION)
    return {"current": APP_VERSION, "remote": remote, "up_to_date": up_to_date}


@router.get("/api/config")
async def api_get_config():
    return {
        "ps5_ip": HOST,
        "lua_port": DEFAULT_LUA_PORT,
        "elf_port": DEFAULT_ELF_PORT,
        "jar_port": DEFAULT_JAR_PORT,
        "js_port": DEFAULT_JS_PORT,
        "port_check_timeout": PORT_CHECK_TIMEOUT,
        "port_check_interval": PORT_CHECK_INTERVAL,
    }


@router.get("/api/state")
async def api_get_state():
    return load_ui_state()


@router.post("/api/state")
async def api_post_state(request: Request):
    save_ui_state(await request.json())
    return {"success": True}


@router.get("/api/ha/logs")
async def api_ha_logs(lines: int = 200):
    log_file = CONFIG_BASE / "ps5_autopayload.log"
    if not log_file.exists():
        return {"lines": [], "error": "Log file not found"}
    try:
        async with aiofiles.open(log_file, "r", encoding="utf-8", errors="replace") as f:
            content = await f.read()
        all_lines = content.splitlines()
        return {"lines": all_lines[-lines:], "total": len(all_lines)}
    except Exception as exc:
        return {"lines": [], "error": str(exc)}
