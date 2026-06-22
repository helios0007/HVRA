import React, { useMemo } from 'react'
import './ComfortIndicator.css'

const RISK_WEIGHT = { critical: 1.0, high: 0.7, moderate: 0.4, safe: 0.0 }

// Ring colour follows the same risk palette used everywhere else in the
// viewer (risk legend, 3D highlight colours) — red→orange→yellow→green.
const LEVEL_COLOR = {
  critical: '#e74c3c',
  high:     '#e67e22',
  moderate: '#f1c40f',
  safe:     '#2ecc71',
  improved: '#2ecc71',
}

function levelFromScore(score) {
  if (score < 0.35) return 'critical'
  if (score < 0.55) return 'high'
  if (score < 0.8) return 'moderate'
  return 'safe'
}

/**
 * Human comfort/vulnerability indicator — a circular progress ring with a
 * person icon at its centre, matching the reference design. Sits at the
 * right edge of the viewer.
 *
 * - No room selected → shows the building-wide aggregate comfort.
 * - A room selected → shows THAT room's own risk (bad/red-orange by
 *   default, since selecting a room is "inspecting its problem").
 * - Once that specific room has a successful AI render (roomRendered),
 *   flips to green/"improved" for that room — not the whole building.
 */
export default function ComfortIndicator({ rooms, selectedRoom, roomRendered }) {
  const { comfortScore, level } = useMemo(() => {
    if (selectedRoom) {
      const ts = selectedRoom.thermal_scores ?? {}
      const lvl = (ts.risk_level ?? 'safe').toLowerCase()
      const score = 1 - (RISK_WEIGHT[lvl] ?? 0)
      return { comfortScore: score, level: lvl in RISK_WEIGHT ? lvl : 'safe' }
    }
    if (!rooms?.length) return { comfortScore: 1, level: 'safe' }
    const c = { critical: 0, high: 0, moderate: 0, safe: 0 }
    for (const r of rooms) {
      const lvl = (r.thermal_scores?.risk_level ?? 'safe').toLowerCase()
      if (c[lvl] != null) c[lvl]++
    }
    const total = rooms.length
    const weighted = Object.entries(c).reduce(
      (sum, [lvl, n]) => sum + n * (RISK_WEIGHT[lvl] ?? 0), 0
    )
    const score = 1 - weighted / total
    return { comfortScore: score, level: levelFromScore(score) }
  }, [rooms, selectedRoom])

  const improved = selectedRoom ? roomRendered : false
  const displayLevel = improved ? 'improved' : level
  const displayScore = improved ? 1 : comfortScore
  const color = LEVEL_COLOR[displayLevel]

  // Ring geometry: a circle with a small gap at the top (like the
  // reference image), filled proportionally to displayScore clockwise.
  const radius = 42
  const circumference = 2 * Math.PI * radius
  const gapDeg = 18                                  // gap at the top, in degrees
  const arcDeg = 360 - gapDeg
  const arcLen = circumference * (arcDeg / 360)
  const filledLen = arcLen * displayScore
  const trackDash = `${arcLen} ${circumference}`
  const fillDash = `${filledLen} ${circumference}`
  const rotation = -90 - gapDeg / 2                  // start just after the top gap

  const label = selectedRoom
    ? (improved ? 'Improved' : selectedRoom.room_name)
    : 'Building'

  return (
    <div className="comfort-ring" title="Human comfort & vulnerability">
      <svg width="92" height="92" viewBox="0 0 100 100" className="comfort-ring-svg">
        {/* Background track */}
        <circle
          cx="50" cy="50" r={radius}
          fill="none" stroke="#e3e3e3" strokeWidth="7"
          strokeDasharray={trackDash}
          strokeLinecap="round"
          transform={`rotate(${rotation} 50 50)`}
        />
        {/* Filled progress arc */}
        <circle
          cx="50" cy="50" r={radius}
          fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={fillDash}
          strokeLinecap="round"
          transform={`rotate(${rotation} 50 50)`}
          className="comfort-ring-fill"
        />
        {/* Person icon — simple shapes (head, torso, arms, legs), tinted
            to match the ring colour. Built from primitives rather than a
            single freehand path so the silhouette stays clean and correct. */}
        <g transform="translate(50 50)" fill={color}>
          {/* Head */}
          <circle cx="0" cy="-14" r="6.5" />
          {/* Torso */}
          <rect x="-7" y="-6" width="14" height="17" rx="5" />
          {/* Arms */}
          <rect x="-12" y="-5" width="4.5" height="13" rx="2.2" />
          <rect x="7.5" y="-5" width="4.5" height="13" rx="2.2" />
          {/* Legs */}
          <rect x="-6" y="9" width="4.5" height="15" rx="2.2" />
          <rect x="1.5" y="9" width="4.5" height="15" rx="2.2" />
        </g>
      </svg>
      <div className="comfort-ring-text">
        <span className="comfort-ring-label">{label}</span>
      </div>
    </div>
  )
}
