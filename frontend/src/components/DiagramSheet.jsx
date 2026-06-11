// Diagram sheet — generated when the user finalizes an intervention set.
// Climatic section (computed sun/shadows/LST curve) + HVI waterfall +
// factor fingerprint, each exportable as SVG for studio panels.

import { useMemo, useRef, useState } from 'react';
import { buildSection } from '../utils/sectionGenerator';
import { INTERVENTION_CATALOG } from '../data/interventionCatalog.js';
import ClimaticSection from './ClimaticSection';
import HVIWaterfall from './HVIWaterfall';
import FactorFingerprint from './FactorFingerprint';

function downloadSVG(node, filename) {
  if (!node) return;
  const clone = node.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], {
    type: 'image/svg+xml;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function meanFactors(fc) {
  const feats = fc?.features?.filter((f) => f.properties?.hvi_factors) || [];
  if (!feats.length) return null;
  const sums = {};
  for (const f of feats) {
    for (const [k, v] of Object.entries(f.properties.hvi_factors)) {
      if (!sums[k]) sums[k] = { score: 0, weight: v.weight };
      sums[k].score += v.score;
    }
  }
  const out = {};
  for (const [k, v] of Object.entries(sums)) out[k] = { score: v.score / feats.length, weight: v.weight };
  return out;
}

const HOURS = [
  { label: '12:00', value: 12 },
  { label: '15:00', value: 15 },
  { label: '17:00', value: 17 },
  { label: '🌙 Night', value: 'night' },
];

export default function DiagramSheet({ buildings, whatIfBuildings, activeIds, zoneFactors, onClose }) {
  const [orientation, setOrientation] = useState('NS');
  const [position, setPosition] = useState(0.5);
  const [solarHour, setSolarHour] = useState(15);

  const sectionRef = useRef(null);
  const waterfallRef = useRef(null);
  const fingerprintRef = useRef(null);

  // Landsat zone mean LST recovered from the factor score (score = (T−30)/18)
  const zoneLstC = 30 + (zoneFactors?.lst?.score ?? 0.6) * 18;

  const section = useMemo(
    () => buildSection(buildings, { orientation, position, solarHour, activeIds, zoneLstC }),
    [buildings, orientation, position, solarHour, activeIds, zoneLstC]
  );

  const activeNames = useMemo(
    () => INTERVENTION_CATALOG.filter((iv) => activeIds.includes(iv.id)).map((iv) => iv.name),
    [activeIds]
  );

  const factorsBefore = useMemo(() => meanFactors(buildings), [buildings]);
  const factorsAfter = useMemo(
    () => (activeIds.length ? meanFactors(whatIfBuildings) : null),
    [whatIfBuildings, activeIds]
  );

  return (
    <div className="diagram-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="diagram-sheet">
        <div className="diagram-header">
          <div>
            <h2>Climatic diagrams</h2>
            <p>
              Computed drawings — solar geometry, cast shadows and Landsat surface temperature
              for the selected intervention set.
            </p>
          </div>
          <button className="diagram-close" onClick={onClose}>✕</button>
        </div>

        {/* controls */}
        <div className="diagram-controls">
          <div className="diagram-control">
            <label>Cut</label>
            <div className="diagram-chips">
              <button className={orientation === 'NS' ? 'on' : ''} onClick={() => setOrientation('NS')}>S–N</button>
              <button className={orientation === 'EW' ? 'on' : ''} onClick={() => setOrientation('EW')}>W–E</button>
            </div>
          </div>
          <div className="diagram-control grow">
            <label>Position {(position * 100).toFixed(0)}%</label>
            <input
              type="range" min="5" max="95" value={position * 100}
              onChange={(e) => setPosition(Number(e.target.value) / 100)}
            />
          </div>
          <div className="diagram-control">
            <label>Solar time</label>
            <div className="diagram-chips">
              {HOURS.map((h) => (
                <button key={h.value} className={solarHour === h.value ? 'on' : ''}
                  onClick={() => setSolarHour(h.value)}>{h.label}</button>
              ))}
            </div>
          </div>
        </div>

        {/* 1 — climatic section */}
        <div className="diagram-card">
          <div className="diagram-card-head">
            <h3>Climatic section</h3>
            <button className="diagram-dl" onClick={() => downloadSVG(sectionRef.current, 'climatic-section.svg')}>
              ⬇ SVG
            </button>
          </div>
          <ClimaticSection ref={sectionRef} section={section} activeNames={activeNames} />
        </div>

        {/* 2 — waterfall */}
        {activeIds.length > 0 && (
          <div className="diagram-card">
            <div className="diagram-card-head">
              <h3>HVI waterfall</h3>
              <button className="diagram-dl" onClick={() => downloadSVG(waterfallRef.current, 'hvi-waterfall.svg')}>
                ⬇ SVG
              </button>
            </div>
            <HVIWaterfall ref={waterfallRef} buildings={buildings} activeIds={activeIds} />
          </div>
        )}

        {/* 3 — fingerprint */}
        <div className="diagram-card half">
          <div className="diagram-card-head">
            <h3>Factor fingerprint</h3>
            <button className="diagram-dl" onClick={() => downloadSVG(fingerprintRef.current, 'factor-fingerprint.svg')}>
              ⬇ SVG
            </button>
          </div>
          <FactorFingerprint ref={fingerprintRef} before={factorsBefore} after={factorsAfter} />
        </div>

        <p className="diagram-note">
          Sun position computed for Barcelona (41.4°N), June 21. Shadows cast from LOD1 building
          heights onto the section plane. Surface temperature: Landsat zone mean modulated by
          computed shading; intervention deltas use the published coefficients from the catalog.
          Night view models nocturnal heat release — retention scales with canyon H/W after
          Oke (1981). All values in °C here; HVI scores are index points. Drawings export as
          SVG — editable in Illustrator.
        </p>
      </div>
    </div>
  );
}
