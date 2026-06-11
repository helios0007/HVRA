// The climatic section — a data drawing in architectural drafting convention.
//
// Cut convention: walls and slabs cut by the section plane are drawn as solid
// poché; faces beyond are light, with era-typical facade articulation
// (Catastro construction year → tall windows + balconies for pre-1980 stock,
// band windows for modern, storefront ground floors). LOD1 geometry: the
// articulation is typological, not surveyed — stated in the title block.
//
// Everything climatic is computed: shadows from the real solar position, the
// surface-temperature curve from Landsat LST bent by the selected
// interventions. Proposals in blue/green, existing fabric in ink.

import { forwardRef } from 'react';
import { getHVIColorHex } from '../utils/hviColors';

const INK = '#1a1a1a';
const POCHE = '#2e2e2a';
const FAINT = '#999';
const RED = '#d43d2a';
const BLUE = '#2563eb';
const GREEN = '#16a34a';

const WALL_M = 0.35; // cut wall thickness
const SLAB_M = 0.3; // cut slab thickness

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

// Scalloped crown outline — section tree
function crownPath(cx, cy, r) {
  const bumps = 9;
  let d = '';
  for (let i = 0; i <= bumps; i++) {
    const a0 = (i / bumps) * Math.PI * 2 - Math.PI / 2;
    const x = cx + Math.cos(a0) * r;
    const y = cy + Math.sin(a0) * r;
    if (i === 0) d = `M${x.toFixed(1)},${y.toFixed(1)}`;
    else {
      const am = ((i - 0.5) / bumps) * Math.PI * 2 - Math.PI / 2;
      const qx = cx + Math.cos(am) * r * 1.22;
      const qy = cy + Math.sin(am) * r * 1.22;
      d += ` Q${qx.toFixed(1)},${qy.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
    }
  }
  return d + 'Z';
}

function Tree({ x, groundY, mY, crownH, crownR }) {
  const r = crownR * mY;
  const cy = groundY - (crownH + crownR * 0.7) * mY;
  return (
    <g stroke={BLUE} fill="none" strokeWidth="1.1">
      <line x1={x} y1={groundY} x2={x} y2={cy + r * 0.5} strokeWidth="1.6" />
      <line x1={x} y1={cy + r * 0.6} x2={x - r * 0.4} y2={cy + r * 0.15} />
      <line x1={x} y1={cy + r * 0.5} x2={x + r * 0.45} y2={cy + r * 0.1} />
      <path d={crownPath(x, cy, r)} fill="#2563eb12" />
    </g>
  );
}

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

// Scale figure, 1.7 m, walking
function Person({ x, groundY, mY }) {
  const h = 1.7 * mY;
  const headR = h * 0.13;
  const y0 = groundY - h;
  return (
    <g stroke={INK} fill={INK} strokeWidth="1" strokeLinecap="round">
      <circle cx={x} cy={y0 + headR} r={headR} fill="none" />
      <line x1={x} y1={y0 + headR * 2.1} x2={x - h * 0.04} y2={groundY - h * 0.38} />
      <line x1={x - h * 0.04} y1={groundY - h * 0.38} x2={x - h * 0.2} y2={groundY} fill="none" />
      <line x1={x - h * 0.04} y1={groundY - h * 0.38} x2={x + h * 0.14} y2={groundY - h * 0.16} fill="none" />
      <line x1={x + h * 0.14} y1={groundY - h * 0.16} x2={x + h * 0.1} y2={groundY} fill="none" />
      <line x1={x - h * 0.16} y1={y0 + h * 0.42} x2={x + h * 0.2} y2={y0 + h * 0.36} fill="none" />
    </g>
  );
}

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

function NightRadiation({ x0, x1, groundY, hw }) {
  const escape = Math.max(0.25, 1 - Math.min(hw, 2) / 2.4);
  const h = 14 + escape * 26;
  const items = [];
  const n = Math.max(2, Math.floor((x1 - x0) / 30));
  for (let i = 1; i <= n; i++) {
    const x = x0 + ((x1 - x0) * i) / (n + 1);
    items.push(
      <g key={i} stroke={RED} strokeWidth="1" fill="none" opacity="0.7">
        <path d={`M${x},${groundY - 3} q3,-${h / 3} 0,-${(h * 2) / 3} q-3,-${h / 4} 0,-${h}`} />
        <polyline points={`${x - 3},${groundY - h + 3} ${x},${groundY - h - 1} ${x + 3},${groundY - h + 3}`} />
      </g>
    );
  }
  return <g>{items}</g>;
}

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

// Oblique dimension ticks (drafting convention)
function DimLine({ x0, x1, y, label }) {
  return (
    <g stroke={INK} strokeWidth="0.8" fontSize="8.5">
      <line x1={x0} y1={y} x2={x1} y2={y} />
      <line x1={x0} y1={y - 6} x2={x0} y2={y + 3} strokeWidth="0.7" />
      <line x1={x1} y1={y - 6} x2={x1} y2={y + 3} strokeWidth="0.7" />
      <line x1={x0 - 2.5} y1={y + 2.5} x2={x0 + 2.5} y2={y - 2.5} strokeWidth="1" />
      <line x1={x1 - 2.5} y1={y + 2.5} x2={x1 + 2.5} y2={y - 2.5} strokeWidth="1" />
      <text x={(x0 + x1) / 2} y={y - 3} textAnchor="middle" stroke="none" fill={INK}>
        {label}
      </text>
    </g>
  );
}

// Cut building: poché walls/slabs, era-typical facade beyond
function Building({ p, x, w, h, groundY, mY, xScale, sunnyRight, night }) {
  const roofY = groundY - h;
  const wallPx = Math.max(WALL_M * xScale, 1.4);
  const slabPx = Math.max(SLAB_M * mY, 1.1);
  const detailed = mY >= 1.0 && w > 26;

  const eraScore = p.factors?.construction_era?.score ?? 0.5;
  const old = p.year ? p.year < 1980 : eraScore >= 0.55;

  // storey levels (m): taller ground floor when the building allows it
  const gf = p.height >= 7.5 ? 3.8 : 3.0;
  const levels = [];
  let lv = gf;
  while (lv < p.height - 1.6) {
    levels.push(lv);
    lv += 3.0;
  }

  const inner = [x + wallPx, x + w - wallPx];
  const Ym = (m) => groundY - m * mY;

  return (
    <g>
      {/* face beyond */}
      <rect x={x} y={roofY} width={w} height={h} fill="#fdfdfb" />

      {detailed && (
        <g>
          {/* storefront ground floor */}
          <rect
            x={inner[0] + 0.4 * xScale}
            y={Ym(gf - 0.9)}
            width={inner[1] - inner[0] - 0.8 * xScale}
            height={(gf - 1.3) * mY}
            fill="#eef0ee"
            stroke="#b9b9b1"
            strokeWidth="0.6"
          />
          {(() => {
            const mullions = [];
            for (let mx = inner[0] + 2.5 * xScale; mx < inner[1] - 1 * xScale; mx += 2.5 * xScale) {
              mullions.push(
                <line key={mx} x1={mx} y1={Ym(gf - 0.9)} x2={mx} y2={Ym(0.4)} stroke="#b9b9b1" strokeWidth="0.6" />
              );
            }
            return mullions;
          })()}

          {/* upper storeys: era-typical openings */}
          {levels.map((lvl, k) => {
            const cells = [];
            if (old) {
              // tall window + balcony rhythm (Eixample type)
              for (let wx = inner[0] + 1.2 * xScale; wx + 1.2 * xScale < inner[1] - 0.8 * xScale; wx += 3.0 * xScale) {
                cells.push(
                  <rect
                    key={wx}
                    x={wx}
                    y={Ym(lvl + 3.0 - 0.7)}
                    width={1.2 * xScale}
                    height={2.1 * mY}
                    fill="#ecedea"
                    stroke="#a8a8a0"
                    strokeWidth="0.6"
                  />
                );
              }
            } else {
              // modern band window
              cells.push(
                <rect
                  key="band"
                  x={inner[0] + 1.0 * xScale}
                  y={Ym(lvl + 2.5)}
                  width={inner[1] - inner[0] - 2.0 * xScale}
                  height={1.5 * mY}
                  fill="#ecedea"
                  stroke="#a8a8a0"
                  strokeWidth="0.6"
                />
              );
            }
            return <g key={k}>{cells}</g>;
          })}

          {/* balconies on the cut facades (old stock) */}
          {old &&
            levels.map((lvl, k) => (
              <g key={`b${k}`} stroke={INK} strokeWidth="0.8" fill={POCHE}>
                {[x, x + w].map((fx, side) => {
                  const dir = side === 0 ? -1 : 1;
                  const bw = 0.5 * xScale * dir;
                  return (
                    <g key={side}>
                      <rect
                        x={Math.min(fx, fx + bw)}
                        y={Ym(lvl) - Math.max(0.18 * mY, 1)}
                        width={Math.abs(bw)}
                        height={Math.max(0.18 * mY, 1)}
                      />
                      <line x1={fx + bw} y1={Ym(lvl)} x2={fx + bw} y2={Ym(lvl + 1.0)} fill="none" />
                      <line x1={fx} y1={Ym(lvl + 1.0)} x2={fx + bw} y2={Ym(lvl + 1.0)} fill="none" />
                    </g>
                  );
                })}
              </g>
            ))}

          {/* cornice on old stock */}
          {old && (
            <g stroke={INK} strokeWidth="1">
              <line x1={x - 0.35 * xScale} y1={Ym(p.height - 0.5)} x2={x + w + 0.35 * xScale} y2={Ym(p.height - 0.5)} />
            </g>
          )}
        </g>
      )}

      {/* simple storey lines when too small for detail */}
      {!detailed &&
        levels.map((lvl, k) => (
          <line key={k} x1={x + 1} y1={Ym(lvl)} x2={x + w - 1} y2={Ym(lvl)} stroke="#dddcd5" strokeWidth="0.7" />
        ))}

      {/* cut poché: walls + slabs */}
      <g fill={POCHE} stroke="none">
        <rect x={x} y={roofY} width={wallPx} height={h} />
        <rect x={x + w - wallPx} y={roofY} width={wallPx} height={h} />
        <rect x={x} y={roofY} width={w} height={slabPx} />
        {levels.map((lvl, k) => (
          <rect key={k} x={x} y={Ym(lvl)} width={w} height={slabPx} />
        ))}
      </g>

      {/* heavy cut outline */}
      <rect x={x} y={roofY} width={w} height={h} fill="none" stroke={INK} strokeWidth="1.9" />
    </g>
  );
}

const ClimaticSection = forwardRef(function ClimaticSection({ section, activeNames = [] }, ref) {
  if (!section) {
    return <div className="diagram-empty">No buildings intersect this cut — move the position slider.</div>;
  }

  const W = 1060;
  const PAD = 56;
  const drawW = W - PAD * 2;
  const xScale = drawW / section.length;

  const vx = section.length / section.maxHeight > 18 ? 2 : 1;
  const mY = xScale * vx;

  const groundY = 30 + section.maxHeight * mY + 56;
  const sunBandTop = 16;

  const isNight = section.sun?.night;
  const stripTop = groundY + 52;
  const stripH = 78;
  const tMax = isNight ? section.zoneLstC - 2 : section.zoneLstC + 6;
  const tMin = isNight ? section.zoneLstC - 20 : Math.min(28, section.zoneLstC - 16);
  const tToY = (t) => stripTop + stripH - ((t - tMin) / (tMax - tMin)) * stripH;
  const H = stripTop + stripH + 76;

  const X = (m) => PAD + m * xScale;
  const sun = section.sun;
  const surface = section.surface || {};

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
      {/* ---- sun or moon (computed) ---- */}
      {sun.night ? (
        <g>
          <path
            d={`M${sunX},${sunY - 8} a8,8 0 1,0 8,8 a6.5,6.5 0 1,1 -8,-8`}
            fill="#fff"
            stroke={INK}
            strokeWidth="1"
          />
          <text x={sunX + 18} y={sunY + 4} fontSize="10" fill={INK}>
            21 Jun · night · stored heat re-radiates — deep canyons cool slowest (Oke 1981)
          </text>
        </g>
      ) : (
        <>
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
        </>
      )}

      {/* ---- night: re-radiation arrows ---- */}
      {sun.night &&
        section.gaps.map((g, i) => (
          <NightRadiation key={i} x0={X(g.x0)} x1={X(g.x1)} groundY={groundY} hw={g.hw} />
        ))}

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
              {!isNight && <ReflectArrows x0={x0} x1={x1} y={groundY} />}
            </g>
          );
        }
        return <rect key={i} x={x0} y={groundY} width={x1 - x0} height={4} fill="#1a1a1a" opacity="0.35" />;
      })}

      {/* ---- sidewalk + curb marks (2 m from each facade) ---- */}
      {section.gaps.filter((g) => g.width >= 6).map((g, i) => (
        <g key={i} stroke={INK} strokeWidth="0.7">
          <line x1={X(g.x0)} y1={groundY - 1.2} x2={X(g.x0 + 2)} y2={groundY - 1.2} />
          <line x1={X(g.x0 + 2)} y1={groundY - 1.2} x2={X(g.x0 + 2)} y2={groundY} />
          <line x1={X(g.x1 - 2)} y1={groundY - 1.2} x2={X(g.x1)} y2={groundY - 1.2} />
          <line x1={X(g.x1 - 2)} y1={groundY - 1.2} x2={X(g.x1 - 2)} y2={groundY} />
        </g>
      ))}

      {/* ---- proposed shade sails ---- */}
      {section.shadePatches.map((s, i) => (
        <ShadeSail key={i} x0={X(s.x0)} x1={X(s.x1)} groundY={groundY} mY={mY} h={s.h} />
      ))}

      {/* ---- proposed trees ---- */}
      {section.trees.map((t, i) => (
        <Tree key={i} x={X(t.x)} groundY={groundY} mY={mY} crownH={t.crownH} crownR={t.crownR} />
      ))}

      {/* ---- building profiles in cut convention ---- */}
      {section.profiles.map((p, i) => {
        const x = X(p.x0);
        const w = (p.x1 - p.x0) * xScale;
        const h = p.height * mY;
        const roofY = groundY - h;
        const sunnyX = sun.shadowDir > 0 ? x + w : x;
        return (
          <g key={i}>
            <Building
              p={p}
              x={x}
              w={w}
              h={h}
              groundY={groundY}
              mY={mY}
              xScale={xScale}
              sunnyRight={sun.shadowDir > 0}
              night={isNight}
            />

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
                {!isNight && <ReflectArrows x0={x} x1={x + w} y={roofY - 4} />}
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

            {/* HVI dot · height · year above the roof */}
            {w > 30 && (
              <g>
                <circle cx={x + 6} cy={roofY - 26} r="3.5" fill={getHVIColorHex(p.hvi ?? 5)} />
                <text x={x + 13} y={roofY - 23} fontSize="9" fill={INK}>
                  HVI {(p.hvi ?? 0).toFixed(1)} · {p.height.toFixed(0)}m{p.year ? ` · ${p.year}` : ''}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* ---- level markers on the tallest building ---- */}
      {(() => {
        const x = X(tallest.x0);
        const roofY = groundY - tallest.height * mY;
        return (
          <g fontSize="8.5" fill={INK} stroke="none">
            {[[groundY, '±0.00'], [roofY, `+${tallest.height.toFixed(2)}`]].map(([y, lbl]) => (
              <g key={lbl}>
                <polygon
                  points={`${x - 14},${y - 5} ${x - 9},${y} ${x - 19},${y}`}
                  fill="none"
                  stroke={INK}
                  strokeWidth="0.8"
                />
                <line x1={x - 9} y1={y} x2={x - 2} y2={y} stroke={INK} strokeWidth="0.8" />
                <text x={x - 14} y={y - 8} textAnchor="middle">{lbl}</text>
              </g>
            ))}
          </g>
        );
      })()}

      {/* ---- scale figures ---- */}
      {(section.people || []).map((p, i) => (
        <Person key={i} x={X(p.x)} groundY={groundY} mY={mY} />
      ))}

      {/* ---- earth hatch below grade ---- */}
      <g stroke="#c9c9c2" strokeWidth="0.7">
        {(() => {
          const lines = [];
          for (let hx = PAD - 10; hx < W - PAD + 10; hx += 7) {
            lines.push(<line key={hx} x1={hx} y1={groundY + 5} x2={hx - 6} y2={groundY + 13} />);
          }
          return lines;
        })()}
      </g>

      {/* ---- ground line ---- */}
      <line x1={PAD - 10} y1={groundY} x2={W - PAD + 10} y2={groundY} stroke={INK} strokeWidth="2.2" />

      {/* ---- orientation labels ---- */}
      <text x={PAD - 30} y={groundY + 5} fontSize="11" fontWeight="700" fill={INK}>
        {section.orientation === 'NS' ? 'S' : 'W'}
      </text>
      <text x={W - PAD + 18} y={groundY + 5} fontSize="11" fontWeight="700" fill={INK}>
        {section.orientation === 'NS' ? 'N' : 'E'}
      </text>

      {/* ---- street dimension lines (drafting ticks) + H/W ---- */}
      {section.gaps.filter((g) => g.width > 6).map((g, i) => (
        <g key={i}>
          <DimLine x0={X(g.x0)} x1={X(g.x1)} y={groundY + 24} label={`${g.width.toFixed(1)} m`} />
          <text x={X((g.x0 + g.x1) / 2)} y={groundY + 36} fontSize="8" fill={FAINT} textAnchor="middle">
            H/W {g.hw.toFixed(1)}
          </text>
        </g>
      ))}

      {/* ---- temperature strip ---- */}
      <g>
        <text x={PAD} y={stripTop - 6} fontSize="9.5" fill={INK} fontWeight="600">
          {isNight ? 'NOCTURNAL SURFACE TEMPERATURE °C' : 'SURFACE TEMPERATURE °C'}
        </text>
        <text x={W - PAD} y={stripTop - 6} fontSize="8.5" fill={FAINT} textAnchor="end">
          {isNight
            ? `post-sunset release of day heat (Landsat ${section.zoneLstC.toFixed(1)}°C) · retention ∝ H/W (Oke 1981)`
            : `Landsat zone mean ${section.zoneLstC.toFixed(1)}°C + computed shading`}
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
          <text x="23" y="0" fill={INK}>{isNight ? 'modelled night (before)' : 'measured (before)'}</text>
          {section.curveAfter && (
            <>
              <line x1="160" y1="-3" x2="178" y2="-3" stroke={BLUE} strokeWidth="1.6" />
              <text x="183" y="0" fill={INK}>
                with interventions: {activeNames.join(' + ') || '—'}
              </text>
            </>
          )}
        </g>
      </g>

      {/* ---- scale bar ---- */}
      <g transform={`translate(${W - PAD - 20 * xScale}, ${H - 40})`} fontSize="8.5" fill={INK}>
        <line x1="0" y1="-4" x2={20 * xScale} y2="-4" stroke={INK} strokeWidth="1.2" />
        <line x1="0" y1="-8" x2="0" y2="0" stroke={INK} strokeWidth="1.2" />
        <line x1={10 * xScale} y1="-7" x2={10 * xScale} y2="-1" stroke={INK} strokeWidth="1" />
        <line x1={20 * xScale} y1="-8" x2={20 * xScale} y2="0" stroke={INK} strokeWidth="1.2" />
        <text x={10 * xScale} y="8" textAnchor="middle">20 m{vx > 1 ? ` · vert ×${vx}` : ''}</text>
      </g>

      {/* ---- title block ---- */}
      <line x1={PAD - 10} y1={H - 30} x2={W - PAD + 10} y2={H - 30} stroke={INK} strokeWidth="0.8" />
      <text x={PAD} y={H - 18} fontSize="9.5" fontWeight="700" fill={INK}>
        CLIMATIC SECTION A–A′ ({section.orientation === 'NS' ? 'S–N' : 'W–E'}) · {section.length.toFixed(0)} m
      </text>
      <text x={PAD} y={H - 7} fontSize="8" fill={FAINT}>
        cut convention: walls/slabs in poché · facade articulation typological by construction era (Catastro) ·
        LOD1 cadastral heights · shadows at computed solar geometry · proposals in blue/green
      </text>
      <text x={W - PAD} y={H - 18} fontSize="8.5" fill={INK} textAnchor="end">
        HVRA · {isNight ? 'night' : `${sun.solarHour}:00 solar`} · 21 Jun
      </text>
    </svg>
  );
});

export default ClimaticSection;
