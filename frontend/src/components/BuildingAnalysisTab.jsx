// Building-level (IFC) analysis, rebuilt natively in our design system so the
// two tools read as one. It drives the teammate's FastAPI pipeline (proxied at
// /bapi → :8001) but renders everything in our dark theme.
//
// Grounding: when a building is selected in the urban tool, its lat/lon and
// construction era pre-fill the intake form, and its HVI/drivers are shown as
// context — so the room-level analysis is anchored to the urban diagnosis.

import { useState, useEffect, useMemo, useCallback } from 'react';
import { uploadBuilding, getShortlist } from '../services/buildingLevelAPI';
import { getHVIColorHex } from '../utils/hviColors';
import '../styles/BuildingAnalysisTab.css';

// Strategy display names (mirrors her strategyMeta.js — fallback prettifies key)
const STRATEGY_LABELS = {
  external_shading_louvers: 'External louvers / brise-soleil',
  operable_external_sunscreen: 'Operable external sunscreen',
  window_external_shutters: 'External shutters (persianes)',
  green_pergola: 'Climbing vegetation screen (green façade)',
  window_enlargement: 'Window enlargement',
  interior_opening_improvement: 'Transom / interior opening',
  stack_effect_roof_vent: 'Stack-effect roof vent',
  external_wall_insulation_etics: 'External wall insulation — ETICS',
  internal_wall_insulation: 'Internal wall insulation',
  roof_insulation: 'Roof insulation membrane',
  cool_roof_coating: 'Cool roof reflective coating',
  solar_control_glazing: 'Solar control glazing',
  cool_facade_paint: 'Cool / reflective façade paint',
  phase_change_materials: 'Phase-change materials (PCM)',
  internal_blinds: 'Internal roller blinds',
  night_purge_ventilation: 'Night purge ventilation',
  cross_ventilation_behaviour: 'Cross-ventilation protocol',
  courtyard_greening: 'Courtyard greening',
  street_tree_canopy: 'Street tree canopy',
  shared_cooling_refuge: 'Shared cooling refuge',
};

const RISK_COLOR = {
  Critical: '#b10026',
  High: '#fc4e2a',
  Moderate: '#fdae61',
  Safe: '#66bd63',
};

const prettyKey = (k) => String(k || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const strategyName = (s) =>
  s?.name || s?.title || STRATEGY_LABELS[s?.strategy || s?.id || s?.key] || prettyKey(s?.strategy || s?.id || s?.key || s);

const EMPTY_FORM = {
  construction_year: '', roof_colour: '', heritage_protection: '', shutter_boxes: '',
  oldest_resident_age: '', ac_access: '', income_category: '', mobility_limitations: '',
};

// Centroid [lon,lat] of an urban building feature.
function featureLonLat(feature) {
  if (!feature) return null;
  const c = feature.properties?.center;
  if (Array.isArray(c) && c.length === 2) return c;
  const g = feature.geometry;
  const ring = g?.type === 'Polygon' ? g.coordinates?.[0]
    : g?.type === 'MultiPolygon' ? g.coordinates?.[0]?.[0] : null;
  if (!ring?.length) return null;
  let x = 0, y = 0;
  for (const [lx, ly] of ring) { x += lx; y += ly; }
  return [x / ring.length, y / ring.length];
}

// Our construction-era factor (0–1, higher = older) → her era bracket.
function eraToBracket(feature) {
  const yr = feature?.properties?.construction_year;
  if (typeof yr === 'number') {
    if (yr < 1960) return 'pre-1960';
    if (yr < 1980) return '1960-1979';
    if (yr <= 2006) return '1980-2006';
    return 'post-2006';
  }
  const s = feature?.properties?.hvi_factors?.construction_era?.score;
  if (typeof s === 'number') {
    if (s >= 0.75) return 'pre-1960';
    if (s >= 0.5) return '1960-1979';
    if (s >= 0.3) return '1980-2006';
    return 'post-2006';
  }
  return '';
}

export default function BuildingAnalysisTab({ selectedBuilding }) {
  const grounded = featureLonLat(selectedBuilding);
  const groundHvi = selectedBuilding?.properties?.hvi_score ?? selectedBuilding?.properties?.vulnerability_score;
  const groundDrivers = selectedBuilding?.properties?.drivers
    || selectedBuilding?.properties?.vulnerability_drivers || [];

  const [lat, setLat] = useState(grounded ? grounded[1] : 41.3851);
  const [lon, setLon] = useState(grounded ? grounded[0] : 2.1734);
  const [form, setForm] = useState(EMPTY_FORM);
  const [ifcFile, setIfcFile] = useState(null);
  const [state, setState] = useState('idle'); // idle | submitting | done | error
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [shortlist, setShortlist] = useState(null);

  // Pre-fill location + era from the selected urban building (grounding).
  useEffect(() => {
    if (!selectedBuilding) return;
    const ll = featureLonLat(selectedBuilding);
    if (ll) { setLon(ll[0]); setLat(ll[1]); }
    const bracket = eraToBracket(selectedBuilding);
    if (bracket) setForm((p) => ({ ...p, construction_year: bracket }));
  }, [selectedBuilding]);

  const setField = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }));

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.ifc')) {
      e.target.value = '';
      setErrorMsg('Only .ifc files are accepted (export from Revit/ArchiCAD as IFC 2x3).');
      setState('error');
      return;
    }
    setIfcFile(f);
    setErrorMsg('');
    if (state === 'error') setState('idle');
  };

  const allFilled = Object.values(form).every(Boolean) && ifcFile && lat && lon;

  const submit = async (e) => {
    e.preventDefault();
    if (!allFilled) { setErrorMsg('Complete every field and choose an IFC file first.'); setState('error'); return; }
    setState('submitting'); setErrorMsg('');
    const fd = new FormData();
    fd.append('ifc_file', ifcFile);
    fd.append('lat', String(lat));
    fd.append('lon', String(lon));
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    try {
      const data = await uploadBuilding(fd);
      setResult(data);
      setState('done');
      setSelectedRoom(null);
      getShortlist(data.job_id).then(setShortlist).catch(() => setShortlist(null));
    } catch (err) {
      setErrorMsg(err.message || 'Could not reach the building-level backend (is it running on :8001?).');
      setState('error');
    }
  };

  const reset = () => { setResult(null); setSelectedRoom(null); setShortlist(null); setState('idle'); };

  const sortedRooms = useMemo(
    () => (result?.rooms ? [...result.rooms].sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)) : []),
    [result]
  );

  const roomShortlist = useCallback((room) => {
    const inline = room?.ai_outputs?.shortlist || room?.shortlist;
    if (Array.isArray(inline) && inline.length) return inline;
    if (Array.isArray(shortlist)) {
      const match = shortlist.find((s) => s.room_id === room?.room_id);
      return match?.shortlist || match?.strategies || [];
    }
    return [];
  }, [shortlist]);

  // ---------------- Results view ----------------
  if (state === 'done' && result) {
    const room = selectedRoom;
    return (
      <div className="ba-results">
        <div className="ba-results-head">
          <div>
            <h3>Building analysis · {result.room_count} rooms</h3>
            <p className="ba-meta">
              {result.neighbourhood && <>{result.neighbourhood} · </>}
              UHI +{(result.uhi_delta ?? 0).toFixed(1)}°C
              {result.epw_synthetic && ' · synthetic climate'}
              {result.warnings?.length > 0 && ` · ${result.warnings.length} warning(s)`}
            </p>
          </div>
          <button className="btn-secondary" onClick={reset}>New assessment</button>
        </div>

        <div className="ba-results-grid">
          <div className="ba-roomlist">
            <h4 className="section-title">Rooms by heat risk</h4>
            <table className="ba-table">
              <thead><tr><th>#</th><th>Room</th><th>Fl.</th><th>Risk</th><th>Score</th></tr></thead>
              <tbody>
                {sortedRooms.map((r, i) => {
                  const risk = r.thermal_scores?.risk_level;
                  const sel = room?.room_id === r.room_id;
                  return (
                    <tr key={r.room_id || i} className={sel ? 'sel' : ''} onClick={() => setSelectedRoom(r)}>
                      <td>{i + 1}</td>
                      <td><span className="ba-room-name">{r.room_name || '—'}</span><span className="ba-room-type">{r.room_type}</span></td>
                      <td>{r.floor ?? '—'}</td>
                      <td><span className="ba-risk" style={{ background: RISK_COLOR[risk] || '#888' }}>{risk || '—'}</span></td>
                      <td className="ba-score">{r.composite_score != null ? r.composite_score.toFixed(2) : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="ba-roomdetail">
            {!room && <p className="ba-hint">Select a room to see its diagnosis and top retrofit strategies.</p>}
            {room && (
              <>
                <h4 className="section-title">{room.room_name} <span className="section-hint">· {room.room_type}</span></h4>
                <div className="ba-room-stats">
                  <span className="ba-risk" style={{ background: RISK_COLOR[room.thermal_scores?.risk_level] || '#888' }}>
                    {room.thermal_scores?.risk_level || '—'}
                  </span>
                  {room.composite_score != null && <span className="ba-chip">score {room.composite_score.toFixed(2)}</span>}
                  {room.area_m != null && <span className="ba-chip">{room.area_m} m²</span>}
                  {room.facades?.[0]?.orientation && <span className="ba-chip">{room.facades[0].orientation}</span>}
                </div>
                {room.ai_outputs?.diagnosis && <p className="ba-diagnosis">{room.ai_outputs.diagnosis}</p>}
                <h4 className="section-title">Recommended retrofits</h4>
                {roomShortlist(room).length === 0 && <p className="ba-hint">No shortlist returned for this room.</p>}
                {roomShortlist(room).map((s, i) => (
                  <div key={i} className="ba-strategy">
                    <div className="ba-strategy-head">
                      <span className="ba-strategy-rank">{i + 1}</span>
                      <span className="ba-strategy-name">{strategyName(s)}</span>
                    </div>
                    {(s.reason || s.rationale || s.why) && <p className="ba-strategy-why">{s.reason || s.rationale || s.why}</p>}
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        <p className="ba-foot">
          Interactive 3D IFC viewer (rooms highlighted on the model, before/after retrofit) is available in
          the building-level tool and is the next piece to bring into this view.
        </p>
      </div>
    );
  }

  // ---------------- Intake form view ----------------
  return (
    <form className="ba-form" onSubmit={submit}>
      <div className="ba-form-intro">
        <h3>Building-level analysis</h3>
        <p>Upload an IFC model for room-by-room heat-vulnerability diagnosis and retrofit strategies.</p>
      </div>

      {grounded ? (
        <div className="ba-grounding">
          <span className="ba-grounding-tag">Grounded in urban analysis</span>
          <span>
            Building at {lat.toFixed(5)}, {lon.toFixed(5)}
            {groundHvi != null && <> · <strong style={{ color: getHVIColorHex(groundHvi) }}>HVI {Number(groundHvi).toFixed(1)}</strong></>}
            {groundDrivers.length > 0 && <> · {groundDrivers.slice(0, 3).join(', ')}</>}
          </span>
        </div>
      ) : (
        <div className="ba-grounding ba-grounding--muted">
          Tip: select a building in <strong>3D Explore</strong> or <strong>HVI Map</strong> first to auto-fill location & era.
        </div>
      )}

      <div className="ba-field-grid">
        <div className="ba-field"><label>Latitude</label>
          <input type="number" step="0.00001" value={lat} onChange={(e) => setLat(parseFloat(e.target.value))} /></div>
        <div className="ba-field"><label>Longitude</label>
          <input type="number" step="0.00001" value={lon} onChange={(e) => setLon(parseFloat(e.target.value))} /></div>
      </div>

      <div className="ba-field ba-file">
        <label>IFC model (.ifc, with IfcSpaces)</label>
        <label className="ba-file-btn">
          <input type="file" accept=".ifc" onChange={handleFile} />
          <span>{ifcFile ? ifcFile.name : 'Choose .ifc file'}</span>
        </label>
      </div>

      <h4 className="section-title">Building data</h4>
      <div className="ba-field-grid">
        <Select label="Construction year" name="construction_year" value={form.construction_year} onChange={setField}
          options={[['pre-1960', 'Pre-1960'], ['1960-1979', '1960–1979'], ['1980-2006', '1980–2006'], ['post-2006', 'Post-2006']]} />
        <Select label="Roof colour / material" name="roof_colour" value={form.roof_colour} onChange={setField}
          options={[['dark_tile', 'Dark tile / asphalt'], ['terracotta', 'Red / terracotta'], ['light_tile', 'Light / cream tile'], ['metal', 'Metal (galvanized)'], ['reflective', 'White / reflective']]} />
        <Select label="Heritage protection" name="heritage_protection" value={form.heritage_protection} onChange={setField}
          options={[['yes', 'Yes — ETICS restricted'], ['no', 'No']]} />
        <Select label="Window shutter boxes" name="shutter_boxes" value={form.shutter_boxes} onChange={setField}
          options={[['yes', 'Yes — present'], ['no', 'No']]} />
      </div>

      <h4 className="section-title">Occupant profile</h4>
      <div className="ba-field-grid">
        <Select label="Oldest resident age" name="oldest_resident_age" value={form.oldest_resident_age} onChange={setField}
          options={[['under-65', 'Under 65'], ['65-75', '65–75'], ['75+', '75+']]} />
        <Select label="AC access" name="ac_access" value={form.ac_access} onChange={setField}
          options={[['yes', 'Yes'], ['no', 'No']]} />
        <Select label="Income category" name="income_category" value={form.income_category} onChange={setField}
          options={[['low', 'Low'], ['medium', 'Medium'], ['high', 'High']]} />
        <Select label="Mobility limitations" name="mobility_limitations" value={form.mobility_limitations} onChange={setField}
          options={[['yes', 'Yes'], ['no', 'No']]} />
      </div>

      {state === 'error' && <div className="ba-error">{errorMsg}</div>}

      <div className="ba-form-footer">
        {state === 'submitting' && <span className="ba-progress">Running pipeline — solar geometry + LLM diagnosis, ~2–5 min…</span>}
        <button type="submit" className="diagram-generate" disabled={state === 'submitting'}>
          {state === 'submitting' ? 'Analyzing…' : 'Run building analysis'}
        </button>
      </div>
    </form>
  );
}

function Select({ label, name, value, onChange, options }) {
  return (
    <div className="ba-field">
      <label htmlFor={name}>{label}</label>
      <select id={name} name={name} value={value} onChange={onChange} required>
        <option value="">Select…</option>
        {options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </div>
  );
}
