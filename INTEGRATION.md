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
- **LLM = local Ollama**, not Anthropic. Her `analysis/llm.py` already supports
  this; `building-level/hvra/backend/.env` sets `LLM_PROVIDER=ollama` /
  `OLLAMA_MODEL=llama3.1:latest`. No API key, no cost, fully offline.

## Deep grounding (urban → building)
Our urban analysis is passed *into* her thermal pipeline, not just shown beside it:
- The frontend derives a **UHI delta (°C)** for the drawn zone from its mean UTCI
  (`frontend/src/utils/urbanGrounding.js`) and sends it as `urban_uhi_delta` on
  `/upload` when a zone has been analysed.
- Her pipeline applies UHI to every outdoor-temperature hour
  (`T_outdoor = T_epw + uhi_delta`). With our value present it **overrides her
  barri-table city average**, so room thermal scores reflect the zone we actually
  measured. Absent → she falls back to her own lookup (standalone unchanged).
- The building tab pre-fills location + construction era from the selected
  building and shows the UHI being passed; her response echoes
  `neighbourhood = "… · urban-grounded"`.

### ⚠️ Deliberate, gated exceptions to the golden rule
Two features need code *inside* her backend; both are **additive and gated** so
her standalone behaviour is unchanged, and both are tagged so they're trivial to
re-apply after a `git subtree pull` (grep the tag, re-add the block).

`# [urban-grounding]` — deep grounding (her pipeline must *read* our value):
- `main.py` — `urban_uhi_delta: float | None = Form(None)`, forwarded to the pipeline + echoed in `inputs`.
- `analysis/pipeline.py` — same optional param; overrides `uhi_delta` only when provided.

`# [ollama-fix]` — makes the local-LLM path actually produce *useful* output:
- `analysis/llm.py` — under the bare `format="json"`, qwen2.5:7b / llama3.1:8b
  *continue* the large input JSON (echo fields, invent weather/date) → 0 usable
  diagnoses. Fix = two helpers used only by the Ollama branch:
  `_ollama_format_schema(system)` returns the stage's concrete **JSON Schema** so
  Ollama structured outputs grammar-constrain the keys (no hallucinated fields);
  `_ollama_user_reminder(system)` adds a stage-aware nudge so the model fills each
  field with substance (without it, it satisfies the schema lazily, e.g.
  `diagnosis:"moderate"`). Result with qwen2.5:7b: 12/12 rooms, full-sentence
  diagnoses + retrofit shortlists. Anthropic branch untouched.
  Recommended model: `qwen2.5:7b` (set in `.env`); llama3.1:8b also works now but
  is weaker. Pull once: `ollama pull qwen2.5:7b`.

On a subtree-pull conflict: keep her version, then `grep -rn "\[urban-grounding\]\|\[ollama-fix\]"`
in this repo's git history and re-apply the marked blocks (or upstream them with her).

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
py -3.12 -m venv .venv                              # 3.12 — no 3.14 wheels for her stack
.\.venv\Scripts\python -m pip install -r requirements.txt  # ifcopenshell, osmnx, pvlib…
# LLM = local Ollama (already configured in .env). Ensure Ollama is running +
#   the model is pulled:  ollama pull llama3.1
.\.venv\Scripts\uvicorn main:app --port 8001       # :8001
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

## Building tab — full native port (done)
Her whole results UI now runs inside our **Building Analysis** tab, dark-themed:
- **Interactive 3D IFC viewer** (`@thatopen/components` + `three`) — rooms colored
  by heat risk, click-to-select, show/hide risk volumes, section cut, and a
  **Before / After retrofit** toggle (loads `/jobs/{id}/ifc` vs `/ifc_after`).
- **Room portfolio + room panel** — diagnosis, risk breakdown, overheating-hours
  table, occupant/ventilation/envelope, and **retrofit cards** with
  wall-section / louver diagrams that **highlight the affected elements in 3D**.

Mechanics:
- Components are **copied** from her frontend into `frontend/src/components/building/`
  (so `building-level/` stays untouched). Only change made to the copies: Viewer3D's
  API base → `/bapi` (was her `:8000`).
- Deps added to our frontend: `three@^0.175`, `@thatopen/components@^2.4`. The old
  unused `web-ifc` / `web-ifc-viewer` pins were removed (they conflicted with
  `@thatopen/fragments`’ `web-ifc@0.0.68`). `vite.config.js` excludes them from
  pre-bundle and includes `.wasm` assets.
- `ifcLoader.setup()` fetches `web-ifc.wasm` from the CDN at runtime → **needs
  internet** the first time a model loads.
- Because these are copies, they won't auto-update on `subtree pull`; re-copy from
  `building-level/hvra/frontend/src/components/` if she changes them.
