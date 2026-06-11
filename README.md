# HVRA — Heat Vulnerability Risk Analyzer

Urban heat **triage** tool: draw a zone on the map and get a building-level
**Heat Vulnerability Index (HVI)** computed from live data sources, visualized as
color-coded 3D buildings, a 2D map, and a street-level thermal heatmap — then test
evidence-based interventions and get a **decision-gate verdict** on whether
building-level retrofit work is needed at all.

**Demo city: Barcelona.** The methodology is globally applicable — every data input
sits behind a swappable loader (`backend/services/data_loaders/`), so adapting to
another city means replacing the cadastre, census, and income loaders with local
equivalents (or synthetic/surrogate defaults for data-sparse cities). The satellite
inputs (Landsat LST, Sentinel-2 NDVI) and the OSM morphology are already global.

## Composite score formula

```
HVI = 0.15·age + 0.10·roof + 0.05·canyon + 0.05·green          (Building exposure · 35%)
    + 0.15·elderly + 0.10·income⁻¹ + 0.07·isolation
    + 0.05·no_AC + 0.03·disability                              (Social vulnerability · 40%)
    + 0.15·LST + 0.05·UHI + 0.05·NDVI⁻¹                         (Thermal context · 25%)
```

All 12 factors are normalized 0–1; the HVI is reported on a 0–10 scale per building
(**index points, not °C**). Index structure follows the exposure–sensitivity–adaptive-capacity
framework of [Reid et al. 2009](https://doi.org/10.1289/ehp.0900683).

### Risk thresholds & decision gate

| HVI | Tier | Action |
|---|---|---|
| 0.0–4.0 | Low | No intervention needed |
| 4.0–5.5 | Moderate | Street-level measures recommended |
| 5.5–7.0 | High | Priority zone — urban + building measures |
| 7.0–10 | Critical | Immediate action — full retrofit pathway |

The Interventions tab applies urban-scale measures first and then issues a verdict:
if the zone drops below **4.0**, no building-level work is needed; if it stays at or
above **5.5**, the affected buildings escalate to building-level analysis (Layer 1).
"Vulnerable time" = share of simulated hours with UTCI > 32 °C (strong heat stress,
ISB UTCI scale), July, 10:00–18:00, static envelope simulation (not time-stepped).

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
