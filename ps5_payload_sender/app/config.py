"""Central configuration – all constants and environment variables."""
from __future__ import annotations

import os
from pathlib import Path

# ── Runtime ───────────────────────────────────────────────────────
HOST: str = os.environ.get("PS5_IP", "")
PORT_CHECK_TIMEOUT: float = float(os.environ.get("PORT_CHECK_TIMEOUT", 10))
PORT_CHECK_INTERVAL: float = float(int(os.environ.get("PORT_CHECK_INTERVAL", 500)) / 1000)
SUPERVISOR_TOKEN: str = os.environ.get("SUPERVISOR_TOKEN", "")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

# ── Paths ─────────────────────────────────────────────────────────
APP_DIR    = Path("/app")
STATIC_DIR = Path(__file__).parent / "static"

CONFIG_BASE       = Path("/config/ps5_autopayload")
PAYLOAD_DIR       = CONFIG_BASE / "payloads"
PROFILES_DIR      = CONFIG_BASE / "profiles"
STATE_FILE        = CONFIG_BASE / "config.json"
DEVICES_FILE      = CONFIG_BASE / "devices.json"
SOURCES_FILE      = CONFIG_BASE / "sources.json"
PAYLOAD_META_FILE = CONFIG_BASE / "payload_meta.json"

# Legacy paths – used once for migration from /data/
OLD_PAYLOAD_DIR  = Path("/data/payloads")
OLD_STATE_FILE   = Path("/data/state.json")
OLD_DEVICES_FILE = Path("/data/devices.json")

# ── Misc ──────────────────────────────────────────────────────────
APP_VERSION = "1.1.3"
MAX_PAYLOAD_VERSIONS  = 5     # versions kept per payload
MAX_TIMING_ENTRIES    = 10    # timing samples kept per port
MAX_LOG_ENTRIES       = 500   # log entries kept in history
MAX_FLOW_RUNS         = 10    # flow analysis runs stored
MAX_FLOW_HISTORY      = 10    # high-level flow runs kept (date + result)

TIMING_FILE       = CONFIG_BASE / "port_timing.json"
FLOW_RUNS_FILE    = CONFIG_BASE / "flow_runs.json"
FLOW_HISTORY_FILE = CONFIG_BASE / "flow_history.json"
GITHUB_RAW_CONFIG = (
    "https://raw.githubusercontent.com/cosmicflow2512/PS5AutopayloadHA"
    "/main/ps5_payload_sender/config.yaml"
)
ALLOWED_PAYLOAD_EXTENSIONS: set[str] = {".lua", ".elf", ".bin"}
HIDDEN_PROFILES: set[str] = {"ftp.txt", "goldhen.txt", "_builder_run.txt"}
