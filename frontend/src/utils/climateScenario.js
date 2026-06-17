// Future-climate scenario layer.
//
// HVRA is the only group with a future-climate input. We apply a mid-century
// warming delta to each building's land-surface-temperature factor and
// recompute the HVI, so the priority map shows not only who is vulnerable now
// but whose vulnerability grows fastest.
//
// Vegetation buffers future warming (evapotranspiration), so the effective
// local delta is modulated by NDVI: low-vegetation buildings (high ndvi factor
// score) warm more than green ones. Documented, tunable estimate.

import { computeHVI } from './interventionEngine.js';
import { riskTier, BUILDING_GATE } from './hviColors.js';

// LST factor normalization is (T − 30) / 18, so +ΔT °C raises the score by
// ΔT / LST_SPAN before the vegetation modifier.
const LST_SPAN = 18;

export const CLIMATE_SCENARIOS = {
  now: { id: 'now', label: 'Present day', deltaC: 0 },
  mid: { id: 'mid', label: 'Mid-century ~2050', deltaC: 2.0 }, // ≈ SSP2-4.5 Mediterranean summer
};

// vegetation modifier: 0.7× (well-vegetated) … 1.3× (bare) of the headline delta
function vegFactor(ndviScore) {
  const s = ndviScore ?? 0.5; // high score = low vegetation
  return 0.7 + 0.6 * Math.max(0, Math.min(1, s));
}

/**
 * Apply a warming delta to a buildings FeatureCollection, returning a new one
 * with bumped LST factor scores and recomputed HVI. Preserves hvi_score_now.
 */
export function applyClimateScenario(buildingsGeoJSON, deltaC) {
  if (!buildingsGeoJSON?.features || !deltaC) return buildingsGeoJSON;

  const features = buildingsGeoJSON.features.map((f) => {
    const factors = f.properties?.hvi_factors;
    if (!factors?.lst) return f;
    const localDelta = deltaC * vegFactor(factors.ndvi?.score);
    const newLst = Math.max(0, Math.min(1, factors.lst.score + localDelta / LST_SPAN));
    const newFactors = { ...factors, lst: { ...factors.lst, score: newLst } };
    const newScore = computeHVI(newFactors);
    return {
      ...f,
      properties: {
        ...f.properties,
        hvi_score_now: f.properties.hvi_score_now ?? f.properties.hvi_score,
        hvi_score: Math.round(newScore * 10) / 10,
        hvi_factors: newFactors,
      },
    };
  });

  return { ...buildingsGeoJSON, features };
}

/**
 * Compare present vs future: zone means and how many buildings cross the
 * building-intervention gate (BUILDING_GATE) under warming.
 */
export function compareScenarios(buildingsNow, deltaC) {
  const now = buildingsNow?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!now.length) return null;
  const future = applyClimateScenario(buildingsNow, deltaC).features;

  const meanNow = now.reduce((s, f) => s + (f.properties.hvi_score ?? 0), 0) / now.length;
  const meanFuture = future.reduce((s, f) => s + (f.properties.hvi_score ?? 0), 0) / now.length;

  let crossings = 0;
  let worstGrowth = { delta: -1, idx: -1 };
  now.forEach((f, i) => {
    const a = f.properties.hvi_score ?? 0;
    const b = future[i].properties.hvi_score ?? 0;
    if (a < BUILDING_GATE && b >= BUILDING_GATE) crossings += 1;
    const d = b - a;
    if (d > worstGrowth.delta) worstGrowth = { delta: d, idx: i };
  });

  return {
    meanNow,
    meanFuture,
    meanDelta: meanFuture - meanNow,
    gateCrossings: crossings,
    fastestGrowthDelta: Math.max(0, worstGrowth.delta),
    tierNow: riskTier(meanNow).label,
    tierFuture: riskTier(meanFuture).label,
  };
}
