"""
Stage 2a — Shapely shadow polygon analysis.

Computes shadow_factor (0=shaded, 1=exposed) per hour for 168 heatwave hours
(July 15–21) at a building's lat/lon using surrounding building footprints
fetched from OpenStreetMap.

Algorithm per hour:
  1. If sun is below horizon → shadow_factor = 0 (no direct radiation anyway).
  2. For each surrounding building:
     a. Convert footprint from EPSG:4326 (lat/lon) to local metres
        (building under analysis at origin 0, 0).
     b. Shadow displacement:
          shadow_length = H / tan(sun_elevation)
          shadow_dir   = (sun_azimuth + 180) % 360   [points away from sun]
          dx = shadow_length × sin(shadow_dir_rad)   [East component]
          dy = shadow_length × cos(shadow_dir_rad)   [North component]
     c. Shadow polygon = convex_hull( footprint ∪ translate(footprint, dx, dy) )
  3. shadow_factor = 0 if origin (0, 0) ∈ ⋃(shadow polygons), else 1.

The result is one shadow_factor per hour at the building location.  All facades
of that building share this map; facade-specific exposure (sun behind the wall)
is handled separately by pvlib's POA irradiance in solar.py.

SOURCE: HVRA_build_reference_4.md §Stage 1 — pvlib + shapely shadow geometry.
"""

from __future__ import annotations
import logging
import math
from typing import List, Optional

from .epw_loader import HourlyClimate

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import Point
    from shapely.affinity import affine_transform, translate
    from shapely.ops import unary_union
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False

try:
    import pvlib
    import pandas as pd
    _PVLIB_OK = True
except ImportError:
    _PVLIB_OK = False

# PROXY: Default building height used when OSM 'height' or 'building:levels' is absent.
# 9 m = 3 storeys, representative for Barcelona Eixample / Gràcia.
# SOURCE: Barcelona building height statistics, Ajuntament de Barcelona urban atlas.
DEFAULT_BUILDING_HEIGHT_M = 9.0

# Metres per degree conversions (approximate, valid for small areas).
LAT_M_PER_DEG = 111_000.0


def get_solar_positions(lat: float, lon: float, climate_hours: List[HourlyClimate]):
    """
    Compute sun azimuth and apparent elevation for each EPW heatwave hour.

    Uses 2023 (non-leap year) as the reference year, with mid-hour timestamps.
    Returns (timestamps, solar_pos DataFrame) or (None, None) if pvlib unavailable.

    SOURCE: pvlib — Holmgren et al. (2018), JOSS.
    """
    if not _PVLIB_OK:
        return None, None
    location = pvlib.location.Location(latitude=lat, longitude=lon)
    timestamps = pd.DatetimeIndex([
        pd.Timestamp(
            f"2023-{h.month:02d}-{h.day:02d} {h.hour - 1:02d}:30:00", tz="UTC"
        )
        for h in climate_hours
    ])
    solar_pos = location.get_solarposition(timestamps)
    return timestamps, solar_pos


def compute_building_shadow_map(
    buildings_gdf,
    lat: float,
    lon: float,
    solar_pos,
    climate_hours: List[HourlyClimate],
) -> tuple[list[float], list[float], list[float]]:
    """
    Compute per-hour shadow_factor for the building at (lat, lon).

    Parameters
    ----------
    buildings_gdf : GeoDataFrame | None
        Surrounding building footprints from OSM (EPSG:4326).
        None → returns all-ones (no obstruction assumed).
    lat, lon : float
        Building location. Maps to origin (0, 0) in local metre system.
    solar_pos : pvlib DataFrame | None
        Pre-computed solar positions for the 168 heatwave hours.
    climate_hours : List[HourlyClimate]
        168 heatwave climate records (for hour ordering).

    Returns
    -------
    shadow_map : list[float]
        168 values: 0.0 = shaded by surrounding building, 1.0 = exposed.
    azimuth_map : list[float]
        168 sun azimuth values in degrees (0 = North, 90 = East).
    elevation_map : list[float]
        168 sun apparent elevation values in degrees.
    """
    n = len(climate_hours)

    if (
        buildings_gdf is None
        or not _SHAPELY_OK
        or not _PVLIB_OK
        or solar_pos is None
    ):
        logger.warning(
            "Shadow analysis unavailable (missing osmnx/shapely/pvlib or OSM fetch failed). "
            "shadow_factor = 1 assumed for all hours."
        )
        return [1.0] * n, [0.0] * n, [0.0] * n

    # ── Pre-process building footprints: convert to local metres ────────────
    lon_m_per_deg = LAT_M_PER_DEG * math.cos(math.radians(lat))
    # affine_transform matrix [a, b, d, e, xoff, yoff]:
    #   new_x = a*lon + b*lat + xoff = lon_m_per_deg*(lon - origin_lon)
    #   new_y = d*lon + e*lat + yoff = LAT_M_PER_DEG*(lat - origin_lat)
    matrix = [
        lon_m_per_deg, 0.0,
        0.0, LAT_M_PER_DEG,
        -lon_m_per_deg * lon,
        -LAT_M_PER_DEG * lat,
    ]

    buildings_local: list[tuple] = []  # (shapely_polygon_m, height_m)
    for _, row in buildings_gdf.iterrows():
        geom = getattr(row, "geometry", None)
        if geom is None or geom.is_empty:
            continue
        try:
            geom_m = affine_transform(geom, matrix)
        except Exception:
            continue
        if geom_m.is_empty or not geom_m.is_valid:
            continue

        height_m = _parse_height(row)
        buildings_local.append((geom_m, height_m))

    if not buildings_local:
        return [1.0] * n, [0.0] * n, [0.0] * n

    origin = Point(0.0, 0.0)   # building under analysis

    shadow_map: list[float] = []
    azimuth_map: list[float] = []
    elevation_map: list[float] = []

    for i in range(n):
        elevation = float(solar_pos["apparent_elevation"].iloc[i])
        azimuth = float(solar_pos["azimuth"].iloc[i])
        azimuth_map.append(round(azimuth, 1))
        elevation_map.append(round(elevation, 2))

        if elevation <= 0.0:
            shadow_map.append(0.0)   # night — no direct radiation
            continue

        # ── Build shadow polygon union for this hour ─────────────────────────
        shadow_polygons = []
        shadow_dir_deg = (azimuth + 180.0) % 360.0
        shadow_dir_rad = math.radians(shadow_dir_deg)
        dx_per_m = math.sin(shadow_dir_rad)   # East component per metre of height
        dy_per_m = math.cos(shadow_dir_rad)   # North component per metre of height
        # Shadow length per unit height (horizontal distance cast per 1 m of building height)
        shadow_len_per_m = 1.0 / math.tan(math.radians(elevation))

        for footprint_m, height_m in buildings_local:
            # Skip building if it could not possibly cast a shadow reaching origin.
            # The max shadow reach of this building = height * shadow_len_per_m.
            # Centroid distance check (fast pre-filter).
            centroid = footprint_m.centroid
            dist_to_origin = math.hypot(centroid.x, centroid.y)
            max_shadow_reach = height_m * shadow_len_per_m
            if dist_to_origin > max_shadow_reach + 50.0:
                # + 50 m slack to account for building footprint extent
                continue

            # Full shadow polygon
            dx = dx_per_m * height_m * shadow_len_per_m
            dy = dy_per_m * height_m * shadow_len_per_m

            try:
                shadow_cast = translate(footprint_m, xoff=dx, yoff=dy)
                shadow_poly = unary_union([footprint_m, shadow_cast]).convex_hull
                shadow_polygons.append(shadow_poly)
            except Exception:
                continue

        if not shadow_polygons:
            shadow_map.append(1.0)
            continue

        try:
            all_shadows = unary_union(shadow_polygons)
            shadow_map.append(0.0 if all_shadows.contains(origin) else 1.0)
        except Exception:
            shadow_map.append(1.0)

    return shadow_map, azimuth_map, elevation_map


def per_facade_shadow_stats(
    shadow_map: list[float],
    azimuth_map: list[float],
    elevation_map: list[float],
    facade_orientation_deg: float,
) -> tuple[float, int]:
    """
    Compute the average shadow_factor and shaded-hour count for one facade,
    restricted to hours when the sun is on the facade's exposed side.

    A facade with bearing B is exposed when the angular difference between
    the sun azimuth and B is < 90° (sun is in front of the facade, not behind).

    Returns (avg_shadow_factor, exposed_hours_count).
    """
    exposed_sf: list[float] = []
    for sf, az, el in zip(shadow_map, azimuth_map, elevation_map):
        if el <= 0.0:
            continue
        angle_diff = abs((az - facade_orientation_deg + 180) % 360 - 180)
        if angle_diff < 90.0:
            exposed_sf.append(sf)
    if not exposed_sf:
        return 1.0, 0
    avg = sum(exposed_sf) / len(exposed_sf)
    exposed_hours = len(exposed_sf)
    return round(avg, 3), exposed_hours


def _parse_height(row) -> float:
    """Extract building height (m) from an OSM row.  Falls back to DEFAULT."""
    for field in ("height", "building:height"):
        v = row.get(field)
        if v:
            try:
                return float(str(v).replace("m", "").strip())
            except ValueError:
                pass
    levels = row.get("building:levels")
    if levels:
        try:
            return float(levels) * 3.0   # PROXY: 3 m per storey
        except ValueError:
            pass
    return DEFAULT_BUILDING_HEIGHT_M
