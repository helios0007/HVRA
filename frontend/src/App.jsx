import { useState, useMemo } from 'react';
import MapView from './components/MapView';
import MapboxDeckView from './components/MapboxDeckView';
import HVI2DMap from './components/HVI2DMap';
import FactorBreakdown from './components/FactorBreakdown';
import DiagramSheet from './components/DiagramSheet';
import LandingPage from './components/LandingPage';
import {
  getHVIColorHex,
  riskLabel,
  riskTier,
  HVI_TIERS,
  SAFE_THRESHOLD,
  BUILDING_GATE,
} from './utils/hviColors';
import {
  applyInterventionsToZone,
  summarizeZoneImpact,
  rankInterventionsForZone,
  computeZoneStats,
} from './utils/interventionEngine';
import { computeWhatIfHeatmap } from './utils/heatmapWhatIf';
import { computeRegenerativeImpact } from './utils/regenerativeImpact';
import { applyClimateScenario, compareScenarios, CLIMATE_SCENARIOS } from './utils/climateScenario';
import { REGEN_TAGS } from './data/interventionCatalog';
import './App.css';

// Explanations and recommended interventions per vulnerability driver
const DRIVER_INFO = {
  thermal_stress_exposure: {
    icon: '🌡️',
    desc: 'Pedestrians experience dangerous heat stress (high UTCI) across large parts of the zone during summer afternoons. Prolonged exposure raises the risk of heat exhaustion, especially for the elderly.',
    actions: ['Shade sails & pergolas', 'Street trees', 'High-albedo pavements', 'Drinking fountains'],
  },
  poor_ventilation: {
    icon: '🌬️',
    desc: 'Narrow street canyons and enclosed blocks block cooling breezes, trapping hot air at street level. Night-time temperatures stay high because heat cannot escape.',
    actions: ['Open ventilation corridors', 'Reduce canyon enclosure', 'Porous ground floors', 'Green facades'],
  },
  high_building_density: {
    icon: '🏢',
    desc: 'Dense built mass absorbs and stores solar heat all day, then re-radiates it at night — the core of the urban heat island effect.',
    actions: ['Green roofs', 'Courtyard greening', 'De-paving & permeable surfaces', 'Cool roof coatings'],
  },
  low_vegetation: {
    icon: '🌳',
    desc: 'Lack of vegetation removes natural cooling through shade and evapotranspiration, leaving surfaces fully exposed to solar radiation.',
    actions: ['Street trees', 'Pocket parks', 'Green roofs', 'Vertical gardens'],
  },
};

function driverInfo(key) {
  return DRIVER_INFO[key] || {
    icon: '⚠️',
    desc: 'This factor contributes to the heat vulnerability of the zone.',
    actions: ['Targeted greening', 'Shade structures'],
  };
}

const PIPELINE_STEPS = [
  'Fetching buildings & geometry',
  'Running thermal simulation (UTCI)',
  'Querying Catastro construction years',
  'Reading satellite LST & NDVI',
  'Loading census-section demographics',
  'Computing HVI for every building',
];

const riskColor = getHVIColorHex;

// Circular gauge for the zone mean HVI
function HVIGauge({ score }) {
  const pct = Math.min(score / 10, 1) * 100;
  const color = riskColor(score);
  return (
    <div className="hvi-gauge">
      <div
        className="hvi-gauge-ring"
        style={{ background: `conic-gradient(${color} ${pct * 3.6}deg, var(--bg-primary) 0deg)` }}
      >
        <div className="hvi-gauge-center">
          <span className="hvi-gauge-value" style={{ color }}>{score.toFixed(1)}</span>
          <span className="hvi-gauge-max">/ 10</span>
        </div>
      </div>
      <div className="hvi-gauge-label" style={{ color }}>{riskLabel(score)} vulnerability</div>
    </div>
  );
}

// Stacked horizontal distribution of risk classes
function RiskDistribution({ stats }) {
  const total = stats.count || 1;
  const segments = [
    { label: 'Low', count: stats.low_vulnerability, color: '#90EE90' },
    { label: 'Medium', count: stats.medium_vulnerability, color: '#FFA500' },
    { label: 'High/Critical', count: stats.high_vulnerability, color: '#FF4500' },
  ];
  return (
    <div className="risk-dist">
      <div className="risk-dist-bar">
        {segments.map((s) => (
          s.count > 0 && (
            <div
              key={s.label}
              className="risk-dist-seg"
              style={{ width: `${(s.count / total) * 100}%`, backgroundColor: s.color }}
              title={`${s.label}: ${s.count} buildings`}
            />
          )
        ))}
      </div>
      <div className="risk-dist-legend">
        {segments.map((s) => (
          <span key={s.label} className="risk-dist-item">
            <i style={{ backgroundColor: s.color }} />
            {s.label} <strong>{s.count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function StatGrid({ stats }) {
  return (
    <div className="stat-grid">
      <div className="stat-cell">
        <span className="stat-cell-value">{stats.count}</span>
        <span className="stat-cell-label">Buildings</span>
      </div>
      <div className="stat-cell">
        <span className="stat-cell-value">{stats.median_hvi?.toFixed(1)}</span>
        <span className="stat-cell-label">Median HVI</span>
      </div>
      <div className="stat-cell">
        <span className="stat-cell-value" style={{ color: riskColor(stats.max_hvi) }}>{stats.max_hvi?.toFixed(1)}</span>
        <span className="stat-cell-label">Max HVI</span>
      </div>
      <div className="stat-cell">
        <span className="stat-cell-value" style={{ color: riskColor(stats.min_hvi) }}>{stats.min_hvi?.toFixed(1)}</span>
        <span className="stat-cell-label">Min HVI</span>
      </div>
    </div>
  );
}

// Present-day ⇄ mid-century climate scenario toggle
function ScenarioToggle({ scenario, setScenario, compare }) {
  return (
    <div className="scenario-toggle">
      <div className="scenario-switch">
        <button className={scenario === 'now' ? 'on' : ''} onClick={() => setScenario('now')}>
          Present day
        </button>
        <button className={scenario === 'mid' ? 'on' : ''} onClick={() => setScenario('mid')}>
          🌡 ~2050 (+2°C)
        </button>
      </div>
      {compare && (
        <p className="scenario-note">
          Under mid-century warming the zone moves <strong>{compare.meanNow.toFixed(1)} → {compare.meanFuture.toFixed(1)}</strong> HVI
          {compare.gateCrossings > 0
            ? `, and ${compare.gateCrossings} building${compare.gateCrossings === 1 ? '' : 's'} cross into the building-intervention gate.`
            : '. Priority shifts to the fastest-warming, least-vegetated blocks.'}
        </p>
      )}
    </div>
  );
}

// Regenerative-ladder tags (adaptation / resilience / regeneration)
function RegenTags({ tags }) {
  if (!tags?.length) return null;
  return (
    <div className="regen-tags">
      {tags.map((t) => {
        const meta = REGEN_TAGS[t];
        if (!meta) return null;
        return (
          <span key={t} className="regen-tag" style={{ borderColor: meta.color, color: meta.color }} title={meta.desc}>
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}

// Health-capital headline: harm avoided, not degrees avoided
function HealthHeadline({ impact, hasInterventions }) {
  if (!impact) return null;
  const h = impact.health;
  const perDecade = (v) => v * 10; // legible cluster-scale framing
  return (
    <div className="health-panel">
      <h4>
        Health capital {hasInterventions ? 'recovered' : 'at risk'}
        <span className="section-hint"> · {impact.population.elderly} residents 65+ in cluster</span>
      </h4>
      {hasInterventions ? (
        <>
          <div className="health-grid">
            <div className="health-cell">
              <span className="health-value">{perDecade(h.deathsAvoided).toFixed(1)}</span>
              <span className="health-label">heat deaths averted / decade</span>
            </div>
            <div className="health-cell">
              <span className="health-value">{Math.round(perDecade(h.morbidityAvoided))}</span>
              <span className="health-label">heat illness cases averted / decade</span>
            </div>
            <div className="health-cell">
              <span className="health-value">{Math.round(h.sleepPersonNightsRecovered).toLocaleString()}</span>
              <span className="health-label">person-nights of sleep recovered / summer</span>
            </div>
          </div>
          <div className="health-gap">
            <div className="health-gap-bar">
              <div className="health-gap-fill" style={{ width: `${Math.min(100, h.gapClosedPct)}%` }} />
            </div>
            <span className="health-gap-label">
              closes <strong>{h.gapClosedPct.toFixed(0)}%</strong> of the cluster's Regenerative Gap
              (avoidable heat-harm in this housing stock)
            </span>
          </div>
        </>
      ) : (
        <p className="health-empty">
          Regenerative Gap: <strong>{perDecade(h.regenerativeGapDeaths).toFixed(1)}</strong> avoidable heat deaths / decade
          and <strong>{Math.round(h.regenerativeGapNights ?? h.tropicalNightsNow)}</strong> tropical nights / summer
          in this cluster. Select interventions to see how much each closes.
        </p>
      )}
    </div>
  );
}

// Ecological give-back beyond the property line
function GiveBackPanel({ give }) {
  if (!give) return null;
  const items = [];
  if (give.dwellingsOffAc > 0)
    items.push([`${give.dwellingsOffAc}`, 'dwellings kept off A/C']);
  if (give.avoidedPeakKw > 0)
    items.push([`${Math.round(give.avoidedPeakKw)} kW`, 'peak grid load avoided']);
  if (give.avoidedWasteHeatKw > 0)
    items.push([`${Math.round(give.avoidedWasteHeatKw)} kW`, 'A/C waste heat kept off the street']);
  if (give.roofAlbedoM2 > 0)
    items.push([`${Math.round(give.roofAlbedoM2).toLocaleString()} m²`, 'roof albedo raised (district give-back)']);
  if (give.greenedM2 > 0)
    items.push([`${Math.round(give.greenedM2).toLocaleString()} m²`, 'new vegetation']);
  if (!items.length) return null;
  return (
    <div className="giveback-panel">
      <h4>Give-back beyond the window <span className="section-hint">· ecology</span></h4>
      <div className="giveback-grid">
        {items.map(([v, l]) => (
          <div key={l} className="giveback-cell">
            <span className="giveback-value">{v}</span>
            <span className="giveback-label">{l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Risk-tier legend: what each band means and what action it calls for
function HVIScaleLegend({ score }) {
  return (
    <div className="hvi-scale-legend">
      <h4>
        HVI risk thresholds <span className="section-hint">(index 0–10)</span>
      </h4>
      {HVI_TIERS.map((t) => {
        const active = score !== undefined && score >= t.min && score < t.max;
        return (
          <div key={t.label} className={`hvi-tier ${active ? 'active' : ''}`}>
            <i style={{ backgroundColor: t.color }} />
            <span className="hvi-tier-range">{t.min.toFixed(1)}–{t.max.toFixed(1)}</span>
            <span className="hvi-tier-label">{t.label}</span>
            <span className="hvi-tier-action">{t.action}</span>
          </div>
        );
      })}
    </div>
  );
}

// Decision gate: is building-level work (Layer 1) needed after urban measures?
function DecisionGate({ before, after, buildings }) {
  const score = after ?? before;
  if (score === undefined || score === null) return null;
  const highCount = buildings?.features?.filter(
    (f) => (f.properties?.hvi_score ?? 0) >= BUILDING_GATE
  ).length ?? 0;

  let cls, icon, verdict, detail;
  if (score < SAFE_THRESHOLD) {
    cls = 'safe';
    icon = '✓';
    verdict = 'Below intervention threshold';
    detail = `Zone HVI ${score.toFixed(1)} < ${SAFE_THRESHOLD.toFixed(1)} — urban-scale measures are sufficient. Building-level retrofit not required.`;
  } else if (score < BUILDING_GATE) {
    cls = 'moderate';
    icon = '◐';
    verdict = 'Street-level measures recommended';
    detail = `Zone HVI ${score.toFixed(1)} sits in the moderate band (${SAFE_THRESHOLD.toFixed(1)}–${BUILDING_GATE.toFixed(1)}). Building-level analysis optional — ${highCount} building${highCount === 1 ? '' : 's'} still ≥ ${BUILDING_GATE.toFixed(1)}.`;
  } else {
    cls = 'high';
    icon = '→';
    verdict = 'Proceed to building-level analysis';
    detail = `Zone HVI ${score.toFixed(1)} ≥ ${BUILDING_GATE.toFixed(1)} after urban measures — escalate ${highCount} high-risk building${highCount === 1 ? '' : 's'} to Layer 1 (envelope retrofit assessment).`;
  }
  return (
    <div className={`decision-gate ${cls}`}>
      <div className="decision-gate-head">
        <span className="decision-gate-icon">{icon}</span>
        <span className="decision-gate-title">Decision gate · {verdict}</span>
      </div>
      <p>{detail}</p>
    </div>
  );
}

// First-use expansion of every acronym in the tool
function Glossary() {
  const terms = [
    ['HVI', 'Heat Vulnerability Index — 0–10 composite of 12 weighted factors (index points, not °C)'],
    ['LST', 'Land Surface Temperature — Landsat 8/9 thermal band, °C'],
    ['NDVI', 'Normalized Difference Vegetation Index — Sentinel-2, 0–1 greenness'],
    ['UTCI', 'Universal Thermal Climate Index — physiological "feels-like" temperature, °C'],
    ['UHI', 'Urban Heat Island — zone LST minus city-mean LST, °C'],
    ['H/W', 'Street canyon height-to-width ratio — controls shading and nocturnal heat retention'],
  ];
  return (
    <details className="glossary">
      <summary>Terminology &amp; definitions</summary>
      <dl>
        {terms.map(([k, v]) => (
          <div key={k} className="glossary-row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function DataSources() {
  const sources = [
    ['Catastro INSPIRE', 'construction years'],
    ['Landsat 8/9', 'surface temperature'],
    ['Sentinel-2', 'NDVI 10m'],
    ['Idescat', 'census sections'],
    ['BCN Open Data', 'income atlas'],
    ['OpenStreetMap', 'green space'],
    ['Infrared SDK', 'UTCI comfort'],
  ];
  return (
    <div className="data-sources">
      <h4>Live data sources</h4>
      <div className="data-sources-list">
        {sources.map(([name, what]) => (
          <span className="source-chip" key={name} title={what}>
            <i className="source-dot" />{name}
          </span>
        ))}
      </div>
    </div>
  );
}

// Ray-casting point-in-ring on [lon,lat] coordinates (no turf dependency).
function pointInRingLL(px, py, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function featureCentroid(feature) {
  const g = feature.geometry;
  if (!g) return null;
  const ring = g.type === 'Polygon' ? g.coordinates?.[0]
    : g.type === 'MultiPolygon' ? g.coordinates?.[0]?.[0] : null;
  if (!ring || !ring.length) return null;
  let x = 0, y = 0;
  for (const [lx, ly] of ring) { x += lx; y += ly; }
  return [x / ring.length, y / ring.length];
}

// Informative dashboard card that doubles as an on/off control.
function ToggleCard({ icon, title, subtitle, metric, metricLabel, on, onClick, accent = '#fb923c' }) {
  return (
    <button
      type="button"
      className={`toggle-card ${on ? 'on' : ''}`}
      onClick={onClick}
      style={{ '--card-accent': accent }}
    >
      <div className="toggle-card-top">
        <span className="toggle-card-icon">{icon}</span>
        <div className="toggle-card-titles">
          <span className="toggle-card-title">{title}</span>
          <span className="toggle-card-sub">{subtitle}</span>
        </div>
        <span className={`toggle-card-switch ${on ? 'on' : ''}`}><span className="toggle-card-knob" /></span>
      </div>
      {metric != null && (
        <div className="toggle-card-metric">
          <span className="toggle-card-metric-value">{metric}</span>
          {metricLabel && <span className="toggle-card-metric-label">{metricLabel}</span>}
        </div>
      )}
    </button>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState('analyze');
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedBuilding, setSelectedBuilding] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [analysisError, setAnalysisError] = useState('');
  const [hviData, setHviData] = useState(null);
  const [contextBuildings, setContextBuildings] = useState(null);
  const [activeInterventions, setActiveInterventions] = useState([]);
  const [showDiagrams, setShowDiagrams] = useState(false);
  const [scenario, setScenario] = useState('now'); // 'now' | 'mid' (~2050)
  const [showLanding, setShowLanding] = useState(true);
  const [showOnlyHighestVulnerable, setShowOnlyHighestVulnerable] = useState(false);
  const [showContextHvi, setShowContextHvi] = useState(false); // color out-of-zone buildings by HVI

  const toggleIntervention = (id) => {
    setActiveInterventions((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  // Future-climate layer: present-day HVI, or warmed to mid-century (~2050).
  // Everything downstream (stats, interventions, drawings, health) reads this.
  const scenarioHvi = useMemo(() => {
    if (!hviData) return null;
    if (scenario === 'now') return hviData;
    const warmed = applyClimateScenario(hviData.buildings_with_hvi, CLIMATE_SCENARIOS.mid.deltaC);
    return { ...hviData, buildings_with_hvi: warmed, hvi_statistics: computeZoneStats(warmed) };
  }, [hviData, scenario]);

  // Present → 2050 comparison for the banner (always vs present-day base)
  const climateCompare = useMemo(
    () => (hviData ? compareScenarios(hviData.buildings_with_hvi, CLIMATE_SCENARIOS.mid.deltaC) : null),
    [hviData]
  );

  // Ranked catalog: zone-wide impact of each intervention alone
  const zoneRanking = useMemo(
    () => rankInterventionsForZone(scenarioHvi?.buildings_with_hvi),
    [scenarioHvi]
  );

  // What-if dataset: buildings recolored with active interventions applied
  const whatIfData = useMemo(() => {
    if (!scenarioHvi || !activeInterventions.length) return null;
    const modified = applyInterventionsToZone(scenarioHvi.buildings_with_hvi, activeInterventions);
    return {
      ...scenarioHvi,
      buildings_with_hvi: modified,
      hvi_statistics: computeZoneStats(modified),
    };
  }, [scenarioHvi, activeInterventions]);

  const whatIfSummary = useMemo(
    () =>
      activeInterventions.length
        ? summarizeZoneImpact(scenarioHvi?.buildings_with_hvi, activeInterventions)
        : null,
    [scenarioHvi, activeInterventions]
  );

  // Mean of each factor across all buildings, for the zone-level methodology panel
  const zoneFactors = useMemo(() => {
    const feats = scenarioHvi?.buildings_with_hvi?.features;
    if (!feats?.length) return null;
    const sums = {};
    let n = 0;
    for (const f of feats) {
      const fac = f.properties?.hvi_factors;
      if (!fac) continue;
      n += 1;
      for (const [k, v] of Object.entries(fac)) {
        if (!sums[k]) sums[k] = { score: 0, weight: v.weight };
        sums[k].score += v.score;
      }
    }
    if (!n) return null;
    const mean = {};
    for (const [k, v] of Object.entries(sums)) {
      mean[k] = { score: v.score / n, weight: v.weight };
    }
    return mean;
  }, [scenarioHvi]);

  // Zone mean land-surface temperature (°C), recovered from the LST factor
  const zoneLstC = 30 + (zoneFactors?.lst?.score ?? 0.6) * 18;
  const peakUtci = selectedZone?.vulnerability_analysis?.climate_context?.peak_utci_celsius
    ?? Math.round(zoneLstC - 4);

  // Regenerative impact — health capital recovered + ecological give-back.
  // The headline output: harm avoided, not degrees avoided.
  const regenImpact = useMemo(
    () =>
      computeRegenerativeImpact(
        scenarioHvi?.buildings_with_hvi,
        whatIfData?.buildings_with_hvi,
        activeInterventions,
        zoneLstC
      ),
    [scenarioHvi, whatIfData, activeInterventions, zoneLstC]
  );

  // UTCI heatmap underlay for the 3D views (from the step-1 simulation)
  const simGrid = selectedZone?.vulnerability_analysis?.simulation_grid;
  const baseHeatmap = useMemo(() => {
    if (!simGrid?.heatmap_image || !simGrid?.bounds) return null;
    return {
      url: simGrid.heatmap_image,
      bounds: simGrid.bounds,
      min: simGrid.min_value,
      max: simGrid.max_value,
      label: simGrid.unit || 'UTCI °C',
    };
  }, [simGrid]);

  // Heatmap re-rendered with the active interventions' cooling deltas,
  // on the SAME color scale so before/after compare directly
  const whatIfHeatmap = useMemo(() => {
    if (!baseHeatmap) return null;
    if (!activeInterventions.length) return baseHeatmap;
    const url = computeWhatIfHeatmap(simGrid, scenarioHvi?.buildings_with_hvi, activeInterventions);
    if (!url) return baseHeatmap; // no raw grid (older analysis) — show original
    return {
      ...baseHeatmap,
      url,
      label: `${simGrid.unit || 'UTCI °C'} · with interventions`,
    };
  }, [baseHeatmap, simGrid, scenarioHvi, activeInterventions]);

  const handleZoneDrawn = async ({ feature, center }) => {
    setLoading(true);
    setLoadingStep(0);
    setAnalysisError('');

    // Advance the visual pipeline steps while the request runs
    const stepTimer = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, PIPELINE_STEPS.length - 1));
    }, 6000);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/urban/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_geojson: feature.geometry,
          center: center,
          size_m: 250,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || 'Heat vulnerability analysis failed');
      }
      setSelectedZone(data);

      setLoadingStep(3);
      const hviResponse = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/hvi/analyze_hvi`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_geojson: feature.geometry,
          center: data.vulnerability_analysis.climate_context.coordinates,
          include_thermal_analysis: true,
        }),
      });

      if (hviResponse.ok) {
        const hviResponse_data = await hviResponse.json();
        setHviData(hviResponse_data);
        // Extract context buildings from thermal analysis if available
        if (hviResponse_data.thermal_analysis?.buffer_zone_buildings) {
          setContextBuildings(hviResponse_data.thermal_analysis.buffer_zone_buildings);
        }
      }

      setActiveTab('explore3d');
    } catch (error) {
      console.error('[ANALYSIS] ERROR:', error);
      setAnalysisError(error.message || 'Failed to analyze zone');
    } finally {
      clearInterval(stepTimer);
      setLoading(false);
    }
  };

  const handleHVITabClick = async () => {
    setActiveTab('hvi');
    if (!hviData && selectedZone) {
      setLoading(true);
      try {
        const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/hvi/analyze_hvi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            zone_geojson: selectedZone.zone_geojson,
            center: selectedZone.vulnerability_analysis.climate_context.coordinates,
            include_thermal_analysis: true,
          }),
        });
        if (!response.ok) throw new Error('HVI analysis failed');
        setHviData(await response.json());
      } catch (error) {
        setAnalysisError(error.message);
      } finally {
        setLoading(false);
      }
    }
  };

  const stats = scenarioHvi?.hvi_statistics;

  // In-zone vs context building split (context = inside Infrared's bbox fetch
  // but outside the drawn polygon) — feeds the 3D Explore dashboard cards.
  const zoneSplit = useMemo(() => {
    const feats = scenarioHvi?.buildings_with_hvi?.features || [];
    const ring = selectedZone?.zone_geojson?.coordinates?.[0];
    if (!feats.length || !ring) return { inZone: feats.length, context: 0 };
    let inZone = 0;
    for (const f of feats) {
      const c = featureCentroid(f);
      if (c && pointInRingLL(c[0], c[1], ring)) inZone++;
    }
    return { inZone, context: feats.length - inZone };
  }, [scenarioHvi, selectedZone]);

  if (showLanding) {
    return <LandingPage onLaunch={() => { setShowLanding(false); setActiveTab('analyze'); }} />;
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="app-brand" onClick={() => setShowLanding(true)} style={{ cursor: 'pointer' }} title="Back to home">
          <span className="app-logo">🏙️ Urban Heat Triage</span>
          <span className="app-subtitle">Heat Vulnerability Index (HVI) · demo city: Barcelona</span>
        </div>
        <div className="app-status">
          {stats && !loading && (
            <span className="zone-chip">
              <i style={{ backgroundColor: riskColor(stats.mean_hvi) }} />
              Zone HVI {stats.mean_hvi.toFixed(1)} · {stats.count} buildings
            </span>
          )}
          {loading && <span className="status-badge loading">⏳ Analyzing…</span>}
          {selectedZone && !loading && <span className="status-badge success">✓ Ready</span>}
          {analysisError && !loading && <span className="status-badge error">✗ Error</span>}
        </div>
      </header>

      {/* Tab Bar */}
      <div className="tab-bar">
        <button className={`tab ${activeTab === 'analyze' ? 'active' : ''}`} onClick={() => setActiveTab('analyze')}>
          <span className="tab-icon">✏️</span> Draw &amp; Analyze
        </button>
        <button className={`tab ${activeTab === 'explore3d' ? 'active' : ''}`} onClick={() => setActiveTab('explore3d')} disabled={!selectedZone}>
          <span className="tab-icon">🧊</span> 3D Explore
        </button>
        <button className={`tab ${activeTab === 'hvi' ? 'active' : ''}`} onClick={handleHVITabClick} disabled={!selectedZone}>
          <span className="tab-icon">🗺️</span> HVI Map
        </button>
        <button className={`tab ${activeTab === 'results' ? 'active' : ''}`} onClick={() => setActiveTab('results')} disabled={!selectedZone}>
          <span className="tab-icon">🌡️</span> Heatmap &amp; Drivers
        </button>
        <button className={`tab ${activeTab === 'interventions' ? 'active' : ''}`} onClick={() => setActiveTab('interventions')} disabled={!hviData}>
          <span className="tab-icon">💡</span> Interventions
        </button>
      </div>

      {/* Loading overlay with pipeline steps */}
      {loading && (
        <div className="pipeline-overlay">
          <div className="pipeline-card">
            <div className="pipeline-spinner" />
            <h3>Analyzing zone</h3>
            <ul className="pipeline-steps">
              {PIPELINE_STEPS.map((step, i) => (
                <li key={step} className={i < loadingStep ? 'done' : i === loadingStep ? 'active' : ''}>
                  <span className="pipeline-dot" />{step}
                </li>
              ))}
            </ul>
            <p className="pipeline-note">First run fetches satellite scenes — up to a minute.</p>
          </div>
        </div>
      )}

      {/* Tab Content */}
      <div className="app-content">
        {/* Tab 1: Analyze */}
        {activeTab === 'analyze' && (
          <div className="tab-panel">
            <div className="panel-main">
              <MapView
                onZoneDrawn={handleZoneDrawn}
                simulationGrid={selectedZone?.vulnerability_analysis?.simulation_grid}
                buildingData={null}
                onBuildingSelected={setSelectedBuilding}
              />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                <h3>Draw an analysis zone</h3>
                <ol className="howto">
                  <li>Use the <strong>polygon tool</strong> (left edge of the map) to outline a study area.</li>
                  <li>Keep it focused — a few city blocks works best.</li>
                  <li>The analysis starts automatically when you close the polygon.</li>
                </ol>

                {analysisError && <div className="error-box">⚠ {analysisError}</div>}

                {selectedZone && (
                  <div className="analysis-summary">
                    <h4>Last analysis</h4>
                    <div className="metric">
                      <label>Vulnerability score</label>
                      <span className="value">{selectedZone.vulnerability_analysis?.score}/10</span>
                    </div>
                    <div className="metric">
                      <label>Peak UTCI</label>
                      <span className="value">{selectedZone.vulnerability_analysis?.climate_context?.peak_utci_celsius}°C</span>
                    </div>
                    <div className="metric">
                      <label>Zone Buildings</label>
                      <span className="value">{selectedZone.vulnerability_analysis?.zone_buildings?.count || selectedZone.vulnerability_analysis?.buildings_3d?.count}</span>
                    </div>
                    {selectedZone.vulnerability_analysis?.buffer_zone_buildings?.count > 0 && (
                      <div className="metric">
                        <label>Context Buildings</label>
                        <span className="value">{selectedZone.vulnerability_analysis?.buffer_zone_buildings?.count}</span>
                      </div>
                    )}
                    {selectedZone.vulnerability_analysis?.drivers?.length > 0 && (
                      <div className="metric">
                        <label>Top driver</label>
                        <span className="value">
                          {selectedZone.vulnerability_analysis.drivers[0].driver.replace(/_/g, ' ')}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                <Glossary />
                <DataSources />
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: 3D Explore */}
        {activeTab === 'explore3d' && selectedZone && (
          <div className="tab-panel">
            <div className="panel-main">
              <MapboxDeckView
                zoneBuildings={selectedZone.vulnerability_analysis?.zone_buildings}
                bufferZoneBuildings={selectedZone.vulnerability_analysis?.buffer_zone_buildings}
                buildingData={selectedZone.vulnerability_analysis?.buildings_3d}
                hviData={scenarioHvi}
                zoneBounds={selectedZone.zone_geojson}
                heatmap={baseHeatmap}
                showOnlyHighestVulnerable={showOnlyHighestVulnerable}
                onToggleHighestVulnerable={() => setShowOnlyHighestVulnerable(!showOnlyHighestVulnerable)}
                showContextHvi={showContextHvi}
              />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                {stats ? (
                  <>
                    <ScenarioToggle scenario={scenario} setScenario={setScenario} compare={climateCompare} />
                    <div className="toggle-card-grid">
                      <ToggleCard
                        icon="🔴"
                        title="Highest HVI building"
                        subtitle={showOnlyHighestVulnerable ? 'Isolated — others greyed, camera orbited in' : 'Tap to isolate & fly to the most at-risk building'}
                        metric={stats?.max_hvi != null ? stats.max_hvi.toFixed(1) : '—'}
                        metricLabel="peak HVI / 10"
                        on={showOnlyHighestVulnerable}
                        onClick={() => setShowOnlyHighestVulnerable(!showOnlyHighestVulnerable)}
                        accent="#ef4444"
                      />
                      <ToggleCard
                        icon="🏙️"
                        title="Context buildings"
                        subtitle={showContextHvi ? 'Colored by HVI' : 'Greyed (outside drawn zone)'}
                        metric={zoneSplit.context}
                        metricLabel={`context · ${zoneSplit.inZone} in zone`}
                        on={showContextHvi}
                        onClick={() => setShowContextHvi(!showContextHvi)}
                        accent="#fb923c"
                      />
                    </div>
                    <HVIGauge score={stats.mean_hvi} />
                    <StatGrid stats={stats} />
                    <HVIScaleLegend score={stats.mean_hvi} />
                    <h4 className="section-title">Risk distribution</h4>
                    <RiskDistribution stats={stats} />
                    {zoneFactors && (
                      <>
                        <h4 className="section-title">Zone factor profile <span className="section-hint">(mean of all buildings)</span></h4>
                        <FactorBreakdown factors={zoneFactors} compact />
                      </>
                    )}
                    <div className="tip-box">
                      💡 <strong>Hover</strong> a building for a quick readout, <strong>click</strong> it for the full
                      12-factor breakdown. Use the view controls (top right) to filter by HVI.
                    </div>
                  </>
                ) : (
                  <p>HVI data not loaded yet — open the HVI Map tab to compute it.</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: HVI 2D Map */}
        {activeTab === 'hvi' && selectedZone && hviData && (
          <div className="tab-panel">
            <div className="panel-main">
              <HVI2DMap selectedZone={selectedZone} hviData={hviData} />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                {stats && (
                  <>
                    <HVIGauge score={stats.mean_hvi} />
                    <StatGrid stats={stats} />
                    <HVIScaleLegend score={stats.mean_hvi} />
                    <h4 className="section-title">Risk distribution</h4>
                    <RiskDistribution stats={stats} />
                  </>
                )}
                <div className="formula-box">
                  <h4>Composite score formula</h4>
                  <code>
                    HVI = 0.15·age + 0.10·roof + 0.05·canyon + 0.05·green<br />
                    &nbsp;&nbsp;+ 0.15·elderly + 0.10·income⁻¹ + 0.07·isolation + 0.05·no_AC + 0.03·disability<br />
                    &nbsp;&nbsp;+ 0.15·LST + 0.05·UHI + 0.05·NDVI⁻¹
                  </code>
                  <div className="formula-chips">
                    <span style={{ borderColor: '#a78bfa', color: '#a78bfa' }}>Building · 35%</span>
                    <span style={{ borderColor: '#34d399', color: '#34d399' }}>Social · 40%</span>
                    <span style={{ borderColor: '#fb923c', color: '#fb923c' }}>Thermal · 25%</span>
                  </div>
                  <p className="formula-cite">
                    Index structure follows the heat-vulnerability framework of{' '}
                    <a href="https://doi.org/10.1289/ehp.0900683" target="_blank" rel="noreferrer">
                      Reid et al. 2009
                    </a>{' '}
                    (exposure · sensitivity · adaptive capacity); weights per studio methodology.
                    Thermal inputs: Landsat C2 L2 LST, Sentinel-2 NDVI. Output in index points (0–10), not °C.
                  </p>
                </div>
                <div className="tip-box">
                  💡 Click any building on the map for its vulnerability breakdown.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Heatmap & Drivers */}
        {activeTab === 'results' && selectedZone && (() => {
          const va = selectedZone.vulnerability_analysis || {};
          const grid = va.simulation_grid || {};
          const cc = va.climate_context || {};
          return (
            <div className="tab-panel">
              <div className="panel-main heatmap-panel">
                <div className="heatmap-wrap">
                  {/* Climate context metric cards */}
                  <div className="climate-grid">
                    <div className="climate-cell hot">
                      <span className="climate-value">{cc.peak_utci_celsius ?? '—'}°C</span>
                      <span className="climate-label">Peak UTCI</span>
                      <span className="climate-hint">Felt temperature at the worst hour</span>
                    </div>
                    <div className="climate-cell">
                      <span className="climate-value">{cc.mean_utci_celsius ?? '—'}°C</span>
                      <span className="climate-label">Mean UTCI</span>
                      <span className="climate-hint">Average over July, 10:00–18:00</span>
                    </div>
                    <div className="climate-cell">
                      <span className="climate-value">{cc.heat_stress_hours_pct ?? '—'}%</span>
                      <span className="climate-label">Vulnerable time</span>
                      <span className="climate-hint">Hours with UTCI &gt; 32°C — strong heat stress, ISB UTCI scale</span>
                    </div>
                    <div className="climate-cell green">
                      <span className="climate-value">{cc.vegetation_count ?? '—'}</span>
                      <span className="climate-label">Trees in zone</span>
                      <span className="climate-hint">Vegetation features detected</span>
                    </div>
                    {zoneFactors?.street_canyon && (() => {
                      const c = zoneFactors.street_canyon.score;
                      const level = c >= 0.6 ? 'High' : c >= 0.4 ? 'Moderate' : 'Low';
                      return (
                        <div className={`climate-cell ${c >= 0.6 ? 'hot' : ''}`}>
                          <span className="climate-value">{level}</span>
                          <span className="climate-label">Nocturnal retention</span>
                          <span className="climate-hint">
                            Deep canyons block sky view — stored heat re-radiates slowly at night (Oke 1981)
                          </span>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Heatmap */}
                  {grid.heatmap_image ? (
                    <>
                      <div className="heatmap-header">
                        <h3>UTCI thermal comfort heatmap</h3>
                        <p>
                          How hot it <em>feels</em> at street level — simulated July, 10:00–18:00.
                          Red areas are where pedestrians face the strongest heat stress.
                        </p>
                      </div>
                      <img
                        className="heatmap-image"
                        src={grid.heatmap_image}
                        alt="UTCI thermal heatmap of the analysis zone"
                      />
                      <div className="heatmap-scale">
                        <span>{grid.min_value?.toFixed(1)}°C — comfortable</span>
                        <div className="heatmap-scale-bar" />
                        <span>extreme — {grid.max_value?.toFixed(1)}°C</span>
                      </div>
                    </>
                  ) : (
                    <div className="heatmap-empty">No heatmap available for this analysis.</div>
                  )}

                  {/* Analysis metadata */}
                  <div className="analysis-meta">
                    <span>📅 {cc.analysis_period || 'July 1–31, 10:00–18:00'}</span>
                    <span>🏢 {cc.buildings_count ?? '—'} buildings simulated</span>
                    <span>🛰️ Infrared SDK thermal model</span>
                    <span>ⓘ Static envelope simulation over typical July conditions — not time-stepped</span>
                  </div>
                </div>
              </div>

              <div className="panel-side">
                <div className="panel-content">
                  <h3>Vulnerability drivers</h3>
                  <p>What is making this zone hot — and what would help.</p>
                  {va.drivers?.map((driver, i) => {
                    const info = driverInfo(driver.driver);
                    const sev = driver.severity;
                    return (
                      <div key={i} className="driver-card rich">
                        <div className="driver-card-head">
                          <span className="driver-icon">{info.icon}</span>
                          <h4>{driver.driver.replace(/_/g, ' ')}</h4>
                          <span
                            className="driver-sev"
                            style={{ color: sev > 0.7 ? '#f87171' : sev > 0.4 ? '#fb923c' : '#fbbf24' }}
                          >
                            {(sev * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="severity-bar">
                          <div
                            className="severity-fill"
                            style={{
                              width: `${sev * 100}%`,
                              backgroundColor: sev > 0.7 ? '#f87171' : sev > 0.4 ? '#fb923c' : '#fbbf24',
                            }}
                          />
                        </div>
                        <p className="driver-desc">{info.desc}</p>
                        <div className="driver-actions">
                          {info.actions.map((a) => (
                            <span className="driver-action-chip" key={a}>{a}</span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })()}

        {/* Tab 5: Interventions — what-if design studio */}
        {activeTab === 'interventions' && hviData && (
          <div className="tab-panel">
            <div className="panel-main">
              <MapboxDeckView
                zoneBuildings={selectedZone?.vulnerability_analysis?.zone_buildings}
                bufferZoneBuildings={selectedZone?.vulnerability_analysis?.buffer_zone_buildings}
                buildingData={selectedZone?.vulnerability_analysis?.buildings_3d}
                hviData={whatIfData || scenarioHvi}
                zoneBounds={selectedZone?.zone_geojson}
                heatmap={whatIfHeatmap}
              />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                <h3>Design interventions</h3>
                <p>Toggle measures to see the zone recolor with the projected HVI. Effects use published cooling coefficients.</p>

                <ScenarioToggle scenario={scenario} setScenario={setScenario} compare={climateCompare} />

                {/* Headline: health capital, not degrees */}
                <HealthHeadline impact={regenImpact} hasInterventions={activeInterventions.length > 0} />

                {/* Before / after summary */}
                {whatIfSummary ? (
                  <div className="whatif-summary">
                    <div className="whatif-col">
                      <span className="whatif-label">Before</span>
                      <span className="whatif-value" style={{ color: getHVIColorHex(whatIfSummary.meanBefore) }}>
                        {whatIfSummary.meanBefore.toFixed(1)}
                      </span>
                    </div>
                    <span className="whatif-arrow">→</span>
                    <div className="whatif-col">
                      <span className="whatif-label">After</span>
                      <span className="whatif-value" style={{ color: getHVIColorHex(whatIfSummary.meanAfter) }}>
                        {whatIfSummary.meanAfter.toFixed(1)}
                      </span>
                    </div>
                    <div className="whatif-col whatif-delta">
                      <span className="whatif-label">Δ HVI pts</span>
                      <span className="whatif-value" style={{ color: '#34d399' }}>
                        −{whatIfSummary.delta.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="whatif-summary empty">
                    Select interventions below to simulate their combined effect.
                  </div>
                )}

                {/* Ecological give-back beyond the property line */}
                {activeInterventions.length > 0 && <GiveBackPanel give={regenImpact?.giveBack} />}

                {/* Decision gate: does this zone still need building-level work? */}
                <DecisionGate
                  before={stats?.mean_hvi}
                  after={whatIfSummary?.meanAfter}
                  buildings={(whatIfData || scenarioHvi)?.buildings_with_hvi}
                />

                {/* Finalize → generated climatic diagrams */}
                <button
                  className="diagram-generate"
                  disabled={!activeInterventions.length}
                  title={activeInterventions.length ? 'Generate section, waterfall and fingerprint diagrams' : 'Select at least one intervention first'}
                  onClick={() => setShowDiagrams(true)}
                >
                  📐 Generate climatic diagrams
                </button>

                {/* Ranked intervention cards */}
                {zoneRanking.map(({ intervention: iv, affected, meanZoneDelta }) => {
                  const active = activeInterventions.includes(iv.id);
                  return (
                    <div
                      key={iv.id}
                      className={`iv-card ${active ? 'active' : ''}`}
                      onClick={() => toggleIntervention(iv.id)}
                    >
                      <div className="iv-card-head">
                        <span className="iv-icon">{iv.icon}</span>
                        <div className="iv-title-wrap">
                          <span className="iv-title">{iv.name}</span>
                          <span className="iv-category">{iv.category}</span>
                        </div>
                        <label className="iv-switch" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={active}
                            onChange={() => toggleIntervention(iv.id)}
                          />
                          <span className="iv-slider" />
                        </label>
                      </div>
                      <p className="iv-desc">{iv.description}</p>
                      <RegenTags tags={iv.regenTags} />
                      <div className="iv-stats">
                        <span className="iv-stat impact">−{meanZoneDelta.toFixed(2)} HVI pts</span>
                        <span className="iv-stat">{affected} buildings</span>
                        <span className="iv-stat">{iv.cost.level}</span>
                        <span className="iv-stat">{iv.timeframe}</span>
                      </div>
                      <div className="iv-evidence" title={iv.evidence}>
                        📚 {iv.evidence}
                        {' '}
                        <a href={iv.source} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                          source
                        </a>
                      </div>
                      <div className="iv-benefits">
                        {iv.coBenefits.map((b) => (
                          <span className="driver-action-chip" key={b}>{b}</span>
                        ))}
                      </div>
                    </div>
                  );
                })}

                <div className="tip-box">
                  💡 Cards are ranked by projected zone-wide HVI reduction. Each intervention only
                  applies to buildings where it makes sense (e.g. cool roofs only on risky roofs).
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Generated diagram sheet overlay */}
      {showDiagrams && scenarioHvi && (
        <DiagramSheet
          buildings={scenarioHvi.buildings_with_hvi}
          contextBuildings={contextBuildings}
          whatIfBuildings={whatIfData?.buildings_with_hvi || scenarioHvi.buildings_with_hvi}
          activeIds={activeInterventions}
          zoneFactors={zoneFactors}
          zoneBounds={selectedZone?.zone_geojson}
          peakUtci={peakUtci}
          onClose={() => setShowDiagrams(false)}
        />
      )}
    </div>
  );
}
