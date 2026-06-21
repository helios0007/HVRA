import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import mapboxgl from 'mapbox-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer, PolygonLayer, BitmapLayer } from '@deck.gl/layers';
import { booleanPointInPolygon, centroid as turfCentroid } from '@turf/turf';
import 'mapbox-gl/dist/mapbox-gl.css';
import FactorBreakdown from './FactorBreakdown';
import { getHVIColorRGB, getHVIColorHex, riskLabel, HVI_GRADIENT_CSS, clippedRange } from '../utils/hviColors';
import { rankInterventionsForBuilding } from '../utils/interventionEngine';

function buildingsToGeoJSON(buildingData) {
  if (!buildingData?.features || !Array.isArray(buildingData.features)) {
    return { type: 'FeatureCollection', features: [] };
  }
  return buildingData;
}

export default function MapboxDeckView({ zoneBuildings, bufferZoneBuildings, buildingData, hviData, zoneBounds, heatmap, showOnlyHighestVulnerable, onToggleHighestVulnerable, showContextHvi = false, onBuildingSelect }) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const overlay = useRef(null);
  const [styleReady, setStyleReady] = useState(false);

  // DEBUG: Log incoming data
  useEffect(() => {
    console.log('[MapboxDeckView] Props received:');
    console.log('  zoneBuildings:', zoneBuildings);
    console.log('  bufferZoneBuildings:', bufferZoneBuildings);
    console.log('  buildingData:', buildingData);
    console.log('  zoneBounds:', zoneBounds);
  }, [zoneBuildings, bufferZoneBuildings, buildingData, zoneBounds]);

  // View controls
  const [heightScale, setHeightScale] = useState(1);   // 1x = true building heights
  const [opacity, setOpacity] = useState(95);
  const [hviFilter, setHviFilter] = useState(0);
  const [wireframe, setWireframe] = useState(false);
  // OFF by default: colors must match the absolute HVI scale used everywhere
  const [relativeColors, setRelativeColors] = useState(false);
  const [showControls, setShowControls] = useState(true);
  // UTCI heatmap underlay (when the parent provides one)
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [heatOpacity, setHeatOpacity] = useState(55);

  // Interaction state
  const [hovered, setHovered] = useState(null);   // { x, y, properties, isBuffer }
  const [selected, setSelected] = useState(null); // feature properties

  useEffect(() => {
    if (!mapContainer.current) return;

    mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11', // minimal dark basemap for street context

      center: [
        parseFloat(import.meta.env.VITE_MAP_CENTER_LNG),
        parseFloat(import.meta.env.VITE_MAP_CENTER_LAT),
      ],
      zoom: parseFloat(import.meta.env.VITE_MAP_ZOOM),
      pitch: 50,
      bearing: -15,
      antialias: true,
    });

    map.current.on('load', () => {
      overlay.current = new MapboxOverlay({ interleaved: true, layers: [] });
      map.current.addControl(overlay.current);
      map.current.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-left');
      setStyleReady(true);
    });

    return () => {
      if (map.current) map.current.remove();
    };
  }, []);

  // Fit view to zone when data arrives
  useEffect(() => {
    if (!map.current || !styleReady || !zoneBounds?.coordinates) return;
    try {
      const ring = zoneBounds.coordinates[0];
      const lngs = ring.map((c) => c[0]);
      const lats = ring.map((c) => c[1]);
      map.current.fitBounds(
        [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
        { padding: 80, pitch: 50, bearing: -15, duration: 1200 }
      );
    } catch (e) { /* keep default view */ }
  }, [zoneBounds, styleReady]);

  const resetCamera = useCallback((pitch, bearing) => {
    if (!map.current || !zoneBounds?.coordinates) return;
    const ring = zoneBounds.coordinates[0];
    const lngs = ring.map((c) => c[0]);
    const lats = ring.map((c) => c[1]);
    map.current.fitBounds(
      [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      { padding: 80, pitch, bearing, duration: 900 }
    );
  }, [zoneBounds]);

  // Orbit the camera onto a clicked/selected building for a close 3D read.
  const flyToFeature = useCallback((feature) => {
    if (!map.current || !feature) return;
    let center = feature.properties?.center;
    if (!center || center.length !== 2) {
      try { center = turfCentroid(feature).geometry.coordinates; } catch (e) { return; }
    }
    if (!center) return;
    map.current.flyTo({
      center,
      zoom: Math.max(map.current.getZoom(), 17.5),
      pitch: 58,
      bearing: (map.current.getBearing() + 35) % 360,
      duration: 1300,
      essential: true,
    });
  }, []);

  // Zone score range — shared by the color stretch, tooltip, and legend
  const scoreRange = useMemo(() => {
    const feats = (hviData?.buildings_with_hvi || buildingData)?.features || [];
    if (!feats.length) return [0, 10];
    const scores = feats.map((f) => f.properties.hvi_score ?? f.properties.vulnerability_score ?? 5);
    // Clip ~10% off each tail so outliers don't flatten the contrast.
    return clippedRange(scores, 0.1);
  }, [hviData, buildingData]);

  // Get all zone buildings and identify the highest HVI one
  const { allZoneBuildings, maxHviBuildingId } = useMemo(() => {
    const buildingsToCheck = hviData?.buildings_with_hvi || zoneBuildings || buildingData;
    if (!buildingsToCheck?.features) return { allZoneBuildings: buildingsToCheck, maxHviBuildingId: null };

    let maxId = null;
    if (showOnlyHighestVulnerable && buildingsToCheck.features.length > 0) {
      // The highest-HVI building must be one INSIDE the drawn zone — context
      // buildings (outside the polygon) are excluded from this pick.
      const zoneFeature = zoneBounds?.coordinates
        ? { type: 'Feature', geometry: zoneBounds, properties: {} }
        : null;
      const candidates = zoneFeature
        ? buildingsToCheck.features.filter((f) => {
            try { return booleanPointInPolygon(turfCentroid(f), zoneFeature); }
            catch (e) { return true; }
          })
        : buildingsToCheck.features;
      if (candidates.length > 0) {
        const maxBuilding = candidates.reduce((max, f) => {
          const fHvi = f.properties?.hvi_score ?? 0;
          const maxHvi = max.properties?.hvi_score ?? 0;
          return fHvi > maxHvi ? f : max;
        });
        // Use a combination of properties as ID to identify the max building
        maxId = maxBuilding.properties?.id || maxBuilding.properties?.identifier || JSON.stringify(maxBuilding.properties);
      }
    }

    return { allZoneBuildings: buildingsToCheck, maxHviBuildingId: maxId };
  }, [hviData, zoneBuildings, buildingData, showOnlyHighestVulnerable, zoneBounds]);

  // The ONE place that decides a building's display color. Tooltip and
  // inspector use this too, so what you hover always matches what you see.
  const displayScore = useCallback((score) => {
    if (relativeColors && scoreRange[1] - scoreRange[0] >= 0.1) {
      return ((score - scoreRange[0]) / (scoreRange[1] - scoreRange[0])) * 10;
    }
    return score;
  }, [relativeColors, scoreRange]);

  // When "Highest HVI only" is enabled, select + orbit onto that building.
  useEffect(() => {
    if (!showOnlyHighestVulnerable || !maxHviBuildingId || !styleReady) return;
    const feats = allZoneBuildings?.features || [];
    const target = feats.find((f) => {
      const id = f.properties?.id || f.properties?.identifier || JSON.stringify(f.properties);
      return id === maxHviBuildingId;
    });
    if (target) {
      setSelected(target.properties);
      flyToFeature(target);
    }
  }, [showOnlyHighestVulnerable, maxHviBuildingId, allZoneBuildings, styleReady, flyToFeature]);

  // Update deck.gl layers when data or controls change
  useEffect(() => {
    if (!overlay.current || !map.current || !styleReady) return;

    console.log('[MapboxDeckView] Updating layers...');
    console.log('  allZoneBuildings:', allZoneBuildings?.features?.length || 0, 'buildings');
    console.log('  bufferZoneBuildings:', bufferZoneBuildings?.features?.length || 0, 'buildings');

    const layers = [];

    // UTCI heatmap underlay — sits on the ground beneath the 3D buildings
    if (heatmap?.url && heatmap?.bounds && showHeatmap) {
      const b = heatmap.bounds;
      layers.push(
        new BitmapLayer({
          id: 'utci-heatmap',
          image: heatmap.url,
          bounds: [b.west, b.south, b.east, b.north],
          opacity: heatOpacity / 100,
          pickable: false,
        })
      );
    }

    const buildingsToRender = allZoneBuildings;
    const bufferBuildingsToRender = bufferZoneBuildings?.features?.length > 0 ? bufferZoneBuildings : null;

    // Render zone buildings (colored by vulnerability)
    if (buildingsToRender) {
      const buildingGeoJSON = buildingsToGeoJSON(buildingsToRender);

      // Tag each building as inside / outside the drawn zone polygon.
      // Infrared returns every building in the zone's bounding box, so some
      // fall outside the actual drawn shape — those render as grey context.
      const zoneFeature = zoneBounds?.coordinates
        ? { type: 'Feature', geometry: zoneBounds, properties: {} }
        : null;
      const inZoneMap = new WeakMap();
      for (const f of buildingGeoJSON.features) {
        let inside = true;
        if (zoneFeature) {
          try {
            inside = booleanPointInPolygon(turfCentroid(f), zoneFeature);
          } catch (e) {
            inside = true;
          }
        }
        inZoneMap.set(f, inside);
      }

      // The HVI score filter applies only to in-zone buildings; out-of-zone
      // context buildings are always shown (greyed, faded).
      const filtered = buildingGeoJSON.features.filter((d) => {
        if (!inZoneMap.get(d)) return true;
        const score = d.properties.hvi_score ?? d.properties.vulnerability_score ?? 5.0;
        return score >= hviFilter;
      });

      const colorFor = (score) => getHVIColorRGB(displayScore(score));

      layers.push(
        new GeoJsonLayer({
          id: 'buildings-layer',
          data: { type: 'FeatureCollection', features: filtered },
          pickable: true,
          extruded: true,
          wireframe,
          filled: true,
          stroked: false,
          getElevation: (f) => (f.properties.height || 15) * heightScale,
          getFillColor: (f) => {
            const inZone = inZoneMap.get(f);
            const score = f.properties.hvi_score ?? f.properties.vulnerability_score ?? 5.0;
            const buildingId = f.properties?.id || f.properties?.identifier || JSON.stringify(f.properties);

            // Highest-HVI isolation: grey EVERYTHING (in-zone + context) except the
            // single highest-HVI building inside the drawn zone.
            if (showOnlyHighestVulnerable && maxHviBuildingId) {
              if (buildingId === maxHviBuildingId) return [...colorFor(score), Math.round(opacity * 2.55)];
              return [128, 128, 128, Math.round((opacity * 0.5) * 2.55)];
            }

            // Context buildings (outside the drawn polygon): grey by default, or
            // HVI-colored (slightly faded) when the user enables the context toggle.
            if (!inZone) {
              if (showContextHvi) return [...colorFor(score), Math.round((opacity * 0.8) * 2.55)];
              return [120, 124, 132, Math.round((opacity * 0.25) * 2.55)];
            }

            return [...colorFor(score), Math.round(opacity * 2.55)];
          },
          getLineColor: [10, 14, 20, 160],
          lineWidthMinPixels: 1,
          material: {
            ambient: 0.45,
            diffuse: 0.7,
            shininess: 28,
            specularColor: [60, 64, 70],
          },
          onHover: (info) => {
            if (info.object) {
              setHovered({ x: info.x, y: info.y, properties: info.object.properties, isBuffer: false });
            } else if (!bufferBuildingsToRender) {
              setHovered(null);
            }
          },
          onClick: (info) => {
            if (info.object) {
              setSelected(info.object.properties);
              flyToFeature(info.object);
              onBuildingSelect?.(info.object);
            }
          },
          updateTriggers: {
            getElevation: [heightScale],
            getFillColor: [opacity, relativeColors, hviFilter, scoreRange, showOnlyHighestVulnerable, maxHviBuildingId, showContextHvi],
          },
        })
      );
    }

    // Render buffer zone buildings (grey with lower opacity)
    if (bufferBuildingsToRender) {
      const bufferGeoJSON = buildingsToGeoJSON(bufferBuildingsToRender);
      const bufferFeatures = bufferGeoJSON.features || [];

      layers.push(
        new GeoJsonLayer({
          id: 'buffer-buildings-layer',
          data: { type: 'FeatureCollection', features: bufferFeatures },
          pickable: true,
          extruded: true,
          wireframe,
          filled: true,
          stroked: false,
          getElevation: (f) => (f.properties.height || 15) * heightScale,
          getFillColor: (f) => {
            // Grey color for context buildings: [128, 128, 128, opacity]
            return [128, 128, 128, Math.round((opacity * 0.6) * 2.55)];
          },
          getLineColor: [80, 80, 80, 160],
          lineWidthMinPixels: 1,
          material: {
            ambient: 0.45,
            diffuse: 0.7,
            shininess: 28,
            specularColor: [60, 64, 70],
          },
          onHover: (info) => {
            if (info.object) {
              setHovered({ x: info.x, y: info.y, properties: info.object.properties, isBuffer: true });
            } else {
              setHovered(null);
            }
          },
          onClick: () => {
            // Don't select context buildings for inspector
          },
          updateTriggers: {
            getElevation: [heightScale],
            getFillColor: [opacity],
          },
        })
      );
    }

    if (zoneBounds) {
      layers.push(
        new PolygonLayer({
          id: 'zone-boundary',
          data: [{ type: 'Feature', geometry: zoneBounds, properties: {} }],
          pickable: false,
          extruded: false,
          wireframe: true,
          getPolygon: (d) => d.geometry.coordinates,
          getLineColor: [88, 166, 255, 220],
          lineWidthMinPixels: 2,
          filled: false,
        })
      );
    }

    overlay.current.setProps({ layers });
  }, [allZoneBuildings, maxHviBuildingId, bufferZoneBuildings, zoneBounds, styleReady, heightScale, opacity, hviFilter, wireframe, relativeColors, displayScore, heatmap, showHeatmap, heatOpacity, showOnlyHighestVulnerable, showContextHvi, onBuildingSelect]);

  const hp = hovered?.properties;
  const hScore = hp ? (hp.hvi_score ?? hp.vulnerability_score ?? 5.0) : null;
  const isBufferBuilding = hovered?.isBuffer;

  return (
    <div className="deck-view">
      <div ref={mapContainer} className="deck-canvas" />

      {/* Hover tooltip — swatch color always matches the rendered building */}
      {hovered && (
        <div className="deck-tooltip" style={{ left: hovered.x + 14, top: hovered.y + 14 }}>
          {isBufferBuilding ? (
            <>
              <div className="deck-tooltip-score" style={{ color: '#888' }}>
                Context building (outside zone)
              </div>
              <div className="deck-tooltip-row">Vulnerability: {hScore.toFixed(1)}</div>
              <div className="deck-tooltip-row">Height: {(hp.height || 0).toFixed(0)} m</div>
            </>
          ) : (
            <>
              <div className="deck-tooltip-score" style={{ color: getHVIColorHex(displayScore(hScore)) }}>
                HVI {hScore.toFixed(1)} · {riskLabel(hScore)}
              </div>
              <div className="deck-tooltip-row">Height: {(hp.height || 0).toFixed(0)} m</div>
              {hp.hvi_factors?.construction_era && (
                <div className="deck-tooltip-row">Era score: {hp.hvi_factors.construction_era.score.toFixed(2)}</div>
              )}
              {relativeColors && (
                <div className="deck-tooltip-row" style={{ fontStyle: 'italic' }}>
                  Color stretched to zone range
                </div>
              )}
              <div className="deck-tooltip-hint">Click for full breakdown</div>
            </>
          )}
        </div>
      )}

      {/* View controls */}
      <div className={`deck-controls ${showControls ? '' : 'collapsed'}`}>
        <button className="deck-controls-toggle" onClick={() => setShowControls(!showControls)}>
          {showControls ? '⚙ View controls ▾' : '⚙ ▸'}
        </button>
        {showControls && (
          <div className="deck-controls-body">
            <label className="ctl">
              <span className="ctl-label">Height scale <em>{heightScale}× {heightScale === 1 ? '(true)' : ''}</em></span>
              <input type="range" min="1" max="10" step="1" value={heightScale}
                onChange={(e) => setHeightScale(Number(e.target.value))} />
            </label>
            <label className="ctl">
              <span className="ctl-label">Building opacity <em>{opacity}%</em></span>
              <input type="range" min="20" max="100" step="5" value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))} />
            </label>
            <label className="ctl">
              <span className="ctl-label">Show HVI ≥ <em>{hviFilter.toFixed(1)}</em></span>
              <input type="range" min="0" max="9" step="0.5" value={hviFilter}
                onChange={(e) => setHviFilter(Number(e.target.value))} />
            </label>
            <label className="ctl ctl-check">
              <input type="checkbox" checked={relativeColors} onChange={(e) => setRelativeColors(e.target.checked)} />
              <span>Stretch colors to zone range</span>
            </label>
            <label className="ctl ctl-check">
              <input type="checkbox" checked={wireframe} onChange={(e) => setWireframe(e.target.checked)} />
              <span>Wireframe edges</span>
            </label>
            {heatmap?.url && (
              <>
                <label className="ctl ctl-check">
                  <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
                  <span>🌡 UTCI heatmap underlay</span>
                </label>
                {showHeatmap && (
                  <label className="ctl">
                    <span className="ctl-label">Heatmap opacity <em>{heatOpacity}%</em></span>
                    <input type="range" min="15" max="100" step="5" value={heatOpacity}
                      onChange={(e) => setHeatOpacity(Number(e.target.value))} />
                  </label>
                )}
              </>
            )}
            <div className="ctl-buttons">
              <button onClick={() => resetCamera(50, -15)}>↻ Reset view</button>
              <button onClick={() => resetCamera(0, 0)}>⬒ Top-down</button>
              <button onClick={() => resetCamera(65, 30)}>◰ Street level</button>
            </div>
          </div>
        )}
      </div>

      {/* Heatmap scale (when the underlay is on) */}
      {heatmap?.url && showHeatmap && (
        <div className="deck-heatlegend">
          <span className="deck-legend-title">🌡</span>
          <div className="deck-legend-gradient-wrap">
            <div
              className="deck-legend-gradient"
              style={{ background: 'linear-gradient(90deg,#0033cc,#0099ff,#ffffff,#ff6600,#cc0000)' }}
            />
            <div className="deck-legend-labels">
              <span>{heatmap.min?.toFixed(0) ?? ''}</span>
              <span className="deck-legend-mode">{heatmap.label || 'UTCI °C'}</span>
              <span>{heatmap.max?.toFixed(0) ?? ''}</span>
            </div>
          </div>
        </div>
      )}

      {/* Color legend */}
      <div className="deck-legend">
        <span className="deck-legend-title">HVI</span>
        <div className="deck-legend-gradient-wrap">
          <div className="deck-legend-gradient" style={{ background: HVI_GRADIENT_CSS }} />
          <div className="deck-legend-labels">
            {relativeColors ? (
              <>
                <span>{scoreRange[0].toFixed(1)}</span>
                <span className="deck-legend-mode">zone range</span>
                <span>{scoreRange[1].toFixed(1)}</span>
              </>
            ) : (
              <>
                <span>0</span>
                <span className="deck-legend-mode">absolute</span>
                <span>10</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Selected building inspector */}
      {selected && (
        <div className="deck-inspector">
          {/* Retrofit Priority Badge */}
          {(selected.hvi_score ?? 5) >= 6.5 && (
            <div className="retrofit-priority-badge" style={{ borderColor: getHVIColorHex(displayScore(selected.hvi_score ?? 5)), backgroundColor: `${getHVIColorHex(displayScore(selected.hvi_score ?? 5))}20` }}>
              <div className="retrofit-priority-header">
                <span className="retrofit-priority-icon">⚠️ RETROFIT PRIORITY</span>
              </div>
              <div className="retrofit-priority-score" style={{ color: getHVIColorHex(displayScore(selected.hvi_score ?? 5)) }}>
                HVI {(selected.hvi_score ?? 5).toFixed(1)}
              </div>
              <div className="retrofit-priority-message">
                Start here: This building needs retrofitting first.
              </div>
            </div>
          )}
          <div className="deck-inspector-header">
            <div>
              <div className="deck-inspector-title">Building inspector</div>
              <div className="deck-inspector-score" style={{ color: getHVIColorHex(displayScore(selected.hvi_score ?? 5)) }}>
                HVI {(selected.hvi_score ?? 5).toFixed(1)} / 10 · {riskLabel(selected.hvi_score ?? 5)}
              </div>
            </div>
            <button className="deck-inspector-close" onClick={() => setSelected(null)}>×</button>
          </div>
          <div className="deck-inspector-meta">
            <span>Height {(selected.height || 0).toFixed(0)} m</span>
            {selected.hvi_breakdown && (
              <>
                <span>Building {selected.hvi_breakdown.building_exposure.toFixed(1)}</span>
                <span>Social {selected.hvi_breakdown.social_vulnerability.toFixed(1)}</span>
                <span>Thermal {selected.hvi_breakdown.thermal_context.toFixed(1)}</span>
              </>
            )}
          </div>
          {selected.hvi_factors ? (
            <>
              {/* Top recommended interventions for THIS building */}
              {(() => {
                const recs = rankInterventionsForBuilding(selected.hvi_factors, 3);
                return recs.length > 0 && (
                  <div className="deck-recs">
                    <div className="deck-recs-title">Recommended interventions</div>
                    {recs.map(({ intervention, deltaHVI }) => (
                      <div className="deck-rec" key={intervention.id}>
                        <span className="deck-rec-icon">{intervention.icon}</span>
                        <span className="deck-rec-name">{intervention.name}</span>
                        <span className="deck-rec-delta">−{deltaHVI.toFixed(1)} HVI</span>
                      </div>
                    ))}
                  </div>
                );
              })()}
              <FactorBreakdown factors={selected.hvi_factors} compact />
            </>
          ) : (
            <p className="deck-inspector-empty">No factor data for this building.</p>
          )}
        </div>
      )}
    </div>
  );
}
