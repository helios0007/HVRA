// Intervention plan generator.
// Projects the analyzed buildings into a local metre frame and computes the
// plan-level design elements for the active interventions:
//   - roof treatments per building (only where the catalog says applicable)
//   - street trees placed by geometry: open ground 3–11 m from a facade,
//     thinned to planting distance — i.e. along the streets, computed
//   - climate-shelter designation (most vulnerable building) + 300 m radius
//   - surface treatment of the unbuilt space (de-paving / cool pavement)

import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';

const M_PER_DEG_LAT = 111320;

function distPointSeg(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2)) : 0;
  const cx = x1 + t * dx;
  const cy = y1 + t * dy;
  return Math.hypot(px - cx, py - cy);
}

function pointInRing(px, py, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function buildPlan(buildings, contextBuildings, zoneBounds, activeIds = [], options = {}) {
  // Handle both old API (3 args) and new API (4 args)
  if (contextBuildings && typeof contextBuildings === 'object' && !('features' in contextBuildings) && Array.isArray(contextBuildings)) {
    activeIds = zoneBounds;
    zoneBounds = contextBuildings;
    contextBuildings = null;
  }

  // When true, interventions are also applied to context (out-of-zone) buildings.
  const includeContextInterventions = !!options.includeContextInterventions;

  const feats = buildings?.features?.filter((f) => f.geometry) || [];
  const contextFeats = contextBuildings?.features?.filter((f) => f.geometry) || [];
  const allFeats = [...feats, ...contextFeats];

  if (!allFeats.length) return null;

  // ---- bbox & projection (metres from the SW corner) ----
  // Scan every building so context buildings stay within the drawing frame.
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const scan = (ring) => {
    for (const [x, y] of ring) {
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    }
  };
  for (const f of allFeats) {
    const g = f.geometry;
    if (g.type === 'Polygon') g.coordinates.forEach(scan);
    else if (g.type === 'MultiPolygon') g.coordinates.forEach((p) => p.forEach(scan));
  }
  const latMid = (s + n) / 2;
  const mLon = M_PER_DEG_LAT * Math.cos((latMid * Math.PI) / 180);
  const toM = ([lon, lat]) => [(lon - w) * mLon, (lat - s) * M_PER_DEG_LAT];
  const widthM = (e - w) * mLon;
  const heightM = (n - s) * M_PER_DEG_LAT;

  // ---- zone boundary (in metres) — also used to classify in-zone vs context ----
  let zoneRing = null;
  const zg = zoneBounds?.geometry || zoneBounds;
  if (zg?.type === 'Polygon' && zg.coordinates?.[0]) zoneRing = zg.coordinates[0].map(toM);

  const has = (id) => activeIds.includes(id);
  const catalogById = Object.fromEntries(INTERVENTION_CATALOG.map((iv) => [iv.id, iv]));
  const applies = (id, factors) => {
    const iv = catalogById[id];
    return iv && factors && (!iv.applicable || iv.applicable(factors));
  };

  // ---- buildings: rings in metres, centroid, HVI, roof treatment ----
  // A building is "context" when its centroid falls outside the drawn zone
  // polygon (Infrared returns everything in the zone's bounding box). Context
  // buildings are drawn faintly and, by default, receive no interventions.
  const items = [];
  for (const f of allFeats) {
    const g = f.geometry;
    const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
    const rings = [];
    for (const poly of polys) for (const ring of poly) rings.push(ring.map(toM));
    if (!rings.length) continue;
    const outer = rings[0];
    let cx = 0, cy = 0;
    for (const [x, y] of outer) {
      cx += x;
      cy += y;
    }
    cx /= outer.length;
    cy /= outer.length;

    const outsideZone = zoneRing ? !pointInRing(cx, cy, zoneRing) : false;
    const isContext = contextFeats.includes(f) || outsideZone;
    const intervene = includeContextInterventions || !isContext;

    const factors = f.properties?.hvi_factors;
    let roof = null;
    if (intervene && has('green_roof') && applies('green_roof', factors)) roof = 'green';
    else if (intervene && has('cool_roof') && applies('cool_roof', factors)) roof = 'cool';
    items.push({
      rings,
      centroid: [cx, cy],
      hvi: f.properties?.hvi_score ?? null,
      retrofit: intervene && has('envelope_retrofit') && applies('envelope_retrofit', factors),
      roof,
      isContext,
    });
  }

  // ---- street trees: geometric placement in the unbuilt space ----
  const trees = [];
  if (has('street_trees')) {
    const edges = [];
    for (const b of items) {
      for (const ring of b.rings) {
        for (let i = 0; i < ring.length - 1; i++) {
          edges.push([ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1]]);
        }
      }
    }
    const STEPM = 5;
    for (let gy = STEPM / 2; gy < heightM; gy += STEPM) {
      for (let gx = STEPM / 2; gx < widthM; gx += STEPM) {
        if (zoneRing && !pointInRing(gx, gy, zoneRing)) continue;
        if (items.some((b) => pointInRing(gx, gy, b.rings[0]))) continue;
        let dMin = Infinity;
        for (const [x1, y1, x2, y2] of edges) {
          const d = distPointSeg(gx, gy, x1, y1, x2, y2);
          if (d < dMin) dMin = d;
          if (dMin < 3) break;
        }
        if (dMin < 3 || dMin > 11) continue; // sidewalk / street band only
        if (trees.some((t) => Math.hypot(t[0] - gx, t[1] - gy) < 9)) continue; // planting distance
        trees.push([gx, gy]);
      }
    }
  }

  // ---- climate shelter: most vulnerable IN-ZONE building + 300 m service radius ----
  let shelter = null;
  const zoneItems = items.filter((b) => !b.isContext);
  if (has('climate_shelter') && zoneItems.length) {
    const target = zoneItems.reduce((a, b) => ((b.hvi ?? 0) > (a.hvi ?? 0) ? b : a));
    shelter = { center: target.centroid, radiusM: 300 };
  }

  return {
    widthM,
    heightM,
    buildings: items,
    zoneRing,
    trees,
    shelter,
    surface: has('depave_planting') ? 'depave' : has('cool_pavement') ? 'cool' : null,
    shade: has('shade_structures'),
    contextIntervened: includeContextInterventions,
  };
}
