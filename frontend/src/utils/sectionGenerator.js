// Climatic section generator.
//
// Cuts a vertical section through the analyzed zone and computes everything
// the drawing shows from data:
//   - building profiles: real footprint chords × real heights (LOD1)
//   - shadows: cast from the computed solar position (solar.js)
//   - surface temperature curve: Landsat zone LST modulated by computed
//     shading, with active interventions applied as evidence-based deltas
//
// All coordinates are converted to a local metre frame along the cut line.

import { solarPosition, projectSunOntoSection, SUMMER_SOLSTICE_DOY } from './solar.js';

const M_PER_DEG_LAT = 111320;

// ---------------------------------------------------------------- geometry

// Ray-casting point-in-ring on lon/lat coordinates.
function pointInRingLL(px, py, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function bboxOfBuildings(features) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const eachPt = (ring) => {
    for (const [x, y] of ring) {
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    }
  };
  for (const f of features) {
    const g = f.geometry;
    if (!g) continue;
    if (g.type === 'Polygon') g.coordinates.forEach(eachPt);
    else if (g.type === 'MultiPolygon') g.coordinates.forEach((p) => p.forEach(eachPt));
  }
  return { w, s, e, n };
}

// Intersection parameter of cut segment A→B with edge Q1→Q2.
// Returns t in metres along the cut, or null.
function edgeCrossing(ax, ay, ux, uy, len, q1, q2) {
  const rx = q2[0] - q1[0];
  const ry = q2[1] - q1[1];
  const denom = ux * ry - uy * rx;
  if (Math.abs(denom) < 1e-12) return null;
  const dx = q1[0] - ax;
  const dy = q1[1] - ay;
  const t = (dx * ry - dy * rx) / denom; // metres along cut
  const u = (dx * uy - dy * ux) / denom; // 0..1 along edge
  if (u < 0 || u >= 1 || t < 0 || t > len) return null;
  return t;
}

/**
 * Build the section model.
 *
 * @param buildings  FeatureCollection (buildings_with_hvi)
 * @param contextBuildings  FeatureCollection (buffer zone buildings) - optional
 * @param opts {
 *   orientation: 'NS' | 'EW'   — direction the cut line runs
 *   position: 0..1             — where across the zone the cut sits
 *   solarHour: number          — solar time (12 = noon)
 *   activeIds: string[]        — selected intervention ids
 *   zoneLstC: number           — Landsat zone mean LST in °C
 * }
 */
export function buildSection(buildings, contextBuildings, opts) {
  // Handle both old API (3 args) and new API (2 args with contextBuildings in opts)
  if (!opts && contextBuildings && typeof contextBuildings === 'object' && !('features' in contextBuildings)) {
    opts = contextBuildings;
    contextBuildings = null;
  }
  const feats = buildings?.features?.filter((f) => f.geometry) || [];
  if (!feats.length) return null;

  const {
    orientation = 'NS',
    position = 0.5,
    solarHour = 12,
    activeIds = [],
    zoneLstC = 42,
    zoneBounds = null,
    includeContextInterventions = false,
  } = opts;

  // Add context buildings to the section if available
  const contextFeats = contextBuildings?.features?.filter((f) => f.geometry) || [];
  const allFeats = [...feats, ...contextFeats];

  const bbox = bboxOfBuildings(allFeats);
  const latMid = (bbox.s + bbox.n) / 2;
  const mPerDegLon = M_PER_DEG_LAT * Math.cos((latMid * Math.PI) / 180);

  // Cut line endpoints (lon/lat) and section bearing (+x axis).
  // Padded 5 m past the bbox so buildings touching the zone edge still
  // produce both entry and exit crossings.
  const padLat = 5 / M_PER_DEG_LAT;
  const padLon = 5 / mPerDegLon;
  let A, B, bearing;
  if (orientation === 'NS') {
    const lon = bbox.w + (bbox.e - bbox.w) * position;
    A = [lon, bbox.s - padLat];
    B = [lon, bbox.n + padLat];
    bearing = 0; // x axis points north
  } else {
    const lat = bbox.s + (bbox.n - bbox.s) * position;
    A = [bbox.w - padLon, lat];
    B = [bbox.e + padLon, lat];
    bearing = 90; // x axis points east
  }

  // Local metre frame: origin at A
  const toM = ([lon, lat]) => [(lon - A[0]) * mPerDegLon, (lat - A[1]) * M_PER_DEG_LAT];
  const Bm = toM(B);
  const length = Math.hypot(Bm[0], Bm[1]);
  if (length < 20) return null;
  const ux = Bm[0] / length;
  const uy = Bm[1] / length;

  // Classify any point along the cut (distance x in metres) as inside the drawn
  // zone polygon or in the surrounding context. With no polygon, treat all as
  // in-zone (back-compat).
  let zoneRingLL = null;
  const zg = zoneBounds?.geometry || zoneBounds;
  if (zg?.type === 'Polygon' && zg.coordinates?.[0]) zoneRingLL = zg.coordinates[0];
  const inZoneAtX = (x) => {
    if (!zoneRingLL) return true;
    const lon = A[0] + (x * ux) / mPerDegLon;
    const lat = A[1] + (x * uy) / M_PER_DEG_LAT;
    return pointInRingLL(lon, lat, zoneRingLL);
  };
  // An intervention is allowed at x when it's inside the zone, or when the user
  // has opted to extend interventions to context buildings too.
  const interveneAtX = (x) => includeContextInterventions || inZoneAtX(x);

  // --- intersect every building footprint with the cut line (even-odd) ---
  const intervals = [];
  for (const f of allFeats) {
    const explicitContext = contextFeats.includes(f);
    const g = f.geometry;
    const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
    const ts = [];
    for (const rings of polys) {
      for (const ring of rings) {
        const ringM = ring.map(toM);
        for (let i = 0; i < ringM.length - 1; i++) {
          const t = edgeCrossing(0, 0, ux, uy, length, ringM[i], ringM[i + 1]);
          if (t !== null) ts.push(t);
        }
      }
    }
    if (ts.length < 2) continue;
    ts.sort((a, b) => a - b);
    for (let i = 0; i + 1 < ts.length; i += 2) {
      if (ts[i + 1] - ts[i] >= 1.5) {
        const mid = (ts[i] + ts[i + 1]) / 2;
        intervals.push({
          x0: ts[i],
          x1: ts[i + 1],
          height: f.properties?.height || 15,
          hvi: f.properties?.hvi_score ?? null,
          hviBefore: f.properties?.hvi_score_before ?? f.properties?.hvi_score ?? null,
          factors: f.properties?.hvi_factors || null,
          year: f.properties?.construction_year ?? null,
          isContext: explicitContext || !inZoneAtX(mid),
        });
      }
    }
  }
  intervals.sort((a, b) => a.x0 - b.x0);

  // Merge overlaps (adjacent party-wall buildings)
  const profiles = [];
  for (const iv of intervals) {
    const last = profiles[profiles.length - 1];
    if (last && iv.x0 < last.x1 - 0.5) {
      // overlapping chords — keep both but clip the start for drawing clarity
      iv.x0 = last.x1;
      if (iv.x1 - iv.x0 < 1.5) continue;
    }
    profiles.push({ ...iv });
  }
  if (!profiles.length) return null;

  // --- street gaps with canyon ratio ---
  const gaps = [];
  for (let i = 0; i + 1 < profiles.length; i++) {
    const w = profiles[i + 1].x0 - profiles[i].x1;
    if (w >= 3) {
      const h = (profiles[i].height + profiles[i + 1].height) / 2;
      const mid = (profiles[i].x1 + profiles[i + 1].x0) / 2;
      gaps.push({ x0: profiles[i].x1, x1: profiles[i + 1].x0, width: w, hw: h / w, isContext: !inZoneAtX(mid) });
    }
  }

  // --- solar position & shadows (or night: no sun, canyon heat retention) ---
  const isNight = solarHour === 'night';
  const sun = isNight
    ? { altitudeDeg: 0, azimuthDeg: 0 }
    : solarPosition(latMid, SUMMER_SOLSTICE_DOY, solarHour);
  const proj = isNight
    ? { shadowDir: 1, shadowRatio: 0, inPlaneAltDeg: 0, weak: true }
    : projectSunOntoSection(sun.altitudeDeg, sun.azimuthDeg, bearing);
  const shadows = [];
  if (!isNight && !proj.weak && proj.shadowRatio > 0.02) {
    for (const p of profiles) {
      const len = p.height * proj.shadowRatio;
      const edge = proj.shadowDir > 0 ? p.x1 : p.x0;
      const sx0 = proj.shadowDir > 0 ? edge : edge - len;
      const sx1 = proj.shadowDir > 0 ? edge + len : edge;
      shadows.push({ x0: Math.max(0, sx0), x1: Math.min(length, sx1), height: p.height, from: edge });
    }
  }

  const insideBuilding = (x) => profiles.some((p) => x >= p.x0 && x <= p.x1);
  const inShadow = (x) => shadows.some((s) => x >= s.x0 && x <= s.x1);

  // --- proposed elements from active interventions ---
  const has = (id) => activeIds.includes(id);
  const trees = [];
  if (has('street_trees')) {
    // Only plant in gaps inside the zone, unless the user extends to context.
    for (const gap of gaps.filter((g) => g.width >= 7 && (includeContextInterventions || !g.isContext))) {
      for (let x = gap.x0 + 4; x <= gap.x1 - 4; x += 9) {
        trees.push({ x, crownR: 2.5, crownH: 5.5 });
      }
    }
  }
  const shadePatches = [];
  if (has('shade_structures')) {
    for (const gap of gaps.filter((g) => (g.hw >= 0.8 || g.width <= 14) && (includeContextInterventions || !g.isContext))) {
      const w = Math.min(4, gap.width * 0.4);
      // patch on the sunny side of the canyon (where the shadow does NOT fall)
      const x0 = proj.shadowDir > 0 ? gap.x1 - w : gap.x0;
      shadePatches.push({ x0, x1: x0 + w, h: 3.5 });
    }
  }
  const underTree = (x) => trees.some((t) => Math.abs(x - t.x) <= t.crownR + 0.5);
  const underShade = (x) => shadePatches.some((s) => x >= s.x0 && x <= s.x1);

  // --- surface temperature curves -------------------------------------
  // Base: Landsat zone-mean LST. Exposed asphalt sits above the zone mean
  // (which averages roofs/streets/green); shading reduces surface temperature.
  // Intervention deltas follow the evidence in the catalog:
  //   de-paving  −5°C surface (Eixample, measured)
  //   cool pavement −8°C (EPA mid-range)
  //   tree canopy / engineered shade ≈ shading effect −6°C surface
  const STEP = 1.5;
  const before = [];
  const after = [];
  const materialDelta = has('cool_pavement') ? -8 : has('depave_planting') ? -5 : 0;

  // Night: surfaces release the heat stored during the day. Open ground cools
  // freely; canyon floors cool slowly because buildings block the sky view —
  // retention scales with H/W after Oke (1981): UHImax ≈ 7.45 + 3.97·ln(H/W).
  // Materials that store less heat (permeable / high-albedo) release less.
  const nightRetention = (x) => {
    const gap = gaps.find((g) => x >= g.x0 && x <= g.x1);
    if (!gap) return 0;
    return Math.min(0.4 * (7.45 + 3.97 * Math.log(Math.max(gap.hw, 0.3))), 8);
  };

  for (let x = 0; x <= length; x += STEP) {
    if (insideBuilding(x)) {
      before.push(null);
      after.push(null);
      continue;
    }

    // Interventions only cool the street where they are allowed (in-zone, or
    // everywhere when the user extends them to context).
    const localMatDelta = interveneAtX(x) ? materialDelta : 0;

    if (isNight) {
      const baseT = zoneLstC - 14 + nightRetention(x);
      before.push({ x, t: baseT });
      // stored-heat reduction: half the daytime material delta; shading is moot
      after.push({ x, t: baseT + localMatDelta / 2 });
      continue;
    }

    const baseT = zoneLstC + 4 - (inShadow(x) ? 6 : 0);
    before.push({ x, t: baseT });

    let tAfter = zoneLstC + 4 + localMatDelta;
    const shaded = inShadow(x) || underTree(x) || underShade(x);
    if (shaded) tAfter -= 6;
    after.push({ x, t: tAfter });
  }

  const smooth = (arr) => {
    const out = arr.slice();
    for (let pass = 0; pass < 2; pass++) {
      for (let i = 1; i < out.length - 1; i++) {
        if (!out[i] || !out[i - 1] || !out[i + 1]) continue;
        out[i] = { x: out[i].x, t: (out[i - 1].t + out[i].t * 2 + out[i + 1].t) / 4 };
      }
    }
    return out;
  };

  // Roof-level interventions (drawn on the buildings, not the street curve)
  const roofTags = [];
  if (has('cool_roof')) roofTags.push({ id: 'cool_roof', label: 'cool roof' });
  if (has('green_roof')) roofTags.push({ id: 'green_roof', label: 'green roof' });
  const facadeTag = has('facade_greening') || has('envelope_retrofit');

  // Scale figures (1.7 m) — one in the widest gap, one under the first tree/shade
  const people = [];
  if (gaps.length) {
    const widest = gaps.reduce((a, b) => (b.width > a.width ? b : a));
    people.push({ x: (widest.x0 + widest.x1) / 2 + 1.5 });
  }
  if (trees.length) people.push({ x: trees[0].x + 2.2 });
  else if (shadePatches.length) people.push({ x: (shadePatches[0].x0 + shadePatches[0].x1) / 2 });

  // Climate shelter: tag the most vulnerable building on the cut
  let shelterIdx = null;
  if (has('climate_shelter') && profiles.length) {
    let best = -1;
    profiles.forEach((p, i) => {
      if (p.isContext) return; // shelter is designated within the drawn zone
      if ((p.hvi ?? 0) > best) {
        best = p.hvi ?? 0;
        shelterIdx = i;
      }
    });
  }

  return {
    surface: {
      depave: has('depave_planting'),
      coolPavement: has('cool_pavement'),
    },
    people,
    shelterIdx,
    contextIntervened: includeContextInterventions,
    envelopeRetrofit: has('envelope_retrofit'),
    facadeGreening: has('facade_greening'),
    length,
    orientation,
    bearing,
    cutLine: [A, B],
    profiles,
    gaps,
    shadows,
    trees,
    shadePatches,
    roofTags,
    facadeTag,
    curveBefore: smooth(before),
    curveAfter: activeIds.length ? smooth(after) : null,
    sun: { ...sun, ...proj, solarHour, night: isNight },
    zoneLstC,
    maxHeight: Math.max(...profiles.map((p) => p.height)),
  };
}
