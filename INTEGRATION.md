# Integrated HVRA — Urban + Building level

One frontend, two backends. The building-level tool (teammate's repo
`gaellehabib24/HVRA_building_level`) is vendored under `building-level/` via
**git subtree** so it lives in this repo *and* stays updatable.

## Architecture
```
Browser → :5173 (single React UI — this repo's frontend)
   /api/*  ───────────────► :8000  urban backend   (this repo)
   /bapi/* ──Vite proxy───► :8001  building backend (building-level/hvra/backend)
```
- The **Building Analysis** tab is rebuilt natively in our dark theme (we do
  *not* run her :3000 frontend). It calls her API through the `/bapi` proxy, so
  no CORS change is needed in her code.
- **Grounding:** selecting a building in *3D Explore* or *HVI Map* pre-fills the
  building tab's location + construction era and shows its HVI as context.

## Run it (3 services)
```powershell
./start-all.ps1            # opens all three terminals
```
or manually:
```
# 1. urban backend
cd backend && python app.py                       # :8000
# 2. building backend (one-time venv + deps first)
cd building-level/hvra/backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt   # ifcopenshell, osmnx, anthropic…
# set ANTHROPIC_API_KEY in building-level/hvra/backend/.env
.\.venv\Scripts\uvicorn main:app --port 8001      # :8001
# 3. frontend
cd frontend && npm run dev                         # :5173
```
The urban tool works on its own; only the **Building Analysis** tab needs :8001.

## Pulling her latest changes
```
git subtree pull --prefix=building-level https://github.com/gaellehabib24/HVRA_building_level main --squash
```
Golden rule: **don't edit files under `building-level/`** — keep all glue in
`frontend/` so subtree pulls never conflict. Deep-grounding fields (passing our
UHI/LST into her pipeline) should be added by her, in her repo, then pulled.

## Not yet ported
The interactive 3D IFC viewer (rooms highlighted on the model, before/after
retrofit) is her heavy `@thatopen/components` viewer — next phase to bring in.
