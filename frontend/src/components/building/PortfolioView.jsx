import React, { useMemo } from 'react'
import './PortfolioView.css'

const RISK_BADGE = {
  Critical: 'pb--critical',
  High:     'pb--high',
  Moderate: 'pb--moderate',
  Safe:     'pb--safe',
}

export default function PortfolioView({ rooms, selectedRoom, onSelectRoom }) {
  // Sort rooms by composite_score descending (highest risk first)
  const sorted = useMemo(
    () => [...rooms].sort((a, b) =>
      (b.composite_score ?? 0) - (a.composite_score ?? 0)
    ),
    [rooms],
  )

  if (sorted.length === 0) {
    return <p className="pv-empty">No rooms found in this building.</p>
  }

  // Hide the orientation column when the IFC had no exterior facade data
  const hasOrientation = sorted.some(r => r.facades?.length > 0)

  return (
    <div className="portfolio-view">
      <table className="pv-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Room</th>
            <th>Fl.</th>
            {hasOrientation && <th>Ori.</th>}
            <th>Risk</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((room, idx) => {
            const ts          = room.thermal_scores ?? {}
            const orientation = room.facades?.[0]?.orientation ?? '—'
            const isSelected  = selectedRoom?.room_id === room.room_id

            return (
              <tr
                key={room.room_id}
                className={`pv-row ${isSelected ? 'pv-row--selected' : ''}`}
                onClick={() => onSelectRoom(room)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && onSelectRoom(room)}
              >
                <td className="pv-rank">{idx + 1}</td>
                <td className="pv-name">
                  <span className="pv-room-name">{room.room_name}</span>
                  <span className="pv-room-type">{room.room_type}</span>
                </td>
                <td className="pv-center">{room.floor ?? '—'}</td>
                {hasOrientation && <td className="pv-center">{orientation}</td>}
                <td>
                  <span className={`p-badge ${RISK_BADGE[ts.risk_level] ?? ''}`}>
                    {ts.risk_level ?? '—'}
                  </span>
                </td>
                <td className="pv-score">
                  <span className="pv-score-val">
                    {room.composite_score != null ? room.composite_score.toFixed(2) : '—'}
                  </span>
                  {room.composite_score != null && (
                    <div className="pv-score-bar-wrap">
                      <div
                        className={`pv-score-bar ${riskClass(room.composite_score)}`}
                        style={{ width: `${Math.round(room.composite_score * 100)}%` }}
                      />
                    </div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function riskClass(score) {
  if (score > 0.7) return 'bar--critical'
  if (score > 0.5) return 'bar--high'
  if (score > 0.3) return 'bar--mod'
  return 'bar--safe'
}
