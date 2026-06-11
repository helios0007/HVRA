// The climatic section — a minimal data drawing.
// Every line is computed: building chords from real footprints, shadows from
// the real solar position, and a surface-temperature curve from Landsat LST
// bent by the selected interventions. Proposed design elements (trees, sails,
// green roofs, de-paved surfaces) are drawn as section symbols at true scale —
// proposals in blue/green, existing fabric in ink.

import { forwardRef } from 'react';
import { getHVIColorHex } from '../utils/hviColors';

const INK = '#1a1a1a';
const FAINT = '#999';
const RED = '#d43d2a';
const BLUE = '#2563eb';
const GREEN = '#16a34a';

function tempPath(curve, xScale, tToY, x0) {
  let d = '';
  let pen = false;
  for (const pt of curve) {
    if (!pt) {
      pen = false;
      continue;
    }
    const cmd = pen ? 'L' : 'M';
    d += `${cmd}${(x0 + pt.x * xScale).toFixed(1)},${tToY(pt.t).toFixed(1)} `;
    pen = true;
  }
  return d;
}

// ---- design element symbols (true scale: mY = px per metre) ----

// Section tree: trunk + branching + clustered crown
function Tree({ x, groundY, mY, crownH, crownR }) {
  const ty = groundY - crownH * mY; // crown base
  const r = crownR * mY;
  const cy = ty - r * 0.55;
  return (
    <g stroke={BLUE} fill="none" strokeWidth="1.1">
      <line x1={x} y1={groundY} x2={x} y2={ty + r * 0.2} strokeWidth="1.6" />
      <line x1={x} y1={ty + r * 0.4} x2={x - r * 0.45} y2={ty - r * 0.15} />
      <line x1={x} y1={ty + r * 0.3} x2={x + r * 0.5} y2={ty - r * 0.1} />
      <g fill="#2563eb14">
        <circle cx={x - r * 0.45} cy={cy} r={r * 0.62} />
        <circle cx={x + r * 0.45} cy={cy + r * 0.08} r={r * 0.62} />
        <circle cx={x} cy={cy - r * 0.42} r={r * 0.66} />
      </g>
    </g>
  );
}

// Tensile shade sail: two posts + catenary canvas
function ShadeSail({ x0, x1, groundY, mY, h }) {
  const y = groundY - h * mY;
  const midX = (x0 + x1) / 2;
  return (
    <g stroke={BLUE} fill="none" strokeWidth="1.2">
      <line x1={x0} y1={groundY} x2={x0} y2={y} />
      <line x1={x1} y1={groundY} x2={x1} y2={y} />
      <path d={`M${x0},${y} Q${midX},${y + 5} ${x1},${y}`} strokeWidth="1.8" />
      <path d={`M${x0},${y} Q${midX},${y + 5} ${x1},${y} L${x1},${y + 2.5} Q${midX},${y + 7.5} ${x0},${y + 2.5} Z`}
        fill="#2563eb18" stroke="none" />
    </g>
  );
}

// Scale figure, 1.7 m
function Person({ x, groundY, mY }) {
  const h = 1.7 * mY;
  const headR = h * 0.14;
  const y0 = groundY - h;
  return (
    <g stroke={INK} fill="none" strokeWidth="1">
      <circle cx={x} cy={y0 + headR} r={headR} />
      <line x1={x} y1={y0 + headR * 2} x2={x} y2={groundY - h * 0.32} />
      <line x1={x} y1={groundY - h * 0.32} x2={x - h * 0.16} y2={groundY} />
      <line x1={x} y1={groundY - h * 0.32} x2={x + h * 0.16} y2={groundY} />
      <line x1={x - h * 0.18} y1={y0 + h * 0.42} x2={x + h * 0.18} y2={y0 + h * 0.38} />
    </g>
  );
}

// Vegetation tufts (green roof / de-paved planting)
function Tufts({ x0, x1, y, color, step = 8, size = 4 }) {
  const items = [];
  for (let x = x0 + step / 2; x < x1; x += step) {
    items.push(
      <path
        key={x}
        d={`M${x - size / 2},${y} Q${x - size / 4},${y - size} ${x},${y} M${x},${y} L${x},${y - size * 1.2} M${x},${y} Q${x + size / 4},${y - size} ${x + size / 2},${y}`}
        stroke={color}
        strokeWidth="1"
        fill="none"
      />
    );
  }
  return <g>{items}</g>;
}

// Reflection arrows off a cool roof (albedo, drawn physics)
function ReflectArrows({ x0, x1, y }) {
  const items = [];
  const n = Math.max(2, Math.floor((x1 - x0) / 36));
  for (let i = 1; i <= n; i++) {
    const x = x0 + ((x1 - x0) * i) / (n + 1);
    items.push(
      <g key={i} stroke={BLUE} strokeWidth="1" fill="none">
        <line x1={x} y1={y - 3} x2={x + 5} y2={y - 13} />
        <polyline points={`${x + 1.5},${y - 11.5} ${x + 5},${y - 13} ${x + 4.5},${y - 9}`} />
      </g>
    );
  }
  return <g>{items}</g>;
}

// Climbing vegetation on a facade
function FacadeVine({ x, y0, y1 }) {
  const h = y1 - y0;
  const n = Math.max(3, Math.floor(h / 14));
  let d = `M${x},${y1}`;
  for (let i = 1; i <= n; i++) {
    const y = y1 - (h * i) / n;
    const dx = i % 2 ? 4 : -4;
    d += ` Q${x + dx},${y + h / n / 2} ${x},${y}`;
  }
  return (
    <g stroke={GREEN} fill="none" strokeWidth="1.2">
      <path d={d} />
      {[...Array(n)].map((_, i) => {
        const y = y1 - (h * (i + 0.5)) / n;
        const dx = i % 2 ? 3.5 : -3.5;
        return <circle key={i} cx={x + dx} cy={y} r="1.6" fill="#16a34a22" />;
      })}
    </g>
  );
}

const ClimaticSection = forwardRef(function ClimaticSection({ section, activeNames = [] }, ref) {
  if (!section) {
    return <div className="diagram-empty">No buildings intersect this cut — move the position slider.</div>;
  }

  const W = 1060;
  const PAD = 50;
  const drawW = W - PAD * 2;
  const xScale = drawW / section.length;

  // True proportions unless the cut is very long relative to building heights
  const vx = section.length / section.maxHeight > 18 ? 2 : 1;
  const mY = xScale * vx; // px per metre, vertical

  const groundY = 30 + section.maxHeight * mY + 56; // sun band above
  const sunBandTop = 16;

  // Temperature strip below ground
  const stripTop = groundY + 40;
  const stripH = 78;
  const tMax = section.zoneLstC + 6;
  const tMin = Math.min(28, section.zoneLstC - 16);
  const tToY = (t) => stripTop + stripH - ((t - tMin) / (tMax - tMin)) * stripH;
  const H = stripTop + stripH + 46;

  const X = (m) => PAD + m * xScale;
  const sun = section.sun;
  const surface = section.surface || {};

  // Sun glyph position: on the side the sun comes from
  const sunX = sun.shadowDir > 0 ? PAD + 30 : W - PAD - 30;
  const sunY = sunBandTop + 14;
  const tallest = section.profiles.reduce((a, b) => (b.height > a.height ? b : a));
  const rayTargetX = X(sun.shadowDir > 0 ? tallest.x1 : tallest.x0);
  const rayTargetY = groundY - tallest.height * mY;

  const hasGreenRoof = section.roofTags.some((t) => t.id === 'green_roof');
  const hasCoolRoof = section.roofTags.some((t) => t.id === 'cool_roof');

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      {/* ---- sun + ray (computed) ---- */}
      <g stroke={INK} fill="none" strokeWidth="1">
        <circle cx={sunX} cy={sunY} r="7" fill="#fff" />
        {[...Array(8)].map((_, i) => {
          const a = (i * Math.PI) / 4;
          return (
            <line
              key={i}
              x1={sunX + Math.cos(a) * 10}
              y1={sunY + Math.sin(a) * 10}
              x2={sunX + Math.cos(a) * 13}
              y2={sunY + Math.sin(a) * 13}
            />
          );
        })}
        {!sun.weak && (
          <line x1={sunX} y1={sunY} x2={rayTargetX} y2={rayTargetY} strokeDasharray="4 4" stroke={FAINT} />
        )}
      </g>
      <text x={sunX + (sun.shadowDir > 0 ? 18 : -18)} y={sunY + 4} fontSize="10" fill={INK}
        textAnchor={sun.shadowDir > 0 ? 'start' : 'end'}>
        21 Jun · {sun.solarHour}:00 solar · alt {sun.altitudeDeg.toFixed(0)}°
        {sun.weak ? ' (⊥ to cut)' : ` · in-plane ${sun.inPlaneAltDeg.toFixed(0)}°`}
      </text>

      {/* ---- shadows (actually cast) ---- */}
      {section.shadows.map((s, i) => (
        <polygon
          key={i}
          points={`${X(s.from)},${groundY - s.height * mY} ${X(s.from)},${groundY} ${X(sun.shadowDir > 0 ? s.x1 : s.x0)},${groundY}`}
          fill="#000"
          opacity="0.08"
        />
      ))}

      {/* ---- ground surface treatment in street gaps ---- */}
      {section.gaps.map((g, i) => {
        const x0 = X(g.x0);
        const x1 = X(g.x1);
        if (surface.depave) {
          return (
            <g key={i}>
              <rect x={x0} y={groundY} width={x1 - x0} height={5} fill="#16a34a18" />
              <Tufts x0={x0} x1={x1} y={groundY} color={GREEN} step={10} size={4.5} />
            </g>
          );
        }
        if (surface.coolPavement) {
          return (
            <g key={i}>
              <rect x={x0} y={groundY} width={x1 - x0} height={4} fill="#2563eb1c" />
              <ReflectArrows x0={x0} x1={x1} y={groundY} />
            </g>
          );
        }
        // existing asphalt
        return <rect key={i} x={x0} y={groundY} width={x1 - x0} height={4} fill="#1a1a1a" opacity="0.35" />;
      })}

      {/* ---- proposed shade sails ---- */}
      {section.shadePatches.map((s, i) => (
        <ShadeSail key={i} x0={X(s.x0)} x1={X(s.x1)} groundY={groundY} mY={mY} h={s.h} />
      ))}

      {/* ---- proposed trees ---- */}
      {section.trees.map((t, i) => (
        <Tree key={i} x={X(t.x)} groundY={groundY} mY={mY} crownH={t.crownH} crownR={t.crownR} />
      ))}

      {/* ---- building profiles + roof/facade design elements ---- */}
      {section.profiles.map((p, i) => {
        const x = X(p.x0);
        const w = (p.x1 - p.x0) * xScale;
        const h = p.height * mY;
        const roofY = groundY - h;
        const sunnyX = sun.shadowDir > 0 ? x + w : x; // facade facing the sun
        return (
          <g key={i}>
            <rect x={x} y={roofY} width={w} height={h} fill="#fff" stroke={INK} strokeWidth="1.4" />

            {/* envelope retrofit: insulation as inner dashed offset */}
            {section.envelopeRetrofit && (
              <rect x={x + 3} y={roofY + 3} width={Math.max(w - 6, 2)} height={h - 3}
                fill="none" stroke={BLUE} strokeWidth="1" strokeDasharray="3 3" />
            )}

            {/* green roof: substrate band + planting tufts */}
            {hasGreenRoof && (
              <g>
                <rect x={x} y={roofY - 3} width={w} height={3} fill="#16a34a30" stroke={GREEN} strokeWidth="0.8" />
                <Tufts x0={x} x1={x + w} y={roofY - 3} color={GREEN} step={9} size={4} />
              </g>
            )}

            {/* cool roof: white coating + reflection arrows */}
            {hasCoolRoof && !hasGreenRoof && (
              <g>
                <line x1={x} y1={roofY - 1.5} x2={x + w} y2={roofY - 1.5} stroke={BLUE} strokeWidth="3" opacity="0.85" />
                <ReflectArrows x0={x} x1={x + w} y={roofY - 4} />
              </g>
            )}

            {/* facade greening on the sun-facing facade */}
            {section.facadeGreening && <FacadeVine x={sunnyX} y0={roofY} y1={groundY} />}

            {/* climate shelter tag on the most vulnerable building */}
            {section.shelterIdx === i && (
              <g>
                <line x1={x + w / 2} y1={roofY - (hasGreenRoof ? 4 : 1)} x2={x + w / 2} y2={roofY - 16} stroke={INK} strokeWidth="1" />
                <polygon points={`${x + w / 2},${roofY - 16} ${x + w / 2 + 11},${roofY - 12.5} ${x + w / 2},${roofY - 9}`} fill={GREEN} />
                <text x={x + w / 2 + 14} y={roofY - 10} fontSize="8.5" fill={GREEN}>refugi climàtic · 26°C</text>
              </g>
            )}

            {/* HVI dot + height */}
            {w > 24 && (
              <>
                <circle cx={x + w / 2 - 14} cy={roofY - 24} r="3.5" fill={getHVIColorHex(p.hvi ?? 5)} />
                <text x={x + w / 2 - 7} y={roofY - 21} fontSize="9" fill={INK}>
                  {(p.hvi ?? 0).toFixed(1)}
                </text>
                <text x={x + w / 2} y={groundY - h / 2 + 3} fontSize="8.5" fill={FAINT} textAnchor="middle">
                  {p.height.toFixed(0)}m{p.year ? ` · ${p.year}` : ''}
                </text>
              </>
            )}
          </g>
        );
      })}

      {/* ---- scale figures ---- */}
      {(section.people || []).map((p, i) => (
        <Person key={i} x={X(p.x)} groundY={groundY} mY={mY} />
      ))}

      {/* ---- ground line ---- */}
      <line x1={PAD - 10} y1={groundY} x2={W - PAD + 10} y2={groundY} stroke={INK} strokeWidth="1.8" />

      {/* ---- canyon H/W annotations ---- */}
      {section.gaps.filter((g) => g.width > 6).map((g, i) => (
        <g key={i} fill={FAINT} fontSize="8.5" textAnchor="middle">
          <text x={X((g.x0 + g.x1) / 2)} y={groundY + 16}>
            {g.width.toFixed(0)}m · H/W {g.hw.toFixed(1)}
          </text>
        </g>
      ))}

      {/* ---- temperature strip ---- */}
      <g>
        <text x={PAD} y={stripTop - 6} fontSize="9.5" fill={INK} fontWeight="600">
          SURFACE TEMPERATURE °C
        </text>
        <text x={W - PAD} y={stripTop - 6} fontSize="8.5" fill={FAINT} textAnchor="end">
          Landsat zone mean {section.zoneLstC.toFixed(1)}°C + computed shading
        </text>
        {[tMin, (tMin + tMax) / 2, tMax].map((t) => (
          <g key={t}>
            <line x1={PAD} y1={tToY(t)} x2={W - PAD} y2={tToY(t)} stroke="#e4e4e0" strokeWidth="0.8" />
            <text x={PAD - 5} y={tToY(t) + 3} fontSize="8.5" fill={FAINT} textAnchor="end">
              {t.toFixed(0)}
            </text>
          </g>
        ))}
        <path d={tempPath(section.curveBefore, xScale, tToY, PAD)} stroke={RED} strokeWidth="1.6" fill="none" />
        {section.curveAfter && (
          <path d={tempPath(section.curveAfter, xScale, tToY, PAD)} stroke={BLUE} strokeWidth="1.6" fill="none" />
        )}
        <g fontSize="9" transform={`translate(${PAD}, ${stripTop + stripH + 16})`}>
          <line x1="0" y1="-3" x2="18" y2="-3" stroke={RED} strokeWidth="1.6" />
          <text x="23" y="0" fill={INK}>measured (before)</text>
          {section.curveAfter && (
            <>
              <line x1="130" y1="-3" x2="148" y2="-3" stroke={BLUE} strokeWidth="1.6" />
              <text x="153" y="0" fill={INK}>
                with interventions: {activeNames.join(' + ') || '—'}
              </text>
            </>
          )}
        </g>
      </g>

      {/* ---- scale bar + vertical exaggeration note ---- */}
      <g transform={`translate(${W - PAD - 20 * xScale}, ${H - 14})`} fontSize="8.5" fill={INK}>
        <line x1="0" y1="-4" x2={20 * xScale} y2="-4" stroke={INK} strokeWidth="1.2" />
        <line x1="0" y1="-8" x2="0" y2="0" stroke={INK} strokeWidth="1.2" />
        <line x1={20 * xScale} y1="-8" x2={20 * xScale} y2="0" stroke={INK} strokeWidth="1.2" />
        <text x={10 * xScale} y="8" textAnchor="middle">20 m{vx > 1 ? ` · vert ×${vx}` : ''}</text>
      </g>

      {/* ---- title ---- */}
      <text x={PAD} y={H - 10} fontSize="9" fill={FAINT}>
        SECTION {section.orientation === 'NS' ? 'S–N' : 'W–E'} · {section.length.toFixed(0)} m ·
        proposed elements in blue/green · shadows cast at computed solar geometry · LOD1 heights
      </text>
    </svg>
  );
});

export default ClimaticSection;
