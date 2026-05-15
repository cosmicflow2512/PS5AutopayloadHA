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
    '"""PS5 Autopayload – auto-generated HA integration (v' + APP_VERSION + ')."""\n'
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
    '_HASS = None\n'
    '_VERSION = "' + APP_VERSION + '"\n'
    '\n'
    '_RUN_PROFILE_VOL = vol.Schema({\n'
    '    vol.Required("profile_name"): cv.string,\n'
    '    vol.Optional("host", default=""): cv.string,\n'
    '})\n'
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
    'async def _run_profile(call: ServiceCall) -> None:\n'
    '    profile = call.data["profile_name"].strip()\n'
    '    if not profile.lower().endswith(".txt"):\n'
    '        profile += ".txt"\n'
    '    host = call.data.get("host", "")\n'
    '    if not host:\n'
    '        cfg = await _get("/api/config")\n'
    '        host = cfg.get("ps5_ip", "")\n'
    '    if not host:\n'
    '        _LOGGER.error("PS5 Autopayload: no PS5 IP configured")\n'
    '        return\n'
    '    await _call("/api/autoload/run", {\n'
    '        "host": host, "profile": profile, "continue_on_error": False,\n'
    '    })\n'
    '\n'
    'async def _stop(call: ServiceCall) -> None:\n'
    '    await _call("/api/autoload/stop")\n'
    '\n'
    'async def _pause(call: ServiceCall) -> None:\n'
    '    await _call("/api/autoload/pause")\n'
    '\n'
    'async def _resume(call: ServiceCall) -> None:\n'
    '    await _call("/api/autoload/resume")\n'
    '\n'
    'async def _reload_profiles(call: ServiceCall) -> None:\n'
    '    if _HASS is not None:\n'
    '        await _refresh_run_profile_schema(_HASS)\n'
    '\n'
    'async def _version_guard(hass: HomeAssistant) -> None:\n'
    '    """Show a persistent "restart required" notice when the add-on has\n'
    '    been updated to a newer version than the integration HA currently\n'
    '    has loaded; dismiss it once they match again (after a restart).\n'
    '    Runs inside HA (always reachable), unlike the add-on start-up\n'
    '    notification which races HA boot and is lost to 502s."""\n'
    '    try:\n'
    '        info = await _get("/api/version")\n'
    '        addon = (info or {}).get("version")\n'
    '        if addon and addon != _VERSION:\n'
    '            await hass.services.async_call(\n'
    '                "persistent_notification", "create",\n'
    '                {"title": "PS5 Autopayload",\n'
    '                 "message": ("Add-on updated to " + str(addon) + " but "\n'
    '                 "Home Assistant still runs integration " + _VERSION + ". "\n'
    '                 "Restart Home Assistant to finish the update."),\n'
    '                 "notification_id": "ps5_autopayload_restart"},\n'
    '                blocking=False,\n'
    '            )\n'
    '        else:\n'
    '            await hass.services.async_call(\n'
    '                "persistent_notification", "dismiss",\n'
    '                {"notification_id": "ps5_autopayload_restart"},\n'
    '                blocking=False,\n'
    '            )\n'
    '    except Exception as exc:\n'
    '        _LOGGER.debug("PS5 Autopayload: version guard skipped - %s", exc)\n'
    '\n'
    'async def _refresh_run_profile_schema(hass: HomeAssistant) -> None:\n'
    '    """Rebuild the run_profile selector from the live add-on flow list.\n'
    '\n'
    '    HA does not re-read services.yaml at runtime. Removing then\n'
    '    re-registering the service fires the service-registered events the\n'
    '    HA frontend listens to, so the automation editor refetches service\n'
    '    descriptions; async_set_service_schema then supplies the fresh\n'
    '    options. Only path that updates the dropdown without a Core restart."""\n'
    '    data = await _get("/api/autoload/profiles")\n'
    '    raw = data.get("profiles", []) or []\n'
    '    opts = []\n'
    '    for p in raw:\n'
    '        n = p[:-4] if isinstance(p, str) and p.endswith(".txt") else p\n'
    '        if n:\n'
    '            opts.append(n)\n'
    '    pn_sel = (\n'
    '        {"select": {"custom_value": True, "sort": True, "options": opts}}\n'
    '        if opts else {"text": {}}\n'
    '    )\n'
    '    if hass.services.has_service(DOMAIN, "run_profile"):\n'
    '        hass.services.async_remove(DOMAIN, "run_profile")\n'
    '    hass.services.async_register(\n'
    '        DOMAIN, "run_profile", _run_profile, schema=_RUN_PROFILE_VOL,\n'
    '    )\n'
    '    try:\n'
    '        hass.services.async_set_service_schema(DOMAIN, "run_profile", {\n'
    '            "name": "Run Flow",\n'
    '            "description": "Execute a saved PS5 Autopayload flow",\n'
    '            "fields": {\n'
    '                "profile_name": {\n'
    '                    "name": "Flow",\n'
    '                    "description": "Select a saved flow",\n'
    '                    "required": True,\n'
    '                    "selector": pn_sel,\n'
    '                },\n'
    '                "host": {\n'
    '                    "name": "PS5 IP Override",\n'
    '                    "description": "Override PS5 IP (uses add-on config if omitted)",\n'
    '                    "required": False,\n'
    '                    "selector": {"text": {}},\n'
    '                },\n'
    '            },\n'
    '        })\n'
    '    except Exception as exc:\n'
    '        _LOGGER.warning("PS5 Autopayload: schema set failed - %s", exc)\n'
    '    _LOGGER.info("PS5 Autopayload: run_profile refreshed (%d flows)", len(opts))\n'
    '    await _version_guard(hass)\n'
    '\n'
    'def _register_services(hass: HomeAssistant) -> None:\n'
    '    """Register all services (idempotent; survives add-on updates)."""\n'
    '    if not hass.services.has_service(DOMAIN, "run_profile"):\n'
    '        hass.services.async_register(\n'
    '            DOMAIN, "run_profile", _run_profile, schema=_RUN_PROFILE_VOL,\n'
    '        )\n'
    '    if not hass.services.has_service(DOMAIN, "stop"):\n'
    '        hass.services.async_register(DOMAIN, "stop",            _stop)\n'
    '        hass.services.async_register(DOMAIN, "pause",           _pause)\n'
    '        hass.services.async_register(DOMAIN, "resume",          _resume)\n'
    '        hass.services.async_register(DOMAIN, "reload_profiles", _reload_profiles)\n'
    '    _LOGGER.info("PS5 Autopayload services registered (v' + APP_VERSION + ')")\n'
    '\n'
    'async def async_setup(hass: HomeAssistant, config: dict) -> bool:\n'
    '    global _HASS\n'
    '    _HASS = hass\n'
    '    _register_services(hass)\n'
    '    hass.async_create_task(_refresh_run_profile_schema(hass))\n'
    '    return True\n'
    '\n'
    'async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:\n'
    '    global _HASS\n'
    '    _HASS = hass\n'
    '    _register_services(hass)\n'
    '    await _refresh_run_profile_schema(hass)\n'
    '    return True\n'
    '\n'
    'async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:\n'
    '    return True\n'
)

_CONFIG_FLOW_PY = (
    '"""Config flow for PS5 Autopayload – adds integration via HA GUI."""\n'
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
                    "Home Assistant. Stelle sicher, dass das Add-on läuft."
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
        "Custom component written (v%s) – %s install",
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
            "Einstellungen → Geräte & Dienste → Integration hinzufügen → "
            '"PS5 Autopayload" suchen und einrichten.'
        )
    else:
        msg = (
            f"PS5 Autopayload Integration aktualisiert (v{APP_VERSION}). "
            "Bitte Home Assistant Core neu starten und dann unter "
            "Einstellungen → Geräte & Dienste → Integration hinzufügen → "
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
