import requests
import logging
import re
from typing import Dict, List, Optional
from shapely.geometry import Point, shape
import json

logger = logging.getLogger(__name__)

class CatastroLoader:
    """
    Fetch building characteristics from the Spanish Catastro INSPIRE services.
    WFS endpoint (free, no API key): https://www.catastro.hacienda.gob.es/webinspire/index.html
    """

    WFS_BUILDINGS_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"

    def __init__(self, municipality_code: str = "08019"):  # Barcelona = 08019
        self.municipality_code = municipality_code
        self.cache = {}

    def get_buildings_in_bbox(
        self,
        bbox: tuple,  # (south, west, north, east) in lat/lon
        limit: int = 2000
    ) -> List[Dict]:
        """
        Fetch buildings in a bounding box from the Catastro INSPIRE WFS.
        Returns a list of dicts with cadastral reference, official
        construction year, and envelope center coordinates.
        """
        cache_key = str(bbox)
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            south, west, north, east = bbox
            logger.info(f"[CATASTRO] WFS query bbox: {bbox}")

            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "BU:Building",
                "srsName": "EPSG::4326",
                "bbox": f"{south},{west},{north},{east},EPSG::4326",
                "count": str(limit),
            }
            response = requests.get(self.WFS_BUILDINGS_URL, params=params, timeout=45)
            response.raise_for_status()

            buildings = self._parse_wfs_buildings(response.text)
            logger.info(f"[CATASTRO] WFS returned {len(buildings)} buildings with construction years")
            self.cache[cache_key] = buildings
            return buildings

        except Exception as e:
            logger.error(f"[CATASTRO] WFS error: {e}")
            return []

    @staticmethod
    def _parse_wfs_buildings(gml: str) -> List[Dict]:
        """
        Parse INSPIRE BU GML: extract cadastral reference, construction year
        (dateOfConstruction/beginning), and envelope center per building.
        Uses regex per feature block — the GML namespaces vary across responses.
        """
        buildings = []
        # Split into per-building blocks
        blocks = re.split(r"<bu-ext2d:Building ", gml)[1:]
        for block in blocks:
            try:
                ref_m = re.search(r"<base:localId>([^<]+)</base:localId>", block)
                year_m = re.search(
                    r"<bu-core2d:beginning>(\d{4})-", block
                )
                low_m = re.search(r"<gml:lowerCorner>([\d.\-]+) ([\d.\-]+)</gml:lowerCorner>", block)
                up_m = re.search(r"<gml:upperCorner>([\d.\-]+) ([\d.\-]+)</gml:upperCorner>", block)
                if not (low_m and up_m):
                    continue
                lat = (float(low_m.group(1)) + float(up_m.group(1))) / 2
                lon = (float(low_m.group(2)) + float(up_m.group(2))) / 2
                year = int(year_m.group(1)) if year_m else None
                # Catastro uses 1-Jan-1 / year<=1000 for unknown dates
                if year is not None and year < 1500:
                    year = None
                buildings.append({
                    "reference": ref_m.group(1) if ref_m else None,
                    "construction_year": year,
                    "lat": lat,
                    "lon": lon,
                })
            except Exception:
                continue
        return buildings

    def get_building_characteristics(self, building_id: str) -> Dict:
        """
        Fetch detailed characteristics for a specific building.
        Returns: construction_year, roof_type, materials, use_type, etc.
        """
        try:
            if building_id in self.cache:
                return self.cache[building_id]

            # Construct Catastro API URL for specific building
            url = f"https://www.catastro.minhap.es/api/ReferenciaCatastral/{building_id}/Inmueble"

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            characteristics = {
                "building_id": building_id,
                "construction_year": data.get("inmueble", {}).get("datos_catastrales", {}).get("año_construcción"),
                "roof_type": data.get("inmueble", {}).get("datos_catastrales", {}).get("tipo_cubierta"),
                "materials": data.get("inmueble", {}).get("datos_catastrales", {}).get("materiales"),
                "use_type": data.get("inmueble", {}).get("datos_catastrales", {}).get("uso"),
                "floor_area": data.get("inmueble", {}).get("datos_catastrales", {}).get("superficie_construida"),
            }

            self.cache[building_id] = characteristics
            return characteristics

        except requests.exceptions.RequestException as e:
            logger.error(f"[CATASTRO] API error for {building_id}: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"[CATASTRO] Error processing building {building_id}: {e}")
            return {"error": str(e)}

    def calculate_construction_era_score(self, year: Optional[int]) -> float:
        """
        Score construction era (0-1, higher = more vulnerable).
        Pre-1980 buildings typically have worse thermal performance.
        """
        if not year or year < 1800:
            return 0.5  # Unknown = medium

        if year < 1980:
            return 0.8  # Pre-1980 = high vulnerability
        elif year < 2007:
            return 0.4  # 1980-2007 = medium
        else:
            return 0.1  # Post-2007 (modern codes) = low

    def calculate_roof_type_score(self, roof_type: Optional[str]) -> float:
        """
        Score roof type (0-1, higher = more vulnerable).
        Flat roofs have higher thermal mass and absorb more heat.
        """
        if not roof_type:
            return 0.5

        roof_type_lower = roof_type.lower()

        if "plana" in roof_type_lower or "flat" in roof_type_lower:
            return 0.8  # Flat roof = high vulnerability
        elif "teja" in roof_type_lower or "tile" in roof_type_lower:
            return 0.3  # Tile = lower vulnerability
        else:
            return 0.5  # Other = medium
