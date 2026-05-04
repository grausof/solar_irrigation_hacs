"""Config flow for Solar Irrigation."""
from __future__ import annotations

import json
import logging
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


def _kc_from_input(preset: str, custom_val: float) -> float:
    if preset in KC_PRESETS and KC_PRESETS[preset][2] is not None:
        return KC_PRESETS[preset][2]
    return round(max(0.1, min(2.0, custom_val)), 2)


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow — 3 steps:
      1. setup   → name, lat/lon, num_zones, flow rate, threshold, Kc preset
      2. et0     → ET0 source
      3. calc_opts → weighting, DST
    Zones are auto-named (Zone 1, Zone 2, …). Everything else is editable later.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    # ── Step 1: everything global ──────────────────────────────────────────

    async def async_step_user(self, user_input=None) -> FlowResult:
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
            vol.Required("kc_preset", default="bermuda"): vol.In(KC_PRESET_KEYS),
            vol.Optional("kc_custom", default=DEFAULT_KC): vol.Coerce(float),
        })

        if user_input is not None:
            kc = _kc_from_input(user_input["kc_preset"], user_input.get("kc_custom", DEFAULT_KC))
            num_zones = user_input["num_zones"]
            zones = [
                {
                    ZONE_ID: f"zone_{i + 1}",
                    ZONE_NAME: f"Zone {i + 1}",
                    ZONE_KC: kc,
                    ZONE_MM_PER_MIN: user_input[CONF_MM_PER_MIN],
                    ZONE_THRESHOLD_MM: user_input[CONF_THRESHOLD_MM],
                    "switch_entity": "",
                    "color": ZONE_COLORS[i % len(ZONE_COLORS)],
                    "pts": [],
                }
                for i in range(num_zones)
            ]
            self._data.update({
                "name": user_input["name"],
                CONF_LAT: user_input[CONF_LAT],
                CONF_LON: user_input[CONF_LON],
                CONF_NORTH_OFFSET: user_input[CONF_NORTH_OFFSET],
                CONF_MM_PER_MIN: user_input[CONF_MM_PER_MIN],
                CONF_THRESHOLD_MM: user_input[CONF_THRESHOLD_MM],
                CONF_BUILDINGS: [],
                CONF_ZONES: zones,
            })
            return await self.async_step_et0()

        kc_hint = " | ".join(
            f"{k}: {v[2]}" for k, v in KC_PRESETS.items() if v[2] is not None
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "ha_lat": str(default_lat),
                "ha_lon": str(default_lon),
                "kc_hint": kc_hint,
            },
        )

    # ── Step 2: ET0 source ─────────────────────────────────────────────────

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

    # ── Step 3: calculation options ────────────────────────────────────────

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
    """Options: edit all global params + advanced JSON for zones/buildings."""

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
