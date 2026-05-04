"""Solar Irrigation integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number"]

CARD_URL = f"/{DOMAIN}/solar-irrigation-card.js"
CARD_VERSION = "0.1.0"
CARD_PATH = Path(__file__).parent / "www" / "solar-irrigation-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the Lovelace card JS and schedule its Lovelace resource registration."""
    # Serve the JS file as a static HTTP path
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)
    ])
    _LOGGER.debug("Serving Solar Irrigation card at %s", CARD_URL)

    # Register the Lovelace resource after HA is fully started so that
    # hass.data["lovelace"] is guaranteed to be populated.
    async def _on_started(_event=None) -> None:
        await _async_ensure_lovelace_resource(hass)

    if hass.is_running:
        # HA already running (e.g. integration reloaded) — register immediately
        hass.async_create_task(_on_started())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)

    return True


async def _async_ensure_lovelace_resource(hass: HomeAssistant) -> None:
    """Add the card JS to Lovelace resources if not already present.

    Works only when Lovelace is in storage mode (the default).
    Safe to call repeatedly — checks for duplicates before inserting.
    On success the user only needs a browser refresh (F5).
    """
    resource_url = f"{CARD_URL}?v={CARD_VERSION}"
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            _LOGGER.debug("Lovelace not found in hass.data — resource must be added manually")
            return

        resources = lovelace.get("resources")
        if resources is None:
            _LOGGER.debug(
                "Lovelace running in YAML mode — add the resource manually: "
                "Settings → Dashboards → Resources → %s (JavaScript module)",
                resource_url,
            )
            return

        if hasattr(resources, "async_load"):
            await resources.async_load()

        # Avoid duplicates across restarts / version changes
        existing = [item.get("url", "") for item in resources.async_items()]
        if any(CARD_URL in u for u in existing):
            _LOGGER.debug("Solar Irrigation card already in Lovelace resources — skipping")
            return

        await resources.async_create_item({"res_type": "module", "url": resource_url})
        _LOGGER.info(
            "Solar Irrigation: Lovelace resource registered (%s). "
            "Please do a hard refresh (Ctrl+Shift+R / Cmd+Shift+R) in your browser.",
            resource_url,
        )

    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not auto-register Lovelace resource: %s. "
            "Add it manually: Settings → Dashboards → Resources → "
            "URL: %s  Type: JavaScript module",
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
