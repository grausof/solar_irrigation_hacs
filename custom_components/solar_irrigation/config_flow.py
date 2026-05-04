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
    CONF_MM_PER_MIN, CONF_THRESHOLD_MM,
    ET0_MODE_WEATHER, ET0_MODE_ENTITY, ET0_MODE_FIXED,
    DEFAULT_ET0_FIXED, DEFAULT_MM_PER_MIN, DEFAULT_THRESHOLD_MM, DEFAULT_KC,
    DEFAULT_NORTH_OFFSET, DEFAULT_WEIGHTED, DEFAULT_USE_DST,
    ZONE_ID, ZONE_NAME, ZONE_MM_PER_MIN, ZONE_THRESHOLD_MM, ZONE_KC,
    KC_PRESETS, KC_PRESET_KEYS,
)

_LOGGER = logging.getLogger(__name__)

ZONE_COLORS = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336",
    "#00BCD4", "#FFEB3B", "#795548", "#607D8B", "#E91E63",
]


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    for src, dst in [("àáâãäå", "a"), ("èéêë", "e"), ("ìíîï", "i"), ("òóôõö", "o"), ("ùúûü", "u")]:
        for ch in src:
            slug = slug.replace(ch, dst)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_") or "zone"


def _kc_from_input(preset: str, custom_val: float) -> float:
    if preset in KC_PRESETS and KC_PRESETS[preset][2] is not None:
        return KC_PRESETS[preset][2]
    return round(max(0.1, min(2.0, custom_val)), 2)


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Solar Irrigation.

    Steps:
      1. user      → name, lat/lon, north_offset, num_zones, global mm_per_min + threshold
      2. zone (x N) → zone name + Kc preset or custom + optional switch entity
      3. et0       → ET0 source
      4. calc_opts → weighting, DST
    Buildings and zone geometry are configured later in the Lovelace card.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._num_zones: int = 1
        self._current_zone: int = 0
        self._zones: list[dict] = []
        self._global_mm_per_min: float = DEFAULT_MM_PER_MIN
        self._global_threshold: float = DEFAULT_THRESHOLD_MM

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Step 1: location, global irrigation params, zone count."""
        default_lat = round(self.hass.config.latitude, 5)
        default_lon = round(self.hass.config.longitude, 5)

        schema = vol.Schema({
            vol.Required("name", default="My Garden"): str,
            vol.Required(CONF_LAT, default=default_lat): vol.Coerce(float),
            vol.Required(CONF_LON, default=default_lon): vol.Coerce(float),
            vol.Optional(CONF_NORTH_OFFSET, default=DEFAULT_NORTH_OFFSET): vol.Coerce(float),
            vol.Required("num_zones", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            vol.Required(CONF_MM_PER_MIN, default=DEFAULT_MM_PER_MIN): vol.Coerce(float),
            vol.Required(CONF_THRESHOLD_MM, default=DEFAULT_THRESHOLD_MM): vol.Coerce(float),
        })

        if user_input is not None:
            self._global_mm_per_min = user_input[CONF_MM_PER_MIN]
            self._global_threshold = user_input[CONF_THRESHOLD_MM]
            self._data.update({
                "name": user_input["name"],
                CONF_LAT: user_input[CONF_LAT],
                CONF_LON: user_input[CONF_LON],
                CONF_NORTH_OFFSET: user_input[CONF_NORTH_OFFSET],
                CONF_MM_PER_MIN: self._global_mm_per_min,
                CONF_THRESHOLD_MM: self._global_threshold,
                CONF_BUILDINGS: [],
            })
            self._num_zones = user_input["num_zones"]
            self._current_zone = 0
            self._zones = []
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"ha_lat": str(default_lat), "ha_lon": str(default_lon)},
        )

    async def async_step_zone(self, user_input=None) -> FlowResult:
        """Step 2 (repeated): configure each irrigation zone."""
        idx = self._current_zone

        schema = vol.Schema({
            vol.Required(ZONE_NAME, default=f"Zone {idx + 1}"): str,
            vol.Required("kc_preset", default="bermuda"): vol.In(KC_PRESET_KEYS),
            # shown only when kc_preset == "custom"; always present to keep schema simple
            vol.Optional("kc_custom", default=DEFAULT_KC): vol.Coerce(float),
            vol.Optional("switch_entity", default=""): str,
        })

        if user_input is not None:
            zone_name = user_input[ZONE_NAME]
            kc = _kc_from_input(user_input["kc_preset"], user_input.get("kc_custom", DEFAULT_KC))
            zone_id = f"zone_{_slugify(zone_name)}_{idx}"
            self._zones.append({
                ZONE_ID: zone_id,
                ZONE_NAME: zone_name,
                ZONE_KC: kc,
                ZONE_MM_PER_MIN: self._global_mm_per_min,
                ZONE_THRESHOLD_MM: self._global_threshold,
                "switch_entity": user_input.get("switch_entity", ""),
                "color": ZONE_COLORS[idx % len(ZONE_COLORS)],
                "pts": [],
            })
            self._current_zone += 1
            if self._current_zone < self._num_zones:
                return await self.async_step_zone()
            self._data[CONF_ZONES] = self._zones
            return await self.async_step_et0()

        kc_hint = " | ".join(
            f"{k}: {v[2]}" for k, v in KC_PRESETS.items() if v[2] is not None
        )
        return self.async_show_form(
            step_id="zone",
            data_schema=schema,
            description_placeholders={
                "zone_index": str(idx + 1),
                "total_zones": str(self._num_zones),
                "kc_hint": kc_hint,
            },
        )

    async def async_step_et0(self, user_input=None) -> FlowResult:
        """Step 3: ET0 source selection."""
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

    async def async_step_calc_opts(self, user_input=None) -> FlowResult:
        """Step 4: advanced calculation options."""
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
    """Options flow: edit global settings + advanced JSON for zones/buildings."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        errors: dict = {}
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
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
            vol.Optional(CONF_MM_PER_MIN, default=current.get(CONF_MM_PER_MIN, DEFAULT_MM_PER_MIN)): vol.Coerce(float),
            vol.Optional(CONF_THRESHOLD_MM, default=current.get(CONF_THRESHOLD_MM, DEFAULT_THRESHOLD_MM)): vol.Coerce(float),
            vol.Optional(CONF_ET0_MODE, default=current.get(CONF_ET0_MODE, ET0_MODE_FIXED)): vol.In(
                [ET0_MODE_FIXED, ET0_MODE_ENTITY, ET0_MODE_WEATHER]
            ),
            vol.Optional(CONF_ET0_FIXED, default=current.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED)): vol.Coerce(float),
            vol.Optional(CONF_ET0_ENTITY, default=current.get(CONF_ET0_ENTITY, "")): str,
            vol.Optional(CONF_WEIGHTED, default=current.get(CONF_WEIGHTED, DEFAULT_WEIGHTED)): bool,
            vol.Optional(CONF_USE_DST, default=current.get(CONF_USE_DST, DEFAULT_USE_DST)): bool,
            vol.Optional(CONF_ZONES, default=json.dumps(current.get(CONF_ZONES, []), ensure_ascii=False)): str,
            vol.Optional(CONF_BUILDINGS, default=json.dumps(current.get(CONF_BUILDINGS, []), ensure_ascii=False)): str,
        })

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
