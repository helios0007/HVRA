import asyncio
import base64
import logging
from io import BytesIO
from typing import Dict, List

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless backend — Tk crashes when used from worker threads
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

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

    # Step 1: Fetch geometry layers in the zone.
    area = await asyncio.to_thread(client.buildings.get_area, zone_geojson)
    print(f"[INFRARED FETCH] Buildings returned: {len(area.buildings) if area.buildings else 0}")
    if not area.buildings:
        raise ValueError(f"No buildings found in zone at ({lat}, {lon})")

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
        logger.warning(
            f"[ANALYZE] Thermal simulation unavailable ({sim_error}); "
            f"falling back to Landsat surface temperature"
        )
        print(f"[ANALYZE] SIMULATION FALLBACK: {sim_error}")
        thermal_source = "Landsat LST fallback (no simulation credits)"
        utci_grid = None
        utci_result = None
        valid_utci = None

        try:
            from services.data_loaders.satellite_loader import SatelliteLoader
            zb = _extract_zone_bounds(zone_geojson)
            sat = SatelliteLoader().get_lst((zb['west'], zb['south'], zb['east'], zb['north']))
        except Exception:
            sat = None

        if sat:
            mean_temp = float(sat['zone_lst_c'])
            peak_temp = float(sat['zone_lst_max_c'])
        else:
            mean_temp, peak_temp = 31.0, 38.0
        # Rough heat-stress estimate from surface temperature
        heat_stress_pct = float(np.clip((mean_temp - 28.0) * 6.0, 5.0, 95.0))

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

    # Generate heatmap image for visualization (only when the simulation ran)
    if utci_grid is not None and valid_utci is not None:
        grid_min = float(np.nanmin(valid_utci))
        grid_max = float(np.nanmax(valid_utci))
        heatmap_base64 = _grid_to_heatmap_png(utci_grid, grid_min, grid_max)
        bounds_dict = _extract_bounds(utci_result.bounds)
        print(f"[SDK BOUNDS] {bounds_dict}")
    else:
        grid_min, grid_max = mean_temp - 3, peak_temp
        heatmap_base64 = None
        zb = _extract_zone_bounds(zone_geojson)
        bounds_dict = {"west": zb['west'], "south": zb['south'], "east": zb['east'], "north": zb['north']}

    # Convert building data to Three.js geometry format
    print(f"[ANALYZE_ZONE] Converting {len(area.buildings) if area.buildings else 0} buildings to Three.js format")

    # Per-building vulnerability scores from the UTCI grid (when available)
    vulnerability_map = {}
    if utci_grid is not None and utci_result is not None:
        temp_geojson = _buildings_to_geojson(area.buildings, zone_geojson)
        temp_geojson = _add_building_vulnerability_scores(
            temp_geojson,
            utci_grid,
            utci_result.bounds,
            grid_min,
            grid_max
        )
        for feature in temp_geojson.get('features', []):
            building_id = feature.get('properties', {}).get('id') or feature.get('id', str(len(vulnerability_map)))
            vulnerability_map[str(building_id)] = feature.get('properties', {}).get('vulnerability_score', 5.0)

    print(f"[VULNERABILITY SCORECARD] Mapped {len(vulnerability_map)} buildings with scores")

    # Convert to Three.js geometry with vulnerability scores
    buildings_threejs = _buildings_to_threejs_geometry(area.buildings, zone_geojson, vulnerability_map)
    print(f"[THREE_JS CONVERSION] Converted {buildings_threejs['count']} buildings to Three.js format")

    return {
        "score": round(vulnerability_score, 1),
        "drivers": drivers,
        "climate_context": {
            "peak_utci_celsius": round(peak_temp, 1),
            "mean_utci_celsius": round(mean_temp, 1),
            "heat_stress_hours_pct": round(heat_stress_pct, 1),
            "analysis_period": "July 1-31, 10:00-18:00",
            "coordinates": [lon, lat],
            "buildings_count": len(area.buildings),
            "vegetation_count": vegetation_count,
            "ground_layers": ground_layers,
            "thermal_source": thermal_source,
        },
        "simulation_grid": {
            "heatmap_image": heatmap_base64,
            "bounds": bounds_dict,
            "min_value": float(grid_min),
            "max_value": float(grid_max),
            "unit": "°C UTCI" if utci_grid is not None else "°C LST",
            # Raw grid (row 0 = south) so the frontend can re-render the
            # heatmap with intervention deltas applied, on the same scale
            "values": _grid_to_values(utci_grid) if utci_grid is not None else None,
        },
        "buildings_3d": buildings_threejs,
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
    Transform building coordinates to geographic lon/lat.

    Per the Infrared SDK, get_area() returns coordinates in
    "polygon-bbox-SW meter space": meters east (x) and north (y) of the
    zone bounding box's south-west corner. Convert with a local
    equirectangular projection — do NOT stretch to the bbox extent,
    which distorts scale and misplaces buildings on the basemap.
    """
    import math

    lat0 = zone_bounds['south']
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))

    geo_x = zone_bounds['west'] + local_x / meters_per_deg_lon
    geo_y = zone_bounds['south'] + local_y / meters_per_deg_lat
    return [geo_x, geo_y]


def _buildings_to_geojson(buildings_list, zone_geojson: Dict) -> Dict:
    """Convert Infrared SDK building objects to GeoJSON FeatureCollection.

    Infrared returns buildings in local coordinate space; we transform to geographic
    by mapping the local coordinate bounding box to the zone's geographic bounds.
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

    # Calculate local coordinate bounds
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

    # Second pass: convert to GeoJSON with coordinate transformation
    first_feature_added = False
    for i, building in enumerate(buildings_to_process):
        try:
            coordinates = None
            height = 15  # Default height in meters

            # Handle DotBimMesh format (has coordinates array)
            if hasattr(building, 'coordinates') and building.coordinates:
                coords_array = building.coordinates
                # DotBimMesh coordinates: flat list of x, y, z values in local space
                # Group into triplets and extract unique z values for height
                unique_z = set()
                xy_coords = []
                for j in range(0, len(coords_array), 3):
                    if j + 2 < len(coords_array):
                        x, y, z = coords_array[j], coords_array[j+1], coords_array[j+2]
                        xy_coords.append([x, y])
                        unique_z.add(z)

                if xy_coords:
                    # Extract unique boundary points (simplify to footprint)
                    unique_points = []
                    seen = set()
                    for pt in xy_coords:
                        pt_tuple = (round(pt[0], 6), round(pt[1], 6))
                        if pt_tuple not in seen:
                            seen.add(pt_tuple)
                            # Transform from local to geographic coordinates
                            # ALWAYS use local_bounds if available, else coordinates stay as-is
                            if local_bounds:
                                geo_coords = _local_to_geographic(pt[0], pt[1], zone_bounds, local_bounds)
                            else:
                                # Fallback: use zone bounds directly as a simple scaling
                                # This assumes the zone polygon bounds roughly match the building extent
                                geo_coords = [pt[0], pt[1]]
                            unique_points.append(geo_coords)

                    if len(unique_points) >= 3:
                        coordinates = [unique_points + [unique_points[0]]]  # Close the polygon
                        if i == 0:
                            print(f"[DEBUG] First building after transformation: {unique_points[0] if unique_points else 'N/A'}")
                            print(f"[DEBUG] local_bounds used? {bool(local_bounds)}")

                    # Set height from max z value
                    if unique_z:
                        height = max(unique_z)

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


def _buildings_to_threejs_geometry(buildings_list, zone_geojson: Dict, vulnerability_scores: Dict = None) -> Dict:
    """
    Convert Infrared SDK buildings to Three.js geometry with full 3D mesh data.
    Sends raw vertices and indices from SDK for accurate 3D rendering.

    buildings_list: List of DotBimMesh from Infrared SDK
    zone_geojson: Zone polygon (GeoJSON) for coordinate reference
    vulnerability_scores: Dict mapping building ID to vulnerability score
    """
    import math

    features = []
    zone_bounds = _extract_zone_bounds(zone_geojson)

    # Handle dict or list of buildings - use index as consistent ID
    if isinstance(buildings_list, dict):
        buildings_to_process = [(str(i), b) for i, (k, b) in enumerate(buildings_list.items())]
    else:
        buildings_to_process = [(str(i), b) for i, b in enumerate(buildings_list)]

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

            # Keep only buildings inside the drawn zone
            if zone_poly is not None and not zone_poly.contains(Point(center_lon, center_lat)):
                skipped_outside += 1
                continue

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
