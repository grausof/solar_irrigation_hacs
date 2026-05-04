"""Solar Irrigation integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number"]

CARD_URL = f"/{DOMAIN}/solar-irrigation-card.js"
CARD_VERSION = "0.1.0"
CARD_PATH = Path(__file__).parent / "www" / "solar-irrigation-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the Lovelace card JS and auto-register it as a Lovelace resource."""
    # 1. Serve the JS file as a static HTTP path
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)
    ])
    _LOGGER.debug("Serving Solar Irrigation card at %s", CARD_URL)

    # 2. Auto-register in Lovelace resources (storage mode only).
    #    This is a best-effort operation: if it fails (YAML mode, not yet loaded,
    #    etc.) we log a debug message and the user can add it manually.
    hass.async_create_task(_async_ensure_lovelace_resource(hass))
    return True


async def _async_ensure_lovelace_resource(hass: HomeAssistant) -> None:
    """Add the card JS to Lovelace resources if not already present.

    Works only when Lovelace is in storage mode (the default).
    Safe to call repeatedly — checks for duplicates before inserting.
    """
    resource_url = f"{CARD_URL}?v={CARD_VERSION}"
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            _LOGGER.debug("Lovelace not in hass.data yet — skipping auto-resource registration")
            return

        resources = lovelace.get("resources")
        if resources is None:
            _LOGGER.debug("Lovelace resources not available (YAML mode?) — add resource manually")
            return

        # Load current resources
        if hasattr(resources, "async_load"):
            await resources.async_load()

        # Check if already registered (any version)
        existing = [item.get("url", "") for item in resources.async_items()]
        if any(CARD_URL in u for u in existing):
            _LOGGER.debug("Solar Irrigation card already registered in Lovelace resources")
            return

        await resources.async_create_item({"res_type": "module", "url": resource_url})
        _LOGGER.info(
            "Solar Irrigation: auto-registered Lovelace resource %s — "
            "you may need to refresh your browser (F5).",
            resource_url,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug(
            "Could not auto-register Lovelace resource (%s). "
            "Add it manually: Settings → Dashboards → Resources → Add resource → "
            "URL: %s, Type: JavaScript module",
            err,
            resource_url,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Irrigation from a config entry."""
    config = {**entry.data, **entry.options}
    coordinator = SolarIrrigationCoordinator(hass, config, entry.entry_id)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
