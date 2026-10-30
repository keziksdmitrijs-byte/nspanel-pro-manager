"""Nightly reboot time for NSPanel Pro Manager."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SET_REBOOT_TIME
from .entity import NSPanelEntity
from .panel import NSPanel


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities([NSPanelRebootTime(panel)])


class NSPanelRebootTime(NSPanelEntity, TimeEntity):
    """Time of the nightly reboot."""

    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, panel: NSPanel) -> None:
        super().__init__(panel, SET_REBOOT_TIME)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> time | None:
        try:
            return time.fromisoformat(str(self.panel.settings.get(SET_REBOOT_TIME)))
        except ValueError:
            return None

    async def async_set_value(self, value: time) -> None:
        await self.panel.async_set(SET_REBOOT_TIME, value.strftime("%H:%M:%S"))
        self.async_write_ha_state()
