// What-if heatmap: re-render the UTCI grid with intervention deltas applied,
// client-side, using the exact colormap and value scale of the backend PNG —
// so before and after are directly comparable.
//
// Grid convention (matches the backend): values[row][col], row 0 = south.
//
// Spatial deltas (°C UTCI, conservative mid-range from the catalog evidence):
//   street cells:  trees −2.6 · shade structures −1.5 · de-paving −1.5
//                  cool pavement −1.0
//   roof cells:    cool roof −1.7 · green roof −1.2 (only on buildings where
//                  the catalog says the measure applies)

import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';

// Backend colormap: LinearSegmentedColormap over 5 evenly spaced stops
const STOPS = [
  [0.0, [0, 51, 204]], // #0033cc
  [0.25, [0, 153, 255]], // #0099ff
  [0.5, [255, 255, 255]], // #ffffff
  [0.75, [255, 102, 0]], // #ff6600
  [1.0, [204, 0, 0]], // #cc0000
];

function colorFor(t) {
  const x = Math.max(0, Math.min(1, t));
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [t0, c0] = STOPS[i];
    const [t1, c1] = STOPS[i + 1];
    if (x >= t0 && x <= t1) {
      const f = (x - t0) / (t1 - t0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * f),
        Math.round(c0[1] + (c1[1] - c0[1]) * f),
        Math.round(c0[2] + (c1[2] - c0[2]) * f),
      ];
    }
  }
  return [204, 0, 0];
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

const STREET_DELTAS = {
  street_trees: -2.6,
  shade_structures: -1.5,
  depave_planting: -1.5,
  cool_pavement: -1.0,
};
const ROOF_DELTAS = { cool_roof: -1.7, green_roof: -1.2 };

/**
 * Render a values grid to a PNG data URL with the backend's colormap.
 * vmin/vmax fix the scale (pass the ORIGINAL range for comparability).
 */
export function renderGridToDataURL(values, vmin, vmax, upscale = 4) {
  const rows = values.length;
  const cols = values[0]?.length || 0;
  if (!rows || !cols) return null;

  const small = document.createElement('canvas');
  small.width = cols;
  small.height = rows;
  const ctx = small.getContext('2d');
  const img = ctx.createImageData(cols, rows);
  const span = Math.max(vmax - vmin, 0.1);

  for (let r = 0; r < rows; r++) {
    const y = rows - 1 - r; // row 0 = south → bottom of the image
    for (let c = 0; c < cols; c++) {
      const v = values[r][c];
      const idx = (y * cols + c) * 4;
      if (v === null || v === undefined) {
        img.data[idx + 3] = 0;
        continue;
      }
      const [cr, cg, cb] = colorFor((v - vmin) / span);
      img.data[idx] = cr;
      img.data[idx + 1] = cg;
      img.data[idx + 2] = cb;
      img.data[idx + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // gentle upscale so deck.gl shows a smooth field, not pixels
  const big = document.createElement('canvas');
  big.width = cols * upscale;
  big.height = rows * upscale;
  const bctx = big.getContext('2d');
  bctx.imageSmoothingEnabled = true;
  bctx.imageSmoothingQuality = 'high';
  bctx.drawImage(small, 0, 0, big.width, big.height);
  return big.toDataURL('image/png');
}

/**
 * Apply the active interventions' spatial deltas to the grid.
 */
export function applyInterventionsToGrid(values, bounds, buildingsGeoJSON, activeIds) {
  const rows = values.length;
  const cols = values[0]?.length || 0;
  if (!rows || !cols) return values;

  const catalogById = Object.fromEntries(INTERVENTION_CATALOG.map((iv) => [iv.id, iv]));
  const streetDelta = activeIds.reduce((sum, id) => sum + (STREET_DELTAS[id] || 0), 0);

  // Buildings with outer ring + bbox + per-building roof delta
  const blds = [];
  for (const f of buildingsGeoJSON?.features || []) {
    const g = f.geometry;
    const ring = g?.type === 'Polygon' ? g.coordinates[0] : g?.type === 'MultiPolygon' ? g.coordinates[0][0] : null;
    if (!ring) continue;
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    for (const [x, y] of ring) {
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    }
    let roofDelta = 0;
    const factors = f.properties?.hvi_factors;
    for (const id of ['green_roof', 'cool_roof']) {
      if (!activeIds.includes(id)) continue;
      const iv = catalogById[id];
      if (factors && (!iv.applicable || iv.applicable(factors))) {
        roofDelta = ROOF_DELTAS[id];
        break; // green roof takes precedence
      }
    }
    blds.push({ ring, w, s, e, n, roofDelta });
  }

  const { west, south, east, north } = bounds;
  const out = [];
  for (let r = 0; r < rows; r++) {
    const lat = south + ((r + 0.5) / rows) * (north - south);
    const row = new Array(cols);
    for (let c = 0; c < cols; c++) {
      const v = values[r][c];
      if (v === null || v === undefined) {
        row[c] = v;
        continue;
      }
      const lon = west + ((c + 0.5) / cols) * (east - west);
      let hit = null;
      for (const b of blds) {
        if (lon < b.w || lon > b.e || lat < b.s || lat > b.n) continue;
        if (pointInRing(lon, lat, b.ring)) {
          hit = b;
          break;
        }
      }
      row[c] = v + (hit ? hit.roofDelta : streetDelta);
    }
    out.push(row);
  }
  return out;
}

/**
 * Full pipeline: grid + interventions → comparable after-image.
 * Returns null when the analysis has no raw grid (older sessions / fallback).
 */
export function computeWhatIfHeatmap(simulationGrid, buildingsGeoJSON, activeIds) {
  if (!simulationGrid?.values || !simulationGrid?.bounds || !activeIds?.length) return null;
  const modified = applyInterventionsToGrid(
    simulationGrid.values,
    simulationGrid.bounds,
    buildingsGeoJSON,
    activeIds
  );
  const url = renderGridToDataURL(modified, simulationGrid.min_value, simulationGrid.max_value);
  return url;
}
