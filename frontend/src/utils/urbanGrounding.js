// Bridge from our urban analysis to the building-level pipeline ("deep grounding").
//
// Her pipeline applies a single UHI delta (°C) to every outdoor-temperature hour
// before computing room thermal scores: T_outdoor = T_epw + uhi_delta. By default
// she looks that delta up from a Barcelona barri-average table (~0–2.5°C, city
// default 1.5°C). When we hand her our OWN measured value, the building scores
// reflect the zone we actually analysed instead of a generic city average.
//
// We don't run a rural baseline, so we INFER the urban warming from the zone's
// measured heat load. The earlier "mean UTCI − 30°C" basis read 0 for real zones
// (their mean UTCI, averaged over 10:00–18:00, is ~27–29°C even when heat stress
// is high). Instead we blend two always-present, monotonic signals:
//   • heat-stress fraction — share of analysed hours in thermal stress, and
//   • peak UTCI above a Barcelona July daytime reference (~28°C).
// Blended and clamped to the plausible Barcelona UHI band, so a hot zone never
// reads 0 and the value stays in the same ballpark as her barri table.

const PEAK_REFERENCE_C = 28.0;     // Barcelona July daytime UTCI reference
const HEAT_STRESS_WEIGHT = 2.0;    // fully heat-stressed zone → +2.0°C
const PEAK_EXCESS_WEIGHT = 0.35;   // per °C of peak UTCI above the reference
const UHI_MIN_C = 0.5;
const UHI_MAX_C = 3.5;

function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

/**
 * Derive an urban UHI delta (°C) from an urban analysis result, or null if the
 * analysis has no usable heat field (caller then lets her tool fall back to its
 * barri-table lookup).
 *
 * @param {object} vulnerabilityAnalysis - selectedZone.vulnerability_analysis
 * @returns {number|null} UHI delta in °C, rounded to 0.1, clamped to [0.5, 3.5]
 */
export function urbanUhiDelta(vulnerabilityAnalysis) {
  const cc = vulnerabilityAnalysis?.climate_context || {};
  const peak = cc.peak_utci_celsius;
  const mean = cc.mean_utci_celsius;
  let pct = cc.heat_stress_hours_pct;          // 0–100
  if (typeof pct === 'number' && pct <= 1) pct *= 100; // tolerate 0–1 fractions

  const hasPeak = typeof peak === 'number' && !Number.isNaN(peak);
  const hasPct = typeof pct === 'number' && !Number.isNaN(pct);

  if (hasPct || hasPeak) {
    const frac = hasPct ? pct / 100 : 0;
    const peakExcess = hasPeak ? Math.max(0, peak - PEAK_REFERENCE_C) : 0;
    const raw = HEAT_STRESS_WEIGHT * frac + PEAK_EXCESS_WEIGHT * peakExcess;
    return Math.round(clamp(raw, UHI_MIN_C, UHI_MAX_C) * 10) / 10;
  }

  // Last-resort fallback: mean UTCI excess over a cooler reference.
  if (typeof mean === 'number' && !Number.isNaN(mean)) {
    return Math.round(clamp(mean - 25, UHI_MIN_C, UHI_MAX_C) * 10) / 10;
  }
  return null;
}

/**
 * Compact grounding context for display + form submission in the building tab.
 * @param {object} vulnerabilityAnalysis - selectedZone.vulnerability_analysis
 * @returns {{uhiDelta:number|null, meanUtci:number|null, peakUtci:number|null, heatStressPct:number|null, zoneScore:number|null}}
 */
export function urbanGroundingContext(vulnerabilityAnalysis) {
  const cc = vulnerabilityAnalysis?.climate_context || {};
  return {
    uhiDelta: urbanUhiDelta(vulnerabilityAnalysis),
    meanUtci: typeof cc.mean_utci_celsius === 'number' ? cc.mean_utci_celsius : null,
    peakUtci: typeof cc.peak_utci_celsius === 'number' ? cc.peak_utci_celsius : null,
    heatStressPct: typeof cc.heat_stress_hours_pct === 'number' ? cc.heat_stress_hours_pct : null,
    zoneScore: typeof vulnerabilityAnalysis?.score === 'number' ? vulnerabilityAnalysis.score : null,
  };
}
