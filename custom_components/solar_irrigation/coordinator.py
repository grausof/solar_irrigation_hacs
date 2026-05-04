"""DataUpdateCoordinator for Solar Irrigation."""
import logging
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_LAT, CONF_LON, CONF_NORTH_OFFSET, CONF_BUILDINGS, CONF_ZONES,
    CONF_ET0_MODE, CONF_ET0_ENTITY, CONF_ET0_FIXED, CONF_USE_DST, CONF_WEIGHTED,
    ET0_MODE_WEATHER, ET0_MODE_ENTITY, ET0_MODE_FIXED,
    ZONE_ID, ZONE_NAME, ZONE_MM_PER_MIN, ZONE_THRESHOLD_MM, ZONE_KC,
    DEFAULT_ET0_FIXED, DEFAULT_MM_PER_MIN, DEFAULT_THRESHOLD_MM, DEFAULT_KC,
    SCAN_INTERVAL_MINUTES,
)
from .solar_math import compute_all_monthly_factors

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=SCAN_INTERVAL_MINUTES)


class SolarIrrigationCoordinator(DataUpdateCoordinator):
    """Manages state for all solar irrigation zones."""

    def __init__(self, hass: HomeAssistant, config: dict, entry_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.config = config
        self.entry_id = entry_id
        self._monthly_factors: dict = {}  # {zone_id: [f1..f12]}
        self._deficit: dict = {}           # {zone_id: float mm}
        self._last_et0_date = None
        self._last_factor_month = None

    @property
    def zones(self) -> list:
        return self.config.get(CONF_ZONES, [])

    @property
    def buildings(self) -> list:
        return self.config.get(CONF_BUILDINGS, [])

    async def _async_update_data(self) -> dict:
        """Fetch and update all zone data."""
        try:
            now = dt_util.now()
            month = now.month

            # Recompute monthly factors if month changed or first run
            if self._last_factor_month != month:
                await self._recompute_factors()
                self._last_factor_month = month

            # Update ET0 and deficit once per day (at first update of the day)
            today = now.date()
            if self._last_et0_date != today:
                et0 = await self._get_et0()
                self._update_deficit(et0, month)
                self._last_et0_date = today

            return self._build_state(month)

        except Exception as err:
            raise UpdateFailed(f"Solar irrigation update error: {err}") from err

    async def _recompute_factors(self) -> None:
        """Compute monthly shadow factors in executor (CPU-bound)."""
        cfg = self.config
        lat = cfg.get(CONF_LAT, 45.0)
        lon = cfg.get(CONF_LON, 9.0)
        north_off = cfg.get(CONF_NORTH_OFFSET, 0)
        weighted = cfg.get(CONF_WEIGHTED, True)
        use_dst = cfg.get(CONF_USE_DST, True)

        def _compute():
            return compute_all_monthly_factors(
                self.buildings, self.zones, lat, lon, weighted, use_dst, north_off
            )

        self._monthly_factors = await self.hass.async_add_executor_job(_compute)
        _LOGGER.info("Recomputed monthly shadow factors for %d zones", len(self.zones))

    async def _get_et0(self) -> float:
        """Get ET0 value from configured source."""
        cfg = self.config
        mode = cfg.get(CONF_ET0_MODE, ET0_MODE_FIXED)

        if mode == ET0_MODE_FIXED:
            return float(cfg.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED))

        if mode == ET0_MODE_ENTITY:
            entity_id = cfg.get(CONF_ET0_ENTITY, "")
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    try:
                        return float(state.state)
                    except ValueError:
                        pass
            _LOGGER.warning("ET0 entity %s unavailable, using fixed default", entity_id)
            return float(cfg.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED))

        if mode == ET0_MODE_WEATHER:
            return await self._et0_from_weather()

        return float(cfg.get(CONF_ET0_FIXED, DEFAULT_ET0_FIXED))

    async def _et0_from_weather(self) -> float:
        """
        Estimate ET0 using Hargreaves-Samani from HA weather entity.
        ET0 = 0.0023 * (T_mean + 17.8) * sqrt(T_max - T_min) * Ra
        Ra (extraterrestrial radiation) approximated from current month.
        """
        weather_entity = self.config.get(CONF_ET0_ENTITY, "")
        if not weather_entity:
            return DEFAULT_ET0_FIXED

        state = self.hass.states.get(weather_entity)
        if not state or state.state in ("unknown", "unavailable"):
            return DEFAULT_ET0_FIXED

        attrs = state.attributes
        t = attrs.get("temperature", 20)
        try:
            t = float(t)
        except (TypeError, ValueError):
            t = 20.0

        # Estimate T_max/T_min from forecast if available, else use ±5°C as rough estimate
        forecast = attrs.get("forecast", [])
        if forecast and len(forecast) > 0:
            try:
                t_max = float(forecast[0].get("temperature", t + 5))
                t_min = float(forecast[0].get("templow", t - 5))
            except (TypeError, ValueError):
                t_max, t_min = t + 5, t - 5
        else:
            t_max, t_min = t + 5, t - 5

        t_mean = (t_max + t_min) / 2
        lat = math.radians(self.config.get(CONF_LAT, 45.0))
        month = dt_util.now().month
        doy_mid = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349][month - 1]
        dr = 1 + 0.033 * math.cos(2 * math.pi * doy_mid / 365)
        dec = 0.409 * math.sin(2 * math.pi * doy_mid / 365 - 1.39)
        ws = math.acos(-math.tan(lat) * math.tan(dec))
        Ra = (24 * 60 / math.pi) * 0.0820 * dr * (
            ws * math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.sin(ws)
        )

        dt_range = max(0.01, t_max - t_min)
        et0 = 0.0023 * (t_mean + 17.8) * math.sqrt(dt_range) * Ra
        return round(max(0.5, min(15.0, et0)), 2)

    def _update_deficit(self, et0: float, month: int) -> None:
        """Update water deficit for each zone based on today's ET0."""
        for zone in self.zones:
            zid = zone.get(ZONE_ID, zone.get(ZONE_NAME, "unknown"))
            factors = self._monthly_factors.get(zid, [1.0] * 12)
            fz = factors[month - 1] if len(factors) >= month else 1.0
            kc = zone.get(ZONE_KC, DEFAULT_KC)
            etc = et0 * kc * fz  # mm/day water need for this zone

            # Deficit accumulates: positive = needs water
            current = self._deficit.get(zid, 0.0)
            self._deficit[zid] = round(current + etc, 2)

    def reduce_deficit(self, zone_id: str, duration_min: float) -> None:
        """Call after irrigation to reduce deficit by water applied."""
        for zone in self.zones:
            zid = zone.get(ZONE_ID, zone.get(ZONE_NAME, "unknown"))
            if zid == zone_id:
                mm_per_min = zone.get(ZONE_MM_PER_MIN, DEFAULT_MM_PER_MIN)
                applied = duration_min * mm_per_min
                self._deficit[zid] = max(0.0, self._deficit.get(zid, 0.0) - applied)
                break

    def override_deficit(self, zone_id: str, value: float) -> None:
        """Manually override deficit value (from number entity)."""
        self._deficit[zone_id] = max(0.0, value)
        self.async_set_updated_data(self._build_state(dt_util.now().month))

    def _build_state(self, month: int) -> dict:
        """Build the state dict returned by coordinator.data."""
        state = {}
        for zone in self.zones:
            zid = zone.get(ZONE_ID, zone.get(ZONE_NAME, "unknown"))
            factors = self._monthly_factors.get(zid, [1.0] * 12)
            fz = factors[month - 1] if len(factors) >= month else 1.0
            deficit = self._deficit.get(zid, 0.0)
            mm_per_min = zone.get(ZONE_MM_PER_MIN, DEFAULT_MM_PER_MIN)
            threshold = zone.get(ZONE_THRESHOLD_MM, DEFAULT_THRESHOLD_MM)
            duration = round(deficit / mm_per_min, 1) if mm_per_min > 0 else 0.0
            should_irrigate = deficit >= threshold

            state[zid] = {
                "shadow_factor": round(fz, 3),
                "monthly_factors": factors,
                "deficit": deficit,
                "duration_min": duration,
                "should_irrigate": should_irrigate,
                "zone_name": zone.get(ZONE_NAME, zid),
                "zone_color": zone.get("color", "#4CAF50"),
            }
        return state
