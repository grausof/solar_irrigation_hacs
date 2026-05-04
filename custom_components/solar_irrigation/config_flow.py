"""Config flow for Solar Irrigation."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_LAT, CONF_LON, CONF_NORTH_OFFSET, CONF_BUILDINGS, CONF_ZONES,
    CONF_ET0_MODE, CONF_ET0_ENTITY, CONF_ET0_FIXED, CONF_USE_DST, CONF_WEIGHTED,
    ET0_MODE_WEATHER, ET0_MODE_ENTITY, ET0_MODE_FIXED,
    DEFAULT_ET0_FIXED, DEFAULT_MM_PER_MIN, DEFAULT_THRESHOLD_MM, DEFAULT_KC,
    DEFAULT_NORTH_OFFSET, DEFAULT_WEIGHTED, DEFAULT_USE_DST,
    ZONE_ID, ZONE_NAME, ZONE_MM_PER_MIN, ZONE_THRESHOLD_MM, ZONE_KC,
)

_LOGGER = logging.getLogger(__name__)

# Auto-assigned colors for zones (up to 10)
ZONE_COLORS = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336",
    "#00BCD4", "#FFEB3B", "#795548", "#607D8B", "#E91E63",
]


def _slugify(name: str) -> str:
    """Convert a zone name to a safe zone_id."""
    slug = name.lower().strip()
    slug = re.sub(r"[àáâãäå]", "a", slug)
    slug = re.sub(r"[èéêë]", "e", slug)
    slug = re.sub(r"[ìíîï]", "i", slug)
    slug = re.sub(r"[òóôõö]", "o", slug)
    slug = re.sub(r"[ùúûü]", "u", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_") or "zone"


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Solar Irrigation.

    Steps:
      1. user        → name, lat, lon, north_offset, num_zones
      2. zone_N      → per-zone name + irrigation params  (repeated num_zones times)
      3. et0         → ET0 source
      4. calc_opts   → weighting, DST
    Buildings are configured later via the web tool in the Lovelace card.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._num_zones: int = 1
        self._current_zone: int = 0
        self._zones: list[dict] = []

    # ── Step 1: location + zone count ──────────────────────────────────────

    async def async_step_user(self, user_input=None) -> FlowResult:
        default_lat = round(self.hass.config.latitude, 5)
        default_lon = round(self.hass.config.longitude, 5)

        schema = vol.Schema({
            vol.Required("name", default="My Garden"): str,
            vol.Required(CONF_LAT, default=default_lat): vol.Coerce(float),
            vol.Required(CONF_LON, default=default_lon): vol.Coerce(float),
            vol.Optional(CONF_NORTH_OFFSET, default=DEFAULT_NORTH_OFFSET): vol.Coerce(float),
            vol.Required("num_zones", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        })

        if user_input is not None:
            self._data.update({
                "name": user_input["name"],
                CONF_LAT: user_input[CONF_LAT],
                CONF_LON: user_input[CONF_LON],
                CONF_NORTH_OFFSET: user_input[CONF_NORTH_OFFSET],
                CONF_BUILDINGS: [],  # populated later via the web tool
            })
            self._num_zones = user_input["num_zones"]
            self._current_zone = 0
            self._zones = []
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "ha_lat": str(default_lat),
                "ha_lon": str(default_lon),
            },
        )

    # ── Step 2 (repeated): one step per zone ───────────────────────────────

    async def async_step_zone(self, user_input=None) -> FlowResult:
        idx = self._current_zone
        default_name = f"Zone {idx + 1}"

        schema = vol.Schema({
            vol.Required(ZONE_NAME, default=default_name): str,
            vol.Optional(ZONE_MM_PER_MIN, default=DEFAULT_MM_PER_MIN): vol.Coerce(float),
            vol.Optional(ZONE_THRESHOLD_MM, default=DEFAULT_THRESHOLD_MM): vol.Coerce(float),
            vol.Optional(ZONE_KC, default=DEFAULT_KC): vol.Coerce(float),
            vol.Optional("switch_entity", default=""): str,
        })

        if user_input is not None:
            zone_name = user_input[ZONE_NAME]
            zone_id = f"zone_{_slugify(zone_name)}_{idx}"
            self._zones.append({
                ZONE_ID: zone_id,
                ZONE_NAME: zone_name,
                ZONE_MM_PER_MIN: user_input[ZONE_MM_PER_MIN],
                ZONE_THRESHOLD_MM: user_input[ZONE_THRESHOLD_MM],
                ZONE_KC: user_input[ZONE_KC],
                "switch_entity": user_input.get("switch_entity", ""),
                "color": ZONE_COLORS[idx % len(ZONE_COLORS)],
                "pts": [],  # geometry added later via the web tool
            })
            self._current_zone += 1
            if self._current_zone < self._num_zones:
                return await self.async_step_zone()
            # All zones collected → next step
            self._data[CONF_ZONES] = self._zones
            return await self.async_step_et0()

        return self.async_show_form(
            step_id="zone",
            data_schema=schema,
            description_placeholders={
                "zone_index": str(idx + 1),
                "total_zones": str(self._num_zones),
            },
        )

    # ── Step 3: ET0 source ─────────────────────────────────────────────────

    async def async_step_et0(self, user_input=None) -> FlowResult:
        schema = vol.Schema({
            vol.Required(CONF_ET0_MODE, default=ET0_MODE_FIXED): vol.In(
                [ET0_MODE_FIXED, ET0_MODE_ENTITY, ET0_MODE_WEATHER]
            ),
            vol.Optional(CONF_ET0_FIXED, default=DEFAULT_ET0_FIXED): vol.Coerce(float),
            vol.Optional(CONF_ET0_ENTITY, default=""): str,
        })

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_calc_opts()

        return self.async_show_form(step_id="et0", data_schema=schema)

    # ── Step 4: calculation options ────────────────────────────────────────

    async def async_step_calc_opts(self, user_input=None) -> FlowResult:
        schema = vol.Schema({
            vol.Optional(CONF_WEIGHTED, default=DEFAULT_WEIGHTED): bool,
            vol.Optional(CONF_USE_DST, default=DEFAULT_USE_DST): bool,
        })

        if user_input is not None:
            self._data.update(user_input)
            name = self._data.pop("name", "My Garden")
            return self.async_create_entry(title=name, data=self._data)

        return self.async_show_form(step_id="calc_opts", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarIrrigationOptionsFlow(config_entry)


class SolarIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Options flow: edit location, ET0, calc options, and zone list."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Single options page for global settings."""
        errors: dict = {}
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            # Parse zones JSON back to list if provided as string
            if isinstance(user_input.get(CONF_ZONES), str):
                try:
                    user_input[CONF_ZONES] = json.loads(user_input[CONF_ZONES])
                except (json.JSONDecodeError, ValueError):
                    errors[CONF_ZONES] = "invalid_json"
            if isinstance(user_input.get(CONF_BUILDINGS), str):
                try:
                    user_input[CONF_BUILDINGS] = json.loads(user_input[CONF_BUILDINGS])
                except (json.JSONDecodeError, ValueError):
                    errors[CONF_BUILDINGS] = "invalid_json"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(CONF_LAT, default=current.get(CONF_LAT, 45.0)): vol.Coerce(float),
            vol.Optional(CONF_LON, default=current.get(CONF_LON, 9.0)): vol.Coerce(float),
            vol.Optional(CONF_NORTH_OFFSET, default=current.get(CONF_NORTH_OFFSET, 0)): vol.Coerce(float),
            vol.Optional(CONF_ET0_MODE, default=current.get(CONF_ET0_MODE, ET0_MODE_FIXED)): vol.In(
                [ET0_MODE_FIXED, ET0_MODE_ENTITY, ET0_MODE_WEATHER]
            ),
            vol.Optional(CONF_ET0_FIXED, default=current.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED)): vol.Coerce(float),
            vol.Optional(CONF_ET0_ENTITY, default=current.get(CONF_ET0_ENTITY, "")): str,
            vol.Optional(CONF_WEIGHTED, default=current.get(CONF_WEIGHTED, DEFAULT_WEIGHTED)): bool,
            vol.Optional(CONF_USE_DST, default=current.get(CONF_USE_DST, DEFAULT_USE_DST)): bool,
            # Advanced: edit zones/buildings as JSON for power users
            vol.Optional(
                CONF_ZONES,
                default=json.dumps(current.get(CONF_ZONES, []), ensure_ascii=False),
            ): str,
            vol.Optional(
                CONF_BUILDINGS,
                default=json.dumps(current.get(CONF_BUILDINGS, []), ensure_ascii=False),
            ): str,
        })

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
