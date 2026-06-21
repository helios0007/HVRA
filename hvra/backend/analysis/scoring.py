"""
Stage 2 final step — Composite score, risk classification, JSON assembly.

Composite Room Risk Score:
    composite_score = (0.40 × solar_gain_score)
                    + (0.35 × vent_deficit_score)
                    + (0.15 × envelope_score)
                    + (0.10 × vuln_multiplier_normalised)

Weight rationale: Solar gain and ventilation are the primary drivers of indoor
overheating in Mediterranean climates.
SOURCE: UPC (2025) Barcelona heat vulnerability study.
NOTE: Weights are design constants — recalibrate after EnergyPlus validation.

Risk classification:
    0.00–0.40  → Safe
    0.40–0.65  → Moderate
    0.65–0.85  → High
    0.85–1.00  → Critical

Output schema matches HVRA_build_reference_4.md §3 Room JSON Schema.
"""

from __future__ import annotations
import json
import os
from typing import Any

from .ifc_parser import RoomData
from .solar import SolarResult
from .ventilation import VentilationResult
from .envelope import EnvelopeResult
from .health_kpis import HealthKPIResult, OccupantProfile


# ── Composite score weights ─────────────────────────────────────────────────────
# Defined as named constants for easy recalibration after EnergyPlus validation.
# SOURCE: HVRA_build_reference_4.md §2d — Composite Room Risk Score.
W_SOLAR    = 0.40
W_VENT     = 0.35
W_ENVELOPE = 0.15
W_VULN     = 0.10

# vuln_multiplier max = 2.0 — used for normalisation
VULN_MULTIPLIER_MAX = 2.0


def compute_composite_score(
    solar_score: float,
    vent_score: float,
    envelope_score: float,
    vuln_multiplier: float,
) -> float:
    """
    Compute composite room risk score (0–1).
    SOURCE: HVRA_build_reference_4.md §2d — weighted formula.
    """
    vuln_norm = min(vuln_multiplier / VULN_MULTIPLIER_MAX, 1.0)
    score = (
        W_SOLAR    * solar_score
        + W_VENT   * vent_score
        + W_ENVELOPE * envelope_score
        + W_VULN   * vuln_norm
    )
    return round(min(max(score, 0.0), 1.0), 3)


def classify_risk(composite_score: float) -> str:
    """
    Map composite score to risk level label.
    SOURCE: HVRA_build_reference_4.md §2d — risk classification thresholds.
    """
    if composite_score >= 0.85:
        return "critical"
    if composite_score >= 0.65:
        return "high"
    if composite_score >= 0.40:
        return "moderate"
    return "safe"


def build_room_json(
    room: RoomData,
    solar: SolarResult,
    vent: VentilationResult,
    envelope: EnvelopeResult,
    kpis: HealthKPIResult,
    occupant: OccupantProfile,
    heritage_protection: bool,
    shutter_boxes: bool,
    neighbourhood: str = "unknown",
    uhi_delta: float = 1.5,
) -> dict[str, Any]:
    """
    Assemble the full room JSON record matching the schema in
    HVRA_build_reference_4.md §3.  The ai_outputs section is left empty —
    it is populated by Stage 3 (LLM diagnosis).
    """
    composite = compute_composite_score(
        solar.solar_gain_score,
        vent.vent_deficit_score,
        envelope.envelope_score,
        occupant.vuln_multiplier,
    )
    risk = classify_risk(composite)

    facades_out = []
    for i, f in enumerate(room.facades):
        # Pull per-facade solar score if available
        facade_solar = solar.facades[i] if i < len(solar.facades) else None
        facades_out.append({
            "orientation": f.orientation_label,
            "orientation_degrees": f.orientation_degrees,
            "wall_area_m2": f.wall_area_m2,
            "window_area_m2": f.window_area_m2,
            "WWR": f.wwr,
            "has_external_shading": f.has_external_shading,
            "wall_U_value": f.wall_u_value,
            "wall_construction_era": _era_label(f.wall_u_value),
            "SHGC": f.shgc,
            "peak_solar_gain_w": facade_solar.peak_solar_gain_w if facade_solar else 0.0,
            "solar_gain_score": facade_solar.solar_gain_score if facade_solar else 0.0,
            "shadow_factor_avg": facade_solar.shadow_factor_avg if facade_solar else 1.0,
            "exposed_hours": facade_solar.exposed_hours if facade_solar else 0,
            "wall_id": f.wall_id,
            "window_ids": f.window_ids,
            "wall_thickness_mm": f.wall_thickness_mm,
            "wall_layers": [
                {"name": l.name, "thickness_mm": l.thickness_mm}
                for l in f.wall_layers
            ],
        })

    return {
        "room_id": room.room_id,
        "ifc_global_id": room.ifc_global_id,
        "door_ids": room.door_ids,
        "room_name": room.room_name,
        "room_type": room.room_type,
        "floor": room.floor,
        "area_m2": room.area_m2,

        "facades": facades_out,

        "ventilation": {
            "exterior_facades": vent.exterior_facades,
            "exterior_orientations": vent.exterior_orientations,
            "cross_ventilation_direct": vent.cross_ventilation_direct,
            "cross_ventilation_reason": vent.cross_ventilation_reason,
            "secondary_path_possible": vent.secondary_path_possible,
            "secondary_path_note": vent.secondary_path_note,
            "estimated_ACH": vent.estimated_ach,   # PROXY
        },

        "envelope": {
            "roof_exposed": envelope.roof_exposed,
            "roof_U_value": envelope.roof_u_value,
            "roof_U_flag": envelope.roof_u_flag,
            "dominant_wall_U_value": envelope.dominant_wall_u_value,
            "wall_U_flag": envelope.wall_u_flag,
            "thermal_mass_score": envelope.thermal_mass_score,
            "roof_absorption": envelope.roof_absorption,
            "roof_peak_solar_gain_W": envelope.roof_peak_solar_gain_w,
            "roof_solar_gain_score": envelope.roof_solar_gain_score,
        },

        "thermal_scores": {
            "solar_gain_score": solar.solar_gain_score,
            "peak_solar_W_per_m2": solar.peak_solar_w_per_m2,
            "vent_deficit_score": vent.vent_deficit_score,
            "envelope_score": envelope.envelope_score,
            "thermal_mass_score": envelope.thermal_mass_score,
            "T_op_estimated_peak_C": kpis.T_op_estimated_peak_c,
            "T_op_flag": kpis.T_op_flag,
            "WBGT_peak_estimated": kpis.wbgt_peak_estimated,
            "WBGT_strain_flag": kpis.wbgt_strain_flag,
            "WBGT_elderly_danger_flag": kpis.wbgt_elderly_danger_flag,
            "overheating_hours": kpis.overheating_hours,
            "age_weighted_overheating": kpis.health_risk_hours,
            "health_risk_hours": kpis.health_risk_hours,
            "overheating_events": kpis.overheating_events,
            "nocturnal_recovery_fail": kpis.nocturnal_recovery_fail,
            "estimated_3am_temp_C": kpis.estimated_3am_temp_c,
            "sleep_disruption_flag": kpis.sleep_disruption_flag,
            "risk_level": risk,
        },

        "occupant": {
            "age_bracket": occupant.age_bracket,
            "AC_access": occupant.ac_access,
            "income_category": occupant.income_category,
            "mobility": "limited" if occupant.mobility_limited else "unrestricted",
            "vuln_multiplier": occupant.vuln_multiplier,
        },

        "building": {
            "heritage_protection": heritage_protection,
            "shutter_box_present": shutter_boxes,
            # UHI correction applied — uhi.get_uhi_correction()
            # SOURCE: UPC (2025) + Copernicus Urban Heat Island dataset
            "neighbourhood": neighbourhood,
            "uhi_delta_applied_c": uhi_delta,
        },

        "composite_score": composite,

        "ai_outputs": {
            "diagnosis": "",
            "key_factors": [],
            "eligible_strategies": [],
            "shortlist": [],
        },
    }


def write_room_problems_json(rooms: list[dict], output_dir: str) -> str:
    """Write room_problems.json to output_dir. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "room_problems.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rooms, f, indent=2, ensure_ascii=False)
    return path


def write_priority_json(rooms: list[dict], output_dir: str) -> str:
    """
    Stage 2b: Python sort of rooms by composite_score descending.
    Produces priority.json for portfolio view.
    SOURCE: HVRA_build_reference_4.md §Pipeline — priority.json produced by Stage 2b.
    """
    priority = sorted(
        [
            {
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "room_type": r["room_type"],
                "floor": r["floor"],
                "orientation": r["facades"][0]["orientation"] if r["facades"] else "",
                "risk_level": r["thermal_scores"]["risk_level"],
                "top_vulnerability_flag": _top_flag(r),
                "composite_score": r["composite_score"],
            }
            for r in rooms
        ],
        key=lambda x: x["composite_score"],
        reverse=True,
    )
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "priority.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(priority, f, indent=2, ensure_ascii=False)
    return path


def _top_flag(room: dict) -> str:
    """Return the single most prominent vulnerability flag for the portfolio list view."""
    ts = room["thermal_scores"]
    if ts.get("WBGT_elderly_danger_flag"):
        return "WBGT elderly danger"
    if ts.get("nocturnal_recovery_fail"):
        return "nocturnal recovery fail"
    if ts.get("T_op_flag"):
        return "T_op > 32°C"
    if ts.get("WBGT_strain_flag"):
        return "WBGT strain"
    if ts.get("solar_gain_score", 0) >= 0.8:
        return "high solar gain"
    if ts.get("vent_deficit_score", 0) >= 0.8:
        return "severe ventilation deficit"
    return "—"


def _era_label(u_value: float) -> str:
    """Infer construction era label from U-value (reverse lookup, approximate)."""
    if u_value >= 2.0:
        return "pre-1960"
    if u_value >= 1.5:
        return "1960-1979"
    if u_value >= 0.8:
        return "1980-2006"
    return "post-2006"
