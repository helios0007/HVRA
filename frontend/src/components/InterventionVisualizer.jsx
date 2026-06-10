import React, { useEffect, useRef } from 'react';

export default function InterventionVisualizer({ map, interventions, showInterventions, opacity, selectedBuilding }) {
  const layersRef = useRef({});

  // Add intervention layers to map
  useEffect(() => {
    console.log('InterventionVisualizer effect triggered:', {
      hasMap: !!map?.current,
      interventions: interventions?.length,
      showInterventions,
      opacity
    });

    if (!map || !map.current || !interventions || !showInterventions) {
      console.log('Early return from InterventionVisualizer effect');
      return;
    }

    const mapInstance = map.current;

    // Remove old layers
    Object.keys(layersRef.current).forEach(layerId => {
      if (mapInstance.getLayer(layerId)) {
        mapInstance.removeLayer(layerId);
      }
      if (mapInstance.getSource(`${layerId}-source`)) {
        mapInstance.removeSource(`${layerId}-source`);
      }
    });
    layersRef.current = {};

    // Add new intervention layers
    interventions.forEach((intervention, idx) => {
      const layerId = `intervention-${intervention.type}-${idx}`;
      const sourceId = `${layerId}-source`;

      try {
        console.log(`Adding intervention layer ${idx}:`, {
          type: intervention.type,
          name: intervention.name,
          hasGeoJSON: !!intervention.visualization_geojson
        });

        // Use visualization_geojson if available, otherwise create feature
        let geojsonData = null;

        if (intervention.visualization_geojson) {
          // Use pre-generated GeoJSON from design specs
          geojsonData = intervention.visualization_geojson;
          if (typeof geojsonData === 'string') {
            geojsonData = JSON.parse(geojsonData);
          }
          console.log(`Layer ${layerId} using GeoJSON:`, geojsonData);
        } else {
          console.log(`Layer ${layerId} creating fallback feature`);
          // Fallback: create feature from intervention data
          const feature = _createFeatureFromIntervention(intervention, selectedBuilding);
          if (!feature) {
            console.log(`Layer ${layerId} feature creation returned null`);
            return;
          }
          geojsonData = feature;
        }

        // Add source
        mapInstance.addSource(sourceId, {
          type: 'geojson',
          data: geojsonData
        });

        // Get layer config based on intervention type
        const layerConfig = _getLayerConfig(intervention, layerId, sourceId);

        // Add layer
        mapInstance.addLayer(layerConfig);
        console.log(`Layer ${layerId} added successfully`);

        // Add hover effects
        mapInstance.on('mouseenter', layerId, () => {
          mapInstance.getCanvas().style.cursor = 'pointer';
        });
        mapInstance.on('mouseleave', layerId, () => {
          mapInstance.getCanvas().style.cursor = '';
        });

        // Show impact on popup hover
        mapInstance.on('click', layerId, (e) => {
          if (e.features && e.features.length > 0) {
            const feature = e.features[0];
            new mapboxgl.Popup()
              .setLngLat(e.lngLat)
              .setHTML(`
                <strong>${intervention.name || intervention.type.replace(/_/g, ' ')}</strong><br/>
                Expected Impact: ${intervention.expected_thermal_impact_celsius}°C<br/>
                Feasibility: ${(intervention.feasibility_score * 100).toFixed(0)}%<br/>
                Cost: $${(intervention.cost_estimate_usd || 0).toLocaleString()}<br/>
                ${intervention.rationale ? `<em>${intervention.rationale}</em>` : ''}
              `)
              .addTo(mapInstance);
          }
        });

        layersRef.current[layerId] = { sourceId, data: geojsonData };
      } catch (err) {
        console.warn(`Failed to add intervention layer ${layerId}:`, err);
      }
    });

    return () => {
      // Cleanup on unmount
      Object.keys(layersRef.current).forEach(layerId => {
        if (mapInstance.getLayer(layerId)) {
          mapInstance.off('mouseenter', layerId);
          mapInstance.off('mouseleave', layerId);
          mapInstance.off('click', layerId);
          mapInstance.removeLayer(layerId);
        }
        const sourceId = layersRef.current[layerId].sourceId;
        if (mapInstance.getSource(sourceId)) {
          mapInstance.removeSource(sourceId);
        }
      });
    };
  }, [interventions, showInterventions, map, selectedBuilding]);

  // Update opacity
  useEffect(() => {
    if (!map || !map.current) return;

    const mapInstance = map.current;
    Object.keys(layersRef.current).forEach(layerId => {
      if (mapInstance.getLayer(layerId)) {
        const paint = mapInstance.getLayer(layerId).paint || {};

        // Update opacity based on layer type
        if (layerId.includes('trees') || layerId.includes('point')) {
          mapInstance.setPaintProperty(layerId, 'circle-opacity', opacity);
        } else if (layerId.includes('water')) {
          mapInstance.setPaintProperty(layerId, 'fill-opacity', opacity);
        } else {
          // Polygons, etc
          if (paint['fill-opacity'] !== undefined) {
            mapInstance.setPaintProperty(layerId, 'fill-opacity', opacity * 0.7);
          }
        }
      }
    });
  }, [opacity, map]);

  return null;
}

// Helper function to create GeoJSON feature from intervention
function _createFeatureFromIntervention(intervention, selectedBuilding) {
  if (!intervention) return null;

  const type = intervention.type;

  // Get building center for positioning interventions
  let centerCoords = [0, 0];
  if (selectedBuilding?.center) {
    centerCoords = selectedBuilding.center;
  } else if (selectedBuilding?.geometry?.coordinates) {
    // Extract center from polygon
    const coords = selectedBuilding.geometry.coordinates[0];
    if (coords && coords.length > 0) {
      let lng = 0, lat = 0;
      coords.forEach(c => {
        lng += c[0];
        lat += c[1];
      });
      centerCoords = [lng / coords.length, lat / coords.length];
    }
  }

  // Different types need different geometries
  switch (type) {
    case 'trees':
    case 'urban_forest':
    case 'street_trees':
      // Create point feature(s) for trees - distribute around building
      return {
        type: 'Feature',
        properties: {
          type: type,
          impact: intervention.expected_thermal_impact_celsius,
          complexity: intervention.implementation_complexity
        },
        geometry: {
          type: 'Point',
          coordinates: centerCoords
        }
      };

    case 'cool_pavements':
    case 'cool_roofs':
    case 'water_features':
    case 'green_roofs':
    case 'green_walls':
    case 'shade_structures':
    case 'ventilation_corridors':
      // Create polygon around building for surface treatments
      if (selectedBuilding?.geometry?.type === 'Polygon' && selectedBuilding.geometry.coordinates?.[0]) {
        // Use building polygon as base
        return {
          type: 'Feature',
          properties: {
            type: type,
            impact: intervention.expected_thermal_impact_celsius,
            complexity: intervention.implementation_complexity
          },
          geometry: selectedBuilding.geometry
        };
      } else {
        // Create a buffer around building center
        const bufferDist = 0.0005; // ~50 meters at equator
        return {
          type: 'Feature',
          properties: {
            type: type,
            impact: intervention.expected_thermal_impact_celsius,
            complexity: intervention.implementation_complexity
          },
          geometry: {
            type: 'Polygon',
            coordinates: [[
              [centerCoords[0] - bufferDist, centerCoords[1] - bufferDist],
              [centerCoords[0] + bufferDist, centerCoords[1] - bufferDist],
              [centerCoords[0] + bufferDist, centerCoords[1] + bufferDist],
              [centerCoords[0] - bufferDist, centerCoords[1] + bufferDist],
              [centerCoords[0] - bufferDist, centerCoords[1] - bufferDist]
            ]]
          }
        };
      }

    default:
      // Generic point-based intervention
      return {
        type: 'Feature',
        properties: {
          type: type,
          impact: intervention.expected_thermal_impact_celsius,
          complexity: intervention.implementation_complexity
        },
        geometry: {
          type: 'Point',
          coordinates: centerCoords
        }
      };
  }
}

// Get layer configuration based on intervention type
function _getLayerConfig(intervention, layerId, sourceId) {
  const type = intervention.type;
  const impact = intervention.expected_thermal_impact_celsius;

  // Color intensifies with impact magnitude
  const getImpactColor = (impact) => {
    if (impact >= 3.5) return '#d32f2f'; // Deep red - highest impact
    if (impact >= 3.0) return '#e53935'; // Red - very high impact
    if (impact >= 2.5) return '#f44336'; // Lighter red - high impact
    if (impact >= 2.0) return '#f39c12'; // Orange - medium-high impact
    if (impact >= 1.5) return '#ffc107'; // Amber - medium impact
    return '#26c6da'; // Cyan - lower impact
  };

  const baseConfig = {
    id: layerId,
    source: sourceId,
    layout: {
      visibility: 'visible'
    }
  };

  // Type-specific configurations with impact-aware colors
  if (type.includes('tree') || type.includes('forest') || type.includes('vegetation') || type.includes('urban_forest')) {
    return {
      ...baseConfig,
      type: 'circle',
      paint: {
        'circle-radius': 8,
        'circle-color': '#1b5e20',
        'circle-opacity': 0.85,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#4caf50',
        'circle-stroke-opacity': 0.9
      }
    };
  } else if (type.includes('pavement') || type.includes('surface') || type.includes('cool_pavement')) {
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': '#b0bec5',
        'fill-opacity': 0.7,
        'fill-outline-color': '#78909c'
      }
    };
  } else if (type.includes('water')) {
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': '#0288d1',
        'fill-opacity': 0.6,
        'fill-outline-color': '#01579b'
      }
    };
  } else if (type.includes('shade') || type.includes('structure') || type.includes('corridor')) {
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': '#ffd54f',
        'fill-opacity': 0.5,
        'fill-outline-color': '#f57f17'
      }
    };
  } else if (type.includes('roof') || type.includes('green') || type.includes('cool_roof')) {
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': '#2e7d32',
        'fill-opacity': 0.7,
        'fill-outline-color': '#1b5e20'
      }
    };
  } else if (type.includes('setback') || type.includes('building')) {
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': '#ff6f00',
        'fill-opacity': 0.5,
        'fill-outline-color': '#e65100'
      }
    };
  } else {
    // Default - color by impact
    return {
      ...baseConfig,
      type: 'fill',
      paint: {
        'fill-color': getImpactColor(impact),
        'fill-opacity': 0.65,
        'fill-outline-color': '#424242'
      }
    };
  }
}
