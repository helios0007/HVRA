// Quantity-based intervention cost estimator.
//
// Philosophy: nothing is a hardcoded *total*. Unit rates below are
// evidence-based constants (same literature as each catalog entry's
// `cost.detail`); the cost shown to the user is always
//   quantity (measured from the zone's real geometry) × unit rate.
// So the figure scales with the actual buildings/streets in the drawn zone.

const M_PER_DEG_LAT = 111320;
const AVG_DWELLING_M2 = 90;     // Barcelona mean dwelling floor area (Idescat)
const FLOOR_HEIGHT_M = 3;       // storey height for floor-count from LOD1 height
const AVG_STREET_WIDTH_M = 12;  // for street-length ≈ street-area / width
const TREE_SPACING_M = 9;       // catalog planting distance
const SHADE_FRACTION = 0.12;    // shade sails cover ≈12% of street area

// Unit rates: { basis, low €, high € [, unit label for 'fixed'] }
// basis decides which measured quantity the rate multiplies.
export const INTERVENTION_UNIT_COST = {
  cool_roof:          { basis: 'roof',     low: 10,    high: 30 },
  green_roof:         { basis: 'roof',     low: 80,    high: 150 },
  street_trees:       { basis: 'tree',     low: 500,   high: 2000 },
  depave_planting:    { basis: 'street',   low: 30,    high: 80 },
  cool_pavement:      { basis: 'street',   low: 5,     high: 80 },
  shade_structures:   { basis: 'shade',    low: 200,   high: 800 },
  facade_greening:    { basis: 'facade',   low: 50,    high: 600 },
  envelope_retrofit:  { basis: 'floor',    low: 150,   high: 400 },
  climate_shelter:    { basis: 'fixed',    low: 20000, high: 80000, unit: 'shelter fit-out' },
  ac_subsidy:         { basis: 'dwelling', low: 1500,  high: 4000 },
  indoor_plants:      { basis: 'dwelling', low: 80,    high: 600 },
  cross_ventilation:  { basis: 'fixed',    low: 0,     high: 0, unit: 'behavioural' },
  interior_shading:   { basis: 'dwelling', low: 150,   high: 600 },
  internal_insulation:{ basis: 'facade',   low: 40,    high: 110 },
};

const BASIS_UNIT = {
  roof: 'm² roof',
  facade: 'm² façade',
  floor: 'm² floor',
  dwelling: 'dwellings',
  tree: 'trees',
  street: 'm² street',
  shade: 'm² shade',
};

// Shoelace area + perimeter of a [lon,lat] ring, in metres / m².
function ringAreaPerimeter(ring, mPerDegLon) {
  let area2 = 0, perim = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const x1 = ring[i][0] * mPerDegLon, y1 = ring[i][1] * M_PER_DEG_LAT;
    const x2 = ring[i + 1][0] * mPerDegLon, y2 = ring[i + 1][1] * M_PER_DEG_LAT;
    area2 += x1 * y2 - x2 * y1;
    perim += Math.hypot(x2 - x1, y2 - y1);
  }
  return { area: Math.abs(area2) / 2, perimeter: perim };
}

export function buildingMetrics(feature) {
  const g = feature?.geometry;
  const ring = g?.type === 'Polygon' ? g.coordinates?.[0]
    : g?.type === 'MultiPolygon' ? g.coordinates?.[0]?.[0] : null;
  if (!ring || ring.length < 4) return null;
  const mPerDegLon = M_PER_DEG_LAT * Math.cos((ring[0][1] * Math.PI) / 180);
  const { area, perimeter } = ringAreaPerimeter(ring, mPerDegLon);
  const height = feature.properties?.height || 12;
  const floors = Math.max(1, Math.round(height / FLOOR_HEIGHT_M));
  const floorM2 = area * floors;
  return {
    footprintM2: area,
    facadeM2: perimeter * height,
    floorM2,
    dwellings: Math.max(1, Math.round(floorM2 / AVG_DWELLING_M2)),
    factors: feature.properties?.hvi_factors || {},
  };
}

// Aggregate the zone-level geometry once; reused for every intervention.
export function zoneCostContext(buildingsGeoJSON, zoneGeojson) {
  const feats = buildingsGeoJSON?.features || [];
  const metrics = feats.map(buildingMetrics).filter(Boolean);
  const totalFootprint = metrics.reduce((s, m) => s + m.footprintM2, 0);

  let zoneAreaM2 = 0;
  const ring = zoneGeojson?.coordinates?.[0];
  if (ring && ring.length > 3) {
    const mPerDegLon = M_PER_DEG_LAT * Math.cos((ring[0][1] * Math.PI) / 180);
    zoneAreaM2 = ringAreaPerimeter(ring, mPerDegLon).area;
  }
  const streetAreaM2 = Math.max(0, zoneAreaM2 - totalFootprint);
  const treeCount = Math.max(1, Math.round(streetAreaM2 / (AVG_STREET_WIDTH_M * TREE_SPACING_M)));
  return { metrics, totalFootprint, zoneAreaM2, streetAreaM2, treeCount };
}

// Cost estimate for one intervention against the zone context.
export function estimateCost(intervention, ctx) {
  const uc = INTERVENTION_UNIT_COST[intervention?.id];
  if (!uc || !ctx) return null;

  // building-based quantities only count buildings the measure applies to
  const applicable = ctx.metrics.filter(
    (m) => !intervention.applicable || intervention.applicable(m.factors)
  );

  let quantity = 0;
  let unit = BASIS_UNIT[uc.basis] || '';
  switch (uc.basis) {
    case 'roof':     quantity = applicable.reduce((s, m) => s + m.footprintM2, 0); break;
    case 'facade':   quantity = applicable.reduce((s, m) => s + m.facadeM2, 0); break;
    case 'floor':    quantity = applicable.reduce((s, m) => s + m.floorM2, 0); break;
    case 'dwelling': quantity = applicable.reduce((s, m) => s + m.dwellings, 0); break;
    case 'tree':     quantity = ctx.treeCount; break;
    case 'street':   quantity = ctx.streetAreaM2; break;
    case 'shade':    quantity = ctx.streetAreaM2 * SHADE_FRACTION; break;
    case 'fixed':    quantity = 1; unit = uc.unit || ''; break;
    default: return null;
  }
  quantity = Math.round(quantity);
  const free = uc.low === 0 && uc.high === 0;
  return {
    free,
    quantity,
    unit,
    perLow: uc.low,
    perHigh: uc.high,
    low: Math.round(quantity * uc.low),
    high: Math.round(quantity * uc.high),
    basis: uc.basis,
  };
}

export function formatEuro(n) {
  if (!n) return '€0';
  if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `€${(n / 1_000).toFixed(n >= 100_000 ? 0 : 1)}k`;
  return `€${Math.round(n)}`;
}
