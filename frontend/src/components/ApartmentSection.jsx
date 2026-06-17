// The coupled-performance drawing — one top-floor apartment, before and after,
// drawn in architectural cut convention with the elderly resident in context.
// Heat paths (solar gain on the SW facade, roof + envelope conduction), the
// cross-ventilation path or its absence, per-surface temperatures, and the
// modelled indoor reduction — all on one verifiable sheet.

import { forwardRef } from 'react';

const INK = '#1a1a1a';
const POCHE = '#2e2e2a';
const POCHE_FAINT = '#bcbcb4';
const FAINT = '#8a8a82';
const HOT = '#d43d2a';
const WARM = '#e8842a';
const BLUE = '#2563eb';
const GREEN = '#16a34a';

const PXM = 58; // pixels per metre (vertical & horizontal, true-ish scale)

function comfortColor(t, ceiling) {
  if (t > ceiling + 3) return HOT;
  if (t > ceiling) return WARM;
  return GREEN;
}

// thick heat arrow; intensity 0–1 sets the width
function HeatArrow({ x1, y1, x2, y2, intensity, color, dashed }) {
  const w = 1.4 + intensity * 6.5;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const hl = 6 + intensity * 5;
  return (
    <g stroke={color} fill={color}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={w} strokeLinecap="round"
        strokeDasharray={dashed ? '5 4' : 'none'} />
      <polygon points={`${x2},${y2} ${x2 - hl * Math.cos(ang - 0.4)},${y2 - hl * Math.sin(ang - 0.4)} ${x2 - hl * Math.cos(ang + 0.4)},${y2 - hl * Math.sin(ang + 0.4)}`} stroke="none" />
    </g>
  );
}

// airflow arrow (ventilation) — thin curved polyline
function AirArrow({ points, color = BLUE }) {
  const pts = points.map((p) => p.join(',')).join(' ');
  const [x2, y2] = points[points.length - 1];
  const [x1, y1] = points[points.length - 2];
  const ang = Math.atan2(y2 - y1, x2 - x1);
  return (
    <g stroke={color} fill={color} strokeWidth="1.6">
      <polyline points={pts} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <polygon points={`${x2},${y2} ${x2 - 7 * Math.cos(ang - 0.4)},${y2 - 7 * Math.sin(ang - 0.4)} ${x2 - 7 * Math.cos(ang + 0.4)},${y2 - 7 * Math.sin(ang + 0.4)}`} stroke="none" />
    </g>
  );
}

// diagonal insulation / treatment hatch inside a rect
function Hatch({ x, y, w, h, color, step = 5 }) {
  const lines = [];
  for (let d = -h; d < w; d += step) {
    const x1 = x + Math.max(0, d);
    const y1 = y + Math.max(0, -d);
    const x2 = x + Math.min(w, d + h);
    const y2 = y + Math.min(h, h - (d + h - w > 0 ? d + h - w : 0)) - Math.max(0, -(d));
    lines.push(<line key={d} x1={x + Math.max(0, d)} y1={y + h - Math.min(h, h + Math.min(0, d))} x2={x + Math.min(w, d + h)} y2={y + h - Math.min(h, h - Math.max(0, d + h - w))} />);
  }
  return <g stroke={color} strokeWidth="0.7" opacity="0.7">{lines}</g>;
}

// temperature callout with leader line
function TempCallout({ x, y, lx, ly, label, color, anchor = 'start' }) {
  return (
    <g>
      <line x1={x} y1={y} x2={lx} y2={ly} stroke={color} strokeWidth="0.7" />
      <circle cx={x} cy={y} r="2" fill={color} />
      <text x={lx + (anchor === 'end' ? -3 : 3)} y={ly + 3} fontSize="8.5" fill={color} textAnchor={anchor}>{label}</text>
    </g>
  );
}

// seated elderly resident with a cane and comfort halo
function Resident({ x, floorY, color }) {
  const s = PXM / 58;
  return (
    <g>
      <ellipse cx={x} cy={floorY - 42 * s} rx="40" ry="52" fill={color} opacity="0.15" />
      {/* armchair */}
      <g stroke={INK} fill="#f3f3ee" strokeWidth="1.2">
        <rect x={x - 20} y={floorY - 40} width={40} height={40} rx="4" />
        <rect x={x - 24} y={floorY - 44} width={8} height={36} rx="3" />
        <rect x={x + 16} y={floorY - 44} width={8} height={36} rx="3" />
      </g>
      {/* seated figure */}
      <g stroke={INK} fill="none" strokeWidth="1.6" strokeLinecap="round">
        <circle cx={x - 2} cy={floorY - 62} r="7" fill="#fff" />
        <line x1={x - 2} y1={floorY - 55} x2={x} y2={floorY - 36} />
        <line x1={x} y1={floorY - 36} x2={x + 14} y2={floorY - 34} />
        <line x1={x + 14} y1={floorY - 34} x2={x + 16} y2={floorY - 8} />
        <line x1={x - 2} y1={floorY - 48} x2={x + 12} y2={floorY - 40} />
        {/* cane */}
        <line x1={x + 20} y1={floorY - 40} x2={x + 22} y2={floorY} />
      </g>
    </g>
  );
}

function Panel({ model, ox, isAfter }) {
  const W = 510;
  const state = isAfter ? model.after : model.before;
  const indoor = isAfter ? model.indoorAfter : model.indoorBefore;
  const surf = isAfter ? model.surfacesAfter : model.surfacesBefore;
  const applied = isAfter ? model.applied : [];
  const ceiling = model.comfortCeiling;
  const cc = comfortColor(indoor, ceiling);
  const has = (p) => applied.some((a) => a.path === p);

  // geometry
  const xSW = ox + 84; // outer face SW wall
  const wallT = 14;
  const xParty = ox + 452; // outer face party wall
  const iL = xSW + wallT; // interior left
  const iR = xParty - wallT; // interior right
  const xPart = ox + 292; // partition centre
  const partT = 7;

  const yParapet = 70;
  const yRoofTop = 86;
  const yCeil = 106; // ceiling underside
  const yFloor = yCeil + 196; // ≈ 3.3 m interior
  const slabT = 10;

  // SW window / balcony
  const winHead = yCeil + 16;
  const winSill = yFloor - 14;
  // light-well window (inner room, party side)
  const lwHead = yCeil + 40;
  const lwSill = yFloor - 70;

  return (
    <g>
      <text x={ox + W / 2} y={24} fontSize="12" fontWeight="700" fill={INK} textAnchor="middle">
        {isAfter ? 'AFTER — top retrofits applied' : 'BEFORE — heat paths into the dwelling'}
      </text>

      {/* sun + rays onto SW facade */}
      <g stroke={WARM} fill="none" strokeWidth="1">
        <circle cx={ox + 46} cy={86} r="10" fill="#fff" />
        {[...Array(8)].map((_, i) => {
          const a = (i * Math.PI) / 4;
          return <line key={i} x1={ox + 46 + Math.cos(a) * 13} y1={86 + Math.sin(a) * 13} x2={ox + 46 + Math.cos(a) * 17} y2={86 + Math.sin(a) * 17} />;
        })}
        {[0, 1, 2].map((k) => (
          <line key={k} x1={ox + 56} y1={96 + k * 8} x2={xSW - 4} y2={winHead + 30 + k * 34} strokeDasharray="4 4" opacity="0.7" />
        ))}
      </g>
      <text x={ox + 30} y={108} fontSize="8.5" fill={FAINT}>SW · 17:00 · alt 38°</text>

      {/* ===== roof build-up ===== */}
      <rect x={xSW - 6} y={yRoofTop} width={xParty - xSW + 12} height={yCeil - yRoofTop} fill={POCHE} />
      {/* parapet */}
      <rect x={xSW - 6} y={yParapet} width={10} height={yRoofTop - yParapet + 4} fill={POCHE} />
      <rect x={xParty - 4} y={yParapet} width={10} height={yRoofTop - yParapet + 4} fill={POCHE} />
      {isAfter && has('roof') && (
        <g>
          <rect x={xSW - 6} y={yRoofTop - 6} width={xParty - xSW + 12} height={6}
            fill={model.retrofits.some((r) => r.id === 'green_roof') ? '#16a34a40' : '#bfdbfe'} stroke={GREEN} strokeWidth="0.6" />
          <text x={xParty - 4} y={yRoofTop - 9} fontSize="8" fill={GREEN} textAnchor="end">
            {model.retrofits.some((r) => r.id === 'green_roof') ? 'green roof' : 'reflective roof + insulation'}
          </text>
        </g>
      )}

      {/* ===== walls (poché) ===== */}
      <rect x={xSW} y={yCeil} width={wallT} height={yFloor - yCeil} fill={POCHE} />
      <rect x={xParty - wallT} y={yCeil} width={wallT} height={yFloor - yCeil} fill={POCHE} />
      {/* external insulation on SW wall (after) */}
      {isAfter && has('wall') && (
        <g>
          <rect x={xSW - 6} y={yCeil} width={6} height={yFloor - yCeil} fill="#dbeafe" stroke={BLUE} strokeWidth="0.6" />
          <Hatch x={xSW - 6} y={yCeil} w={6} h={yFloor - yCeil} color={BLUE} step={6} />
        </g>
      )}
      {/* partition */}
      <rect x={xPart - partT / 2} y={yCeil} width={partT} height={yFloor - yCeil} fill={POCHE_FAINT} />
      {/* ceiling + floor slabs */}
      <rect x={xSW} y={yCeil} width={xParty - xSW} height={slabT} fill={POCHE} />
      <rect x={xSW} y={yFloor} width={xParty - xSW} height={slabT} fill={POCHE} />
      {/* insulation under roof slab (after) */}
      {isAfter && has('roof') && <Hatch x={iL} y={yCeil + slabT} w={iR - iL} h={6} color={BLUE} step={6} />}

      {/* room labels */}
      <text x={(iL + xPart) / 2} y={yCeil + 24} fontSize="8.5" fill={FAINT} textAnchor="middle">LIVING ROOM · SW</text>
      <text x={(xPart + iR) / 2} y={yCeil + 24} fontSize="8.5" fill={FAINT} textAnchor="middle">BEDROOM</text>

      {/* ===== SW window + balcony ===== */}
      <rect x={xSW} y={winHead} width={wallT} height={winSill - winHead} fill="#dde6ef" stroke={INK} strokeWidth="0.8" />
      {/* balcony slab + railing */}
      <rect x={xSW - 42} y={yFloor - 4} width={42} height={6} fill={POCHE} />
      <g stroke={INK} strokeWidth="1">
        <line x1={xSW - 42} y1={yFloor - 4} x2={xSW - 42} y2={yFloor - 44} />
        {[0, 1, 2, 3, 4].map((k) => <line key={k} x1={xSW - 42 + k * 9} y1={yFloor - 44} x2={xSW - 42 + k * 9} y2={yFloor - 4} />)}
        <line x1={xSW - 42} y1={yFloor - 44} x2={xSW} y2={yFloor - 44} />
      </g>
      {/* external louvers/shutters on the window (after) */}
      {isAfter && has('solar') && (
        <g stroke={BLUE} strokeWidth="1.4">
          {[...Array(7)].map((_, k) => (
            <line key={k} x1={xSW - 11} y1={winHead + 8 + k * ((winSill - winHead) / 7)} x2={xSW - 2} y2={winHead + 2 + k * ((winSill - winHead) / 7)} />
          ))}
          <text x={xSW - 13} y={winHead - 2} fontSize="7.5" fill={BLUE} textAnchor="end">louvers</text>
        </g>
      )}

      {/* ===== light-well window (party side) ===== */}
      <rect x={xParty - wallT} y={lwHead} width={wallT} height={lwSill - lwHead} fill="#dde6ef" stroke={INK} strokeWidth="0.8" />
      {!state.ventCross && (
        <g stroke={HOT} strokeWidth="1.3">
          <line x1={xParty - wallT + 2} y1={lwHead + 4} x2={xParty - 2} y2={lwHead + 16} />
          <line x1={xParty - 2} y1={lwHead + 4} x2={xParty - wallT + 2} y2={lwHead + 16} />
          <text x={xParty - wallT - 4} y={lwHead - 3} fontSize="7.5" fill={HOT} textAnchor="end">shut</text>
        </g>
      )}

      {/* ===== furniture ===== */}
      {/* bed in bedroom (against party wall) */}
      <g stroke={INK} fill="#f3f3ee" strokeWidth="1">
        <rect x={iR - 96} y={yFloor - 34} width={96} height={34} rx="3" />
        <rect x={iR - 96} y={yFloor - 34} width={20} height={34} fill="#e6e6df" />
      </g>
      <text x={iR - 48} y={yFloor - 40} fontSize="7.5" fill={FAINT} textAnchor="middle">bed</text>
      {/* low table near window */}
      <rect x={iL + 96} y={yFloor - 18} width={40} height={4} fill={POCHE} />
      <line x1={iL + 100} y1={yFloor - 14} x2={iL + 100} y2={yFloor} stroke={INK} strokeWidth="1" />
      <line x1={iL + 132} y1={yFloor - 14} x2={iL + 132} y2={yFloor} stroke={INK} strokeWidth="1" />

      {/* solar insolation patch on the floor (length ∝ solarGain) */}
      <polygon
        points={`${iL},${yFloor} ${iL + 50 + state.solarGain * 120},${yFloor} ${iL + 30 + state.solarGain * 120},${yFloor - 5} ${iL},${yFloor - 5}`}
        fill={WARM} opacity={isAfter ? 0.18 : 0.32}
      />

      {/* ===== HEAT PATHS ===== */}
      {/* roof conduction — several arrows across the ceiling */}
      {[0, 1, 2, 3].map((k) => {
        const x = iL + 50 + k * ((iR - iL - 100) / 3);
        return <HeatArrow key={k} x1={x} y1={yCeil + slabT + 8} x2={x} y2={yCeil + slabT + 34} intensity={state.roofGain} color={HOT} />;
      })}
      {/* solar gain through SW glazing */}
      <HeatArrow x1={xSW + wallT + 2} y1={(winHead + winSill) / 2} x2={iL + 70} y2={(winHead + winSill) / 2 + 26} intensity={state.solarGain} color={WARM} />
      {/* SW wall conduction */}
      <HeatArrow x1={xSW + wallT + 2} y1={yFloor - 60} x2={iL + 40} y2={yFloor - 56} intensity={state.wallConduction} color={WARM} />

      {/* ===== VENTILATION ===== */}
      {state.ventCross ? (
        <g>
          <AirArrow points={[
            [xSW + wallT + 4, winSill - 30],
            [iL + 120, winSill - 40],
            [xPart, yCeil + 60],
            [iR - 30, lwSill - 10],
            [xParty - wallT - 4, lwHead + (lwSill - lwHead) / 2],
          ]} />
          <text x={xPart} y={yCeil + 52} fontSize="8.5" fill={BLUE} textAnchor="middle">cross-ventilation</text>
          {/* ceiling fan */}
          <g stroke={BLUE} strokeWidth="1.2" fill="none">
            <line x1={iL + 150} y1={yCeil + slabT} x2={iL + 150} y2={yCeil + slabT + 8} />
            <ellipse cx={iL + 138} cy={yCeil + slabT + 10} rx="12" ry="3" />
            <ellipse cx={iL + 162} cy={yCeil + slabT + 10} rx="12" ry="3" />
          </g>
        </g>
      ) : (
        <g>
          <AirArrow points={[[xSW + wallT + 4, winSill - 30], [iL + 110, winSill - 36], [iL + 150, winSill - 24]]} color={HOT} />
          <text x={iL + 150} y={winSill - 40} fontSize="8.5" fill={HOT}>no cross-ventilation</text>
          <text x={iL + 150} y={winSill - 28} fontSize="7.5" fill={FAINT}>single-aspect · heat trapped</text>
        </g>
      )}

      {/* ===== surface temperature callouts ===== */}
      <TempCallout x={iL + 200} y={yCeil + slabT + 2} lx={iR - 6} ly={yCeil + 44} label={`ceiling ${surf.roof.toFixed(0)}°C`} color={HOT} anchor="end" />
      <TempCallout x={xSW + wallT + 1} y={yFloor - 90} lx={iL + 30} ly={yFloor - 96} label={`SW wall ${surf.swWall.toFixed(0)}°C`} color={WARM} />
      <TempCallout x={xSW + wallT / 2} y={winHead + 10} lx={iL + 36} ly={winHead + 6} label={`glazing ${surf.glazing.toFixed(0)}°C`} color={WARM} />

      {/* the resident, by the window */}
      <Resident x={iL + 74} floorY={yFloor} color={cc} />

      {/* indoor operative temperature */}
      <g>
        <text x={iR - 6} y={yCeil + 64} fontSize="9" fill={FAINT} textAnchor="end">indoor operative</text>
        <text x={iR - 6} y={yCeil + 88} fontSize="23" fontWeight="700" fill={cc} textAnchor="end">{indoor.toFixed(1)}°C</text>
        <text x={iR - 6} y={yCeil + 104} fontSize="8.5" fill={cc} textAnchor="end">
          {indoor > ceiling ? `+${(indoor - ceiling).toFixed(1)}°C over safe (${ceiling}°C)` : 'within safe range'}
        </text>
      </g>

      {/* floors-below indicator (top-floor condition) */}
      <g>
        <rect x={xSW} y={yFloor + slabT} width={xParty - xSW} height={34} fill="#efefe9" />
        <rect x={xSW} y={yFloor + slabT} width={wallT} height={34} fill={POCHE_FAINT} />
        <rect x={xParty - wallT} y={yFloor + slabT} width={wallT} height={34} fill={POCHE_FAINT} />
        <text x={(iL + iR) / 2} y={yFloor + slabT + 21} fontSize="8" fill={FAINT} textAnchor="middle">floor below (cooler)</text>
        {/* break line */}
        <path d={`M${xSW - 6},${yFloor + slabT + 40} l8,-5 l8,10 l8,-10 l8,10 l8,-10 l8,10 l8,-5`} fill="none" stroke={FAINT} strokeWidth="0.8" />
      </g>

      {/* ceiling-height dimension */}
      <g stroke={INK} strokeWidth="0.7" fontSize="8">
        <line x1={iR + 16} y1={yCeil + slabT} x2={iR + 16} y2={yFloor} />
        <line x1={iR + 12} y1={yCeil + slabT} x2={iR + 20} y2={yCeil + slabT} />
        <line x1={iR + 12} y1={yFloor} x2={iR + 20} y2={yFloor} />
        <text x={iR + 22} y={(yCeil + yFloor) / 2} fill={FAINT} transform={`rotate(90 ${iR + 22} ${(yCeil + yFloor) / 2})`} textAnchor="middle">
          {((yFloor - yCeil - slabT) / PXM).toFixed(1)} m
        </text>
      </g>
    </g>
  );
}

const ApartmentSection = forwardRef(function ApartmentSection({ model }, ref) {
  if (!model) return <div className="diagram-empty">No buildings to model.</div>;

  const W = 1020;
  const H = 480;

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      <Panel model={model} ox={0} isAfter={false} />
      <Panel model={model} ox={W / 2} isAfter />

      {/* divider + indoor reduction callout */}
      <line x1={W / 2} y1={40} x2={W / 2} y2={H - 46} stroke="#e0e0da" strokeWidth="1" strokeDasharray="3 4" />
      <g transform={`translate(${W / 2}, 250)`}>
        <circle r="32" fill="#fff" stroke={GREEN} strokeWidth="1.5" />
        <text y="-4" fontSize="8.5" fill={FAINT} textAnchor="middle">indoor</text>
        <text y="13" fontSize="16" fontWeight="700" fill={GREEN} textAnchor="middle">−{model.indoorReduction.toFixed(1)}°C</text>
      </g>

      {/* title block */}
      <line x1={20} y1={H - 38} x2={W - 20} y2={H - 38} stroke={INK} strokeWidth="0.8" />
      <text x={20} y={H - 25} fontSize="10" fontWeight="700" fill={INK}>
        COUPLED PERFORMANCE — {model.persona.label}{model.persona.year ? ` (${model.persona.year})` : ''}
      </text>
      <text x={20} y={H - 13} fontSize="8" fill={FAINT}>
        schematic dwelling section · cut walls/slabs in poché · indoor operative temperature modelled from peak UTCI {model.peakUtci.toFixed(0)}°C +
        roof/envelope/solar gains · retrofits: {model.retrofits.map((r) => r.name).join(', ') || '—'}
      </text>
      <text x={W - 20} y={H - 25} fontSize="9" fill={INK} textAnchor="end">HVRA · dwelling section · 1:100</text>
    </svg>
  );
});

export default ApartmentSection;
