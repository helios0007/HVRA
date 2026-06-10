// Single source of truth for HVI colors and labels.
// Used by the 3D explorer, the 2D HVI map, and the side panels so every
// view shows exactly the same color for the same score.

export const HVI_STOPS = [
  [0, [144, 238, 144]],   // light green
  [3, [255, 255, 0]],     // yellow
  [4, [255, 165, 0]],     // orange
  [6, [255, 69, 0]],      // orange-red
  [8, [139, 0, 0]],       // dark red
  [10, [139, 0, 0]],
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

export function riskLabel(score) {
  const s = score ?? 5;
  if (s >= 8) return 'Critical';
  if (s >= 6) return 'High';
  if (s >= 4) return 'Medium';
  if (s >= 3) return 'Low-Medium';
  return 'Low';
}

// CSS gradient matching HVI_STOPS — use for every legend
export const HVI_GRADIENT_CSS =
  'linear-gradient(90deg, #90EE90 0%, #FFFF00 30%, #FFA500 40%, #FF4500 60%, #8B0000 80%)';
