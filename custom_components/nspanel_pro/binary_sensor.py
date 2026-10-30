"""Binary sensors for NSPanel Pro Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import NSPanelEntity
from .panel import NSPanel


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    panel: NSPanel = entry.runtime_data
    async_add_entities([NSPanelConnected(panel), NSPanelScreen(panel), NSPanelProvisioning(panel)])


class NSPanelConnected(NSPanelEntity, BinarySensorEntity):
    """ADB connection to the panel."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, panel: NSPanel) -> None:
        super().__init__(panel, "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success and self.status and self.status.online)


class NSPanelScreen(NSPanelEntity, BinarySensorEntity):
    """Screen awake."""

    _attr_icon = "mdi:tablet"

    def __init__(self, panel: NSPanel) -> None:
        super().__init__(panel, "screen")

    @property
    def is_on(self) -> bool | None:
        return self.status.awake if self.status else None


class NSPanelProvisioning(NSPanelEntity, BinarySensorEntity):
    """Setup in progress."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, panel: NSPanel) -> None:
        super().__init__(panel, "provisioning")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.panel.provisioning

    @property
    def extra_state_attributes(self):
        return {"last_result": self.panel.last_provision}
