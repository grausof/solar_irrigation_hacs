"""
Solar math: sun position, shadow polygons, zone shadow fractions.

Ported from shadow_tool.html (JavaScript) to Python.
Uses Shapely for polygon intersection instead of OffscreenCanvas pixel counting.

Coordinate system:
  - Buildings and zones are stored as lists of {x, y} points in LOCAL METRIC coords (meters).
  - Origin (0,0) is arbitrary reference point (e.g. SW corner of the garden).
  - north_offset: degrees to rotate to align the canvas Y axis with geographic North.
  - Shadow length = h / tan(el) meters.
  - Shadow direction = sun azimuth + 180° (opposite to sun), corrected for north_offset.

Shadow algorithm (same as JS):
  1. For each building polygon, compute shadow polygon (extrusion toward anti-sun direction).
  2. For each zone, compute fraction of zone area covered by union of shadow polygons.
  3. shadow_frac = (covered area) / (zone area)
  4. light_frac  = 1 - shadow_frac
"""

import math
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

try:
    from shapely.geometry import Polygon as ShapelyPolygon, MultiPolygon
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    _LOGGER.warning("Shapely not available — shadow fractions will be approximated with PIP sampling")


# ─────────────────────────── DST ────────────────────────────

def is_dst(month: int) -> bool:
    """Italy DST: April–October (approx). Generalized: months 4–10."""
    return 4 <= month <= 10


def dst_offset(month: int, use_dst: bool = True) -> int:
    """Hours to subtract from local time to get standard time."""
    return 1 if (use_dst and is_dst(month)) else 0


# ─────────────────────────── SUN POSITION ────────────────────────────

def sun_pos(month: int, hour: float, lat: float, lon: float, use_dst: bool = True) -> Optional[dict]:
    """
    Calculate sun azimuth and elevation for given month, local hour, lat, lon.

    Returns dict {az: degrees (0=N, 90=E, 180=S, 270=W), el: degrees above horizon}
    or None if sun is below 0.5° elevation.
    """
    lat_r = math.radians(lat)
    solar_hour = hour - dst_offset(month, use_dst)

    doy_base = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    doy = doy_base[month - 1] + 15

    B = 2 * math.pi * (doy - 81) / 364
    eot = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    dec = math.radians(23.45 * math.sin(2 * math.pi * (doy - 81) / 365))

    lstm = 15 * round(lon / 15)
    tc = 4 * (lon - lstm) + eot
    lst = solar_hour + tc / 60
    hra = math.radians((lst - 12) * 15)

    sin_el = math.sin(lat_r) * math.sin(dec) + math.cos(lat_r) * math.cos(dec) * math.cos(hra)
    sin_el = max(-1.0, min(1.0, sin_el))
    el = math.asin(sin_el)

    if math.degrees(el) < 0.5:
        return None

    cos_az_num = math.sin(dec) - math.sin(lat_r) * sin_el
    cos_az_den = math.cos(lat_r) * math.cos(el)
    if abs(cos_az_den) < 1e-10:
        return None
    cos_az = max(-1.0, min(1.0, cos_az_num / cos_az_den))
    az = math.acos(cos_az)
    if math.sin(hra) > 0:
        az = 2 * math.pi - az

    return {"el": math.degrees(el), "az": math.degrees(az)}


# ─────────────────────────── SHADOW GEOMETRY ────────────────────────────

def shadow_poly(pts: list, h: float, sun: dict, north_offset: float = 0) -> list:
    """
    Compute shadow polygon cast by a building with vertices `pts` and height `h` meters.
    Sun position given as {az, el} in degrees.
    north_offset: degrees to rotate to align canvas Y with geographic North.

    Returns list of {x, y} points or [] if no shadow (sun below horizon or behind building).
    """
    if len(pts) < 3:
        return []

    shadow_len = h / math.tan(math.radians(sun["el"]))
    saz = (sun["az"] + 180) % 360
    ang = math.radians(north_offset + saz)
    sdx = shadow_len * math.cos(ang)
    sdy = shadow_len * math.sin(ang)

    n = len(pts)
    L = math.hypot(sdx, sdy) or 1.0
    sux, suy = sdx / L, sdy / L

    # Compute winding (CW vs CCW)
    area = sum(pts[i]["x"] * pts[(i+1)%n]["y"] - pts[(i+1)%n]["x"] * pts[i]["y"] for i in range(n))
    cw = area >= 0

    # Determine which edges face away from sun (back-facing = cast shadow)
    edge_back = []
    for i in range(n):
        j = (i + 1) % n
        ex = pts[j]["x"] - pts[i]["x"]
        ey = pts[j]["y"] - pts[i]["y"]
        nx = ey if cw else -ey
        ny = -ex if cw else ex
        edge_back.append((nx * sux + ny * suy) > 0)

    if not any(edge_back):
        return []

    if all(edge_back):
        result = list(pts)
        for i in range(n - 1, -1, -1):
            result.append({"x": pts[i]["x"] + sdx, "y": pts[i]["y"] + sdy})
        return result

    # Find start of first back-facing run
    start = 0
    for i in range(n):
        prev = (i - 1) % n
        if not edge_back[prev] and edge_back[i]:
            start = i
            break

    result = []
    for k in range(n):
        i = (start + k) % n
        prev = (i - 1) % n
        pB = edge_back[prev]
        cB = edge_back[i]
        if not pB and not cB:
            result.append({"x": pts[i]["x"], "y": pts[i]["y"]})
        elif not pB and cB:
            result.append({"x": pts[i]["x"], "y": pts[i]["y"]})
            result.append({"x": pts[i]["x"] + sdx, "y": pts[i]["y"] + sdy})
        elif pB and cB:
            result.append({"x": pts[i]["x"] + sdx, "y": pts[i]["y"] + sdy})
        else:
            result.append({"x": pts[i]["x"] + sdx, "y": pts[i]["y"] + sdy})
            result.append({"x": pts[i]["x"], "y": pts[i]["y"]})

    return result


def compute_shadow_polys(buildings: list, sun: dict, north_offset: float = 0) -> list:
    """Compute all shadow polygons for a list of buildings given a sun position."""
    result = []
    for b in buildings:
        pts = b.get("pts", [])
        h = b.get("h", 3.0)
        if len(pts) >= 3:
            sp = shadow_poly(pts, h, sun, north_offset)
            if len(sp) >= 3:
                result.append(sp)
    return result


def _pts_to_shapely(pts: list) -> Optional["ShapelyPolygon"]:
    """Convert list of {x,y} to Shapely Polygon, or None if invalid."""
    if len(pts) < 3:
        return None
    try:
        poly = ShapelyPolygon([(p["x"], p["y"]) for p in pts])
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if poly.area > 0 else None
    except Exception:
        return None


def zone_shadow_frac_shapely(zone_pts: list, shadow_polys: list) -> float:
    """
    Compute fraction of zone area covered by shadow polygons using Shapely.
    More precise than pixel counting (used in web tool).
    """
    zone = _pts_to_shapely(zone_pts)
    if zone is None or zone.area == 0:
        return 0.0
    if not shadow_polys:
        return 0.0

    shadow_shapes = [_pts_to_shapely(sp) for sp in shadow_polys]
    shadow_shapes = [s for s in shadow_shapes if s is not None]
    if not shadow_shapes:
        return 0.0

    try:
        shadow_union = unary_union(shadow_shapes)
        intersection = zone.intersection(shadow_union)
        return min(1.0, intersection.area / zone.area)
    except Exception as e:
        _LOGGER.warning("Shapely intersection error: %s", e)
        return 0.0


def zone_shadow_frac_pip(zone_pts: list, shadow_polys: list, samples: int = 50) -> float:
    """
    Fallback: point-in-polygon sampling when Shapely is not available.
    Less precise but no external dependency.
    """
    if len(zone_pts) < 3 or not shadow_polys:
        return 0.0

    xs = [p["x"] for p in zone_pts]
    ys = [p["y"] for p in zone_pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    def pip(px, py, poly):
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]["x"], poly[i]["y"]
            xj, yj = poly[j]["x"], poly[j]["y"]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    zone_count = shadow_count = 0
    step = max((x1 - x0) / samples, (y1 - y0) / samples, 0.01)
    px = x0
    while px <= x1:
        py = y0
        while py <= y1:
            if pip(px, py, zone_pts):
                zone_count += 1
                if any(pip(px, py, sp) for sp in shadow_polys):
                    shadow_count += 1
            py += step
        px += step

    return shadow_count / zone_count if zone_count > 0 else 0.0


def zone_shadow_frac(zone_pts: list, shadow_polys: list) -> float:
    """Compute zone shadow fraction, using Shapely if available."""
    if SHAPELY_AVAILABLE:
        return zone_shadow_frac_shapely(zone_pts, shadow_polys)
    return zone_shadow_frac_pip(zone_pts, shadow_polys)


# ─────────────────────────── MONTHLY ANALYSIS ────────────────────────────

def month_frac(
    month: int,
    buildings: list,
    zones: list,
    lat: float,
    lon: float,
    weighted: bool = True,
    use_dst: bool = True,
    north_offset: float = 0,
) -> list:
    """
    Compute the light fraction (1 - shadow fraction) for each zone for a given month.

    Iterates over daylight hours at 15-min intervals, weights each step by
    sin(el)^1.5 if weighted=True (irradiance-proportional), or 1.0 (uniform).

    Returns list of floats [0.0–1.0] per zone (1.0 = always in sun, 0.0 = always in shadow).
    """
    max_h = 21 if (use_dst and is_dst(month)) else 20
    total = 0.0
    shaded_w = [0.0] * len(zones)

    for hi in range(5 * 4, max_h * 4 + 1):
        hour = hi / 4.0
        sun = sun_pos(month, hour, lat, lon, use_dst)
        if sun is None:
            continue
        sin_el = math.sin(math.radians(sun["el"]))
        if sin_el <= 0:
            continue
        w = math.pow(sin_el, 1.5) if weighted else 1.0
        total += w

        shadow_polys = compute_shadow_polys(buildings, sun, north_offset)
        for zi, zone in enumerate(zones):
            pts = zone.get("pts", [])
            if len(pts) < 3:
                continue
            frac = zone_shadow_frac(pts, shadow_polys)
            shaded_w[zi] += w * frac

    if total == 0:
        return [1.0] * len(zones)
    return [round(1.0 - shaded_w[i] / total, 3) for i in range(len(zones))]


def compute_all_monthly_factors(
    buildings: list,
    zones: list,
    lat: float,
    lon: float,
    weighted: bool = True,
    use_dst: bool = True,
    north_offset: float = 0,
) -> dict:
    """
    Compute monthly shadow light factors for all 12 months.

    Returns dict: {zone_id: [f_jan, f_feb, ..., f_dec]}
    """
    results = {zone.get("zone_id", str(i)): [] for i, zone in enumerate(zones)}

    for month in range(1, 13):
        fracs = month_frac(month, buildings, zones, lat, lon, weighted, use_dst, north_offset)
        for i, zone in enumerate(zones):
            zid = zone.get("zone_id", str(i))
            results[zid].append(fracs[i])

    return results


def latlon_to_local(lat: float, lon: float, origin_lat: float, origin_lon: float) -> dict:
    """
    Convert geographic coordinates to local metric coordinates (meters).
    Simple tangent plane approximation, accurate for small areas (<1 km).
    """
    x = (lon - origin_lon) * math.cos(math.radians(origin_lat)) * 111320
    y = (lat - origin_lat) * 111320
    return {"x": x, "y": y}


def local_to_latlon(x: float, y: float, origin_lat: float, origin_lon: float) -> dict:
    """Inverse of latlon_to_local."""
    lat = origin_lat + y / 111320
    lon = origin_lon + x / (math.cos(math.radians(origin_lat)) * 111320)
    return {"lat": lat, "lon": lon}
