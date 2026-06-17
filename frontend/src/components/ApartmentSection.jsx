// The coupled-performance drawing: one apartment, before and after, with the
// elderly resident drawn in. Heat paths (solar gain on the SW facade, roof and
// envelope conduction), the ventilation path or its absence, computed surface
// temperatures, and the modelled indoor reduction — all on one sheet.

import { forwardRef } from 'react';

const INK = '#1a1a1a';
const POCHE = '#2e2e2a';
const FAINT = '#8a8a82';
const HOT = '#d43d2a';
const WARM = '#e8842a';
const BLUE = '#2563eb';
const GREEN = '#16a34a';

function comfortColor(t, ceiling) {
  if (t > ceiling + 3) return HOT;
  if (t > ceiling) return WARM;
  return GREEN;
}

// thick heat arrow; intensity 0–1 sets the width
function HeatArrow({ x1, y1, x2, y2, intensity, color }) {
  const w = 1.5 + intensity * 7;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const hl = 6 + intensity * 5;
  const a1 = ang - 2.5, a2 = ang + 2.5;
  return (
    <g stroke={color} fill={color}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={w} strokeLinecap="round" />
      <polygon
        points={`${x2},${y2} ${x2 - hl * Math.cos(a1)},${y2 - hl * Math.sin(a1)} ${x2 - hl * Math.cos(a2)},${y2 - hl * Math.sin(a2)}`}
        stroke="none"
      />
    </g>
  );
}

// seated elderly resident with a comfort halo
function Resident({ x, floorY, color }) {
  return (
    <g>
      <ellipse cx={x} cy={floorY - 26} rx="34" ry="40" fill={color} opacity="0.16" />
      <g stroke={INK} fill="none" strokeWidth="1.5" strokeLinecap="round">
        {/* chair */}
        <line x1={x + 10} y1={floorY} x2={x + 10} y2={floorY - 30} />
        <line x1={x + 10} y1={floorY - 30} x2={x - 8} y2={floorY - 30} />
        {/* seated body */}
        <circle cx={x - 6} cy={floorY - 46} r="6" />
        <line x1={x - 6} y1={floorY - 40} x2={x - 4} y2={floorY - 26} />
        <line x1={x - 4} y1={floorY - 26} x2={x + 8} y2={floorY - 26} />
        <line x1={x + 8} y1={floorY - 26} x2={x + 8} y2={floorY - 12} />
        <line x1={x + 8} y1={floorY - 12} x2={x + 14} y2={floorY} />
        {/* arm + cane */}
        <line x1={x - 5} y1={floorY - 36} x2={x + 4} y2={floorY - 26} />
        <line x1={x + 16} y1={floorY - 30} x2={x + 16} y2={floorY} />
      </g>
    </g>
  );
}

function Panel({ state, indoor, peakUtci, ceiling, ox, title, isAfter, applied }) {
  const W = 480;
  const fy = 322; // floor line
  const ceilY = fy - 132; // interior ceiling
  const roofTop = ceilY - 16;
  const left = ox + 96; // SW facade inner
  const right = ox + 384; // party wall inner
  const wallW = 13;
  const winY = fy - 86; // window sill
  const winH = 52;

  const surf = {
    roof: indoor + 3.2 * state.roofGain,
    sw: indoor + 2.6 * state.solarGain,
  };
  const cc = comfortColor(indoor, ceiling);

  return (
    <g>
      {/* panel title */}
      <text x={ox + W / 2} y={26} fontSize="12" fontWeight="700" fill={INK} textAnchor="middle">
        {title}
      </text>

      {/* sun + rays to the SW facade */}
      <g stroke={WARM} fill="none" strokeWidth="1">
        <circle cx={ox + 44} cy={70} r="9" fill="#fff" />
        {[...Array(8)].map((_, i) => {
          const a = (i * Math.PI) / 4;
          return <line key={i} x1={ox + 44 + Math.cos(a) * 12} y1={70 + Math.sin(a) * 12} x2={ox + 44 + Math.cos(a) * 16} y2={70 + Math.sin(a) * 16} />;
        })}
        <line x1={ox + 52} y1={78} x2={left - 6} y2={winY + 8} strokeDasharray="4 4" stroke={WARM} />
        <line x1={ox + 52} y1={78} x2={left + 30} y2={roofTop - 2} strokeDasharray="4 4" stroke={WARM} opacity="0.6" />
      </g>
      <text x={ox + 30} y={94} fontSize="8.5" fill={FAINT}>SW · 17:00</text>

      {/* roof slab (+ treatment when after) */}
      <rect x={left - wallW} y={roofTop} width={right - left + 2 * wallW} height={16} fill={POCHE} />
      {isAfter && applied.some((a) => a.path === 'roof') && (
        <g>
          <rect x={left - wallW} y={roofTop - 4} width={right - left + 2 * wallW} height={4} fill={GREEN} opacity="0.5" />
          <text x={right} y={roofTop - 7} fontSize="8" fill={GREEN} textAnchor="end">reflective / planted roof</text>
        </g>
      )}

      {/* room walls (poché) */}
      <rect x={left - wallW} y={ceilY} width={wallW} height={fy - ceilY} fill={POCHE} />
      <rect x={right} y={ceilY} width={wallW} height={fy - ceilY} fill={POCHE} />
      {/* external insulation on the SW wall when after */}
      {isAfter && applied.some((a) => a.path === 'wall') && (
        <rect x={left - wallW - 5} y={ceilY} width={5} height={fy - ceilY} fill={BLUE} opacity="0.4" />
      )}
      {/* ceiling + floor slabs */}
      <rect x={left - wallW} y={ceilY} width={right - left + 2 * wallW} height={6} fill={POCHE} />
      <rect x={left - wallW} y={fy} width={right - left + 2 * wallW} height={7} fill={POCHE} />

      {/* SW window opening */}
      <rect x={left - wallW} y={winY} width={wallW} height={winH} fill="#dfe6ee" stroke={INK} strokeWidth="0.8" />
      {/* external shading louvers when after */}
      {isAfter && applied.some((a) => a.path === 'solar') && (
        <g stroke={BLUE} strokeWidth="1.4">
          {[0, 1, 2, 3].map((k) => (
            <line key={k} x1={left - wallW - 9} y1={winY + 6 + k * 14} x2={left - wallW - 1} y2={winY + 2 + k * 14} />
          ))}
        </g>
      )}

      {/* HEAT PATHS IN */}
      {/* roof conduction */}
      <HeatArrow x1={left + 60} y1={ceilY - 4} x2={left + 60} y2={ceilY + 30} intensity={state.roofGain} color={HOT} />
      {/* solar gain through SW glazing */}
      <HeatArrow x1={left - 2} y1={winY + winH / 2} x2={left + 54} y2={winY + winH / 2 + 14} intensity={state.solarGain} color={WARM} />
      {/* SW wall conduction */}
      <HeatArrow x1={left - 2} y1={ceilY + 44} x2={left + 30} y2={ceilY + 50} intensity={state.wallConduction} color={WARM} />

      {/* VENTILATION PATH or its absence */}
      {state.ventCross ? (
        <g>
          <HeatArrow x1={right + 2} y1={winY + 14} x2={right - 60} y2={winY + 6} intensity={0.5} color={BLUE} />
          <text x={(left + right) / 2} y={ceilY + 22} fontSize="8.5" fill={BLUE} textAnchor="middle">cross-ventilation</text>
        </g>
      ) : (
        <g stroke={HOT} strokeWidth="1.4">
          {/* party wall, blocked */}
          <line x1={right + 2} y1={winY + 6} x2={right + 11} y2={winY + 24} />
          <line x1={right + 11} y1={winY + 6} x2={right + 2} y2={winY + 24} />
          <text x={right - 6} y={ceilY + 22} fontSize="8" fill={HOT} textAnchor="end">no cross-ventilation</text>
        </g>
      )}

      {/* surface temperatures */}
      <text x={left + 70} y={ceilY + 20} fontSize="8.5" fill={HOT}>ceiling {surf.roof.toFixed(0)}°C</text>
      <text x={left + 4} y={winY - 4} fontSize="8.5" fill={WARM}>SW wall {surf.sw.toFixed(0)}°C</text>

      {/* the resident */}
      <Resident x={left + 150} floorY={fy} color={cc} />

      {/* indoor operative temperature */}
      <g>
        <text x={right - 6} y={fy - 54} fontSize="9" fill={FAINT} textAnchor="end">indoor operative</text>
        <text x={right - 6} y={fy - 32} fontSize="22" fontWeight="700" fill={cc} textAnchor="end">
          {indoor.toFixed(1)}°C
        </text>
        <text x={right - 6} y={fy - 16} fontSize="8.5" fill={cc} textAnchor="end">
          {indoor > ceiling ? `+${(indoor - ceiling).toFixed(1)}°C over safe (${ceiling}°C)` : 'within safe range'}
        </text>
      </g>

      {/* floor / ground */}
      <line x1={ox + 70} y1={fy + 7} x2={ox + W - 40} y2={fy + 7} stroke={INK} strokeWidth="1.6" />
    </g>
  );
}

const ApartmentSection = forwardRef(function ApartmentSection({ model }, ref) {
  if (!model) return <div className="diagram-empty">No buildings to model.</div>;

  const W = 980;
  const H = 380;

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      <Panel state={model.before} indoor={model.indoorBefore} peakUtci={model.peakUtci}
        ceiling={model.comfortCeiling} ox={0} title="BEFORE — heat paths in" isAfter={false} applied={[]} />
      <Panel state={model.after} indoor={model.indoorAfter} peakUtci={model.peakUtci}
        ceiling={model.comfortCeiling} ox={W / 2} title="AFTER — top retrofits applied" isAfter applied={model.applied} />

      {/* divider */}
      <line x1={W / 2} y1={40} x2={W / 2} y2={H - 40} stroke="#e0e0da" strokeWidth="1" strokeDasharray="3 4" />

      {/* reduction callout */}
      <g transform={`translate(${W / 2}, ${175})`}>
        <circle r="30" fill="#fff" stroke={GREEN} strokeWidth="1.5" />
        <text y="-3" fontSize="9" fill={FAINT} textAnchor="middle">indoor</text>
        <text y="12" fontSize="15" fontWeight="700" fill={GREEN} textAnchor="middle">−{model.indoorReduction.toFixed(1)}°C</text>
      </g>

      {/* persona + retrofit legend / title block */}
      <line x1={20} y1={H - 30} x2={W - 20} y2={H - 30} stroke={INK} strokeWidth="0.8" />
      <text x={20} y={H - 17} fontSize="9.5" fontWeight="700" fill={INK}>
        COUPLED PERFORMANCE — {model.persona.label}{model.persona.year ? ` (${model.persona.year})` : ''}
      </text>
      <text x={20} y={H - 6} fontSize="8" fill={FAINT}>
        schematic dwelling section · indoor operative temperature modelled from peak UTCI {model.peakUtci.toFixed(0)}°C + roof/envelope/solar gains ·
        retrofits: {model.retrofits.map((r) => r.name).join(', ') || '—'}
      </text>
    </svg>
  );
});

export default ApartmentSection;
