"""Switches for NSPanel Pro Manager."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb import AdbError
from .const import SET_NIGHTLY_REBOOT, SET_SCREENSAVER, SET_SYSTEM_CONTROLS
from .entity import NSPanelEntity
from .panel import NSPanel

SWITCHES = (
    (SET_SYSTEM_CONTROLS, "mdi:gesture-tap-button", None),
    (SET_SCREENSAVER, "mdi:clock-digital", None),
    (SET_NIGHTLY_REBOOT, "mdi:restart-alert", EntityCategory.CONFIG),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities(NSPanelSwitch(panel, key, icon, cat) for key, icon, cat in SWITCHES)


class NSPanelSwitch(NSPanelEntity, SwitchEntity):
    """Persistent on/off setting of the panel."""

    def __init__(self, panel: NSPanel, key: str, icon: str, category: EntityCategory | None) -> None:
        super().__init__(panel, key)
        self._key = key
        self._attr_icon = icon
        self._attr_entity_category = category

    @property
    def available(self) -> bool:
        # Settings can be changed while the panel is offline (applied on reconnect)
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.panel.settings.get(self._key))

    async def _set(self, value: bool) -> None:
        try:
            await self.panel.async_set(self._key, value)
        except AdbError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
