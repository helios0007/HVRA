# Launches the full integrated tool in three terminals:
#   1. Urban backend    (this repo)        -> http://localhost:8000
#   2. Building backend  (vendored teammate) -> http://localhost:8001
#   3. Frontend (single UI)                 -> http://localhost:5173
#
# Run from the repo root:  ./start-all.ps1
# One-time setup for the building backend (separate venv + deps + key):
#   cd building-level/hvra/backend
#   python -m venv .venv
#   .\.venv\Scripts\pip install -r requirements.txt
#   set ANTHROPIC_API_KEY in building-level/hvra/backend/.env

$root = $PSScriptRoot

Write-Host "Starting urban backend on :8000 ..."
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; python app.py"

Write-Host "Starting building backend on :8001 ..."
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\building-level\hvra\backend'; if (Test-Path .\.venv\Scripts\uvicorn.exe) { .\.venv\Scripts\uvicorn main:app --port 8001 } else { uvicorn main:app --port 8001 }"

Write-Host "Starting frontend on :5173 ..."
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm run dev"

Write-Host "All three launched. Open http://localhost:5173"
