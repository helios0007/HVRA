import { useState, useMemo } from 'react';
import MapView from './components/MapView';
import MapboxDeckView from './components/MapboxDeckView';
import HVI2DMap from './components/HVI2DMap';
import FactorBreakdown from './components/FactorBreakdown';
import DiagramSheet from './components/DiagramSheet';
import { getHVIColorHex, riskLabel } from './utils/hviColors';
import {
  applyInterventionsToZone,
  summarizeZoneImpact,
  rankInterventionsForZone,
} from './utils/interventionEngine';
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

export default function App() {
  const [activeTab, setActiveTab] = useState('analyze');
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedBuilding, setSelectedBuilding] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [analysisError, setAnalysisError] = useState('');
  const [hviData, setHviData] = useState(null);
  const [activeInterventions, setActiveInterventions] = useState([]);
  const [showDiagrams, setShowDiagrams] = useState(false);

  const toggleIntervention = (id) => {
    setActiveInterventions((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  // Ranked catalog: zone-wide impact of each intervention alone
  const zoneRanking = useMemo(
    () => rankInterventionsForZone(hviData?.buildings_with_hvi),
    [hviData]
  );

  // What-if dataset: buildings recolored with active interventions applied
  const whatIfData = useMemo(() => {
    if (!hviData || !activeInterventions.length) return null;
    const modified = applyInterventionsToZone(hviData.buildings_with_hvi, activeInterventions);
    const scores = modified.features
      .map((f) => f.properties?.hvi_score)
      .filter((s) => s !== undefined);
    const mean = scores.reduce((a, b) => a + b, 0) / (scores.length || 1);
    return {
      ...hviData,
      buildings_with_hvi: modified,
      hvi_statistics: {
        ...hviData.hvi_statistics,
        mean_hvi: Math.round(mean * 10) / 10,
        min_hvi: Math.min(...scores),
        max_hvi: Math.max(...scores),
        high_vulnerability: scores.filter((s) => s >= 7).length,
        medium_vulnerability: scores.filter((s) => s >= 4 && s < 7).length,
        low_vulnerability: scores.filter((s) => s < 4).length,
      },
    };
  }, [hviData, activeInterventions]);

  const whatIfSummary = useMemo(
    () =>
      activeInterventions.length
        ? summarizeZoneImpact(hviData?.buildings_with_hvi, activeInterventions)
        : null,
    [hviData, activeInterventions]
  );

  // Mean of each factor across all buildings, for the zone-level methodology panel
  const zoneFactors = useMemo(() => {
    const feats = hviData?.buildings_with_hvi?.features;
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
  }, [hviData]);

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
        setHviData(await hviResponse.json());
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

  const stats = hviData?.hvi_statistics;

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="app-brand">
          <span className="app-logo">🏙️ Urban Heat Analyzer</span>
          <span className="app-subtitle">Heat Vulnerability Index · Barcelona</span>
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
                      <label>Buildings</label>
                      <span className="value">{selectedZone.vulnerability_analysis?.buildings_3d?.count}</span>
                    </div>
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
                buildingData={selectedZone.vulnerability_analysis?.buildings_3d}
                hviData={hviData}
                zoneBounds={selectedZone.zone_geojson}
              />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                {stats ? (
                  <>
                    <HVIGauge score={stats.mean_hvi} />
                    <StatGrid stats={stats} />
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
                      <span className="climate-label">Heat-stress hours</span>
                      <span className="climate-hint">Share of hours above stress threshold</span>
                    </div>
                    <div className="climate-cell green">
                      <span className="climate-value">{cc.vegetation_count ?? '—'}</span>
                      <span className="climate-label">Trees in zone</span>
                      <span className="climate-hint">Vegetation features detected</span>
                    </div>
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
                buildingData={selectedZone?.vulnerability_analysis?.buildings_3d}
                hviData={whatIfData || hviData}
                zoneBounds={selectedZone?.zone_geojson}
              />
            </div>
            <div className="panel-side">
              <div className="panel-content">
                <h3>Design interventions</h3>
                <p>Toggle measures to see the zone recolor with the projected HVI. Effects use published cooling coefficients.</p>

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
                      <span className="whatif-label">Zone HVI</span>
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
                      <div className="iv-stats">
                        <span className="iv-stat impact">−{meanZoneDelta.toFixed(2)} zone HVI</span>
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
      {showDiagrams && hviData && (
        <DiagramSheet
          buildings={hviData.buildings_with_hvi}
          whatIfBuildings={whatIfData?.buildings_with_hvi || hviData.buildings_with_hvi}
          activeIds={activeInterventions}
          zoneFactors={zoneFactors}
          onClose={() => setShowDiagrams(false)}
        />
      )}
    </div>
  );
}
