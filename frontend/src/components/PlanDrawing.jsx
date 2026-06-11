// Intervention plan — true-scale roof plan of the zone with the selected
// measures drawn as plan symbols: roof treatments on eligible buildings,
// computed street-tree positions, surface treatment of the unbuilt space,
// climate-shelter radius, and the section cut line for cross-reference.

import { forwardRef } from 'react';
import { getHVIColorHex } from '../utils/hviColors';

const INK = '#1a1a1a';
const FAINT = '#999';
const BLUE = '#2563eb';
const GREEN = '#16a34a';

const PlanDrawing = forwardRef(function PlanDrawing(
  { plan, orientation = 'NS', position = 0.5, activeNames = [] },
  ref
) {
  if (!plan) return <div className="diagram-empty">No buildings to draw.</div>;

  const W = 1060;
  const PAD = 46;
  const maxH = 640;
  const scale = Math.min((W - PAD * 2) / plan.widthM, (maxH - PAD * 2) / plan.heightM);
  const H = plan.heightM * scale + PAD * 2 + 26;

  // metres → px, with north up (flip y)
  const X = (m) => PAD + m * scale;
  const Y = (m) => PAD + (plan.heightM - m) * scale;

  const ringPath = (ring) =>
    ring.map(([x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join('') + 'Z';
  const buildingPath = (b) => b.rings.map(ringPath).join(' ');

  // unbuilt space = zone (or bbox) minus all footprints, via even-odd fill
  const outerRing = plan.zoneRing
    ? ringPath(plan.zoneRing)
    : `M${X(0)},${Y(0)}L${X(plan.widthM)},${Y(0)}L${X(plan.widthM)},${Y(plan.heightM)}L${X(0)},${Y(plan.heightM)}Z`;
  const unbuiltPath = outerRing + ' ' + plan.buildings.map(buildingPath).join(' ');

  const surfaceFill =
    plan.surface === 'depave' ? '#16a34a14' : plan.surface === 'cool' ? '#2563eb10' : null;

  // section cut line across the plan
  const cutA =
    orientation === 'NS'
      ? [[plan.widthM * position, -4], [plan.widthM * position, plan.heightM + 4]]
      : [[-4, plan.heightM * position], [plan.widthM + 4, plan.heightM * position]];

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ background: '#fcfcfa', borderRadius: 8 }}
      fontFamily="ui-monospace, 'SF Mono', Consolas, monospace"
    >
      {/* surface treatment of the unbuilt space */}
      {surfaceFill && <path d={unbuiltPath} fill={surfaceFill} fillRule="evenodd" stroke="none" />}

      {/* zone boundary */}
      {plan.zoneRing && (
        <path d={ringPath(plan.zoneRing)} fill="none" stroke={BLUE} strokeWidth="1.2" strokeDasharray="6 4" opacity="0.7" />
      )}

      {/* climate-shelter service radius (clipped by the sheet) */}
      {plan.shelter && (
        <circle
          cx={X(plan.shelter.center[0])}
          cy={Y(plan.shelter.center[1])}
          r={plan.shelter.radiusM * scale}
          fill="#16a34a08"
          stroke={GREEN}
          strokeWidth="1"
          strokeDasharray="5 5"
        />
      )}

      {/* buildings */}
      {plan.buildings.map((b, i) => (
        <g key={i}>
          <path
            d={buildingPath(b)}
            fill={b.roof === 'green' ? '#16a34a22' : b.roof === 'cool' ? '#2563eb14' : '#fff'}
            fillRule="evenodd"
            stroke={INK}
            strokeWidth="1.1"
          />
          {b.retrofit && (
            <path d={buildingPath(b)} fill="none" fillRule="evenodd" stroke={BLUE} strokeWidth="2.6" opacity="0.35" />
          )}
          <circle cx={X(b.centroid[0])} cy={Y(b.centroid[1])} r="2.6" fill={getHVIColorHex(b.hvi ?? 5)} />
        </g>
      ))}

      {/* shelter flag on top of its building */}
      {plan.shelter && (
        <g>
          <line
            x1={X(plan.shelter.center[0])}
            y1={Y(plan.shelter.center[1])}
            x2={X(plan.shelter.center[0])}
            y2={Y(plan.shelter.center[1]) - 14}
            stroke={INK}
            strokeWidth="1"
          />
          <polygon
            points={`${X(plan.shelter.center[0])},${Y(plan.shelter.center[1]) - 14} ${X(plan.shelter.center[0]) + 10},${Y(plan.shelter.center[1]) - 10.5} ${X(plan.shelter.center[0])},${Y(plan.shelter.center[1]) - 7}`}
            fill={GREEN}
          />
          <text x={X(plan.shelter.center[0]) + 13} y={Y(plan.shelter.center[1]) - 8} fontSize="8.5" fill={GREEN}>
            refugi climàtic · r300m
          </text>
        </g>
      )}

      {/* street trees: crown circles at true scale */}
      {plan.trees.map(([tx, ty], i) => (
        <g key={i}>
          <circle cx={X(tx)} cy={Y(ty)} r={2.5 * scale} fill="#2563eb12" stroke={BLUE} strokeWidth="1" />
          <circle cx={X(tx)} cy={Y(ty)} r="1.2" fill={BLUE} />
        </g>
      ))}

      {/* section cut line A–A′ */}
      <g stroke={INK} strokeWidth="1.1">
        <line
          x1={X(cutA[0][0])}
          y1={Y(cutA[0][1])}
          x2={X(cutA[1][0])}
          y2={Y(cutA[1][1])}
          strokeDasharray="14 4 3 4"
        />
      </g>
      <text x={X(cutA[0][0]) + (orientation === 'NS' ? 5 : 0)} y={Y(cutA[0][1]) + (orientation === 'NS' ? -3 : -5)} fontSize="10" fontWeight="700" fill={INK}>
        A
      </text>
      <text x={X(cutA[1][0]) + (orientation === 'NS' ? 5 : -16)} y={Y(cutA[1][1]) + (orientation === 'NS' ? 10 : -5)} fontSize="10" fontWeight="700" fill={INK}>
        A′
      </text>

      {/* north arrow */}
      <g transform={`translate(${W - PAD - 8}, ${PAD + 4})`}>
        <polygon points="0,-12 4,4 0,1 -4,4" fill={INK} />
        <text x="0" y="16" fontSize="9" textAnchor="middle" fill={INK}>N</text>
      </g>

      {/* scale bar */}
      <g transform={`translate(${W - PAD - 50 * scale}, ${H - 18})`} fontSize="8.5" fill={INK}>
        <line x1="0" y1="-4" x2={50 * scale} y2="-4" stroke={INK} strokeWidth="1.2" />
        <line x1="0" y1="-8" x2="0" y2="0" stroke={INK} strokeWidth="1.2" />
        <line x1={25 * scale} y1="-7" x2={25 * scale} y2="-1" stroke={INK} strokeWidth="1" />
        <line x1={50 * scale} y1="-8" x2={50 * scale} y2="0" stroke={INK} strokeWidth="1.2" />
        <text x={25 * scale} y="8" textAnchor="middle">50 m</text>
      </g>

      {/* title + legend */}
      <text x={PAD} y={H - 10} fontSize="9" fill={FAINT}>
        INTERVENTION PLAN · cut A–A′ = climatic section · dots = building HVI ·
        {plan.trees.length ? ` ${plan.trees.length} trees placed geometrically (3–11 m from facades, 9 m spacing) ·` : ''}
        {activeNames.length ? ` ${activeNames.join(' + ')}` : ' no interventions selected'}
      </text>
    </svg>
  );
});

export default PlanDrawing;
