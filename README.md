# HVRA — Heat Vulnerability Risk Analyzer

Urban heat vulnerability analysis tool for Barcelona. Draw a zone on the map and get a
building-level **Heat Vulnerability Index (HVI)** computed from live data sources,
visualized as color-coded 3D buildings, a 2D map, and a street-level thermal heatmap.

## Composite score formula

```
HVI = 0.15·age + 0.10·roof + 0.05·canyon + 0.05·green          (Building exposure · 35%)
    + 0.15·elderly + 0.10·income⁻¹ + 0.07·isolation
    + 0.05·no_AC + 0.03·disability                              (Social vulnerability · 40%)
    + 0.15·LST + 0.05·UHI + 0.05·NDVI⁻¹                         (Thermal context · 25%)
```

All 12 factors are normalized 0–1; the HVI is reported on a 0–10 scale per building.

## Data sources (all live)

| Factor | Source |
|---|---|
| Building footprints & 3D meshes | Infrared SDK (api.infrared.city) |
| UTCI thermal comfort simulation | Infrared SDK (requires simulation credits) |
| Construction year per building | Catastro INSPIRE WFS (official Spanish cadastre) |
| Roof type, green space, streets | OpenStreetMap (Overpass / osmnx) |
| % population 65+ (census-section level) | Idescat Taules v2 API |
| Income per census section (2022) | Barcelona Open Data income atlas |
| Households by size / cooling system (Census 2021) | Idescat |
| Land surface temperature + UHI delta | Landsat 8/9 C2 L2 via Microsoft Planetary Computer |
| NDVI vegetation index | Sentinel-2 L2A via AWS Earth Search |
| Census section boundaries | Barcelona Open Data (1,068 polygons, WGS84) |

If the Infrared thermal simulation is unavailable (quota), the analysis automatically
falls back to real Landsat surface temperature so results still complete.

## Setup

### Backend (FastAPI, Python 3.12+)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # fill in INFRARED_API_KEY and MAPBOX_TOKEN
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
cp .env.example .env          # fill in VITE_MAPBOX_TOKEN
npm run dev                   # http://localhost:5173
```

## Usage

1. **Draw & Analyze** — outline a study area with the polygon tool; analysis starts automatically.
2. **3D Explore** — buildings colored by HVI on a dark basemap. Hover for a readout, click for the full 12-factor breakdown. Sliders for height scale, opacity, and HVI filtering.
3. **HVI Map** — 2D footprint map with the same color scale; click a building for details.
4. **Heatmap & Drivers** — street-level UTCI heatmap, climate context metrics, and the vulnerability drivers with recommended interventions.
