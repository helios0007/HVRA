# How to run HVRA

## Requirements
- Anaconda Python 3.13 (venv already created at `backend/.venv`)
- Node.js + npm (frontend dependencies already installed)
- Anthropic API key (already saved in `backend/.env`)
- Google Maps API key (already saved in `frontend/.env`)

---

## Every time you want to run the tool

Open **two CMD terminals**.

---

### Terminal 1 — Backend

```
cd "e:\Documents (E)\IAAC-Spain\1_YEAR 2025-2026\Semester_03\RESEARCH STUDIO\HVRA\hvra\backend"
.venv\Scripts\uvicorn main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### Terminal 2 — Frontend

```
cd "e:\Documents (E)\IAAC-Spain\1_YEAR 2025-2026\Semester_03\RESEARCH STUDIO\HVRA\hvra\frontend"
npm run dev
```

You should see:
```
VITE v6.x  ready in xxx ms
➜  Local: http://localhost:3000/
```

---

## Open the tool

Go to **http://localhost:3000** in your browser.

---

## Submitting a building

1. Click on the map to place a pin on your building
2. Upload an IFC file (must have IfcSpaces — export from Revit with "Export rooms and spaces" checked)
3. Fill in all dropdowns (building data + occupant profile)
4. Click **Submit building**
5. Wait 2–5 minutes for the pipeline to complete (solar calculations + LLM diagnosis)

---

## Switching LLM (Claude API ↔ free local model)

The diagnosis + retrofit shortlist (Stages 3/4b) can run on either:

| Provider | Cost | Quality | Setup |
|---|---|---|---|
| `anthropic` (default) | uses API credits | best | ANTHROPIC_API_KEY in `.env` |
| `ollama` | free, local | okay for testing | install https://ollama.com then `ollama pull llama3.1:8b` |

**To switch:** edit `backend/.env` and uncomment/comment this line, then restart uvicorn:

```
LLM_PROVIDER=ollama
```

Line commented out (`#LLM_PROVIDER=ollama`) → uses Claude API.
Line active → uses the local Ollama model (Claude key not needed, no credits used).

All scores, risk levels and eligibility filtering are computed in Python and are
identical regardless of the LLM — only the written diagnosis and the top-3
ranking/justifications come from the model.

---

## Notes

- The Anthropic API key is stored in `backend/.env` — no need to set it manually
- The Google Maps API key is stored in `frontend/.env` — no need to set it manually
- Analysis results are saved in `backend/uploads/<job-id>/`
- To stop either server: **Ctrl+C** in its terminal
