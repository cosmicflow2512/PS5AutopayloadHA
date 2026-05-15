"""
PS5 Payload Sender – FastAPI entry point (v3.11)

This file is intentionally thin: app creation, startup hook, router registration
and static-file mount. All routes live in routers/*.py, all heavy logic lives
in focused modules:

  config.py            – constants & env vars
  models.py            – Pydantic request models
  ha_component.py      – HA custom component generator
  ha_client.py         – HA Supervisor API helpers
  storage.py           – file I/O (payloads, profiles, devices, UI state)
  websocket_manager.py – ConnectionManager singleton
  exec_engine.py       – execution state machine + autoload runner
  routers/             – HTTP/WebSocket endpoints grouped by feature
"""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import payload_sender as _ps_module
from config import APP_VERSION, PAYLOAD_DIR, STATIC_DIR
from exec_engine import ExecState, executor
from ha_client import push_ha_state, reload_integration, write_ha_services_yaml
from routers import (
    autoload,
    backup,
    core,
    devices,
    flow_notify,
    ha,
    payloads,
    ports,
    sources,
    timing,
    ws,
)
from storage import setup_storage


def _setup_logging() -> logging.Logger:
    _log_dir = Path("/config/ps5_autopayload")
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / "ps5_autopayload.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        _log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not root.handlers:
        root.addHandler(fh)
        root.addHandler(sh)

    return logging.getLogger("ps5_autopayload")


_log = _setup_logging()

setup_storage()

# send_payload resolves payload paths via this module-level constant
_ps_module.PAYLOAD_DIR = PAYLOAD_DIR

app = FastAPI(title="PS5 Autopayload", version=APP_VERSION)

app.include_router(core.router)
app.include_router(devices.router)
app.include_router(payloads.router)
app.include_router(sources.router)
app.include_router(autoload.router)
app.include_router(ports.router)
app.include_router(ha.router)
app.include_router(backup.router)
app.include_router(timing.router)
app.include_router(flow_notify.router)
app.include_router(ws.router)


@app.on_event("startup")
async def _on_startup() -> None:
    _log.info("PS5 Autopayload v%s starting up", APP_VERSION)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, push_ha_state, ExecState.IDLE)
    await loop.run_in_executor(executor, write_ha_services_yaml)
    loop.run_in_executor(executor, reload_integration)
    _log.info("Startup complete")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8765, log_level="info", access_log=False)
