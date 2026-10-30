"""Numbers for NSPanel Pro Manager."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb import AdbError
from .const import SET_BRIGHTNESS, SET_DIM_BRIGHTNESS, SET_PROXIMITY_THRESHOLD, SET_SCREENSAVER_TIMEOUT
from .entity import NSPanelEntity
from .panel import NSPanel

NUMBERS = (
    # key, icon, min, max, step, unit, mode
    (SET_BRIGHTNESS, "mdi:brightness-6", 5, 100, 1, PERCENTAGE, NumberMode.SLIDER),
    (SET_DIM_BRIGHTNESS, "mdi:brightness-4", 1, 60, 1, PERCENTAGE, NumberMode.SLIDER),
    (SET_SCREENSAVER_TIMEOUT, "mdi:timer-outline", 15, 1800, 15, UnitOfTime.SECONDS, NumberMode.BOX),
    (SET_PROXIMITY_THRESHOLD, "mdi:hand-wave", 0, 5000, 1, None, NumberMode.BOX),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities(NSPanelNumber(panel, *n) for n in NUMBERS)


class NSPanelNumber(NSPanelEntity, NumberEntity):
    """Persistent numeric setting of the panel."""

    def __init__(self, panel: NSPanel, key, icon, vmin, vmax, step, unit, mode) -> None:
        super().__init__(panel, key)
        self._key = key
        self._attr_icon = icon
        self._attr_native_min_value = vmin
        self._attr_native_max_value = vmax
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = mode
        if key == SET_PROXIMITY_THRESHOLD:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return float(self.panel.settings.get(self._key))

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.panel.async_set(self._key, int(value))
        except AdbError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()
