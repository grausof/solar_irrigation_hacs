# Solar Irrigation

A Home Assistant HACS integration that calculates shadow factors for irrigation zones based on building geometry and sun position, then manages irrigation schedules according to plant water deficit.

---

## What it does

Solar Irrigation models the shadows cast by buildings and obstacles onto your garden zones throughout the day. It uses this to:

- Compute a **monthly light factor** (0.0 = always shaded, 1.0 = always in full sun) for every irrigation zone.
- Estimate the **crop evapotranspiration** (ETc) for each zone using the FAO-56 approach: `ETc = ET0 × Kc × light_factor`.
- Accumulate a **water deficit** (mm) over time and trigger irrigation when the deficit exceeds a configurable threshold.
- Expose sensor, binary sensor, and number entities per zone, ready to drive automations or a dedicated Lovelace card.

---

## Requirements

- Home Assistant 2024.1.0 or newer
- Python package `shapely>=2.0.0` (installed automatically by HA from `manifest.json`)
- HACS 1.x

---

## Installation via HACS

1. In HACS, go to **Integrations → Custom repositories**.
2. Add `https://github.com/yourusername/solar-irrigation-hacs` with category **Integration**.
3. Search for **Solar Irrigation** and install it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration** and search for **Solar Irrigation**.

---

## Configuration steps

The integration is configured through a multi-step UI flow.

### Step 1 — Location

| Field | Description |
|-------|-------------|
| **Installation name** | Friendly name for the config entry |
| **Latitude** | Geographic latitude (pre-filled from HA config) |
| **Longitude** | Geographic longitude (pre-filled from HA config) |
| **North offset (degrees)** | Rotation angle to align the coordinate system's Y-axis with geographic North. Use 0 if your building map is already North-aligned. |

### Step 2 — Buildings

Paste a JSON array describing your buildings and obstacles. Each element:

```json
[
  {
    "pts": [
      {"x": 0, "y": 0},
      {"x": 10, "y": 0},
      {"x": 10, "y": 5},
      {"x": 0, "y": 5}
    ],
    "h": 6.5
  }
]
```

- `pts`: polygon vertices in **local metric coordinates** (meters from an arbitrary origin, e.g. SW corner of your garden).
- `h`: building height in meters.

Leave `[]` if there are no obstacles.

### Step 3 — Zones

Paste a JSON array of irrigation zones:

```json
[
  {
    "zone_id": "zone_lawn",
    "name": "Lawn",
    "pts": [
      {"x": 0, "y": 0},
      {"x": 8, "y": 0},
      {"x": 8, "y": 6},
      {"x": 0, "y": 6}
    ],
    "color": "#4CAF50",
    "switch_entity": "switch.irrigation_lawn",
    "mm_per_min": 0.5,
    "threshold_mm": 3.0,
    "kc": 0.7
  }
]
```

| Field | Required | Description |
|-------|----------|-------------|
| `zone_id` | ✅ | Unique identifier (used in entity IDs) |
| `name` | ✅ | Human-readable zone name |
| `pts` | ✅ | Polygon vertices in local metric coords |
| `color` | ❌ | Hex color for the Lovelace card |
| `switch_entity` | ❌ | HA switch entity to control the valve |
| `mm_per_min` | ❌ | Water applied per minute (default: 0.5 mm/min) |
| `threshold_mm` | ❌ | Deficit threshold to trigger irrigation (default: 3.0 mm) |
| `kc` | ❌ | Crop coefficient — scales ET0 (default: 0.7) |

### Step 4 — ET0 Source

| Mode | Description |
|------|-------------|
| `fixed` | Use a constant mm/day value (e.g. 5.0). Good for testing. |
| `entity` | Read ET0 from a numeric HA sensor (e.g. from a weather station). |
| `weather` | Estimate ET0 via the Hargreaves-Samani formula from a HA weather entity. |

### Step 5 — Options

| Option | Description |
|--------|-------------|
| **Weight by irradiance** | If enabled, each time step is weighted by sin²·⁵(elevation) — proportional to solar irradiance. Recommended. |
| **Apply DST correction** | Subtract 1 hour for DST months (April–October, Italian/Central European convention). |

---

## Entities created per zone

For each zone with `zone_id` = `"zone_lawn"` the following entities are created:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.solar_factor_lawn` | Sensor | Monthly light factor (0.0–1.0) for the current month |
| `sensor.water_deficit_lawn` | Sensor (mm) | Accumulated water deficit |
| `sensor.irrigation_duration_lawn` | Sensor (min) | Suggested irrigation duration = deficit / mm_per_min |
| `binary_sensor.should_irrigate_lawn` | Binary Sensor | True when deficit ≥ threshold |
| `number.deficit_override_lawn` | Number (mm) | Manually set the deficit (useful after manual irrigation) |

All entities share a device per zone under **Settings → Devices**.

---

## Linking zones to irrigation switches

The integration computes *when* and *how long* to irrigate; it does **not** automatically turn switches on/off. Use a standard HA automation:

```yaml
alias: "Irrigate Lawn when needed"
trigger:
  - platform: state
    entity_id: binary_sensor.should_irrigate_zone_lawn
    to: "on"
condition:
  - condition: time
    after: "06:00:00"
    before: "09:00:00"
action:
  - service: switch.turn_on
    target:
      entity_id: switch.irrigation_lawn
  - delay:
      minutes: "{{ states('sensor.irrigation_duration_zone_lawn') | float }}"
  - service: switch.turn_off
    target:
      entity_id: switch.irrigation_lawn
  # Reset deficit after irrigation
  - service: number.set_value
    target:
      entity_id: number.deficit_override_zone_lawn
    data:
      value: 0
```

---

## Lovelace card

Add the custom card from `frontend/solar-irrigation-card.js` as a Lovelace resource:

```yaml
# configuration.yaml or through UI: Settings → Dashboards → Resources
resources:
  - url: /hacsfiles/solar_irrigation/solar-irrigation-card.js
    type: module
```

Then use it in a dashboard:

```yaml
type: custom:solar-irrigation-card
title: My Garden
zones:
  - zone_id: zone_lawn
    name: Lawn
    color: "#4CAF50"
    factor_entity: sensor.solar_factor_zone_lawn
    deficit_entity: sensor.water_deficit_zone_lawn
    duration_entity: sensor.irrigation_duration_zone_lawn
    irrigate_entity: binary_sensor.should_irrigate_zone_lawn
  - zone_id: zone_flower_bed
    name: Flower Bed
    color: "#FF7043"
    factor_entity: sensor.solar_factor_zone_flower_bed
    deficit_entity: sensor.water_deficit_zone_flower_bed
    duration_entity: sensor.irrigation_duration_zone_flower_bed
    irrigate_entity: binary_sensor.should_irrigate_zone_flower_bed
```

---

## How it works (technical)

1. **Sun position** is calculated using a simplified solar geometry model (equation of time, declination, hour angle) matching the original JavaScript tool.
2. **Shadow polygons** are extruded from building footprints in the anti-sun direction, with length = `h / tan(elevation)`.
3. **Zone shadow fraction** is computed via [Shapely](https://shapely.readthedocs.io/) polygon intersection (precise), with a point-in-polygon sampling fallback if Shapely is unavailable.
4. **Monthly factors** are computed by integrating over daylight hours at 15-minute intervals for the 15th of each month.
5. **Water deficit** accumulates daily: `deficit += ET0 × Kc × light_factor`. After irrigation, `deficit` is reduced by `duration_min × mm_per_min`.

---

## Coordinate system

All building and zone polygons use a **local metric coordinate system** (meters). The origin (0, 0) can be any convenient reference point (e.g. the SW corner of your garden). The `north_offset` parameter rotates the coordinate system so that the Y-axis aligns with geographic North.

Helper functions `latlon_to_local` and `local_to_latlon` in `solar_math.py` convert between geographic and local coordinates if needed.
