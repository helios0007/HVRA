from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import logging

from config import Config
from api.routes import urban, ifc, strategies, zones, interventions, hvi
from services.infrared_client import get_infrared_client, close_infrared_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize Infrared client
    await get_infrared_client()
    yield
    # Shutdown: cleanup
    close_infrared_client()

app = FastAPI(
    title="Urban Design Intervention Tool",
    version="0.1.0",
    description="Urban vulnerability analysis + design suggestion engine",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(urban.router, prefix="/api/urban", tags=["urban"])
app.include_router(ifc.router, prefix="/api/ifc", tags=["ifc"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(zones.router, prefix="/api/zones", tags=["zones"])
app.include_router(interventions.router)
app.include_router(hvi.router, prefix="/api/hvi", tags=["hvi"])

# Serve uploaded files
if os.path.exists(Config.UPLOAD_DIR):
    app.mount("/data/uploads", StaticFiles(directory=Config.UPLOAD_DIR), name="uploads")

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=False
    )
