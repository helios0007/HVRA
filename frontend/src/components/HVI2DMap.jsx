import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import FactorBreakdown from './FactorBreakdown';
import { getHVIColorHex, riskLabel, HVI_GRADIENT_CSS } from '../utils/hviColors';
import '../styles/HVI2DMap.css';

export default function HVI2DMap({ selectedZone, hviData, onBuildingSelect }) {
  const mapRef = useRef(null);
  const leafletMapRef = useRef(null);
  const [selectedBuilding, setSelectedBuilding] = useState(null);

  useEffect(() => {
    console.log('[HVI2DMap] Initializing with:', {
      hasMapRef: !!mapRef.current,
      hasZone: !!selectedZone,
      hasHviData: !!hviData,
      buildingCount: hviData?.buildings_with_hvi?.features?.length
    });

    if (!mapRef.current || !selectedZone || !hviData) {
      console.log('[HVI2DMap] Missing required props, skipping initialization');
      return;
    }

    // Initialize or get existing map
    if (!leafletMapRef.current) {
      leafletMapRef.current = L.map(mapRef.current).setView([41.3851, 2.1734], 15);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(leafletMapRef.current);
    }

    const map = leafletMapRef.current;

    // Clear existing layers
    map.eachLayer((layer) => {
      if (layer instanceof L.GeoJSON) {
        map.removeLayer(layer);
      }
    });

    // Add buildings GeoJSON — same shared HVI color scale as the 3D explorer
    if (hviData.buildings_with_hvi?.features) {
      L.geoJSON(hviData.buildings_with_hvi, {
        style: (feature) => {
          const score = feature.properties.hvi_score || 5;
          return {
            fillColor: getHVIColorHex(score),
            weight: 1,
            opacity: 0.8,
            color: '#333',
            fillOpacity: 0.85,
          };
        },
        onEachFeature: (feature, layer) => {
          const score = feature.properties.hvi_score || 5;
          const popup = `
            <div class="building-popup">
              <strong style="color:${getHVIColorHex(score)}">HVI ${score.toFixed(1)}/10 · ${riskLabel(score)}</strong><br/>
              Height: ${(feature.properties.height || 0).toFixed(1)}m
            </div>
          `;
          layer.bindPopup(popup);
          layer.on('click', () => {
            setSelectedBuilding(feature);
            onBuildingSelect?.(feature);
          });
        },
      }).addTo(map);
    }

    // Drawn-zone boundary — drawn on top so the user can tell which buildings
    // fall inside the analysed zone vs. the surrounding context.
    if (selectedZone.zone_geojson?.coordinates) {
      L.geoJSON(
        { type: 'Feature', geometry: selectedZone.zone_geojson, properties: {} },
        {
          interactive: false,
          style: {
            fill: false,
            color: '#2563eb',
            weight: 2.5,
            opacity: 0.9,
            dashArray: '8 5',
          },
        }
      ).addTo(map);
    }

    // Fit bounds to zone
    if (selectedZone.zone_geojson?.coordinates) {
      const bounds = L.latLngBounds(
        selectedZone.zone_geojson.coordinates[0].map(([lng, lat]) => [lat, lng])
      );
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [selectedZone, hviData]);

  return (
    <div className="hvi-2d-container">
      <div ref={mapRef} className="hvi-2d-map" />

      {selectedBuilding && (
        <div className="building-details-panel">
          <button
            className="close-btn"
            onClick={() => {
              setSelectedBuilding(null);
              onBuildingSelect?.(null);
            }}
          >
            ×
          </button>

          <h3>Building Details</h3>
          <div className="detail-group">
            <strong>HVI Score: {selectedBuilding.properties.hvi_score?.toFixed(1) || 'N/A'}/10</strong>
            <div className="score-bar">
              <div
                className="score-fill"
                style={{
                  width: `${((selectedBuilding.properties.hvi_score || 0) / 10) * 100}%`,
                  backgroundColor: selectedBuilding.properties.hvi_score >= 8 ? '#8B0000' :
                                   selectedBuilding.properties.hvi_score >= 6 ? '#FF4500' :
                                   selectedBuilding.properties.hvi_score >= 4 ? '#FFA500' : '#90EE90'
                }}
              />
            </div>
          </div>

          {selectedBuilding.properties.hvi_factors ? (
            <div className="breakdown">
              <h4>12-Factor Breakdown</h4>
              <FactorBreakdown factors={selectedBuilding.properties.hvi_factors} compact />
            </div>
          ) : selectedBuilding.properties.hvi_breakdown && (
            <div className="breakdown">
              <h4>Factor Breakdown</h4>
              <div className="factor">
                <label>Building Exposure (35%)</label>
                <div className="factor-bar">
                  <div
                    className="factor-fill"
                    style={{ width: `${Math.min((selectedBuilding.properties.hvi_breakdown.building_exposure || 0) / 10 * 100, 100)}%` }}
                  />
                </div>
                <span>{(selectedBuilding.properties.hvi_breakdown.building_exposure || 0).toFixed(1)}/10</span>
              </div>

              <div className="factor">
                <label>Social Vulnerability (40%)</label>
                <div className="factor-bar">
                  <div
                    className="factor-fill"
                    style={{ width: `${Math.min((selectedBuilding.properties.hvi_breakdown.social_vulnerability || 0) / 10 * 100, 100)}%` }}
                  />
                </div>
                <span>{(selectedBuilding.properties.hvi_breakdown.social_vulnerability || 0).toFixed(1)}/10</span>
              </div>

              <div className="factor">
                <label>Thermal Context (25%)</label>
                <div className="factor-bar">
                  <div
                    className="factor-fill"
                    style={{ width: `${Math.min((selectedBuilding.properties.hvi_breakdown.thermal_context || 0) / 10 * 100, 100)}%` }}
                  />
                </div>
                <span>{(selectedBuilding.properties.hvi_breakdown.thermal_context || 0).toFixed(1)}/10</span>
              </div>
            </div>
          )}

          <div className="detail-group">
            <label>Height: {(selectedBuilding.properties.height || 0).toFixed(1)}m</label>
            <label>UTCI: {(selectedBuilding.properties.utci_celsius || 0).toFixed(1)}°C</label>
          </div>
        </div>
      )}

      <div className="hvi-legend">
        <h4>HVI Scale</h4>
        <div style={{ width: 160, height: 10, borderRadius: 99, background: HVI_GRADIENT_CSS }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 4, opacity: 0.8 }}>
          <span>0</span><span>3</span><span>4</span><span>6</span><span>8+</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, opacity: 0.6 }}>
          <span>Low</span><span>Med</span><span>High</span><span>Critical</span>
        </div>
      </div>
    </div>
  );
}
