import asyncio
import logging
import os
import shutil
import uuid

from dotenv import load_dotenv
load_dotenv()  # loads .env from the backend directory

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HVRA — Heat Vulnerability Retrofit Assistant", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "HVRA backend", "version": "0.3.0"}


@app.post("/upload")
async def upload_building(
    ifc_file: UploadFile = File(...),
    lat: float = Form(...),
    lon: float = Form(...),
    construction_year: str = Form(...),
    roof_colour: str = Form(...),
    heritage_protection: str = Form(...),
    shutter_boxes: str = Form(...),
    oldest_resident_age: str = Form(...),
    ac_access: str = Form(...),
    income_category: str = Form(...),
    mobility_limitations: str = Form(...),
    # [urban-grounding] optional UHI delta (°C) measured by the urban tool for
    # this zone. When provided it overrides the barri-table lookup so building
    # thermal scores use our actual analysis. Absent → her standalone behaviour.
    urban_uhi_delta: float | None = Form(None),
):
    if not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(
            status_code=400,
            detail="File must be a .ifc file. Export from Revit / ArchiCAD as IFC 2x3.",
        )

    # ── Create job directory ────────────────────────────────────────────────
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(UPLOADS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    ifc_path = os.path.join(job_dir, "input.ifc")
    with open(ifc_path, "wb") as buf:
        shutil.copyfileobj(ifc_file.file, buf)

    logger.info("Job %s: saved IFC → %s", job_id, ifc_path)

    # ── Coerce form string booleans ─────────────────────────────────────────
    heritage_bool = heritage_protection.lower() == "yes"
    shutter_bool  = shutter_boxes.lower() == "yes"
    ac_bool       = ac_access.lower() == "yes"
    mobility_bool = mobility_limitations.lower() == "yes"

    try:
        from analysis.pipeline import run_pipeline

        # Run sync pipeline (Stages 2 + 4a) in a thread pool so it does not
        # block the FastAPI event loop during I/O-heavy osmnx / ifcopenshell work.
        result = await asyncio.to_thread(
            run_pipeline,
            ifc_path=ifc_path,
            lat=lat,
            lon=lon,
            construction_year=construction_year,
            roof_colour=roof_colour,
            heritage_protection=heritage_bool,
            shutter_boxes=shutter_bool,
            oldest_resident_age=oldest_resident_age,
            ac_access=ac_bool,
            income_category=income_category,
            mobility_limitations=mobility_bool,
            output_dir=job_dir,
            urban_uhi_delta=urban_uhi_delta,  # [urban-grounding]
        )

        # Run async LLM stages (Stage 3 + 4b) directly in the async context.
        # Provider: LLM_PROVIDER=anthropic (default) or ollama (local, no key).
        from analysis.llm import llm_provider
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        use_llm = llm_provider() == "ollama" or bool(api_key)
        if use_llm and result.get("rooms"):
            from analysis.llm import run_llm_stages
            from analysis.prefilter import load_strategy_library
            strategy_library = load_strategy_library()
            result = await run_llm_stages(result, job_dir, api_key, strategy_library)
        elif not use_llm:
            result.setdefault("warnings", []).append(
                "No LLM configured — Stage 3 (diagnosis) and Stage 4b (shortlist) skipped. "
                "Set ANTHROPIC_API_KEY, or LLM_PROVIDER=ollama for a local model."
            )

    except ImportError as exc:
        logger.warning("Analysis dependencies not installed: %s", exc)
        result = {
            "rooms": [],
            "files": {},
            "epw_synthetic": False,
            "warnings": [
                f"Analysis dependencies not installed ({exc}). "
                "Run: pip install -r requirements.txt"
            ],
        }
    except Exception as exc:
        logger.exception("Pipeline error for job %s", job_id)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    return {
        "success": True,
        "job_id": job_id,
        "filename": ifc_file.filename,
        "room_count": len(result["rooms"]),
        "epw_synthetic": result.get("epw_synthetic", False),
        "neighbourhood": result.get("neighbourhood", "unknown"),
        "uhi_delta": result.get("uhi_delta", 1.5),
        "epw_night_min": result.get("epw_night_min", 20.0),
        "warnings": result.get("warnings", []),
        "rooms": result["rooms"],
        "roof_element_ids": result.get("roof_element_ids", []),
        "prevailing_wind_deg": result.get("prevailing_wind_deg"),
        "files": result.get("files", {}),
        "inputs": {
            "location": {"lat": lat, "lon": lon},
            "construction_year": construction_year,
            "roof_colour": roof_colour,
            "heritage_protection": heritage_protection,
            "shutter_boxes": shutter_boxes,
            "oldest_resident_age": oldest_resident_age,
            "ac_access": ac_access,
            "income_category": income_category,
            "mobility_limitations": mobility_limitations,
            "urban_uhi_delta": urban_uhi_delta,  # [urban-grounding] echo for transparency
        },
    }


# ── Job result endpoints ────────────────────────────────────────────────────────

@app.get("/jobs/{job_id}/room_problems")
async def get_room_problems(job_id: str):
    """Return room_problems.json for a completed job (includes Stage 3 diagnosis)."""
    import json
    path = os.path.join(UPLOADS_DIR, job_id, "room_problems.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or not yet complete.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/jobs/{job_id}/priority")
async def get_priority(job_id: str):
    """Return priority.json (rooms ranked by composite_score descending)."""
    import json
    path = os.path.join(UPLOADS_DIR, job_id, "priority.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/jobs/{job_id}/eligible_strategies")
async def get_eligible_strategies(job_id: str):
    """Return eligible_strategies.json (Stage 4a pre-filter output) per room."""
    import json
    path = os.path.join(UPLOADS_DIR, job_id, "eligible_strategies.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} eligible_strategies not found. "
                   "Ensure the pipeline completed successfully.",
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/jobs/{job_id}/shortlist")
async def get_shortlist(job_id: str):
    """Return shortlist.json (Stage 4b top-3 retrofit strategies per room)."""
    import json
    path = os.path.join(UPLOADS_DIR, job_id, "shortlist.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} shortlist not found. "
                   "Ensure ANTHROPIC_API_KEY is set and the pipeline completed successfully.",
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/jobs/{job_id}/ifc")
async def get_ifc(job_id: str):
    """Serve the original input IFC file for the before-state 3D viewer."""
    path = os.path.join(UPLOADS_DIR, job_id, "input.ifc")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} IFC not found.")
    return FileResponse(path, media_type="application/octet-stream", filename="model.ifc")


@app.get("/jobs/{job_id}/ifc_after")
async def get_ifc_after(job_id: str):
    """
    Serve a modified IFC with Category A retrofit geometry added (after-state viewer).
    Generates and caches after.ifc on first request.
    """
    import json

    job_dir = os.path.join(UPLOADS_DIR, job_id)
    ifc_path = os.path.join(job_dir, "input.ifc")
    after_path = os.path.join(job_dir, "after.ifc")
    shortlist_path = os.path.join(job_dir, "shortlist.json")

    if not os.path.exists(ifc_path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} IFC not found.")

    if not os.path.exists(after_path):
        shortlist: list = []
        if os.path.exists(shortlist_path):
            with open(shortlist_path, encoding="utf-8") as f:
                shortlist = json.load(f)
        try:
            from analysis.retrofit_geometry import generate_after_model
            await asyncio.to_thread(generate_after_model, ifc_path, shortlist, after_path)
        except Exception as exc:
            logger.warning("ifc_after generation failed for job %s: %s — serving original", job_id, exc)
            return FileResponse(ifc_path, media_type="application/octet-stream", filename="after.ifc")

    return FileResponse(after_path, media_type="application/octet-stream", filename="after.ifc")


@app.get("/strategy_library")
async def get_strategy_library():
    """Return the static strategy library (all 19 strategies with full metadata)."""
    import json
    path = os.path.join(os.path.dirname(__file__), "config", "strategy_library.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Strategy library not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
