import React, { useState, useCallback } from "react";
import { GoogleMap, useJsApiLoader, Marker } from "@react-google-maps/api";
import "./IntakeForm.css";

const MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const MAP_CENTER = { lat: 41.3851, lng: 2.1734 }; // Barcelona
const MAP_STYLE = { width: "100%", height: "380px", borderRadius: "6px" };

const INITIAL_FORM = {
  construction_year: "",
  roof_colour: "",
  heritage_protection: "",
  shutter_boxes: "",
  oldest_resident_age: "",
  ac_access: "",
  income_category: "",
  mobility_limitations: "",
};

export default function IntakeForm({ onSuccess }) {
  const { isLoaded, loadError } = useJsApiLoader({ googleMapsApiKey: MAPS_API_KEY });

  const [markerPos, setMarkerPos] = useState(null);
  const [ifcFile, setIfcFile] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [submitState, setSubmitState] = useState("idle"); // idle | submitting | success | error
  const [errorMsg, setErrorMsg] = useState("");
  const [responseData, setResponseData] = useState(null);

  const handleMapClick = useCallback((e) => {
    setMarkerPos({ lat: e.latLng.lat(), lng: e.latLng.lng() });
  }, []);

  const handleField = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".ifc")) {
      e.target.value = "";
      alert("Only .ifc files are accepted. Export from Revit/ArchiCAD as IFC 2x3.");
      return;
    }
    setIfcFile(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!markerPos) {
      alert("Click on the map to set the building location before submitting.");
      return;
    }
    if (!ifcFile) {
      alert("Upload an IFC file before submitting.");
      return;
    }

    setSubmitState("submitting");
    setErrorMsg("");

    const fd = new FormData();
    fd.append("ifc_file", ifcFile);
    fd.append("lat", String(markerPos.lat));
    fd.append("lon", String(markerPos.lng));
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));

    try {
      const res = await fetch(`${API_URL}/upload`, { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Server error" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (onSuccess) {
        onSuccess(data);
      } else {
        setResponseData(data);
        setSubmitState("success");
      }
    } catch (err) {
      setErrorMsg(err.message || "Could not reach the backend. Is it running on port 8000?");
      setSubmitState("error");
    }
  };

  const handleReset = () => {
    setSubmitState("idle");
    setMarkerPos(null);
    setIfcFile(null);
    setForm(INITIAL_FORM);
    setResponseData(null);
    setErrorMsg("");
  };

  if (submitState === "success") {
    return (
      <div className="success-screen">
        <div className="success-icon">✓</div>
        <h2>Upload received</h2>
        <p>
          <strong>{responseData?.filename}</strong> uploaded successfully.
        </p>
        <p className="success-note">
          Location: {responseData?.building?.location?.lat?.toFixed(5)},{" "}
          {responseData?.building?.location?.lon?.toFixed(5)}
        </p>
        <p className="success-note pipeline-note">
          Analysis pipeline is not yet wired (Stage 1 scaffold). The /upload endpoint
          accepted all form data and saved the IFC file.
        </p>
        <button className="btn-secondary" onClick={handleReset}>
          Start new assessment
        </button>
      </div>
    );
  }

  return (
    <form className="intake-form" onSubmit={handleSubmit} noValidate>
      <div className="form-intro">
        <h1>Building Assessment</h1>
        <p>Complete all fields to submit a building for heat vulnerability analysis.</p>
      </div>

      {/* ── Section 1: Location ── */}
      <section className="form-section">
        <div className="section-header">
          <span className="section-num">01</span>
          <div>
            <h2>Building location</h2>
            <p className="section-hint">Click directly on your building on the map.</p>
          </div>
        </div>

        {!MAPS_API_KEY && (
          <div className="alert alert-warn">
            No Google Maps API key found. Copy <code>.env.example</code> to <code>.env</code> and add
            your key, then restart the dev server.
          </div>
        )}

        {loadError && (
          <div className="alert alert-error">
            Google Maps failed to load — check your API key and network connection.
          </div>
        )}

        {!isLoaded && !loadError && (
          <div className="map-skeleton">Loading map…</div>
        )}

        {isLoaded && (
          <GoogleMap
            mapContainerStyle={MAP_STYLE}
            center={markerPos || MAP_CENTER}
            zoom={14}
            onClick={handleMapClick}
            options={{ disableDefaultUI: false, clickableIcons: false }}
          >
            {markerPos && <Marker position={markerPos} />}
          </GoogleMap>
        )}

        {markerPos ? (
          <p className="coords-display">
            Lat {markerPos.lat.toFixed(6)} &nbsp;/&nbsp; Lon {markerPos.lng.toFixed(6)}
          </p>
        ) : (
          <p className="coords-placeholder">No location selected yet</p>
        )}
      </section>

      {/* ── Section 2: IFC file ── */}
      <section className="form-section">
        <div className="section-header">
          <span className="section-num">02</span>
          <div>
            <h2>IFC model</h2>
            <p className="section-hint">
              Export from Revit / ArchiCAD / Rhino as IFC 2x3. Ensure "Export rooms and spaces"
              is checked.
            </p>
          </div>
        </div>

        <label className="file-label">
          <input type="file" accept=".ifc" required onChange={handleFile} />
          <span className="file-btn">Choose .ifc file</span>
          <span className="file-name">{ifcFile ? ifcFile.name : "No file chosen"}</span>
        </label>
      </section>

      {/* ── Section 3: Building data ── */}
      <section className="form-section">
        <div className="section-header">
          <span className="section-num">03</span>
          <div>
            <h2>Building data</h2>
          </div>
        </div>

        <div className="field-grid">
          <div className="field">
            <label htmlFor="construction_year">Construction year</label>
            <select
              id="construction_year"
              name="construction_year"
              required
              value={form.construction_year}
              onChange={handleField}
            >
              <option value="">Select era…</option>
              <option value="pre-1960">Pre-1960</option>
              <option value="1960-1979">1960–1979</option>
              <option value="1980-2006">1980–2006</option>
              <option value="post-2006">Post-2006</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="roof_colour">Roof colour / material</label>
            <select
              id="roof_colour"
              name="roof_colour"
              required
              value={form.roof_colour}
              onChange={handleField}
            >
              <option value="">Select…</option>
              <option value="dark_tile">Dark tile / dark asphalt</option>
              <option value="terracotta">Red / terracotta tile</option>
              <option value="light_tile">Light grey / cream tile</option>
              <option value="metal">Metal (unpainted / galvanized)</option>
              <option value="reflective">White / reflective coating</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="heritage_protection">Heritage protection zone</label>
            <select
              id="heritage_protection"
              name="heritage_protection"
              required
              value={form.heritage_protection}
              onChange={handleField}
            >
              <option value="">Select…</option>
              <option value="yes">Yes — ETICS restricted</option>
              <option value="no">No</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="shutter_boxes">Existing window shutter boxes</label>
            <select
              id="shutter_boxes"
              name="shutter_boxes"
              required
              value={form.shutter_boxes}
              onChange={handleField}
            >
              <option value="">Select…</option>
              <option value="yes">Yes — shutter boxes present</option>
              <option value="no">No</option>
            </select>
          </div>
        </div>
      </section>

      {/* ── Section 4: Occupant profile ── */}
      <section className="form-section">
        <div className="section-header">
          <span className="section-num">04</span>
          <div>
            <h2>Occupant profile</h2>
            <p className="section-hint">
              Drives the vulnerability multiplier used in age-weighted overheating hours (KPI 4).
            </p>
          </div>
        </div>

        <div className="field-grid">
          <div className="field">
            <label htmlFor="oldest_resident_age">Age of oldest resident</label>
            <select
              id="oldest_resident_age"
              name="oldest_resident_age"
              required
              value={form.oldest_resident_age}
              onChange={handleField}
            >
              <option value="">Select bracket…</option>
              <option value="under-65">Under 65</option>
              <option value="65-75">65–75</option>
              <option value="75+">75+</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="ac_access">AC access</label>
            <select
              id="ac_access"
              name="ac_access"
              required
              value={form.ac_access}
              onChange={handleField}
            >
              <option value="">Select…</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="income_category">Income category</label>
            <select
              id="income_category"
              name="income_category"
              required
              value={form.income_category}
              onChange={handleField}
            >
              <option value="">Select category…</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="mobility_limitations">Mobility limitations</label>
            <select
              id="mobility_limitations"
              name="mobility_limitations"
              required
              value={form.mobility_limitations}
              onChange={handleField}
            >
              <option value="">Select…</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
        </div>
      </section>

      {submitState === "error" && (
        <div className="alert alert-error">{errorMsg}</div>
      )}

      <div className="form-footer">
        <button
          type="submit"
          className="btn-primary"
          disabled={submitState === "submitting"}
        >
          {submitState === "submitting" ? "Uploading…" : "Submit building"}
        </button>
      </div>
    </form>
  );
}
