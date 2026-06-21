import React, { useState } from 'react'
import WallSection from './WallSection'
import LouverSketch from './LouverSketch'
import { STRATEGY_META } from './strategyMeta'
import './RetrofitCard.css'

const RANK_LABELS = { 1: '1st', 2: '2nd', 3: '3rd' }

const CATEGORY_BADGE = {
  A: { label: 'Geometry', color: '#27ae60' },
  B: { label: 'Material', color: '#e67e22' },
  C: { label: 'Operational', color: '#1abc9c' },
  D: { label: 'Urban', color: '#3498db' },
}

// Shading strategies only apply to specific facade orientations — highlight
// only windows on those facades (mirrors the backend pre-filter conditions).
const SHADING_TARGETS = {
  external_shading_louvers:    { orients: ['S', 'SE', 'SW'], minSolar: 0.6 },
  window_external_shutters:    { orients: ['S', 'SE', 'SW'], minSolar: 0.6 },
  operable_external_sunscreen: { orients: ['S', 'SE', 'SW', 'W'], minSolar: 0.6 },
  solar_control_glazing:       { orients: ['S', 'SE', 'SW', 'W'], minSolar: 0.5 },
}

// Behavioural ventilation schedules rendered as protocol tables
const SCHEDULES = {
  cross_ventilation_behaviour: [
    ['07:00–10:00', 'Open windows on both façades together', 'Outdoor cooler than indoor'],
    ['10:00–20:00', 'Close windows, lower shading', 'Outdoor hotter than indoor'],
    ['20:00–23:00', 'Re-open both façades together', 'Outdoor cooler than indoor'],
  ],
  night_purge_ventilation: [
    ['23:00–06:00', 'Open all available openings', 'Only if outdoor < indoor temperature'],
    ['06:00–08:00', 'Close everything, shutters down', 'Trap the overnight coolth'],
    ['08:00–23:00', 'Keep closed during the heat of day', 'Re-open only if outdoor turns cooler'],
  ],
}

const VENT_PALETTE = ['#1abc9c', '#e67e22', '#9b59b6', '#3498db']

/**
 * Facades that a shading strategy applies to, for this room.
 *
 * A single physical façade can be split across several IfcWall segments
 * (structural columns, recesses, Revit export quirks) — only the segment
 * that happens to carry the window scores any solar gain, since gain is
 * proportional to window area. Filtering by each wall's OWN score would
 * silently drop sibling segments on the same orientation that have no
 * window of their own. Instead: qualify by ORIENTATION using the room's
 * best score on that orientation, then return every windowed facade on
 * any orientation that qualifies.
 */
function shadingFacades(strategyId, room) {
  const rule = SHADING_TARGETS[strategyId]
  const allFacades = room?.facades ?? []
  const windowed = allFacades.filter(f => f.window_ids?.length)
  if (!rule) return windowed

  const oriented = windowed.filter(f => rule.orients.includes(f.orientation))

  // Best solar_gain_score seen on each orientation, across ALL facade
  // segments of that orientation (not just the windowed one) — a
  // sun-exposed wall segment still indicates real solar exposure on that
  // façade even if the score happens to be attached to a different segment.
  const bestScoreByOrientation = {}
  for (const f of allFacades) {
    if (!rule.orients.includes(f.orientation)) continue
    const score = f.solar_gain_score ?? 0
    if (!(f.orientation in bestScoreByOrientation) || score > bestScoreByOrientation[f.orientation]) {
      bestScoreByOrientation[f.orientation] = score
    }
  }

  const highSolar = oriented.filter(f => (bestScoreByOrientation[f.orientation] ?? 0) > rule.minSolar)
  return highSolar.length ? highSolar : oriented
}

function degToCompass(deg) {
  const octants = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return octants[Math.round((deg % 360) / 45) % 8]
}

function angularDist(a, b) {
  const d = Math.abs(a - b) % 360
  return d > 180 ? 360 - d : d
}

/**
 * Group a room's windows by facade orientation, one color per orientation.
 * Windows of the same color are opened together. Groups are ordered by the
 * prevailing summer wind: the façade facing the wind comes first (inlet),
 * so the flow arrow runs windward → leeward.
 */
function ventilationGroups(room, windDeg) {
  const byOrient = {}
  for (const f of room?.facades ?? []) {
    if (!f.window_ids?.length) continue
    if (!byOrient[f.orientation]) {
      byOrient[f.orientation] = { ids: [], deg: f.orientation_degrees ?? 0 }
    }
    byOrient[f.orientation].ids.push(...f.window_ids)
  }
  let groups = Object.entries(byOrient).map(([orientation, g]) => ({
    orientation,
    orientationDeg: g.deg,
    globalIds: g.ids,
  }))
  if (windDeg != null && groups.length > 1) {
    groups = [...groups].sort(
      (a, b) => angularDist(a.orientationDeg, windDeg) - angularDist(b.orientationDeg, windDeg)
    )
  }
  return groups.map((g, i) => ({ ...g, hexColor: VENT_PALETTE[i % VENT_PALETTE.length] }))
}

/**
 * Full ventilation visual plan for a room.
 * If the room itself has windows on ≥2 façades → in-room cross-ventilation.
 * If it has only one windowed façade, look for a door-connected neighbouring
 * room with windows on a different façade — cross-ventilation through the
 * open connecting door.
 */
function buildVentPlan(room, allRooms, windDeg) {
  const own = ventilationGroups(room, windDeg)
  const base = {
    groups: own,
    crossRoom: false,
    partnerName: null,
    doorIds: room?.door_ids ?? [],
    roomGids: [room?.ifc_global_id].filter(Boolean),
  }
  if (own.length !== 1) return base

  const myDoors = new Set(room?.door_ids ?? [])
  if (!myDoors.size) return base

  let best = null
  for (const other of allRooms ?? []) {
    if (other.room_id === room.room_id || other.floor !== room.floor) continue
    const sharedDoors = (other.door_ids ?? []).filter(d => myDoors.has(d))
    if (!sharedDoors.length) continue
    const otherGroups = ventilationGroups(other, windDeg)
      .filter(g => g.orientation !== own[0].orientation)
    if (!otherGroups.length) continue
    // Prefer the most opposite facade (best pressure differential)
    const score = Math.abs(180 - angularDist(otherGroups[0].orientationDeg, own[0].orientationDeg))
    if (!best || score < best.score) {
      best = { other, group: otherGroups[0], sharedDoors, score }
    }
  }
  if (!best) return base

  let groups = [
    { ...own[0], roomGlobalId: room.ifc_global_id },
    { ...best.group, roomGlobalId: best.other.ifc_global_id },
  ]
  if (windDeg != null) {
    groups.sort((a, b) => angularDist(a.orientationDeg, windDeg) - angularDist(b.orientationDeg, windDeg))
  }
  groups = groups.map((g, i) => ({ ...g, hexColor: VENT_PALETTE[i % VENT_PALETTE.length] }))

  return {
    groups,
    crossRoom: true,
    partnerName: best.other.room_name || best.other.room_id,
    doorIds: best.sharedDoors,
    roomGids: [room.ifc_global_id, best.other.ifc_global_id].filter(Boolean),
  }
}

/**
 * Resolve which IFC GlobalIds to highlight for this strategy + room.
 * Returns { globalIds: string[], hexColor: string }
 */
function resolveHighlight(strategyId, room, roofIds = []) {
  const meta = STRATEGY_META[strategyId]
  if (!meta || !room?.facades) return null

  const { target, highlightColor } = meta
  const facades = room.facades ?? []

  if (target === 'wall') {
    const ids = facades.map(f => f.wall_id).filter(Boolean)
    return ids.length ? { globalIds: ids, hexColor: highlightColor } : null
  }
  if (target === 'window') {
    // Shading strategies: only windows on the facades the strategy targets
    const source = SHADING_TARGETS[strategyId] ? shadingFacades(strategyId, room) : facades
    const ids = source.flatMap(f => f.window_ids ?? []).filter(Boolean)
    return ids.length ? { globalIds: ids, hexColor: highlightColor } : null
  }
  if (target === 'all_windows') {
    const ids = facades.flatMap(f => f.window_ids ?? []).filter(Boolean)
    return ids.length ? { globalIds: ids, hexColor: highlightColor } : null
  }
  if (target === 'roof') {
    // Prefer actual roof elements (IfcRoof / roof slabs) from the backend;
    // fall back to the room's walls only when none were found in the IFC
    if (roofIds.length) return { globalIds: roofIds, hexColor: highlightColor }
    const ids = facades.map(f => f.wall_id).filter(Boolean)
    return ids.length ? { globalIds: ids, hexColor: highlightColor } : null
  }
  // door / building: no specific element to highlight
  return null
}

/**
 * Pick the wall layers from the most relevant facade for this strategy.
 * For wall strategies: first south/SE/SW facade, else first facade.
 * For roof strategies: first facade (will be overridden by sectionType).
 */
function pickFacadeLayers(strategyId, room) {
  const facades = room?.facades ?? []
  if (!facades.length) return { layers: [], uValue: null, shgc: null }

  const southFacing = facades.find(f =>
    ['S', 'SE', 'SW'].includes(f.orientation)
  )
  const facade = southFacing ?? facades[0]
  return {
    layers: facade.wall_layers ?? [],
    uValue: facade.wall_U_value ?? null,
    shgc: facade.SHGC ?? null,
    thickness: facade.wall_thickness_mm ?? 0,
  }
}

function approxUValueAfter(uBefore, sectionType) {
  if (!uBefore) return null
  const improvements = {
    wall_etics:    0.35,
    wall_internal: 0.40,
    roof_insulation: 0.30,
    roof_coating:  null,
    wall_pcm:      null,
    facade_paint:  null,
    glazing:       1.6,   // approximate target U for solar control glazing
    blinds:        null,
  }
  const target = improvements[sectionType]
  if (target === null || target === undefined) return null
  return Math.min(uBefore, target)
}


export default function RetrofitCard({ strategy, room, allRooms = [], roofIds = [], windDeg, onHighlight, onHighlightGroups, onHighlightClear }) {
  const [expanded, setExpanded] = useState(false)

  const meta = STRATEGY_META[strategy.strategy_id] ?? {}
  const name = meta.name ?? strategy.strategy_id
  const cat = meta.category ?? '?'
  const catBadge = CATEGORY_BADGE[cat]
  const highlight = resolveHighlight(strategy.strategy_id, room, roofIds)
  const { layers, uValue, shgc } = pickFacadeLayers(strategy.strategy_id, room)
  const uAfter = meta.sectionType ? approxUValueAfter(uValue, meta.sectionType) : null

  const ventPlan = cat === 'C' ? buildVentPlan(room, allRooms, windDeg) : null
  const ventGroups = ventPlan?.groups ?? []
  const schedule = SCHEDULES[strategy.strategy_id]
  const louverFacades = strategy.strategy_id === 'external_shading_louvers'
    ? shadingFacades(strategy.strategy_id, room)
    : []

  const handleToggle = () => {
    const next = !expanded
    setExpanded(next)
    if (next) {
      if (cat === 'C' && ventGroups.length && onHighlightGroups) {
        onHighlightGroups(ventGroups, {
          drawFlow: true,
          doorIds: ventPlan.doorIds,
          roomGlobalIds: ventPlan.roomGids,
          forceDoors: ventPlan.crossRoom,
        })
      } else if (highlight && onHighlight) {
        onHighlight(highlight.globalIds, highlight.hexColor, room?.ifc_global_id)
      }
    } else if (onHighlightClear) {
      onHighlightClear()
    }
  }

  return (
    <div className={`retrofit-card rank-${strategy.rank}`}>
      <div className="rc-header" onClick={handleToggle} role="button">
        <span className="rc-rank">{RANK_LABELS[strategy.rank] ?? `#${strategy.rank}`}</span>
        <span className="rc-name">{name}</span>
        <div className="rc-header-right">
          {catBadge && (
            <span
              className="rc-cat-badge"
              style={{ background: catBadge.color + '22', color: catBadge.color, borderColor: catBadge.color + '55' }}
            >
              {cat} · {catBadge.label}
            </span>
          )}
          <span className="rc-chevron">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      <div className="rc-metrics">
        <div className="metric">
          <span className="metric-val">−{strategy.delta_T_expected_C?.toFixed(1)}°C</span>
          <span className="metric-lbl">ΔT cooling</span>
        </div>
        <div className="metric">
          <span className="metric-val">
            {strategy.cost_eur_m2 === 0 ? 'Free' : `€${strategy.cost_eur_m2?.toFixed(0)}/m²`}
          </span>
          <span className="metric-lbl">Cost</span>
        </div>
        <div className="metric">
          <span className="metric-val">
            {strategy.carbon_kgCO2_m2 < 0
              ? `−${Math.abs(strategy.carbon_kgCO2_m2).toFixed(1)}`
              : strategy.carbon_kgCO2_m2?.toFixed(1)} kg
          </span>
          <span className="metric-lbl">CO₂/m²</span>
        </div>
      </div>

      {expanded && (
        <div className="rc-body">
          {/* 3D viewer hint */}
          {highlight && (
            <div className="rc-highlight-hint">
              <span
                className="rc-highlight-dot"
                style={{ background: highlight.hexColor }}
              />
              {meta.highlightLabel ?? 'Highlighted in 3D viewer'}
            </div>
          )}
          {cat === 'D' && (
            <div className="rc-flag-urban">
              Building-level intervention — not applicable to individual rooms.
            </div>
          )}
          {cat === 'C' && (
            <div className="rc-flag-operational">
              Behavioural protocol — no construction required.
            </div>
          )}

          {/* Category C: paired-window legend */}
          {cat === 'C' && ventGroups.length > 0 && (
            <div className="rc-vent-legend">
              {ventGroups.length >= 2 ? (
                <>
                  <p className="rc-vent-title">
                    Open windows of these façades <strong>at the same time</strong>:
                  </p>
                  {ventGroups.map((g, i) => (
                    <span key={g.orientation} className="rc-vent-item">
                      <span className="rc-vent-dot" style={{ background: g.hexColor }} />
                      {g.orientation} façade ({g.globalIds.length} window{g.globalIds.length > 1 ? 's' : ''})
                      {windDeg != null && (i === 0 ? ' — inlet (faces wind)' : ' — outlet')}
                    </span>
                  ))}
                  {ventPlan?.crossRoom && (
                    <p className="rc-vent-warn">
                      The second façade belongs to <strong>{ventPlan.partnerName}</strong> —
                      cross-ventilation works only with the connecting door kept open
                      (path shown through the door in 3D).
                    </p>
                  )}
                  {windDeg != null && (
                    <p className="rc-vent-wind">
                      Prevailing summer wind: from {degToCompass(windDeg)} ({Math.round(windDeg)}°)
                    </p>
                  )}
                </>
              ) : (
                <p className="rc-vent-warn">
                  Only one façade of this room has openings, and no door-connected
                  neighbouring room offers a second façade. True cross-ventilation is
                  not achievable here — the path shown runs to the nearest interior door.
                </p>
              )}
            </div>
          )}

          {/* Category C: protocol schedule table */}
          {schedule && (
            <table className="rc-schedule">
              <thead>
                <tr><th>Time</th><th>Action</th><th>Condition</th></tr>
              </thead>
              <tbody>
                {schedule.map((row, i) => (
                  <tr key={i}>
                    <td className="rc-sched-time">{row[0]}</td>
                    <td>{row[1]}</td>
                    <td className="rc-sched-cond">{row[2]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Louvers: blade direction sketch for the targeted façade */}
          {louverFacades.length > 0 && (
            <LouverSketch orientation={louverFacades[0].orientation} />
          )}

          {/* Category B: wall/roof section diagram */}
          {cat === 'B' && meta.sectionType && (
            <WallSection
              layers={layers}
              sectionType={meta.sectionType}
              uValueBefore={uValue}
              uValueAfter={uAfter}
              shgcBefore={shgc}
              shgcAfter={meta.sectionType === 'glazing' ? 0.35 : undefined}
            />
          )}

          {strategy.justification && (
            <p className="rc-justification">{strategy.justification}</p>
          )}
          {strategy.feasibility_note && (
            <div className="rc-feasibility">
              <span className="rc-label">Feasibility</span>
              <p>{strategy.feasibility_note}</p>
            </div>
          )}
          {strategy.literature_source && (
            <p className="rc-source">{strategy.literature_source}</p>
          )}

          {/* Shading alternates — same problem, different budget/operability trade-off */}
          {strategy.alternates?.length > 0 && (
            <div className="rc-alternates">
              <span className="rc-label">Alternative options</span>
              <p className="rc-alt-note">
                Same shading function, different cost and operability — choose based on budget:
              </p>
              {strategy.alternates.map(alt => (
                <div key={alt.strategy_id} className="rc-alt-item">
                  <span className="rc-alt-name">{alt.name}</span>
                  <span className="rc-alt-metrics">
                    €{alt.cost_eur_m2_min}–{alt.cost_eur_m2_max}/m² ·
                    {' '}−{alt.delta_T_min}–{alt.delta_T_max}°C
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
