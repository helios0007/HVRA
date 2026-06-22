// Building-level (IFC) analysis, rebuilt natively in our design system so the
// two tools read as one. It drives the teammate's FastAPI pipeline (proxied at
// /bapi → :8001) but renders everything in our dark theme.
//
// Results view ports her full UI natively: an interactive 3D IFC viewer
// (rooms colored by heat risk, click-to-select, before/after retrofit) beside a
// room portfolio + room panel (diagnosis, score breakdown, overheating hours,
// and retrofit cards with wall-section / louver diagrams that highlight the
// affected elements in the 3D model). Components live in ./building/ — copied
// from her vendored frontend so building-level/ stays untouched for subtree pulls.
//
// Grounding: when a building is selected in the urban tool, its lat/lon and
// construction era pre-fill the intake form, its measured UHI is fed into her
// pipeline, and its HVI/drivers are shown as context.

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { uploadBuilding } from '../services/buildingLevelAPI';
import { getHVIColorHex } from '../utils/hviColors';
import { urbanGroundingContext, buildUrbanContext } from '../utils/urbanGrounding';
import Viewer3D from './building/Viewer3D';
import RoomPanel from './building/RoomPanel';
import PortfolioView from './building/PortfolioView';
import ComfortIndicator from './building/ComfortIndicator';
import RenderView from './building/RenderView';
import ErrorBoundary from './building/ErrorBoundary';
import '../styles/BuildingAnalysisTab.css';
import '../styles/buildingViewer.css';

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

export default function BuildingAnalysisTab({ selectedBuilding, urbanAnalysis }) {
  const grounded = featureLonLat(selectedBuilding);
  const groundHvi = selectedBuilding?.properties?.hvi_score ?? selectedBuilding?.properties?.vulnerability_score;
  const groundDrivers = selectedBuilding?.properties?.drivers
    || selectedBuilding?.properties?.vulnerability_drivers || [];

  // Deep grounding: the urban tool's measured UHI delta for this zone, fed into
  // her pipeline so room thermal scores use our analysis, not a city average.
  const urban = useMemo(() => urbanGroundingContext(urbanAnalysis), [urbanAnalysis]);
  // Full site-context blob fed to her pipeline (deep grounding — wind, night UHI,
  // shading, outdoor HVI + drivers). Empty {} when no urban analysis is loaded.
  const urbanCtx = useMemo(
    () => buildUrbanContext(urbanAnalysis, selectedBuilding),
    [urbanAnalysis, selectedBuilding],
  );

  const [lat, setLat] = useState(grounded ? grounded[1] : 41.3851);
  const [lon, setLon] = useState(grounded ? grounded[0] : 2.1734);
  const [form, setForm] = useState(EMPTY_FORM);
  const [ifcFile, setIfcFile] = useState(null);
  const [state, setState] = useState('idle'); // idle | submitting | done | error
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);

  // Results-view state (mirrors her App.jsx)
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [viewerTab, setViewerTab] = useState('portfolio'); // portfolio | room
  const [beforeAfter, setBeforeAfter] = useState('before');
  const viewerRef = useRef(null);

  // AI-render flow (mirrors her App.jsx). Before/after is gated on hasRender so
  // an 'after' view never appears before a render actually exists.
  const [hasRender, setHasRender] = useState(false);
  const [renderHistory, setRenderHistory] = useState([]);
  const [renderIndex, setRenderIndex] = useState(-1);
  const [renderOpen, setRenderOpen] = useState(false);
  const [renderedRoomIds, setRenderedRoomIds] = useState(() => new Set());
  const effectiveBeforeAfter = hasRender ? beforeAfter : 'before';

  // Pre-fill location + era from the selected urban building (grounding).
  useEffect(() => {
    if (!selectedBuilding) return;
    const ll = featureLonLat(selectedBuilding);
    if (ll) { setLon(ll[0]); setLat(ll[1]); }
    const bracket = eraToBracket(selectedBuilding);
    if (bracket) setForm((p) => ({ ...p, construction_year: bracket }));
  }, [selectedBuilding]);

  // ── 3D highlight bridge (RetrofitCard / RoomPanel → Viewer3D) ──────────────
  const handleRoomSelect = useCallback((room) => {
    setSelectedRoom(room);
    setViewerTab('room');
  }, []);
  const handleStrategyHighlight = useCallback((globalIds, hexColor, roomGlobalId) => {
    viewerRef.current?.highlightElements(globalIds, hexColor, true, { roomGlobalId });
  }, []);
  const handleHighlightClear = useCallback(() => {
    viewerRef.current?.clearHighlights();
  }, []);
  const handleStrategyHighlightGroups = useCallback((groups, opts) => {
    viewerRef.current?.highlightGroups(groups, true, opts);
  }, []);
  const handleInspectRoomToggle = useCallback((roomGlobalId, on, riskLevel) => {
    if (on) viewerRef.current?.highlightInspectedRoom(roomGlobalId, riskLevel);
    else viewerRef.current?.clearInspectedRoomHighlight();
  }, []);

  // ── AI render bridge (RetrofitCard → RenderView, Street-View fallback via
  // a 3D viewport screenshot). Mirrors her App.jsx render handlers. ──────────
  const handleCaptureScreenshot = useCallback(
    () => viewerRef.current?.captureScreenshot() ?? Promise.resolve(null), []);
  const handleOpenRender = useCallback((req) => {
    const initialStatus = req.viewType === 'exterior' ? 'framing' : 'idle';
    setRenderHistory((prev) => {
      const next = [...prev, { ...req, status: initialStatus, imageUrl: null, error: null }];
      setRenderIndex(next.length - 1);
      return next;
    });
    setRenderOpen(true);
  }, []);
  const handleRenderNavigate = useCallback((i) => setRenderIndex(i), []);
  const handleRenderClose = useCallback(() => setRenderOpen(false), []);
  const handleRenderResolve = useCallback((i, patch) => {
    setRenderHistory((prev) => {
      const next = prev.map((h, idx) => (idx === i ? { ...h, ...patch } : h));
      if (patch.status === 'done') {
        const roomId = next[i]?.room?.room_id;
        if (roomId) setRenderedRoomIds((s) => new Set(s).add(roomId));
      }
      return next;
    });
    if (patch.status === 'done') setHasRender(true);
  }, []);

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
    // Deep grounding: pass the full measured site context (UHI day/night, peak/
    // mean UTCI, heat-stress %, prevailing wind, outdoor HVI + drivers, vegetation/
    // albedo, sky-openness shading). Her pipeline overrides its barri-table /
    // generic defaults per-field. Empty {} when no urban analysis is loaded →
    // standalone behaviour unchanged. `urban_uhi_delta` kept as a legacy fallback.
    if (urban.uhiDelta != null) fd.append('urban_uhi_delta', String(urban.uhiDelta));
    if (urbanCtx && Object.keys(urbanCtx).length > 0) {
      fd.append('urban_context', JSON.stringify(urbanCtx));
    }
    try {
      const data = await uploadBuilding(fd);
      setResult(data);
      setSelectedRoom(null);
      setViewerTab('portfolio');
      setBeforeAfter('before');
      setHasRender(false); setRenderHistory([]); setRenderIndex(-1);
      setRenderOpen(false); setRenderedRoomIds(new Set());
      setState('done');
    } catch (err) {
      setErrorMsg(err.message || 'Could not reach the building-level backend (is it running on :8001?).');
      setState('error');
    }
  };

  const reset = () => {
    setResult(null); setSelectedRoom(null); setViewerTab('portfolio');
    setBeforeAfter('before'); setState('idle');
    setHasRender(false); setRenderHistory([]); setRenderIndex(-1);
    setRenderOpen(false); setRenderedRoomIds(new Set());
  };

  // ---------------- Results view (full native port) ----------------
  if (state === 'done' && result) {
    return (
      <div className="ba-viewer">
        <div className="ba-viewer-head">
          <div className="ba-viewer-meta">
            <h3>Building analysis · {result.room_count} rooms</h3>
            <p className="ba-meta">
              {result.neighbourhood && <>{result.neighbourhood} · </>}
              UHI +{(result.uhi_delta ?? 0).toFixed(1)}°C
              {result.epw_synthetic && ' · synthetic climate'}
              {result.warnings?.length > 0 && ` · ${result.warnings.length} warning(s)`}
            </p>
          </div>
          <div className="ba-viewer-actions">
            {hasRender ? (
              <div className="ba-ba-toggle">
                <button className={effectiveBeforeAfter === 'before' ? 'active' : ''} onClick={() => setBeforeAfter('before')}>Before</button>
                <button className={effectiveBeforeAfter === 'after' ? 'active' : ''} onClick={() => setBeforeAfter('after')}>After retrofit</button>
              </div>
            ) : (
              <span className="ba-render-hint" title="Open a room → expand a shading/window strategy card → Render">
                Render a strategy to unlock before / after
              </span>
            )}
            <button className="btn-secondary" onClick={reset}>New assessment</button>
          </div>
        </div>

        <div className="ba-viewer-body">
          <aside className="ba-viewer-sidebar">
            {renderOpen && renderHistory.length > 0 ? (
              <RenderView
                history={renderHistory}
                index={renderIndex}
                onNavigate={handleRenderNavigate}
                onClose={handleRenderClose}
                onResolve={handleRenderResolve}
                onCaptureScreenshot={handleCaptureScreenshot}
              />
            ) : (
              <>
                <div className="ba-viewer-tabs">
                  <button className={viewerTab === 'portfolio' ? 'active' : ''} onClick={() => setViewerTab('portfolio')}>
                    All rooms ({result.rooms.length})
                  </button>
                  <button className={viewerTab === 'room' ? 'active' : ''} onClick={() => setViewerTab('room')} disabled={!selectedRoom}>
                    Room detail
                  </button>
                </div>
                <div className="ba-viewer-sidecontent">
                  {viewerTab === 'portfolio' && (
                    <PortfolioView rooms={result.rooms} selectedRoom={selectedRoom} onSelectRoom={handleRoomSelect} />
                  )}
                  {viewerTab === 'room' && selectedRoom && (
                    <RoomPanel
                      room={selectedRoom}
                      allRooms={result.rooms}
                      beforeAfter={effectiveBeforeAfter}
                      roofIds={result.roof_element_ids ?? []}
                      windDeg={result.prevailing_wind_deg}
                      crossVentSpaces={result.cross_ventilation?.spaces ?? []}
                      jobId={result.job_id}
                      onInspectRoomToggle={handleInspectRoomToggle}
                      onStrategyHighlight={handleStrategyHighlight}
                      onStrategyHighlightGroups={handleStrategyHighlightGroups}
                      onHighlightClear={handleHighlightClear}
                      onOpenRender={handleOpenRender}
                    />
                  )}
                  {viewerTab === 'room' && !selectedRoom && (
                    <p className="ba-hint">Click a room in the 3D viewer or the list to see its detail.</p>
                  )}
                </div>
              </>
            )}
          </aside>

          <main className="ba-viewer-main">
            <ErrorBoundary>
              <Viewer3D
                ref={viewerRef}
                key={result.job_id}
                jobId={result.job_id}
                rooms={result.rooms}
                selectedRoom={selectedRoom}
                onRoomSelect={handleRoomSelect}
                beforeAfter={effectiveBeforeAfter}
              />
            </ErrorBoundary>
            <div className="ba-viewer-legend">
              <span className="leg critical">Critical</span>
              <span className="leg high">High</span>
              <span className="leg moderate">Moderate</span>
              <span className="leg safe">Safe</span>
            </div>
            {/* Human comfort/vulnerability ring — building-wide, or the selected
                room's own risk; flips to "improved" once that room is rendered. */}
            <ComfortIndicator
              rooms={result.rooms}
              selectedRoom={selectedRoom}
              roomRendered={selectedRoom ? renderedRoomIds.has(selectedRoom.room_id) : false}
            />
          </main>
        </div>
      </div>
    );
  }

  // ---------------- Intake form view ----------------
  return (
    <form className="ba-form" onSubmit={submit}>
      <div className="ba-form-intro">
        <h3>Building-level analysis</h3>
        <p>Upload an IFC model for room-by-room heat-vulnerability diagnosis, retrofit strategies, and an interactive 3D model.</p>
      </div>

      {grounded || urban.uhiDelta != null ? (
        <div className="ba-grounding">
          <span className="ba-grounding-tag">Grounded in urban analysis</span>
          <span>
            {grounded
              ? <>Building at {lat.toFixed(5)}, {lon.toFixed(5)}</>
              : <>Using this zone's urban heat analysis</>}
            {groundHvi != null && <> · <strong style={{ color: getHVIColorHex(groundHvi) }}>HVI {Number(groundHvi).toFixed(1)}</strong></>}
            {urban.uhiDelta != null && (
              <> · <strong title={`Derived from this zone's heat load${urban.heatStressPct != null ? ` (${urban.heatStressPct.toFixed(0)}% heat-stress hours` : ''}${urban.peakUtci != null ? `, peak UTCI ${urban.peakUtci.toFixed(1)}°C)` : urban.heatStressPct != null ? ')' : ''} — overrides her barri-table default`}>
                UHI +{urban.uhiDelta.toFixed(1)}°C → building model
              </strong></>
            )}
            {groundDrivers.length > 0 && <> · {groundDrivers.slice(0, 3).join(', ')}</>}
          </span>
          {Object.keys(urbanCtx).length > 0 && (
            <span className="ba-grounding-extra">
              {urbanCtx.uhi_delta_night != null && <em>night UHI +{urbanCtx.uhi_delta_night.toFixed(1)}°C</em>}
              {urbanCtx.prevailing_wind_deg != null && <em>wind {Math.round(urbanCtx.prevailing_wind_deg)}°</em>}
              {urbanCtx.shading_factor != null && <em>sky-openness {(urbanCtx.shading_factor * 100).toFixed(0)}%</em>}
              {urbanCtx.dominant_driver && <em>priority: {urbanCtx.dominant_driver.replace(/_/g, ' ')}</em>}
              {urbanCtx.ground_albedo != null && <em>albedo {urbanCtx.ground_albedo.toFixed(2)}</em>}
            </span>
          )}
        </div>
      ) : (
        <div className="ba-grounding ba-grounding--muted">
          Tip: analyse a zone, then select a building in <strong>3D Explore</strong> or <strong>HVI Map</strong> to ground this analysis (location, era & measured UHI).
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
        {state === 'submitting' && <span className="ba-progress">Running pipeline — solar geometry + local LLM diagnosis, ~2–5 min…</span>}
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
