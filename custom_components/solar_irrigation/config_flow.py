"""Config flow for Solar Irrigation."""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_LAT, CONF_LON, CONF_NORTH_OFFSET, CONF_BUILDINGS, CONF_ZONES,
    CONF_ET0_MODE, CONF_ET0_ENTITY, CONF_ET0_FIXED, CONF_USE_DST, CONF_WEIGHTED,
    ET0_MODE_WEATHER, ET0_MODE_ENTITY, ET0_MODE_FIXED,
    DEFAULT_ET0_FIXED, DEFAULT_NORTH_OFFSET, DEFAULT_WEIGHTED, DEFAULT_USE_DST,
)

_LOGGER = logging.getLogger(__name__)

STEP_ET0_SCHEMA = vol.Schema({
    vol.Required(CONF_ET0_MODE, default=ET0_MODE_FIXED): vol.In([
        ET0_MODE_FIXED, ET0_MODE_ENTITY, ET0_MODE_WEATHER
    ]),
    vol.Optional(CONF_ET0_FIXED, default=DEFAULT_ET0_FIXED): vol.Coerce(float),
    vol.Optional(CONF_ET0_ENTITY, default=""): str,
})

STEP_OPTIONS_SCHEMA = vol.Schema({
    vol.Optional(CONF_WEIGHTED, default=DEFAULT_WEIGHTED): bool,
    vol.Optional(CONF_USE_DST, default=DEFAULT_USE_DST): bool,
})


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Solar Irrigation."""

    VERSION = 1

    def __init__(self):
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Step 1: Basic location setup."""
        errors = {}

        # Default lat/lon from HA config
        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        schema = vol.Schema({
            vol.Required("name", default="My Garden"): str,
            vol.Required(CONF_LAT, default=round(default_lat, 5)): vol.Coerce(float),
            vol.Required(CONF_LON, default=round(default_lon, 5)): vol.Coerce(float),
            vol.Optional(CONF_NORTH_OFFSET, default=DEFAULT_NORTH_OFFSET): vol.Coerce(float),
        })

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_buildings()

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "ha_lat": str(round(default_lat, 4)),
                "ha_lon": str(round(default_lon, 4)),
            },
        )

    async def async_step_buildings(self, user_input=None) -> FlowResult:
        """Step 2: Buildings/obstacles JSON."""
        errors = {}

        schema = vol.Schema({
            vol.Optional(CONF_BUILDINGS, default="[]"): str,
        })

        if user_input is not None:
            try:
                buildings = json.loads(user_input.get(CONF_BUILDINGS, "[]"))
                if not isinstance(buildings, list):
                    raise ValueError("Must be a JSON array")
                self._data[CONF_BUILDINGS] = buildings
                return await self.async_step_zones()
            except (json.JSONDecodeError, ValueError) as e:
                errors[CONF_BUILDINGS] = "invalid_json"
                _LOGGER.error("Invalid buildings JSON: %s", e)

        return self.async_show_form(
            step_id="buildings",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_zones(self, user_input=None) -> FlowResult:
        """Step 3: Zones JSON."""
        errors = {}

        example = json.dumps([
            {
                "zone_id": "zone_cucina",
                "name": "Cucina",
                "pts": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 3}, {"x": 0, "y": 3}],
                "color": "#4CAF50",
                "switch_entity": "switch.irrigazione_cucina",
                "mm_per_min": 0.5,
                "threshold_mm": 3.0,
                "kc": 0.7
            }
        ], indent=2)

        schema = vol.Schema({
            vol.Required(CONF_ZONES, default=example): str,
        })

        if user_input is not None:
            try:
                zones = json.loads(user_input.get(CONF_ZONES, "[]"))
                if not isinstance(zones, list) or len(zones) == 0:
                    raise ValueError("Must be a non-empty JSON array")
                # Validate each zone has required fields
                for z in zones:
                    if "zone_id" not in z or "name" not in z or "pts" not in z:
                        raise ValueError("Each zone must have zone_id, name, pts")
                self._data[CONF_ZONES] = zones
                return await self.async_step_et0()
            except (json.JSONDecodeError, ValueError) as e:
                errors[CONF_ZONES] = "invalid_json"
                _LOGGER.error("Invalid zones JSON: %s", e)

        return self.async_show_form(
            step_id="zones",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_et0(self, user_input=None) -> FlowResult:
        """Step 4: ET0 source."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_options()

        return self.async_show_form(
            step_id="et0",
            data_schema=STEP_ET0_SCHEMA,
            errors=errors,
        )

    async def async_step_options(self, user_input=None) -> FlowResult:
        """Step 5: Options (weighting, DST)."""
        if user_input is not None:
            self._data.update(user_input)
            name = self._data.pop("name", "My Garden")
            return self.async_create_entry(title=name, data=self._data)

        return self.async_show_form(
            step_id="options",
            data_schema=STEP_OPTIONS_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarIrrigationOptionsFlow(config_entry)


class SolarIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Options flow for updating configuration."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage options."""
        errors = {}
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            # Validate zones JSON if provided
            if CONF_ZONES in user_input:
                try:
                    zones = json.loads(user_input[CONF_ZONES])
                    user_input[CONF_ZONES] = zones
                except (json.JSONDecodeError, ValueError):
                    errors[CONF_ZONES] = "invalid_json"
            if CONF_BUILDINGS in user_input:
                try:
                    buildings = json.loads(user_input[CONF_BUILDINGS])
                    user_input[CONF_BUILDINGS] = buildings
                except (json.JSONDecodeError, ValueError):
                    errors[CONF_BUILDINGS] = "invalid_json"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(CONF_LAT, default=current.get(CONF_LAT, 45.0)): vol.Coerce(float),
            vol.Optional(CONF_LON, default=current.get(CONF_LON, 9.0)): vol.Coerce(float),
            vol.Optional(CONF_NORTH_OFFSET, default=current.get(CONF_NORTH_OFFSET, 0)): vol.Coerce(float),
            vol.Optional(CONF_ET0_MODE, default=current.get(CONF_ET0_MODE, ET0_MODE_FIXED)): vol.In([
                ET0_MODE_FIXED, ET0_MODE_ENTITY, ET0_MODE_WEATHER
            ]),
            vol.Optional(CONF_ET0_FIXED, default=current.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED)): vol.Coerce(float),
            vol.Optional(CONF_ET0_ENTITY, default=current.get(CONF_ET0_ENTITY, "")): str,
            vol.Optional(CONF_WEIGHTED, default=current.get(CONF_WEIGHTED, DEFAULT_WEIGHTED)): bool,
            vol.Optional(CONF_USE_DST, default=current.get(CONF_USE_DST, DEFAULT_USE_DST)): bool,
            vol.Optional(CONF_BUILDINGS, default=json.dumps(current.get(CONF_BUILDINGS, []))): str,
            vol.Optional(CONF_ZONES, default=json.dumps(current.get(CONF_ZONES, []))): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
