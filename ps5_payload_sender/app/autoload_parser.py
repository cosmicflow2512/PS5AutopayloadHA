"""
Autoload file parser for PS5 Payload Sender.

Syntax (one directive per line):
  # comment                          – ignored
  # ~version <file> <tag>            – pin payload version
  # ~notify k=v k=v ...              – per-flow notification settings
                                       (loader_ready=on flow_started=off
                                        flow_completed=on flow_failed=on
                                        service=notify.mobile_app_phone)
  filename.lua [port]                – send payload (port optional)
  filename.elf [port]                – send payload (port optional)
  filename.bin [port]                – send payload (port optional, default ELF port)
  filename.jar [port]                – send payload (port optional, default BD-UN-JB port)
  filename.js  [port]                – send payload (port optional, default Y2JB port 50000)
  !<ms>                              – delay in milliseconds
  ?<port>                            – wait until port is reachable (short wait)
  ?<port> <timeout_s>                – wait_port with custom timeout
  ?<port> <timeout_s> <interval_ms>  – wait_port with custom timeout & poll interval
  ??<port>                           – WAIT FOR LOADER, defaults 3 h / 30 s / 1 sample
  ??<port> <max_wait_s>              – long-form wait with custom max
  ??<port> <max_wait_s> <interval_s>
  ??<port> <max_wait_s> <interval_s> <stability_count>
  @notify "<title>" "<message>"      – emit notification using flow's service
  @notify "<title>" "<message>" notify.<override>
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class SendDirective:
    filename: str
    port: Optional[int] = None


@dataclass
class DelayDirective:
    milliseconds: int


@dataclass
class WaitPortDirective:
    port: int
    timeout_seconds: float = 60.0
    interval_ms: int = 500   # poll interval in milliseconds


@dataclass
class WaitForLoaderDirective:
    """Long-running wait for the P2JB / Patience ELF loader port.

    Differences from :class:`WaitPortDirective`:
      * defaults tuned for multi-hour waits (3 h max, 30 s poll)
      * requires N consecutive successful polls before continuing
      * timeout makes the whole flow FAIL and fires a failure notification
      * success fires the loader-ready notification
    """
    # 0 / 0.0 means "use the per-flow ~notify header default" — the engine
    # falls back to loader_port / loader_interval_s / loader_max_wait_s.
    port: int = 0
    max_wait_seconds: float = 0.0
    interval_seconds: float = 0.0
    stability_count: int = 1


@dataclass
class NotifyDirective:
    """Manually placed notification step. Always sends via the flow's
    configured notify config; ``service_override`` (if set) overrides
    only the notify.<service> target for this one event."""
    title: str
    message: str = ""
    service_override: Optional[str] = None


Directive = Union[
    SendDirective, DelayDirective, WaitPortDirective,
    WaitForLoaderDirective, NotifyDirective,
]

_PAYLOAD_RE = re.compile(
    r'^(?P<name>.+?\.(lua|elf|bin|jar|js))\s*(?P<port>\d+)?$',
    re.IGNORECASE
)

_VERSION_PIN_RE = re.compile(r'^#\s*~version\s+(\S+)\s+(\S+)\s*$')
_NOTIFY_HDR_RE  = re.compile(r'^#\s*~notify\s+(.*)$')


def parse_version_pins(content: str) -> dict:
    """Return {filename: version_tag} for all ~version annotations in a flow file."""
    pins: dict = {}
    for line in content.splitlines():
        m = _VERSION_PIN_RE.match(line.strip())
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def set_version_pin(content: str, filename: str, version: str) -> str:
    """Set or replace the ~version annotation for *filename* in *content*."""
    pin_line = f'# ~version {filename} {version}'
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = _VERSION_PIN_RE.match(line.strip())
        if m and m.group(1) == filename:
            lines[i] = pin_line + ('\n' if line.endswith('\n') else '')
            return ''.join(lines)
    # Not found: insert before the first non-comment, non-empty line
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            lines.insert(i, pin_line + '\n')
            return ''.join(lines)
    return ''.join(lines) + pin_line + '\n'


# ── Notify config header ──────────────────────────────────────────

_DEFAULT_NOTIFY_CONFIG: Dict[str, Any] = {
    # Event toggles
    "loader_ready":          True,
    "flow_started":          False,
    "flow_completed":        True,
    "flow_failed":           True,
    # Delivery
    "service":               "",       # notify.<service>; empty = persistent only
    "persistent":            True,     # send HA persistent_notification.create
    # Loader-watch — flow-level master switch (replaces the WAIT FOR LOADER step)
    "wait_for_loader_enabled": False,
    "loader_port":           9021,
    "loader_interval_s":     30,
    "loader_max_wait_s":     10800,    # 3 h
}

_BOOL_KEYS = (
    "loader_ready", "flow_started", "flow_completed", "flow_failed",
    "persistent", "wait_for_loader_enabled",
)
_INT_KEYS  = ("loader_port", "loader_interval_s", "loader_max_wait_s")


def _coerce_bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "on", "yes", "y")


def _coerce_int(val: str, fallback: int) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return fallback


def parse_notify_config(content: str) -> Dict[str, Any]:
    """Read the first ``# ~notify k=v k=v …`` header in *content*.

    Missing keys fall back to :data:`_DEFAULT_NOTIFY_CONFIG`. Unknown keys
    are ignored. Returns a fresh dict (safe to mutate).
    """
    cfg = dict(_DEFAULT_NOTIFY_CONFIG)
    for line in content.splitlines():
        m = _NOTIFY_HDR_RE.match(line.strip())
        if not m:
            continue
        try:
            tokens = shlex.split(m.group(1))
        except ValueError:
            continue
        for tok in tokens:
            if "=" not in tok:
                continue
            k, _, v = tok.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == "service":
                cfg["service"] = v
            elif k in _BOOL_KEYS:
                cfg[k] = _coerce_bool(v)
            elif k in _INT_KEYS:
                cfg[k] = _coerce_int(v, cfg[k])
        break  # only the first header counts
    return cfg


def render_notify_config(cfg: Dict[str, Any]) -> str:
    """Render a notify config dict as a single ``# ~notify …`` line.

    Only emits non-default values so flows without notification config
    stay tidy. Service is always quoted to survive shell-style parsing.
    """
    parts = []
    for key in ("loader_ready", "flow_started", "flow_completed", "flow_failed"):
        parts.append(f"{key}={'on' if cfg.get(key) else 'off'}")
    # Flow-level loader-wait master switch (replaces the WAIT FOR LOADER step)
    if cfg.get("wait_for_loader_enabled"):
        parts.append("wait_for_loader_enabled=on")
    # Loader config emitted only when values differ from defaults
    for key, default in (("loader_port", 9021),
                         ("loader_interval_s", 30),
                         ("loader_max_wait_s", 10800)):
        v = int(cfg.get(key, default) or default)
        if v != default:
            parts.append(f"{key}={v}")
    # Explicit persistent toggle written only when off (default is on)
    if cfg.get("persistent") is False:
        parts.append("persistent=off")
    svc = (cfg.get("service") or "").strip()
    if svc:
        parts.append(f'service="{svc}"')
    return "# ~notify " + " ".join(parts)


def set_notify_config(content: str, cfg: Dict[str, Any]) -> str:
    """Replace (or insert) the first ``# ~notify …`` header in *content*."""
    line_out = render_notify_config(cfg)
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if _NOTIFY_HDR_RE.match(line.strip()):
            lines[i] = line_out + ('\n' if line.endswith('\n') else '')
            return ''.join(lines)
    # Not found: insert at the top (after a leading shebang-style comment if any)
    insert_at = 0
    if lines and lines[0].lstrip().startswith('#') and '~' not in lines[0]:
        insert_at = 1
    lines.insert(insert_at, line_out + '\n')
    return ''.join(lines)


# ── Directive parsing ─────────────────────────────────────────────

_NOTIFY_CALL_RE = re.compile(r'^@notify\b\s*(.*)$', re.IGNORECASE)


def parse_line(line: str) -> Optional[Directive]:
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    if line.startswith('!'):
        try:
            ms = int(line[1:].strip())
        except ValueError:
            return None
        return DelayDirective(milliseconds=max(0, ms))

    # ?? must be checked BEFORE ? so the long form wins.
    if line.startswith('??'):
        # All params are optional now — they're stored at the flow level
        # in the ~notify header. port=0 / max=0 / interval=0 signal
        # "use the header config" to the exec engine. Legacy flows that
        # still ship `??9021 7200 30 1` keep working unchanged.
        rest = line[2:].strip().split()
        port = 0
        max_wait = 0.0
        interval = 0.0
        stability = 1
        if rest:
            try: port = int(rest[0])
            except ValueError: pass
        if len(rest) >= 2:
            try: max_wait = float(rest[1])
            except ValueError: pass
        if len(rest) >= 3:
            try: interval = max(1.0, float(rest[2]))
            except ValueError: pass
        if len(rest) >= 4:
            try: stability = max(1, int(rest[3]))
            except ValueError: pass
        return WaitForLoaderDirective(
            port=port,
            max_wait_seconds=max_wait,
            interval_seconds=interval,
            stability_count=stability,
        )

    if line.startswith('?'):
        rest = line[1:].strip().split()
        if not rest:
            return None
        try:
            port = int(rest[0])
        except ValueError:
            return None
        timeout = 60.0
        interval_ms = 500
        if len(rest) >= 2:
            try:
                timeout = float(rest[1])
            except ValueError:
                pass
        if len(rest) >= 3:
            try:
                interval_ms = max(100, int(rest[2]))
            except ValueError:
                pass
        return WaitPortDirective(port=port, timeout_seconds=timeout, interval_ms=interval_ms)

    m_notify = _NOTIFY_CALL_RE.match(line)
    if m_notify:
        try:
            args = shlex.split(m_notify.group(1))
        except ValueError:
            return None
        if not args:
            return None
        title = args[0]
        message = args[1] if len(args) >= 2 else ""
        # The third positional is treated as a service override only if it
        # looks like a notify.<svc> token. Otherwise it folds into message.
        service: Optional[str] = None
        if len(args) >= 3 and args[2].startswith("notify."):
            service = args[2]
        return NotifyDirective(title=title, message=message, service_override=service)

    m = _PAYLOAD_RE.match(line)
    if m:
        name = m.group('name').strip()
        port_str = m.group('port')
        port = int(port_str) if port_str else None
        return SendDirective(filename=name, port=port)

    return None


def parse_autoload_file(content: str) -> List[Directive]:
    directives: List[Directive] = []
    for line in content.splitlines():
        directive = parse_line(line)
        if directive is not None:
            directives.append(directive)
    return directives


def parse_autoload_path(path: Path) -> List[Directive]:
    return parse_autoload_file(path.read_text(encoding="utf-8", errors="replace"))
