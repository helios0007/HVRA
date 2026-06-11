// Factor fingerprint — the zone's 12 HVI factors as a closed profile,
// before (red outline) vs after interventions (blue fill). Shows at a glance
// which kind of vulnerability the package addresses and which it can't touch.

import { forwardRef } from 'react';

const FACTORS = [
  ['construction_era', 'Age'],
  ['roof_type', 'Roof'],
  ['street_canyon', 'Canyon'],
  ['green_space', 'Green'],
  ['elderly_population', 'Elderly'],
  ['household_income', 'Income'],
  ['social_isolation', 'Isolation'],
  ['no_ac', 'No AC'],
  ['disability', 'Disability'],
  ['lst', 'LST'],
  ['uhi_delta', 'UHI'],
  ['ndvi', 'NDVI'],
];

function polygonPoints(factors, cx, cy, r) {
  return FACTORS.map(([key], i) => {
    const a = (i / FACTORS.length) * Math.PI * 2 - Math.PI / 2;
    const v = factors?.[key]?.score ?? 0;
    return `${(cx + Math.cos(a) * r * v).toFixed(1)},${(cy + Math.sin(a) * r * v).toFixed(1)}`;
  }).join(' ');
}

const FactorFingerprint = forwardRef(function FactorFingerprint({ before, after }, ref) {
  if (!before) return null;
  const S = 340;
  const cx = S / 2;
  const cy = S / 2 + 6;
  const r = 118;

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${S} ${S}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8, maxWidth: 360 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      <text x={S / 2} y={18} fontSize="9.5" fill="#1a1a1a" fontWeight="600" textAnchor="middle">
        FACTOR FINGERPRINT — zone mean, 0–1
      </text>

      {/* rings */}
      {[0.25, 0.5, 0.75, 1].map((v) => (
        <polygon
          key={v}
          points={FACTORS.map((_, i) => {
            const a = (i / FACTORS.length) * Math.PI * 2 - Math.PI / 2;
            return `${cx + Math.cos(a) * r * v},${cy + Math.sin(a) * r * v}`;
          }).join(' ')}
          fill="none"
          stroke="#e4e4e0"
          strokeWidth={v === 1 ? 1 : 0.6}
        />
      ))}

      {/* axes + labels */}
      {FACTORS.map(([key, label], i) => {
        const a = (i / FACTORS.length) * Math.PI * 2 - Math.PI / 2;
        const lx = cx + Math.cos(a) * (r + 16);
        const ly = cy + Math.sin(a) * (r + 16);
        return (
          <g key={key}>
            <line x1={cx} y1={cy} x2={cx + Math.cos(a) * r} y2={cy + Math.sin(a) * r}
              stroke="#eeeeea" strokeWidth="0.6" />
            <text x={lx} y={ly + 3} fontSize="8.5" fill="#777" textAnchor="middle">{label}</text>
          </g>
        );
      })}

      {/* after fill, before outline */}
      {after && (
        <polygon points={polygonPoints(after, cx, cy, r)} fill="#2563eb22" stroke="#2563eb" strokeWidth="1.5" />
      )}
      <polygon points={polygonPoints(before, cx, cy, r)} fill="none" stroke="#d43d2a" strokeWidth="1.6" />

      {/* legend */}
      <g fontSize="9" transform={`translate(${S / 2 - 90}, ${S - 10})`}>
        <line x1="0" y1="-3" x2="16" y2="-3" stroke="#d43d2a" strokeWidth="1.6" />
        <text x="20" y="0" fill="#1a1a1a">before</text>
        {after && (
          <>
            <rect x="70" y="-9" width="16" height="8" fill="#2563eb22" stroke="#2563eb" strokeWidth="1.2" />
            <text x="90" y="0" fill="#1a1a1a">with interventions</text>
          </>
        )}
      </g>
    </svg>
  );
});

export default FactorFingerprint;
