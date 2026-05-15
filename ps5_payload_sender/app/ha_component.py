"""
Auto-generates the HA custom component files under
/config/custom_components/ps5_autopayload/.

Only rewritten when APP_VERSION changes to avoid unnecessary HA reloads.
"""
from __future__ import annotations

import json
import logging
import shutil
import urllib.request
from pathlib import Path

from config import APP_DIR, APP_VERSION, SUPERVISOR_TOKEN

_log = logging.getLogger("ps5_autopayload")

_CC_DIR = Path("/config/custom_components/ps5_autopayload")

# ── __init__.py source (embedded as a string) ─────────────────────
_INIT_PY = (
    '"""PS5 Autopayload \u2013 auto-generated HA integration (v' + APP_VERSION + ')."""\n'
    'from __future__ import annotations\n'
    'import logging\n'
    'import aiohttp\n'
    'import voluptuous as vol\n'
    'from homeassistant.config_entries import ConfigEntry\n'
    'from homeassistant.core import HomeAssistant, ServiceCall\n'
    'import homeassistant.helpers.config_validation as cv\n'
    '\n'
    '_LOGGER = logging.getLogger(__name__)\n'
    'DOMAIN = "ps5_autopayload"\n'
    '_ADDON_BASES = ["http://localhost:8765", "http://172.30.32.1:8765"]\n'
    '\n'
    'async def _call(path: str, data: dict | None = None) -> dict:\n'
    '    for base in _ADDON_BASES:\n'
    '        try:\n'
    '            to = aiohttp.ClientTimeout(total=60)\n'
    '            async with aiohttp.ClientSession(timeout=to) as s:\n'
    '                if data is not None:\n'
    '                    async with s.post(f"{base}{path}", json=data) as r:\n'
    '                        return await r.json()\n'
    '                async with s.post(f"{base}{path}") as r:\n'
    '                        return await r.json()\n'
    '        except Exception:\n'
    '            continue\n'
    '    _LOGGER.warning("PS5 Autopayload: add-on unreachable at %s", path)\n'
    '    return {}\n'
    '\n'
    'async def _get(path: str) -> dict:\n'
    '    for base in _ADDON_BASES:\n'
    '        try:\n'
    '            to = aiohttp.ClientTimeout(total=10)\n'
    '            async with aiohttp.ClientSession(timeout=to) as s:\n'
    '                async with s.get(f"{base}{path}") as r:\n'
    '                    return await r.json()\n'
    '        except Exception:\n'
    '            continue\n'
    '    return {}\n'
    '\n'
    'def _register_services(hass: HomeAssistant) -> None:\n'
    '    """Register all PS5 Autopayload HA services (idempotent)."""\n'
    '    if hass.services.has_service(DOMAIN, "run_profile"):\n'
    '        return\n'
    '\n'
    '    async def run_profile(call: ServiceCall) -> None:\n'
    '        profile = call.data["profile_name"].strip()\n'
    '        if not profile.lower().endswith(".txt"):\n'
    '            profile += ".txt"\n'
    '        host = call.data.get("host", "")\n'
    '        if not host:\n'
    '            cfg = await _get("/api/config")\n'
    '            host = cfg.get("ps5_ip", "")\n'
    '        if not host:\n'
    '            _LOGGER.error("PS5 Autopayload: no PS5 IP configured")\n'
    '            return\n'
    '        await _call("/api/autoload/run", {\n'
    '            "host": host, "profile": profile, "continue_on_error": False,\n'
    '        })\n'
    '\n'
    '    async def stop(call: ServiceCall) -> None:\n'
    '        await _call("/api/autoload/stop")\n'
    '\n'
    '    async def pause(call: ServiceCall) -> None:\n'
    '        await _call("/api/autoload/pause")\n'
    '\n'
    '    async def resume(call: ServiceCall) -> None:\n'
    '        await _call("/api/autoload/resume")\n'
    '\n'
    '    async def reload_profiles(call: ServiceCall) -> None:\n'
    '        result = await _call("/api/ha/reload-integration")\n'
    '        if result.get("success"):\n'
    '            _LOGGER.info("PS5 Autopayload: integration reloaded with fresh profiles")\n'
    '        else:\n'
    '            _LOGGER.warning("PS5 Autopayload: reload failed \u2013 %s", result.get("error"))\n'
    '\n'
    '    hass.services.async_register(\n'
    '        DOMAIN, "run_profile", run_profile,\n'
    '        schema=vol.Schema({\n'
    '            vol.Required("profile_name"): cv.string,\n'
    '            vol.Optional("host", default=""): cv.string,\n'
    '        }),\n'
    '    )\n'
    '    hass.services.async_register(DOMAIN, "stop",            stop)\n'
    '    hass.services.async_register(DOMAIN, "pause",           pause)\n'
    '    hass.services.async_register(DOMAIN, "resume",          resume)\n'
    '    hass.services.async_register(DOMAIN, "reload_profiles", reload_profiles)\n'
    '    _LOGGER.info("PS5 Autopayload services registered (v' + APP_VERSION + ')")\n'
    '\n'
    'async def async_setup(hass: HomeAssistant, config: dict) -> bool:\n'
    '    _register_services(hass)\n'
    '    return True\n'
    '\n'
    'async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:\n'
    '    _register_services(hass)\n'
    '    return True\n'
    '\n'
    'async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:\n'
    '    return True\n'
)

_CONFIG_FLOW_PY = (
    '"""Config flow for PS5 Autopayload \u2013 adds integration via HA GUI."""\n'
    'from homeassistant import config_entries\n'
    '\n'
    'DOMAIN = "ps5_autopayload"\n'
    '\n'
    'class PS5AutopayloadConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):\n'
    '    VERSION = 1\n'
    '\n'
    '    async def async_step_user(self, user_input=None):\n'
    '        if user_input is not None:\n'
    '            await self.async_set_unique_id(DOMAIN)\n'
    '            self._abort_if_unique_id_configured()\n'
    '            return self.async_create_entry(title="PS5 Autopayload", data={})\n'
    '        return self.async_show_form(step_id="user")\n'
)

_STRINGS_EN = {
    "config": {
        "step": {
            "user": {
                "title": "PS5 Autopayload",
                "description": (
                    "Connects to the PS5 Autopayload add-on running on this "
                    "Home Assistant instance. Make sure the add-on is running."
                ),
            }
        },
        "abort": {"already_configured": "PS5 Autopayload is already configured."},
    }
}

_STRINGS_DE = {
    "config": {
        "step": {
            "user": {
                "title": "PS5 Autopayload",
                "description": (
                    "Verbindet sich mit dem PS5 Autopayload Add-on auf diesem "
                    "Home Assistant. Stelle sicher, dass das Add-on l\u00e4uft."
                ),
            }
        },
        "abort": {"already_configured": "PS5 Autopayload ist bereits konfiguriert."},
    }
}

_SERVICES_YAML = (
    'run_profile:\n'
    '  name: Run Profile\n'
    '  description: Execute a saved PS5 Autopayload profile\n'
    '  fields:\n'
    '    profile_name:\n'
    '      name: Profile Name\n'
    '      description: Select or type a profile name (without .txt)\n'
    '      required: true\n'
    '      selector:\n'
    '        text:\n'
    '    host:\n'
    '      name: PS5 IP Override\n'
    '      description: Override PS5 IP (uses add-on config if omitted)\n'
    '      required: false\n'
    '      selector:\n'
    '        text:\n'
    'stop:\n'
    '  name: Stop\n'
    '  description: Stop the current PS5 Autopayload execution\n'
    'pause:\n'
    '  name: Pause\n'
    '  description: Pause the current execution\n'
    'resume:\n'
    '  name: Resume\n'
    '  description: Resume a paused execution\n'
    'reload_profiles:\n'
    '  name: Reload Profiles\n'
    '  description: Refresh the profile dropdown from the add-on\n'
)


def write_custom_component() -> None:
    """Write HA custom component files; skipped when version is unchanged."""
    manifest_path = _CC_DIR / "manifest.json"

    # Always sync the icon regardless of version
    _CC_DIR.mkdir(parents=True, exist_ok=True)
    _icon_src = APP_DIR / "icon.png"
    if _icon_src.exists():
        shutil.copy2(_icon_src, _CC_DIR / "icon.png")
        brand_dir = _CC_DIR / "brand"
        brand_dir.mkdir(exist_ok=True)
        shutil.copy2(_icon_src, brand_dir / "icon.png")

    # Skip full rewrite when version matches
    current: dict = {}
    if manifest_path.exists():
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if current.get("version") == APP_VERSION:
        return

    first_install = not manifest_path.exists()
    (_CC_DIR / "translations").mkdir(exist_ok=True)

    manifest_path.write_text(json.dumps({
        "domain": "ps5_autopayload",
        "name": "PS5 Autopayload",
        "version": APP_VERSION,
        "documentation": "https://github.com/cosmicflow2512/PS5AutopayloadHA",
        "dependencies": [],
        "codeowners": [],
        "requirements": [],
        "iot_class": "local_push",
        "config_flow": True,
    }, indent=2), encoding="utf-8")

    (_CC_DIR / "__init__.py").write_text(_INIT_PY, encoding="utf-8")
    (_CC_DIR / "config_flow.py").write_text(_CONFIG_FLOW_PY, encoding="utf-8")

    _strings_json = json.dumps(_STRINGS_EN, indent=2)
    (_CC_DIR / "strings.json").write_text(_strings_json, encoding="utf-8")
    (_CC_DIR / "translations" / "en.json").write_text(_strings_json, encoding="utf-8")
    (_CC_DIR / "translations" / "de.json").write_text(
        json.dumps(_STRINGS_DE, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (_CC_DIR / "services.yaml").write_text(_SERVICES_YAML, encoding="utf-8")

    _log.info(
        "Custom component written (v%s) \u2013 %s install",
        APP_VERSION,
        "first" if first_install else "update",
    )
    _send_ha_notification(first_install)


def _send_ha_notification(first_install: bool) -> None:
    if not SUPERVISOR_TOKEN:
        return
    if first_install:
        msg = (
            f"PS5 Autopayload Integration installiert (v{APP_VERSION}). "
            "Bitte Home Assistant Core neu starten, dann unter "
            "Einstellungen \u2192 Ger\u00e4te & Dienste \u2192 Integration hinzuf\u00fcgen \u2192 "
            '"PS5 Autopayload" suchen und einrichten.'
        )
    else:
        msg = (
            f"PS5 Autopayload Integration aktualisiert (v{APP_VERSION}). "
            "Bitte Home Assistant Core neu starten und dann unter "
            "Einstellungen \u2192 Ger\u00e4te & Dienste \u2192 Integration hinzuf\u00fcgen \u2192 "
            '"PS5 Autopayload" suchen.'
        )
    try:
        data = json.dumps({
            "title": "PS5 Autopayload",
            "message": msg,
            "notification_id": "ps5_autopayload_setup",
        }).encode()
        req = urllib.request.Request(
            "http://supervisor/core/api/services/persistent_notification/create",
            data=data,
            headers={
                "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        _log.warning("Could not send HA notification: %s", exc)
