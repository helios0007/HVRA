import asyncio
import base64
import logging
import math
from io import BytesIO
from typing import Dict, List, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless backend — Tk crashes when used from worker threads
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from shapely.geometry import Polygon, Point

from infrared_sdk.analyses.types import (
    AnalysesName,
    TcsModelBaseRequest,
    TcsModelRequest,
    TcsSubtype,
    UtciModelBaseRequest,
    UtciModelRequest,
)
from infrared_sdk.models import Location, TimePeriod

from services.infrared_client import get_infrared_client

logger = logging.getLogger(__name__)


def _degrees_to_meters(degrees: float, latitude: float) -> float:
    """Convert degrees to meters at given latitude."""
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(latitude))
    return degrees * meters_per_deg_lon


# ── Urban → building grounding signals (derived from already-fetched data) ──────
# Consumed by the building-level tool via the frontend `urban_context` blob.

# Coarse shortwave albedo per ground-material family. Names are matched by
# substring against the Infrared ground_materials layer keys. Values are typical
# midday albedos (Oke, Boundary Layer Climates; Santamouris 2013).
_GROUND_ALBEDO = {
    "water": 0.06, "asphalt": 0.10, "road": 0.10, "tarmac": 0.10,
    "concrete": 0.30, "pavement": 0.27, "paving": 0.27, "stone": 0.25,
    "soil": 0.20, "sand": 0.30, "bare": 0.20, "gravel": 0.20,
    "grass": 0.23, "vegetation": 0.20, "tree": 0.18, "park": 0.22,
    "roof": 0.20, "building": 0.20,
}


def _building_footprints(buildings_list):
    """Return [(cx, cy, height_m), ...] in local metric space for each building.

    Infrared returns building vertices as a flat [x,y,z, x,y,z, ...] array in
    local metres; the footprint centroid is the mean of the XY vertices and the
    height is `.height` (fallback: vertical extent of the vertices).
    """
    out = []
    items = buildings_list.values() if isinstance(buildings_list, dict) else buildings_list
    for b in items:
        coords = getattr(b, "coordinates", None)
        if not coords or len(coords) < 9:
            continue
        xs = coords[0::3]; ys = coords[1::3]; zs = coords[2::3]
        cx = sum(xs) / len(xs); cy = sum(ys) / len(ys)
        h = float(getattr(b, "height", 0.0) or 0.0)
        if h <= 0.0 and zs:
            h = max(zs) - min(zs)
        if h > 0.0:
            out.append((cx, cy, h))
    return out


def _zone_sky_openness(buildings_list, radius_m: float = 60.0) -> float | None:
    """Zone-level sky-openness proxy in [0,1] (1 = open sky, lower = more shaded).

    Heuristic SVF: for each building, bin neighbouring buildings within `radius_m`
    into 8 azimuth sectors, take the tallest obstruction per sector as an elevation
    angle atan(Δh / distance), and average sin(angle) across sectors (empty sectors
    contribute 0 obstruction). Openness = 1 − mean obstruction, averaged over all
    buildings. Returns None when geometry is unavailable. Not a CFD/raytraced SVF —
    a fast neighbour-shading approximation from the massing already loaded.
    """
    fps = _building_footprints(buildings_list)
    if len(fps) < 2:
        return None
    per_building = []
    for i, (xi, yi, hi) in enumerate(fps):
        sectors = [0.0] * 8
        for j, (xj, yj, hj) in enumerate(fps):
            if i == j:
                continue
            dx = xj - xi; dy = yj - yi
            d = math.hypot(dx, dy)
            if d <= 1.0 or d > radius_m:
                continue
            rel_h = hj - hi  # only neighbours taller than me block my sky
            if rel_h <= 0.0:
                continue
            ang = math.atan2(rel_h, d)          # elevation angle to neighbour top
            s = int(((math.degrees(math.atan2(dy, dx)) + 360) % 360) // 45)
            sectors[s] = max(sectors[s], math.sin(ang))
        obstruction = sum(sectors) / 8.0
        per_building.append(max(0.0, 1.0 - obstruction))
    if not per_building:
        return None
    openness = sum(per_building) / len(per_building)
    return round(min(1.0, max(0.2, openness)), 3)


def _ground_albedo(ground_layers) -> float | None:
    """Mean shortwave albedo (0–1) from the zone's ground-material layer names."""
    if not ground_layers:
        return None
    vals = []
    for name in ground_layers:
        key = str(name).lower()
        for frag, alb in _GROUND_ALBEDO.items():
            if frag in key:
                vals.append(alb)
                break
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def _create_buffer_zone(zone_geojson: Dict, buffer_meters: float = 150) -> Polygon:
    """Create a circular buffer zone around the zone's center point (150m radius).

    Instead of buffering the zone polygon boundary, this creates a circle around
    the center point, ensuring even distribution of context buildings on all sides.
    """
    coords_raw = zone_geojson.get("coordinates", [])
    if coords_raw and isinstance(coords_raw[0], (int, float)):
        coords = [coords_raw]
    else:
        coords = coords_raw[0] if coords_raw else []

    if not coords or len(coords) < 2:
        return None

    # Calculate zone center point
    lons = [c[0] for c in coords if len(c) >= 2]
    lats = [c[1] for c in coords if len(c) >= 2]
    center_lon = sum(lons) / len(lons) if lons else 0
    center_lat = sum(lats) / len(lats) if lats else 0

    # Convert buffer meters to degrees (use latitude-based conversion for lon)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))

    # Create circular buffer in degrees
    buffer_deg_lat = buffer_meters / meters_per_deg_lat
    buffer_deg_lon = buffer_meters / meters_per_deg_lon

    # Create a circle (approximated as a polygon with many points)
    center_point = Point(center_lon, center_lat)

    # Use average of lat/lon buffer for circular approximation
    buffer_deg_avg = (buffer_deg_lat + buffer_deg_lon) / 2
    circular_buffer = center_point.buffer(buffer_deg_avg)

    return circular_buffer


def _point_in_polygon(point: Tuple[float, float], polygon: Polygon) -> bool:
    """Check if a point is inside a polygon."""
    return polygon.contains(Point(point))


def _separate_buildings_by_zone(buildings_geojson: Dict, zone_geojson: Dict, buffer_meters: float = 150) -> Tuple[List[Dict], List[Dict]]:
    """
    Separate buildings into zone and buffer zone buildings.
    Returns: (zone_buildings, buffer_buildings)
    """
    zone_polygon = Polygon(_extract_coords_from_geojson(zone_geojson))
    buffer_polygon = _create_buffer_zone(zone_geojson, buffer_meters)

    zone_buildings = []
    buffer_buildings = []

    for feature in buildings_geojson.get('features', []):
        geometry = feature.get('geometry', {})
        if geometry.get('type') == 'Polygon':
            coords = geometry.get('coordinates', [[]])[0]
            if coords:
                centroid = Point(
                    sum(c[0] for c in coords) / len(coords),
                    sum(c[1] for c in coords) / len(coords)
                )

                if zone_polygon.contains(centroid):
                    zone_buildings.append(feature)
                elif buffer_polygon and buffer_polygon.contains(centroid):
                    buffer_buildings.append(feature)

    return zone_buildings, buffer_buildings


def _extract_coords_from_geojson(zone_geojson: Dict) -> List[List[float]]:
    """Extract coordinate ring from zone GeoJSON."""
    coords_raw = zone_geojson.get("coordinates", [])
    if coords_raw and isinstance(coords_raw[0], (int, float)):
        return [coords_raw]
    return coords_raw[0] if coords_raw else []


async def analyze_zone_vulnerability(zone_geojson: Dict, center: List[float]) -> Dict:
    """
    Analyze urban heat vulnerability using Infrared SDK thermal comfort analyses.
    Requires valid Infrared API credentials. No fallback to stub data.
    """
    print(f"[ANALYZE] Starting with zone_geojson type: {type(zone_geojson)}, center type: {type(center)}")
    print(f"[ANALYZE] Zone geojson keys: {list(zone_geojson.keys()) if isinstance(zone_geojson, dict) else 'NOT DICT'}")

    # Normalize coordinates in zone_geojson to ensure proper nested array format
    if isinstance(zone_geojson, dict) and 'coordinates' in zone_geojson:
        coords_raw = zone_geojson['coordinates']
        if coords_raw and len(coords_raw) > 0:
            first_elem = coords_raw[0]

            # Case 1: Flat array of numbers [lon, lat, lon, lat, ...]
            # OR single pair [lon, lat]
            if isinstance(first_elem, (int, float)):
                print(f"[ANALYZE] WARNING: Normalizing flat coordinate array to ring format")
                zone_geojson = dict(zone_geojson)
                # Reshape flat array to pairs
                pairs = [[coords_raw[i], coords_raw[i+1]] for i in range(0, len(coords_raw)-1, 2)]
                zone_geojson['coordinates'] = [pairs]

            # Case 2: Ring format [[lon, lat], [lon, lat], ...] - needs wrapping to polygon
            elif isinstance(first_elem, list) and len(first_elem) == 2 and isinstance(first_elem[0], (int, float)):
                print(f"[ANALYZE] WARNING: Normalizing ring to polygon format")
                zone_geojson = dict(zone_geojson)
                zone_geojson['coordinates'] = [coords_raw]

    if len(center) != 2:
        raise ValueError("Center must be [lon, lat].")

    lon, lat = center
    client = await get_infrared_client()

    # Log polygon bounds for debugging
    print(f"[ANALYZE] Getting Infrared client... done")
    if zone_geojson.get('coordinates'):
        coords_raw = zone_geojson['coordinates']
        print(f"[POLYGON] Raw coordinates structure: len={len(coords_raw)}, type={type(coords_raw)}, [0]={type(coords_raw[0]) if coords_raw else 'empty'}")

        # Normalize coordinates: if first element is a number, wrap it
        if coords_raw and len(coords_raw) > 0 and isinstance(coords_raw[0], (int, float)):
            print(f"[POLYGON] WARNING: Coordinates appear to be a single pair, wrapping...")
            coords = [coords_raw]
        else:
            coords = coords_raw[0] if coords_raw else []

        print(f"[POLYGON] Normalized coords: {len(coords)} vertices")
        if len(coords) > 0 and len(coords[0]) >= 2:
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            print(f"[POLYGON BOUNDS] lng: {min(lngs):.6f}-{max(lngs):.6f}, lat: {min(lats):.6f}-{max(lats):.6f}")
            print(f"[POLYGON COORDS] {len(coords)} vertices, center=[{lon}, {lat}]")
        else:
            print(f"[POLYGON] ERROR: Invalid coordinates structure")

    # Step 1: Fetch buildings from zone only (skip context/buffer buildings for now)
    area = await asyncio.to_thread(client.buildings.get_area, zone_geojson)
    if not area.buildings:
        raise ValueError(f"No buildings found in zone at ({lat}, {lon})")

    all_zone_buildings = area.buildings
    local_bounds = None

    vegetation = await asyncio.to_thread(client.vegetation.get_area, zone_geojson)
    ground_materials = await asyncio.to_thread(client.ground_materials.get_area, zone_geojson)

    # Step 2: Find nearest weather station.
    stations = await asyncio.to_thread(
        lambda: client.weather.get_weather_file_from_location(lat=lat, lon=lon, radius=50)
    )
    if not stations:
        raise ValueError(f"No weather stations found near ({lat}, {lon})")

    # Step 3: Define July (peak summer heat) analysis window.
    time_period = TimePeriod(
        start_month=7,
        start_day=1,
        start_hour=10,
        end_month=7,
        end_day=31,
        end_hour=18,
    )

    # Steps 4-7: thermal comfort simulation. Requires Infrared simulation
    # credits — on failure (e.g. HTTP 402 quota exhausted) or timeout, fall
    # back to real satellite LST so the analysis still completes.
    utci_grid = None
    utci_result = None
    valid_utci = None
    thermal_source = "Infrared UTCI simulation"

    try:
        weather_data = await asyncio.to_thread(
            lambda: client.weather.filter_weather_data(
                identifier=stations[0]["uuid"],
                time_period=time_period,
            )
        )

        location = Location(latitude=lat, longitude=lon)

        utci_payload = UtciModelRequest.from_weatherfile_payload(
            payload=UtciModelBaseRequest(
                analysis_type=AnalysesName.thermal_comfort_index,
            ),
            location=location,
            time_period=time_period,
            weather_data=weather_data,
        )

        tcs_payload = TcsModelRequest.from_weatherfile_payload(
            payload=TcsModelBaseRequest(
                analysis_type=AnalysesName.thermal_comfort_statistics,
                subtype=TcsSubtype.heat_stress,
            ),
            location=location,
            time_period=time_period,
            weather_data=weather_data,
        )

        utci_result = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.run_area_and_wait(
                    utci_payload,
                    zone_geojson,
                    buildings=area.buildings,
                    vegetation=vegetation.features,
                    ground_materials=ground_materials.layers,
                )
            ),
            timeout=420,
        )
        tcs_result = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.run_area_and_wait(
                    tcs_payload,
                    zone_geojson,
                    buildings=area.buildings,
                    vegetation=vegetation.features,
                    ground_materials=ground_materials.layers,
                )
            ),
            timeout=420,
        )

        if not hasattr(utci_result, 'merged_grid') or not hasattr(tcs_result, 'merged_grid'):
            raise ValueError("Thermal analysis returned unexpected result format")

        utci_grid = utci_result.merged_grid
        tcs_grid = tcs_result.merged_grid

        valid_utci = utci_grid[~np.isnan(utci_grid)]
        valid_tcs = tcs_grid[~np.isnan(tcs_grid)]
        if len(valid_utci) == 0 or len(valid_tcs) == 0:
            raise ValueError("Thermal analysis returned no valid data")

        peak_temp = float(np.nanmax(utci_grid))
        mean_temp = float(np.nanmean(valid_utci))
        heat_stress_fraction = float(np.nanmean(valid_tcs))
        heat_stress_pct = heat_stress_fraction * 100 if heat_stress_fraction <= 1.0 else heat_stress_fraction

    except Exception as sim_error:
        # No fallback - thermal simulation is required for proper heatmap generation
        logger.error(f"[ANALYZE] Thermal simulation failed: {sim_error}")
        print(f"[ANALYZE] THERMAL SIMULATION ERROR: {sim_error}")
        raise ValueError(
            f"Thermal comfort analysis failed. Please check your Infrared API credentials and try again. "
            f"Error: {str(sim_error)}"
        )

    # Calculate vulnerability score (0-10 scale).
    temp_score = min(5, (peak_temp - 28) / 2)  # baseline ~28°C
    stress_score = min(5, heat_stress_pct / 10)
    vulnerability_score = temp_score + stress_score

    vegetation_count = len(vegetation.features)
    ground_layers = list(ground_materials.layers.keys())

    # Infer drivers from analysis results.
    drivers = []

    if mean_temp > 30:
        drivers.append({
            "driver": "urban_heat_island",
            "severity": min(1.0, (mean_temp - 28) / 4),
            "data_source": "Infrared UTCI analysis",
        })

    if heat_stress_pct > 30:
        drivers.append({
            "driver": "thermal_stress_exposure",
            "severity": min(1.0, heat_stress_pct / 100),
            "data_source": "Infrared thermal comfort statistics",
        })

    if vegetation_count == 0:
        drivers.append({
            "driver": "vegetation_deficit",
            "severity": 0.6,
            "data_source": "Infrared vegetation layer",
        })

    if len(area.buildings) > 100:
        drivers.append({
            "driver": "poor_ventilation",
            "severity": min(1.0, len(area.buildings) / 300),
            "data_source": "Infrared 3D building footprint",
        })

    if len(area.buildings) > 100:
        drivers.append({
            "driver": "high_building_density",
            "severity": min(1.0, len(area.buildings) / 300),
            "data_source": "Infrared 3D building footprint",
        })

    if not drivers:
        drivers.append({
            "driver": "baseline_thermal_conditions",
            "severity": 0.3,
            "data_source": "Infrared UTCI analysis",
        })

    # Generate heatmap image for visualization from the thermal simulation
    if utci_grid is None or valid_utci is None:
        raise ValueError("UTCI grid is not available - thermal simulation did not complete properly")

    grid_min = float(np.nanmin(valid_utci))
    grid_max = float(np.nanmax(valid_utci))

    try:
        heatmap_base64 = _grid_to_heatmap_png(utci_grid, grid_min, grid_max)
        print(f"[HEATMAP] Generated heatmap from UTCI grid (min={grid_min:.1f}°C, max={grid_max:.1f}°C)")
    except Exception as hm_error:
        logger.error(f"[HEATMAP] Failed to generate heatmap: {hm_error}")
        raise ValueError(f"Failed to generate heatmap visualization: {str(hm_error)}")

    bounds_dict = _extract_bounds(utci_result.bounds)
    print(f"[SDK BOUNDS] {bounds_dict}")

    # Convert building data to Three.js geometry format (zone only, no buffer)
    all_zone_buildings = area.buildings
    all_buffer_buildings = {}  # Empty for now

    # Calculate local_bounds from zone buildings
    zone_only_x_coords = []
    zone_only_y_coords = []
    for building in (all_zone_buildings.values() if isinstance(all_zone_buildings, dict) else all_zone_buildings):
        if hasattr(building, 'coordinates') and building.coordinates:
            coords_array = building.coordinates
            for j in range(0, len(coords_array), 3):
                if j + 2 < len(coords_array):
                    zone_only_x_coords.append(coords_array[j])
                    zone_only_y_coords.append(coords_array[j + 1])

    if zone_only_x_coords and zone_only_y_coords:
        local_bounds = {
            "x_min": min(zone_only_x_coords),
            "x_max": max(zone_only_x_coords),
            "y_min": min(zone_only_y_coords),
            "y_max": max(zone_only_y_coords)
        }
    else:
        local_bounds = None

    # Per-building vulnerability scores from the UTCI grid (when available)
    vulnerability_map = {}
    zone_buildings_geojson = None

    if utci_grid is not None and utci_result is not None:
        # Score zone buildings (affected by thermal analysis)
        zone_buildings_geojson = _buildings_to_geojson(all_zone_buildings, zone_geojson, local_bounds)
        zone_buildings_geojson = _add_building_vulnerability_scores(
            zone_buildings_geojson,
            utci_grid,
            utci_result.bounds,
            grid_min,
            grid_max
        )

        # Collect vulnerability map for buildings
        for feature in zone_buildings_geojson.get('features', []):
            building_id = feature.get('properties', {}).get('id') or feature.get('id', str(len(vulnerability_map)))
            vulnerability_map[str(building_id)] = feature.get('properties', {}).get('vulnerability_score', 5.0)

    # Convert to Three.js geometry with vulnerability scores
    zone_buildings_threejs = _buildings_to_threejs_geometry(all_zone_buildings, zone_geojson, vulnerability_map, local_bounds=local_bounds)
    buffer_buildings_threejs = None

    return {
        "score": round(vulnerability_score, 1),
        "drivers": drivers,
        "climate_context": {
            "peak_utci_celsius": round(peak_temp, 1),
            "mean_utci_celsius": round(mean_temp, 1),
            "heat_stress_hours_pct": round(heat_stress_pct, 1),
            "analysis_period": "July 1-31, 10:00-18:00",
            "coordinates": [lon, lat],
            "buildings_count": len(all_zone_buildings),
            "vegetation_count": vegetation_count,
            "ground_layers": ground_layers,
            "thermal_source": thermal_source,
            # Urban→building grounding signals derived from already-fetched data.
            # Consumed by the building tool via the frontend `urban_context` blob.
            "sky_openness": _zone_sky_openness(all_zone_buildings),  # 0–1 SVF proxy → solar shading
            "ground_albedo": _ground_albedo(ground_layers),          # mean ground albedo 0–1
        },
        "simulation_grid": {
            "heatmap_image": heatmap_base64,
            "bounds": bounds_dict,
            "min_value": float(grid_min),
            "max_value": float(grid_max),
            "unit": "°C UTCI",
            # Raw grid (row 0 = south) so the frontend can re-render the
            # heatmap with intervention deltas applied, on the same scale
            "values": _grid_to_values(utci_grid),
        },
        "zone_buildings": zone_buildings_threejs,
        "buffer_zone_buildings": buffer_buildings_threejs if buffer_buildings_threejs else {"count": 0, "features": []},
    }

def _extract_zone_bounds(zone_geojson: Dict) -> Dict:
    """Extract bounds from zone GeoJSON Polygon."""
    coords_raw = zone_geojson.get("coordinates", [])

    # Normalize coordinates: if first element is a number, wrap it
    if coords_raw and len(coords_raw) > 0 and isinstance(coords_raw[0], (int, float)):
        coords = [coords_raw]  # Single pair, wrap it
    else:
        coords = coords_raw[0] if coords_raw else []

    if not coords or len(coords) < 2:
        return None

    try:
        lons = [c[0] for c in coords if len(c) >= 2]
        lats = [c[1] for c in coords if len(c) >= 2]

        if not lons or not lats:
            return None

        return {
            "west": min(lons),
            "east": max(lons),
            "south": min(lats),
            "north": max(lats)
        }
    except (TypeError, IndexError) as e:
        print(f"[BOUNDS] Error extracting bounds: {e}")
        return None


def _local_to_geographic(local_x: float, local_y: float, zone_bounds: Dict, local_bounds: Dict = None) -> tuple:
    """
    Transform Infrared building coordinates to geographic lon/lat.

    Infrared's buildings.get_area() returns vertices in "polygon-bbox-SW meter
    space" (documented in the SDK): meters EAST (x) and NORTH (y) of the zone
    bounding box's SW corner, i.e. (min_lon, min_lat). The SDK's tile grid is
    built from that same SW corner, and longitude is scaled by the zone's
    CENTER latitude (infrared_sdk/tiling/tiles.py + transforms.lonlat_to_meters):
        x = (lon - min_lon) * 111320 * cos(center_lat)
        y = (lat - min_lat) * 111320
    We invert exactly that — nothing more.

    IMPORTANT: do NOT subtract the building min (local_bounds) or rescale to the
    zone span. The coordinates already share the zone's SW origin, so any
    normalization shifts/squashes every footprint off its true location (the
    SW-most building is not at the zone SW corner — there is a street/gap there).
    local_bounds is accepted only for call-site compatibility and is unused.
    """
    import math

    meters_per_deg_lat = 111320.0
    center_lat = (zone_bounds['south'] + zone_bounds['north']) / 2.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))

    geo_x = zone_bounds['west'] + local_x / meters_per_deg_lon
    geo_y = zone_bounds['south'] + local_y / meters_per_deg_lat

    return [geo_x, geo_y]


def _buildings_to_geojson(buildings_list, zone_geojson: Dict, local_bounds: Dict = None) -> Dict:
    """Convert Infrared SDK building objects to GeoJSON FeatureCollection.

    Infrared returns buildings in local coordinate space; we transform to geographic
    by mapping the local coordinate bounding box to the zone's geographic bounds.

    local_bounds: Optional pre-calculated bounds from ALL buildings (zone + buffer).
                  If provided, uses this for coordinate transformation instead of
                  recalculating from just the buildings_list.
    """
    print("\n" + "="*80)
    print("[BUILDINGS_GEOJSON] FUNCTION CALLED")
    print("="*80 + "\n")
    features = []

    # Normalize zone_geojson coordinates first
    coords_raw = zone_geojson.get("coordinates", [])
    if coords_raw and len(coords_raw) > 0 and isinstance(coords_raw[0], (int, float)):
        print(f"[BUILDINGS_GEOJSON] Normalizing zone coordinates (was single pair)")
        zone_geojson = {
            "type": zone_geojson.get("type", "Polygon"),
            "coordinates": [coords_raw]
        }

    zone_bounds = _extract_zone_bounds(zone_geojson)
    print(f"[BUILDINGS_GEOJSON] Zone bounds: {zone_bounds}")

    # Handle if buildings_list is a dict (from Infrared SDK)
    if isinstance(buildings_list, dict):
        print(f"[BUILDINGS_GEOJSON] Converting {len(buildings_list)} buildings from dict format (Infrared SDK)")
        buildings_to_process = list(buildings_list.values())
    else:
        print(f"[BUILDINGS_GEOJSON] Converting {len(buildings_list)} buildings from list format")
        buildings_to_process = list(buildings_list)

    # First pass: collect all local coordinates to find their bounds
    all_x_coords = []
    all_y_coords = []

    print(f"[DEBUG] buildings_to_process: {len(buildings_to_process)} items")
    print(f"[DEBUG] First building type: {type(buildings_to_process[0]) if buildings_to_process else 'N/A'}")
    if buildings_to_process:
        print(f"[DEBUG] First building has 'coordinates'? {hasattr(buildings_to_process[0], 'coordinates')}")
        if hasattr(buildings_to_process[0], 'coordinates'):
            print(f"[DEBUG] First building coordinates type: {type(buildings_to_process[0].coordinates)}")
            print(f"[DEBUG] First building coordinates length: {len(buildings_to_process[0].coordinates) if buildings_to_process[0].coordinates else 0}")

    for building in buildings_to_process:
        if hasattr(building, 'coordinates') and building.coordinates:
            coords_array = building.coordinates
            for j in range(0, len(coords_array), 3):
                if j + 2 < len(coords_array):
                    x, y = coords_array[j], coords_array[j+1]
                    all_x_coords.append(x)
                    all_y_coords.append(y)

    # Calculate local coordinate bounds if not provided
    if local_bounds is None:
        print(f"[DEBUG] Collected {len(all_x_coords)} x-coordinates, {len(all_y_coords)} y-coordinates")
        if all_x_coords and all_y_coords:
            local_x_min, local_x_max = min(all_x_coords), max(all_x_coords)
            local_y_min, local_y_max = min(all_y_coords), max(all_y_coords)
            print(f"[DEBUG] LOCAL BOUNDS CALCULATED: X=[{local_x_min}, {local_x_max}], Y=[{local_y_min}, {local_y_max}]")

            # Write debug info to file
            debug_msg = f"""
[BUILDINGS_GEOJSON] Buildings coordinate ranges:
  X: [{local_x_min:.4f}, {local_x_max:.4f}]
  Y: [{local_y_min:.4f}, {local_y_max:.4f}]
[BUILDINGS_GEOJSON] Zone geographic bounds:
  West={zone_bounds['west']:.6f}, East={zone_bounds['east']:.6f}
  South={zone_bounds['south']:.6f}, North={zone_bounds['north']:.6f}
[BUILDINGS_GEOJSON] Buildings coords look like lat/lon? {(-180 <= local_x_min <= 180 and -90 <= local_y_min <= 90)}
"""
            with open('debug_coordinates.txt', 'w') as f:
                f.write(debug_msg)

            logger.info(debug_msg.strip())

            # Sample coordinates
            sample_x, sample_y = all_x_coords[0], all_y_coords[0]
            geo_test = _local_to_geographic(sample_x, sample_y, zone_bounds, None)
            logger.info(f"Sample: Local ({sample_x:.6f}, {sample_y:.6f}) -> Output ({geo_test[0]:.6f}, {geo_test[1]:.6f})")

            # Store bounds for coordinate transformation
            local_bounds = {
                "x_min": local_x_min,
                "x_max": local_x_max,
                "y_min": local_y_min,
                "y_max": local_y_max
            }
        else:
            local_bounds = None
            print(f"[DEBUG] NO LOCAL BOUNDS CALCULATED - no coordinates collected in first pass!")
            logger.info(f"No coordinates found in buildings")
    else:
        print(f"[DEBUG] Using provided local_bounds: X=[{local_bounds['x_min']:.2f}, {local_bounds['x_max']:.2f}], Y=[{local_bounds['y_min']:.2f}, {local_bounds['y_max']:.2f}]")

    # Import for proper footprint extraction
    from shapely.geometry import Polygon as ShpPolygon, MultiPoint
    from shapely.ops import unary_union

    # Second pass: convert to GeoJSON with coordinate transformation
    first_feature_added = False
    for i, building in enumerate(buildings_to_process):
        try:
            coordinates = None
            height = 15  # Default height in meters

            # Handle DotBimMesh format (has coordinates array)
            if hasattr(building, 'coordinates') and building.coordinates:
                coords_array = building.coordinates
                indices = building.indices if hasattr(building, 'indices') else None

                # Extract vertices and z values
                verts = []
                z_coords = []
                for j in range(0, len(coords_array), 3):
                    if j + 2 < len(coords_array):
                        verts.append((coords_array[j], coords_array[j + 1]))
                        z_coords.append(coords_array[j + 2])

                if len(verts) < 3:
                    continue

                height = (max(z_coords) - min(z_coords)) if z_coords else 15.0

                # Build proper footprint from mesh triangles (not just unique points)
                footprint = None
                if indices and len(indices) >= 3:
                    tris = []
                    nv = len(verts)
                    for t in range(0, len(indices) - 2, 3):
                        a, b, c = indices[t], indices[t + 1], indices[t + 2]
                        if a < nv and b < nv and c < nv:
                            try:
                                tri = ShpPolygon([verts[a], verts[b], verts[c]])
                                if tri.is_valid and tri.area > 1e-9:
                                    tris.append(tri)
                            except Exception:
                                continue
                    if tris:
                        try:
                            merged = unary_union(tris).buffer(0)
                            if not merged.is_empty:
                                footprint = merged
                        except Exception:
                            footprint = None

                # Fallback: convex hull of vertices
                if footprint is None:
                    footprint = MultiPoint(verts).convex_hull

                if footprint.geom_type == 'MultiPolygon':
                    footprint = max(footprint.geoms, key=lambda g: g.area)
                if footprint.geom_type != 'Polygon' or footprint.is_empty:
                    continue

                # Simplify to remove slivers
                footprint = footprint.simplify(0.3, preserve_topology=True)
                if footprint.geom_type != 'Polygon' or footprint.is_empty:
                    continue

                # Transform footprint coordinates to geographic
                if local_bounds:
                    geo_coords = [
                        [_local_to_geographic(pt[0], pt[1], zone_bounds, local_bounds) for pt in footprint.exterior.coords]
                    ]
                else:
                    geo_coords = [list(footprint.exterior.coords)]

                if len(geo_coords[0]) >= 3:
                    coordinates = geo_coords
                    if i == 0:
                        print(f"[BUILDINGS_GEOJSON] ===== FIRST BUILDING DEBUG =====")
                        print(f"[BUILDINGS_GEOJSON] Local footprint (raw): {footprint.exterior.coords[0] if footprint.exterior.coords else 'N/A'}")
                        print(f"[BUILDINGS_GEOJSON] Geographic footprint (transformed): {geo_coords[0][0] if geo_coords[0] else 'N/A'}")
                        print(f"[BUILDINGS_GEOJSON] Zone bounds: west={zone_bounds['west']}, south={zone_bounds['south']}, east={zone_bounds['east']}, north={zone_bounds['north']}")
                        print(f"[BUILDINGS_GEOJSON] Local bounds: {local_bounds}")
                        print(f"[BUILDINGS_GEOJSON] ===== END DEBUG =====")

            # Fallback: try geometry/footprint attributes
            elif hasattr(building, 'geometry'):
                geometry = building.geometry
                if hasattr(geometry, 'exterior'):
                    coords = [[_local_to_geographic(c[0], c[1], zone_bounds, local_bounds) for c in geometry.exterior.coords]]
                    coordinates = coords
            elif hasattr(building, 'footprint'):
                geometry = building.footprint
                if hasattr(geometry, 'exterior'):
                    coords = [[_local_to_geographic(c[0], c[1], zone_bounds, local_bounds) for c in geometry.exterior.coords]]
                    coordinates = coords

            if not coordinates:
                continue

            # Get height information
            if hasattr(building, 'height') and building.height:
                height = float(building.height)
            elif hasattr(building, 'max_height') and building.max_height:
                height = float(building.max_height)

            min_height = 0
            if hasattr(building, 'min_height') and building.min_height:
                min_height = float(building.min_height)

            # Create GeoJSON feature with consistent ID
            feature = {
                "type": "Feature",
                "id": str(i),  # Consistent building ID
                "properties": {
                    "id": str(i),  # Also in properties for lookup
                    "height": height,
                    "min_height": min_height,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coordinates
                }
            }

            # Add debug info to first feature
            if i == 0:
                feature["properties"]["_debug_local_bounds"] = str(local_bounds)
                feature["properties"]["_debug_zone_bounds"] = str(zone_bounds)
                if coordinates and len(coordinates) > 0 and len(coordinates[0]) > 0:
                    feature["properties"]["_debug_first_coord"] = coordinates[0][0]

            features.append(feature)
        except (AttributeError, TypeError, ValueError, IndexError) as e:
            print(f"[BUILDINGS_GEOJSON] Error processing building {i}: {e}")
            continue

    print(f"[BUILDINGS_GEOJSON] Successfully converted {len(features)} buildings to GeoJSON")
    print(f"[BUILDINGS_GEOJSON] local_bounds={local_bounds}, zone_bounds={zone_bounds}")
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _extract_bounds(bounds) -> Dict:
    """Extract bounds as dict. Bounds format: (min_longitude, min_latitude, max_longitude, max_latitude)."""
    try:
        if hasattr(bounds, '__iter__') and len(bounds) == 4:
            # Tuple/list format: (west, south, east, north)
            west, south, east, north = bounds
            return {
                "west": float(west),
                "south": float(south),
                "east": float(east),
                "north": float(north),
            }
    except (TypeError, ValueError):
        pass

    # Try attribute access
    if hasattr(bounds, 'west') and hasattr(bounds, 'east'):
        return {
            "west": float(bounds.west),
            "south": float(bounds.south),
            "east": float(bounds.east),
            "north": float(bounds.north),
        }

    raise ValueError(f"Cannot parse bounds: {bounds}")


def _grid_to_values(grid: np.ndarray, max_side: int = 140):
    """Downsample the UTCI grid to a JSON-friendly 2D list (row 0 = south).
    NaN cells (outside the simulation footprint) become None."""
    step = max(1, int(np.ceil(max(grid.shape) / max_side)))
    g = grid[::step, ::step]
    return [
        [None if np.isnan(v) else round(float(v), 2) for v in row]
        for row in g
    ]


def _grid_to_heatmap_png(grid: np.ndarray, min_val: float, max_val: float) -> str:
    """Convert UTCI grid to base64-encoded heatmap PNG. Grid data only, no labels."""
    # Use actual data range or sensible defaults for thermal comfort
    vmin = min_val if not np.isnan(min_val) else 20
    vmax = max_val if not np.isnan(max_val) else 45

    # Ensure vmin < vmax
    if vmin >= vmax:
        vmax = vmin + 5

    # Create colormap: cool (blue) → neutral (white) → hot (red)
    colors = ['#0033cc', '#0099ff', '#ffffff', '#ff6600', '#cc0000']
    cmap = LinearSegmentedColormap.from_list('utci', colors, N=256)

    # Create figure without axes/labels for clean raster overlay
    fig = plt.figure(figsize=(10, 10), dpi=100, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])  # Full figure, no margins
    ax.axis('off')

    # Plot grid as raster (flip vertically to match map coordinates)
    im = ax.imshow(np.flipud(grid), cmap=cmap, vmin=vmin, vmax=vmax, aspect='auto')

    # Convert to base64 PNG
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, dpi=100)
    buf.seek(0)
    plt.close(fig)

    png_data = buf.getvalue()
    return f"data:image/png;base64,{base64.b64encode(png_data).decode()}"


def _add_building_vulnerability_scores(
    buildings_geojson: Dict,
    utci_grid: np.ndarray,
    bounds,
    grid_min: float,
    grid_max: float
) -> Dict:
    """
    Calculate per-building vulnerability scores by sampling the thermal grid.
    Returns GeoJSON with added vulnerability_score property (0-10 scale).
    """
    # Extract bounds
    try:
        if hasattr(bounds, '__iter__') and len(bounds) == 4:
            west, south, east, north = bounds
        else:
            west, south, east, north = bounds.west, bounds.south, bounds.east, bounds.north
    except Exception as e:
        print(f"[VULNERABILITY SCORING] Failed to extract bounds: {e}")
        return buildings_geojson

    grid_height, grid_width = utci_grid.shape
    print(f"[VULNERABILITY SCORING] Grid shape: {grid_height}x{grid_width}, Bounds: ({west:.4f}, {south:.4f}, {east:.4f}, {north:.4f})")
    print(f"[VULNERABILITY SCORING] Grid min: {grid_min:.1f}, max: {grid_max:.1f}")
    print(f"[VULNERABILITY SCORING] Processing {len(buildings_geojson.get('features', []))} buildings")

    # Calculate grid mean for NaN fallback
    valid_cells = utci_grid[~np.isnan(utci_grid)]
    grid_mean = np.mean(valid_cells) if len(valid_cells) > 0 else (grid_min + grid_max) / 2
    print(f"[VULNERABILITY SCORING] Grid mean (for NaN fallback): {grid_mean:.1f}")

    # Sample each building at its centroid
    scored_count = 0
    utci_samples = []
    for feature in buildings_geojson.get("features", []):
        try:
            geometry = feature.get("geometry", {})

            # Calculate centroid from polygon
            if geometry.get("type") == "Polygon":
                coords = geometry.get("coordinates", [[]])[0]
                if coords and len(coords) > 0:
                    centroid_lon = sum(c[0] for c in coords) / len(coords)
                    centroid_lat = sum(c[1] for c in coords) / len(coords)
                else:
                    print(f"[VULNERABILITY SCORING] Polygon has no coordinates")
                    feature["properties"]["vulnerability_score"] = 5.0
                    continue
            else:
                print(f"[VULNERABILITY SCORING] Feature is not a Polygon: {geometry.get('type')}")
                feature["properties"]["vulnerability_score"] = 5.0
                continue

            # Map geographic coordinates to grid indices
            # Normalize coordinates to [0, 1] within bounds
            norm_x = (centroid_lon - west) / (east - west)
            norm_y = (centroid_lat - south) / (north - south)

            # Convert to grid indices (x increases left-to-right, y increases bottom-to-top)
            grid_col = int(np.clip(norm_x * grid_width, 0, grid_width - 1))
            grid_row = int(np.clip((1 - norm_y) * grid_height, 0, grid_height - 1))  # Flip y-axis

            # Sample grid value at building location
            utci_value = utci_grid[grid_row, grid_col]

            # Calculate vulnerability score (0-10 scale)
            # Use grid min/max to normalize the temperature value
            if np.isnan(utci_value):
                # Use grid mean for buildings with no direct thermal data
                utci_value = grid_mean

            # Map UTCI value to vulnerability (higher temp = higher vulnerability)
            # Normalize to 0-10 scale based on grid min/max
            if grid_max > grid_min:
                normalized = (utci_value - grid_min) / (grid_max - grid_min)
                vulnerability_score = normalized * 10
            else:
                vulnerability_score = 5.0

            vulnerability_score = float(np.clip(vulnerability_score, 0, 10))

            # Add vulnerability score to properties
            feature["properties"]["vulnerability_score"] = round(vulnerability_score, 1)
            feature["properties"]["utci_celsius"] = round(float(utci_value), 1)
            utci_samples.append(float(utci_value))
            scored_count += 1

            # Debug log first few buildings
            if scored_count <= 5:
                print(f"[VULN_SAMPLE] Bldg {scored_count}: centroid=({centroid_lon:.6f}, {centroid_lat:.6f}) grid=({grid_col}, {grid_row}) utci={utci_value:.2f} score={vulnerability_score:.1f}")

        except (KeyError, TypeError, ValueError, IndexError) as e:
            # Skip buildings with invalid geometry
            feature["properties"]["vulnerability_score"] = 5.0
            print(f"[VULNERABILITY SCORING] Error processing building: {str(e)}")
            continue

    print(f"[VULNERABILITY SCORING] Successfully scored {scored_count} buildings")

    # Show sampled UTCI statistics
    if utci_samples:
        valid_samples = [v for v in utci_samples if v is not None]
        if valid_samples:
            print(f"[VULNERABILITY SCORING] Sampled UTCI range: {min(valid_samples):.2f} to {max(valid_samples):.2f}, mean: {sum(valid_samples)/len(valid_samples):.2f}")

    # Final verification before returning
    final_scored_count = sum(1 for f in buildings_geojson.get("features", [])
                             if f.get("properties", {}).get("vulnerability_score") is not None)
    print(f"[VULNERABILITY SCORING] FINAL CHECK: {final_scored_count} buildings with vulnerability_score in return data")

    if buildings_geojson.get("features"):
        first_props = buildings_geojson["features"][0].get("properties", {})
        print(f"[VULNERABILITY SCORING] First building properties keys: {list(first_props.keys())}")
        print(f"[VULNERABILITY SCORING] First building vulnerability_score: {first_props.get('vulnerability_score')}")

    return buildings_geojson


def _buildings_to_threejs_geometry(buildings_list, zone_geojson: Dict, vulnerability_scores: Dict = None, is_buffer_zone: bool = False, local_bounds: Dict = None) -> Dict:
    """
    Convert Infrared SDK buildings to Three.js geometry with full 3D mesh data.
    Sends raw vertices and indices from SDK for accurate 3D rendering.

    buildings_list: List of DotBimMesh from Infrared SDK
    zone_geojson: Zone polygon (GeoJSON) for coordinate reference
    vulnerability_scores: Dict mapping building ID to vulnerability score
    is_buffer_zone: If True, don't filter buildings by zone boundary (they're in buffer)
    local_bounds: Optional pre-calculated bounds from ALL buildings. If provided, uses this
                  for coordinate transformation instead of recalculating from buildings_list.
    """
    import math

    features = []
    zone_bounds = _extract_zone_bounds(zone_geojson)

    # Handle dict or list of buildings - use index as consistent ID
    if isinstance(buildings_list, dict):
        buildings_to_process = [(str(i), b) for i, (k, b) in enumerate(buildings_list.items())]
    else:
        buildings_to_process = [(str(i), b) for i, b in enumerate(buildings_list)]

    # Use provided local_bounds or calculate from buildings
    if local_bounds is None:
        # First pass: collect all local coordinates to find their bounds
        all_x_coords = []
        all_y_coords = []
        for building_id, building in buildings_to_process:
            if hasattr(building, 'coordinates') and building.coordinates:
                coords_array = building.coordinates
                for j in range(0, len(coords_array), 3):
                    if j + 2 < len(coords_array):
                        x, y = coords_array[j], coords_array[j+1]
                        all_x_coords.append(x)
                        all_y_coords.append(y)

        # Calculate local coordinate bounds for proper mapping
        if all_x_coords and all_y_coords:
            local_bounds = {
                "x_min": min(all_x_coords),
                "x_max": max(all_x_coords),
                "y_min": min(all_y_coords),
                "y_max": max(all_y_coords)
            }
        else:
            local_bounds = None

    # Debug: log vulnerability_scores keys
    if vulnerability_scores:
        print(f"[THREE_JS] vulnerability_scores keys (first 5): {list(vulnerability_scores.keys())[:5]}")
    else:
        print("[THREE_JS] WARNING: vulnerability_scores is None or empty!")

    from shapely.geometry import Polygon as ShpPolygon, MultiPoint, Point, shape as shp_shape
    from shapely.ops import unary_union

    # Zone polygon (geographic) for clipping buildings to the drawn boundary
    zone_poly = None
    try:
        zone_poly = shp_shape(zone_geojson)
        if not zone_poly.is_valid:
            zone_poly = zone_poly.buffer(0)
    except Exception:
        zone_poly = None

    # Second pass: convert buildings to clean footprints
    skipped_outside = 0
    for building_id, building in buildings_to_process:
        try:
            if not (hasattr(building, 'coordinates') and building.coordinates):
                continue

            coords_array = building.coordinates
            indices = building.indices if hasattr(building, 'indices') else None

            verts = []
            z_coords = []
            for j in range(0, len(coords_array), 3):
                if j + 2 < len(coords_array):
                    verts.append((coords_array[j], coords_array[j + 1]))
                    z_coords.append(coords_array[j + 2])

            if len(verts) < 3:
                continue

            height = (max(z_coords) - min(z_coords)) if z_coords else 15.0

            # Build the true footprint: union of the mesh triangles.
            # Vertex array order is NOT boundary order — chaining vertices
            # directly creates self-intersecting polygons.
            footprint = None
            if indices and len(indices) >= 3:
                tris = []
                nv = len(verts)
                for t in range(0, len(indices) - 2, 3):
                    a, b, c = indices[t], indices[t + 1], indices[t + 2]
                    if a < nv and b < nv and c < nv:
                        try:
                            tri = ShpPolygon([verts[a], verts[b], verts[c]])
                            if tri.is_valid and tri.area > 1e-9:
                                tris.append(tri)
                        except Exception:
                            continue
                if tris:
                    try:
                        merged = unary_union(tris).buffer(0)
                        if not merged.is_empty:
                            footprint = merged
                    except Exception:
                        footprint = None

            # Fallback when no usable face indices: convex hull of vertices
            if footprint is None:
                footprint = MultiPoint(verts).convex_hull

            if footprint.geom_type == 'MultiPolygon':
                footprint = max(footprint.geoms, key=lambda g: g.area)
            if footprint.geom_type != 'Polygon' or footprint.is_empty:
                continue

            # Drop sliver vertices from triangulation (local units ~ meters)
            footprint = footprint.simplify(0.3, preserve_topology=True)
            if footprint.geom_type != 'Polygon' or footprint.is_empty:
                continue

            # Transform rings (exterior + courtyard holes) to lon/lat
            def ring_to_geo(ring):
                return [list(_local_to_geographic(x, y, zone_bounds, local_bounds)) for x, y in ring.coords]

            rings = [ring_to_geo(footprint.exterior)]
            for interior in footprint.interiors:
                r = ring_to_geo(interior)
                if len(r) >= 4:
                    rings.append(r)

            ext = rings[0]
            center_lon = sum(c[0] for c in ext) / len(ext)
            center_lat = sum(c[1] for c in ext) / len(ext)

            # DEBUG: Log first building transformation
            if building_id == "0" or building_id == 0:
                print(f"[THREE_JS] ===== FIRST BUILDING DEBUG (THREEJS) =====")
                print(f"[THREE_JS] Building ID: {building_id}")
                print(f"[THREE_JS] Local footprint exterior (first 3 verts): {list(footprint.exterior.coords)[:3]}")
                print(f"[THREE_JS] Geographic footprint exterior (first 3 verts): {rings[0][:3] if rings[0] else 'N/A'}")
                print(f"[THREE_JS] Zone bounds: {zone_bounds}")
                print(f"[THREE_JS] Local bounds: {local_bounds}")
                print(f"[THREE_JS] Center: [{center_lon}, {center_lat}]")
                print(f"[THREE_JS] ===== END DEBUG =====")

            # NOTE: Buildings passed here have already been filtered during separation phase.
            # We trust the separation logic and don't re-check containment, since polygon
            # centroid may differ from the point used during separation, causing false rejections.

            vuln_score = vulnerability_scores.get(building_id, 5.0) if vulnerability_scores else 5.0

            feature = {
                "type": "Feature",
                "properties": {
                    "id": building_id,
                    "height": float(height),
                    "vulnerability_score": float(vuln_score),
                    "center": [center_lon, center_lat]
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": rings
                }
            }
            features.append(feature)

        except (AttributeError, TypeError, ValueError, IndexError, ZeroDivisionError):
            continue

    print(f"[THREE_JS] {len(features)} clean footprints in zone; {skipped_outside} buildings outside boundary skipped")
    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features)
    }


def calculate_driver_severity(zone_geojson: Dict, driver_name: str) -> float:
    """Calculate severity of a specific vulnerability driver."""
    return 0.5

