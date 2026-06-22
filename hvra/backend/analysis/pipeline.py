"""
HVRA Pipeline orchestrator — Stages 2 + 4a.

Run order per building upload:
  1.  Parse IFC → rooms + facades              (ifc_parser)
  2.  Load EPW climate data + night min        (epw_loader)
  3.  Compute solar positions — once           (shadow.get_solar_positions via pvlib)
  4.  Fetch surrounding buildings from OSM     (solar.fetch_surrounding_buildings)
  5.  Compute shadow map — once per building   (shadow.compute_building_shadow_map)
  6.  UHI correction — once per building       (uhi.get_uhi_correction)
  7.  Load strategy library — once             (prefilter.load_strategy_library)
  8.  Build occupant profile — once            (health_kpis.build_occupant_profile)

  Per room:
    Stage 2a  Solar gain                       (solar.compute_solar_results)
    Stage 2b  Ventilation                      (ventilation.analyze_ventilation)
    Stage 2c  Envelope                         (envelope.compute_envelope)
    Stage 2d  Health KPIs + UHI correction     (health_kpis.compute_health_kpis)
              Composite score + JSON assembly  (scoring.build_room_json)
    Stage 4a  Pre-filter eligible strategies   (prefilter.run_prefilter)

  10. Write room_problems.json + priority.json + eligible_strategies.json
"""

from __future__ import annotations
import logging
import os
from typing import Any

from .ifc_parser import parse_ifc
from .epw_loader import load_epw_or_synthetic, overnight_min_temp, prevailing_wind_direction
from .shadow import get_solar_positions, compute_building_shadow_map
from .solar import compute_solar_results, fetch_surrounding_buildings
from .ventilation import analyze_ventilation
from .envelope import compute_envelope
from .health_kpis import compute_health_kpis, build_occupant_profile
from .uhi import get_uhi_correction
from .scoring import build_room_json, write_room_problems_json, write_priority_json
from .prefilter import load_strategy_library, run_prefilter, write_eligible_strategies_json

logger = logging.getLogger(__name__)

EPW_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "barcelona", "barcelona.epw"
)


def run_pipeline(
    ifc_path: str,
    lat: float,
    lon: float,
    construction_year: str,
    roof_colour: str,
    heritage_protection: bool,
    shutter_boxes: bool,
    oldest_resident_age: str,
    ac_access: bool,
    income_category: str,
    mobility_limitations: bool,
    output_dir: str,
) -> dict[str, Any]:
    """
    Run the Stage 2 calculation engine end-to-end for one building.

    Returns dict with keys:
        rooms         : list of room dicts (room_problems.json content)
        files         : paths to written output files
        epw_synthetic : bool — True if synthetic EPW fallback was used
        neighbourhood : str  — neighbourhood name from UHI lookup
        uhi_delta     : float — UHI correction applied (°C)
        epw_night_min : float — EPW overnight min temp (°C), used for night purge eligibility
        warnings      : list of warning strings
    """
    warnings: list[str] = []

    # ── 1. Parse IFC ────────────────────────────────────────────────────────
    logger.info("Parsing IFC: %s", ifc_path)
    rooms = parse_ifc(ifc_path, construction_year)
    if not rooms:
        warnings.append(
            "No IfcSpace elements found in the IFC file. "
            "Ensure rooms are exported (Revit: File → Export → IFC → "
            "'Export rooms and spaces')."
        )
        return {
            "rooms": [], "files": {}, "epw_synthetic": False,
            "neighbourhood": "unknown", "uhi_delta": 1.5, "warnings": warnings,
        }
    logger.info("Found %d rooms", len(rooms))

    # ── 2. Load EPW climate data ─────────────────────────────────────────────
    logger.info("Loading EPW: %s", EPW_PATH)
    climate_hours, is_synthetic = load_epw_or_synthetic(EPW_PATH)
    epw_night_min = overnight_min_temp(climate_hours)
    logger.info("EPW overnight min (3–5am): %.1f°C (night purge eligibility threshold: 22°C)", epw_night_min)
    if is_synthetic:
        warnings.append(
            "EPW file not found — using synthetic Barcelona July climate data. "
            "Download ESP_CT_Barcelona.081810_TMYx.epw from climate.onebuilding.org "
            "and place it at backend/config/barcelona/barcelona.epw."
        )

    # ── 3. Compute solar positions once (shared by shadow + solar modules) ──
    logger.info("Computing solar positions for lat=%.4f, lon=%.4f", lat, lon)
    times, solar_pos = get_solar_positions(lat, lon, climate_hours)
    if solar_pos is None:
        warnings.append(
            "pvlib not installed — solar positions unavailable. "
            "Shadow analysis and pvlib POA irradiance will be skipped. "
            "Run: pip install pvlib pandas"
        )

    # ── 4. Fetch surrounding buildings from OSM ──────────────────────────────
    logger.info("Fetching surrounding buildings from OSM (100 m radius)")
    buildings_gdf = fetch_surrounding_buildings(lat, lon, radius_m=100.0)
    if buildings_gdf is None:
        warnings.append(
            "Surrounding buildings not available (osmnx not installed or network error). "
            "Shadow factors set to 1.0 — solar gain scores may be slightly overestimated."
        )
    else:
        logger.info("OSM: %d surrounding building features fetched", len(buildings_gdf))

    # ── 5. Compute shadow map — once per building ────────────────────────────
    logger.info("Computing shapely shadow polygons for 168 heatwave hours")
    shadow_map, azimuth_map, elevation_map = compute_building_shadow_map(
        buildings_gdf=buildings_gdf,
        lat=lat,
        lon=lon,
        solar_pos=solar_pos,
        climate_hours=climate_hours,
    )
    daytime_total = sum(1 for e in elevation_map if e > 0)
    shaded_hours = sum(
        1 for sf, el in zip(shadow_map, elevation_map) if sf == 0.0 and el > 0
    )
    logger.info(
        "Shadow map complete: %d/%d daytime hours shaded by surrounding buildings",
        shaded_hours, daytime_total,
    )

    # ── 6. UHI correction ────────────────────────────────────────────────────
    neighbourhood, uhi_delta = get_uhi_correction(lat, lon)
    logger.info(
        "UHI: neighbourhood=%s, delta=+%.1f°C applied to all T_outdoor values",
        neighbourhood, uhi_delta,
    )

    # ── 7. Load strategy library (once per pipeline run) ────────────────────
    try:
        strategy_library = load_strategy_library()
        logger.info("Strategy library loaded: %d strategies", len(strategy_library))
    except Exception as exc:
        strategy_library = []
        warnings.append(f"Strategy library not loaded: {exc}")

    # ── 8. Build occupant profile (same across all rooms) ───────────────────
    occupant = build_occupant_profile(
        age_bracket=oldest_resident_age,
        ac_access=ac_access,
        income_category=income_category,
        mobility_limited=mobility_limitations,
    )

    # ── 9. Per-room analysis ─────────────────────────────────────────────────
    room_jsons: list[dict] = []

    for room in rooms:
        logger.debug("Analysing room: %s (%s)", room.room_name, room.room_id)

        # Stage 2a — Solar gain with shapely shadow map
        solar = compute_solar_results(
            facades=room.facades,
            climate_hours=climate_hours,
            lat=lat,
            lon=lon,
            shadow_map=shadow_map,
            azimuth_map=azimuth_map,
            elevation_map=elevation_map,
            times=times,
            solar_pos=solar_pos,
        )

        # Stage 2b — Ventilation
        vent = analyze_ventilation(
            facades=room.facades,
            has_interior_doors=room.has_interior_doors,
        )

        # Stage 2c — Envelope
        envelope = compute_envelope(
            facades=room.facades,
            construction_year=construction_year,
            roof_colour=roof_colour,
            is_top_floor=room.is_top_floor,
            area_m2=room.area_m2,
            climate_hours=climate_hours,
        )

        # Stage 2d — Health KPIs with UHI correction
        kpis = compute_health_kpis(
            room_type=room.room_type,
            area_m2=room.area_m2,
            solar=solar,
            vent=vent,
            envelope=envelope,
            climate_hours=climate_hours,
            occupant=occupant,
            construction_year=construction_year,
            uhi_delta=uhi_delta,                 # ← applied to every T_outdoor hour
        )

        record = build_room_json(
            room=room,
            solar=solar,
            vent=vent,
            envelope=envelope,
            kpis=kpis,
            occupant=occupant,
            heritage_protection=heritage_protection,
            shutter_boxes=shutter_boxes,
            neighbourhood=neighbourhood,
            uhi_delta=uhi_delta,
        )

        # Stage 4a — pre-filter eligible strategies
        if strategy_library:
            eligible_ids = run_prefilter(
                room=record,
                strategy_library=strategy_library,
                heritage_protection=heritage_protection,
                shutter_boxes=shutter_boxes,
                epw_night_min=epw_night_min,
                construction_year=construction_year,
            )
            record["ai_outputs"]["eligible_strategies"] = eligible_ids

        room_jsons.append(record)

    # ── 10. Write output files ───────────────────────────────────────────────
    rp_path = write_room_problems_json(room_jsons, output_dir)
    pr_path = write_priority_json(room_jsons, output_dir)
    es_path = write_eligible_strategies_json(room_jsons, strategy_library, output_dir)

    logger.info(
        "Pipeline complete: %d rooms → %s (eligible_strategies written: %s)",
        len(room_jsons), output_dir, bool(es_path),
    )

    from .ifc_parser import get_roof_element_ids
    roof_element_ids = get_roof_element_ids(ifc_path)

    # Prevailing July daytime wind — drives ventilation inlet/outlet display.
    # Synthetic fallback 135° = Barcelona's summer sea breeze (marinada, SE).
    wind_deg = prevailing_wind_direction(EPW_PATH)
    if wind_deg is None:
        wind_deg = 135.0

    # Cross-ventilation diagnosis overlay — independent of the room scoring
    # above, so a failure here must never break the rest of the pipeline.
    try:
        from .cross_ventilation import analyze_cross_ventilation
        cross_vent_result = analyze_cross_ventilation(ifc_path)
        import json as _json
        cv_path = os.path.join(output_dir, "cross_ventilation.json")
        with open(cv_path, "w", encoding="utf-8") as f:
            _json.dump(cross_vent_result, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.exception("Cross-ventilation analysis failed — continuing without it")
        cross_vent_result = {"spaces": []}
        warnings.append(f"Cross-ventilation diagnosis failed: {exc}")

    return {
        "rooms": room_jsons,
        "roof_element_ids": roof_element_ids,
        "prevailing_wind_deg": wind_deg,
        "cross_ventilation": cross_vent_result,
        "files": {
            "room_problems": rp_path,
            "priority": pr_path,
            "eligible_strategies": es_path,
        },
        "epw_synthetic": is_synthetic,
        "neighbourhood": neighbourhood,
        "uhi_delta": uhi_delta,
        "epw_night_min": epw_night_min,
        "warnings": warnings,
    }
