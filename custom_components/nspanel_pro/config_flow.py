"""Config flow for NSPanel Pro Manager."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .adb import AdbError, NSPanelAdb
from .const import (
    CONF_COMPANION_PACKAGE,
    CONF_DASHBOARD,
    CONF_INSTALL_COMPANION,
    CONF_INSTALL_TOOLS,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    CONF_PROVISION,
    DEFAULT_COMPANION_PACKAGE,
    DEFAULT_DASHBOARD,
    DEFAULT_MQTT_PORT,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NSPanelProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an NSPanel Pro by IP address."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            adb = NSPanelAdb(self.hass, host, port)
            serial = ""
            try:
                # Up to 30 s for "Allow USB debugging?" to be accepted on the panel
                await adb.async_connect(auth_timeout=30)
                serial = await adb.async_shell("getprop ro.serialno", timeout=10)
                model = await adb.async_shell("getprop ro.product.model", timeout=10)
            except AdbError as err:
                _LOGGER.warning("Cannot connect to %s:%s: %s", host, port, err)
                errors["base"] = "auth" if "auth" in str(err).lower() else "cannot_connect"
            finally:
                await adb.async_close()

            if not errors:
                await self.async_set_unique_id(serial or f"{host}:{port}")
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                name = (user_input.get(CONF_NAME) or "").strip() or f"NSPanel Pro {host}"
                _LOGGER.info("Adding %s (%s, %s)", name, model, serial)
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_PROVISION: bool(user_input.get(CONF_PROVISION, True)),
                    },
                    options={
                        CONF_DASHBOARD: user_input.get(CONF_DASHBOARD, DEFAULT_DASHBOARD),
                        CONF_COMPANION_PACKAGE: DEFAULT_COMPANION_PACKAGE,
                        CONF_INSTALL_COMPANION: True,
                        CONF_INSTALL_TOOLS: True,
                        CONF_MQTT_PORT: DEFAULT_MQTT_PORT,
                    },
                )

        user_input = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                vol.Optional(CONF_NAME, default=user_input.get(CONF_NAME, "")): str,
                vol.Optional(CONF_DASHBOARD, default=user_input.get(CONF_DASHBOARD, DEFAULT_DASHBOARD)): str,
                vol.Optional(CONF_PROVISION, default=user_input.get(CONF_PROVISION, True)): bool,
                vol.Optional(CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NSPanelProOptionsFlow()


class NSPanelProOptionsFlow(OptionsFlow):
    """Panel options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = dict(user_input)
            if not data.get(CONF_MQTT_HOST):
                data.pop(CONF_MQTT_HOST, None)
            return self.async_create_entry(data=data)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(CONF_DASHBOARD, default=opts.get(CONF_DASHBOARD, DEFAULT_DASHBOARD)): str,
                vol.Optional(
                    CONF_MQTT_HOST, description={"suggested_value": opts.get(CONF_MQTT_HOST, "")}
                ): str,
                vol.Optional(CONF_MQTT_PORT, default=opts.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)): int,
                vol.Optional(
                    CONF_COMPANION_PACKAGE, default=opts.get(CONF_COMPANION_PACKAGE, DEFAULT_COMPANION_PACKAGE)
                ): str,
                vol.Optional(CONF_INSTALL_COMPANION, default=opts.get(CONF_INSTALL_COMPANION, True)): bool,
                vol.Optional(CONF_INSTALL_TOOLS, default=opts.get(CONF_INSTALL_TOOLS, True)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
