import React, { useState, useEffect } from 'react'
import RetrofitCard from './RetrofitCard'
import OverheatingTable from './OverheatingTable'
import './RoomPanel.css'

const T_OP_THRESHOLD = { 'under-65': 28.0, '65-75': 26.0, '75+': 25.0 }

const RISK_CLASS = {
  Critical: 'badge--critical',
  High:     'badge--high',
  Moderate: 'badge--moderate',
  Safe:     'badge--safe',
}

// [cross-vent] human labels for the cross-ventilation classifier (Gaelle's
// analysis/cross_ventilation.py) — keep in sync with her classification keys.
const CROSS_VENT_LABEL = {
  strong_cross_ventilation:   'Strong cross-ventilation',
  moderate_cross_ventilation: 'Moderate cross-ventilation',
  weak_adjacent_ventilation:  'Weak adjacent ventilation',
  single_sided:               'Single-sided only',
  indirect_possible:          'Indirect (via connected room)',
  poor:                       'Poor / none',
  unknown:                    'Unknown',
}

export default function RoomPanel({ room, allRooms, beforeAfter, roofIds, windDeg, crossVentSpaces = [], jobId, onInspectRoomToggle, onStrategyHighlight, onStrategyHighlightGroups, onHighlightClear, onOpenRender }) {
  const ts      = room.thermal_scores ?? {}
  const vent    = room.ventilation    ?? {}
  const env     = room.envelope       ?? {}
  const occ     = room.occupant       ?? {}
  const ai      = room.ai_outputs     ?? {}
  const shortlist = ai.shortlist      ?? []

  const primaryOrientation = room.facades?.[0]?.orientation ?? '—'

  // [cross-vent] this room's ventilation diagnosis, matched by IfcSpace id.
  const cv = crossVentSpaces.find((s) => s.space_id === room.ifc_global_id) ?? null

  // Room-inspect highlight toggle — resets to off whenever the inspected
  // room changes, and clears the 3D highlight on unmount/room switch so it
  // never lingers on the wrong room.
  const [inspectOn, setInspectOn] = useState(false)
  useEffect(() => {
    setInspectOn(false)
    return () => onInspectRoomToggle?.(room.ifc_global_id, false)
  }, [room.ifc_global_id])

  const toggleInspect = () => {
    const next = !inspectOn
    setInspectOn(next)
    onInspectRoomToggle?.(room.ifc_global_id, next, ts.risk_level)
  }

  return (
    <div className="room-panel">
      {/* ── Identity ── */}
      <div className="rp-identity">
        <div className="rp-name-row">
          <h2 className="rp-name">{room.room_name}</h2>
          <span className={`risk-badge ${RISK_CLASS[ts.risk_level] ?? ''}`}>
            {ts.risk_level ?? '—'}
          </span>
        </div>
        <div className="rp-meta">
          Floor {room.floor ?? '—'} · {room.room_type ?? '—'} ·{' '}
          {room.area_m2?.toFixed(0)} m² · {primaryOrientation} facade ·{' '}
          Score {ts.composite_score?.toFixed(2) ?? '—'}
        </div>
        <label className="rp-inspect-toggle">
          <input type="checkbox" checked={inspectOn} onChange={toggleInspect} />
          Highlight this room in 3D
        </label>
      </div>

      {/* ── Diagnosis ── */}
      {ai.diagnosis && (
        <div className="rp-section">
          <h3 className="rp-section-title">Diagnosis</h3>
          <p className="rp-diagnosis">{ai.diagnosis}</p>
          {ai.key_factors?.length > 0 && (
            <div className="rp-factors">
              {ai.key_factors.map((f, i) => (
                <span key={i} className="factor-chip">{f}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Score breakdown ── */}
      <div className="rp-section">
        <h3 className="rp-section-title">Risk breakdown</h3>
        <div className="score-grid">
          <ScoreRow label="Solar gain"    value={ts.solar_gain_score} />
          <ScoreRow label="Ventilation"   value={ts.ventilation_score} />
          <ScoreRow label="Envelope"      value={ts.envelope_score} />
          <ScoreRow label="Composite"     value={ts.composite_score} highlight />
          <BoolRow  label="Nocturnal recovery"
                    pass={!ts.nocturnal_recovery_fail}
                    passLabel="OK"
                    failLabel="Fail" />
          <InfoRow  label="Overheating hours" value={`${ts.overheating_hours ?? 0} h`} />
          <InfoRow  label="Age-weighted OH"   value={`${ts.age_weighted_overheating?.toFixed(0) ?? 0} h`} />
        </div>
        <OverheatingTable
          events={ts.overheating_events}
          threshold={T_OP_THRESHOLD[occ.age_bracket]}
        />
      </div>

      {/* ── Occupant ── */}
      <div className="rp-section">
        <h3 className="rp-section-title">Occupant profile</h3>
        <div className="score-grid">
          <InfoRow label="Age bracket"        value={occ.age_bracket ?? '—'} />
          <BoolRow label="AC access"          pass={!!occ.ac_access} passLabel="Yes" failLabel="No" />
          <InfoRow label="Income"             value={occ.income_category ?? '—'} />
          <BoolRow label="Mobility limited"   pass={false} passLabel="No" failLabel="Yes"
                   override={occ.mobility_limited ? 'fail' : 'pass'} />
        </div>
      </div>

      {/* ── Ventilation ── */}
      <div className="rp-section">
        <h3 className="rp-section-title">Ventilation</h3>
        <div className="score-grid">
          <InfoRow label="Cross-ventilation"
                   value={cv ? CROSS_VENT_LABEL[cv.classification] ?? cv.classification : '—'} />
          <InfoRow label="Confidence"
                   value={cv ? `${Math.round((cv.confidence ?? 0) * 100)}%` : '—'} />
          <InfoRow label="Exterior facades"  value={vent.exterior_facades ?? 0} />
        </div>
        {cv?.recommendations?.length > 0 && (
          <ul className="rp-vent-recs">
            {cv.recommendations.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        )}
        {cv?.assumptions?.length > 0 && (
          <p className="rp-vent-assumptions">{cv.assumptions.join(' ')}</p>
        )}
      </div>

      {/* ── Envelope ── */}
      <div className="rp-section">
        <h3 className="rp-section-title">Envelope</h3>
        <div className="score-grid">
          <InfoRow label="Wall U-value"
                   value={env.dominant_wall_U_value != null
                     ? `${env.dominant_wall_U_value.toFixed(2)} W/m²K`
                     : '—'} />
          <InfoRow label="Roof U-value"
                   value={env.roof_U_value != null
                     ? `${env.roof_U_value.toFixed(2)} W/m²K`
                     : '—'} />
          <BoolRow label="Roof exposed" pass={!!env.roof_exposed} passLabel="Yes" failLabel="No" />
        </div>
      </div>

      {/* ── Retrofit shortlist ── */}
      <div className="rp-section">
        <h3 className="rp-section-title">
          {beforeAfter === 'after' ? 'Proposed retrofits (after)' : 'Top 3 retrofit strategies'}
        </h3>
        {shortlist.length === 0 ? (
          <p className="rp-empty">
            No shortlist available — ensure ANTHROPIC_API_KEY is set and the pipeline completed.
          </p>
        ) : (
          shortlist.map(s => (
            <RetrofitCard
              key={s.rank}
              strategy={s}
              room={room}
              allRooms={allRooms}
              roofIds={roofIds}
              windDeg={windDeg}
              crossVent={cv}
              jobId={jobId}
              onHighlight={onStrategyHighlight}
              onHighlightGroups={onStrategyHighlightGroups}
              onHighlightClear={onHighlightClear}
              onOpenRender={onOpenRender}
            />
          ))
        )}
      </div>
    </div>
  )
}

function ScoreRow({ label, value, highlight }) {
  if (value == null) return null
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  const level = value > 0.7 ? 'bar--high' : value > 0.45 ? 'bar--med' : 'bar--low'
  return (
    <div className={`score-row ${highlight ? 'score-row--highlight' : ''}`}>
      <span className="score-label">{label}</span>
      <div className="score-bar-wrap">
        <div className={`score-bar ${level}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="score-num">{value.toFixed(2)}</span>
    </div>
  )
}

function BoolRow({ label, pass, passLabel, failLabel, override }) {
  const isPass = override === 'pass' ? true : override === 'fail' ? false : pass
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <span className={`bool-badge ${isPass ? 'bool--pass' : 'bool--fail'}`}>
        {isPass ? passLabel : failLabel}
      </span>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <span className="info-val">{value}</span>
    </div>
  )
}
