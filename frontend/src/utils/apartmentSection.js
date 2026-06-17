// Apartment-scale "coupled performance" section model.
//
// Picks the worst-case persona dwelling in the zone — top-floor, SW-facing,
// pre-1980, elderly, no air-conditioning (the Barceloneta resident) — and
// models the heat paths into that one apartment: solar gain on the SW facade,
// conduction through the roof and poor envelope, and the cross-ventilation
// path or its absence. Produces a BEFORE state and an AFTER state with the
// dwelling's top retrofits applied, with the modelled indoor reduction.
//
// Indoor operative temperature is a transparent additive model (documented
// coefficients), not a full energy simulation — enough to make the design
// argument verifiable on the drawing.

import { rankInterventionsForBuilding } from './interventionEngine.js';
import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';

const C = {
  topFloorPenalty: 2.0, // °C, top floor under the roof
  kRoof: 4.0, // °C at roofGain = 1
  kWall: 2.5, // °C at wallConduction = 1
  kSolar: 3.5, // °C at solarGain = 1
  ventTrapped: 1.5, // °C added when single-aspect (no cross ventilation)
  ventRelief: -1.5, // °C when cross ventilation is enabled
  comfortCeiling: 30, // °C operative — above this the elderly resident is at risk
};

function personaScore(f) {
  if (!f) return -1;
  return (
    (f.construction_era?.score ?? 0) * 1.2 +
    (f.roof_type?.score ?? 0) * 1.0 +
    (f.elderly_population?.score ?? 0) * 1.2 +
    (f.no_ac?.score ?? 0) * 1.0 +
    (f.lst?.score ?? 0) * 0.8
  );
}

function indoorTemp(baseOutdoor, m) {
  return (
    baseOutdoor +
    C.topFloorPenalty +
    C.kRoof * m.roofGain * 0.6 +
    C.kWall * m.wallConduction * 0.5 +
    C.kSolar * m.solarGain * 0.5 +
    (m.ventCross ? C.ventRelief : C.ventTrapped)
  );
}

/**
 * @param buildings FeatureCollection (scenario-adjusted)
 * @param activeIds user-selected interventions (if empty, uses the dwelling's top-3)
 * @param peakUtci  zone peak UTCI °C (felt temperature)
 */
export function buildApartment(buildings, activeIds = [], peakUtci = 34) {
  const feats = buildings?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!feats.length) return null;

  // pick the persona dwelling
  let best = feats[0];
  let bestScore = -1;
  for (const f of feats) {
    const s = personaScore(f.properties.hvi_factors);
    if (s > bestScore) {
      bestScore = s;
      best = f;
    }
  }
  const f = best.properties.hvi_factors;
  const year = best.properties.construction_year;

  // before-state heat-path intensities (0–1)
  const roofGain = f.roof_type?.score ?? 0.6;
  const wallConduction = f.construction_era?.score ?? 0.7;
  const solarGain = Math.min(1, 0.4 + 0.6 * (f.lst?.score ?? 0.6));
  const ventCrossBefore = (f.street_canyon?.score ?? 0.5) < 0.5; // dense canyon → single-aspect
  const before = { roofGain, wallConduction, solarGain, ventCross: ventCrossBefore };

  // which retrofits: user's selection (those applicable here) or the top-3
  let chosen;
  if (activeIds.length) {
    chosen = INTERVENTION_CATALOG.filter(
      (iv) => activeIds.includes(iv.id) && (!iv.applicable || iv.applicable(f))
    );
  } else {
    chosen = rankInterventionsForBuilding(f, 3).map((r) => r.intervention);
  }
  const ids = new Set(chosen.map((iv) => iv.id));

  // after-state: each retrofit attenuates the matching heat path
  const after = { ...before };
  const applied = [];
  if (ids.has('cool_roof') || ids.has('green_roof')) {
    after.roofGain = roofGain * 0.35;
    applied.push({ label: ids.has('green_roof') ? 'Green roof' : 'Cool roof', path: 'roof' });
  }
  if (ids.has('envelope_retrofit') || ids.has('facade_greening')) {
    after.wallConduction = wallConduction * 0.4;
    applied.push({ label: ids.has('envelope_retrofit') ? 'External insulation' : 'Green facade', path: 'wall' });
  }
  if (ids.has('shade_structures') || ids.has('facade_greening') || ids.has('envelope_retrofit')) {
    after.solarGain = solarGain * 0.4;
    applied.push({ label: 'External shading on SW glazing', path: 'solar' });
  }
  if (ids.has('envelope_retrofit')) {
    after.ventCross = true; // retrofit includes a cross-ventilation strategy
    applied.push({ label: 'Cross-ventilation enabled', path: 'vent' });
  }

  const indoorBefore = indoorTemp(peakUtci, before);
  const indoorAfter = indoorTemp(peakUtci, after);

  return {
    persona: {
      year: year || null,
      label: 'Top-floor dwelling · SW facade · pre-1980 · elderly resident · no A/C',
      hviBefore: best.properties.hvi_score ?? null,
    },
    peakUtci,
    before,
    after,
    indoorBefore,
    indoorAfter,
    indoorReduction: indoorBefore - indoorAfter,
    comfortCeiling: C.comfortCeiling,
    retrofits: chosen.map((iv) => ({ id: iv.id, icon: iv.icon, name: iv.name })),
    applied,
  };
}
