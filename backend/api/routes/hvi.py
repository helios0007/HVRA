from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Tuple
import logging
import asyncio

from services.hvi_calculator import HVICalculator
from services.urban_analysis import analyze_zone_vulnerability

logger = logging.getLogger(__name__)

router = APIRouter()

class HVIAnalysisRequest(BaseModel):
    zone_geojson: Dict
    center: List[float]
    include_thermal_analysis: bool = True

class HVIAnalysisResponse(BaseModel):
    zone_id: str
    buildings_with_hvi: Dict
    hvi_statistics: Dict
    thermal_analysis: Optional[Dict] = None

def _extract_bbox_from_geojson(zone_geojson: Dict) -> Optional[Tuple[float, float, float, float]]:
    """Extract bounding box (south, west, north, east) from GeoJSON polygon."""
    try:
        coords = zone_geojson.get("coordinates", [[]])[0]
        if not coords:
            return None

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]

        # Return as (south, west, north, east) for OSM
        return (min(lats), min(lons), max(lats), max(lons))
    except Exception as e:
        logger.debug(f"[HVI API] Could not extract bbox: {e}")
        return None

@router.post("/analyze_hvi", response_model=HVIAnalysisResponse)
async def analyze_zone_hvi(request: HVIAnalysisRequest):
    """
    Analyze Heat Vulnerability Index (HVI) for a zone.

    Combines:
    - Building characteristics (OSM/Catastro): construction era, roof type
    - Social vulnerability (Idescat): elderly %, income, isolation, disability
    - Thermal context (Infrared): LST, UHI, NDVI, street canyon ratios

    Returns buildings with HVI scores (0-10 scale) and zone statistics.
    """
    try:
        lon, lat = request.center
        zone_id = f"HVI_{int(lon*100)}_X{int(lat*100)}_Y"

        logger.info(f"[HVI API] Analyzing zone {zone_id}")

        # Extract zone bbox for OSM building query
        zone_bbox = _extract_bbox_from_geojson(request.zone_geojson)
        logger.info(f"[HVI API] Zone bbox: {zone_bbox}")

        # Step 1: Run thermal analysis (UTCI, heat stress, vegetation)
        thermal_analysis = None
        if request.include_thermal_analysis:
            try:
                thermal_analysis = await analyze_zone_vulnerability(
                    request.zone_geojson,
                    request.center
                )
                logger.info("[HVI API] Thermal analysis complete")
            except Exception as e:
                logger.warning(f"[HVI API] Thermal analysis failed: {e}")
                raise

        # Step 2: Extract buildings from thermal analysis
        if not thermal_analysis:
            raise ValueError("Thermal analysis did not return data")

        buildings_geojson = thermal_analysis.get("zone_buildings", {})
        if not buildings_geojson or not buildings_geojson.get("features"):
            raise ValueError("No buildings found in thermal analysis")

        logger.info(f"[HVI API] Found {len(buildings_geojson.get('features', []))} buildings")

        # Step 3: Calculate HVI for all buildings (with OSM + Idescat data)
        hvi_calc = HVICalculator()
        buildings_with_hvi = hvi_calc.calculate_hvi_for_zone(
            zone_geojson=request.zone_geojson,
            buildings_geojson=buildings_geojson,
            thermal_data=thermal_analysis,
            zone_bbox=zone_bbox
        )

        # Step 4: Get summary statistics
        hvi_stats = hvi_calc.get_hvi_statistics(buildings_with_hvi)

        logger.info(f"[HVI API] HVI calculation complete. Mean HVI: {hvi_stats.get('mean_hvi'):.1f}")

        return HVIAnalysisResponse(
            zone_id=zone_id,
            buildings_with_hvi=buildings_with_hvi,
            hvi_statistics=hvi_stats,
            thermal_analysis=thermal_analysis
        )

    except ValueError as e:
        logger.error(f"[HVI API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"HVI analysis failed: {str(e)}")
    except Exception as e:
        logger.error(f"[HVI API] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"HVI analysis error: {str(e)}")

@router.get("/hvi_factors")
async def get_hvi_factors():
    """
    Get HVI factor definitions and weights.
    Useful for frontend to display breakdown of vulnerability.
    """
    # Weights are GLOBAL contributions (all 12 sum to 1.00):
    # HVI = 0.15*age + 0.10*roof + 0.05*canyon + 0.05*green
    #     + 0.15*elderly + 0.10*income^-1 + 0.07*isolation + 0.05*no_AC + 0.03*disability
    #     + 0.15*LST + 0.05*UHI + 0.05*NDVI^-1
    return {
        "building_exposure": {
            "weight": 0.35,
            "factors": {
                "construction_era": {
                    "weight": 0.15,
                    "description": "Catastro INSPIRE WFS - pre-1980 = highest risk"
                },
                "roof_type": {
                    "weight": 0.10,
                    "description": "Catastro/OSM - flat roof = higher thermal mass risk"
                },
                "street_canyon": {
                    "weight": 0.05,
                    "description": "OSM + building heights - narrow = less ventilation"
                },
                "green_space": {
                    "weight": 0.05,
                    "description": "OSM parks/grass - absence within 50m = higher exposure"
                }
            }
        },
        "social_vulnerability": {
            "weight": 0.40,
            "factors": {
                "elderly_population": {
                    "weight": 0.15,
                    "description": "Idescat (census-section level) - excess mortality multiplier"
                },
                "household_income": {
                    "weight": 0.10,
                    "description": "Barcelona Open Data income atlas per census section - inverse scored"
                },
                "single_person_households": {
                    "weight": 0.07,
                    "description": "Census 2021 - social isolation proxy"
                },
                "ac_access_proxy": {
                    "weight": 0.05,
                    "description": "Census 2021 dwellings by cooling system - energy poverty"
                },
                "disability_prevalence": {
                    "weight": 0.03,
                    "description": "% population with mobility/self-care limitations (INE)"
                }
            }
        },
        "thermal_context": {
            "weight": 0.25,
            "factors": {
                "lst": {
                    "weight": 0.15,
                    "description": "Infrared City API - primary thermal signal"
                },
                "uhi_delta": {
                    "weight": 0.05,
                    "description": "Infrared City - local overheating above baseline"
                },
                "ndvi": {
                    "weight": 0.05,
                    "description": "Vegetation cover - inverse scored"
                }
            }
        },
        "hvi_scale": {
            "0-3": "Low vulnerability",
            "3-6": "Medium vulnerability",
            "6-8": "High vulnerability",
            "8-10": "Critical vulnerability"
        },
        "data_sources": {
            "catastro": "Catastro INSPIRE WFS (official construction year per building)",
            "idescat": "Idescat Taules v2 API (elderly per census section, income, households, cooling)",
            "bcn_open_data": "Barcelona Open Data (census section boundaries, income per section 2022)",
            "osm": "OpenStreetMap Overpass (green spaces, roof tags, street network)",
            "infrared": "Infrared SDK (thermal comfort, vegetation, LST)"
        }
    }

@router.post("/hvi_hotspots")
async def identify_hvi_hotspots(request: HVIAnalysisRequest):
    """
    Identify HVI hotspots (highest vulnerability areas) for intervention targeting.
    Returns ranked zones for prioritized interventions.
    """
    try:
        # Run full HVI analysis
        hvi_response = await analyze_zone_hvi(request)

        buildings = hvi_response.buildings_with_hvi.get("features", [])

        # Sort by HVI score
        sorted_buildings = sorted(
            buildings,
            key=lambda b: b.get("properties", {}).get("hvi_score", 0),
            reverse=True
        )

        # Top 20% are hotspots
        hotspot_count = max(1, len(sorted_buildings) // 5)
        hotspots = sorted_buildings[:hotspot_count]

        # Calculate hotspot statistics
        hotspot_hvi_values = [
            b.get("properties", {}).get("hvi_score", 0)
            for b in hotspots
        ]

        return {
            "hotspot_count": len(hotspots),
            "hotspot_coverage": f"{(len(hotspots)/len(buildings)*100):.1f}%",
            "mean_hotspot_hvi": round(sum(hotspot_hvi_values) / len(hotspot_hvi_values), 1),
            "buildings": hotspots,
            "recommendations": [
                f"Priority 1: Focus interventions on top {hotspot_count} buildings with HVI > 7.5",
                "Recommendation: Green infrastructure + cooling centers in hotspots",
                "Recommendation: Target AC subsidies to high-elderly + high-HVI areas",
                "Recommendation: Increase street vegetation in narrow canyons"
            ]
        }

    except Exception as e:
        logger.error(f"[HVI API] Hotspot identification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
