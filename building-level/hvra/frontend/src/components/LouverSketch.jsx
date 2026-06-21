/**
 * LouverSketch — vertical section through a window showing louver blades,
 * the high summer sun being blocked and the low winter sun passing through.
 * Blade guidance depends on the façade orientation (Barcelona ~41.4°N):
 *   S        — horizontal blades; summer noon sun ~72° alt is easily blocked
 *   SE / SW  — blades tilted ~45° toward the low morning/afternoon sun
 *   E / W    — vertical fins work better than horizontal blades
 */

import React from 'react'

const GUIDANCE = {
  S:  { blade: 'Horizontal blades', note: 'Summer noon sun (~72°) blocked; low winter sun (~25°) and view kept.' },
  SE: { blade: 'Blades tilted ~45°', note: 'Tilt toward the morning sun; lower altitude than solar noon.' },
  SW: { blade: 'Blades tilted ~45°', note: 'Tilt toward the afternoon sun — the most punishing exposure in Barcelona.' },
  E:  { blade: 'Vertical fins', note: 'Sun is too low in the east for horizontal blades to help.' },
  W:  { blade: 'Vertical fins', note: 'Sun is too low in the west for horizontal blades to help.' },
}

export default function LouverSketch({ orientation = 'S' }) {
  const g = GUIDANCE[orientation] ?? GUIDANCE.S

  // Geometry: wall on right side, blades protruding to the left (exterior)
  const wallX = 200          // left face of wall
  const winTop = 52
  const winBot = 152
  const blades = [52, 72, 92, 112, 132, 152]

  return (
    <div className="louver-sketch">
      <p className="ls-title">Louver section — {orientation} façade · {g.blade}</p>
      <svg width="280" height="200" viewBox="0 0 280 200">
        {/* Wall above + below window */}
        <rect x={wallX} y={14} width={14} height={winTop - 14} fill="#c9c2b4" stroke="#777" strokeWidth="0.6" />
        <rect x={wallX} y={winBot} width={14} height={188 - winBot} fill="#c9c2b4" stroke="#777" strokeWidth="0.6" />
        {/* Glazing */}
        <line x1={wallX + 7} y1={winTop} x2={wallX + 7} y2={winBot} stroke="#7fb3d5" strokeWidth="3" />

        {/* Louver blades — angled ~30° down-out */}
        {blades.map((y, i) => (
          <line key={i}
            x1={wallX - 22} y1={y + 9}
            x2={wallX - 2}  y2={y}
            stroke="#555" strokeWidth="3" strokeLinecap="round"
          />
        ))}
        {/* Support */}
        <line x1={wallX - 12} y1={winTop - 4} x2={wallX - 12} y2={winBot + 6} stroke="#999" strokeWidth="1" />

        {/* Summer sun ray — steep, blocked at blades */}
        <line x1={120} y1={20} x2={wallX - 14} y2={96} stroke="#e67e22" strokeWidth="1.6" />
        <circle cx={114} cy={16} r="7" fill="#f1c40f" stroke="#e67e22" />
        <text x={104} y={38} fontSize="8" fill="#b9770e">Summer ~72°</text>
        {/* blocked marker */}
        <text x={wallX - 26} y={100} fontSize="9" fontWeight="700" fill="#c0392b">✕</text>

        {/* Winter sun ray — shallow, passes between blades into the room */}
        <line x1={20} y1={88} x2={wallX + 5} y2={122} stroke="#f39c12" strokeWidth="1.4" strokeDasharray="5 3" />
        <line x1={wallX + 5} y1={122} x2={262} y2={138} stroke="#f39c12" strokeWidth="1.4" strokeDasharray="5 3" />
        <circle cx={16} cy={84} r="6" fill="#fdebd0" stroke="#f39c12" />
        <text x={10} y={104} fontSize="8" fill="#b9770e">Winter ~25°</text>
        <text x={224} y={132} fontSize="7.5" fill="#7d6608">enters ✓</text>

        {/* EXT / INT labels */}
        <text x={150} y={186} fontSize="7.5" fill="#999" fontStyle="italic">EXTERIOR</text>
        <text x={232} y={186} fontSize="7.5" fill="#999" fontStyle="italic">INTERIOR</text>

        {/* Blade angle annotation */}
        <text x={wallX - 90} y={166} fontSize="8" fill="#444">blade tilt ≈ 30° down</text>
        <line x1={wallX - 36} y1={162} x2={wallX - 14} y2={142} stroke="#888" strokeWidth="0.6" />
      </svg>
      <p className="ls-note">{g.note}</p>
    </div>
  )
}
