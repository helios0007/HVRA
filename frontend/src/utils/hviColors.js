// Single source of truth for HVI colors and labels.
// Used by the 3D explorer, the 2D HVI map, and the side panels so every
// view shows exactly the same color for the same score.

// Sequential ColorBrewer YlOrRd: pale (low vulnerability) → deep red (high).
// Tuned so the realistic urban band (≈4–7) spans orange→red for strong on-screen
// contrast — a flat 4.9–6.1 zone now reads clearly instead of "all orange".
export const HVI_STOPS = [
  [0, [255, 255, 204]],   // #ffffcc  pale yellow (near-white)
  [3, [255, 237, 160]],   // #ffeda0
  [4, [254, 178, 76]],    // #feb24c  orange
  [5, [253, 141, 60]],    // #fd8d3c
  [6, [252, 78, 42]],     // #fc4e2a  orange-red
  [7, [227, 26, 28]],     // #e31a1c  red
  [8.5, [177, 0, 38]],    // #b10026
  [10, [128, 0, 38]],     // #800026  deep red
];

// Continuous interpolation across the legend hues (absolute 0-10 scale)
export function getHVIColorRGB(score) {
  const s = Math.max(0, Math.min(10, score ?? 5));
  for (let i = 0; i < HVI_STOPS.length - 1; i++) {
    const [v0, c0] = HVI_STOPS[i];
    const [v1, c1] = HVI_STOPS[i + 1];
    if (s >= v0 && s <= v1) {
      const t = v1 === v0 ? 0 : (s - v0) / (v1 - v0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
      ];
    }
  }
  return [255, 165, 0];
}

export function getHVIColorHex(score) {
  const [r, g, b] = getHVIColorRGB(score);
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

// Risk label aligned to the tier thresholds below (single threshold set).
export function riskLabel(score) {
  const s = score ?? 5;
  if (s >= 7.0) return 'Critical';
  if (s >= 5.5) return 'High';
  if (s >= 4.0) return 'Moderate';
  return 'Low';
}

// CSS gradient matching HVI_STOPS — use for every legend
export const HVI_GRADIENT_CSS =
  'linear-gradient(90deg, #ffffcc 0%, #ffeda0 30%, #feb24c 40%, #fd8d3c 50%, #fc4e2a 60%, #e31a1c 70%, #b10026 85%, #800026 100%)';

// Clip the extreme tails of a score list and return [low, high] for relative
// (zone-stretched) coloring, so a couple of outliers don't flatten everything
// else. Default clips ~10% off each end (advisor request).
export function clippedRange(scores, tail = 0.1) {
  const vals = (scores || []).filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (vals.length < 4) return vals.length ? [vals[0], vals[vals.length - 1]] : [0, 10];
  const lo = vals[Math.floor(tail * (vals.length - 1))];
  const hi = vals[Math.ceil((1 - tail) * (vals.length - 1))];
  return hi > lo ? [lo, hi] : [vals[0], vals[vals.length - 1]];
}

// ---- Risk tiers & decision thresholds (single source of truth) ----
// HVI is a 0–10 composite index (index points, NOT °C).
// SAFE_THRESHOLD: below this, no intervention is needed.
// BUILDING_GATE: if the zone stays at/above this after urban-scale measures,
// building-level analysis (Layer 1) is warranted — the "decision gate".
export const SAFE_THRESHOLD = 4.0;
export const BUILDING_GATE = 5.5;

export const HVI_TIERS = [
  { min: 0, max: 4.0, label: 'Low', color: '#feb24c', action: 'No intervention needed' },
  { min: 4.0, max: 5.5, label: 'Moderate', color: '#fd8d3c', action: 'Street-level measures recommended' },
  { min: 5.5, max: 7.0, label: 'High', color: '#fc4e2a', action: 'Priority zone — urban + building measures' },
  { min: 7.0, max: 10, label: 'Critical', color: '#b10026', action: 'Immediate action — full retrofit pathway' },
];

export function riskTier(score) {
  const s = score ?? 5;
  return HVI_TIERS.find((t) => s < t.max) || HVI_TIERS[HVI_TIERS.length - 1];
}
