// Regenerative impact engine.
//
// Translates the tool's headline output from "degrees avoided" to "harm
// avoided" (health capital) and "give-back beyond the property line" (ecology).
// Every coefficient is named and documented so the numbers are defensible and
// tunable — they are modelled estimates, not measurements.
//
// HEALTH model — heat-attributable mortality among the elderly, anchored to the
// Spanish/Madrid heat-health literature (Díaz, Linares, Carmona; MCC network).
// We scale a baseline elderly heat-mortality rate by each cluster's HVI
// relative to the city mid-scale, so a more vulnerable cluster carries more
// avoidable harm. Interventions lower HVI → lower attributable harm.
//
// GIVE-BACK model — what each measure does OUTSIDE the window: dwellings kept
// off air-conditioning (avoided anthropogenic waste heat + avoided peak grid
// load), roof area whose albedo is raised (district radiative give-back), and
// square metres of new vegetation.

import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';

export const HEALTH_MODEL = {
  // Occupancy
  peoplePerM2Residential: 0.025, // ≈ 40 m²/person, dense Mediterranean stock
  avgFloorHeightM: 3.0,
  m2PerDwelling: 90,

  // Heat-attributable mortality in a hot Mediterranean summer, per 100k of the
  // 75+ population, at the city mid-scale (HVI ≈ refHVI). Documented estimate
  // from Spanish heat-mortality studies.
  baseHeatMortalityPer100kElderly: 130,
  refHVI: 5.0,
  // Fraction of that harm that is addressable through building/urban exposure
  // (the rest is clinical/behavioural and outside our lever).
  exposureAttributableFraction: 0.6,
  elderlyShareCap: 0.25, // factor score 1.0 ↔ 25% population 65+

  // Morbidity: heat-related ED visits / hospitalisations per heat death
  morbidityPerDeath: 18,

  // Sleep: tropical nights (Tmin disrupts sleep) modelled from zone LST
  tropicalNightsPerDegLST: 4, // nights per °C of zone LST above the base
  tropicalNightBaseLSTc: 30,
  maxTropicalNights: 80,
};

export const GIVEBACK_MODEL = {
  acPeakKwPerDwelling: 1.2, // peak electrical draw of a room A/C avoided
  acWasteHeatKwPerDwelling: 3.0, // waste heat that A/C would reject to the street
  coolRoofAlbedoDelta: 0.5,
};

// ---- geometry helpers -------------------------------------------------------

function ringAreaM2(ring) {
  if (!ring || ring.length < 4) return 0;
  const lat0 = ring[0][1];
  const mLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  const mLat = 111320;
  let a = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const x1 = ring[i][0] * mLon, y1 = ring[i][1] * mLat;
    const x2 = ring[i + 1][0] * mLon, y2 = ring[i + 1][1] * mLat;
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

function footprintArea(feature) {
  const g = feature.geometry;
  if (!g) return 0;
  if (g.type === 'Polygon') return ringAreaM2(g.coordinates[0]);
  if (g.type === 'MultiPolygon') return g.coordinates.reduce((s, p) => s + ringAreaM2(p[0]), 0);
  return 0;
}

function buildingOccupancy(feature) {
  const area = footprintArea(feature);
  const height = feature.properties?.height || 12;
  const floors = Math.max(1, Math.round(height / HEALTH_MODEL.avgFloorHeightM));
  const floorArea = area * floors;
  const residents = floorArea * HEALTH_MODEL.peoplePerM2Residential;
  const dwellings = Math.max(1, Math.round(floorArea / HEALTH_MODEL.m2PerDwelling));
  const elderlyScore = feature.properties?.hvi_factors?.elderly_population?.score ?? 0.5;
  const elderlyFrac = Math.min(0.30, elderlyScore * HEALTH_MODEL.elderlyShareCap);
  return { area, floors, residents, dwellings, elderly: residents * elderlyFrac };
}

// ---- main -------------------------------------------------------------------

/**
 * @param beforeBuildings FeatureCollection at current state (scenario-adjusted)
 * @param afterBuildings  FeatureCollection with interventions applied (or null)
 * @param activeIds       selected intervention ids
 * @param zoneLstC        zone mean land-surface temperature (°C)
 */
export function computeRegenerativeImpact(beforeBuildings, afterBuildings, activeIds = [], zoneLstC = 42) {
  const feats = beforeBuildings?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!feats.length) return null;

  const H = HEALTH_MODEL;
  const afterFeats = afterBuildings?.features || [];

  let residents = 0, elderly = 0;
  let deathsNow = 0, deathsAfter = 0;
  const catalogById = Object.fromEntries(INTERVENTION_CATALOG.map((iv) => [iv.id, iv]));

  const give = { dwellingsOffAc: 0, avoidedPeakKw: 0, avoidedWasteHeatKw: 0, roofAlbedoM2: 0, greenedM2: 0 };
  const passiveCooling = ['cool_roof', 'green_roof', 'envelope_retrofit', 'facade_greening', 'street_trees', 'shade_structures', 'depave_planting'];

  feats.forEach((f, i) => {
    const occ = buildingOccupancy(f);
    residents += occ.residents;
    elderly += occ.elderly;

    const hviBefore = f.properties.hvi_score ?? 5;
    const hviAfter = afterFeats[i]?.properties?.hvi_score ?? hviBefore;

    const perElderly = (occ.elderly / 1e5) * H.baseHeatMortalityPer100kElderly * H.exposureAttributableFraction;
    deathsNow += perElderly * (hviBefore / H.refHVI);
    deathsAfter += perElderly * (hviAfter / H.refHVI);

    // give-back accounting (only where the measure applies to THIS building)
    const factors = f.properties.hvi_factors;
    const applies = (id) => {
      const iv = catalogById[id];
      return iv && (!iv.applicable || iv.applicable(factors));
    };
    if (activeIds.includes('cool_roof') && applies('cool_roof')) give.roofAlbedoM2 += occ.area;
    if (activeIds.includes('green_roof') && applies('green_roof')) give.greenedM2 += occ.area;
    if (activeIds.includes('depave_planting') && applies('depave_planting')) give.greenedM2 += occ.area * 0.4;
    if (activeIds.includes('facade_greening') && applies('facade_greening')) give.greenedM2 += occ.area * 0.3;

    // dwellings kept off A/C: building currently lacks cooling AND receives a
    // passive measure that removes the need to install it
    const noAcScore = factors?.no_ac?.score ?? 0;
    const getsPassive = passiveCooling.some((id) => activeIds.includes(id) && applies(id));
    if (noAcScore >= 0.5 && getsPassive) {
      give.dwellingsOffAc += occ.dwellings;
    }
  });

  give.avoidedPeakKw = give.dwellingsOffAc * GIVEBACK_MODEL.acPeakKwPerDwelling;
  give.avoidedWasteHeatKw = give.dwellingsOffAc * GIVEBACK_MODEL.acWasteHeatKwPerDwelling;

  const deathsAvoided = Math.max(0, deathsNow - deathsAfter);
  const regenerativeGapDeaths = deathsNow; // addressable heat-harm at current state
  const gapClosedPct = deathsNow > 0 ? (deathsAvoided / deathsNow) * 100 : 0;
  const improveFrac = deathsNow > 0 ? deathsAvoided / deathsNow : 0;

  // sleep
  const nightsNow = Math.min(
    H.maxTropicalNights,
    Math.max(5, (zoneLstC - H.tropicalNightBaseLSTc) * H.tropicalNightsPerDegLST)
  );
  const nightsAvoided = nightsNow * improveFrac;
  const sleepPersonNightsRecovered = nightsAvoided * residents;

  return {
    population: { residents: Math.round(residents), elderly: Math.round(elderly) },
    health: {
      heatDeathsNow: deathsNow,
      heatDeathsAfter: deathsAfter,
      deathsAvoided,
      morbidityAvoided: deathsAvoided * H.morbidityPerDeath,
      sleepPersonNightsRecovered,
      tropicalNightsNow: Math.round(nightsNow),
      regenerativeGapDeaths,
      gapClosedPct,
    },
    giveBack: give,
  };
}
