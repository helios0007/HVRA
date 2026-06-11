// The climatic section — a minimal data drawing.
// Every line is computed: building chords from real footprints, shadows from
// the real solar position, and a surface-temperature curve from Landsat LST
// bent by the selected interventions.

import { forwardRef } from 'react';
import { getHVIColorHex } from '../utils/hviColors';

const INK = '#1a1a1a';
const FAINT = '#999';
const RED = '#d43d2a';
const BLUE = '#2563eb';

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
  const stripTop = groundY + 34;
  const stripH = 78;
  const tMax = section.zoneLstC + 6;
  const tMin = Math.min(28, section.zoneLstC - 16);
  const tToY = (t) => stripTop + stripH - ((t - tMin) / (tMax - tMin)) * stripH;
  const H = stripTop + stripH + 46;

  const X = (m) => PAD + m * xScale;
  const sun = section.sun;

  // Sun glyph position: on the side the sun comes from
  const sunX = sun.shadowDir > 0 ? PAD + 30 : W - PAD - 30;
  const sunY = sunBandTop + 14;
  // Sun ray hitting the tallest building's far corner
  const tallest = section.profiles.reduce((a, b) => (b.height > a.height ? b : a));
  const rayTargetX = X(sun.shadowDir > 0 ? tallest.x1 : tallest.x0);
  const rayTargetY = groundY - tallest.height * mY;

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

      {/* ---- proposed shade patches ---- */}
      {section.shadePatches.map((s, i) => (
        <g key={i} stroke={BLUE} strokeWidth="1.2" fill="none">
          <line x1={X(s.x0)} y1={groundY - s.h * mY} x2={X(s.x1)} y2={groundY - s.h * mY} />
          <line x1={X(s.x0)} y1={groundY - s.h * mY} x2={X(s.x0)} y2={groundY} strokeDasharray="2 3" />
          <line x1={X(s.x1)} y1={groundY - s.h * mY} x2={X(s.x1)} y2={groundY} strokeDasharray="2 3" />
        </g>
      ))}

      {/* ---- proposed trees ---- */}
      {section.trees.map((t, i) => (
        <g key={i} stroke={BLUE} fill="none" strokeWidth="1.2">
          <line x1={X(t.x)} y1={groundY} x2={X(t.x)} y2={groundY - t.crownH * mY} />
          <circle cx={X(t.x)} cy={groundY - (t.crownH + t.crownR * 0.7) * mY} r={t.crownR * mY} fill="#2563eb14" />
        </g>
      ))}

      {/* ---- building profiles ---- */}
      {section.profiles.map((p, i) => {
        const x = X(p.x0);
        const w = (p.x1 - p.x0) * xScale;
        const h = p.height * mY;
        return (
          <g key={i}>
            <rect x={x} y={groundY - h} width={w} height={h} fill="#fff" stroke={INK} strokeWidth="1.4" />
            {/* roof intervention marks */}
            {section.roofTags.length > 0 && (
              <line x1={x} y1={groundY - h - 2.5} x2={x + w} y2={groundY - h - 2.5}
                stroke={section.roofTags[0].id === 'green_roof' ? '#16a34a' : BLUE} strokeWidth="2.5" />
            )}
            {section.facadeTag && (
              <line x1={sun.shadowDir > 0 ? x + 2.5 : x + w - 2.5} y1={groundY - h} x2={sun.shadowDir > 0 ? x + 2.5 : x + w - 2.5} y2={groundY}
                stroke="#16a34a" strokeWidth="2" strokeDasharray="3 3" />
            )}
            {/* HVI dot + height */}
            {w > 24 && (
              <>
                <circle cx={x + w / 2 - 14} cy={groundY - h - 12} r="3.5" fill={getHVIColorHex(p.hvi ?? 5)} />
                <text x={x + w / 2 - 7} y={groundY - h - 9} fontSize="9" fill={INK}>
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

      {/* ---- ground line ---- */}
      <line x1={PAD - 10} y1={groundY} x2={W - PAD + 10} y2={groundY} stroke={INK} strokeWidth="1.8" />

      {/* ---- canyon H/W annotations ---- */}
      {section.gaps.filter((g) => g.width > 6).map((g, i) => (
        <g key={i} fill={FAINT} fontSize="8.5" textAnchor="middle">
          <text x={X((g.x0 + g.x1) / 2)} y={groundY + 12}>
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
        {/* axis */}
        {[tMin, (tMin + tMax) / 2, tMax].map((t) => (
          <g key={t}>
            <line x1={PAD} y1={tToY(t)} x2={W - PAD} y2={tToY(t)} stroke="#e4e4e0" strokeWidth="0.8" />
            <text x={PAD - 5} y={tToY(t) + 3} fontSize="8.5" fill={FAINT} textAnchor="end">
              {t.toFixed(0)}
            </text>
          </g>
        ))}
        {/* before / after curves */}
        <path d={tempPath(section.curveBefore, xScale, tToY, PAD)} stroke={RED} strokeWidth="1.6" fill="none" />
        {section.curveAfter && (
          <path d={tempPath(section.curveAfter, xScale, tToY, PAD)} stroke={BLUE} strokeWidth="1.6" fill="none" />
        )}
        {/* legend */}
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
        shadows cast at computed solar geometry · LOD1 cadastral heights
      </text>
    </svg>
  );
});

export default ClimaticSection;
