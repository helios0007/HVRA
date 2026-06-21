from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import os
import uuid
from config import Config
from services.urban_analysis import analyze_zone_vulnerability
from services.intervention_engine import match_and_rank_strategies
from services.cache_service import get_cache

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
    Caches results to avoid re-analyzing identical zones.
    Requires valid Infrared API key in INFRARED_API_KEY environment variable.
    """
    try:
        lon, lat = request.center
        zone_id = f"BCN_{request.size_m}_X{int(lon*100)}_Y{int(lat*100)}"

        zone_path = os.path.join(Config.ZONES_DIR, f"{zone_id}.geojson")
        with open(zone_path, 'w') as f:
            json.dump(request.zone_geojson, f)

        # Check cache first — if same zone geometry was analyzed, return cached result
        cache = get_cache()
        cached_result = cache.get(request.zone_geojson)
        if cached_result:
            return AnalyzeResponse(
                zone_id=zone_id,
                zone_geojson=request.zone_geojson,
                vulnerability_analysis=cached_result['vulnerability_analysis'],
                suggested_interventions=cached_result['suggested_interventions']
            )

        # Not in cache — run the expensive analysis
        vulnerability = await analyze_zone_vulnerability(request.zone_geojson, request.center)
        suggestions = match_and_rank_strategies(vulnerability)

        # Store in cache for future requests
        cache_data = {
            'vulnerability_analysis': vulnerability,
            'suggested_interventions': suggestions
        }
        cache.set(request.zone_geojson, cache_data)

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

@router.get("/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    cache = get_cache()
    cache_dir = cache.cache_dir
    if os.path.exists(cache_dir):
        files = [f for f in os.listdir(cache_dir) if f.endswith('.json')]
        size_mb = sum(os.path.getsize(os.path.join(cache_dir, f)) for f in files) / (1024 * 1024)
        return {
            "cached_analyses": len(files),
            "cache_size_mb": round(size_mb, 2),
            "cache_dir": cache_dir
        }
    return {"cached_analyses": 0, "cache_size_mb": 0, "cache_dir": cache_dir}

@router.post("/cache/clear")
async def clear_cache():
    """Clear analysis cache (use after code changes affecting analysis logic)."""
    cache = get_cache()
    if cache.clear():
        return {"status": "cache cleared"}
    return {"error": "failed to clear cache"}
