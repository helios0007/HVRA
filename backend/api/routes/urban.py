from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import os
import uuid
from config import Config
from services.urban_analysis import analyze_zone_vulnerability
from services.intervention_engine import match_and_rank_strategies

router = APIRouter()

class AnalyzeRequest(BaseModel):
    zone_geojson: Dict
    center: List[float]
    size_m: int = 250

class AnalyzeResponse(BaseModel):
    zone_id: str
    zone_geojson: Dict
    vulnerability_analysis: Dict
    suggested_interventions: List[Dict]

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_zone(request: AnalyzeRequest):
    """
    Analyze urban zone vulnerability using Infrared SDK and return design suggestions.
    Requires valid Infrared API key in INFRARED_API_KEY environment variable.
    """
    try:
        lon, lat = request.center
        zone_id = f"BCN_{request.size_m}_X{int(lon*100)}_Y{int(lat*100)}"

        zone_path = os.path.join(Config.ZONES_DIR, f"{zone_id}.geojson")
        with open(zone_path, 'w') as f:
            json.dump(request.zone_geojson, f)

        vulnerability = await analyze_zone_vulnerability(request.zone_geojson, request.center)
        suggestions = match_and_rank_strategies(vulnerability)

        return AnalyzeResponse(
            zone_id=zone_id,
            zone_geojson=request.zone_geojson,
            vulnerability_analysis=vulnerability,
            suggested_interventions=suggestions
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Infrared analysis failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Infrared API error: {str(e)}")

@router.get("/zones")
async def list_zones():
    """List all analyzed zones."""
    zones = []
    if os.path.exists(Config.ZONES_DIR):
        for filename in os.listdir(Config.ZONES_DIR):
            if filename.endswith('.geojson'):
                zone_path = os.path.join(Config.ZONES_DIR, filename)
                with open(zone_path, 'r') as f:
                    geojson = json.load(f)
                    zones.append({
                        "zone_id": filename.replace('.geojson', ''),
                        "geojson": geojson
                    })
    return {"zones": zones}

@router.get("/strategy/{strategy_id}")
async def get_strategy_details(strategy_id: str):
    """Get detailed information about a strategy."""
    strategy_path = "./data/urban_strategy_pool.json"
    if os.path.exists(strategy_path):
        with open(strategy_path, 'r') as f:
            pool = json.load(f)
        strategy = next(
            (s for s in pool.get("strategies", []) if s["id"] == strategy_id),
            None
        )
        if strategy:
            return strategy
    return {"error": f"Strategy {strategy_id} not found"}
