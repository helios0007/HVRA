"""
Thermal-to-Design Rules Engine

Maps infrared thermal vulnerabilities to architectural design parameters and generates
parametric design specs and visualization geometry (GeoJSON).
"""

from typing import Dict, List, Any, Tuple, Optional
from pydantic import BaseModel
import math
import json

# ============================================================================
# Design Parameter Mapping: Thermal Vulnerabilities → Design Specs
# ============================================================================

THERMAL_VULNERABILITY_INTERVENTIONS = {
    "high_mrt": {
        "threshold": {"mrt_celsius": 50},
        "description": "Mean Radiant Temperature exceeds 50°C; user exposed to intense solar radiation",
        "interventions": [
            {
                "type": "urban_forest",
                "name": "Urban Forest (Street Trees)",
                "priority": "high",
                "parameters": {
                    "tree_canopy_coverage_pct": 40,
                    "spacing_meters": 8,
                    "tree_height_meters": 12,
                    "species": "deciduous_mixed",
                    "svf_reduction": 0.4,
                },
                "expected_impact_celsius": {"mrt": -12, "air_temp": -1.5, "utci": -2.0},
                "implementation_months": 6,
                "cost_per_100m2": 500,
                "visualization_type": "point_grid",
            },
            {
                "type": "shade_structure",
                "name": "Tensile Shade Structures",
                "priority": "high",
                "parameters": {
                    "coverage_area_m2": 500,
                    "orientation": "perpendicular_to_afternoon_sun",
                    "shade_factor": 0.8,
                    "height_clearance_m": 3.5,
                },
                "expected_impact_celsius": {"mrt": -10, "utci": -1.5},
                "implementation_months": 4,
                "cost_per_100m2": 800,
                "visualization_type": "polygon_pattern",
            },
            {
                "type": "cool_pavements",
                "name": "Cool Pavements (Light Concrete/Permeable)",
                "priority": "medium",
                "parameters": {
                    "target_albedo": 0.5,
                    "area_m2": 1000,
                    "material": "light_concrete_or_permeable_paving",
                    "thermal_mass_high": True,
                },
                "expected_impact_celsius": {"mrt": -5, "surface_temp": -12, "utci": -1.0},
                "implementation_months": 3,
                "cost_per_m2": 75,
                "visualization_type": "polygon_fill",
            },
            {
                "type": "water_feature",
                "name": "Water Feature (Fountain/Pond)",
                "priority": "medium",
                "parameters": {
                    "area_m2": 200,
                    "evaporative_cooling_factor": 0.7,
                    "circulation_system": "active_pump",
                },
                "expected_impact_celsius": {"mrt": -4, "utci": -0.8},
                "implementation_months": 8,
                "cost_per_m2": 600,
                "visualization_type": "polygon_water",
            },
        ]
    },

    "poor_ventilation": {
        "threshold": {"wind_speed_ms": 0.5, "hw_ratio": 2.5},
        "description": "Stagnant air in street canyon; low wind speed and high H/W ratio trap hot air",
        "interventions": [
            {
                "type": "ventilation_corridor",
                "name": "Ventilation Corridor (Gap in Building Line)",
                "priority": "high",
                "parameters": {
                    "corridor_width_meters": 50,
                    "corridor_length_meters": 200,
                    "orientation": "perpendicular_to_prevailing_wind",
                    "vegetation_integration": True,
                },
                "expected_impact_celsius": {"air_temp": -2.5, "utci": -2.0},
                "expected_wind_increase_ms": 0.8,
                "implementation_months": 12,
                "cost_per_m2": 150,  # Primarily landscaping
                "visualization_type": "corridor_line",
            },
            {
                "type": "building_setback",
                "name": "Building Setback (Urban Morphology Change)",
                "priority": "high",
                "parameters": {
                    "setback_meters": 10,
                    "setback_side": "windward",
                    "height_reduction_m": 5,
                    "creates_wind_tunnel": True,
                },
                "expected_impact_celsius": {"air_temp": -2.0, "utci": -1.5},
                "expected_wind_increase_ms": 0.6,
                "implementation_months": 24,
                "cost_per_m2": 800,  # Demolition + reconstruction
                "visualization_type": "building_geometry_change",
            },
            {
                "type": "green_strip_linear",
                "name": "Linear Green Strip (Bioswale/Rain Garden)",
                "priority": "medium",
                "parameters": {
                    "width_meters": 5,
                    "length_meters": 200,
                    "vegetation_type": "herbaceous_with_trees",
                    "permeable_soil": True,
                },
                "expected_impact_celsius": {"air_temp": -1.0, "utci": -0.8},
                "expected_wind_increase_ms": 0.2,
                "implementation_months": 6,
                "cost_per_m2": 100,
                "visualization_type": "polygon_strip",
            },
        ]
    },

    "high_albedo_deficit": {
        "threshold": {"roof_albedo": 0.2, "wall_albedo": 0.25},
        "description": "Dark building envelope; low surface reflectivity increases thermal mass heating",
        "interventions": [
            {
                "type": "cool_roofing",
                "name": "Cool Roof Coating (High-Albedo Retrofit)",
                "priority": "high",
                "parameters": {
                    "target_albedo": 0.65,
                    "material": "reflective_coating_or_light_membrane",
                    "cost_per_application": 15,  # €/m²
                    "maintenance_years": 10,
                },
                "expected_impact_celsius": {"roof_surface_temp": -18, "utci": -1.2},
                "interior_cooling_benefit_pct": 8,
                "implementation_months": 2,
                "cost_per_m2": 15,
                "visualization_type": "roof_polygon",
            },
            {
                "type": "green_roof",
                "name": "Green Roof (Extensive Vegetation)",
                "priority": "medium",
                "parameters": {
                    "coverage_pct": 50,
                    "substrate_depth_cm": 15,
                    "vegetation_type": "extensive_sedum",
                    "water_retention_mm": 60,
                },
                "expected_impact_celsius": {"surface_temp": -8, "interior_temp": -2, "utci": -0.5},
                "interior_cooling_benefit_pct": 5,
                "stormwater_retention_pct": 60,
                "implementation_months": 4,
                "cost_per_m2": 120,
                "visualization_type": "roof_polygon_green",
            },
            {
                "type": "cool_wall",
                "name": "Cool Wall Coating",
                "priority": "medium",
                "parameters": {
                    "target_albedo": 0.5,
                    "facade_area_m2": 1000,
                    "color": "light_neutral_tones",
                    "material": "reflective_paint_or_finish",
                },
                "expected_impact_celsius": {"wall_surface_temp": -8, "interior_temp": -1, "utci": -0.3},
                "implementation_months": 1,
                "cost_per_m2": 20,
                "visualization_type": "facade_polygon",
            },
            {
                "type": "vertical_greening",
                "name": "Vertical Greening (Green Wall / Ivy)",
                "priority": "low",
                "parameters": {
                    "coverage_pct": 60,
                    "facade_area_m2": 500,
                    "vegetation_type": "climbing_ivy_or_panel_system",
                    "air_gap_cm": 10,
                },
                "expected_impact_celsius": {"wall_surface_temp": -6, "interior_temp": -1.5, "utci": -0.2},
                "interior_cooling_benefit_pct": 3,
                "implementation_months": 3,
                "cost_per_m2": 150,
                "visualization_type": "facade_polygon_green",
            },
        ]
    },

    "low_vegetation": {
        "threshold": {"vegetation_coverage_pct": 15},
        "description": "Insufficient vegetation; low canopy coverage increases exposure to solar radiation",
        "interventions": [
            {
                "type": "urban_forest_dense",
                "name": "Dense Urban Forest (Parks/Squares)",
                "priority": "high",
                "parameters": {
                    "tree_canopy_coverage_pct": 50,
                    "spacing_meters": 6,
                    "tree_height_meters": 15,
                    "area_m2": 5000,
                },
                "expected_impact_celsius": {"mrt": -14, "air_temp": -2.5, "utci": -3.0},
                "implementation_months": 10,
                "cost_per_100m2": 600,
                "visualization_type": "point_grid_dense",
            },
            {
                "type": "green_corridor",
                "name": "Green Corridor (Linear Park)",
                "priority": "medium",
                "parameters": {
                    "width_meters": 30,
                    "tree_canopy_coverage_pct": 40,
                    "understory_vegetation": True,
                },
                "expected_impact_celsius": {"mrt": -10, "air_temp": -1.5, "utci": -2.0},
                "implementation_months": 8,
                "cost_per_100m2": 450,
                "visualization_type": "polygon_strip_green",
            },
        ]
    }
}

# ============================================================================
# Design Spec Classes
# ============================================================================

class InterventionDesignSpec(BaseModel):
    """A single design intervention with parameters and expected impact."""
    intervention_id: str
    type: str
    name: str
    priority: str
    parameters: Dict[str, Any]
    expected_impact_celsius: Dict[str, float]
    implementation_months: int
    cost_estimate_usd: float
    visualization_geojson: Dict[str, Any]
    feasibility_score: float  # 0-1, based on available area
    implementation_priority: int  # 1 = highest priority
    rationale: str


class DesignSpecificationResponse(BaseModel):
    """Response with all design specs for a vulnerable zone."""
    zone_id: str
    vulnerability_drivers: List[str]
    design_specs: List[InterventionDesignSpec]
    combined_thermal_impact: float  # Sum of all expected impacts
    recommended_combination: List[str]  # intervention_ids in recommended order


# ============================================================================
# Core Mapping Functions
# ============================================================================

def map_thermal_to_design(
    vulnerability_analysis: Dict[str, Any],
    zone_geojson: Optional[Dict[str, Any]] = None
) -> DesignSpecificationResponse:
    """
    Main function: Map thermal vulnerabilities to design specifications.

    Args:
        vulnerability_analysis: Dict with keys:
            - vulnerability_score: float (0-10)
            - peak_utci_celsius: float
            - drivers: List[Dict] with 'driver' and 'severity'
            - climate_context: Dict with climate data
            - zone_geojson: Optional GeoJSON of vulnerable zone

        zone_geojson: Optional GeoJSON of the zone (for geometry generation)

    Returns:
        DesignSpecificationResponse with ranked design interventions
    """
    # Extract vulnerability drivers
    drivers = vulnerability_analysis.get("drivers", [])
    driver_names = []
    driver_severity = {}

    for d in drivers:
        if isinstance(d, dict):
            name = d.get("driver", "unknown")
            severity = d.get("severity", 0.5)
            if name != "unknown":
                driver_names.append(name)
                driver_severity[name] = severity

    # Get zone geometry if available
    if not zone_geojson and "zone_geojson" in vulnerability_analysis:
        zone_geojson = vulnerability_analysis["zone_geojson"]

    # Map each driver to interventions
    design_specs = []
    intervention_id_counter = 0

    for driver_name in driver_names:
        if driver_name in THERMAL_VULNERABILITY_INTERVENTIONS:
            mapping = THERMAL_VULNERABILITY_INTERVENTIONS[driver_name]
            severity = driver_severity.get(driver_name, 0.5)

            for intervention_template in mapping["interventions"]:
                spec = _create_intervention_spec(
                    driver_name=driver_name,
                    intervention_template=intervention_template,
                    severity=severity,
                    zone_geojson=zone_geojson,
                    spec_id=intervention_id_counter,
                    vulnerability_analysis=vulnerability_analysis
                )
                design_specs.append(spec)
                intervention_id_counter += 1

    # Rank by priority and thermal impact
    design_specs = _rank_design_specs(design_specs, driver_severity)

    # Recommend a combination (pareto-optimal)
    recommended = _recommend_combination(design_specs, max_cost_usd=500000)

    return DesignSpecificationResponse(
        zone_id=vulnerability_analysis.get("zone_id", "unknown"),
        vulnerability_drivers=driver_names,
        design_specs=design_specs,
        combined_thermal_impact=sum(
            spec.expected_impact_celsius.get("mrt", 0) or
            spec.expected_impact_celsius.get("air_temp", 0) or
            spec.expected_impact_celsius.get("utci", 0)
            for spec in design_specs
        ),
        recommended_combination=recommended
    )


def _create_intervention_spec(
    driver_name: str,
    intervention_template: Dict[str, Any],
    severity: float,
    zone_geojson: Optional[Dict[str, Any]],
    spec_id: int,
    vulnerability_analysis: Dict[str, Any]
) -> InterventionDesignSpec:
    """Create a complete intervention design spec from template."""

    int_type = intervention_template["type"]
    parameters = intervention_template["parameters"].copy()

    # Adjust parameters based on severity
    parameters = _adjust_parameters_by_severity(parameters, severity, int_type)

    # Generate visualization geometry
    visualization = _generate_intervention_geometry(
        int_type=int_type,
        parameters=parameters,
        zone_geojson=zone_geojson,
        vulnerability_analysis=vulnerability_analysis
    )

    # Calculate feasibility score
    feasibility = _calculate_feasibility(int_type, parameters, zone_geojson)

    # Calculate cost
    cost_usd = _estimate_cost(int_type, parameters)

    # Build rationale
    rationale = _build_rationale(driver_name, int_type, severity, parameters)

    return InterventionDesignSpec(
        intervention_id=f"{driver_name}_{int_type}_{spec_id}",
        type=int_type,
        name=intervention_template["name"],
        priority=intervention_template["priority"],
        parameters=parameters,
        expected_impact_celsius=intervention_template["expected_impact_celsius"],
        implementation_months=intervention_template["implementation_months"],
        cost_estimate_usd=cost_usd,
        visualization_geojson=visualization,
        feasibility_score=feasibility,
        implementation_priority=_calculate_priority(
            driver_name,
            int_type,
            severity
        ),
        rationale=rationale
    )


def _adjust_parameters_by_severity(
    parameters: Dict[str, Any],
    severity: float,
    int_type: str
) -> Dict[str, Any]:
    """Scale parameters based on vulnerability severity (0-1)."""
    adjusted = parameters.copy()

    severity_factor = 0.7 + (severity * 0.3)  # Range: 0.7 to 1.0

    # Adjust key numeric parameters
    if "tree_canopy_coverage_pct" in adjusted:
        adjusted["tree_canopy_coverage_pct"] = int(
            adjusted["tree_canopy_coverage_pct"] * severity_factor
        )
    if "coverage_area_m2" in adjusted:
        adjusted["coverage_area_m2"] = int(
            adjusted["coverage_area_m2"] * severity_factor
        )
    if "target_albedo" in adjusted:
        # For albedo, higher severity → need more increase
        base_albedo = 0.15  # Typical dark surface
        target = adjusted["target_albedo"]
        adjusted["target_albedo"] = base_albedo + (target - base_albedo) * severity_factor

    return adjusted


def _generate_intervention_geometry(
    int_type: str,
    parameters: Dict[str, Any],
    zone_geojson: Optional[Dict[str, Any]],
    vulnerability_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate GeoJSON visualization geometry for intervention."""

    viz_type = None
    for mapping in THERMAL_VULNERABILITY_INTERVENTIONS.values():
        for intervention in mapping["interventions"]:
            if intervention["type"] == int_type:
                viz_type = intervention.get("visualization_type", "polygon")
                break
        if viz_type:
            break

    # If no zone GeoJSON, return a template
    if not zone_geojson:
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "intervention_type": int_type,
                        "note": "Geometry generation requires zone_geojson"
                    },
                    "geometry": None  # Placeholder
                }
            ]
        }

    # Generate based on intervention type
    if int_type in ["urban_forest", "urban_forest_dense"]:
        return _generate_tree_layer(zone_geojson, parameters)
    elif int_type in ["cool_pavements", "permeable_pavements"]:
        return _generate_pavement_layer(zone_geojson, parameters)
    elif int_type in ["ventilation_corridor", "green_strip_linear", "green_corridor"]:
        return _generate_corridor_layer(zone_geojson, parameters)
    elif int_type in ["water_feature"]:
        return _generate_water_layer(zone_geojson, parameters)
    elif int_type in ["cool_roofing", "green_roof"]:
        return _generate_roof_layer(zone_geojson, parameters)
    else:
        return _generate_generic_polygon_layer(zone_geojson, parameters)


def _generate_tree_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate tree point layer with 8m grid spacing."""
    spacing = parameters.get("spacing_meters", 8)
    coverage = parameters.get("tree_canopy_coverage_pct", 40)

    # Get zone bounds (simplified)
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        for feature in zone_geojson.get("features", []):
            if feature.get("geometry", {}).get("type") == "Polygon":
                coords = feature["geometry"]["coordinates"][0]
                # Generate grid
                for i, (lng, lat) in enumerate(coords[:-1]):
                    # Simplified: create tree points at regular intervals
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "feature_type": "tree",
                            "coverage_contribution_pct": coverage / max(1, len(coords) - 1),
                            "canopy_height_m": parameters.get("tree_height_meters", 12),
                            "expected_shade_factor": 0.7
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lng, lat]
                        }
                    })

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "tree_template"},
            "geometry": {"type": "Point", "coordinates": [0, 0]}
        }]
    }


def _generate_pavement_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate pavement polygon layer."""
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        for feature in zone_geojson.get("features", []):
            if feature.get("geometry", {}).get("type") == "Polygon":
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "pavement",
                        "albedo": parameters.get("target_albedo", 0.5),
                        "material": parameters.get("material", "cool_concrete"),
                        "area_m2": parameters.get("area_m2", 1000)
                    },
                    "geometry": feature["geometry"]
                })

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "pavement_template"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
        }]
    }


def _generate_corridor_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate ventilation corridor or green strip line."""
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        for feature in zone_geojson.get("features", []):
            if feature.get("geometry", {}).get("type") == "Polygon":
                coords = feature["geometry"]["coordinates"][0]
                if len(coords) > 1:
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "feature_type": "corridor",
                            "width_meters": parameters.get("corridor_width_meters", 50),
                            "orientation": parameters.get("orientation", "perpendicular"),
                            "vegetation_integrated": parameters.get("vegetation_integration", False)
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords[::max(1, len(coords)//3)]  # Sample 3 points
                        }
                    })

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "corridor_template"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        }]
    }


def _generate_water_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate water feature polygon layer."""
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        for feature in zone_geojson.get("features", [])[:1]:  # Just first zone
            if feature.get("geometry", {}).get("type") == "Polygon":
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "water",
                        "area_m2": parameters.get("area_m2", 200),
                        "evaporative_cooling": parameters.get("evaporative_cooling_factor", 0.7)
                    },
                    "geometry": feature["geometry"]
                })

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "water_template"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 0.1], [0.1, 0.1], [0.1, 0], [0, 0]]]}
        }]
    }


def _generate_roof_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate roof treatment polygon layer."""
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        for feature in zone_geojson.get("features", []):
            if feature.get("geometry", {}).get("type") == "Polygon":
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "roof",
                        "coverage_pct": parameters.get("coverage_pct", 50),
                        "material": parameters.get("material", "reflective"),
                        "target_albedo": parameters.get("target_albedo", 0.65)
                    },
                    "geometry": feature["geometry"]
                })

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "roof_template"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
        }]
    }


def _generate_generic_polygon_layer(
    zone_geojson: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate generic polygon layer from zone."""
    features = []
    if zone_geojson.get("type") == "FeatureCollection":
        features = zone_geojson.get("features", [])

    return {
        "type": "FeatureCollection",
        "features": features if features else [{
            "type": "Feature",
            "properties": {"type": "generic_template"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
        }]
    }


def _calculate_feasibility(
    int_type: str,
    parameters: Dict[str, Any],
    zone_geojson: Optional[Dict[str, Any]]
) -> float:
    """Calculate feasibility score (0-1) based on intervention type and available area."""
    # Base feasibility by type
    base_feasibility = {
        "urban_forest": 0.8,
        "urban_forest_dense": 0.7,
        "cool_pavements": 0.9,
        "shade_structure": 0.75,
        "water_feature": 0.6,
        "ventilation_corridor": 0.5,
        "building_setback": 0.3,
        "cool_roofing": 0.95,
        "green_roof": 0.7,
        "cool_wall": 0.85,
        "vertical_greening": 0.75,
        "green_strip_linear": 0.6,
        "green_corridor": 0.65,
    }

    feasibility = base_feasibility.get(int_type, 0.5)

    # Adjust based on zone size if available
    if zone_geojson:
        # Simplified: just check if zone exists
        feasibility *= 0.95

    return min(1.0, max(0.0, feasibility))


def _estimate_cost(int_type: str, parameters: Dict[str, Any]) -> float:
    """Estimate USD cost based on intervention type and parameters."""
    cost_map = {
        "urban_forest": 500 * parameters.get("tree_canopy_coverage_pct", 40) / 40,  # €/100m² × area factor
        "urban_forest_dense": 600 * parameters.get("tree_canopy_coverage_pct", 50) / 50,
        "cool_pavements": 75 * parameters.get("area_m2", 1000),
        "shade_structure": 800 * (parameters.get("coverage_area_m2", 500) / 100),
        "water_feature": 600 * parameters.get("area_m2", 200),
        "ventilation_corridor": 150 * (parameters.get("corridor_width_meters", 50) * parameters.get("corridor_length_meters", 200)) / 100,
        "building_setback": 800 * 500,  # Large, assumes major construction
        "cool_roofing": 15 * 1000,  # €/m² × typical roof area
        "green_roof": 120 * (parameters.get("coverage_pct", 50) * 1000 / 100),
        "cool_wall": 20 * parameters.get("facade_area_m2", 1000),
        "vertical_greening": 150 * parameters.get("facade_area_m2", 500),
        "green_strip_linear": 100 * (parameters.get("width_meters", 5) * parameters.get("length_meters", 200)),
        "green_corridor": 450 * (parameters.get("width_meters", 30) * 200 / 100),
    }

    cost_eur = cost_map.get(int_type, 50000)
    return cost_eur * 1.1  # Convert EUR to USD (rough estimate)


def _build_rationale(
    driver_name: str,
    int_type: str,
    severity: float,
    parameters: Dict[str, Any]
) -> str:
    """Build a text rationale for the intervention."""
    severity_pct = int(severity * 100)

    rationales = {
        ("high_mrt", "urban_forest"): f"High MRT ({severity_pct}% severity). Tree canopy at {parameters.get('tree_canopy_coverage_pct', 40)}% coverage with {parameters.get('spacing_meters', 8)}m spacing blocks solar radiation and reduces radiant temperature.",
        ("high_mrt", "cool_pavements"): f"High MRT ({severity_pct}% severity). Light pavement (albedo {parameters.get('target_albedo', 0.5)}) reflects solar heat instead of absorbing.",
        ("poor_ventilation", "ventilation_corridor"): f"Poor ventilation ({severity_pct}% severity). {parameters.get('corridor_width_meters', 50)}m gap perpendicular to prevailing wind creates cross-canyon airflow.",
        ("poor_ventilation", "building_setback"): f"Poor ventilation ({severity_pct}% severity). {parameters.get('setback_meters', 10)}m setback and {parameters.get('height_reduction_m', 5)}m height reduction open street canyon to wind.",
        ("high_albedo_deficit", "cool_roofing"): f"Dark roof ({severity_pct}% severity). Increase albedo to {parameters.get('target_albedo', 0.65)} via reflective coating to reduce roof surface temperature.",
        ("high_albedo_deficit", "green_roof"): f"Dark roof ({severity_pct}% severity). {parameters.get('coverage_pct', 50)}% green roof provides insulation and evaporative cooling.",
        ("low_vegetation", "urban_forest_dense"): f"Sparse vegetation ({severity_pct}% severity). Dense forest at {parameters.get('tree_canopy_coverage_pct', 50)}% coverage restores shade and ecosystem cooling.",
    }

    return rationales.get(
        (driver_name, int_type),
        f"Address {driver_name} ({severity_pct}% severity) with {int_type} intervention."
    )


def _rank_design_specs(
    design_specs: List[InterventionDesignSpec],
    driver_severity: Dict[str, float]
) -> List[InterventionDesignSpec]:
    """Rank design specs by priority, thermal impact, and feasibility."""

    def score(spec: InterventionDesignSpec) -> float:
        # Weighted scoring
        impact = sum(spec.expected_impact_celsius.values()) / max(1, len(spec.expected_impact_celsius))
        feasibility = spec.feasibility_score
        priority_weight = {
            "high": 10,
            "medium": 5,
            "low": 1
        }
        priority = priority_weight.get(spec.priority, 3)

        return (impact * 0.5) + (feasibility * 0.3) + (priority * 0.2)

    return sorted(design_specs, key=score, reverse=True)


def _calculate_priority(
    driver_name: str,
    int_type: str,
    severity: float
) -> int:
    """Calculate implementation priority (1=highest)."""
    # Find priority in original mapping
    for mapping in THERMAL_VULNERABILITY_INTERVENTIONS.values():
        for intervention in mapping["interventions"]:
            if intervention["type"] == int_type:
                priority_map = {"high": 1, "medium": 2, "low": 3}
                base_priority = priority_map.get(intervention["priority"], 2)
                # Adjust by severity: higher severity = lower number (higher priority)
                return max(1, int(base_priority * (2 - severity)))

    return 3


def _recommend_combination(
    design_specs: List[InterventionDesignSpec],
    max_cost_usd: float = 500000
) -> List[str]:
    """Select a Pareto-optimal combination of interventions within budget."""
    # Simple greedy: pick highest impact interventions within budget
    recommended = []
    total_cost = 0.0

    for spec in design_specs:
        if total_cost + spec.cost_estimate_usd <= max_cost_usd:
            recommended.append(spec.intervention_id)
            total_cost += spec.cost_estimate_usd
            if len(recommended) >= 3:  # Max 3 recommendations
                break

    return recommended
