"""Sensors for NSPanel Pro Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import NSPanelEntity
from .panel import NSPanel

SENSORS = (
    # key, icon, device_class, category
    ("ip_address", "mdi:ip-network", None, EntityCategory.DIAGNOSTIC),
    ("last_boot", "mdi:restart", SensorDeviceClass.TIMESTAMP, EntityCategory.DIAGNOSTIC),
    ("screen_brightness", "mdi:brightness-percent", None, EntityCategory.DIAGNOSTIC),
    ("companion_version", "mdi:home-assistant", None, EntityCategory.DIAGNOSTIC),
    ("tools_version", "mdi:tools", None, EntityCategory.DIAGNOSTIC),
    ("webview_version", "mdi:web", None, EntityCategory.DIAGNOSTIC),
    ("foreground_app", "mdi:application", None, EntityCategory.DIAGNOSTIC),
    ("proximity", "mdi:hand-wave", None, EntityCategory.DIAGNOSTIC),
    ("proximity_peak", "mdi:chart-bell-curve", None, EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities(NSPanelSensor(panel, *s) for s in SENSORS)


class NSPanelSensor(NSPanelEntity, SensorEntity):
    """Diagnostic value of the panel."""

    def __init__(self, panel: NSPanel, key, icon, device_class, category) -> None:
        super().__init__(panel, key)
        self._key = key
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_entity_category = category
        if key in ("proximity", "proximity_peak"):
            self._attr_state_class = SensorStateClass.MEASUREMENT if key == "proximity" else None

    @property
    def native_value(self):
        st = self.status
        info = self.panel.info
        if self._key == "ip_address":
            return (st.ip if st else None) or self.panel.adb.host
        if self._key == "last_boot":
            return st.boot_time if st else None
        if self._key == "screen_brightness":
            return st.brightness if st else None
        if self._key == "companion_version":
            return info.companion
        if self._key == "tools_version":
            return info.tools
        if self._key == "webview_version":
            return info.webview
        if self._key == "foreground_app":
            return st.foreground if st else None
        if self._key == "proximity":
            return st.proximity if st else None
        if self._key == "proximity_peak":
            m = self.panel.proximity_measure
            return m["max"] if m else None
        return None

    @property
    def available(self) -> bool:
        if self._key == "proximity_peak":
            return True
        return super().available

    @property
    def extra_state_attributes(self):
        if self._key == "proximity_peak":
            attrs = dict(self.panel.proximity_measure or {})
            attrs["measuring"] = self.panel.measuring
            return attrs
        return None
