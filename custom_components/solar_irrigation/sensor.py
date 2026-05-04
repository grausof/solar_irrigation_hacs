"""Sensor platform for Solar Irrigation."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ZONES, ZONE_ID, ZONE_NAME
from .coordinator import SolarIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities."""
    coordinator: SolarIrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    zones = coordinator.zones

    entities = []
    for zone in zones:
        zid = zone.get(ZONE_ID, zone.get(ZONE_NAME, "unknown"))
        name = zone.get(ZONE_NAME, zid)
        entities.extend([
            SolarIrrigationFactorSensor(coordinator, entry, zid, name),
            SolarIrrigationDeficitSensor(coordinator, entry, zid, name),
            SolarIrrigationDurationSensor(coordinator, entry, zid, name),
        ])

    async_add_entities(entities)


class SolarIrrigationBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Solar Irrigation sensors."""

    def __init__(self, coordinator, entry, zone_id, zone_name, sensor_type):
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._sensor_type = sensor_type
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{zone_id}_{sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{zone_id}")},
            name=f"Solar Irrigation — {zone_name}",
            manufacturer="Solar Irrigation",
            model="Zone",
        )

    @property
    def _zone_data(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get(self._zone_id, {})


class SolarIrrigationFactorSensor(SolarIrrigationBaseSensor):
    """Shadow light factor sensor (0.0 = full shadow, 1.0 = full sun)."""

    def __init__(self, coordinator, entry, zone_id, zone_name):
        super().__init__(coordinator, entry, zone_id, zone_name, "shadow_factor")
        self._attr_name = f"Solar Factor {zone_name}"
        self._attr_icon = "mdi:weather-sunny"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = None

    @property
    def native_value(self):
        return self._zone_data.get("shadow_factor")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._zone_data
        return {
            "monthly_factors": data.get("monthly_factors", []),
            "zone_name": self._zone_name,
            "zone_id": self._zone_id,
        }


class SolarIrrigationDeficitSensor(SolarIrrigationBaseSensor):
    """Water deficit sensor in mm."""

    def __init__(self, coordinator, entry, zone_id, zone_name):
        super().__init__(coordinator, entry, zone_id, zone_name, "deficit")
        self._attr_name = f"Water Deficit {zone_name}"
        self._attr_icon = "mdi:water-minus"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "mm"

    @property
    def native_value(self):
        return self._zone_data.get("deficit")


class SolarIrrigationDurationSensor(SolarIrrigationBaseSensor):
    """Irrigation duration sensor in minutes."""

    def __init__(self, coordinator, entry, zone_id, zone_name):
        super().__init__(coordinator, entry, zone_id, zone_name, "duration_min")
        self._attr_name = f"Irrigation Duration {zone_name}"
        self._attr_icon = "mdi:timer-outline"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "min"

    @property
    def native_value(self):
        return self._zone_data.get("duration_min")
