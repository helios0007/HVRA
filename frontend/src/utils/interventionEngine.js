// What-if engine: apply interventions to a building's 12 HVI factors and
// recompute the composite score instantly — no re-simulation needed.
//
// HVI = 10 × Σ(weight_i × score_i), weights sum to 1.00 (set by the backend).

import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';

const clamp01 = (v) => Math.max(0, Math.min(1, v));

export function computeHVI(factors) {
  let total = 0;
  for (const f of Object.values(factors)) {
    total += (f.weight ?? 0) * (f.score ?? 0.5);
  }
  return Math.max(0, Math.min(10, total * 10));
}

// Apply one intervention's factor deltas. Interventions can only improve
// (lower) a factor — `set` floors at the target, `add` subtracts.
function applyDeltas(factors, deltas) {
  const out = { ...factors };
  for (const [key, delta] of Object.entries(deltas)) {
    if (!out[key]) continue;
    let score = out[key].score;
    if (delta.set !== undefined) score = Math.min(score, delta.set);
    if (delta.add !== undefined) score = score + delta.add;
    out[key] = { ...out[key], score: clamp01(score) };
  }
  return out;
}

// Apply a set of interventions (by id) to a building's factors.
// Only interventions applicable to THIS building take effect.
export function applyInterventions(factors, interventionIds) {
  let current = factors;
  for (const id of interventionIds) {
    const intervention = INTERVENTION_CATALOG.find((i) => i.id === id);
    if (!intervention) continue;
    if (intervention.applicable && !intervention.applicable(current)) continue;
    current = applyDeltas(current, intervention.factorDeltas);
  }
  return current;
}

// Rank interventions for one building by how much HVI they would remove.
export function rankInterventionsForBuilding(factors, limit = 3) {
  if (!factors) return [];
  const baseline = computeHVI(factors);
  const ranked = [];
  for (const intervention of INTERVENTION_CATALOG) {
    if (intervention.applicable && !intervention.applicable(factors)) continue;
    const after = applyDeltas(factors, intervention.factorDeltas);
    const deltaHVI = baseline - computeHVI(after);
    if (deltaHVI > 0.01) {
      ranked.push({ intervention, deltaHVI });
    }
  }
  ranked.sort((a, b) => b.deltaHVI - a.deltaHVI);
  return ranked.slice(0, limit);
}

// Apply interventions across a whole buildings FeatureCollection.
// Returns a new FeatureCollection with updated hvi_score / hvi_factors,
// preserving the original score in hvi_score_before.
export function applyInterventionsToZone(buildingsGeoJSON, interventionIds) {
  if (!buildingsGeoJSON?.features || !interventionIds.length) return buildingsGeoJSON;

  const features = buildingsGeoJSON.features.map((f) => {
    const factors = f.properties?.hvi_factors;
    if (!factors) return f;
    const newFactors = applyInterventions(factors, interventionIds);
    const newScore = computeHVI(newFactors);
    return {
      ...f,
      properties: {
        ...f.properties,
        hvi_score: Math.round(newScore * 10) / 10,
        hvi_score_before: f.properties.hvi_score_before ?? f.properties.hvi_score,
        hvi_factors: newFactors,
      },
    };
  });

  return { ...buildingsGeoJSON, features };
}

// Zone-level summary for an intervention set: mean HVI before/after,
// buildings affected, and per-intervention zone impact for ranking cards.
export function summarizeZoneImpact(buildingsGeoJSON, interventionIds) {
  const feats = buildingsGeoJSON?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!feats.length) return null;

  const before = feats.map((f) => f.properties.hvi_score_before ?? f.properties.hvi_score);
  const meanBefore = before.reduce((a, b) => a + b, 0) / before.length;

  const after = feats.map((f) => {
    const nf = applyInterventions(f.properties.hvi_factors, interventionIds);
    return computeHVI(nf);
  });
  const meanAfter = after.reduce((a, b) => a + b, 0) / after.length;

  return {
    meanBefore,
    meanAfter,
    delta: meanBefore - meanAfter,
    count: feats.length,
  };
}

// Recompute zone statistics for a buildings FeatureCollection (used for the
// climate-scenario view, where HVI is bumped client-side).
export function computeZoneStats(buildingsGeoJSON) {
  const scores = (buildingsGeoJSON?.features || [])
    .map((f) => f.properties?.hvi_score)
    .filter((s) => s !== undefined && s !== null);
  if (!scores.length) return null;
  const sorted = [...scores].sort((a, b) => a - b);
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const median = sorted[Math.floor(sorted.length / 2)];
  return {
    count: scores.length,
    mean_hvi: Math.round(mean * 10) / 10,
    median_hvi: Math.round(median * 10) / 10,
    max_hvi: Math.max(...scores),
    min_hvi: Math.min(...scores),
    high_vulnerability: scores.filter((s) => s >= 7).length,
    medium_vulnerability: scores.filter((s) => s >= 4 && s < 7).length,
    low_vulnerability: scores.filter((s) => s < 4).length,
  };
}

// For the catalog cards: zone-wide effect of each single intervention.
export function rankInterventionsForZone(buildingsGeoJSON) {
  const feats = buildingsGeoJSON?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!feats.length) return [];

  return INTERVENTION_CATALOG.map((intervention) => {
    let totalDelta = 0;
    let affected = 0;
    for (const f of feats) {
      const factors = f.properties.hvi_factors;
      if (intervention.applicable && !intervention.applicable(factors)) continue;
      const d = computeHVI(factors) - computeHVI(applyDeltas(factors, intervention.factorDeltas));
      if (d > 0.01) {
        totalDelta += d;
        affected += 1;
      }
    }
    return {
      intervention,
      affected,
      meanZoneDelta: feats.length ? totalDelta / feats.length : 0,
    };
  })
    .filter((r) => r.affected > 0)
    .sort((a, b) => b.meanZoneDelta - a.meanZoneDelta);
}
