"""
Stage 2b — Ventilation Analysis.

Cross-ventilation logic (rule-based, no CFD):
  1. Count exterior facades per room.
  2. If only one → cross_ventilation_direct = false.
  3. If ≥ two → check orientation angle between any two:
       angle ≥ 45° → cross_ventilation_direct = true
       angle < 45° (near-parallel) → false
  4. Interior door present → secondary_path_possible = true.

ACH proxy values:
  PROXY: Order-of-magnitude estimates, not CFD.
  SOURCE: EN 15242 — calculation methods for air flow rates.
  SOURCE: EN 15251 / ASHRAE 62.1 — ACH_target = 4.0 for Mediterranean residential.

vent_deficit_score = min(1 − (ACH_estimated / ACH_target), 1.0)
"""

from __future__ import annotations
import math
from dataclasses import dataclass

from .ifc_parser import FacadeData


# ── Constants ───────────────────────────────────────────────────────────────────

# SOURCE: EN 15251 / ASHRAE 62.1 natural ventilation guidance
ACH_TARGET = 4.0   # minimum adequate ACH for thermal comfort, Mediterranean residential

# PROXY: order-of-magnitude ACH estimates, not CFD.
# SOURCE: EN 15242 Table A.2 — residential natural ventilation reference values.
ACH_SINGLE_FACADE = 0.4       # one exterior facade, openable window
ACH_CROSS_VENTILATED = 2.0    # two non-parallel facades, openable windows (mid of 1.5–2.5)
ACH_NO_OPENABLE = 0.1         # infiltration only

# Minimum orientation angle between two facades to qualify as cross-ventilation
# SOURCE: HVRA_build_reference_4.md §2b — angle ≥ 45° rule
CROSS_VENT_MIN_ANGLE_DEG = 45.0


@dataclass
class VentilationResult:
    exterior_facades: int
    exterior_orientations: list[str]          # compass labels of exterior facades
    cross_ventilation_direct: bool
    cross_ventilation_reason: str
    secondary_path_possible: bool
    secondary_path_note: str
    estimated_ach: float                      # PROXY value
    vent_deficit_score: float                 # 0 (good) → 1 (no ventilation)


def analyze_ventilation(
    facades: list[FacadeData],
    has_interior_doors: bool,
) -> VentilationResult:
    """
    Analyse natural ventilation potential from IFC facade geometry.

    Parameters
    ----------
    facades : list[FacadeData]
        Exterior facades for this room (from ifc_parser).
    has_interior_doors : bool
        True if any interior wall has an IfcDoor (enables secondary path).
    """
    orientations = [f.orientation_degrees for f in facades]
    orientation_labels = [f.orientation_label for f in facades]
    n_ext = len(facades)

    # ── Determine cross-ventilation ─────────────────────────────────────────
    if n_ext == 0:
        cross_direct = False
        reason = "no exterior facades detected in IFC"
        ach = ACH_NO_OPENABLE  # PROXY
    elif n_ext == 1:
        cross_direct = False
        reason = "single exterior facade — no opposing opening"
        # Has window → some natural ventilation
        has_window = facades[0].window_area_m2 > 0.01
        ach = ACH_SINGLE_FACADE if has_window else ACH_NO_OPENABLE  # PROXY
    else:
        # Check all pairs of exterior facades for qualifying angle
        max_angle = _max_pairwise_angle(orientations)
        if max_angle >= CROSS_VENT_MIN_ANGLE_DEG:
            cross_direct = True
            reason = f"two exterior facades with {max_angle:.0f}° separation — cross-ventilation possible"
            ach = ACH_CROSS_VENTILATED  # PROXY
        else:
            cross_direct = False
            reason = (
                f"two exterior facades but only {max_angle:.0f}° apart — "
                "near-parallel, insufficient cross-ventilation"
            )
            ach = ACH_SINGLE_FACADE  # PROXY — behaves like single facade

    # ── Secondary path via interior door ────────────────────────────────────
    if not cross_direct and has_interior_doors:
        secondary_path = True
        secondary_note = (
            "interior door to adjacent space may provide partial stack-effect path"
        )
    else:
        secondary_path = False
        secondary_note = ""

    # ── Ventilation deficit score ────────────────────────────────────────────
    # SOURCE: HVRA_build_reference_4.md §2b
    vent_deficit = min(max(1.0 - (ach / ACH_TARGET), 0.0), 1.0)

    return VentilationResult(
        exterior_facades=n_ext,
        exterior_orientations=orientation_labels,
        cross_ventilation_direct=cross_direct,
        cross_ventilation_reason=reason,
        secondary_path_possible=secondary_path,
        secondary_path_note=secondary_note,
        estimated_ach=round(ach, 2),
        vent_deficit_score=round(vent_deficit, 3),
    )


def _max_pairwise_angle(bearings: list[float]) -> float:
    """
    Return the maximum angular separation between any two compass bearings.
    Uses the shorter arc (0–180°) so NW–SE = 135°, not 225°.
    """
    if len(bearings) < 2:
        return 0.0
    max_angle = 0.0
    for i in range(len(bearings)):
        for j in range(i + 1, len(bearings)):
            diff = abs(bearings[i] - bearings[j]) % 360
            angle = min(diff, 360 - diff)
            if angle > max_angle:
                max_angle = angle
    return max_angle
