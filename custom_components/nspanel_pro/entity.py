"""Base entity for NSPanel Pro Manager."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .panel import NSPanel, PanelStatus


class NSPanelEntity(CoordinatorEntity):
    """Entity bound to one panel."""

    _attr_has_entity_name = True

    def __init__(self, panel: NSPanel, key: str) -> None:
        super().__init__(panel.coordinator)
        self.panel = panel
        self._attr_translation_key = key
        uid = panel.entry.unique_id or panel.entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        info = panel.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=panel.title,
            manufacturer="SONOFF",
            model=f"NSPanel Pro ({info.model})" if info.model else "NSPanel Pro",
            sw_version=info.firmware or None,
            serial_number=info.serial or None,
            configuration_url=None,
        )

    @property
    def status(self) -> PanelStatus | None:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        return super().available and self.status is not None and self.status.online
