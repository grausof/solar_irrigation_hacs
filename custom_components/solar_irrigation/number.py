"""Number platform for Solar Irrigation (deficit override)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
        entities.append(DeficitOverrideNumber(coordinator, entry, zid, name))
    async_add_entities(entities)


class DeficitOverrideNumber(CoordinatorEntity, NumberEntity):
    """Number entity to manually override water deficit for a zone."""

    def __init__(self, coordinator, entry, zone_id, zone_name):
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_unique_id = f"{entry.entry_id}_{zone_id}_deficit_override"
        self._attr_name = f"Deficit Override {zone_name}"
        self._attr_icon = "mdi:water-sync"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 50.0
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = "mm"
        self._attr_mode = NumberMode.BOX
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{zone_id}")},
            name=f"Solar Irrigation — {zone_name}",
            manufacturer="Solar Irrigation",
            model="Zone",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._zone_id, {}).get("deficit", 0.0)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.override_deficit(self._zone_id, value)
