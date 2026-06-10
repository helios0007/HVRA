from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
import os
from config import Config
from services.ifc_processor import process_ifc_file

router = APIRouter()

@router.post("/upload")
async def upload_ifc(
    file: UploadFile = File(...),
    latitude: float = Form(default=None),
    longitude: float = Form(default=None)
):
    """
    Upload and parse IFC file.
    Optionally accepts latitude and longitude to override building location.
    """
    file_path = os.path.join(Config.UPLOAD_DIR, file.filename)
    with open(file_path, 'wb') as f:
        f.write(await file.read())

    result = process_ifc_file(file_path, latitude=latitude, longitude=longitude)

    return {
        "file_id": file.filename,
        "url": f"/data/uploads/{file.filename}",
        "units": result.get("units", []),
        "origin": result.get("origin", None),
        "bounds": result.get("bounds", None),
        "building_geojson": result.get("building_geojson", None),
    }

@router.get("/files")
async def list_ifc_files():
    """List uploaded IFC files."""
    files = []
    if os.path.exists(Config.UPLOAD_DIR):
        files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.endswith('.ifc')]
    return {"files": files}
