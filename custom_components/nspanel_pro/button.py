"""Buttons for NSPanel Pro Manager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb import AdbError
from .entity import NSPanelEntity
from .panel import NSPanel


@dataclass(frozen=True, kw_only=True)
class NSPanelButtonDescription(ButtonEntityDescription):
    press: Callable[[NSPanel], Awaitable[None]]
    always_available: bool = False


BUTTONS: tuple[NSPanelButtonDescription, ...] = (
    NSPanelButtonDescription(key="open_dashboard", icon="mdi:view-dashboard", press=lambda p: p.async_open_dashboard()),
    NSPanelButtonDescription(key="restart_app", icon="mdi:application-cog", press=lambda p: p.async_restart_app()),
    NSPanelButtonDescription(key="screen_on", icon="mdi:monitor", press=lambda p: p.async_screen(True)),
    NSPanelButtonDescription(key="screen_off", icon="mdi:monitor-off", press=lambda p: p.async_screen(False)),
    NSPanelButtonDescription(
        key="reboot", device_class=ButtonDeviceClass.RESTART, press=lambda p: p.async_reboot()
    ),
    NSPanelButtonDescription(
        key="open_tools", icon="mdi:tools", entity_category=EntityCategory.CONFIG, press=lambda p: p.async_open_tools()
    ),
    NSPanelButtonDescription(
        key="provision",
        icon="mdi:auto-fix",
        entity_category=EntityCategory.CONFIG,
        press=lambda p: p.async_provision(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities(NSPanelButton(panel, d) for d in BUTTONS)


class NSPanelButton(NSPanelEntity, ButtonEntity):
    """Action on the panel."""

    entity_description: NSPanelButtonDescription

    def __init__(self, panel: NSPanel, description: NSPanelButtonDescription) -> None:
        super().__init__(panel, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        if self.entity_description.key == "provision":
            self.hass.async_create_background_task(self.panel.async_provision(), "nspanel_pro provision")
            return
        try:
            await self.entity_description.press(self.panel)
        except AdbError as err:
            raise HomeAssistantError(str(err)) from err
