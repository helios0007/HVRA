import asyncio
import base64
import json
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
    expose_headers=["X-Render-Source"],
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

    # Persist building location — needed later by /jobs/{id}/render to fetch
    # a Street View photo, since that endpoint is called independently of
    # this upload request (after the user clicks "Render" on a strategy card).
    with open(os.path.join(job_dir, "location.json"), "w", encoding="utf-8") as f:
        json.dump({"lat": lat, "lon": lon}, f)

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
        "cross_ventilation": result.get("cross_ventilation", {"spaces": []}),
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


@app.get("/jobs/{job_id}/cross_ventilation")
async def get_cross_ventilation(job_id: str):
    """Return cross_ventilation.json — the per-room ventilation diagnosis
    overlay (classification, exterior openings, airflow path, recommendations)."""
    import json
    path = os.path.join(UPLOADS_DIR, job_id, "cross_ventilation.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} cross_ventilation data not found.")
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
    path = os.path.join(os.path.dirname(__file__), "config", "strategy_library.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Strategy library not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Stage 5b — AI retrofit rendering ────────────────────────────────────────────

@app.get("/renderable_strategies")
async def get_renderable_strategies():
    """Strategy IDs eligible for AI rendering, and whether each needs an
    exterior or interior source photo — drives whether the frontend shows
    a 'Render' button on a given strategy card."""
    from analysis.render import RENDERABLE_STRATEGIES
    return {sid: {"view": v["view"]} for sid, v in RENDERABLE_STRATEGIES.items()}


@app.get("/jobs/{job_id}/street_view_preview")
async def street_view_preview(
    job_id: str,
    heading: float = 0.0,
    pitch: int = 0,
    fov: int = 80,
):
    """
    Live (uncached, no AI call) Street View frame for the given camera
    params — lets the user pan/tilt/zoom and see the result before
    committing to a paid AI render. Returns 404 if there's no Street View
    coverage at the building's location at all.
    """
    job_dir = os.path.join(UPLOADS_DIR, job_id)
    loc_path = os.path.join(job_dir, "location.json")
    if not os.path.exists(loc_path):
        raise HTTPException(status_code=404, detail=f"Job {job_id} location not found.")
    with open(loc_path, encoding="utf-8") as f:
        loc = json.load(f)

    from analysis.street_view import fetch_facade_photo
    fov = max(20, min(120, fov))
    pitch = max(-90, min(90, pitch))
    image = await fetch_facade_photo(loc["lat"], loc["lon"], heading, fov=fov, pitch=pitch)
    if image is None:
        raise HTTPException(status_code=404, detail="No Street View coverage at this location.")

    from fastapi.responses import Response
    return Response(content=image, media_type="image/jpeg")


@app.post("/jobs/{job_id}/render")
async def render_retrofit(
    job_id: str,
    room_id: str = Form(...),
    strategy_id: str = Form(...),
    orientation: str = Form(""),
    room_name: str = Form(""),
    custom_prompt: str = Form(""),
    heading: float | None = Form(None),
    pitch: int = Form(0),
    fov: int = Form(80),
    fallback_screenshot: UploadFile | None = File(None),
):
    """
    Generate (or return a cached) AI render showing strategy_id applied to
    room_id's facade/interior. Tries Street View first (exterior strategies
    only); falls back to fallback_screenshot (a viewport capture the
    frontend sends) if Street View has no coverage or the strategy needs an
    interior view.

    custom_prompt : optional user styling instructions (e.g. "darker wood
    tone, steeper angle") appended to the strategy's base prompt.

    Renders are cached on disk per (room_id, strategy_id, custom_prompt) —
    re-requesting the same combination returns the cached PNG instead of
    calling the paid Gemini API again. A different custom_prompt produces
    and caches a separate render rather than overwriting the default one.
    """
    from analysis.render import is_renderable, render_view_type, generate_retrofit_render

    if not is_renderable(strategy_id):
        raise HTTPException(
            status_code=400,
            detail=f"Strategy '{strategy_id}' is not eligible for AI rendering.",
        )

    job_dir = os.path.join(UPLOADS_DIR, job_id)
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    renders_dir = os.path.join(job_dir, "renders")
    os.makedirs(renders_dir, exist_ok=True)
    safe_room = "".join(c if c.isalnum() else "_" for c in room_id)

    # Custom prompts AND a non-default camera frame each get their own cache
    # slot so they never collide with — or overwrite — the default render.
    resolved_heading = heading if heading is not None else _orientation_to_heading(orientation)
    frame_variant = ""
    if heading is not None or pitch != 0 or fov != 80:
        frame_variant = f"__h{round(resolved_heading)}p{pitch}f{fov}"

    variant = frame_variant
    if custom_prompt.strip():
        import hashlib
        variant += "__" + hashlib.sha1(custom_prompt.strip().encode("utf-8")).hexdigest()[:10]

    cache_path = os.path.join(renders_dir, f"{safe_room}__{strategy_id}{variant}.png")
    source_path = os.path.join(renders_dir, f"{safe_room}__{strategy_id}{variant}__source.jpg")
    meta_path = os.path.join(renders_dir, f"{safe_room}__{strategy_id}{variant}__meta.json")

    if os.path.exists(cache_path) and os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return FileResponse(cache_path, media_type="image/png", headers={"X-Render-Source": meta["source"]})

    view_type = render_view_type(strategy_id)
    base_image: bytes | None = None
    source = "screenshot"

    if view_type == "exterior":
        loc_path = os.path.join(job_dir, "location.json")
        if os.path.exists(loc_path):
            with open(loc_path, encoding="utf-8") as f:
                loc = json.load(f)
            try:
                from analysis.street_view import fetch_facade_photo
                base_image = await fetch_facade_photo(
                    loc["lat"], loc["lon"], resolved_heading, pitch=pitch, fov=fov,
                )
                if base_image:
                    source = "street_view"
            except Exception as exc:
                logger.warning("Street View fetch error for job %s: %s", job_id, exc)

    if base_image is None:
        if fallback_screenshot is None:
            raise HTTPException(
                status_code=422,
                detail="No Street View coverage and no fallback screenshot provided. "
                       "Capture a viewport screenshot and resend with fallback_screenshot.",
            )
        base_image = await fallback_screenshot.read()

    try:
        result_png = await generate_retrofit_render(
            base_image, strategy_id, room_name=room_name, orientation=orientation,
            custom_prompt=custom_prompt,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Render generation failed for job %s room %s strategy %s",
                          job_id, room_id, strategy_id)
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc

    # Save the source photo too — so the user can self-check Street View
    # actually pointed at the right building/facade before trusting the render.
    with open(source_path, "wb") as f:
        f.write(base_image)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"source": source}, f)
    with open(cache_path, "wb") as f:
        f.write(result_png)
    logger.info("Job %s: rendered %s / %s via %s", job_id, room_id, strategy_id, source)

    return FileResponse(cache_path, media_type="image/png", headers={"X-Render-Source": source})


@app.get("/jobs/{job_id}/render_source")
async def get_render_source(
    job_id: str,
    room_id: str,
    strategy_id: str,
    custom_prompt: str = "",
    heading: float | None = None,
    pitch: int = 0,
    fov: int = 80,
    orientation: str = "",
):
    """Return the source photo (Street View or viewport screenshot) a
    cached render was generated from, so the user can verify Street View
    actually captured the correct building/facade."""
    job_dir = os.path.join(UPLOADS_DIR, job_id)
    safe_room = "".join(c if c.isalnum() else "_" for c in room_id)

    frame_variant = ""
    if heading is not None or pitch != 0 or fov != 80:
        resolved_heading = heading if heading is not None else _orientation_to_heading(orientation)
        frame_variant = f"__h{round(resolved_heading)}p{pitch}f{fov}"

    variant = frame_variant
    if custom_prompt.strip():
        import hashlib
        variant += "__" + hashlib.sha1(custom_prompt.strip().encode("utf-8")).hexdigest()[:10]

    source_path = os.path.join(job_dir, "renders", f"{safe_room}__{strategy_id}{variant}__source.jpg")
    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Source photo not found for this render.")
    return FileResponse(source_path, media_type="image/jpeg")


def _orientation_to_heading(orientation_label: str) -> float:
    """Compass label (N/NE/E/.../NW) → bearing degrees, for Street View heading."""
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    try:
        return labels.index(orientation_label.upper()) * 45.0
    except ValueError:
        return 180.0  # default: look south
