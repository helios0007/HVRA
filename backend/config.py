import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly load from backend/.env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=str(env_path), override=True)

class Config:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/urban_tool"
    )

    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "")

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
    ZONES_DIR = os.getenv("ZONES_DIR", "./data/zones")

    DEFAULT_CRS = os.getenv("DEFAULT_CRS", "EPSG:4326")

    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 8000))
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
os.makedirs(Config.ZONES_DIR, exist_ok=True)
