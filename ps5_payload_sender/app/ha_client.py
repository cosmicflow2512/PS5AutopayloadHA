"""
Home Assistant API client helpers:
  - push entity state to HA via Supervisor API
  - write services.yaml with current profile list
  - reload HA config entry
  - fetch remote version from GitHub
  - send notifications (persistent + configurable notify.* service)
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

from config import APP_VERSION, PROFILES_DIR, SUPERVISOR_TOKEN, HIDDEN_PROFILES

_log = logging.getLogger("ps5_autopayload")

_CC_DIR = Path("/config/custom_components/ps5_autopayload")
_GITHUB_RAW_CONFIG = (
    "https://raw.githubusercontent.com/cosmicflow2512/PS5AutopayloadHA"
    "/main/ps5_payload_sender/config.yaml"
)


# ── HA entity push ────────────────────────────────────────────────

def push_ha_state(state_val: str) -> None:
    """Push *state_val* to HA sensor + binary_sensor entities (blocking)."""
    if not SUPERVISOR_TOKEN:
        _log.debug("HA push skipped – no SUPERVISOR_TOKEN")
        return

    is_running = state_val in ("running", "paused")
    entities = [
        (
            "sensor.ps5_autopayload_status",
            state_val,
            {
                "friendly_name": "PS5 Autopayload Status",
                "icon": "mdi:gamepad-variant",
                "version": APP_VERSION,
            },
        ),
        (
            "binary_sensor.ps5_autopayload_running",
            "on" if is_running else "off",
            {
                "friendly_name": "PS5 Autopayload Running",
                "device_class": "connectivity",
                "icon": "mdi:play-circle" if is_running else "mdi:stop-circle",
            },
        ),
    ]

    for entity_id, val, attrs in entities:
        url = f"http://supervisor/core/api/states/{entity_id}"
        try:
            data = json.dumps({"state": val, "attributes": attrs}).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                _log.info("HA entity '%s' → '%s' (HTTP %s)", entity_id, val, resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            _log.error("HA push HTTP %s for '%s': %s | %s", exc.code, entity_id, exc.reason, body)
        except urllib.error.URLError as exc:
            _log.error("HA push URL error for '%s': %s", entity_id, exc.reason)
        except Exception as exc:
            _log.exception("HA push unexpected error for '%s': %s", entity_id, exc)


# ── services.yaml ─────────────────────────────────────────────────

def write_ha_services_yaml() -> None:
    """Write services.yaml with current profile list so HA dropdown stays fresh."""
    if not (_CC_DIR / "manifest.json").exists():
        return  # component not installed yet

    profiles: List[str] = []
    if PROFILES_DIR.exists():
        profiles = sorted(
            f.name[:-4]
            for f in PROFILES_DIR.iterdir()
            if f.is_file() and f.suffix.lower() == ".txt" and f.name not in HIDDEN_PROFILES
        )

    lines: List[str] = [
        "run_profile:\n",
        "  name: Run Profile\n",
        "  description: Execute a saved PS5 Autopayload profile\n",
        "  fields:\n",
        "    profile_name:\n",
        "      name: Profile Name\n",
        "      description: Select a profile (without .txt)\n",
        "      required: true\n",
    ]
    if profiles:
        lines += [
            "      selector:\n",
            "        select:\n",
            "          custom_value: true\n",
            "          options:\n",
        ]
        for p in profiles:
            lines.append(f"          - '{p}'\n")
    else:
        lines += ["      selector:\n", "        text:\n"]

    lines += [
        "    host:\n",
        "      name: PS5 IP Override\n",
        "      description: Override PS5 IP (uses add-on config if omitted)\n",
        "      required: false\n",
        "      selector:\n",
        "        text:\n",
        "stop:\n",
        "  name: Stop\n",
        "  description: Stop the current execution\n",
        "pause:\n",
        "  name: Pause\n",
        "  description: Pause the current execution\n",
        "resume:\n",
        "  name: Resume\n",
        "  description: Resume a paused execution\n",
        "reload_profiles:\n",
        "  name: Reload Profiles\n",
        "  description: Refresh the profile dropdown (then reload integration in HA)\n",
    ]
    (_CC_DIR / "services.yaml").write_text("".join(lines), encoding="utf-8")
    _log.info("HA services.yaml written with %d profiles", len(profiles))


# ── Reload integration ────────────────────────────────────────────

def reload_integration() -> dict:
    """Ask the HA integration to refresh its run_profile flow list.

    Previously this looked up the config entry via
    ``GET /core/api/config/config_entries/entries`` and called
    ``homeassistant.reload_config_entry``. That REST path does not exist
    in HA Core (config entries are WebSocket-only) and returned HTTP 404
    on every save, so the dropdown never updated without a Core restart.

    Instead we call the integration's own ``ps5_autopayload.reload_profiles``
    service. ``POST /core/api/services/<domain>/<service>`` is the same
    proven endpoint used for notifications; the service handler rebuilds
    the run_profile selector directly inside HA.
    """
    if not SUPERVISOR_TOKEN:
        return {"success": False, "error": "No SUPERVISOR_TOKEN"}
    ok = _call_ha_service("ps5_autopayload", "reload_profiles", {})
    if ok:
        _log.info("HA integration flow list refresh requested")
        return {"success": True}
    return {"success": False, "error": "reload_profiles service call failed"}


# ── Notifications ──────────────────────────────────────────────────

def _call_ha_service(domain: str, service: str, data: dict, timeout: float = 5.0) -> bool:
    """POST /core/api/services/{domain}/{service}. Returns True on HTTP 2xx."""
    if not SUPERVISOR_TOKEN:
        _log.debug("HA service call skipped — no SUPERVISOR_TOKEN")
        return False
    url = f"http://supervisor/core/api/services/{domain}/{service}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        _log.error("HA service %s.%s HTTP %s: %s | %s", domain, service, exc.code, exc.reason, body)
    except Exception as exc:
        _log.error("HA service %s.%s error: %s", domain, service, exc)
    return False


def send_persistent_notification(title: str, message: str) -> bool:
    """Create a HA persistent_notification (shows in HA's notification center)."""
    return _call_ha_service(
        "persistent_notification", "create",
        {"title": title, "message": message},
    )


def send_notify_service(service: str, title: str, message: str) -> bool:
    """Call ``notify.<service>``.

    The user-facing config always carries the ``notify.`` prefix (it's
    validated to start with it). Strip it here so the REST URL becomes
    ``/core/api/services/notify/<service>`` rather than the broken
    ``/core/api/services/notify/notify.<service>``.
    """
    svc = service.strip()
    if svc.startswith("notify."):
        svc = svc[len("notify."):]
    if not svc:
        _log.warning("send_notify_service: empty service after stripping prefix")
        return False
    return _call_ha_service("notify", svc, {"title": title, "message": message})


def send_monitor_notification(
    title: str, message: str, notify_service: Optional[str] = None,
    *, persistent: bool = True,
) -> dict:
    """Create an HA persistent_notification by default and optionally also
    call notify.<service>. ``persistent`` can be turned off so a service
    target receives the notification without a duplicate appearing in
    HA's notification center.

    Returns ``{"persistent": bool | None, "service": bool | None}``.
    """
    pn_ok: Optional[bool] = None
    if persistent:
        pn_ok = send_persistent_notification(title, message)
    svc_ok: Optional[bool] = None
    if notify_service:
        svc_ok = send_notify_service(notify_service, title, message)
    if pn_ok is None and svc_ok is None:
        _log.warning("Notification dispatched with no delivery channel enabled")
    _log.info("Monitor notification sent: persistent=%s service=%s", pn_ok, svc_ok)
    return {"persistent": pn_ok, "service": svc_ok}


# ── Remote version check ──────────────────────────────────────────

def get_remote_version() -> str:
    """Fetch the version string from GitHub config.yaml (blocking). Returns '' on failure."""
    try:
        req = urllib.request.Request(
            _GITHUB_RAW_CONFIG,
            headers={"User-Agent": "PS5PayloadSender/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode()
        for line in content.splitlines():
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip().strip("\"'")
    except Exception:
        pass
    return ""


# ── Debug helper ──────────────────────────────────────────────────

def debug_ha_push(current_state: str) -> dict:
    """Try a PUT to the status sensor and return diagnostics."""
    if not SUPERVISOR_TOKEN:
        return {
            "supervisor_token": False,
            "error": "SUPERVISOR_TOKEN is empty – add 'homeassistant_api: true' to config.yaml",
        }
    entity_id = "sensor.ps5_autopayload_status"
    results = []
    try:
        data = json.dumps({
            "state": current_state,
            "attributes": {"friendly_name": "PS5 Autopayload Status"},
        }).encode()
        req = urllib.request.Request(
            f"http://supervisor/core/api/states/{entity_id}",
            data=data,
            headers={
                "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            results.append({"entity": entity_id, "http_status": resp.status, "response": body[:200]})
    except urllib.error.HTTPError as exc:
        results.append({
            "entity": entity_id,
            "http_error": exc.code,
            "reason": str(exc.reason),
            "body": exc.read().decode()[:200],
        })
    except Exception as exc:
        results.append({"entity": entity_id, "error": str(exc)})

    return {
        "supervisor_token": True,
        "token_prefix": SUPERVISOR_TOKEN[:8] + "…",
        "current_state": current_state,
        "results": results,
    }
