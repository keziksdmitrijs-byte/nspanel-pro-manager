"""NSPanel Pro Manager — set up and control Sonoff NSPanel Pro panels over ADB."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .adb import AdbError, NSPanelAdb
from .const import CONF_PROVISION, DOMAIN
from .panel import NSPanel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NSPanelConfigEntry = ConfigEntry[NSPanel]

SERVICE_SHELL = "shell"
SERVICE_PROVISION = "provision"
ATTR_DEVICE_ID = "device_id"
ATTR_COMMAND = "command"


def _panels_for_call(hass: HomeAssistant, call: ServiceCall) -> list[NSPanel]:
    device_ids = call.data.get(ATTR_DEVICE_ID)
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not device_ids:
        return [entry.runtime_data for entry in entries]
    if isinstance(device_ids, str):
        device_ids = [device_ids]
    registry = dr.async_get(hass)
    panels: list[NSPanel] = []
    for device_id in device_ids:
        device = registry.async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device {device_id}")
        for entry in entries:
            if entry.entry_id in device.config_entries:
                panels.append(entry.runtime_data)
    return panels


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services."""

    async def _shell(call: ServiceCall) -> ServiceResponse:
        result: dict[str, str] = {}
        for panel in _panels_for_call(hass, call):
            try:
                result[panel.adb.host] = await panel.adb.async_shell(call.data[ATTR_COMMAND], timeout=60)
            except AdbError as err:
                raise HomeAssistantError(str(err)) from err
        return {"results": result}

    async def _provision(call: ServiceCall) -> None:
        for panel in _panels_for_call(hass, call):
            hass.async_create_background_task(panel.async_provision(), f"{DOMAIN} provision")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SHELL,
        _shell,
        schema=vol.Schema(
            {vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string]), vol.Required(ATTR_COMMAND): cv.string}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROVISION,
        _provision,
        schema=vol.Schema({vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string])}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NSPanelConfigEntry) -> bool:
    """Set up one panel."""
    adb = NSPanelAdb(hass, entry.data[CONF_HOST], entry.data.get(CONF_PORT, 5555))
    panel = NSPanel(hass, entry, adb)
    try:
        await panel.async_setup()
    except AdbError as err:
        from homeassistant.exceptions import ConfigEntryNotReady

        raise ConfigEntryNotReady(str(err)) from err
    await panel.coordinator.async_config_entry_first_refresh()
    entry.runtime_data = panel

    provision = bool(entry.data.get(CONF_PROVISION))
    if provision:
        # First start after adding the panel: run the full setup once
        hass.config_entries.async_update_entry(
            entry, data={k: v for k, v in entry.data.items() if k != CONF_PROVISION}
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if provision:
        hass.async_create_background_task(panel.async_provision(), f"{DOMAIN} provision")
    else:
        hass.async_create_background_task(panel.async_apply_settings(), f"{DOMAIN} apply")
    return True


async def _async_options_updated(hass: HomeAssistant, entry: NSPanelConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NSPanelConfigEntry) -> bool:
    """Unload a panel."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded
