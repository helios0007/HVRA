"""
Stage 4a — Rule-based pre-filter.

Reads room_problems.json entries and strategy_library.json.
For each room, checks each strategy's applicability conditions against
the computed room fields and produces eligible_strategies.json.

Pre-filter condition table:
    SOURCE: HVRA_build_reference_4.md §Stage 4a — Rule-based pre-filter.

Only eligible strategies are passed to the Stage 4b LLM shortlist.

Orientation note:
    South-facing (high solar exposure risk): S, SE, SW
    South + West facing (solar_control_glazing adds W): S, SE, SW, W
    SOURCE: HVRA_build_reference_4.md §Strategy Library — applicable façades per strategy.
"""

from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Orientation sets ────────────────────────────────────────────────────────────
# SOURCE: HVRA_build_reference_4.md §Strategy Library — per-strategy applicable façades.
_SOUTH_FACING = {"S", "SE", "SW"}          # louvers, shutters, blinds, pergola
_SOUTH_WEST_FACING = {"S", "SE", "SW", "W"}  # solar_control_glazing

# Portfolio/urban strategies are excluded from room-level pre-filter.
_PORTFOLIO_STRATEGIES = {"courtyard_greening", "shared_cooling_refuge", "street_tree_canopy"}

STRATEGY_LIBRARY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "strategy_library.json"
)


def load_strategy_library(path: str = STRATEGY_LIBRARY_PATH) -> list[dict]:
    """Load and return the strategy library as a list of strategy dicts."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_prefilter(
    room: dict[str, Any],
    strategy_library: list[dict],
    heritage_protection: bool,
    shutter_boxes: bool,
    epw_night_min: float,
    construction_year: str,
) -> list[str]:
    """
    Check each strategy's applicability conditions against a room's computed fields.

    Returns a list of strategy IDs that passed the pre-filter for this room.
    Portfolio-level strategies (courtyard_greening, shared_cooling_refuge,
    street_tree_canopy) are never included — they are building/municipality interventions.

    Parameters
    ----------
    room : dict
        Full room record from room_problems.json.
    strategy_library : list[dict]
        Loaded strategy_library.json entries.
    heritage_protection : bool
        Building-level heritage protection flag (from intake form).
    shutter_boxes : bool
        Existing shutter boxes present (from intake form).
    epw_night_min : float
        Minimum outdoor dry-bulb temperature during 3–5am hours in the heatwave week.
        SOURCE: epw_loader.overnight_min_temp().
    construction_year : str
        One of 'pre-1960' | '1960-1979' | '1980-2006' | 'post-2006'.
    """
    ts = room.get("thermal_scores", {})
    vent = room.get("ventilation", {})
    env = room.get("envelope", {})
    facades = room.get("facades", [])

    # Room-level scores
    solar_score_room = ts.get("solar_gain_score", 0.0)
    nocturnal_fail = ts.get("nocturnal_recovery_fail", False)

    # Ventilation fields
    cross_vent = vent.get("cross_ventilation_direct", False)
    secondary_path = vent.get("secondary_path_possible", False)
    exterior_facade_count = vent.get("exterior_facades", 0)

    # Envelope fields
    roof_exposed = env.get("roof_exposed", False)
    roof_u = env.get("roof_U_value", 0.0)
    wall_u = env.get("dominant_wall_U_value", 0.0)

    # Pre-computed facade helpers
    south_facades_high_solar = _facades_matching(facades, _SOUTH_FACING, 0.6)
    south_w_facades_mid_solar = _facades_matching(facades, _SOUTH_WEST_FACING, 0.5)
    south_w_facades_high_solar = _facades_matching(facades, _SOUTH_WEST_FACING, 0.6)
    south_facades_any_solar = _facades_matching(facades, _SOUTH_FACING, 0.4)
    has_south_high = len(south_facades_high_solar) > 0
    has_south_w_mid = len(south_w_facades_mid_solar) > 0
    has_south_w_high = len(south_w_facades_high_solar) > 0
    has_south_any = len(south_facades_any_solar) > 0

    eligible: list[str] = []

    for strategy in strategy_library:
        sid = strategy["id"]

        if sid in _PORTFOLIO_STRATEGIES:
            continue  # portfolio-level only — never room-eligible

        eligible_flag = False

        # ── SHADING ───────────────────────────────────────────────────────────

        if sid == "external_shading_louvers":
            # SOURCE: HVRA §4a — solar_gain_score > 0.6 AND SW/SE/S AND no heritage
            eligible_flag = has_south_high and not heritage_protection

        elif sid == "internal_blinds":
            # SOURCE: HVRA §4a — solar_gain_score > 0.6 AND SW/SE/S; always low-cost fallback
            eligible_flag = has_south_high

        elif sid == "solar_control_glazing":
            # SOURCE: HVRA §4a — solar_gain_score > 0.5 AND SW/SE/S/W AND glazing era pre-2006
            # "pre-2000" mapped to construction_year != "post-2006" (closest available category)
            eligible_flag = has_south_w_mid and construction_year != "post-2006"

        elif sid == "green_pergola":
            # SOURCE: HVRA §Strategy Library — ground floor or accessible terrace/balcony
            floor = room.get("floor", 999)
            eligible_flag = has_south_any and floor == 0

        elif sid == "window_external_shutters":
            # SOURCE: HVRA §4a — solar_gain_score > 0.6 AND SW/SE/S AND shutter_box_present
            eligible_flag = has_south_high and shutter_boxes

        elif sid == "operable_external_sunscreen":
            # SOURCE: hvra_strategy_library_categorized.md A2 — solar_gain_score > 0.6
            # AND SW/SE/S/W AND no heritage (external alteration like louvers)
            eligible_flag = has_south_w_high and not heritage_protection

        # ── VENTILATION ───────────────────────────────────────────────────────

        elif sid == "window_enlargement":
            # SOURCE: HVRA §4a — cross_ventilation_direct = false AND exterior_facades >= 1
            eligible_flag = not cross_vent and exterior_facade_count >= 1

        elif sid == "interior_opening_improvement":
            # SOURCE: HVRA §4a — secondary_path_possible = true
            eligible_flag = secondary_path

        elif sid == "stack_effect_roof_vent":
            # SOURCE: HVRA §Strategy Library — roof_exposed = true (top floor)
            eligible_flag = roof_exposed

        elif sid == "night_purge_ventilation":
            # SOURCE: HVRA §4a — nocturnal_recovery_fail = true AND EPW night min < 22°C
            # SOURCE: Blondeau et al. (1997) — night purge only beneficial when outdoor < 22°C
            eligible_flag = nocturnal_fail and epw_night_min < 22.0

        elif sid == "cross_ventilation_behaviour":
            # SOURCE: HVRA §4a — cross_ventilation_direct = true ONLY
            # Opposite condition to interior_opening_improvement and window_enlargement.
            eligible_flag = cross_vent

        # ── ENVELOPE ─────────────────────────────────────────────────────────

        elif sid == "external_wall_insulation_etics":
            # SOURCE: HVRA §4a — wall_U_value > 1.2 AND heritage_protection = false
            eligible_flag = wall_u > 1.2 and not heritage_protection

        elif sid == "roof_insulation":
            # SOURCE: HVRA §4a — roof_exposed = true AND roof_U_value > 1.5
            eligible_flag = roof_exposed and roof_u > 1.5

        elif sid == "cool_roof_coating":
            # SOURCE: HVRA §Strategy Library — roof_exposed = true (flat roof)
            eligible_flag = roof_exposed

        elif sid == "phase_change_materials":
            # SOURCE: HVRA §4a — nocturnal_recovery_fail = true
            eligible_flag = nocturnal_fail

        elif sid == "internal_wall_insulation":
            # SOURCE: HVRA §4a — wall_U_value > 1.2 regardless of heritage
            # Particularly relevant when heritage_protection = true (ETICS ineligible)
            eligible_flag = wall_u > 1.2

        elif sid == "cool_facade_paint":
            # SOURCE: HVRA §4a — solar_gain_score > 0.5 AND exterior wall exposed
            eligible_flag = solar_score_room > 0.5 and exterior_facade_count >= 1

        if eligible_flag:
            eligible.append(sid)

    logger.debug(
        "Pre-filter: room %s → %d eligible strategies: %s",
        room.get("room_id"), len(eligible), eligible,
    )
    return eligible


def write_eligible_strategies_json(
    room_jsons: list[dict],
    strategy_library: list[dict],
    output_dir: str,
) -> str:
    """
    Write eligible_strategies.json — per-room list of eligible strategy entries.

    Each room entry contains:
      - room_id, room_name
      - eligible_strategy_ids: list of str
      - strategies: list of full strategy library entries for eligible strategies

    This is the input file for Stage 4b (LLM shortlist).
    """
    library_index = {s["id"]: s for s in strategy_library}

    output = []
    for room in room_jsons:
        ids = room.get("ai_outputs", {}).get("eligible_strategies", [])
        output.append({
            "room_id": room["room_id"],
            "room_name": room["room_name"],
            "eligible_strategy_ids": ids,
            "strategies": [library_index[sid] for sid in ids if sid in library_index],
        })

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "eligible_strategies.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    return path


# ── Internal helpers ────────────────────────────────────────────────────────────

def _facades_matching(
    facades: list[dict],
    orientations: set[str],
    min_solar_score: float,
) -> list[dict]:
    """
    Return facades whose orientation is in the given set AND whose
    per-facade solar_gain_score exceeds min_solar_score.
    """
    return [
        f for f in facades
        if f.get("orientation") in orientations
        and f.get("solar_gain_score", 0.0) > min_solar_score
    ]
