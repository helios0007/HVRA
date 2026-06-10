import logging
import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from services.data_loaders.catastro_loader import CatastroLoader
from services.data_loaders.census_section_loader import CensusSectionLoader
from services.data_loaders.idescat_loader import IdescatLoader
from services.data_loaders.osm_loader import OSMLoader
from services.data_loaders.osm_building_loader import OSMBuildingLoader
from services.data_loaders.satellite_loader import SatelliteLoader

logger = logging.getLogger(__name__)

class HVICalculator:
    """
    Heat Vulnerability Index (HVI) calculator.

    Combines three weighted components:
    - Building Exposure (35%): construction era, roof type, street canyon, green space
    - Social Vulnerability (40%): elderly, income, isolation, AC access, disability
    - Thermal Context (25%): LST, UHI, NDVI

    Final score: 0-10 scale (higher = more vulnerable)
    """

    # Composite score formula (all weights are absolute, sum to 1.00):
    # HVI = 0.15*age + 0.10*roof + 0.05*canyon + 0.05*green
    #     + 0.15*elderly + 0.10*income^-1 + 0.07*isolation + 0.05*no_AC + 0.03*disability
    #     + 0.15*LST + 0.05*UHI + 0.05*NDVI^-1
    # Bucket totals: Building 0.35, Social 0.40, Thermal 0.25

    # Weights for main components (bucket weights)
    WEIGHTS = {
        "building_exposure": 0.35,
        "social_vulnerability": 0.40,
        "thermal_context": 0.25
    }

    # Sub-weights within Building Exposure (normalized so bucket * sub = absolute weight)
    # era: 0.15/0.35, roof: 0.10/0.35, canyon: 0.05/0.35, green: 0.05/0.35
    BUILDING_WEIGHTS = {
        "construction_era": 0.15 / 0.35,
        "roof_type": 0.10 / 0.35,
        "street_canyon": 0.05 / 0.35,
        "green_space": 0.05 / 0.35
    }

    # Sub-weights within Social Vulnerability
    # elderly: 0.15/0.40, income: 0.10/0.40, isolation: 0.07/0.40,
    # no_AC: 0.05/0.40, disability: 0.03/0.40
    SOCIAL_WEIGHTS = {
        "elderly_population": 0.15 / 0.40,
        "household_income": 0.10 / 0.40,
        "single_person_households": 0.07 / 0.40,
        "ac_access_proxy": 0.05 / 0.40,  # Energy poverty proxy: % households without AC
        "disability_prevalence": 0.03 / 0.40
    }

    # Sub-weights within Thermal Context
    # LST: 0.15/0.25, UHI: 0.05/0.25, NDVI: 0.05/0.25
    THERMAL_WEIGHTS = {
        "lst": 0.15 / 0.25,
        "uhi_delta": 0.05 / 0.25,
        "ndvi": 0.05 / 0.25
    }

    def __init__(self):
        self.catastro = CatastroLoader()
        self.idescat = IdescatLoader()
        self.osm = OSMLoader()
        self.osm_buildings = OSMBuildingLoader()
        self.census_sections = CensusSectionLoader()
        self.satellite = SatelliteLoader()

    def calculate_hvi_for_zone(
        self,
        zone_geojson: Dict,
        buildings_geojson: Dict,
        thermal_data: Dict,
        social_data: Dict = None,
        zone_bbox: Tuple[float, float, float, float] = None
    ) -> Dict:
        """
        Calculate Heat Vulnerability Index for all buildings in a zone.

        Args:
            zone_geojson: GeoJSON of zone polygon
            buildings_geojson: GeoJSON FeatureCollection of buildings
            thermal_data: Dict with UTCI grid, LST, NDVI from Infrared
            social_data: Dict with census data from Idescat (optional)
            zone_bbox: (south, west, north, east) for OSM building query (optional)

        Returns:
            Updated buildings_geojson with added hvi_score property
        """
        try:
            logger.info("[HVI] Starting HVI calculation for zone")
            logger.info(f"[HVI] Buildings count: {len(buildings_geojson.get('features', []))}")
            logger.info(f"[HVI] Zone bbox: {zone_bbox}, type: {type(zone_bbox)}")
            logger.info(f"[HVI] Thermal data keys: {list(thermal_data.keys()) if isinstance(thermal_data, dict) else 'NOT A DICT'}")

            # Step 1a: Fetch official construction years from Catastro INSPIRE WFS
            catastro_buildings = []
            if zone_bbox:
                try:
                    catastro_buildings = self.catastro.get_buildings_in_bbox(zone_bbox)
                    logger.info(f"[HVI] Catastro WFS: {len(catastro_buildings)} buildings with construction years")
                except Exception as e:
                    logger.warning(f"[HVI] Could not fetch Catastro data: {e}")

            # Step 1b: Fetch OSM building data (roof types, fallback construction years)
            osm_building_data = {}
            if zone_bbox:
                try:
                    osm_building_data = self.osm_buildings.get_building_construction_dates(zone_bbox)
                    logger.info(f"[HVI] Fetched OSM data for {len(osm_building_data)} buildings")
                except Exception as e:
                    logger.warning(f"[HVI] Could not fetch OSM building data: {e}")
                    osm_building_data = {}

            # Step 1c: Fetch green space geometries (parks/grass/forest) around the zone
            green_geometries = []
            if zone_bbox:
                try:
                    south, west, north, east = zone_bbox
                    pad = 0.002  # ~200m padding so edge buildings see nearby parks
                    green_geometries = self.osm.get_green_spaces_in_bbox(
                        (south - pad, west - pad, north + pad, east + pad)
                    )
                except Exception as e:
                    logger.warning(f"[HVI] Could not fetch green spaces: {e}")

            # Step 1d: Fetch real satellite thermal data (Landsat LST + Sentinel-2 NDVI)
            satellite_data = {}
            if zone_bbox:
                try:
                    south, west, north, east = zone_bbox
                    sat_bbox = (west, south, east, north)  # loaders expect WSEN
                    lst = self.satellite.get_lst(sat_bbox)
                    ndvi = self.satellite.get_ndvi(sat_bbox)
                    if lst:
                        satellite_data["lst"] = lst
                    if ndvi:
                        satellite_data["ndvi"] = ndvi
                except Exception as e:
                    logger.warning(f"[HVI] Satellite data fetch failed: {e}")

            # Step 2: Fetch Idescat social data (municipality baseline)
            if not social_data:
                try:
                    social_data = self.idescat.get_municipality_data()
                    logger.info("[HVI] Fetched Idescat social data")
                except Exception as e:
                    logger.warning(f"[HVI] Could not fetch Idescat data: {e}")
                    social_data = {}

            # Step 2b: Refine with census-section level data where available
            try:
                section_codes = self.census_sections.get_sections_for_zone(zone_geojson)
                if section_codes:
                    sec_elderly = self.idescat.get_elderly_percentage_for_sections(section_codes)
                    if sec_elderly is not None:
                        social_data["elderly_pct"] = sec_elderly
                    sec_income = self.census_sections.get_income_for_sections(section_codes)
                    if sec_income is not None:
                        social_data["income_per_capita_eur"] = sec_income
                    social_data["census_sections"] = section_codes
            except Exception as e:
                logger.warning(f"[HVI] Census-section refinement failed: {e}")

            # Step 3: Calculate component scores
            try:
                logger.info("[HVI] Calculating building exposure scores...")
                building_scores = self._calculate_building_exposure_scores(
                    buildings_geojson,
                    thermal_data,
                    osm_building_data,
                    catastro_buildings,
                    green_geometries
                )
                logger.info(f"[HVI] Building exposure scores complete: {len(building_scores)} buildings")
            except Exception as e:
                logger.error(f"[HVI] Error calculating building exposure: {e}", exc_info=True)
                building_scores = {}

            try:
                logger.info("[HVI] Calculating social vulnerability...")
                population = thermal_data.get("population_in_zone", 1000) if isinstance(thermal_data, dict) else 1000
                social_score = self._calculate_social_vulnerability_score(
                    social_data,
                    population
                )
                logger.info(f"[HVI] Social vulnerability score: {social_score:.2f}")
            except Exception as e:
                logger.error(f"[HVI] Error calculating social vulnerability: {e}", exc_info=True)
                social_score = 0.5

            try:
                logger.info("[HVI] Calculating thermal context...")
                thermal_score = self._calculate_thermal_context_score(thermal_data, satellite_data)
                logger.info(f"[HVI] Thermal context score: {thermal_score:.2f}")
            except Exception as e:
                logger.error(f"[HVI] Error calculating thermal context: {e}", exc_info=True)
                thermal_score = 0.5

            # Per-factor scores shared across the zone (social + thermal)
            social_factors = getattr(self, "_last_social_factors", {}) or {}
            thermal_factors = getattr(self, "_last_thermal_factors", {}) or {}

            # Add scores to buildings
            for i, feature in enumerate(buildings_geojson.get("features", [])):
                building_id = feature.get("properties", {}).get("id") or str(i)

                # Get individual component scores
                bscore = building_scores.get(str(building_id), building_scores.get(building_id, {}))
                building_exp_score = bscore.get("total", 0.5)

                # Composite HVI (0-10): bucket_weight * bucket_score, where each
                # bucket_score is the absolute-weight formula normalized within the bucket.
                # Equivalent to: 10 * (0.15*age + 0.10*roof + ... + 0.05*NDVI^-1)
                hvi = (
                    self.WEIGHTS["building_exposure"] * building_exp_score * 10 +
                    self.WEIGHTS["social_vulnerability"] * social_score * 10 +
                    self.WEIGHTS["thermal_context"] * thermal_score * 10
                )

                hvi = float(np.clip(hvi, 0, 10))

                # Add to feature properties
                feature["properties"]["hvi_score"] = round(hvi, 1)
                feature["properties"]["hvi_breakdown"] = {
                    "building_exposure": round(building_exp_score * 10, 1),
                    "social_vulnerability": round(social_score * 10, 1),
                    "thermal_context": round(thermal_score * 10, 1)
                }
                # Full 12-factor breakdown (each factor 0-1, weight = global contribution)
                feature["properties"]["hvi_factors"] = {
                    "construction_era": {"score": round(bscore.get("construction_era", 0.5), 2), "weight": 0.15},
                    "roof_type": {"score": round(bscore.get("roof_type", 0.5), 2), "weight": 0.10},
                    "street_canyon": {"score": round(bscore.get("street_canyon", 0.5), 2), "weight": 0.05},
                    "green_space": {"score": round(bscore.get("green_space", 0.5), 2), "weight": 0.05},
                    "elderly_population": {"score": round(social_factors.get("elderly", 0.5), 2), "weight": 0.15},
                    "household_income": {"score": round(social_factors.get("income", 0.5), 2), "weight": 0.10},
                    "social_isolation": {"score": round(social_factors.get("isolation", 0.5), 2), "weight": 0.07},
                    "no_ac": {"score": round(social_factors.get("ac_access", 0.5), 2), "weight": 0.05},
                    "disability": {"score": round(social_factors.get("disability", 0.5), 2), "weight": 0.03},
                    "lst": {"score": round(thermal_factors.get("lst", 0.5), 2), "weight": 0.15},
                    "uhi_delta": {"score": round(thermal_factors.get("uhi", 0.5), 2), "weight": 0.05},
                    "ndvi": {"score": round(thermal_factors.get("ndvi", 0.5), 2), "weight": 0.05}
                }

            logger.info("[HVI] Successfully calculated HVI for all buildings")

            return buildings_geojson

        except Exception as e:
            logger.error(f"[HVI] Error calculating HVI: {e}")
            return buildings_geojson

    @staticmethod
    def _building_centroid(feature: Dict) -> Optional[Tuple[float, float]]:
        """Approximate centroid (lon, lat) of a building polygon feature."""
        try:
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates")
            if geom.get("type") == "Polygon":
                ring = coords[0]
            elif geom.get("type") == "MultiPolygon":
                ring = coords[0][0]
            else:
                return None
            lon = sum(c[0] for c in ring) / len(ring)
            lat = sum(c[1] for c in ring) / len(ring)
            return (lon, lat)
        except Exception:
            return None

    @staticmethod
    def _match_catastro_year(
        centroid: Tuple[float, float],
        catastro_buildings: List[Dict],
        max_dist_deg: float = 0.0005,  # ~50m
    ) -> Optional[int]:
        """Find construction year of the nearest Catastro building."""
        if not centroid or not catastro_buildings:
            return None
        lon, lat = centroid
        cos_lat = math.cos(math.radians(lat))
        best_year, best_d2 = None, max_dist_deg ** 2
        for cb in catastro_buildings:
            if cb.get("construction_year") is None:
                continue
            dx = (cb["lon"] - lon) * cos_lat
            dy = cb["lat"] - lat
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best_year = cb["construction_year"]
        return best_year

    def _calculate_building_exposure_scores(
        self,
        buildings_geojson: Dict,
        thermal_data: Dict,
        osm_building_data: Dict = None,
        catastro_buildings: List[Dict] = None,
        green_geometries: List = None
    ) -> Dict:
        """
        Calculate building exposure scores (0-1) for each building.
        Components: construction era, roof type, street canyon, green space.

        Construction year priority: Catastro WFS (official) -> OSM -> feature props.
        Green space: real distance to nearest OSM park/grass polygon.
        """
        scores = {}
        catastro_buildings = catastro_buildings or []
        green_geometries = green_geometries or []
        catastro_hits = 0

        # Pre-scale green geometries once (lon * cos(lat)) so distances are isotropic
        scaled_green = []
        features_list = buildings_geojson.get("features", [])
        if green_geometries and features_list:
            ref = self._building_centroid(features_list[0])
            if ref:
                cos_lat = math.cos(math.radians(ref[1]))
                from shapely.ops import transform as shp_transform
                for geom in green_geometries:
                    try:
                        scaled_green.append(
                            shp_transform(lambda x, y, z=None: (x * cos_lat, y), geom)
                        )
                    except Exception:
                        continue

        for feature in buildings_geojson.get("features", []):
            try:
                building_id = feature.get("properties", {}).get("id") or feature.get("id")
                props = feature.get("properties", {})
                centroid = self._building_centroid(feature)

                # Construction year: Catastro (official) → OSM → feature properties
                construction_year = self._match_catastro_year(centroid, catastro_buildings)
                if construction_year:
                    catastro_hits += 1
                elif osm_building_data and str(building_id) in osm_building_data:
                    construction_year = osm_building_data[str(building_id)].get("construction_year")
                else:
                    construction_year = props.get("construction_year")

                # Get roof type from: OSM → feature properties → estimate from year
                roof_type = None
                roof_score = None

                if osm_building_data and str(building_id) in osm_building_data:
                    osm_data = osm_building_data[str(building_id)]
                    roof_shape = osm_data.get("roof_shape")
                    roof_material = osm_data.get("roof_material")

                    if roof_shape:
                        roof_score = self.osm_buildings.parse_roof_shape(roof_shape)
                    if roof_material and not roof_score:
                        roof_score = self.osm_buildings.parse_roof_material(roof_material)

                if not roof_score:
                    if construction_year:
                        roof_score = self.osm_buildings.estimate_roof_type_from_year(construction_year)
                    else:
                        roof_score = self.catastro.calculate_roof_type_score(roof_type)

                # Calculate construction era score
                era_score = self.catastro.calculate_construction_era_score(construction_year)

                # Street canyon score
                canyon_score = self.osm.normalize_canyon_ratio_score(
                    props.get("street_canyon_hw_ratio", 0.5)
                )

                # Green space: real distance to nearest park/grass polygon
                green_score = self._calculate_green_space_score(
                    feature,
                    thermal_data,
                    scaled_green,
                    centroid
                )

                # Weighted sum
                building_exp = (
                    self.BUILDING_WEIGHTS["construction_era"] * era_score +
                    self.BUILDING_WEIGHTS["roof_type"] * roof_score +
                    self.BUILDING_WEIGHTS["street_canyon"] * canyon_score +
                    self.BUILDING_WEIGHTS["green_space"] * green_score
                )

                scores[str(building_id)] = {
                    "total": building_exp,
                    "construction_era": era_score,
                    "roof_type": roof_score,
                    "street_canyon": canyon_score,
                    "green_space": green_score,
                    "construction_year": construction_year
                }

            except Exception as e:
                logger.debug(f"[HVI] Error scoring building: {e}")
                scores[str(building_id)] = {"total": 0.5}

        logger.info(
            f"[HVI] Catastro year matches: {catastro_hits}/{len(scores)} buildings; "
            f"green geometries available: {len(green_geometries)}"
        )
        return scores

    def _calculate_social_vulnerability_score(
        self,
        social_data: Dict,
        population: int = 1000
    ) -> float:
        """
        Calculate social vulnerability score (0-1) for the zone.
        Aggregates: elderly %, income, isolation, AC access, disability.

        Tries to extract from Idescat API responses; falls back to Barcelona averages.
        """
        try:
            scores = {}

            # Real Idescat values (flat keys), fall back to Barcelona averages
            social_data = social_data or {}
            elderly_pct = social_data.get("elderly_pct") or 17.0
            income_pc_eur = social_data.get("income_per_capita_eur")
            single_person_pct = social_data.get("single_person_pct") or 22.0
            disability_pct = social_data.get("disability_pct") or 8.0
            # % dwellings without cooling system (ceph census table)
            no_ac_pct = social_data.get("no_ac_pct") or 35.0

            logger.debug(
                f"[HVI] Social data: elderly={elderly_pct:.1f}%, "
                f"income_pc=€{income_pc_eur}, single={single_person_pct:.1f}%, "
                f"no_AC={no_ac_pct:.1f}%, disability={disability_pct:.1f}%"
            )

            # Score each factor (0-1, higher = more vulnerable)
            scores["elderly"] = self.idescat.normalize_demographic_score(elderly_pct)
            if income_pc_eur:
                scores["income"] = self.idescat.normalize_income_per_capita_score(income_pc_eur)
            else:
                scores["income"] = self.idescat.normalize_income_score(28000)
            scores["isolation"] = self.idescat.normalize_demographic_score(single_person_pct)
            scores["ac_access"] = self.idescat.normalize_demographic_score(no_ac_pct)
            scores["disability"] = self.idescat.normalize_demographic_score(disability_pct)

            # Weighted sum
            social_vuln = (
                self.SOCIAL_WEIGHTS["elderly_population"] * scores["elderly"] +
                self.SOCIAL_WEIGHTS["household_income"] * scores["income"] +
                self.SOCIAL_WEIGHTS["single_person_households"] * scores["isolation"] +
                self.SOCIAL_WEIGHTS["ac_access_proxy"] * scores["ac_access"] +
                self.SOCIAL_WEIGHTS["disability_prevalence"] * scores["disability"]
            )

            logger.info(f"[HVI] Social vulnerability score: {social_vuln:.2f}")
            self._last_social_factors = scores
            return float(np.clip(social_vuln, 0, 1))

        except Exception as e:
            logger.error(f"[HVI] Error calculating social vulnerability: {e}")
            self._last_social_factors = {}
            return 0.5

    def _calculate_thermal_context_score(
        self,
        thermal_data: Dict,
        satellite_data: Dict = None
    ) -> float:
        """
        Calculate thermal context score (0-1).
        Primary: real satellite data — Landsat C2 L2 surface temperature
        (LST + UHI delta vs city mean) and Sentinel-2 NDVI.
        Fallback: Infrared UTCI/vegetation proxies.
        """
        try:
            scores = {}
            satellite_data = satellite_data or {}
            sat_lst = satellite_data.get("lst") or {}
            sat_ndvi = satellite_data.get("ndvi") or {}

            # --- LST score ---
            if sat_lst.get("zone_lst_c") is not None:
                # Real Landsat surface temperature. Summer LST in Barcelona
                # ranges roughly 30C (vegetated/coastal) to 48C (dense urban).
                lst_score = min(1.0, max(0.0, (sat_lst["zone_lst_c"] - 30.0) / 18.0))
                logger.info(f"[HVI] LST score from Landsat: {lst_score:.2f} ({sat_lst['zone_lst_c']:.1f}C)")
            else:
                # Fallback: Infrared peak UTCI (baseline ~28C, max concern ~40C)
                peak_temp = thermal_data.get("peak_utci_celsius", 32)
                lst_score = min(1.0, max(0, (peak_temp - 28) / 12))

            # --- UHI delta score ---
            if sat_lst.get("uhi_delta_c") is not None:
                # Real zone-vs-city LST difference from the same Landsat scene.
                # 0C = at city mean; +5C or more = severe local overheating.
                uhi_score = min(1.0, max(0.0, sat_lst["uhi_delta_c"] / 5.0))
                logger.info(f"[HVI] UHI score from Landsat: {uhi_score:.2f} (delta {sat_lst['uhi_delta_c']:+.1f}C)")
            else:
                mean_temp = thermal_data.get("mean_utci_celsius", 28)
                uhi_delta = max(0, mean_temp - 24)
                uhi_score = min(1.0, uhi_delta / 8)

            # --- NDVI score (inverse: less vegetation = higher vulnerability) ---
            if sat_ndvi.get("mean_ndvi") is not None:
                # Real Sentinel-2 NDVI. Dense urban ~0.1, leafy districts ~0.4+
                ndvi_score = min(1.0, max(0.0, 1.0 - (sat_ndvi["mean_ndvi"] / 0.5)))
                logger.info(f"[HVI] NDVI score from Sentinel-2: {ndvi_score:.2f} (NDVI {sat_ndvi['mean_ndvi']:.3f})")
            else:
                vegetation_count = thermal_data.get("vegetation_count", 100)
                ndvi_score = max(0, 1.0 - (vegetation_count / 300))

            scores = {
                "lst": lst_score,
                "uhi": uhi_score,
                "ndvi": ndvi_score
            }

            # Weighted sum
            thermal_context = (
                self.THERMAL_WEIGHTS["lst"] * lst_score +
                self.THERMAL_WEIGHTS["uhi_delta"] * uhi_score +
                self.THERMAL_WEIGHTS["ndvi"] * ndvi_score
            )

            logger.debug(f"[HVI] Thermal context score: {thermal_context:.2f}")
            self._last_thermal_factors = scores
            return float(np.clip(thermal_context, 0, 1))

        except Exception as e:
            logger.error(f"[HVI] Error calculating thermal context: {e}")
            self._last_thermal_factors = {}
            return 0.5

    def _calculate_green_space_score(
        self,
        building_feature: Dict,
        thermal_data: Dict,
        green_geometries: List = None,
        centroid: Tuple[float, float] = None
    ) -> float:
        """
        Green space proximity score (0-1). Higher = less green nearby.
        Primary: real distance from building centroid to nearest OSM
        park/grass polygon (spec: green within 50m = low exposure).
        `green_geometries` must already be lon-scaled by cos(lat).
        Fallback: zone-wide vegetation count from Infrared.
        """
        try:
            if green_geometries and centroid:
                from shapely.geometry import Point

                lon, lat = centroid
                cos_lat = math.cos(math.radians(lat))
                pt = Point(lon * cos_lat, lat)
                # Distance in "scaled degrees"; 1 deg lat ~ 111.32 km
                min_dist_m = float("inf")
                for geom in green_geometries:
                    try:
                        d = pt.distance(geom) * 111320.0
                        if d < min_dist_m:
                            min_dist_m = d
                    except Exception:
                        continue

                if min_dist_m <= 50:
                    return 0.15   # Green space within 50m
                elif min_dist_m <= 100:
                    return 0.45
                elif min_dist_m <= 200:
                    return 0.7
                else:
                    return 0.9    # No green nearby

            # Fallback: aggregate vegetation count from Infrared
            vegetation_count = thermal_data.get("vegetation_count", 100)
            if vegetation_count > 150:
                return 0.2
            elif vegetation_count > 80:
                return 0.4
            elif vegetation_count > 40:
                return 0.6
            else:
                return 0.9

        except Exception as e:
            logger.debug(f"[HVI] Error calculating green space score: {e}")
            return 0.5

    def get_hvi_statistics(self, buildings_geojson: Dict) -> Dict:
        """
        Calculate summary statistics for HVI scores in the zone.
        """
        try:
            hvi_values = [
                f.get("properties", {}).get("hvi_score", 5.0)
                for f in buildings_geojson.get("features", [])
            ]

            if not hvi_values:
                return {"error": "No buildings with HVI scores"}

            return {
                "mean_hvi": round(float(np.mean(hvi_values)), 1),
                "median_hvi": round(float(np.median(hvi_values)), 1),
                "std_hvi": round(float(np.std(hvi_values)), 1),
                "min_hvi": round(float(np.min(hvi_values)), 1),
                "max_hvi": round(float(np.max(hvi_values)), 1),
                "count": len(hvi_values),
                "high_vulnerability": sum(1 for v in hvi_values if v >= 7),  # Count buildings with high HVI
                "medium_vulnerability": sum(1 for v in hvi_values if 4 <= v < 7),
                "low_vulnerability": sum(1 for v in hvi_values if v < 4)
            }

        except Exception as e:
            logger.error(f"[HVI] Error calculating statistics: {e}")
            return {"error": str(e)}
