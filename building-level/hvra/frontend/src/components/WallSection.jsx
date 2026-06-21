/**
 * WallSection — before/after wall section diagrams for Category B strategies.
 *
 * Style: architectural section — vertical layer strips (exterior → interior,
 * left → right), labels stacked on the left with leader lines pointing to
 * each layer, like a typical wall assembly detail.
 *
 * Props:
 *   layers        {Array<{name, thickness_mm}>}  existing wall layers exterior→interior
 *   sectionType   wall_etics | wall_internal | roof_insulation | roof_coating |
 *                 glazing | facade_paint | wall_pcm | blinds
 *   uValueBefore  number  W/m²K
 *   uValueAfter   number  W/m²K
 *   shgcBefore    number  (glazing only)
 *   shgcAfter     number  (glazing only)
 */

import React from 'react'
import './WallSection.css'

// ── Added layers per strategy (name, thickness) ───────────────────────────
const ADDED_LAYERS = {
  wall_etics:      [{ name: 'EPS insulation', thickness_mm: 80 }, { name: 'Render coat', thickness_mm: 10 }],
  wall_internal:   [{ name: 'PIR board', thickness_mm: 60 }, { name: 'Plasterboard', thickness_mm: 12 }],
  roof_insulation: [{ name: 'Rigid insulation', thickness_mm: 80 }, { name: 'Waterproof membrane', thickness_mm: 8 }],
  roof_coating:    [{ name: 'Cool coating', thickness_mm: 4 }],
  wall_pcm:        [{ name: 'PCM panel', thickness_mm: 25 }],
  facade_paint:    [{ name: 'Reflective paint', thickness_mm: 2 }],
  glazing:         [],
  blinds:          [{ name: 'Roller blind', thickness_mm: 30 }],
}

// Which side the added layers attach to (layers run exterior → interior)
const ADD_SIDE = {
  wall_etics:      'exterior',
  wall_internal:   'interior',
  roof_insulation: 'exterior',   // on top of roof = outer side
  roof_coating:    'exterior',
  wall_pcm:        'interior',
  facade_paint:    'exterior',
  glazing:         'replace',
  blinds:          'interior',
}

const ANNOTATIONS = {
  wall_etics:      'ETICS system added on the exterior face',
  wall_internal:   'Insulated board + plasterboard added on the interior face',
  roof_insulation: 'Rigid insulation + new membrane added on top of roof slab',
  roof_coating:    'Reflective cool coating applied to roof surface',
  wall_pcm:        'PCM panel integrated on the interior side',
  facade_paint:    'Reflective paint applied to exterior surface',
  glazing:         'Glass replaced with solar-control low-e unit',
  blinds:          'Roller blind installed at window head',
}

// ── Fill style per material ────────────────────────────────────────────────
function fillFor(name, idPrefix) {
  const n = name.toLowerCase()
  if (/(wool|eps|pir|insul|pcm)/.test(n)) return `url(#${idPrefix}-insul)`
  if (/brick/.test(n))                    return `url(#${idPrefix}-brick)`
  if (/air/.test(n))                      return '#f4fafd'
  if (/membrane/.test(n))                 return '#6ee7b7'
  if (/(coating|paint|glass|glazing)/.test(n)) return '#bfdbfe'
  if (/blind/.test(n))                    return '#d1d5db'
  if (/render/.test(n))                   return '#d8d3c8'
  if (/(plaster|board)/.test(n))          return '#efece4'
  return '#e5e7eb'
}

// ── Geometry constants ─────────────────────────────────────────────────────
const SVG_W = 290
const SVG_H = 240
const STRIPS_X = 150      // where layer strips start
const STRIPS_MAX_W = 120
const STRIP_TOP = 34
const STRIP_H = 150

function SectionDiagram({ title, layers, uValue, uColor, idPrefix, shgc }) {
  const totalMm = layers.reduce((s, l) => s + l.thickness_mm, 0)
  const scale = STRIPS_MAX_W / Math.max(totalMm, 1)

  let x = STRIPS_X
  const strips = layers.map(l => {
    const w = Math.max(l.thickness_mm * scale, 5)
    const s = { x, w, ...l }
    x += w
    return s
  })
  const stripsEnd = x

  // Label rows spread within the strip height
  const n = strips.length
  const labelYs = strips.map((_, i) =>
    STRIP_TOP + 14 + (n > 1 ? i * ((STRIP_H - 28) / (n - 1)) : (STRIP_H - 28) / 2)
  )

  return (
    <div className="ws-panel">
      <p className="ws-label">{title}</p>
      <svg width={SVG_W} height={SVG_H} viewBox={`0 0 ${SVG_W} ${SVG_H}`}>
        <defs>
          {/* batt insulation: zigzag */}
          <pattern id={`${idPrefix}-insul`} width="8" height="8" patternUnits="userSpaceOnUse">
            <rect width="8" height="8" fill="#f9efc7" />
            <path d="M0 8 L4 0 L8 8" stroke="#c9a94e" strokeWidth="0.8" fill="none" />
          </pattern>
          {/* brick: diagonal hatch */}
          <pattern id={`${idPrefix}-brick`} width="7" height="7" patternUnits="userSpaceOnUse">
            <rect width="7" height="7" fill="#dca08a" />
            <path d="M0 7 L7 0" stroke="#a35d44" strokeWidth="0.8" />
          </pattern>
        </defs>

        {/* U-value / SHGC annotation */}
        {uValue != null && (
          <text x={STRIPS_X + STRIPS_MAX_W / 2} y={16} textAnchor="middle"
                fontSize="9" fontWeight="700" fill={uColor}>
            U = {uValue.toFixed(2)} W/m²K
          </text>
        )}
        {shgc != null && (
          <text x={STRIPS_X + STRIPS_MAX_W / 2} y={uValue != null ? 28 : 16}
                textAnchor="middle" fontSize="8" fill="#1d4ed8">
            SHGC = {shgc.toFixed(2)}
          </text>
        )}

        {/* EXT / INT markers */}
        <text x={STRIPS_X - 4} y={STRIP_TOP + STRIP_H + 12} textAnchor="end"
              fontSize="7" fill="#999" fontStyle="italic">EXT</text>
        <text x={stripsEnd + 4} y={STRIP_TOP + STRIP_H + 12} fontSize="7"
              fill="#999" fontStyle="italic">INT</text>

        {/* Layer strips */}
        {strips.map((s, i) => (
          <rect key={i}
            x={s.x} y={STRIP_TOP} width={s.w} height={STRIP_H}
            fill={fillFor(s.name, idPrefix)}
            stroke={s.added ? '#d97706' : '#777'}
            strokeWidth={s.added ? 1.6 : 0.6}
            strokeDasharray={s.added ? '4 2' : 'none'}
          />
        ))}

        {/* Labels + leader lines */}
        {strips.map((s, i) => {
          const y = labelYs[i]
          const cx = s.x + s.w / 2
          return (
            <g key={i}>
              <text x={4} y={y + 3} fontSize="7.5"
                    fontWeight={s.added ? 700 : 400}
                    fill={s.added ? '#b45309' : '#444'}>
                {s.name} — {Math.round(s.thickness_mm)}mm
              </text>
              <line x1={STRIPS_X - 46} y1={y} x2={cx} y2={y}
                    stroke={s.added ? '#d97706' : '#999'} strokeWidth="0.7" />
              <circle cx={cx} cy={y} r="1.4" fill={s.added ? '#d97706' : '#999'} />
            </g>
          )
        })}

        {/* Total thickness dimension line */}
        <line x1={STRIPS_X} y1={STRIP_TOP + STRIP_H + 20} x2={stripsEnd} y2={STRIP_TOP + STRIP_H + 20}
              stroke="#666" strokeWidth="0.7" />
        <line x1={STRIPS_X} y1={STRIP_TOP + STRIP_H + 16} x2={STRIPS_X} y2={STRIP_TOP + STRIP_H + 24}
              stroke="#666" strokeWidth="0.7" />
        <line x1={stripsEnd} y1={STRIP_TOP + STRIP_H + 16} x2={stripsEnd} y2={STRIP_TOP + STRIP_H + 24}
              stroke="#666" strokeWidth="0.7" />
        <text x={(STRIPS_X + stripsEnd) / 2} y={STRIP_TOP + STRIP_H + 34}
              textAnchor="middle" fontSize="8" fill="#555">
          {Math.round(totalMm)} mm
        </text>
      </svg>
    </div>
  )
}

export default function WallSection({ layers = [], sectionType, uValueBefore, uValueAfter, shgcBefore, shgcAfter }) {
  const isGlazing = sectionType === 'glazing'

  const existing = isGlazing
    ? [{ name: 'Single glazing', thickness_mm: 6 }]
    : layers.length > 0
      ? layers.map(l => ({ ...l }))
      : [{ name: 'Existing wall', thickness_mm: 300 }]

  const added = (ADDED_LAYERS[sectionType] ?? []).map(l => ({ ...l, added: true }))
  const side = ADD_SIDE[sectionType] ?? 'interior'

  let after
  if (side === 'replace' && isGlazing) {
    after = [{ name: 'Solar control glazing', thickness_mm: 24, added: true }]
  } else if (side === 'exterior') {
    after = [...added, ...existing]
  } else {
    after = [...existing, ...added]
  }

  return (
    <div className="wall-section">
      <div className="ws-panels">
        <SectionDiagram
          title="Before"
          layers={existing}
          uValue={uValueBefore}
          uColor="#c0392b"
          idPrefix={`ws-b-${sectionType}`}
          shgc={isGlazing ? shgcBefore : null}
        />
        <div className="ws-arrow">→</div>
        <SectionDiagram
          title="After"
          layers={after}
          uValue={uValueAfter}
          uColor="#27ae60"
          idPrefix={`ws-a-${sectionType}`}
          shgc={isGlazing ? (shgcAfter ?? 0.35) : null}
        />
      </div>
      {ANNOTATIONS[sectionType] && (
        <p className="ws-annotation">{ANNOTATIONS[sectionType]}</p>
      )}
    </div>
  )
}
