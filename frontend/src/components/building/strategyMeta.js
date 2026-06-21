/**
 * Strategy metadata — category, highlight target, colors, and display name.
 * Category drives the visualization mode in RetrofitCard and Viewer3D.
 *
 * Categories:
 *   A — Geometry change: before/after IFC toggle (new element added)
 *   B — Material change: highlight surface in 3D + wall/roof/window section SVG
 *   C — Operational: highlight openings + airflow arrows
 *   D — Urban/external: building-level flag only
 *
 * target: which elements to highlight
 *   'wall'    — exterior wall GlobalIds from room.facades[].wall_id
 *   'window'  — window GlobalIds from room.facades[].window_ids
 *   'roof'    — roof surface (top-floor room, no specific GlobalId — highlight all top-floor walls)
 *   'door'    — interior door (not currently trackable — skip highlight)
 *   'all_windows' — all windows across all facades
 *   'building' — building-level only, no room highlight
 */

export const STRATEGY_META = {
  // ── Category A — Geometry changes ──────────────────────────────────────
  external_shading_louvers: {
    category: 'A',
    name: 'External louvers / brise-soleil',
    target: 'window',
    highlightColor: '#27ae60',   // green — new element
    highlightLabel: 'Louvers added',
  },
  operable_external_sunscreen: {
    category: 'A',
    name: 'Operable external sunscreen',
    target: 'window',
    highlightColor: '#27ae60',
    highlightLabel: 'Sunscreen added',
  },
  window_external_shutters: {
    category: 'A',
    name: 'External shutters (persianes)',
    target: 'window',
    highlightColor: '#27ae60',
    highlightLabel: 'Shutters added',
  },
  green_pergola: {
    category: 'A',
    name: 'Climbing vegetation screen (green façade)',
    target: 'wall',
    highlightColor: '#27ae60',
    highlightLabel: 'Vegetation screen added in front of façade',
  },
  window_enlargement: {
    category: 'A',
    name: 'Window enlargement',
    target: 'window',
    highlightColor: '#27ae60',
    highlightLabel: 'Window enlarged',
  },
  interior_opening_improvement: {
    category: 'A',
    name: 'Transom / interior opening',
    target: 'door',
    highlightColor: '#27ae60',
    highlightLabel: 'Transom added',
  },
  stack_effect_roof_vent: {
    category: 'A',
    name: 'Stack-effect roof vent',
    target: 'roof',
    highlightColor: '#27ae60',
    highlightLabel: 'Roof vent added',
  },

  // ── Category B — Material changes ───────────────────────────────────────
  external_wall_insulation_etics: {
    category: 'B',
    name: 'External wall insulation — ETICS',
    target: 'wall',
    highlightColor: '#e67e22',   // orange — material change
    highlightLabel: 'ETICS insulation layer',
    sectionType: 'wall_etics',
  },
  internal_wall_insulation: {
    category: 'B',
    name: 'Internal wall insulation',
    target: 'wall',
    highlightColor: '#e67e22',
    highlightLabel: 'Internal insulation layer',
    sectionType: 'wall_internal',
  },
  roof_insulation: {
    category: 'B',
    name: 'Roof insulation membrane',
    target: 'roof',
    highlightColor: '#e67e22',
    highlightLabel: 'Insulation membrane added',
    sectionType: 'roof_insulation',
  },
  cool_roof_coating: {
    category: 'B',
    name: 'Cool roof reflective coating',
    target: 'roof',
    highlightColor: '#3498db',   // light blue — albedo change
    highlightLabel: 'Cool coating applied',
    sectionType: 'roof_coating',
  },
  solar_control_glazing: {
    category: 'B',
    name: 'Solar control glazing',
    target: 'window',
    highlightColor: '#3498db',
    highlightLabel: 'Solar control glazing',
    sectionType: 'glazing',
  },
  cool_facade_paint: {
    category: 'B',
    name: 'Cool / reflective façade paint',
    target: 'wall',
    highlightColor: '#ecf0f1',   // near-white — albedo change
    highlightLabel: 'Reflective paint applied',
    sectionType: 'facade_paint',
  },
  phase_change_materials: {
    category: 'B',
    name: 'Phase-change materials (PCM)',
    target: 'wall',
    highlightColor: '#9b59b6',   // purple — thermal mass
    highlightLabel: 'PCM layer integrated',
    sectionType: 'wall_pcm',
  },
  internal_blinds: {
    category: 'B',
    name: 'Internal roller blinds',
    target: 'window',
    highlightColor: '#95a5a6',   // grey — low-impact
    highlightLabel: 'Internal blinds installed',
    sectionType: 'blinds',
  },

  // ── Category C — Operational / behavioral ──────────────────────────────
  night_purge_ventilation: {
    category: 'C',
    name: 'Night purge ventilation',
    target: 'all_windows',
    highlightColor: '#1abc9c',   // teal — airflow
    highlightLabel: 'Open at night (23:00–06:00)',
  },
  cross_ventilation_behaviour: {
    category: 'C',
    name: 'Cross-ventilation protocol',
    target: 'all_windows',
    highlightColor: '#1abc9c',
    highlightLabel: 'Open simultaneously',
  },

  // ── Category D — Urban / external ──────────────────────────────────────
  courtyard_greening: {
    category: 'D',
    name: 'Courtyard greening',
    target: 'building',
    highlightColor: '#27ae60',
    highlightLabel: 'Building-level intervention',
  },
  street_tree_canopy: {
    category: 'D',
    name: 'Street tree canopy',
    target: 'building',
    highlightColor: '#27ae60',
    highlightLabel: 'Municipality coordination required',
  },
  shared_cooling_refuge: {
    category: 'D',
    name: 'Shared cooling refuge',
    target: 'building',
    highlightColor: '#3498db',
    highlightLabel: 'Portfolio-level intervention',
  },
}
