from typing import Dict, List

# Evidence-based heat intervention strategies.
# Cooling effects are drawn from peer-reviewed literature / authoritative
# reports — see "evidence" per entry. Mirrors the frontend catalog in
# frontend/src/data/interventionCatalog.js.

STRATEGIES = [
    {
        "id": "street_trees",
        "name": "Street tree planting",
        "description": "Canopy trees on adjacent streets — shading plus evapotranspiration",
        "evidence": "-2.6C air (US avg); -8.2C PET per street tree; -0.13C LST per 10% canopy (EU coefficient, Nature Comms 2021)",
        "thermal_impact": {"mean_reduction_celsius": 2.6, "range": [1.5, 4.0]},
        "cost": {"min": 500, "max": 2000, "unit": "EUR/tree"},
        "implementation": {"duration_months": [12, 24], "phases": ["species selection", "planting", "establishment"]},
        "primary_drivers_addressed": ["vegetation_deficit", "urban_heat_island", "thermal_stress_exposure"],
        "co_benefits": {"air_quality": "improved", "stormwater_management": "improved", "wellbeing": "high"},
    },
    {
        "id": "cool_roofs",
        "name": "Cool / white roof retrofitting",
        "description": "High-albedo roof coatings on flat dark roofs",
        "evidence": "Up to -40C roof surface; -1.7C surface UHI at 50% coverage, albedo 0.65 (IOP 2014)",
        "thermal_impact": {"mean_reduction_celsius": 1.7, "range": [1.0, 2.5]},
        "cost": {"min": 10, "max": 30, "unit": "EUR/m2"},
        "implementation": {"duration_months": [3, 6], "phases": ["preparation", "coating", "curing"]},
        "primary_drivers_addressed": ["urban_heat_island", "high_building_density"],
        "co_benefits": {"energy_savings_pct": 20, "roof_lifetime": "extended"},
    },
    {
        "id": "depave_greening",
        "name": "De-paving + pocket greening",
        "description": "Replace sealed asphalt with permeable planted surfaces (Eixample courtyard model)",
        "evidence": "Eixample measured: 1%->15% permeable = -5C surface (~ -0.36C per +1% permeable)",
        "thermal_impact": {"mean_reduction_celsius": 2.0, "range": [1.0, 5.0]},
        "cost": {"min": 30, "max": 80, "unit": "EUR/m2"},
        "implementation": {"duration_months": [6, 18], "phases": ["design", "de-paving", "planting"]},
        "primary_drivers_addressed": ["vegetation_deficit", "urban_heat_island", "high_building_density"],
        "co_benefits": {"flood_mitigation": "improved", "public_space": "improved"},
    },
    {
        "id": "shade_structures",
        "name": "Shade sails, pergolas & awnings",
        "description": "Engineered shade over sidewalks and plazas (Eixample awning tradition)",
        "evidence": "-50% mean radiant temperature under shade; -5 to -15C UTCI at noon (Mediterranean)",
        "thermal_impact": {"mean_reduction_celsius": 3.0, "range": [2.0, 6.0]},
        "cost": {"min": 200, "max": 800, "unit": "EUR/m2"},
        "implementation": {"duration_months": [2, 6], "phases": ["design", "fabrication", "installation"]},
        "primary_drivers_addressed": ["thermal_stress_exposure", "poor_ventilation"],
        "co_benefits": {"immediate_effect": True, "street_life": "improved"},
    },
    {
        "id": "ventilation_corridors",
        "name": "Ventilation corridor opening",
        "description": "Traffic calming + street greening to channel cooler peripheral air",
        "evidence": "Superblocks measured -0.4C ambient (Urban Ecology Agency); corridor trees -3.2C max",
        "thermal_impact": {"mean_reduction_celsius": 0.4, "range": [0.4, 1.2]},
        "cost": {"min": 50000, "max": 150000, "unit": "EUR/street segment"},
        "implementation": {"duration_months": [12, 36], "phases": ["planning", "traffic reordering", "greening"]},
        "primary_drivers_addressed": ["poor_ventilation", "urban_heat_island"],
        "co_benefits": {"air_quality": "improved", "noise": "reduced", "active_mobility": "improved"},
    },
    {
        "id": "climate_shelters",
        "name": "Climate shelter designation",
        "description": "Equip nearby public buildings as refugis climatics (26C, water, rest areas)",
        "evidence": "Barcelona network: 368 shelters by 2024; protective for elderly/isolated residents",
        "thermal_impact": {"mean_reduction_celsius": 0.0, "range": [0.0, 0.0]},
        "cost": {"min": 5000, "max": 50000, "unit": "EUR/shelter"},
        "implementation": {"duration_months": [3, 12], "phases": ["selection", "equipment", "communication"]},
        "primary_drivers_addressed": ["thermal_stress_exposure"],
        "co_benefits": {"social_contact": "improved", "immediate_effect": True, "health_protection": "high"},
    },
]


def match_and_rank_strategies(vulnerability_profile: Dict) -> List[Dict]:
    """
    Match strategies to vulnerability drivers and rank by effectiveness.
    """
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
    for strategy in STRATEGIES:
        score = sum(
            drivers.get(driver, 0.0)
            for driver in strategy.get("primary_drivers_addressed", [])
        ) / max(len(strategy.get("primary_drivers_addressed", [])), 1)

        if score > 0.3:
            matched.append({
                "rank": len(matched) + 1,
                "strategy_id": strategy["id"],
                "name": strategy["name"],
                "evidence": strategy.get("evidence", ""),
                "thermal_impact": strategy["thermal_impact"]["mean_reduction_celsius"],
                "cost_estimate": {
                    "min": strategy["cost"]["min"],
                    "max": strategy["cost"]["max"],
                    "unit": strategy["cost"]["unit"],
                },
                "implementation_months": sum(strategy["implementation"]["duration_months"]) // 2,
                "confidence": 0.85,
                "co_benefits": strategy.get("co_benefits", {}),
            })

    return sorted(matched, key=lambda x: x["thermal_impact"], reverse=True)[:5]
