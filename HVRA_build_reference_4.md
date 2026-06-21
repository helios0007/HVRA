# HVRA — Heat Vulnerability Retrofit Assistant
## Technical Build Reference
*Generated from design sessions — May 2026*

---

## 1. Project Aim

**Total aim:** Build a SaaS web platform that reads a building's IFC model, computes room-level heat vulnerability using physiologically grounded metrics, and uses an LLM to generate a plain-language diagnosis and ranked retrofit shortlist — enabling municipalities, housing operators, and architects to make evidence-based retrofit decisions under limited public budgets.

**Site context:** Barcelona. 28% of housing stock is highly vulnerable to extreme heat (UPC 2025). 591,211 homes lack sufficient cross-ventilation. High-risk areas: Barceloneta, parts of Gràcia, Left Eixample.

**Target users:**
- Municipalities and housing operators (primary — portfolio-level prioritization)
- Architects and designers (secondary — building-level intervention)

**Key metric:** Reduce peak indoor operative temperature by 3–5°C during summer heatwave conditions compared to the unretrofitted baseline.

**What this tool is not:** It is not an energy compliance tool. It is not a comfort optimizer. It is a health-risk reduction and retrofit prioritization tool grounded in excess-mortality evidence.

---

## 2. System Pipeline

The pipeline has five stages. Stages 1–2 are deterministic (no LLM). Stages 3–4 use the LLM. Stage 5 is the visualization interface.

```
INPUTS → CALCULATION ENGINE → AI DIAGNOSIS → AI SHORTLIST → VISUALIZATION
```

### Named output files

| File | Produced by | Level | Consumed by |
|---|---|---|---|
| `room_problems.json` | Stage 2 (then updated by Stage 3) | Per room | Stage 3, Stage 4a, Stage 5 |
| `priority.json` | Stage 2b — Python sort, no LLM | Per room, ranked | Stage 5 portfolio view only |
| `strategy_library.json` | Static — authored once, never generated | Global | Stage 4a |
| `eligible_strategies.json` | Stage 4a pre-filter | Per room | Stage 4b |
| `shortlist.json` | Stage 4b retrofit recommender | Per room | Stage 5 |

### File flow in order

```
Stage 2   → room_problems.json         (scores, flags, composite_score per room)
Stage 2b  → priority.json              (rooms ranked by composite_score, Python sort only)
Stage 3   → room_problems.json         (+ diagnosis and key_factors added)
Stage 4a  → eligible_strategies.json   (pre-filter output per room)
Stage 4b  → shortlist.json             (top 3 strategies per room)

Stage 5 reads:
  room_problems.json  → 3D color overlay + side panel diagnosis + scores
  priority.json       → portfolio ranked list view
  shortlist.json      → retrofit cards in side panel
```

**`priority.json`** is produced immediately after Stage 2 by a simple Python sort of all rooms by `composite_score` descending. It is a ranked list of rooms from most to least thermally affected. It has no knowledge of the shortlist and does not feed into Stages 3 or 4. It is an extra visualization parameter only — it drives the portfolio list view so a municipality can see which rooms need intervention most urgently.

**`shortlist.json`** has no knowledge of priority. It gives each room its top 3 applicable strategies independently of how that room ranks against others.

**`room_problems.json`** is updated in place. Stage 2 creates it with computed scores and flags. Stage 3 adds `diagnosis` and `key_factors` text fields to the same file. It is one file that grows as it passes through the pipeline.

---

### Stage 1 — Inputs

The tool is designed to work in any city. Barcelona is the proof of concept. All city-specific data sits in swappable config files — the pipeline logic never changes.

---

#### What the user provides — 8 inputs only

| Field | Type | What it drives |
|---|---|---|
| Building location | Google Maps picker → exact lat/lon | Sun position, shadow analysis, UHI lookup, surrounding buildings clip |
| IFC model | File upload (.ifc export from Revit, ArchiCAD, Rhino) | All geometry, room boundaries, wall orientations, windows, floor levels |
| Construction year | Dropdown (pre-1960 / 1960–79 / 1980–2006 / post-2006) | U-value lookup table per wall and roof |
| Roof colour / material | Dropdown (dark tile / terracotta / light tile / metal / reflective) | Roof solar absorption (albedo), used in the sol-air roof solar gain calculation (envelope.py) |
| Heritage protection zone | Yes / No | Routes insulation recommendation: ETICS (external) vs internal wall insulation |
| Existing window shutter boxes | Yes / No | If yes, external shutters rank above louvers in shading shortlist |
| Age of oldest resident | Dropdown (under 65 / 65–75 / 75+) | vuln_multiplier |
| AC access | Yes / No | vuln_multiplier |
| Income category | Low / Medium / High | vuln_multiplier |
| Mobility limitations | Yes / No | vuln_multiplier |

**Building location** is selected by clicking directly on the building on a Google Maps tile embedded in the form. This gives the exact lat/lon of the building — not a neighbourhood centroid. The user never types an address.

```javascript
map.addListener("click", (event) => {
  selectedLatLon = {
    lat: event.latLng.lat(),
    lng: event.latLng.lng(),
  };
});
```

**IFC model** is exported from Revit, ArchiCAD, or Rhino as a `.ifc` file. Never accept `.rvt` directly. In Revit: File → Export → IFC → select IFC 2x3 Coordination View → ensure "Export rooms and spaces" is checked (off by default in some versions). The IFC must contain: `IfcSpace` (rooms), `IfcWall` (walls with placement matrices), `IfcWindow` (hosted on walls), `IfcBuildingStorey` (floor levels).

---

#### What the code derives automatically — user provides nothing

| Derived data | How derived |
|---|---|
| Wall orientation (compass bearing) | Extracted from IFC wall placement matrix by `ifcopenshell` |
| Window area and WWR | Extracted from IFC `IfcWindow` elements |
| Room boundaries and adjacency | Extracted from IFC `IfcSpace` elements |
| Floor level per room | Extracted from IFC `IfcBuildingStorey` |
| Self-shading geometry (balconies, overhangs) | Extracted from IFC geometry |
| Sun position per hour | `pvlib` computes from lat/lon + July 15–21 dates |
| Surrounding buildings footprints and heights | `osmnx` queries OpenStreetMap within 100m radius of lat/lon |
| Shadow factor per façade per hour | Computed from sun position + surrounding buildings using `shapely` geometry |
| Neighbourhood | Spatial lookup from lat/lon against neighbourhood polygons GeoJSON |
| UHI temperature correction | Looked up from neighbourhood → UHI delta table |
| U-value per wall | From IFC material layers if present; otherwise era lookup table |
| SHGC per window | From glazing era lookup table |
| EPW climate data | Static file pre-loaded for Barcelona; July 15–21 hours extracted |

**Wall orientation** is never asked of the user — it is read directly from the IFC wall placement matrix:

```python
import ifcopenshell.util.placement
import numpy as np

for wall in ifc.by_type("IfcWall"):
    matrix = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
    normal = np.array([-matrix[1][0], -matrix[1][1]])
    angle = np.degrees(np.arctan2(normal[0], normal[1])) % 360
    # angle = compass bearing of wall outward face in degrees
```

**Surrounding buildings** are fetched live from OpenStreetMap using `osmnx`:

```python
import osmnx as ox
buildings = ox.features_from_point(
    (lat, lon),
    tags={"building": True},
    dist=100
)
```

**Shadow factor per façade per hour** is computed using `pvlib` for sun position and `shapely` for shadow polygon geometry — no Ladybug, no Rhino, no simulation engine. Pure Python, runs in seconds:

```python
import pvlib
location = pvlib.location.Location(latitude=lat, longitude=lon)
solar_position = location.get_solarposition(times=heatwave_hours)
# For each hour: compute shadow polygon from surrounding buildings
# Check if shadow polygon intersects façade position
# shadow_factor = 0 if shaded, 1 if exposed
# I_effective = I_direct × shadow_factor + I_diffuse
```

---

#### City-agnostic config structure

All Barcelona-specific data lives in swappable config files. To add a new city, add a new folder — the pipeline code does not change:

```
config/
  barcelona/
    epw.epw                  ← Climate.OneBuilding: Barcelona El Prat
    buildings.geojson        ← Barcelona Open Data (or OSM fallback)
    neighbourhoods.geojson   ← Barcelona Open Data
    uhi_deltas.json          ← UPC 2025 study + Copernicus dataset
    u_value_defaults.json    ← CTE DB-HE (Spanish building code)
  london/                    ← future expansion
    epw.epw
    ...
```

**EPW source:** climate.onebuilding.org — free, covers 4000+ locations worldwide. Barcelona file: `ESP_CT_Barcelona.081810_TMYx.epw`. Extract July 15–21 (hours 4513–4680) for the heatwave design week using the `ladybug` EPW reader or direct CSV parsing.

**UHI delta table for Barcelona (from UPC 2025 study + Copernicus Urban Heat Island dataset):**

```python
UHI_DELTA = {
    "Barceloneta":           1.5,
    "Eixample Esquerra":     2.5,
    "Eixample Dreta":        2.5,
    "Gràcia":                2.0,
    "El Clot":               1.5,
    "Sarrià-Sant Gervasi":   0.5,
    "Poblenou":              1.0,
}
# Applied as: T_outdoor_adjusted = T_epw + UHI_DELTA[neighbourhood]
```

**U-value defaults by construction era (CTE DB-HE + IVE typology database):**

| Era | Wall U-value (W/m²K) | Roof U-value (W/m²K) |
|---|---|---|
| Pre-1960 | 2.0–2.5 | 2.5–3.0 |
| 1960–1979 | 1.5–2.0 | 2.0–2.5 |
| 1980–2006 | 0.8–1.5 | 1.0–1.5 |
| Post-2006 | 0.4–0.8 | 0.4–0.6 |

**IFC fallback:** If no BIM model exists, accept a structured data form where the operator manually inputs room dimensions, façade orientations, window areas, wall construction era, and floor level. Lower fidelity but still produces a defensible risk ranking for the prioritization use case.

---

### Stage 2 — Calculation Engine (Python, deterministic, no LLM)

This stage translates raw geometry and climate data into structured, semantically meaningful facts per room. The LLM never touches geometry — it only reads the JSON this stage produces.

**Library:** `ifcopenshell` for IFC parsing.

---

#### 2a. Solar Gain per Façade

**What it does:** Estimates how much solar radiation enters each room through its windows during the heatwave week.

**Formula:**
```
Solar_gain (W) = I_solar × A_window × SHGC × (1 − shading_factor)
```

| Variable | Definition | Source |
|---|---|---|
| `I_solar` | Effective solar irradiance on façade (W/m²) = `I_direct × shadow_factor + I_diffuse` per hour, summed over heatwave week | EPW file + pvlib sun position + shapely shadow geometry |
| `A_window` | Window area (m²) | IFC IfcWindow element |
| `SHGC` | Solar Heat Gain Coefficient — default 0.6 single glazing, 0.35 double glazing | ASHRAE Fundamentals Ch.18 |
| `shading_factor` | External shading element check from IFC (louvers, overhangs) — separate from shadow_factor which is obstruction-based | IFC element check |

**WWR (Window-to-Wall Ratio):**
```
WWR = A_window / A_wall
```
Pure geometry from IFC. No reference needed.

**Solar gain score (0–1):**
```
solar_gain_score = min(Solar_gain / 600, 1.0)
```
600 W is the fixed critical upper bound. Capped at 1.0.

**SHGC defaults by glazing era (if not in IFC materials):**

| Era | Glazing type | SHGC default |
|---|---|---|
| Pre-1980 | Single glazing | 0.6 |
| 1980–2006 | Basic double glazing | 0.45 |
| Post-2006 | Low-e double glazing | 0.35 |

**Reference:** ASHRAE Fundamentals Handbook, Chapter 18 (Nonresidential Cooling and Heating Load Calculations).

---

#### 2b. Ventilation Analysis

**What it does:** Determines whether a room can achieve cross-ventilation and estimates its air change rate.

**Cross-ventilation logic (rule-based, no formula):**
1. Count exterior façades per room from IFC wall adjacency data
2. If only one exterior façade → `cross_ventilation_direct = false`
3. If two or more exterior façades → check orientation difference:
   - If angle between them ≥ 45° → `cross_ventilation_direct = true`
   - If angle < 45° (near-parallel walls) → `cross_ventilation_direct = false`
4. Check for interior door to adjacent room with a different exterior façade → `secondary_path_possible = true`

**ACH proxy values (not CFD — add `# PROXY` comment in code):**

| Condition | Estimated ACH |
|---|---|
| Single exterior façade, openable window | 0.4 |
| Two non-parallel exterior façades, openable windows | 1.5–2.5 |
| No openable windows | 0.1 (infiltration only) |

**Ventilation deficit score (0–1):**
```
vent_deficit_score = min(1 − (ACH_estimated / ACH_target), 1.0)
```
Where `ACH_target = 4.0` (minimum adequate natural ventilation for thermal comfort).

**Reference:** EN 15242 (Ventilation for buildings — Calculation methods for air flow rates). ACH target from EN 15251 / ASHRAE 62.1 natural ventilation guidance for Mediterranean residential buildings.

---

#### 2c. Envelope Thermal Performance

**What it does:** Flags walls and roofs with poor thermal resistance that allow heat to conduct in.

**U-value lookup table by construction era** (use when IFC material layers are absent):

| Era | Wall U-value (W/m²K) | Roof U-value (W/m²K) |
|---|---|---|
| Pre-1960 | 2.0–2.5 | 2.5–3.0 |
| 1960–1979 | 1.5–2.0 | 2.0–2.5 |
| 1980–2006 | 0.8–1.5 | 1.0–1.5 |
| Post-2006 | 0.4–0.8 | 0.4–0.6 |

**Reference:** Spanish Technical Building Code (CTE DB-HE) historical compliance requirements, cross-referenced with IVE (Institut Valencià de l'Edificació) Mediterranean residential typology database.

**Flagging thresholds:**

| Condition | Flag |
|---|---|
| Wall U-value > 1.2 W/m²K on exterior façade | Flag for wall insulation intervention |
| Roof U-value > 1.5 W/m²K on top floor | Flag for roof insulation intervention |

**Reference for thresholds:** CTE DB-HE 2022 renovation requirements for existing buildings in climate zone B3 (Barcelona).

**Roof colour / material → solar absorption (albedo):**

| Roof colour option (form) | Material reference | Albedo range | Absorption used (1 − midpoint albedo) |
|---|---|---|---|
| Dark tile / dark asphalt | Dark Concrete Tiles / Aged Dark Asphalt | 0.04–0.35 | 0.850 |
| Red / terracotta tile | Red / Terracotta Clay Tiles | 0.25–0.35 | 0.700 |
| Light grey / cream tile | Light Grey / Cream Tiles | 0.40–0.55 | 0.525 |
| Metal (unpainted / galvanized) | Unpainted Corrugated Steel | 0.30–0.50 | 0.600 |
| White / reflective coating | White Concrete Tiles / Elastomeric White Paint | 0.70–0.85 | 0.225 |

**Reference:** Lawrence Berkeley National Laboratory (LBNL) Heat Island Group Pigment Database; Cool Roof Rating Council (CRRC) product rating database; US EPA Heat Island Reduction Program technical profiles; ASTM E1980 (Solar Reflectance Index calculation). Each absorption value is the midpoint of the cited albedo range (1 − albedo_mid).

**Roof solar gain — sol-air method (top-floor / roof-exposed rooms only):**

```
T_sol-air = T_outdoor + (roof_absorption × GHI) / h_o
Q_roof    = U_roof × A_roof × (T_sol-air − T_outdoor)
          = U_roof × A_roof × roof_absorption × GHI / h_o
```

- `GHI` = global horizontal irradiance (W/m²), taken directly from the EPW hourly record (roof treated as horizontal — no tilt transform needed)
- `h_o` = external surface film coefficient = 19 W/m²K (ASHRAE Fundamentals Handbook Ch.18, typical value for an exterior surface at light-to-moderate wind, ≈7.5 mph)
- `A_roof` ≈ room floor area (flat-roof assumption: the roof above a top-floor room is approximately the same area as the room below it)
- Peak hourly gain across the EPW heatwave week is normalised **per m² of roof** against 200 W/m² (the per-m² equivalent of the 600 W / ~3 m² window-gain reference used for facades in Stage 2a) to produce `roof_solar_gain_score` (0–1)
- The room's roof penalty in `envelope_score` is `max(roof_U_value_penalty, roof_solar_gain_score)` — so a poorly-insulated OR a dark/absorptive roof can each independently drive the envelope penalty up; a top-floor room is only protected from the roof penalty if both U-value and colour are favourable

**Reference:** ASHRAE Fundamentals Handbook Ch.18 — Sol-Air Temperature method (standard simplified method for converting absorbed solar radiation into an equivalent conduction-driving temperature for opaque surfaces, avoiding full transient heat-conduction simulation).

---

#### 2d. Health KPIs and Overheating Score

This is the core health methodology. Four KPIs are computed per room and combined into a composite score.

---

**KPI 1 — Operative Temperature (T_op)**

```
T_op = (T_air + T_mrt) / 2
```

Valid for indoor spaces with air velocity < 0.2 m/s (still air — correct assumption for indoor heatwave conditions).

- `T_air` = estimated indoor air temperature (from EPW outdoor temp + solar gain adjustment + ventilation rate)
- `T_mrt` = Mean Radiant Temperature. MVP approximation:
  - Low solar exposure (solar_gain_score < 0.4): `T_mrt = T_air + 2°C`
  - High solar exposure (solar_gain_score ≥ 0.4): `T_mrt = T_air + 4°C`

**Threshold:** T_op > 32°C → elderly thermoregulation loss begins.

**Reference:** EN ISO 7726 (Ergonomics of the thermal environment — Instruments for measuring physical quantities). ASHRAE 55-2020, Section 5.3. Elderly threshold: WHO (2011), *Heat and Health* technical report.

---

**KPI 2 — WBGT (Wet Bulb Globe Temperature)**

Indoor formula (no solar radiation term — correct for indoor use):
```
WBGT_indoor = 0.7 × T_wb + 0.3 × T_air
```

Wet bulb temperature `T_wb` derived from EPW dry bulb (`T_air`) and relative humidity (`RH`) using the Stull (2011) formula:

```
T_wb = T_air × arctan(0.151977 × (RH + 8.313659)^0.5)
     + arctan(T_air + RH)
     − arctan(RH − 1.676331)
     + 0.00391838 × RH^1.5 × arctan(0.023101 × RH)
     − 4.686035
```

Accuracy: ±0.65°C across Barcelona heatwave temperature and humidity ranges.

**Thresholds:**

| WBGT | Meaning |
|---|---|
| > 28°C | Physiological strain in healthy adults |
| > 32°C | Serious risk for elderly occupants |

**References:**
- Stull, R. (2011). *Wet-Bulb Temperature from Relative Humidity and Air Temperature*. Journal of Applied Meteorology and Climatology, 50(11), 2267–2269.
- ISO 7243:2017 (Ergonomics of the thermal environment — Assessment of heat stress using the WBGT index).

---

**KPI 3 — Nocturnal Recovery Temperature**

No formula — threshold-based flag:
```
IF estimated_indoor_temp_at_3am > 26°C → nocturnal_recovery_fail = true
```

Estimated 3am indoor temperature = EPW minimum overnight temperature + delta based on thermal mass score:
- High thermal mass (score > 0.6): add 1°C
- Low thermal mass (score < 0.3): add 3°C

**Threshold:** 26°C indoors at 3am — body cannot complete overnight thermal recovery. After 3 consecutive failing nights, heat exhaustion risk compounds significantly.

**References:**
- Samuelson, H. et al. (2020). *Housing as a Critical Determinant of Heat Vulnerability and Health.*
- Public Health England (2015). *Heatwave Plan for England.*

---

**KPI 4 — Age-Weighted Overheating Hours**

```
health_risk_hours = Σ (hours where T_op > threshold_for_occupant) × vuln_multiplier
```

**Operative temperature thresholds by occupant category:**

| Occupant | T_op threshold |
|---|---|
| Healthy adult (under 65) | 28°C |
| Elderly (65–75) | 26°C |
| Elderly high-risk (75+) | 25°C |

**Vulnerability multiplier (`vuln_multiplier`):**

| Condition | Multiplier |
|---|---|
| Age 65–75, AC access | 1.2 |
| Age 65–75, no AC | 1.5 |
| Age 75+, no AC, low income | 2.0 |
| Age 75+, no AC, limited mobility | 2.0 |

**Reference:** Samuelson, H. et al. (2020). Thresholds by occupant category and age-weighting approach derived from her methodology. Multiplier values (1.2–2.0) are a design decision within the range her framework implies — document explicitly in the thesis.

---

**Sleep disruption thresholds** (secondary flags, especially for bedroom room_type):

| Threshold | Effect |
|---|---|
| T_air > 24°C | Sleep quality degrades measurably |
| T_air > 27°C | Deep sleep (NREM stage 3) significantly disrupted |

Stable and well-established — implement directly.

---

**Composite Room Risk Score:**

```
composite_score = (0.4 × solar_gain_score)
                + (0.35 × vent_deficit_score)
                + (0.15 × envelope_score)
                + (0.10 × vuln_multiplier_normalized)
```

Where:
- `envelope_score` = normalized wall/roof U-value above threshold
- `vuln_multiplier_normalized` = vuln_multiplier / 2.0

**Weight rationale:** Solar gain and ventilation are the two primary drivers of indoor overheating in Mediterranean climates (UPC 2025 Barcelona study). Weights are design decisions — define as adjustable constants at top of scoring module, recalibrate after EnergyPlus validation.

**Risk classification:**

| Score | Risk level |
|---|---|
| 0.0–0.40 | Safe |
| 0.40–0.65 | Moderate |
| 0.65–0.85 | High |
| 0.85–1.0 | Critical |

---

### Stage 3 — AI Diagnosis (LLM, reads JSON, writes narrative)

**One sub-component only: the Building Interpreter.** The Prioritization Engine has been removed. There is no apartment-level scoring.

**What the LLM receives:** `room_problems.json` for that room — the computed scores, flags, façade data, and occupant profile from Stage 2.

**What the LLM produces:**
1. `diagnosis` — plain-language paragraph translating the computed scores into a human-readable assessment. Specific to this room, not generic. Names the actual problems: façade orientation, ventilation situation, occupant condition, why nocturnal recovery will fail.
2. `key_factors` — ordered array of the 2–4 most significant contributors to risk in plain words (e.g. `["unshaded SW façade", "no cross-ventilation", "elderly resident no AC"]`).

**Critical constraint:** The LLM adds no new computed information. It discovers no new problems. It invents no numbers. It is a narrator, not an analyst — it translates what Stage 2 already computed into language a housing officer or municipality can read. Both output fields are text only and flow to the visualization side panel. They do not feed into Stage 4.

**Example output narrative:** *"This SW-facing bedroom on the 4th floor is at critical heat risk. Its large unshaded window (WWR 0.39) faces peak afternoon sun, and with only one exterior façade, cross-ventilation is not possible. The top-floor location with poor roof insulation means nocturnal recovery will fail on consecutive heatwave nights. The elderly resident without AC access is at high personal risk."*

**Prompting principle:** Feed structured JSON, request structured JSON output. The LLM follows a defined output schema. It does not freestyle. It never invents ΔT numbers.

**Output file:** `room_problems.json` updated — `diagnosis` string and `key_factors` array added to the existing room JSON. No new file created.

---

### Stage 4 — AI Shortlist (LLM + rule-based pre-filter)

**Architecture: hybrid — rule-based pre-filter feeds into LLM reasoning.**

The LLM does not rank strategies by generic ΔT. It reasons about fit — which strategies directly address the diagnosed problems in this specific room — then ranks by impact metrics within the eligible set only.

---

#### Step 4a — Rule-based pre-filter (Python)

**Input files:** `room_problems.json` + `strategy_library.json`

Reads the room JSON and checks each strategy's applicability conditions against the room's computed fields. Marks strategies as eligible or ineligible. Only eligible strategies go to the LLM.

| Condition in JSON | Strategies flagged eligible |
|---|---|
| `solar_gain_score > 0.6` AND SW/SE/S façade | External shading louvers, solar control glazing, internal blinds, external shutters |
| `solar_gain_score > 0.5` AND exterior wall exposed | Cool façade paint |
| `cross_ventilation_direct = false` | Window enlargement, stack-effect vent, interior opening improvement |
| `cross_ventilation_direct = true` | Cross-ventilation behavioural protocol |
| `secondary_path_possible = true` | Interior door / transom intervention |
| `roof_exposed = true` AND `roof_U_value > 1.5` | Roof insulation, cool roof coating, stack-effect roof vent |
| `wall_U_value > 1.2` AND `heritage_protection = false` | External wall insulation (ETICS) |
| `wall_U_value > 1.2` AND `heritage_protection = true` | Internal wall insulation (ETICS ineligible in heritage zones) |
| `wall_U_value > 1.2` (regardless of heritage) | Internal wall insulation always eligible as fallback |
| `nocturnal_recovery_fail = true` AND EPW night min < 22°C | Night purge ventilation |
| `nocturnal_recovery_fail = true` | PCM, thermal mass upgrade |
| `occupant.age_bracket = "70+"` AND `occupant.AC_access = false` | Prioritize low-disruption, low-cost in LLM ranking |
| `shutter_box_present = true` AND SW/SE/S façade | External shutters rank above louvers in shortlist |

Produces a candidate set of 4–6 eligible strategies. Only these go to the LLM.

**Output file:** `eligible_strategies.json` — per room, subset of `strategy_library.json` that passed the pre-filter conditions.

---

#### Step 4b — LLM ranking (contextual judgment)

**Input files:** `room_problems.json` + `eligible_strategies.json` (with full library entries for eligible strategies only)

The LLM receives: room JSON + candidate strategy set with library data.

The LLM reasons about:
- Which strategies best address the specific diagnosed problem (not just highest generic ΔT)
- Feasibility nuances (heritage zone, structural constraints, building type)
- Occupant situation (elderly + low income → weight low-cost and low-disruption higher even if ΔT is slightly lower)
- Strategy interactions (shading + night purge together are more effective than either alone — flag this in justification)

**Output file:** `shortlist.json` — per room, top 3 strategies ranked, each with strategy name, room-specific justification, expected ΔT, cost range, embodied carbon, feasibility note, and literature source.

---

#### Strategy Library — Full Specification

Each entry: `id`, `name`, `type`, `delta_T_min`, `delta_T_max`, `cost_eur_m2_min`, `cost_eur_m2_max`, `carbon_kgCO2_m2`, `applicability_conditions`, `literature_source`, `notes`.

---

**SHADING STRATEGIES**

**1. external_shading_louvers**
- Name: External louvers / brise-soleil
- Applicable façades: SW, SE, S
- ΔT: 2–4°C peak reduction
- Cost: €150–250/m² of façade
- Carbon: 10–15 kgCO₂e/m²
- Applicability conditions: `solar_gain_score > 0.6` on SW/SE/S façade; no heritage protection flag
- Note: Intercepts radiation before it enters glazing — far more effective than internal shading
- Reference: IDAE (2011), *Guía técnica de instalaciones de climatización con equipos autónomos*; Henze et al. (2004), Energy and Buildings

**2. internal_blinds**
- Name: Internal roller blinds
- Applicable façades: any with window
- ΔT: 0.5–1°C
- Cost: €20–50/m² of window
- Carbon: 2–4 kgCO₂e/m²
- Applicability conditions: always eligible as low-cost fallback
- Note: Solar radiation has already entered room as heat before blind intercepts it — limited effectiveness. Rank last among shading options
- Reference: ASHRAE Fundamentals Handbook — internal shading SHGC reduction tables

**3. solar_control_glazing**
- Name: Solar control glazing replacement
- Applicable façades: SW, SE, S, W
- ΔT: 1–2°C
- Cost: €200–400/m² of window
- Carbon: 18–25 kgCO₂e/m²
- Applicability conditions: `solar_gain_score > 0.5`; glazing era pre-2000
- Reference: CTE DB-HE 2022; Pérez-Lombard et al. (2008), Energy and Buildings

**4. green_pergola**
- Name: Green pergola / climbing vegetation
- Applicable façades: SW, SE, S (exterior)
- ΔT: 1–2°C (plus evapotranspiration ambient cooling benefit)
- Cost: €80–150/m²
- Carbon: negative over lifecycle (carbon sequestration)
- Applicability conditions: ground floor or accessible terrace/balcony required
- Reference: Pérez et al. (2011), *Green walls and their interaction with the urban microclimate*, Energy and Buildings

---

**VENTILATION STRATEGIES**

**5. window_enlargement**
- Name: Window enlargement
- ΔT: 1–3°C (conditional — only effective if a second exterior façade exists or can be created)
- Cost: €300–600/m² (structural work included)
- Carbon: 25–40 kgCO₂e/m²
- Applicability conditions: `cross_ventilation_direct = false` AND `exterior_facades >= 1` AND structural feasibility
- Note: Requires structural check. Flag if building is load-bearing masonry
- Reference: EN 15242; Givoni (1992), *Comfort, climate analysis and building design guidelines*, Energy and Buildings

**6. interior_opening_improvement**
- Name: Interior opening / transom addition
- ΔT: 0.5–1.5°C
- Cost: €15–30/m² (door modification only)
- Carbon: 1–3 kgCO₂e/m²
- Applicability conditions: `secondary_path_possible = true`
- Note: Creates partial stack-effect ventilation path through apartment. Low disruption, no structural work
- Reference: Allard (1998), *Natural Ventilation in Buildings*, James and James

**7. stack_effect_roof_vent**
- Name: Stack-effect roof vent
- ΔT: 1–2°C
- Cost: €100–200/unit
- Carbon: 5–8 kgCO₂e/m²
- Applicability conditions: `roof_exposed = true`; top floor or upper floors
- Reference: Santamouris & Asimakopoulos (1996), *Passive Cooling of Buildings*, James and James

**8. night_purge_ventilation**
- Name: Night purge ventilation (behavioural protocol)
- ΔT: 1–2°C nocturnal only (not peak daytime)
- Cost: €0 (no construction)
- Carbon: 0
- Applicability conditions: `nocturnal_recovery_fail = true` AND EPW July overnight minimum < 22°C
- **Critical filter:** If EPW Barcelona July overnight minimum stays above 24°C during heatwave, exclude this strategy entirely — outdoor air is too warm to provide cooling benefit
- Reference: Blondeau et al. (1997), *Night ventilation for building cooling in summer*, Solar Energy

---

**ENVELOPE STRATEGIES**

**9. external_wall_insulation_etics**
- Name: External wall insulation — ETICS system
- ΔT: 1–2°C
- Cost: €80–150/m² of wall
- Carbon: 8–12 kgCO₂e/m²
- Applicability conditions: `wall_U_value > 1.2` on exterior façade
- Reference: IDAE (2016), *Guía práctica de la energía para la rehabilitación de edificios*; CTE DB-HE 2022

**10. roof_insulation**
- Name: Roof insulation membrane
- ΔT: 1–3°C (top floor rooms only)
- Cost: €40–80/m² of roof
- Carbon: 6–10 kgCO₂e/m²
- Applicability conditions: `roof_exposed = true` AND `roof_U_value > 1.5`
- Reference: IDAE (2016); Synnefa et al. (2007), *Estimating the effect of using cool or green roofs on energy savings*, Energy and Buildings

**11. cool_roof_coating**
- Name: Cool roof reflective coating
- ΔT: 1–2°C
- Cost: €15–30/m² of roof
- Carbon: 2–4 kgCO₂e/m²
- Applicability conditions: `roof_exposed = true`; flat roof confirmed
- Note: Highest cost-effectiveness ratio for top-floor rooms. Often combinable with roof insulation
- Reference: Synnefa et al. (2007); Santamouris et al. (2011), *Using advanced cool materials in the urban built environment*, Solar Energy

**12. phase_change_materials**
- Name: Phase-change materials (PCM) in wall assembly
- ΔT: 0.5–1.5°C peak shift — delays peak by 2–4 hours, does not eliminate it
- Cost: €50–120/m² of wall
- Carbon: 10–18 kgCO₂e/m²
- Applicability conditions: `nocturnal_recovery_fail = true`; most effective when combined with night purge ventilation
- Note: PCM shifts timing of peak temperature, not its magnitude. The LLM justification string must flag this distinction explicitly
- Reference: Kuznik et al. (2011), *A review on phase change materials integrated in building walls*, Renewable and Sustainable Energy Reviews

---

**URBAN / SHARED STRATEGIES**

**13. courtyard_greening**
- Name: Courtyard greening
- ΔT: 0.5–1°C ambient reduction in adjacent rooms
- Cost: €200–500/courtyard (project-dependent)
- Carbon: negative lifecycle
- Applicability conditions: building has interior courtyard in IFC
- Reference: Santamouris et al. (2001), *On the impact of urban climate on the energy consumption of buildings*, Solar Energy

**14. shared_cooling_refuge**
- Name: Shared ground-floor cooling refuge
- ΔT: not applicable to individual rooms — resilience metric only
- Cost: highly variable
- Applicability conditions: portfolio-level intervention, not room-level
- Reference: WHO (2011), *Heat and Health*

**15. street_tree_canopy**
- Name: Street tree canopy on SW elevation
- ΔT: 0.5–1°C ambient
- Cost: municipal budget item
- Applicability conditions: urban context intervention, requires municipality coordination
- Reference: Bowler et al. (2010), *Urban greening to cool towns and cities*, Landscape and Urban Planning

---

**ADDITIONAL ENVELOPE STRATEGIES**

**16. internal_wall_insulation**
- Name: Internal wall insulation
- ΔT: 0.5–1.5°C
- Cost: €30–60/m² of wall
- Carbon: 5–8 kgCO₂e/m²
- Applicability conditions: `wall_U_value > 1.2` on exterior façade; particularly relevant when `heritage_protection = true` making external ETICS ineligible
- Note: More accessible for tenants than external insulation — no building permit required in most cases. Slightly reduces room area. Cold bridge risk at wall-floor and wall-ceiling junctions. Should rank above ETICS when heritage protection flag is true
- Reference: IDAE (2016); CTE DB-HE 2022

**17. cool_facade_paint**
- Name: Cool / reflective façade paint
- ΔT: 0.5–2°C (higher impact on currently dark facades)
- Cost: €8–20/m² of façade
- Carbon: 1–3 kgCO₂e/m²
- Applicability conditions: `solar_gain_score > 0.5`; exterior wall exposed to direct solar radiation; regulation check required — heritage zones may restrict colour changes
- Note: Highest cost-effectiveness ratio in the entire library for wall surfaces. Same albedo physics as cool roof coating applied to vertical surfaces. Impact is greater on darker existing facades. Flag heritage check in feasibility note. Requires municipality or community approval in many Barcelona buildings
- Reference: Synnefa et al. (2007); Santamouris et al. (2011), *Using advanced cool materials in the urban built environment*, Solar Energy

---

**ADDITIONAL SHADING STRATEGIES**

**18. window_external_shutters**
- Name: External shutters (persianes)
- ΔT: 1.5–3°C
- Cost: €80–150/m² of window
- Carbon: 6–10 kgCO₂e/m²
- Applicability conditions: `solar_gain_score > 0.6`; SW/SE/S façade; existing shutter box present in IFC or confirmed by occupant form
- Note: Extremely common in Barcelona — many apartments have existing shutter boxes with broken or unused shutters. If shutter box exists, installation cost drops significantly. Generally accepted in heritage zones unlike external louvers. Should rank above external louvers when shutter box already exists
- Reference: IDAE (2011)

---

**ADDITIONAL VENTILATION STRATEGIES**

**19. cross_ventilation_behaviour**
- Name: Cross-ventilation behavioural protocol
- ΔT: 0.5–1.5°C
- Cost: €0 (no construction)
- Carbon: 0
- Applicability conditions: `cross_ventilation_direct = true` — ONLY eligible when apartment already has cross-ventilation potential; opposite condition to interior_opening_improvement
- Note: The air path already exists but the resident is not using it. Intervention is a protocol: which windows to open, in which sequence, at which times of day to maximise airflow. Zero cost, zero disruption. Should always rank in shortlist when cross_ventilation_direct = true, regardless of other conditions
- Reference: Givoni (1992); Allard (1998)

---

### Stage 5 — Visualization (SaaS Web App)

**Platform decision: SaaS web app, not a Revit plugin.**

Reasons: municipalities don't have Revit licenses; shareable via link; fits the portfolio license business model; fastest to build in 3 weeks.

**Tech stack:**
- Frontend: React
- Backend: FastAPI (Python)
- IFC parsing: `ifcopenshell` (server-side)
- 3D viewer: **That Open Components (TOC)** — formerly IFC.js — React component library for IFC/Fragments browser rendering
- IFC → Fragments conversion: server-side, once per upload
- Storage: SQLite or JSON store (MVP)

**Input files read by visualization:**
- `room_problems.json` — drives 3D color overlay (risk_level per room) and side panel (diagnosis narrative + scores)
- `shortlist.json` — drives retrofit cards in side panel
- `strategy_library.json` — referenced for strategy detail display

**Viewer flow:**
1. User uploads `.ifc` file
2. Backend parses with `ifcopenshell` → extracts room data + geometry
3. Backend converts IFC → Fragments (compressed, web-optimized for TOC viewer)
4. Analysis engine runs (Stages 2–4) → all output files produced
5. Color mapping applied to Fragments viewer by IFC `GlobalId` per room
6. User sees colored 3D model in browser

**Color scheme:**
- Critical → red
- High → orange
- Moderate → yellow
- Safe → green
- Ventilation deficit → hatched pattern overlay on walls (secondary encoding alongside color)

**Side panel (opens on room click — no chat input):**
1. Room header: name, type, floor, risk level badge
2. AI diagnosis narrative (from `room_problems.json` — pre-generated, not a real-time LLM call)
3. Risk score breakdown — interpreted labels, not raw numbers
4. Before/after toggle — switches viewer colors to show predicted post-retrofit state; ΔT shown per room
5. Top 3 retrofit cards (from `shortlist.json`) — selectable, selection drives the before/after toggle
6. Export row: download room PDF

**Portfolio view (municipality use case):**
- Reads `priority.json` — displays all rooms pre-sorted by composite_score descending
- No apartment grouping, no floor grouping — per room only, because orientation differs room by room
- Columns: room ID, room name, floor, orientation, risk level, top vulnerability flag, composite_score
- Filterable by risk level, floor, orientation

**Export outputs:**
- PDF report: per-room evidence dossier with diagnosis, scores, and shortlist
- CSV export (optional Revit path): `room_id, ifc_global_id, risk_level, top_strategy` → readable by Dynamo script applying `OverrideGraphicSettings` color overrides in Revit

---

#### 3D Before / After Retrofit Modeling

When the user selects a retrofit strategy from the shortlist, the viewer switches to an "after retrofit" state. How this state is visualized depends on whether the strategy involves a physical geometry change or not.

**Two categories of strategy for visualization purposes:**

**Category A — Geometry-modifiable strategies**
These involve a physical change that can be represented in 3D by modifying the IFC geometry programmatically. The viewer generates a modified version of the relevant element and displays it alongside or replacing the original:

| Strategy | What changes in 3D |
|---|---|
| `external_shading_louvers` | Louver geometry added in front of window on wall exterior |
| `window_enlargement` | Window element resized larger in wall opening |
| `stack_effect_roof_vent` | Vent/chimney element added to roof surface |
| `interior_opening_improvement` | Transom or opening added above interior door |
| `green_pergola` | Pergola geometry added in front of façade |
| `window_external_shutters` | Shutter panels added flanking window element |
| `roof_insulation` | Insulation layer added above roof slab |
| `external_wall_insulation_etics` | Insulation layer added to exterior wall face |
| `internal_wall_insulation` | Insulation layer added to interior wall face |

For these strategies, the viewer generates the modified geometry using `ifcopenshell` to create new IFC elements (or modify existing ones) programmatically, converts to Fragments, and renders the before/after as a toggle. The new geometry is rendered in a distinct color (e.g. green overlay) to make the addition visually clear.

**Category B — Non-geometry strategies**
These cannot be shown as a 3D model change. Instead the affected element is highlighted with a color overlay and an annotation label:

| Strategy | Visualization |
|---|---|
| `cool_roof_coating` | Roof surface highlighted in light blue with label "cool coating applied" |
| `cool_facade_paint` | Façade surface highlighted in white/light color with label "reflective paint applied" |
| `solar_control_glazing` | Window highlighted in blue tint with label "solar control glazing" |
| `internal_blinds` | Window highlighted with label "internal blinds installed" |
| `night_purge_ventilation` | Window highlighted with animated arrow showing airflow direction |
| `cross_ventilation_behaviour` | All openings highlighted with animated airflow arrows |
| `phase_change_materials` | Wall surface highlighted with label "PCM layer integrated" |

**Implementation approach:**
- All geometry modifications are generated server-side using `ifcopenshell` when the shortlist is produced
- Pre-generate both the baseline Fragments file and one modified Fragments file per Category A strategy in the shortlist
- Store both versions and serve them on toggle — no real-time geometry computation in the browser
- Category B strategies apply only color overrides and SVG annotation overlays on top of the baseline Fragments viewer — no new geometry files needed

---

## 3. Room JSON Schema

Full structured output of Stage 2, which feeds into Stages 3 and 4. The LLM never reads geometry directly — everything it needs to reason about must be in this JSON.

```json
{
  "room_id": "R_204",
  "room_name": "Bedroom SW",
  "room_type": "bedroom",
  "floor": 4,
  "area_m2": 14.2,

  "facades": [
    {
      "orientation": "SW",
      "orientation_degrees": 225,
      "wall_area_m2": 12.4,
      "window_area_m2": 4.8,
      "WWR": 0.39,
      "has_external_shading": false,
      "shading_obstruction": "none",
      "wall_U_value": 1.8,
      "wall_construction_era": "pre-1980"
    }
  ],

  "ventilation": {
    "exterior_facades": 1,
    "exterior_orientations": ["SW"],
    "cross_ventilation_direct": false,
    "cross_ventilation_reason": "single exterior facade, no opposing opening",
    "secondary_path_possible": true,
    "secondary_path_note": "interior door to NE-facing living room",
    "estimated_ACH": 0.4
  },

  "envelope": {
    "roof_exposed": true,
    "roof_U_value": 2.1,
    "dominant_wall_U_value": 1.8
  },

  "thermal_scores": {
    "solar_gain_score": 0.87,
    "peak_solar_W_per_m2": 312,
    "vent_deficit_score": 0.91,
    "thermal_mass_score": 0.22,
    "T_op_estimated_peak_C": 34.1,
    "WBGT_peak_estimated": 33.4,
    "health_risk_hours": 142,
    "nocturnal_recovery_fail": true,
    "estimated_3am_temp_C": 28.1,
    "sleep_disruption_flag": true,
    "risk_level": "critical"
  },

  "occupant": {
    "age_bracket": "70+",
    "AC_access": false,
    "income_category": "low",
    "mobility": "limited",
    "household_size": 1,
    "vuln_multiplier": 2.0
  },

  "composite_score": 0.94,

  "ai_outputs": {
    "diagnosis": "This SW-facing bedroom on the 4th floor is at critical heat risk...",
    "key_factors": ["unshaded SW facade", "single exterior facade", "top floor roof exposure", "elderly resident no AC"],
    "eligible_strategies": ["external_shading_louvers", "roof_insulation", "interior_opening_improvement"],
    "shortlist": [
      {
        "strategy_id": "external_shading_louvers",
        "rank": 1,
        "justification": "SW façade with WWR 0.39 and no existing shading is the primary driver of solar gain. External louvers intercept radiation before it enters the glazing.",
        "delta_T_expected_C": 3.2,
        "cost_eur_m2": 180,
        "carbon_kgCO2_m2": 12,
        "feasibility_note": "No heritage protection flag. Wall area sufficient for mounting.",
        "literature_source": "IDAE (2011); Henze et al. (2004)"
      },
      {
        "strategy_id": "roof_insulation",
        "rank": 2,
        "justification": "Top floor with roof U-value of 2.1 W/m²K. Roof is the secondary heat gain path and directly causes nocturnal recovery failure.",
        "delta_T_expected_C": 2.1,
        "cost_eur_m2": 60,
        "carbon_kgCO2_m2": 8,
        "feasibility_note": "Flat roof confirmed. Standard membrane system applicable.",
        "literature_source": "IDAE (2016); Synnefa et al. (2007)"
      },
      {
        "strategy_id": "interior_opening_improvement",
        "rank": 3,
        "justification": "Direct cross-ventilation not possible (single exterior façade). A secondary air path through the interior door to the NE living room enables partial stack-effect ventilation at near-zero cost.",
        "delta_T_expected_C": 1.0,
        "cost_eur_m2": 20,
        "carbon_kgCO2_m2": 2,
        "feasibility_note": "Requires only door modification or transom addition. No structural work.",
        "literature_source": "Allard (1998)"
      }
    ]
  }
}
```

---

## 4. Validation Strategy

**Layer 1 — Rule-based thresholds from literature**

Every risk flag in Stage 2 is triggered by a published threshold. Add `# SOURCE:` comments in code.

| Rule | Reference |
|---|---|
| T_op > 32°C elderly risk | WHO (2011), Heat and Health |
| WBGT > 28°C strain / > 32°C elderly danger | ISO 7243:2017 |
| Nocturnal recovery > 26°C | Samuelson (2020); Public Health England (2015) |
| Sleep disruption > 24°C / > 27°C | Established sleep medicine literature |
| Wall U-value > 1.2 flag | CTE DB-HE 2022 |
| Roof U-value > 1.5 flag | CTE DB-HE 2022 |
| ACH target 4.0 | EN 15251 / ASHRAE 62.1 |

**Layer 2 — One calibration simulation**
Run one full EnergyPlus or DesignBuilder simulation on the chosen reference apartment (worst-case: top floor, SW façade, Barceloneta or Left Eixample) using the Barcelona heatwave EPW. Confirm that Stage 2 proxy scores correctly identify the same high-risk rooms. Required for one reference case only.

**Layer 3 — Literature-sourced ΔT values**
All strategy ΔT numbers come from published sources in the strategy library. The LLM system prompt must instruct it to use only library values, never generate its own numbers.

---

## 5. Full Reference List

| Reference | Used in |
|---|---|
| ASHRAE Fundamentals Handbook, Ch.18 | Stage 2a — solar gain, SHGC defaults |
| ASHRAE 55-2020 | Stage 2d — operative temperature definition |
| ASHRAE 62.1 | Stage 2b — ACH target |
| EN 15242 | Stage 2b — ventilation flow rate methodology |
| EN 15251 | Stage 2b — ACH target (4.0) |
| EN ISO 7726 | Stage 2d — operative temperature formula |
| ISO 7243:2017 | Stage 2d — WBGT thresholds |
| CTE DB-HE 2022 | Stage 2c — U-value thresholds; Stage 4 — glazing |
| IVE typology database | Stage 2c — U-value defaults by era |
| LBNL Heat Island Group Pigment Database | Stage 2c — roof albedo by colour/material |
| Cool Roof Rating Council (CRRC) product database | Stage 2c — roof albedo by colour/material |
| US EPA Heat Island Reduction Program | Stage 2c — roof albedo by colour/material |
| ASTM E1980 | Stage 2c — Solar Reflectance Index methodology |
| ASHRAE Fundamentals Handbook, Ch.18 | Stage 2c — sol-air temperature roof solar gain method |
| WHO (2011), Heat and Health | Stage 2d — elderly T_op threshold |
| Stull, R. (2011), J. Applied Meteorology and Climatology | Stage 2d — wet bulb temperature formula |
| Samuelson et al. (2020) | Stage 2d — overheating hours methodology, nocturnal threshold |
| Public Health England (2015), Heatwave Plan for England | Stage 2d — nocturnal recovery threshold |
| UPC (2025), Barcelona heat vulnerability study | Stage 1 — site context statistics |
| IDAE (2011), Guía técnica climatización | Stage 4 — shading ΔT values |
| IDAE (2016), Guía rehabilitación de edificios | Stage 4 — insulation ΔT and costs |
| Henze et al. (2004), Energy and Buildings | Stage 4 — external shading ΔT |
| Pérez-Lombard et al. (2008), Energy and Buildings | Stage 4 — glazing ΔT |
| Pérez et al. (2011), Energy and Buildings | Stage 4 — green pergola ΔT |
| Givoni (1992), Energy and Buildings | Stage 4 — window enlargement ΔT |
| Allard (1998), Natural Ventilation in Buildings | Stage 4 — interior opening ΔT |
| Santamouris & Asimakopoulos (1996), Passive Cooling of Buildings | Stage 4 — stack-effect vent ΔT |
| Blondeau et al. (1997), Solar Energy | Stage 4 — night purge ΔT |
| Synnefa et al. (2007), Energy and Buildings | Stage 4 — roof insulation and cool roof ΔT |
| Santamouris et al. (2011), Solar Energy | Stage 4 — cool roof ΔT |
| Kuznik et al. (2011), Renewable and Sustainable Energy Reviews | Stage 4 — PCM ΔT |
| Santamouris et al. (2001), Solar Energy | Stage 4 — courtyard greening ΔT |
| Bowler et al. (2010), Landscape and Urban Planning | Stage 4 — street trees ΔT |

---

## 6. Architecture Notes for Claude Code

**Key libraries:**
- `ifcopenshell` — IFC parsing, wall orientation extraction, window and room geometry
- `pvlib` — sun position calculation (azimuth, altitude) per hour for any lat/lon
- `shapely` — shadow polygon geometry: computes shadow cast by surrounding buildings onto each façade
- `osmnx` — fetches surrounding building footprints and heights from OpenStreetMap within radius of building location
- `That Open Components (TOC)` — IFC/Fragments browser viewer (React)
- `FastAPI` — backend API
- `anthropic` Python SDK — LLM calls
- `numpy` — WBGT and temperature calculations
- `reportlab` or `WeasyPrint` — PDF report generation
- `pandas` — risk score computation and portfolio ranking

**Processing flow (backend):**
1. `/upload` endpoint receives IFC file
2. `ifcopenshell` parses → extracts rooms, walls, windows, materials, orientations
3. EPW file loaded (static, pre-loaded for Barcelona — July 15–21 design week)
4. Stage 2 calculations run per room → `room_problems.json` produced (scores, flags, composite_score, risk_level)
5. Stage 2b Python sort → `priority.json` produced (all rooms ranked by composite_score descending)
6. Stage 3 LLM call per room → `diagnosis` + `key_factors` added to `room_problems.json` (translation only, no new computation)
7. Stage 4a pre-filter reads `room_problems.json` + `strategy_library.json` → `eligible_strategies.json` produced per room
8. Stage 4b LLM call per room → `shortlist.json` produced (top 3 strategies ranked)
9. IFC → Fragments conversion runs (for viewer)
10. All files stored → frontend fetches and renders

**File summary for Claude Code:**

| File | Created at step | Updated at step | Used at step |
|---|---|---|---|
| `room_problems.json` | Step 4 | Step 6 | Steps 7, 10 |
| `priority.json` | Step 5 | Never | Step 10 (portfolio view only) |
| `strategy_library.json` | Static in codebase | Never | Steps 7, 10 |
| `eligible_strategies.json` | Step 7 | Never | Step 8 |
| `shortlist.json` | Step 8 | Never | Step 10 |

**LLM call structure:**
- Model: `claude-sonnet-4-20250514`
- System prompt: role as building health diagnostician; use only provided JSON data and strategy library values; never invent ΔT numbers; return structured JSON only
- User message: room JSON + eligible strategy subset from library
- Output: structured JSON (diagnosis string + key_factors array + shortlist array)
- Do not stream — wait for full structured response, validate JSON schema before storing

**Formula implementation notes:**
- Implement Stull (2011) wet bulb formula first — WBGT and all downstream health scores depend on it
- Add `# SOURCE: [reference]` comment on every threshold and formula line
- Add `# PROXY: order-of-magnitude estimate, not CFD` on all ACH values
- Define composite score weights as named constants at top of scoring module — easy to recalibrate after EnergyPlus validation

**Speed target:** Full building analysis under 30 seconds for 10–20 apartments. Stage 2 is fast (seconds per room). LLM calls are the bottleneck — run in parallel with `asyncio`.

**Revit export (bonus, not MVP):**
Expose `/export/csv` endpoint returning `room_id, ifc_global_id, risk_level, top_strategy` per room. A companion Dynamo script applies `OverrideGraphicSettings` color overrides in Revit by matching `ifc_global_id`. Gives the "highlight walls in Revit" demo without a full plugin — approximately 1–2 days of work.

---

## 7. Business Model Notes

**Primary product:** SaaS platform, annual portfolio license
- Target price: ~€8,000/year per 500-unit portfolio
- Named client 1: Barcelona Housing Consortium
- Named client 2: Barcelona Public Health Agency (ASPB)
- Named client 3: Habitatge Metròpolis Barcelona (social housing operator)

**Secondary product:** Retrofit assessment consultancy — one-off fee per building assessment report, targeting private building owners and arquitectos técnicos.

**Rebuttal for "what if there is no BIM model":** A LOD 200 massing model with room boundaries, wall orientations, and window positions is sufficient — producible from existing floor plans in hours. As a fallback, the tool accepts a structured data form with manual inputs. This produces lower fidelity but still a defensible portfolio-level risk ranking, which is sufficient for the prioritization use case.

**Validation milestone (thesis requirement):** Interview at least one municipality, housing operator, or climate adaptation stakeholder before mid-term to validate the prioritization value proposition.

---

*This document reflects design decisions made through iterative sessions — May 2026. Use as ground truth for implementation. Document any architectural changes made during the build as amendments here.*
