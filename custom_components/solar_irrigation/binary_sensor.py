"""Binary sensor platform for Solar Irrigation."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ZONE_ID, ZONE_NAME
from .coordinator import SolarIrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SolarIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for zone in coordinator.zones:
        zid = zone.get(ZONE_ID, zone.get(ZONE_NAME, "unknown"))
        name = zone.get(ZONE_NAME, zid)
        entities.append(ShouldIrrigateSensor(coordinator, entry, zid, name))
    async_add_entities(entities)


class ShouldIrrigateSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: True when zone needs irrigation."""

    def __init__(self, coordinator, entry, zone_id, zone_name):
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_unique_id = f"{entry.entry_id}_{zone_id}_should_irrigate"
        self._attr_name = f"Should Irrigate {zone_name}"
        self._attr_device_class = BinarySensorDeviceClass.MOISTURE
        self._attr_icon = "mdi:sprinkler"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{zone_id}")},
            name=f"Solar Irrigation — {zone_name}",
            manufacturer="Solar Irrigation",
            model="Zone",
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._zone_id, {}).get("should_irrigate")
