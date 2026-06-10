import csv
import json
import logging
import os
from typing import Dict, List, Optional

from shapely.geometry import shape

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
SECTIONS_FILE = os.path.join(DATA_DIR, "census_sections_bcn_wgs84.json")
INCOME_FILE = os.path.join(DATA_DIR, "renda_2022_bcn.csv")


class CensusSectionLoader:
    """
    Map zone geometries to Barcelona census sections and provide
    section-level socioeconomic data.

    Local datasets (downloaded from Barcelona Open Data):
    - census_sections_bcn_wgs84.json: 1,068 section polygons (WGS84),
      derived from Unitats_Administratives_BCN (EPSG:25831 -> EPSG:4326)
    - renda_2022_bcn.csv: disposable household income per person and
      census section, 2022 (Atlas de Distribucion de Renta de los Hogares)
    """

    def __init__(self):
        self._sections = None   # list of (code, shapely geometry)
        self._income = None     # dict section_code -> EUR/person

    def _load_sections(self):
        if self._sections is not None:
            return
        self._sections = []
        try:
            with open(SECTIONS_FILE, encoding="utf-8") as f:
                fc = json.load(f)
            for feat in fc.get("features", []):
                code = feat["properties"]["section_code"]
                geom = shape(feat["geometry"])
                self._sections.append((code, geom))
            logger.info(f"[CENSUS] Loaded {len(self._sections)} census section polygons")
        except Exception as e:
            logger.error(f"[CENSUS] Could not load section polygons: {e}")

    def _load_income(self):
        if self._income is not None:
            return
        self._income = {}
        try:
            with open(INCOME_FILE, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    district = int(row["Codi_Districte"])
                    section = int(row["Seccio_Censal"])
                    code = f"080193{district:02d}{section:03d}"
                    try:
                        self._income[code] = float(row["Import_Euros"])
                    except (ValueError, TypeError):
                        continue
            logger.info(f"[CENSUS] Loaded income for {len(self._income)} sections")
        except Exception as e:
            logger.error(f"[CENSUS] Could not load income CSV: {e}")

    def get_sections_for_zone(self, zone_geojson: Dict) -> List[str]:
        """Census section codes whose polygons intersect the zone."""
        self._load_sections()
        try:
            zone = shape(zone_geojson)
        except Exception as e:
            logger.error(f"[CENSUS] Invalid zone geometry: {e}")
            return []

        codes = [code for code, geom in self._sections if geom.intersects(zone)]
        logger.info(f"[CENSUS] Zone intersects {len(codes)} census sections: {codes[:8]}")
        return codes

    def get_income_for_sections(self, section_codes: List[str]) -> Optional[float]:
        """Mean disposable household income per person (EUR/year, 2022)."""
        self._load_income()
        values = [self._income[c] for c in section_codes if c in self._income]
        if not values:
            return None
        mean_income = sum(values) / len(values)
        logger.info(
            f"[CENSUS] Income for {len(values)} sections: "
            f"mean €{mean_income:.0f} (range €{min(values):.0f}-€{max(values):.0f})"
        )
        return mean_income
