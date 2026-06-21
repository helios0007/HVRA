"""
Stage 2a — Solar Gain per Façade.

Formula:
    Solar_gain (W) = I_solar × A_window × SHGC × (1 − shading_factor)
where:
    I_solar = I_direct × shadow_factor + I_diffuse  (per hour)
    solar_gain_score = min(peak_Solar_gain / 600, 1.0)

shadow_factor (0=shaded by surrounding buildings, 1=exposed) is computed by
shadow.py using shapely polygons and passed in as a precomputed list.

shading_factor (0=no IFC shading, ~0.7 if IFC louvers present) accounts for
  fixed architectural shading elements detected in the IFC model.

SOURCE: ASHRAE Fundamentals Handbook Ch.18 — solar gain formula, SHGC defaults.
SOURCE: HVRA_build_reference_4.md §2a — solar_gain_score normalisation at 600 W.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

import math

try:
    import pvlib
    import pandas as pd
    _PVLIB_AVAILABLE = True
except ImportError:
    _PVLIB_AVAILABLE = False

from .ifc_parser import FacadeData
from .epw_loader import HourlyClimate


SOLAR_GAIN_CRITICAL_W = 600.0   # SOURCE: HVRA_build_reference_4.md §2a — upper bound

# PROXY: IFC shading element reduces gain by 70% (external louver at typical angle).
# Real reduction depends on louver geometry — use detailed calculation when available.
IFC_SHADING_FACTOR = 0.70


@dataclass
class FacadeSolarResult:
    orientation_degrees: float
    orientation_label: str
    peak_irradiance_w_m2: float     # peak I_effective on facade surface (W/m²)
    peak_solar_gain_w: float        # peak instantaneous Solar_gain (W)
    solar_gain_score: float         # 0–1
    shadow_factor_avg: float        # mean shadow_factor during exposed hours (0–1)
    exposed_hours: int              # hours where sun is on this facade's side


@dataclass
class SolarResult:
    solar_gain_score: float                    # room-level max across all facades
    peak_solar_w_per_m2: float                 # peak I_effective on worst facade
    facades: list[FacadeSolarResult]
    hourly_indoor_delta_c: list[float]         # 168 values for T_air estimation


def compute_solar_results(
    facades: list[FacadeData],
    climate_hours: List[HourlyClimate],
    lat: float,
    lon: float,
    shadow_map: Optional[list[float]] = None,      # 168 precomputed shadow factors
    azimuth_map: Optional[list[float]] = None,     # 168 sun azimuths (degrees)
    elevation_map: Optional[list[float]] = None,   # 168 sun elevations (degrees)
    times=None,
    solar_pos=None,
) -> SolarResult:
    """
    Compute solar gain for every exterior facade of a room.

    shadow_map, azimuth_map, elevation_map should be precomputed by pipeline.py
    (once per building, shared by all rooms) via shadow.compute_building_shadow_map().
    If not provided, shadow_factor defaults to 1.0 (no obstruction assumed).

    Returns a SolarResult with per-facade scores and an hourly ΔT series
    (168 values) representing the solar contribution to indoor air temperature.
    """
    if not facades:
        return SolarResult(
            solar_gain_score=0.0,
            peak_solar_w_per_m2=0.0,
            facades=[],
            hourly_indoor_delta_c=[0.0] * len(climate_hours),
        )

    n = len(climate_hours)
    _shadow = shadow_map if shadow_map is not None else [1.0] * n
    _azimuth = azimuth_map if azimuth_map is not None else [0.0] * n
    _elevation = elevation_map if elevation_map is not None else [45.0] * n

    if _PVLIB_AVAILABLE and solar_pos is None:
        times, solar_pos = _get_solar_positions(lat, lon, climate_hours)

    facade_results: list[FacadeSolarResult] = []
    worst_hourly_gain = [0.0] * n

    for facade in facades:
        hourly_gain_w = _compute_facade_hourly_gain(
            facade=facade,
            climate_hours=climate_hours,
            times=times,
            solar_pos=solar_pos,
            shadow_map=_shadow,
        )

        peak_gain = max(hourly_gain_w) if hourly_gain_w else 0.0
        score = min(peak_gain / SOLAR_GAIN_CRITICAL_W, 1.0)

        # Peak irradiance on the facade surface (before window area × SHGC)
        reduction = IFC_SHADING_FACTOR if facade.has_external_shading else 0.0
        denom = facade.window_area_m2 * facade.shgc * (1.0 - reduction)
        peak_irr = (peak_gain / denom) if denom > 0.0 else 0.0

        # Per-facade shadow stats restricted to exposed hours
        from .shadow import per_facade_shadow_stats
        avg_sf, exposed_h = per_facade_shadow_stats(
            _shadow, _azimuth, _elevation, facade.orientation_degrees
        )

        facade_results.append(FacadeSolarResult(
            orientation_degrees=facade.orientation_degrees,
            orientation_label=facade.orientation_label,
            peak_irradiance_w_m2=round(peak_irr, 1),
            peak_solar_gain_w=round(peak_gain, 1),
            solar_gain_score=round(score, 3),
            shadow_factor_avg=avg_sf,
            exposed_hours=exposed_h,
        ))

        for i, gain in enumerate(hourly_gain_w):
            if gain > worst_hourly_gain[i]:
                worst_hourly_gain[i] = gain

    room_score = max(f.solar_gain_score for f in facade_results)
    peak_irr_room = max(f.peak_irradiance_w_m2 for f in facade_results)

    # Indoor ΔT from solar: PROXY calibrated for Mediterranean masonry 14 m² room.
    # Recalibrate after EnergyPlus validation.
    hourly_delta_c = [g * 0.007 for g in worst_hourly_gain]

    return SolarResult(
        solar_gain_score=round(room_score, 3),
        peak_solar_w_per_m2=round(peak_irr_room, 1),
        facades=facade_results,
        hourly_indoor_delta_c=hourly_delta_c,
    )


def fetch_surrounding_buildings(lat: float, lon: float, radius_m: float = 100.0):
    """
    Fetch surrounding building footprints + heights from OpenStreetMap.
    Returns a GeoDataFrame or None if osmnx unavailable / network error.

    SOURCE: HVRA_build_reference_4.md §Stage 1 — osmnx surrounding buildings.
    """
    try:
        import osmnx as ox
        return ox.features_from_point(
            (lat, lon),
            tags={"building": True},
            dist=radius_m,
        )
    except Exception:
        return None


# ── Internal helpers ────────────────────────────────────────────────────────────

def _get_solar_positions(lat: float, lon: float, climate_hours: List[HourlyClimate]):
    """
    Compute sun azimuth and elevation for each EPW hour using pvlib.
    Exposed here so pipeline.py can call it once and reuse for shadow + solar.
    SOURCE: pvlib — Holmgren et al. (2018), JOSS.
    """
    from .shadow import get_solar_positions as _gsp
    return _gsp(lat, lon, climate_hours)


def _compute_facade_hourly_gain(
    facade: FacadeData,
    climate_hours: List[HourlyClimate],
    times,
    solar_pos,
    shadow_map: list[float],
) -> list[float]:
    ifc_shading = IFC_SHADING_FACTOR if facade.has_external_shading else 0.0
    if _PVLIB_AVAILABLE and solar_pos is not None:
        return _pvlib_hourly_gain(facade, climate_hours, times, solar_pos, shadow_map, ifc_shading)
    return _geometric_hourly_gain(facade, climate_hours, shadow_map, ifc_shading)


def _pvlib_hourly_gain(
    facade: FacadeData,
    climate_hours: List[HourlyClimate],
    times,
    solar_pos,
    shadow_map: list[float],
    ifc_shading: float,
) -> list[float]:
    """Full pvlib POA irradiance on a vertical facade, with shapely shadow map applied."""
    gains = []
    for i, h in enumerate(climate_hours):
        zenith = float(solar_pos["apparent_zenith"].iloc[i])
        azimuth = float(solar_pos["azimuth"].iloc[i])
        elevation = float(solar_pos["apparent_elevation"].iloc[i])

        if elevation <= 0.0:
            gains.append(0.0)
            continue

        try:
            airmass = pvlib.atmosphere.get_relative_airmass(zenith)
            dni_extra = float(pvlib.irradiance.get_extra_radiation(times[i]))
            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=90,
                surface_azimuth=facade.orientation_degrees,
                solar_zenith=zenith,
                solar_azimuth=azimuth,
                dni=h.direct_normal_wh_m2,
                ghi=h.global_horiz_wh_m2,
                dhi=h.diffuse_horiz_wh_m2,
                model="perez",
                airmass=airmass,
                dni_extra=dni_extra,
            )
        except Exception:
            gains.append(0.0)
            continue

        I_direct = max(0.0, float(poa.get("poa_direct", 0.0)))
        I_diffuse = max(0.0, float(poa.get("poa_sky_diffuse", 0.0))) + max(
            0.0, float(poa.get("poa_ground_diffuse", 0.0))
        )

        shadow_f = shadow_map[i]   # 0=shaded, 1=exposed — from shapely shadow.py

        # SOURCE: HVRA_build_reference_4.md §2a
        I_solar = I_direct * shadow_f + I_diffuse
        gain = I_solar * facade.window_area_m2 * facade.shgc * (1.0 - ifc_shading)
        gains.append(max(0.0, gain))

    return gains


def _geometric_hourly_gain(
    facade: FacadeData,
    climate_hours: List[HourlyClimate],
    shadow_map: list[float],
    ifc_shading: float,
) -> list[float]:
    """
    Fallback solar gain when pvlib is unavailable.
    PROXY: Simplified geometric approximation — install pvlib for accuracy.
    """
    gains = []
    for i, h in enumerate(climate_hours):
        solar_hour = h.hour - 1 + 0.5
        hour_angle_deg = (solar_hour - 12) * 15.0
        declination_deg = 21.5   # approx July declination

        cos_inc = _cosine_incidence_vertical(
            40.5, declination_deg, hour_angle_deg, facade.orientation_degrees
        )
        if cos_inc <= 0.0:
            gains.append(0.0)
            continue

        shadow_f = shadow_map[i]
        I_direct_facade = h.direct_normal_wh_m2 * cos_inc * shadow_f
        I_diffuse_facade = h.diffuse_horiz_wh_m2 * 0.5
        I_solar = I_direct_facade + I_diffuse_facade
        gain = I_solar * facade.window_area_m2 * facade.shgc * (1.0 - ifc_shading)
        gains.append(max(0.0, gain))
    return gains


def _cosine_incidence_vertical(
    lat_deg: float,
    declination_deg: float,
    hour_angle_deg: float,
    surface_azimuth_deg: float,
) -> float:
    """PROXY: Simplified incidence angle formula for a vertical surface."""
    phi = math.radians(lat_deg)
    delta = math.radians(declination_deg)
    omega = math.radians(hour_angle_deg)
    gamma = math.radians(surface_azimuth_deg - 180)
    cos_theta = (
        -math.sin(delta) * math.cos(phi) * math.cos(gamma)
        + math.cos(delta) * math.sin(phi) * math.cos(omega) * math.cos(gamma)
        + math.cos(delta) * math.sin(omega) * math.sin(gamma)
    )
    return max(0.0, cos_theta)
