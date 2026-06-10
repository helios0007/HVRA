import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import MapboxDraw from '@mapbox/mapbox-gl-draw';
import { centroid } from '@turf/turf';
import InterventionVisualizer from './InterventionVisualizer';
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css';
import 'mapbox-gl/dist/mapbox-gl.css';

// Transform building coordinates from local to geographic space if needed
function transformBuildingCoordinates(buildingData, drawnZone) {
  if (!buildingData?.features || buildingData.features.length === 0) {
    return buildingData;
  }

  // Get zone bounds (geographic coordinates)
  let zoneBounds = null;
  if (drawnZone?.geometry?.type === 'Polygon' && drawnZone.geometry.coordinates?.[0]) {
    const coords = drawnZone.geometry.coordinates[0];
    const lons = coords.map(c => c[0]);
    const lats = coords.map(c => c[1]);
    zoneBounds = {
      west: Math.min(...lons),
      east: Math.max(...lons),
      south: Math.min(...lats),
      north: Math.max(...lats)
    };
  }

  // Collect all building coordinates to determine if they're in local space
  const allCoords = [];
  buildingData.features.forEach(f => {
    if (f.geometry?.type === 'Polygon' && f.geometry?.coordinates?.[0]) {
      f.geometry.coordinates[0].forEach(coord => {
        if (Array.isArray(coord) && coord.length >= 2) {
          allCoords.push(coord);
        }
      });
    }
  });

  if (allCoords.length === 0) return buildingData;

  // Check if coordinates are in geographic space (lon between -180 and 180, lat between -90 and 90)
  const minLon = Math.min(...allCoords.map(c => c[0]));
  const maxLon = Math.max(...allCoords.map(c => c[0]));
  const minLat = Math.min(...allCoords.map(c => c[1]));
  const maxLat = Math.max(...allCoords.map(c => c[1]));

  const isGeographic = (minLon >= -180 && maxLon <= 180 && minLat >= -90 && maxLat <= 90);
  const looksLikeLatLon = (minLon >= -5 && maxLon <= 5 && minLat >= 35 && maxLat <= 45);

  console.log('[TRANSFORM] Coordinate check:');
  console.log(`  Min/Max Lon: [${minLon}, ${maxLon}]`);
  console.log(`  Min/Max Lat: [${minLat}, ${maxLat}]`);
  console.log(`  Is Geographic? ${isGeographic}, Looks like Barcelona? ${looksLikeLatLon}`);

  // If coordinates already look like geographic (especially Barcelona), return as-is
  if (looksLikeLatLon && zoneBounds) {
    console.log('[TRANSFORM] Coordinates already geographic, no transformation needed');
    return buildingData;
  }

  // If not geographic and we have zone bounds, apply transformation
  if (!isGeographic && zoneBounds) {
    console.log('[TRANSFORM] Applying local→geographic transformation');
    console.log(`  Zone bounds: W=${zoneBounds.west}, E=${zoneBounds.east}, S=${zoneBounds.south}, N=${zoneBounds.north}`);

    // Local bounds from building coordinates
    const localBounds = {
      x_min: minLon,
      x_max: maxLon,
      y_min: minLat,
      y_max: maxLat
    };

    console.log(`  Local bounds: X=[${localBounds.x_min}, ${localBounds.x_max}], Y=[${localBounds.y_min}, ${localBounds.y_max}]`);

    // Create deep copy and transform coordinates
    const transformedData = JSON.parse(JSON.stringify(buildingData));

    transformedData.features.forEach(feature => {
      if (feature.geometry?.type === 'Polygon' && feature.geometry?.coordinates?.[0]) {
        feature.geometry.coordinates[0].forEach(coord => {
          if (Array.isArray(coord) && coord.length >= 2) {
            // Linear transformation: local → geographic
            let geoX = coord[0];
            let geoY = coord[1];

            if (localBounds.x_max > localBounds.x_min) {
              const normX = (coord[0] - localBounds.x_min) / (localBounds.x_max - localBounds.x_min);
              geoX = zoneBounds.west + normX * (zoneBounds.east - zoneBounds.west);
            } else {
              geoX = (zoneBounds.west + zoneBounds.east) / 2;
            }

            if (localBounds.y_max > localBounds.y_min) {
              const normY = (coord[1] - localBounds.y_min) / (localBounds.y_max - localBounds.y_min);
              geoY = zoneBounds.south + normY * (zoneBounds.north - zoneBounds.south);
            } else {
              geoY = (zoneBounds.south + zoneBounds.north) / 2;
            }

            coord[0] = geoX;
            coord[1] = geoY;
          }
        });
      }
    });

    console.log('[TRANSFORM] Transformation complete');
    return transformedData;
  }

  // No transformation needed
  return buildingData;
}

export default function MapView({ onZoneDrawn, simulationGrid, buildingData, ifcBuildingData, onBuildingSelected, selectedBuilding, suggestedInterventions, showInterventions, interventionOpacity }) {
  const [interventionOpacityLocal, setInterventionOpacityLocal] = useState(interventionOpacity || 0.7);
  const mapContainer = useRef(null);
  const map = useRef(null);
  const draw = useRef(null);
  const selectedBuildingRef = useRef(null);

  // Debug: Log when props change
  useEffect(() => {
    console.log('MapView received props:', {
      suggestedInterventions: suggestedInterventions?.length || 0,
      showInterventions,
      selectedBuilding: !!selectedBuilding,
      mapLoaded: !!map.current
    });
  }, [suggestedInterventions, showInterventions, selectedBuilding]);

  useEffect(() => {
    mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/light-v11', // minimal monochrome basemap
      center: [
        parseFloat(import.meta.env.VITE_MAP_CENTER_LNG),
        parseFloat(import.meta.env.VITE_MAP_CENTER_LAT),
      ],
      zoom: parseFloat(import.meta.env.VITE_MAP_ZOOM),
      pitch: 0,
      bearing: 0,
    });

    // Keep the canvas matched to the panel size
    const resizeObserver = new ResizeObserver(() => map.current?.resize());
    resizeObserver.observe(mapContainer.current);
    map.current.once('remove', () => resizeObserver.disconnect());

    // Wait for map to fully load before adding drawing controls
    map.current.on('load', () => {
      draw.current = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
          polygon: true,
          trash: true,
        },
      });

      map.current.addControl(draw.current);
      console.log('Drawing controls added to map');

      map.current.on('draw.create', updateSelection);
      map.current.on('draw.update', updateSelection);
    });

    // Add building click handler
    map.current.on('style.load', addBuildingClickHandler);

    // Don't add default Mapbox buildings - will use Infrared buildings instead
    map.current.on('style.load', () => {
      // Remove default Mapbox buildings if they exist
      if (map.current.getLayer('buildings')) {
        map.current.removeLayer('buildings');
      }
      if (map.current.getLayer('buildings-3d')) {
        map.current.removeLayer('buildings-3d');
      }
    });

    return () => map.current?.remove();
  }, []);

  useEffect(() => {
    if (!map.current || !simulationGrid) return;

    const { heatmap_image, bounds } = simulationGrid;
    if (!heatmap_image || !bounds) return;

    const mapInstance = map.current;
    let cancelled = false;

    function addHeatmapLayer() {
      if (cancelled) return;
      try {
        if (mapInstance.getLayer('heatmap-layer')) {
          mapInstance.removeLayer('heatmap-layer');
        }
        if (mapInstance.getSource('heatmap-source')) {
          mapInstance.removeSource('heatmap-source');
        }

        const coordinates = [
          [bounds.west, bounds.north],
          [bounds.east, bounds.north],
          [bounds.east, bounds.south],
          [bounds.west, bounds.south],
        ];

        mapInstance.addSource('heatmap-source', {
          type: 'image',
          url: heatmap_image,
          coordinates: coordinates,
        });

        mapInstance.addLayer({
          id: 'heatmap-layer',
          type: 'raster',
          source: 'heatmap-source',
          paint: { 'raster-opacity': 0.65 },
        });

        // Bring the view to the heatmap so it's visible after a remount
        mapInstance.fitBounds(
          [[bounds.west, bounds.south], [bounds.east, bounds.north]],
          { padding: 60, duration: 800 }
        );

        console.log('Heatmap layer added successfully (buildings on top)');
      } catch (err) {
        // Style not ready yet — retry on the next idle frame
        console.warn('Heatmap add failed, retrying on idle:', err.message);
        mapInstance.once('idle', addHeatmapLayer);
      }
    }

    if (mapInstance.isStyleLoaded()) {
      addHeatmapLayer();
    } else {
      mapInstance.once('load', addHeatmapLayer);
      // Fallback for remounts where 'load' already fired between checks
      mapInstance.once('idle', addHeatmapLayer);
    }

    return () => {
      cancelled = true;
      mapInstance.off('load', addHeatmapLayer);
      mapInstance.off('idle', addHeatmapLayer);
    };
  }, [simulationGrid]);

  useEffect(() => {
    if (!map.current || !buildingData) return;

    // Add building data layer if provided from Infrared
    if (!map.current.getLayer('infrared-buildings-3d')) {
      try {
        // Get the drawn zone from the draw instance
        let drawnZone = null;
        if (draw.current) {
          const data = draw.current.getAll();
          if (data.features && data.features.length > 0) {
            drawnZone = data.features[0];
          }
        }

        // Transform coordinates from local to geographic if needed
        const transformedBuildingData = transformBuildingCoordinates(buildingData, drawnZone);

        map.current.addSource('infrared-buildings', {
          type: 'geojson',
          data: transformedBuildingData,
        });

        // Color-code buildings by vulnerability score (0-10 scale)
        const vulnerabilityColor = [
          'interpolate',
          ['linear'],
          ['get', 'vulnerability_score'],
          0, '#2ecc71',      // Green - low vulnerability
          3, '#f1c40f',      // Yellow
          5, '#f39c12',      // Orange
          7, '#e74c3c',      // Red - high vulnerability
          10, '#c0392b'      // Dark red - critical
        ];

        console.log('Color expression:', vulnerabilityColor);
        console.log('Sample building properties:', transformedBuildingData.features[0]?.properties);
        console.log('Sample building geometry:', transformedBuildingData.features[0]?.geometry);

        // Debug: log coordinate ranges
        const lngs = [];
        const lats = [];

        transformedBuildingData.features.forEach(f => {
          if (f.geometry?.type === 'Polygon' && f.geometry?.coordinates?.[0]) {
            f.geometry.coordinates[0].forEach(coord => {
              if (Array.isArray(coord) && coord.length >= 2) {
                lngs.push(coord[0]);
                lats.push(coord[1]);
              }
            });
          }
        });

        if (lngs.length > 0 && lats.length > 0) {
          console.log('[FRONTEND DEBUG] Building coordinate ranges AFTER TRANSFORM:');
          console.log(`  Longitudes (X): [${Math.min(...lngs)}, ${Math.max(...lngs)}]`);
          console.log(`  Latitudes (Y): [${Math.min(...lats)}, ${Math.max(...lats)}]`);
          console.log(`  Sample coordinate: [${lngs[0]}, ${lats[0]}]`);
        } else {
          console.log('[FRONTEND DEBUG] Could not extract coordinates - check geometry structure');
        }

        // Add building layer
        map.current.addLayer({
          id: 'infrared-buildings-3d',
          source: 'infrared-buildings',
          type: 'fill-extrusion',
          paint: {
            'fill-extrusion-color': vulnerabilityColor,
            'fill-extrusion-height': ['get', 'height'],
            'fill-extrusion-base': ['get', 'min_height'],
            'fill-extrusion-opacity': 0.9,
          },
        });

        // Move to top to ensure it's above heatmap
        map.current.moveLayer('infrared-buildings-3d');

        console.log('Infrared buildings layer added with vulnerability coloring (on top)');
      } catch (err) {
        console.warn('Could not add building data layer:', err);
      }
    }
  }, [buildingData]);

  // Clear selection highlight when clicking elsewhere
  useEffect(() => {
    if (!map.current) return;

    const handleMapClick = (e) => {
      // Only clear if not clicking on a building
      const existingLayers = ['buildings-3d', 'infrared-buildings-3d', 'ifc-buildings-3d'].filter((layerId) =>
        map.current.getLayer(layerId)
      );

      if (existingLayers.length > 0) {
        const features = map.current.queryRenderedFeatures({ layers: existingLayers, point: e.point });
        if (features.length === 0) {
          // Clear selection
          if (map.current.getLayer('selected-building-highlight')) {
            map.current.removeLayer('selected-building-highlight');
          }
          if (map.current.getSource('selected-building-source')) {
            map.current.removeSource('selected-building-source');
          }
        }
      }
    };

    map.current.on('click', handleMapClick);
    return () => map.current?.off('click', handleMapClick);
  }, []);

  useEffect(() => {
    if (!map.current || !ifcBuildingData) return;

    // Add IFC building data layer if provided
    if (map.current.getLayer('ifc-buildings-3d')) {
      map.current.removeLayer('ifc-buildings-3d');
    }
    if (map.current.getSource('ifc-buildings')) {
      map.current.removeSource('ifc-buildings');
    }

    try {
      map.current.addSource('ifc-buildings', {
        type: 'geojson',
        data: ifcBuildingData,
      });

      // Determine which layer to add before (if it exists)
      let beforeLayer = null;
      if (map.current.getLayer('infrared-buildings-3d')) {
        beforeLayer = 'infrared-buildings-3d';
      } else if (map.current.getLayer('heatmap-layer')) {
        beforeLayer = 'heatmap-layer';
      } else if (map.current.getLayer('buildings-3d')) {
        beforeLayer = 'buildings-3d';
      }

      const layerConfig = {
        id: 'ifc-buildings-3d',
        source: 'ifc-buildings',
        type: 'fill-extrusion',
        paint: {
          'fill-extrusion-color': '#FFB84D',
          'fill-extrusion-height': ['get', 'height'],
          'fill-extrusion-base': ['get', 'min_height'],
          'fill-extrusion-opacity': 0.85,
        },
      };

      if (beforeLayer) {
        map.current.addLayer(layerConfig, beforeLayer);
      } else {
        map.current.addLayer(layerConfig);
      }

      console.log('IFC building layer added');
    } catch (err) {
      console.warn('Could not add IFC building layer:', err);
    }
  }, [ifcBuildingData]);

  const addBuildingClickHandler = () => {
    if (!map.current) return;

    // Make building layers clickable
    map.current.on('click', 'buildings-3d', handleBuildingClick);
    map.current.on('click', 'infrared-buildings-3d', handleBuildingClick);
    map.current.on('click', 'ifc-buildings-3d', handleBuildingClick);

    // Change cursor on hover and show vulnerability tooltip
    ['buildings-3d', 'infrared-buildings-3d', 'ifc-buildings-3d'].forEach((layerId) => {
      map.current.on('mouseenter', layerId, (e) => {
        map.current.getCanvas().style.cursor = 'pointer';

        // Show vulnerability score in popup if available
        if (layerId === 'infrared-buildings-3d' && e.features && e.features.length > 0) {
          const feature = e.features[0];
          const vulnScore = feature.properties?.vulnerability_score;
          if (vulnScore !== undefined && vulnScore !== null) {
            new mapboxgl.Popup({ closeButton: false, closeOnClick: false })
              .setLngLat(e.lngLat)
              .setHTML(`
                <div style="padding: 0.5rem; font-size: 0.85rem;">
                  <strong>Heat Vulnerability: ${vulnScore}/10</strong><br/>
                  <small>${feature.properties?.utci_celsius || 'N/A'}°C UTCI</small>
                </div>
              `)
              .addTo(map.current);
          }
        }
      });

      map.current.on('mouseleave', layerId, () => {
        map.current.getCanvas().style.cursor = '';
        // Close any open popups from hover
        const popups = document.querySelectorAll('.mapboxgl-popup');
        popups.forEach((popup) => {
          if (popup.textContent.includes('Heat Vulnerability')) {
            popup.remove();
          }
        });
      });
    });
  };

  const handleBuildingClick = (e) => {
    if (!e.features || e.features.length === 0) return;

    const feature = e.features[0];
    const properties = feature.properties || {};
    const geometry = feature.geometry;

    // Determine which layer was clicked
    let sourceLayer = 'unknown';
    if (e.layer?.id === 'buildings-3d') sourceLayer = 'Mapbox Buildings';
    else if (e.layer?.id === 'infrared-buildings-3d') sourceLayer = 'Infrared Analysis';
    else if (e.layer?.id === 'ifc-buildings-3d') sourceLayer = 'IFC Model';

    // Extract building info
    const buildingInfo = {
      id: feature.id || Math.random(),
      source: sourceLayer,
      type: geometry.type,
      geometry: geometry,
      properties: properties,
      height: properties.height || 0,
      min_height: properties.min_height || 0,
      name: properties.name || 'Building',
    };

    // Get building center coordinates
    if (geometry.type === 'Polygon') {
      const coords = geometry.coordinates[0];
      let centerLng = 0,
        centerLat = 0;
      coords.forEach((coord) => {
        centerLng += coord[0];
        centerLat += coord[1];
      });
      buildingInfo.center = [centerLng / coords.length, centerLat / coords.length];
    }

    selectedBuildingRef.current = buildingInfo;
    onBuildingSelected?.(buildingInfo);
    highlightSelectedBuilding(buildingInfo);
  };

  const highlightSelectedBuilding = (buildingInfo) => {
    if (!map.current || !buildingInfo.geometry) return;

    // Remove previous selection layer
    if (map.current.getLayer('selected-building-highlight')) {
      map.current.removeLayer('selected-building-highlight');
    }
    if (map.current.getSource('selected-building-source')) {
      map.current.removeSource('selected-building-source');
    }

    // Add selection source
    map.current.addSource('selected-building-source', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: buildingInfo.geometry,
        properties: buildingInfo.properties,
      },
    });

    // Add highlight layer
    map.current.addLayer({
      id: 'selected-building-highlight',
      source: 'selected-building-source',
      type: 'fill-extrusion',
      paint: {
        'fill-extrusion-color': '#FFD700',
        'fill-extrusion-height': ['get', 'height'],
        'fill-extrusion-base': ['get', 'min_height'],
        'fill-extrusion-opacity': 0.9,
        'fill-extrusion-vertical-gradient': true,
      },
    });
  };

  const updateSelection = () => {
    const data = draw.current.getAll();
    console.log('Drawing updated:', { features: data.features.length });
    if (data.features.length > 0) {
      const feature = data.features[0];
      const center = centroid(feature).geometry.coordinates;
      console.log('Zone drawn:', { center, featureType: feature.geometry.type });
      onZoneDrawn({ feature, center });
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={mapContainer}
        style={{ width: '100%', height: '100%' }}
      />

      {/* Building Vulnerability Legend */}
      {buildingData && (
        <div
          style={{
            position: 'absolute',
            top: '1.5rem',
            right: '1.5rem',
            backgroundColor: 'white',
            padding: '1rem',
            borderRadius: '12px',
            boxShadow: '0 10px 25px rgba(15, 23, 42, 0.1)',
            border: '1px solid #E2E8F0',
            minWidth: '200px',
            zIndex: 10,
            backdropFilter: 'blur(8px)',
            background: 'rgba(255, 255, 255, 0.95)',
            fontSize: '0.85rem'
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '0.75rem', color: '#0F172A' }}>
            Heat Vulnerability
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: '20px', height: '20px', backgroundColor: '#c0392b', borderRadius: '3px' }} />
              <span>Critical (9-10)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: '20px', height: '20px', backgroundColor: '#e74c3c', borderRadius: '3px' }} />
              <span>High (7-9)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: '20px', height: '20px', backgroundColor: '#f39c12', borderRadius: '3px' }} />
              <span>Moderate (5-7)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: '20px', height: '20px', backgroundColor: '#f1c40f', borderRadius: '3px' }} />
              <span>Low-Moderate (3-5)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: '20px', height: '20px', backgroundColor: '#2ecc71', borderRadius: '3px' }} />
              <span>Low (0-3)</span>
            </div>
          </div>
        </div>
      )}

      {/* Intervention Opacity Slider */}
      {suggestedInterventions && suggestedInterventions.length > 0 && showInterventions && (
        <div
          style={{
            position: 'absolute',
            bottom: '1.5rem',
            left: '1.5rem',
            backgroundColor: 'white',
            padding: '1.25rem',
            borderRadius: '12px',
            boxShadow: '0 10px 25px rgba(15, 23, 42, 0.1)',
            border: '1px solid #E2E8F0',
            minWidth: '280px',
            zIndex: 10,
            backdropFilter: 'blur(8px)',
            background: 'rgba(255, 255, 255, 0.95)'
          }}
        >
          <div style={{ marginBottom: '1rem' }}>
            <label style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '0.95rem',
              fontWeight: 600,
              marginBottom: '0.75rem',
              color: '#0F172A'
            }}>
              <span>Intervention Visibility</span>
              <span style={{
                backgroundColor: '#E8F3FF',
                color: '#0F6FD9',
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                fontSize: '0.85rem',
                fontWeight: 700
              }}>
                {(interventionOpacityLocal * 100).toFixed(0)}%
              </span>
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={interventionOpacityLocal * 100}
              onChange={(e) => setInterventionOpacityLocal(parseFloat(e.target.value) / 100)}
              style={{
                width: '100%',
                height: '8px',
                appearance: 'none',
                backgroundColor: '#F1F5F9',
                borderRadius: '4px',
                outline: 'none',
                background: `linear-gradient(to right, #0F6FD9 0%, #0F6FD9 ${interventionOpacityLocal * 100}%, #E2E8F0 ${interventionOpacityLocal * 100}%, #E2E8F0 100%)`
              }}
            />
          </div>
          <div style={{
            fontSize: '0.8rem',
            color: '#78909C',
            display: 'flex',
            justifyContent: 'space-between',
            paddingTop: '0.75rem',
            borderTop: '1px solid #E2E8F0'
          }}>
            <span>📍 Current</span>
            <span>✨ Proposed</span>
          </div>
        </div>
      )}

      {/* Intervention Visualizer */}
      <InterventionVisualizer
        map={map}
        interventions={suggestedInterventions}
        showInterventions={showInterventions}
        opacity={interventionOpacityLocal}
        selectedBuilding={selectedBuilding}
      />
    </div>
  );
}
