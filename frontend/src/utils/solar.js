// Solar geometry for the climatic section.
// Standard astronomical formulas (Cooper declination + horizontal coordinates);
// accurate to well under 1° — more than enough for shadow casting at urban scale.

const DEG = Math.PI / 180;

// Solar declination (degrees) for a day of year (Cooper 1969)
export function declination(dayOfYear) {
  return 23.45 * Math.sin(DEG * (360 / 365) * (284 + dayOfYear));
}

/**
 * Sun position for a latitude, day of year and *solar* hour (12 = solar noon).
 * Returns { altitudeDeg, azimuthDeg } — azimuth from north, clockwise (S = 180).
 */
export function solarPosition(latDeg, dayOfYear, solarHour) {
  const phi = latDeg * DEG;
  const delta = declination(dayOfYear) * DEG;
  const H = (solarHour - 12) * 15 * DEG; // hour angle, + after noon

  const sinAlt = Math.sin(phi) * Math.sin(delta) + Math.cos(phi) * Math.cos(delta) * Math.cos(H);
  const altitude = Math.asin(Math.max(-1, Math.min(1, sinAlt)));

  const cosAz =
    (Math.sin(delta) - sinAlt * Math.sin(phi)) / (Math.cos(altitude) * Math.cos(phi) || 1e-9);
  let azimuth = Math.acos(Math.max(-1, Math.min(1, cosAz))) / DEG; // 0..180 from north
  if (H > 0) azimuth = 360 - azimuth; // afternoon → western sky

  return { altitudeDeg: altitude / DEG, azimuthDeg: azimuth };
}

/**
 * Project the sun onto a vertical section plane.
 * sectionBearingDeg = compass bearing of the section's +x axis (0 = north, 90 = east).
 *
 * Returns:
 *   shadowDir   — +1 / −1: direction shadows fall along the section x axis
 *   shadowRatio — shadow length per metre of building height *along the section*
 *   inPlaneAltDeg — apparent sun angle drawn in the section
 *   weak        — true when the sun is nearly perpendicular to the cut
 *                 (shadows fall across the street, not along the drawing)
 */
export function projectSunOntoSection(altitudeDeg, azimuthDeg, sectionBearingDeg) {
  const alt = altitudeDeg * DEG;
  const az = azimuthDeg * DEG;
  const bearing = sectionBearingDeg * DEG;

  // Unit vector pointing toward the sun
  const east = Math.cos(alt) * Math.sin(az);
  const north = Math.cos(alt) * Math.cos(az);
  const up = Math.sin(alt);

  // Component of the horizontal sun direction along the section x axis
  const along = east * Math.sin(bearing) + north * Math.cos(bearing);

  const shadowDir = along >= 0 ? -1 : 1; // shadow falls away from the sun
  const shadowRatio = up > 1e-6 ? Math.abs(along) / up : 0;
  const inPlaneAltDeg = Math.atan2(up, Math.abs(along)) / DEG;

  return {
    shadowDir,
    shadowRatio,
    inPlaneAltDeg,
    weak: Math.abs(along) < 0.12,
  };
}

// Day-of-year helpers for the UI presets
export const SUMMER_SOLSTICE_DOY = 172; // June 21
