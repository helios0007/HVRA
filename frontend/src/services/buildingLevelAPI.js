// Client for the building-level (IFC) backend — teammate's FastAPI service.
//
// In dev the browser calls our own origin under /bapi/*, and Vite proxies that
// to http://localhost:8001 (see vite.config.js). That keeps everything
// same-origin (no CORS change in her repo) and lets us swap the real host via
// VITE_BUILDING_API_BASE_URL for a deployed setup.

const BASE = import.meta.env.VITE_BUILDING_API_BASE_URL || '/bapi';

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Building API ${res.status} on ${path}`);
  return res.json();
}

export async function health() {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// Runs the full pipeline synchronously on the backend (≈2–5 min) and returns
// the complete result: { job_id, room_count, rooms[], neighbourhood, uhi_delta,
// roof_element_ids, prevailing_wind_deg, warnings, inputs, ... }.
export async function uploadBuilding(formData) {
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const getRoomProblems = (jobId) => getJSON(`/jobs/${jobId}/room_problems`);
export const getShortlist = (jobId) => getJSON(`/jobs/${jobId}/shortlist`);
export const getPriority = (jobId) => getJSON(`/jobs/${jobId}/priority`);
export const getEligibleStrategies = (jobId) => getJSON(`/jobs/${jobId}/eligible_strategies`);
export const ifcUrl = (jobId, after = false) => `${BASE}/jobs/${jobId}/ifc${after ? '_after' : ''}`;
