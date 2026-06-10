from typing import Dict, List
import json
import os

MOCK_STRATEGIES = [
    {
        "id": "green_corridors_linear",
        "name": "Green street corridors",
        "description": "Linear parks (20–40m wide) with native vegetation",
        "thermal_impact": {
            "mean_reduction_celsius": 2.1,
            "range": [1.5, 2.5]
        },
        "cost": {
            "min": 400,
            "max": 600,
            "unit": "€/100m²"
        },
        "implementation": {
            "duration_months": [20, 28],
            "phases": ["planning", "construction", "commissioning"]
        },
        "primary_drivers_addressed": ["vegetation_deficit", "urban_heat_island"],
        "co_benefits": {
            "air_quality_improvement_pct": 12,
            "jobs_construction": 250,
            "stormwater_management": "improved"
        }
    },
    {
        "id": "cool_roofs_retrofitting",
        "name": "Cool roofs retrofitting",
        "description": "High-albedo roof coatings",
        "thermal_impact": {
            "mean_reduction_celsius": 1.8,
            "range": [1.2, 2.3]
        },
        "cost": {
            "min": 15,
            "max": 25,
            "unit": "€/m²"
        },
        "implementation": {
            "duration_months": [3, 6],
            "phases": ["preparation", "coating", "curing"]
        },
        "primary_drivers_addressed": ["urban_heat_island"],
        "co_benefits": {
            "energy_savings_pct": 20,
            "jobs_construction": 50
        }
    },
    {
        "id": "water_features_fountains",
        "name": "Water features & fountains",
        "description": "Public fountains and water features for evaporative cooling",
        "thermal_impact": {
            "mean_reduction_celsius": 1.5,
            "range": [0.8, 2.0]
        },
        "cost": {
            "min": 50000,
            "max": 150000,
            "unit": "€/installation"
        },
        "implementation": {
            "duration_months": [6, 12],
            "phases": ["design", "construction", "testing"]
        },
        "primary_drivers_addressed": ["urban_heat_island", "poor_ventilation"],
        "co_benefits": {
            "aesthetic_value": "high",
            "community_engagement": "high",
            "jobs_construction": 30
        }
    }
]

def match_and_rank_strategies(vulnerability_profile: Dict) -> List[Dict]:
    """
    Match strategies to vulnerability drivers and rank by effectiveness.
    """
    # Defensively handle different driver formats
    drivers_raw = vulnerability_profile.get("drivers", []) if isinstance(vulnerability_profile, dict) else []
    drivers = {}

    for d in (drivers_raw if isinstance(drivers_raw, list) else []):
        try:
            if isinstance(d, dict):
                driver_name = d.get("driver", "unknown")
                severity = d.get("severity", 0)
            else:
                driver_name = str(d)
                severity = 0.5

            if driver_name and driver_name != "unknown":
                drivers[driver_name] = severity
        except Exception as e:
            print(f"Error processing driver {d}: {e}")

    matched = []
    for strategy in MOCK_STRATEGIES:
        score = sum(
            drivers.get(driver, 0.0)
            for driver in strategy.get("primary_drivers_addressed", [])
        ) / max(len(strategy.get("primary_drivers_addressed", [])), 1)

        if score > 0.3:
            matched.append({
                "rank": len(matched) + 1,
                "strategy_id": strategy["id"],
                "name": strategy["name"],
                "thermal_impact": strategy["thermal_impact"]["mean_reduction_celsius"],
                "cost_estimate": {
                    "min": strategy["cost"]["min"],
                    "max": strategy["cost"]["max"],
                    "unit": strategy["cost"]["unit"]
                },
                "implementation_months": sum(strategy["implementation"]["duration_months"]) // 2,
                "confidence": 0.85,
                "co_benefits": strategy.get("co_benefits", {}),
            })

    return sorted(matched, key=lambda x: x["thermal_impact"], reverse=True)[:5]
