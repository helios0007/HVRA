"""
Stage 2d — Health KPIs and Overheating Score.

Four KPIs computed per room:
  KPI 1  Operative Temperature T_op = (T_air + T_mrt) / 2
         SOURCE: EN ISO 7726; ASHRAE 55-2020 §5.3
         Threshold T_op > 32°C → elderly thermoregulation loss begins
         SOURCE: WHO (2011), Heat and Health technical report

  KPI 2  WBGT_indoor = 0.7 × T_wb + 0.3 × T_air
         T_wb from Stull (2011) formula — accuracy ±0.65°C
         SOURCE: Stull, R. (2011), J. Applied Meteorology and Climatology 50(11)
         SOURCE: ISO 7243:2017 — WBGT thresholds

  KPI 3  Nocturnal recovery: indoor 3 am temp > 26°C → fail flag
         SOURCE: Samuelson et al. (2020); Public Health England (2015)

  KPI 4  Age-weighted overheating hours
         SOURCE: Samuelson et al. (2020) — methodology and thresholds
         Multiplier values 1.2–2.0 are design decisions within Samuelson's range

Sleep disruption thresholds (secondary flags):
  T_air > 24°C → sleep quality degrades
  T_air > 27°C → NREM stage 3 significantly disrupted
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List

from .epw_loader import HourlyClimate, overnight_min_temp
from .solar import SolarResult
from .ventilation import VentilationResult
from .envelope import EnvelopeResult


# ── Occupant risk thresholds ────────────────────────────────────────────────────
# SOURCE: Samuelson et al. (2020) — operative temperature thresholds by age bracket
T_OP_THRESHOLD: dict[str, float] = {
    "under-65": 28.0,
    "65-75":    26.0,
    "75+":      25.0,
}

# SOURCE: WHO (2011), Heat and Health — elderly thermoregulation threshold
T_OP_ELDERLY_RISK = 32.0

# SOURCE: ISO 7243:2017 — WBGT thresholds
WBGT_STRAIN_THRESHOLD = 28.0   # physiological strain, healthy adults
WBGT_ELDERLY_DANGER   = 32.0   # serious risk for elderly

# SOURCE: Samuelson et al. (2020); Public Health England (2015) — nocturnal threshold
NOCTURNAL_FAIL_THRESHOLD = 26.0   # °C indoor at 3 am

# Sleep disruption — established sleep medicine literature
SLEEP_QUALITY_THRESHOLD = 24.0    # T_air > 24°C → sleep quality degrades
SLEEP_NREM_THRESHOLD    = 27.0    # T_air > 27°C → deep sleep significantly disrupted

# UHI delta for Barcelona neighbourhood lookup (subset).
# Full table in HVRA_build_reference_4.md §Stage 1.
# SOURCE: UPC (2025) Barcelona heat vulnerability study + Copernicus Urban Heat Island dataset
# UHI delta is now passed in from uhi.py; this fallback is kept for direct calls
# without a neighbourhood lookup.
# SOURCE: UPC (2025) Barcelona heat vulnerability study — city average UHI.
UHI_DELTA_DEFAULT = 1.5


@dataclass
class OccupantProfile:
    age_bracket: str       # 'under-65' | '65-75' | '75+'
    ac_access: bool
    income_category: str   # 'low' | 'medium' | 'high'
    mobility_limited: bool
    vuln_multiplier: float


@dataclass
class HealthKPIResult:
    # KPI 1
    T_op_estimated_peak_c: float
    T_op_flag: bool                   # True if T_op > 32°C (elderly threshold)

    # KPI 2
    wbgt_peak_estimated: float
    wbgt_strain_flag: bool            # True if WBGT > 28°C
    wbgt_elderly_danger_flag: bool    # True if WBGT > 32°C

    # KPI 3
    estimated_3am_temp_c: float
    nocturnal_recovery_fail: bool     # True if 3am indoor > 26°C

    # KPI 4
    overheating_hours: int            # raw hours where T_op > age-bracket threshold
    health_risk_hours: float          # age-weighted = overheating_hours × vuln_multiplier
    sleep_disruption_flag: bool       # True if bedroom T_air > sleep threshold
    overheating_events: list[dict]    # [{month, day, hour, T_op_C}, ...] — every hour that exceeded threshold

    # Indoor air temperature series (168 values, July 15–21)
    hourly_T_air_c: list[float]


def compute_health_kpis(
    room_type: str,
    area_m2: float,
    solar: SolarResult,
    vent: VentilationResult,
    envelope: EnvelopeResult,
    climate_hours: List[HourlyClimate],
    occupant: OccupantProfile,
    construction_year: str,
    uhi_delta: float = UHI_DELTA_DEFAULT,
) -> HealthKPIResult:
    """
    Compute all four health KPIs for a room.

    Parameters
    ----------
    uhi_delta : float
        Urban Heat Island correction (°C) for this building's neighbourhood.
        Applied as: T_outdoor_adjusted = T_epw + uhi_delta.
        SOURCE: UPC (2025) + Copernicus Urban Heat Island dataset.
        Passed from uhi.get_uhi_correction() via pipeline.py.
    """
    # ── Estimate indoor air temperature for each of the 168 heatwave hours ──
    hourly_T_air = _estimate_hourly_T_air(
        climate_hours, solar, vent, envelope, area_m2, construction_year, uhi_delta
    )

    peak_T_air = max(hourly_T_air)

    # ── KPI 1: Operative Temperature ────────────────────────────────────────
    # T_mrt approximation based on solar exposure
    # SOURCE: EN ISO 7726 — operative temperature definition
    # ASHRAE 55-2020 §5.3 — valid for air velocity < 0.2 m/s (still air)
    if solar.solar_gain_score < 0.4:
        T_mrt = peak_T_air + 2.0    # low solar exposure
    else:
        T_mrt = peak_T_air + 4.0    # high solar exposure
    T_op = (peak_T_air + T_mrt) / 2.0
    T_op_flag = T_op > T_OP_ELDERLY_RISK
    # SOURCE: WHO (2011), Heat and Health — T_OP_ELDERLY_RISK = 32°C

    # ── KPI 2: WBGT ─────────────────────────────────────────────────────────
    # Find the peak-temperature EPW hour for WBGT calculation
    peak_hour = max(climate_hours, key=lambda h: h.dry_bulb_c)
    T_wb_peak = wet_bulb_stull(peak_T_air, peak_hour.relative_humidity_pct)
    wbgt = 0.7 * T_wb_peak + 0.3 * peak_T_air
    # SOURCE: ISO 7243:2017 — indoor WBGT formula (no solar radiation term for indoor)

    # ── KPI 3: Nocturnal Recovery ────────────────────────────────────────────
    # Apply UHI to overnight outdoor minimum — UHI is present at night.
    # SOURCE: Samuelson et al. (2020); Public Health England (2015) — 26°C threshold.
    # SOURCE: UHI correction — T_outdoor_adjusted = T_epw + uhi_delta.
    T_3am_outdoor_epw = overnight_min_temp(climate_hours)
    T_3am_outdoor_adjusted = T_3am_outdoor_epw + uhi_delta
    T_3am_indoor = _estimate_3am_indoor(T_3am_outdoor_adjusted, envelope.thermal_mass_score)
    nocturnal_fail = T_3am_indoor > NOCTURNAL_FAIL_THRESHOLD
    # SOURCE: NOCTURNAL_FAIL_THRESHOLD = 26°C — Samuelson et al. (2020)

    # ── KPI 4: Age-Weighted Overheating Hours ────────────────────────────────
    t_op_threshold = T_OP_THRESHOLD.get(occupant.age_bracket, 28.0)
    # SOURCE: Samuelson et al. (2020) — T_op thresholds by age bracket

    # Compute T_op series from T_air series (same T_mrt offset)
    hourly_T_op = [
        (t + (t + (4.0 if solar.solar_gain_score >= 0.4 else 2.0))) / 2.0
        for t in hourly_T_air
    ]
    overheating_hours = sum(1 for t in hourly_T_op if t > t_op_threshold)
    health_risk_hours = overheating_hours * occupant.vuln_multiplier
    # SOURCE: Samuelson et al. (2020) — age-weighted overheating hours formula

    # Per-hour overheating events — actual calendar timestamps, not just a count.
    # SOURCE: HourlyClimate (month/day/hour) from the EPW heatwave week (July 15–21).
    overheating_events = [
        {
            "month": h.month,
            "day": h.day,
            "hour": h.hour,
            "T_op_C": round(t_op, 1),
        }
        for h, t_op in zip(climate_hours, hourly_T_op)
        if t_op > t_op_threshold
    ]

    # ── Sleep disruption (bedroom-specific flag) ─────────────────────────────
    # T_air > 24°C degrades sleep quality; > 27°C disrupts NREM stage 3
    sleep_flag = False
    if room_type == "bedroom":
        night_temps = [
            t for h, t in zip(climate_hours, hourly_T_air)
            if h.hour in range(22, 25) or h.hour in range(1, 7)
        ]
        if night_temps:
            peak_night = max(night_temps)
            sleep_flag = peak_night > SLEEP_QUALITY_THRESHOLD

    return HealthKPIResult(
        T_op_estimated_peak_c=round(T_op, 1),
        T_op_flag=T_op_flag,
        wbgt_peak_estimated=round(wbgt, 1),
        wbgt_strain_flag=wbgt > WBGT_STRAIN_THRESHOLD,
        wbgt_elderly_danger_flag=wbgt > WBGT_ELDERLY_DANGER,
        estimated_3am_temp_c=round(T_3am_indoor, 1),
        nocturnal_recovery_fail=nocturnal_fail,
        overheating_hours=overheating_hours,
        health_risk_hours=round(health_risk_hours, 1),
        overheating_events=overheating_events,
        sleep_disruption_flag=sleep_flag,
        hourly_T_air_c=[round(t, 2) for t in hourly_T_air],
    )


def wet_bulb_stull(T_air: float, RH: float) -> float:
    """
    Wet-bulb temperature from dry-bulb and relative humidity.
    Accuracy ±0.65°C across Barcelona heatwave T/RH ranges.

    SOURCE: Stull, R. (2011). Wet-Bulb Temperature from Relative Humidity
            and Air Temperature. J. Applied Meteorology and Climatology,
            50(11), 2267–2269.
    """
    T_wb = (
        T_air * math.atan(0.151977 * (RH + 8.313659) ** 0.5)
        + math.atan(T_air + RH)
        - math.atan(RH - 1.676331)
        + 0.00391838 * RH ** 1.5 * math.atan(0.023101 * RH)
        - 4.686035
    )
    return round(T_wb, 2)


def build_occupant_profile(
    age_bracket: str,
    ac_access: bool,
    income_category: str,
    mobility_limited: bool,
) -> OccupantProfile:
    """
    Compute vulnerability multiplier from occupant conditions.

    SOURCE: Samuelson et al. (2020) — multiplier values 1.2–2.0 are design
    decisions within her methodology's implied range.
    """
    vuln = _vuln_multiplier(age_bracket, ac_access, income_category, mobility_limited)
    return OccupantProfile(
        age_bracket=age_bracket,
        ac_access=ac_access,
        income_category=income_category,
        mobility_limited=mobility_limited,
        vuln_multiplier=vuln,
    )


# ── Internal helpers ────────────────────────────────────────────────────────────

def _vuln_multiplier(
    age_bracket: str, ac_access: bool, income_category: str, mobility_limited: bool
) -> float:
    """
    Vulnerability multiplier for age-weighted overheating hours.
    SOURCE: Samuelson et al. (2020) — multipliers 1.2–2.0.
    """
    if age_bracket == "under-65":
        return 1.0

    if age_bracket == "65-75":
        return 1.2 if ac_access else 1.5
        # SOURCE: Samuelson (2020) — 65–75: 1.2 with AC, 1.5 without AC

    if age_bracket == "75+":
        if not ac_access and (income_category == "low" or mobility_limited):
            return 2.0
            # SOURCE: Samuelson (2020) — 75+, no AC, low income or limited mobility
        return 1.8  # 75+ without AC but moderate conditions

    return 1.0


def _estimate_hourly_T_air(
    climate_hours: List[HourlyClimate],
    solar: SolarResult,
    vent: VentilationResult,
    envelope: EnvelopeResult,
    area_m2: float,
    construction_year: str,
    uhi_delta: float = UHI_DELTA_DEFAULT,
) -> list[float]:
    """
    Estimate indoor air temperature for each of the 168 heatwave hours.

    Model:
      T_indoor(t) = T_outdoor_adjusted(t) + ΔT_solar(t) + ΔT_vent_penalty

    where:
      T_outdoor_adjusted = T_epw + uhi_delta
        SOURCE: HVRA_build_reference_4.md §Stage 1 — UHI correction
                T_outdoor_adjusted = T_epw + UHI_DELTA[neighbourhood]

      ΔT_solar(t) = solar_gain_score × 5°C × thermal_damping × (GHI(t) / max_GHI)
        PROXY: Not CFD. Thermal mass damping calibrated for Mediterranean masonry.
        Recalibrate after EnergyPlus validation.
        SOURCE: Calibrated against UPC (2025) Barcelona typology.

      ΔT_vent_penalty = vent_deficit_score × 2°C
        PROXY: SOURCE: Givoni (1992) — ventilation cooling potential 1–3°C Mediterranean.
    """
    max_ghi = max((h.global_horiz_wh_m2 for h in climate_hours), default=1.0)
    if max_ghi < 1.0:
        max_ghi = 1.0

    SOLAR_DELTA_MAX_C = 5.0
    peak_solar_delta = solar.solar_gain_score * SOLAR_DELTA_MAX_C * envelope.thermal_damping

    VENT_PENALTY_MAX_C = 2.0
    vent_penalty = vent.vent_deficit_score * VENT_PENALTY_MAX_C

    T_indoor = []
    for h in climate_hours:
        ghi_fraction = h.global_horiz_wh_m2 / max_ghi
        delta_solar = peak_solar_delta * ghi_fraction
        # Apply UHI correction to every outdoor temperature hour
        # SOURCE: HVRA_build_reference_4.md §Stage 1
        T_air = h.dry_bulb_c + uhi_delta + delta_solar + vent_penalty
        T_indoor.append(T_air)

    return T_indoor


def _estimate_3am_indoor(T_outdoor_3am: float, thermal_mass_score: float) -> float:
    """
    Estimate indoor temperature at 3am from overnight outdoor minimum
    plus thermal mass delta.

    SOURCE: Samuelson et al. (2020); Public Health England (2015).
    Thermal mass delta values from HVRA_build_reference_4.md §KPI3.
    """
    if thermal_mass_score > 0.6:
        delta = 1.0    # high mass: building stays slightly warmer than outdoors
    elif thermal_mass_score < 0.3:
        delta = 3.0    # low mass: building releases daytime heat, stays warmer
    else:
        delta = 2.0    # mid mass

    return T_outdoor_3am + delta
