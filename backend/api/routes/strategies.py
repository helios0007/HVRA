from fastapi import APIRouter
import json
import os

router = APIRouter()

@router.get("/")
async def list_strategies():
    """List all available strategies."""
    strategy_path = "./data/urban_strategy_pool.json"
    if os.path.exists(strategy_path):
        with open(strategy_path, 'r') as f:
            pool = json.load(f)
            return {"strategies": pool.get("strategies", [])}
    return {"strategies": []}

@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get strategy by ID."""
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
