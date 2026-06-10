from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List
import json
import os
from config import Config

router = APIRouter()

class ZoneCreate(BaseModel):
    geojson: Dict
    center: List[float]
    size_m: int = 250

@router.get("/")
async def get_zones():
    """Get all zones."""
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

@router.post("/")
async def create_zone(zone: ZoneCreate):
    """Create a new zone."""
    lon, lat = zone.center
    zone_id = f"BCN_{zone.size_m}_X{int(lon*100)}_Y{int(lat*100)}"
    zone_path = os.path.join(Config.ZONES_DIR, f"{zone_id}.geojson")

    with open(zone_path, 'w') as f:
        json.dump(zone.geojson, f)

    return {"zone_id": zone_id, "geojson": zone.geojson}

@router.get("/{zone_id}")
async def get_zone(zone_id: str):
    """Get a specific zone by ID."""
    zone_path = os.path.join(Config.ZONES_DIR, f"{zone_id}.geojson")
    if os.path.exists(zone_path):
        with open(zone_path, 'r') as f:
            geojson = json.load(f)
            return {"zone_id": zone_id, "geojson": geojson}
    return {"error": f"Zone {zone_id} not found"}
