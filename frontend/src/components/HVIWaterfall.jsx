// HVI waterfall — the whole intervention argument in one strip.
// Mean zone HVI cascading down through each selected intervention, with each
// step's marginal contribution computed by the same engine that colors the map.

import { forwardRef, useMemo } from 'react';
import { getHVIColorHex } from '../utils/hviColors';
import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';
import { applyInterventionsToZone } from '../utils/interventionEngine';

const CATEGORY_COLOR = { Building: '#a78bfa', Street: '#fb923c', Social: '#34d399' };

function meanHVI(fc) {
  const scores = (fc?.features || [])
    .map((f) => f.properties?.hvi_score)
    .filter((s) => s !== undefined && s !== null);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
}

const HVIWaterfall = forwardRef(function HVIWaterfall({ buildings, activeIds }, ref) {
  const steps = useMemo(() => {
    if (!buildings || !activeIds?.length) return null;

    // Order selected interventions by individual impact, then take marginal deltas
    const ordered = INTERVENTION_CATALOG.filter((iv) => activeIds.includes(iv.id));
    const start = meanHVI(buildings);
    let applied = [];
    let prev = start;
    const out = [];
    for (const iv of ordered) {
      applied = [...applied, iv.id];
      const m = meanHVI(applyInterventionsToZone(buildings, applied));
      out.push({ iv, delta: prev - m, after: m });
      prev = m;
    }
    out.sort((a, b) => b.delta - a.delta);
    // recompute cumulatively in sorted order for clean reading
    applied = [];
    prev = start;
    for (const s of out) {
      applied = [...applied, s.iv.id];
      const m = meanHVI(applyInterventionsToZone(buildings, applied));
      s.delta = prev - m;
      s.after = m;
      prev = m;
    }
    return { start, end: prev, items: out.filter((s) => s.delta > 0.005) };
  }, [buildings, activeIds]);

  if (!steps) return null;

  const W = 1060;
  const H = 150;
  const PAD = 60;
  const span = Math.max(steps.start - steps.end, 0.4);
  const xMin = steps.end - span * 0.18;
  const xMax = steps.start + span * 0.18;
  const X = (v) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);

  const rowH = 16;
  const top = 38;

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${Math.max(H, top + (steps.items.length + 2) * (rowH + 6) + 24)}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      <text x={PAD} y={20} fontSize="9.5" fill="#1a1a1a" fontWeight="600">
        ZONE HVI WATERFALL — marginal contribution of each measure (HVI index points, not °C)
      </text>

      {/* start bar */}
      <g transform={`translate(0, ${top})`}>
        <rect x={X(steps.start) - 3} y={0} width={6} height={rowH} fill={getHVIColorHex(steps.start)} />
        <text x={X(steps.start) + 8} y={rowH - 4} fontSize="10" fill="#1a1a1a" fontWeight="600">
          {steps.start.toFixed(2)} before
        </text>
      </g>

      {steps.items.map((s, i) => {
        const y = top + (i + 1) * (rowH + 6);
        const x1 = X(s.after + s.delta);
        const x0 = X(s.after);
        return (
          <g key={s.iv.id} transform={`translate(0, ${y})`}>
            <rect x={x0} y={0} width={Math.max(x1 - x0, 1.5)} height={rowH}
              fill={CATEGORY_COLOR[s.iv.category] || '#888'} opacity="0.85" rx="2" />
            {/* connector from previous level */}
            <line x1={x1} y1={-6} x2={x1} y2={0} stroke="#bbb" strokeWidth="1" />
            <text x={x0 - 6} y={rowH - 4} fontSize="9.5" fill="#1a1a1a" textAnchor="end">
              {s.iv.icon} {s.iv.name}
            </text>
            <text x={x1 + 6} y={rowH - 4} fontSize="9.5" fill="#555">
              −{s.delta.toFixed(2)}
            </text>
          </g>
        );
      })}

      {/* end bar */}
      <g transform={`translate(0, ${top + (steps.items.length + 1) * (rowH + 6)})`}>
        <rect x={X(steps.end) - 3} y={0} width={6} height={rowH} fill={getHVIColorHex(steps.end)} />
        <text x={X(steps.end) - 8} y={rowH - 4} fontSize="10" fill="#1a1a1a" fontWeight="600" textAnchor="end">
          {steps.end.toFixed(2)} after
        </text>
        <text x={X(steps.end) + 8} y={rowH - 4} fontSize="9.5" fill="#16a34a">
          Δ −{(steps.start - steps.end).toFixed(2)}
        </text>
      </g>
    </svg>
  );
});

export default HVIWaterfall;
