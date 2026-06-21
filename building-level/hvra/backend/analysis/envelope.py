"""
Stage 2c — Envelope Thermal Performance.

Flags walls and roofs with high U-values (poor thermal resistance).
Computes envelope_score (0–1) for use in the composite score.
Estimates thermal mass score from construction era.

U-value lookup table:
  SOURCE: CTE DB-HE historical compliance requirements.
  SOURCE: IVE (Institut Valencià de l'Edificació) Mediterranean typology database.

Flagging thresholds:
  Wall  U > 1.2 W/m²K  → flag for insulation intervention
  Roof  U > 1.5 W/m²K  → flag for roof insulation intervention
  SOURCE: CTE DB-HE 2022 renovation requirements for climate zone B3 (Barcelona).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from .ifc_parser import FacadeData, U_VALUE_DEFAULTS
from .epw_loader import HourlyClimate


# ── Flagging thresholds ─────────────────────────────────────────────────────────
# SOURCE: CTE DB-HE 2022 — renovation requirements for existing buildings in B3
WALL_U_FLAG_THRESHOLD = 1.2   # W/m²K
ROOF_U_FLAG_THRESHOLD = 1.5   # W/m²K

# ── Roof solar absorption factors by roof colour ────────────────────────────────
# absorption = 1 − albedo. Albedo (solar reflectance) ranges and midpoints below:
# SOURCE: Lawrence Berkeley National Laboratory (LBNL) Heat Island Group Pigment
#         Database; Cool Roof Rating Council (CRRC) product rating database;
#         US EPA Heat Island Reduction Program technical profiles; ASTM E1980.
#   dark_tile        Dark Concrete Tiles / Aged Dark Asphalt   albedo 0.04–0.35 → mid 0.15
#   terracotta       Red / Terracotta Clay Tiles               albedo 0.25–0.35 → mid 0.30
#   light_tile       Light Grey / Cream Tiles                  albedo 0.40–0.55 → mid 0.475
#   metal            Unpainted Corrugated Steel                albedo 0.30–0.50 → mid 0.40
#   reflective       White Concrete Tiles / Elastomeric White Paint  albedo 0.70–0.85 → mid 0.775
ROOF_ALBEDO = {
    "dark_tile":   0.15,
    "terracotta":  0.30,
    "light_tile":  0.475,
    "metal":       0.40,
    "reflective":  0.775,
}
ROOF_ABSORPTION = {k: round(1.0 - v, 3) for k, v in ROOF_ALBEDO.items()}
# Back-compat aliases for older job data saved under the previous 3-option scheme
ROOF_ABSORPTION["dark"] = ROOF_ABSORPTION["dark_tile"]
ROOF_ABSORPTION["light"] = ROOF_ABSORPTION["light_tile"]

# ── Thermal mass score by era ────────────────────────────────────────────────────
# Higher score = more thermal mass (delays peak, reduces swing).
# PROXY: Relative scale 0–1 derived from wall mass density (kg/m²) by era.
# SOURCE: IVE typology database — Mediterranean residential construction types.
THERMAL_MASS_BY_ERA = {
    "pre-1960":  0.80,   # solid masonry: brick/stone ≥ 300 mm
    "1960-1979": 0.60,   # hollow brick + concrete frame
    "1980-2006": 0.35,   # lightweight concrete block
    "post-2006": 0.25,   # modern lightweight / insulated systems
}

# Thermal mass damping factor applied to steady-state solar gain ΔT.
# High mass absorbs heat, reducing peak indoor swing.
# PROXY: calibrated for Mediterranean masonry; validate with EnergyPlus.
THERMAL_DAMPING = {
    "pre-1960":  0.25,
    "1960-1979": 0.35,
    "1980-2006": 0.45,
    "post-2006": 0.50,
}


# Roof solar gain normalisation, in W/m² of roof (NOT a flat W threshold).
# The facade solar_gain_score in solar.py is normalised against 600 W of gain
# through a typical window opening (1–3 m²) — that threshold cannot be reused
# directly for the roof, since roof area (≈ room floor area, e.g. 15–60 m²) is
# an order of magnitude larger and would saturate the score at 1.0 regardless
# of colour. Instead the roof gain is normalised per m² of roof, using the
# same 600 W reference but scaled to a representative ~3 m² opening
# (600 / 3 = 200 W/m²) as the "critical" specific gain.
ROOF_GAIN_CRITICAL_W_PER_M2 = 200.0

# External surface film coefficient (combined convective + radiative), used in
# the Sol-Air temperature method to convert absorbed radiation into an
# equivalent surface temperature rise.
# SOURCE: ASHRAE Fundamentals Handbook Ch.18 — sol-air temperature, typical
# external film coefficient h_o ≈ 17–23 W/m²K for outdoor surfaces in light
# to moderate wind; 19 W/m²K used here (ASHRAE default for vertical/horizontal
# exterior surfaces, 7.5 mph wind).
EXTERNAL_FILM_COEFFICIENT = 19.0  # W/m²K


@dataclass
class EnvelopeResult:
    roof_exposed: bool
    roof_u_value: float             # W/m²K
    roof_u_flag: bool               # True if U > 1.5 W/m²K
    roof_absorption: float          # solar absorption factor (0–1)
    roof_peak_solar_gain_w: float   # peak instantaneous roof solar gain (W), sol-air method
    roof_solar_gain_score: float    # 0–1, same 600 W normalisation as facades
    dominant_wall_u_value: float    # W/m²K — highest among exterior walls
    wall_u_flag: bool               # True if any wall U > 1.2 W/m²K
    thermal_mass_score: float       # 0–1
    thermal_damping: float          # 0–1 (reduces solar-driven ΔT in health model)
    envelope_score: float           # 0–1 normalised for composite score


def compute_roof_solar_gain(
    roof_u_value: float,
    roof_absorption: float,
    area_m2: float,
    climate_hours: List[HourlyClimate],
) -> tuple[float, float]:
    """
    Peak roof solar heat gain via the Sol-Air Temperature method (ASHRAE
    Fundamentals Handbook Ch.18), applied to a horizontal roof surface.

    Sol-air temperature:  T_sol-air = T_outdoor + (absorption × GHI) / h_o
    Roof heat gain:        Q_roof   = U_roof × A_roof × (T_sol-air − T_outdoor)
                                     = U_roof × A_roof × absorption × GHI / h_o

    GHI (global horizontal irradiance) is used directly without a tilt
    transform since the roof is treated as a horizontal surface.

    Returns (peak_gain_w, solar_gain_score).
    """
    if not climate_hours or area_m2 <= 0:
        return 0.0, 0.0

    peak_gain = 0.0
    for h in climate_hours:
        ghi = max(0.0, h.global_horiz_wh_m2)
        delta_t_sol_air = (roof_absorption * ghi) / EXTERNAL_FILM_COEFFICIENT
        gain = roof_u_value * area_m2 * delta_t_sol_air
        if gain > peak_gain:
            peak_gain = gain

    # Normalise per m² of roof so the score reflects roof colour/U-value
    # intensity, independent of how large the room happens to be.
    gain_per_m2 = peak_gain / area_m2 if area_m2 > 0 else 0.0
    score = min(gain_per_m2 / ROOF_GAIN_CRITICAL_W_PER_M2, 1.0)
    return round(peak_gain, 1), round(score, 3)


def compute_envelope(
    facades: list[FacadeData],
    construction_year: str,
    roof_colour: str,
    is_top_floor: bool,
    area_m2: float = 0.0,
    climate_hours: Optional[List[HourlyClimate]] = None,
) -> EnvelopeResult:
    """
    Compute envelope thermal performance for a single room.

    Parameters
    ----------
    facades : list[FacadeData]
        Exterior facades (already have wall_u_value from IFC or era lookup).
    construction_year : str
        One of 'pre-1960' | '1960-1979' | '1980-2006' | 'post-2006'.
    roof_colour : str
        One of 'dark_tile' | 'terracotta' | 'light_tile' | 'metal' | 'reflective'
        (legacy 'dark' / 'light' accepted as aliases).
    is_top_floor : bool
        True if room is on the highest storey — determines roof_exposed.
    area_m2 : float
        Room floor area — used as the roof area for top-floor rooms (flat-roof
        assumption: roof area ≈ floor area below it).
    climate_hours : list[HourlyClimate], optional
        EPW heatwave-week hourly records, needed for the roof solar gain term.
        If omitted, roof_peak_solar_gain_w / roof_solar_gain_score are 0.
    """
    era = construction_year

    # ── Wall U-value ────────────────────────────────────────────────────────
    wall_u_values = [f.wall_u_value for f in facades] if facades else []
    dominant_wall_u = max(wall_u_values) if wall_u_values else U_VALUE_DEFAULTS.get(era, U_VALUE_DEFAULTS["pre-1960"])["wall"]
    wall_u_flag = dominant_wall_u > WALL_U_FLAG_THRESHOLD
    # SOURCE: CTE DB-HE 2022 — WALL_U_FLAG_THRESHOLD = 1.2 W/m²K

    # ── Roof U-value ────────────────────────────────────────────────────────
    roof_exposed = is_top_floor
    roof_u = U_VALUE_DEFAULTS.get(era, U_VALUE_DEFAULTS["pre-1960"])["roof"]
    roof_u_flag = roof_exposed and roof_u > ROOF_U_FLAG_THRESHOLD
    # SOURCE: CTE DB-HE 2022 — ROOF_U_FLAG_THRESHOLD = 1.5 W/m²K

    roof_abs = ROOF_ABSORPTION.get(roof_colour, ROOF_ABSORPTION["dark_tile"])

    # ── Roof solar gain (sol-air method) — only for top-floor/roof-exposed rooms
    if roof_exposed and climate_hours:
        roof_peak_gain, roof_solar_score = compute_roof_solar_gain(
            roof_u_value=roof_u,
            roof_absorption=roof_abs,
            area_m2=area_m2,
            climate_hours=climate_hours,
        )
    else:
        roof_peak_gain, roof_solar_score = 0.0, 0.0

    # ── Thermal mass ─────────────────────────────────────────────────────────
    mass_score = THERMAL_MASS_BY_ERA.get(era, 0.35)
    damping = THERMAL_DAMPING.get(era, 0.40)

    # ── Envelope score (0–1) for composite formula ───────────────────────────
    # Normalise dominant wall U against the flag threshold.
    # Wall contribution weighted 2/3, roof contribution 1/3 (wall area >> roof area).
    # Roof penalty now blends U-value flagging with the colour-driven solar
    # gain score, so a dark roof scores worse than a reflective one even at
    # identical U-value.
    wall_penalty = min((dominant_wall_u - WALL_U_FLAG_THRESHOLD) / WALL_U_FLAG_THRESHOLD, 1.0)
    wall_penalty = max(wall_penalty, 0.0)

    if roof_exposed:
        roof_u_penalty = min((roof_u - ROOF_U_FLAG_THRESHOLD) / ROOF_U_FLAG_THRESHOLD, 1.0)
        roof_u_penalty = max(roof_u_penalty, 0.0)
        roof_penalty = max(roof_u_penalty, roof_solar_score)
    else:
        roof_penalty = 0.0

    envelope_score = round((2 / 3) * wall_penalty + (1 / 3) * roof_penalty, 3)

    return EnvelopeResult(
        roof_exposed=roof_exposed,
        roof_u_value=round(roof_u, 2),
        roof_u_flag=roof_u_flag,
        roof_absorption=roof_abs,
        roof_peak_solar_gain_w=roof_peak_gain,
        roof_solar_gain_score=roof_solar_score,
        dominant_wall_u_value=round(dominant_wall_u, 2),
        wall_u_flag=wall_u_flag,
        thermal_mass_score=round(mass_score, 2),
        thermal_damping=round(damping, 2),
        envelope_score=envelope_score,
    )
