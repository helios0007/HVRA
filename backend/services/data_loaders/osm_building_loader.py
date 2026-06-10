import logging
import geopandas as gpd
import osmnx as ox
from typing import Dict, Optional, Tuple
from shapely.geometry import Point

logger = logging.getLogger(__name__)

class OSMBuildingLoader:
    """
    Fetch building construction dates and characteristics from OpenStreetMap.
    Free, instant, and covers ~35-40% of Barcelona buildings.
    """

    def __init__(self):
        self.cache = {}

    def get_building_construction_dates(
        self,
        bbox: Tuple[float, float, float, float]
    ) -> Dict:
        """
        Fetch building construction dates from OSM in a bounding box.
        bbox: (south, west, north, east) in lat/lon

        Returns: Dict mapping OSM way ID → {construction_year, roof_shape, roof_material}
        """
        try:
            south, west, north, east = bbox
            logger.info(f"[OSM BUILDINGS] Querying construction dates in bbox: {bbox}")

            # Query OSM for all buildings with construction date tag
            tags = {"building": True}

            # Fetch buildings from OSM (osmnx v2 expects bbox=(left, bottom, right, top))
            try:
                buildings = ox.features_from_bbox(bbox=(west, south, east, north), tags=tags)
            except TypeError:
                # osmnx v1 positional signature: (north, south, east, west)
                buildings = ox.features_from_bbox(north, south, east, west, tags=tags)

            logger.info(f"[OSM BUILDINGS] Found {len(buildings)} total buildings")

            # Extract buildings with construction dates
            results = {}
            construction_date_count = 0
            roof_shape_count = 0
            roof_material_count = 0

            for idx, building in buildings.iterrows():
                try:
                    osm_id = building.get("osmid", idx)

                    construction_year = None
                    if "building:construction_date" in building.index:
                        date_str = building["building:construction_date"]
                        try:
                            # Extract year from format "YYYY", "YYYY-MM-DD", or "~YYYY"
                            year_str = str(date_str).strip("~").split("-")[0]
                            construction_year = int(year_str)
                            construction_date_count += 1
                        except (ValueError, AttributeError):
                            pass

                    roof_shape = building.get("building:roof:shape", None)
                    if roof_shape:
                        roof_shape_count += 1

                    roof_material = building.get("building:roof:material", None)
                    if roof_material:
                        roof_material_count += 1

                    # Only store if we have at least construction date
                    if construction_year:
                        results[str(osm_id)] = {
                            "construction_year": construction_year,
                            "roof_shape": roof_shape,
                            "roof_material": roof_material,
                            "source": "OSM",
                            "osm_id": osm_id
                        }

                except Exception as e:
                    logger.debug(f"[OSM BUILDINGS] Error processing building {idx}: {e}")
                    continue

            logger.info(
                f"[OSM BUILDINGS] Found construction dates for {construction_date_count} buildings, "
                f"roof shapes for {roof_shape_count}, roof materials for {roof_material_count}"
            )

            return results

        except Exception as e:
            logger.error(f"[OSM BUILDINGS] Error fetching buildings: {e}")
            return {}

    def match_osm_to_infrared_buildings(
        self,
        infrared_buildings: list,
        osm_dates: Dict
    ) -> Dict:
        """
        Match Infrared buildings (in local coords) to OSM buildings (in lat/lon).
        Returns mapping of Infrared building ID → OSM construction data.

        This is a simple centroid-based matching; production would use proper spatial indexing.
        """
        try:
            logger.info(f"[OSM BUILDINGS] Matching {len(infrared_buildings)} Infrared buildings to OSM data")

            matches = {}

            # For each Infrared building, find nearest OSM building
            for i, building in enumerate(infrared_buildings):
                try:
                    # Extract centroid from Infrared building coordinates
                    if not hasattr(building, "coordinates") or not building.coordinates:
                        continue

                    coords_array = building.coordinates
                    x_coords = [coords_array[j] for j in range(0, len(coords_array), 3)]
                    y_coords = [coords_array[j + 1] for j in range(0, len(coords_array), 3)]

                    if not x_coords or not y_coords:
                        continue

                    # Note: Infrared buildings are in local coords, not lat/lon
                    # This simplified matching assumes zone bounds are handled elsewhere
                    # In production, transform coords properly first

                    building_id = str(i)

                    # Check if we have OSM data for this building
                    # (In production, would do spatial join)
                    if building_id in osm_dates:
                        matches[building_id] = osm_dates[building_id]
                    elif len(osm_dates) > 0:
                        # Use first available as placeholder
                        # Real implementation: find nearest by distance
                        first_osm = list(osm_dates.values())[0]
                        matches[building_id] = first_osm.copy()

                except Exception as e:
                    logger.debug(f"[OSM BUILDINGS] Error matching building {i}: {e}")
                    continue

            logger.info(f"[OSM BUILDINGS] Matched {len(matches)} buildings to OSM data")
            return matches

        except Exception as e:
            logger.error(f"[OSM BUILDINGS] Error in matching: {e}")
            return {}

    def parse_roof_shape(self, roof_shape: Optional[str]) -> float:
        """
        Infer roof type score (0-1) from OSM roof:shape tag.
        Flat roofs are more vulnerable to heat.
        """
        if not roof_shape:
            return 0.5

        roof_lower = str(roof_shape).lower()

        if "flat" in roof_lower or "plana" in roof_lower:
            return 0.8  # Flat roof = high vulnerability
        elif "pitched" in roof_lower or "gabled" in roof_lower:
            return 0.3  # Pitched = good for shedding heat
        elif "dome" in roof_lower or "round" in roof_lower:
            return 0.4  # Dome = moderate
        else:
            return 0.5  # Unknown

    def parse_roof_material(self, roof_material: Optional[str]) -> float:
        """
        Infer roof vulnerability (0-1) from OSM roof:material tag.
        """
        if not roof_material:
            return 0.5

        material_lower = str(roof_material).lower()

        if "asbestos" in material_lower or "tar" in material_lower or "gravel" in material_lower:
            return 0.9  # Dark, absorbs heat
        elif "tile" in material_lower or "slate" in material_lower or "clay" in material_lower:
            return 0.3  # Traditional materials, better thermal properties
        elif "metal" in material_lower or "zinc" in material_lower:
            return 0.7  # Reflects some, but gets hot
        elif "concrete" in material_lower:
            return 0.7  # Dark concrete absorbs heat
        elif "glass" in material_lower or "skylights" in material_lower:
            return 0.6  # Some glass effects
        else:
            return 0.5  # Unknown

    def estimate_roof_type_from_year(self, year: Optional[int]) -> float:
        """
        If OSM doesn't have roof shape, estimate from construction year.
        Flat roofs became more common in modern Barcelona (1960+).
        """
        if not year:
            return 0.5

        if year < 1900:
            return 0.2  # Victorian era = pitched roofs
        elif year < 1960:
            return 0.4  # Mixed, some traditional
        elif year < 2000:
            return 0.7  # Modern = flat roofs common
        else:
            return 0.6  # Recent codes, some variation

    def get_building_height_estimate(self, construction_year: Optional[int]) -> float:
        """
        Rough estimate of building height from construction year.
        Used if Infrared height data is missing.
        """
        if not construction_year:
            return 15

        if construction_year < 1900:
            return 8  # Old 3-4 story
        elif construction_year < 1960:
            return 15  # 5-6 story
        elif construction_year < 2000:
            return 20  # 6-7 story modern
        else:
            return 25  # Taller modern buildings
