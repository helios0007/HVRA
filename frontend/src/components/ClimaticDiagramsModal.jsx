import { useState } from 'react';
import ApartmentSection from './ApartmentSection';
import ClimaticSection from './ClimaticSection';
import PlanDrawing from './PlanDrawing';
import '../styles/ClimaticDiagramsModal.css';

export default function ClimaticDiagramsModal({ isOpen, onClose, selectedBuilding, zoneAnalysis }) {
  const [solarTime, setSolarTime] = useState(15); // 15:00 by default
  const [solarTimeLabel, setSolarTimeLabel] = useState('15:00');

  if (!isOpen) return null;

  // Mock model data for apartment section (would come from backend analysis)
  const apartmentModel = {
    before: { outdoor: 37.3, indoor: 34.2 },
    after: { outdoor: 37.3, indoor: 35.4 },
    indoorBefore: 34.2,
    indoorAfter: 35.4,
    surfacesBefore: { sw_wall: 52, roof: 58, floor: 28 },
    surfacesAfter: { sw_wall: 48, roof: 51, floor: 28 },
    applied: [
      { path: 'roof', label: 'Cool roof coating' },
      { path: 'sw_window', label: 'External shading' },
      { path: 'ventilation', label: 'Cross-ventilation' },
    ],
    comfortCeiling: 26,
  };

  const climaticModel = {
    outdoor: 37.3,
    zones: [
      { x: 50, name: 'SW facade', t: 52, driver: 'solar' },
      { x: 200, name: 'Street level', t: 34, driver: 'uhi' },
      { x: 350, name: 'Shaded zone', t: 29, driver: 'vegetation' },
    ],
  };

  const handleSolarTimeChange = (e) => {
    const value = parseFloat(e.target.value);
    setSolarTime(value);

    if (value === 12) setSolarTimeLabel('12:00');
    else if (value === 15) setSolarTimeLabel('15:00');
    else if (value === 17) setSolarTimeLabel('17:00');
    else if (value === -1) setSolarTimeLabel('Night');
  };

  return (
    <div className="climatic-diagrams-modal-overlay" onClick={onClose}>
      <div className="climatic-diagrams-modal" onClick={(e) => e.stopPropagation()}>
        <div className="climatic-diagrams-header">
          <h2>Climatic diagrams</h2>
          <p>Computed drawings — solar geometry, cast shadows and Landsat surface temperature for the selected building</p>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="climatic-diagrams-controls">
          <div className="solar-control">
            <label>SOLAR TIME</label>
            <div className="solar-slider-container">
              <input
                type="range"
                min="12"
                max="17"
                step="1"
                value={solarTime === -1 ? 17.5 : solarTime}
                onChange={handleSolarTimeChange}
                className="solar-slider"
              />
              <div className="solar-time-labels">
                <span className={solarTime === 12 ? 'active' : ''}>12:00</span>
                <span className={solarTime === 15 ? 'active' : ''}>15:00</span>
                <span className={solarTime === 17 ? 'active' : ''}>17:00</span>
                <button
                  className={`night-btn ${solarTime === -1 ? 'active' : ''}`}
                  onClick={() => {
                    setSolarTime(-1);
                    setSolarTimeLabel('Night');
                  }}
                >
                  Night
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="climatic-diagrams-content">
          {/* Apartment Section — Before/After */}
          <section className="diagram-section apartment-section">
            <h3>Coupled performance — the resident's apartment</h3>
            <ApartmentSection model={apartmentModel} ox={50} isAfter={false} />
          </section>

          {/* Climatic Section */}
          <section className="diagram-section climatic-section">
            <h3>Climatic section</h3>
            <ClimaticSection
              model={climaticModel}
              interventions={apartmentModel.applied}
              solarTime={solarTime}
            />
          </section>

          {/* Intervention Plan */}
          <section className="diagram-section intervention-plan">
            <h3>Intervention plan</h3>
            <PlanDrawing plan={zoneAnalysis?.intervention_plan} />
          </section>
        </div>
      </div>
    </div>
  );
}
