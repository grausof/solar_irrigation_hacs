DOMAIN = "solar_irrigation"
CONF_LAT = "latitude"
CONF_LON = "longitude"
CONF_NORTH_OFFSET = "north_offset"  # degrees, rotation to align north on map
CONF_BUILDINGS = "buildings"  # JSON list of {pts:[{x,y}], h:meters}
CONF_ZONES = "zones"  # JSON list of zone dicts
CONF_ET0_MODE = "et0_mode"
CONF_ET0_ENTITY = "et0_entity"
CONF_ET0_FIXED = "et0_fixed"
CONF_USE_DST = "use_dst"
CONF_WEIGHTED = "irradiance_weighted"
CONF_MM_PER_MIN = "mm_per_min"     # global default flow rate
CONF_THRESHOLD_MM = "threshold_mm"  # global default irrigation threshold

ET0_MODE_WEATHER = "weather"
ET0_MODE_ENTITY = "entity"
ET0_MODE_FIXED = "fixed"

# Zone config keys
ZONE_NAME = "name"
ZONE_ID = "zone_id"
ZONE_PTS = "pts"  # list of {x,y} in local meters from origin
ZONE_COLOR = "color"
ZONE_SWITCH_ENTITY = "switch_entity"
ZONE_MM_PER_MIN = "mm_per_min"
ZONE_THRESHOLD_MM = "threshold_mm"
ZONE_KC = "kc"  # crop coefficient

# Kc presets: key → (label_en, label_it, kc_value)
KC_PRESETS: dict[str, tuple[str, str, float]] = {
    "bermuda":  ("Bermuda grass (Cynodon dactylon)",    "Gramigna Bermuda (Cynodon dactylon)",    0.65),
    "ryegrass": ("Italian ryegrass (Lolium perenne)",   "Loietto italico (Lolium perenne)",        0.85),
    "fescue":   ("Tall fescue (Festuca arundinacea)",   "Festuca alta (Festuca arundinacea)",      0.80),
    "zoysia":   ("Zoysia grass",                         "Erba Zoysia",                             0.60),
    "custom":   ("Custom (enter Kc manually)",           "Personalizzato (inserisci Kc manuale)",   None),
}
KC_PRESET_KEYS = list(KC_PRESETS.keys())

# Update intervals
SCAN_INTERVAL_MINUTES = 30

# Default values
DEFAULT_ET0_FIXED = 5.0  # mm/day
DEFAULT_MM_PER_MIN = 0.5
DEFAULT_THRESHOLD_MM = 3.0
DEFAULT_KC = 0.65          # Bermuda default
DEFAULT_NORTH_OFFSET = 0
DEFAULT_WEIGHTED = True
DEFAULT_USE_DST = True
