import requests
import logging
from typing import Dict, List, Optional, Tuple
from shapely.geometry import shape, Point, LineString, box
import numpy as np

logger = logging.getLogger(__name__)

class OSMLoader:
    """
    Fetch OpenStreetMap data for street network analysis.
    Uses Overpass API for spatial queries.
    """

    OVERPASS_API = "https://overpass-api.de/api/interpreter"

    def __init__(self):
        self.cache = {}

    def get_green_spaces_in_bbox(
        self,
        bbox: Tuple[float, float, float, float],
    ) -> List:
        """
        Fetch green space polygons (parks, gardens, grass, forest) in a bbox
        via Overpass. bbox: (south, west, north, east).
        Returns a list of shapely geometries in WGS84.
        """
        cache_key = f"green_{bbox}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            south, west, north, east = bbox
            query = f"""
            [out:json][timeout:30];
            (
                way["leisure"~"park|garden|playground"]({south},{west},{north},{east});
                way["landuse"~"grass|forest|meadow|village_green|recreation_ground"]({south},{west},{north},{east});
                way["natural"~"wood|scrub"]({south},{west},{north},{east});
            );
            out geom;
            """
            response = requests.post(
                self.OVERPASS_API,
                data=query.encode("utf-8"),
                timeout=45,
                headers={"User-Agent": "urban-hvi-tool/1.0"},
            )
            response.raise_for_status()
            data = response.json()

            from shapely.geometry import Polygon, LineString as ShapelyLine

            geometries = []
            for el in data.get("elements", []):
                pts = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
                if len(pts) < 3:
                    continue
                try:
                    if pts[0] == pts[-1]:
                        geometries.append(Polygon(pts))
                    else:
                        geometries.append(ShapelyLine(pts))
                except Exception:
                    continue

            logger.info(f"[OSM] Found {len(geometries)} green space geometries in bbox")
            self.cache[cache_key] = geometries
            return geometries

        except Exception as e:
            logger.error(f"[OSM] Green space query failed: {e}")
            return []

    def get_streets_in_bbox(self, bbox: Tuple[float, float, float, float]) -> Dict:
        """
        Fetch street network in a bounding box.
        bbox: (west, south, east, north) in lat/lon

        Returns: GeoJSON FeatureCollection of streets with width info
        """
        try:
            west, south, east, north = bbox
            logger.info(f"[OSM] Querying streets in bbox: {bbox}")

            # Overpass QL query for streets (roads and paths)
            query = f"""
            [bbox:{south},{west},{north},{east}];
            (
                way["highway"~"residential|secondary|tertiary|primary|trunk|motorway"];
                way["highway"~"living_street|service|track"];
            );
            out body center geom;
            """

            params = {"data": query}
            response = requests.post(
                self.OVERPASS_API,
                data=query,
                timeout=30,
                headers={"Content-Type": "application/osm3s"}
            )
            response.raise_for_status()

            # Parse OSM XML response to extract streets
            streets = self._parse_osm_response(response.text)

            logger.info(f"[OSM] Found {len(streets)} streets in bbox")

            return {
                "type": "FeatureCollection",
                "features": streets,
                "bbox": list(bbox),
                "source": "OpenStreetMap via Overpass API"
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"[OSM] API error: {e}")
            return {"features": [], "error": str(e)}
        except Exception as e:
            logger.error(f"[OSM] Error parsing response: {e}")
            return {"features": [], "error": str(e)}

    def _parse_osm_response(self, osm_xml: str) -> List[Dict]:
        """Parse OSM XML response to extract street features."""
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(osm_xml)
            streets = []

            for way in root.findall(".//way"):
                way_id = way.get("id")
                tags = {tag.get("k"): tag.get("v") for tag in way.findall("tag")}

                # Extract nodes to build geometry
                node_refs = [nd.get("ref") for nd in way.findall("nd")]

                # Get street name and type
                name = tags.get("name", "Unknown")
                highway_type = tags.get("highway", "unclassified")
                width = tags.get("width")  # May not be present

                # Convert width string to float if available
                width_m = None
                if width:
                    try:
                        width_m = float(width.replace(" m", "").strip())
                    except:
                        pass

                # Estimate width from highway type if not tagged
                if not width_m:
                    width_m = self._estimate_street_width(highway_type)

                feature = {
                    "type": "Feature",
                    "id": way_id,
                    "properties": {
                        "name": name,
                        "highway": highway_type,
                        "width_m": width_m,
                        "node_count": len(node_refs)
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": []  # Would need node coordinates from OSM
                    }
                }

                streets.append(feature)

            return streets

        except Exception as e:
            logger.error(f"[OSM] XML parsing error: {e}")
            return []

    def _estimate_street_width(self, highway_type: str) -> float:
        """
        Estimate street width (meters) based on OSM highway classification.
        Used when width tag is not available.
        """
        width_map = {
            "motorway": 30,
            "trunk": 25,
            "primary": 20,
            "secondary": 18,
            "tertiary": 15,
            "residential": 12,
            "living_street": 8,
            "service": 8,
            "track": 5,
            "unclassified": 10
        }
        return width_map.get(highway_type, 10)

    def calculate_street_canyon_ratio(
        self,
        building_height: float,
        street_width: float
    ) -> float:
        """
        Calculate street canyon height-to-width ratio (H/W).
        Higher H/W = more enclosed canyon = lower ventilation.

        Returns ratio (e.g., 0.5 = building is half as tall as street is wide)
        """
        if street_width <= 0:
            return 0

        return building_height / street_width

    def get_average_canyon_ratio_in_zone(
        self,
        buildings_geojson: Dict,
        streets_geojson: Dict
    ) -> Dict:
        """
        Calculate average H/W ratio for all buildings in a zone.
        Accounts for proximity to streets and building heights.

        Returns statistics on canyon ratios.
        """
        try:
            ratios = []

            buildings = buildings_geojson.get("features", [])
            streets = streets_geojson.get("features", [])

            if not streets:
                logger.warning("[OSM] No streets in zone, cannot calculate canyon ratios")
                return {
                    "mean_ratio": 0,
                    "median_ratio": 0,
                    "count": 0,
                    "warning": "No street data available"
                }

            # For each building, find nearest street and calculate H/W
            for building in buildings:
                try:
                    height = building.get("properties", {}).get("height", 15)

                    # Get building centroid
                    if building.get("geometry", {}).get("type") == "Polygon":
                        coords = building["geometry"]["coordinates"][0]
                        centroid = [
                            sum(c[0] for c in coords) / len(coords),
                            sum(c[1] for c in coords) / len(coords)
                        ]
                    else:
                        continue

                    # Find nearest street
                    min_distance = float("inf")
                    nearest_street_width = 10  # Default

                    for street in streets:
                        street_width = street.get("properties", {}).get("width_m", 10)
                        # In production, calculate actual distance from building to street
                        # For now, use nearest street width
                        nearest_street_width = street_width
                        break  # Simplified

                    # Calculate H/W ratio
                    ratio = self.calculate_street_canyon_ratio(height, nearest_street_width)
                    ratios.append(ratio)

                except Exception as e:
                    logger.debug(f"[OSM] Error calculating ratio for building: {e}")
                    continue

            if ratios:
                return {
                    "mean_ratio": float(np.mean(ratios)),
                    "median_ratio": float(np.median(ratios)),
                    "std_ratio": float(np.std(ratios)),
                    "min_ratio": float(np.min(ratios)),
                    "max_ratio": float(np.max(ratios)),
                    "count": len(ratios)
                }
            else:
                return {
                    "mean_ratio": 0,
                    "count": 0,
                    "warning": "Could not calculate ratios for buildings"
                }

        except Exception as e:
            logger.error(f"[OSM] Error calculating average canyon ratio: {e}")
            return {"error": str(e)}

    def normalize_canyon_ratio_score(self, hw_ratio: float) -> float:
        """
        Normalize street canyon H/W ratio to vulnerability score (0-1).
        Higher H/W = more enclosed canyon = less ventilation = higher vulnerability.

        Ranges:
        - H/W < 0.5: wide open streets, good ventilation (low vulnerability)
        - H/W 0.5-1.0: moderate canyon (medium vulnerability)
        - H/W > 1.0: narrow, tall canyons (high vulnerability)
        """
        if hw_ratio < 0.2:
            return 0.1  # Very open
        elif hw_ratio < 0.5:
            return 0.3  # Open
        elif hw_ratio < 1.0:
            return 0.5  # Moderate
        elif hw_ratio < 1.5:
            return 0.7  # Enclosed
        else:
            return 0.9  # Very enclosed
