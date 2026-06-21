# HVRA — Retrofit Strategy Library (Categorized)
> For Claude Code: drives visualization output logic per strategy card
> Last updated: June 2026

---

## Visualization category definitions

Each strategy belongs to one of four categories. The category determines what the strategy card renders — not just what text it shows.

| Category | Visualization output | 3D viewer behavior |
|---|---|---|
| **A — Geometry changes** | Section/elevation detail + 3D element added or modified | Generate new IFC element, render as green overlay toggle |
| **B — Material changes** | Section detail showing layer assembly before/after with U-value or SHGC delta | Highlight affected surface with color + label annotation. No new IFC element. |
| **C — Operational / behavioral** | Airflow protocol diagram (floor plan with arrows + schedule) | Highlight openings with animated airflow arrows |
| **D — Urban / external** | Annotated site plan or street section | Flag at building/block level only, not room level |

---

## Category A — Geometry changes
*A new physical element is added to or modified in the building. 3D viewer: generate new IFC element, render before/after toggle as green overlay. Card: section or elevation SVG + performance delta + method steps.*

### A1. external_shading_louvers
- **Name:** External louvers / brise-soleil
- **Applicable façades:** SW, SE, S
- **ΔT:** 2–4°C peak reduction
- **Cost:** €150–250/m² of façade
- **Carbon:** 10–15 kgCO₂e/m²
- **Applicability:** `solar_gain_score > 0.6` on SW/SE/S façade; `heritage_protection = false`
- **3D change:** Louver geometry added in front of window on wall exterior
- **Card visual:** Section showing louver blade depth, angle, and fixing detail on exterior wall face. Optimal blade angle derivable from solar altitude at peak hour for this façade orientation.
- **Note:** Intercepts radiation before it enters glazing — far more effective than internal shading.
- **Source:** IDAE (2011); Henze et al. (2004), Energy and Buildings

### A2. operable_external_sunscreen
- **Name:** Operable external sunscreen (retractable)
- **Applicable façades:** SW, SE, S, W
- **ΔT:** 1.5–3°C (variable by deployment)
- **Cost:** €100–200/m² of window
- **Carbon:** 8–12 kgCO₂e/m²
- **Applicability:** `solar_gain_score > 0.6`; user can operate manually or via timer
- **3D change:** Retractable screen element added in front of window
- **Card visual:** Window elevation + section showing screen housing, guide rails, retracted and deployed positions.
- **Note:** Preferred over fixed louvers when occupant needs daylight flexibility. Better accepted in heritage zones than fixed brise-soleil.

### A3. window_external_shutters
- **Name:** External shutters (persianes)
- **Applicable façades:** SW, SE, S
- **ΔT:** 1.5–3°C
- **Cost:** €80–150/m² of window
- **Carbon:** 6–10 kgCO₂e/m²
- **Applicability:** `solar_gain_score > 0.6`; SW/SE/S façade; `shutter_box_present = true` preferred
- **3D change:** Shutter panels added flanking window element
- **Card visual:** Window elevation + horizontal section showing shutter box, guide rails, panel thickness.
- **Note:** Very common in Barcelona — many apartments have existing shutter boxes with broken or unused shutters. If shutter box already exists, installation cost drops significantly. Accepted in heritage zones unlike external louvers. Should rank above external louvers when shutter box already present.
- **Source:** IDAE (2011)

### A4. green_pergola
- **Name:** Climbing vegetation screen (green façade)
- **Applicable façades:** SW, SE, S (exterior)
- **ΔT:** 1–2°C (plus evapotranspiration ambient cooling benefit)
- **Cost:** €80–150/m²
- **Carbon:** Negative over lifecycle (carbon sequestration)
- **Applicability:** Ground floor or accessible terrace/balcony required (plants need soil access and maintenance)
- **3D change:** Trellis/support structure with climbing vegetation added in front of façade, with stand-off air gap
- **Card visual:** Section showing support frame, vegetation layer, stand-off distance from wall face.
- **Note:** This is a vertical green-façade screen shading the wall and windows ("double-skin green façade"), NOT a garden pergola. Internal id `green_pergola` kept for compatibility.
- **Source:** Pérez et al. (2011), Energy and Buildings

### A5. window_enlargement
- **Name:** Window enlargement
- **Applicable façades:** Any with cross-ventilation potential
- **ΔT:** 1–3°C (conditional — only effective if a second exterior façade exists or can be created)
- **Cost:** €300–600/m² (structural work included)
- **Carbon:** 25–40 kgCO₂e/m²
- **Applicability:** `cross_ventilation_direct = false` AND `exterior_facades >= 1` AND structural feasibility
- **3D change:** Window element resized larger in wall opening
- **Card visual:** Floor plan with ventilation path arrows — not a section detail. Positioning and cross-ventilation path matter more than size. Flag if load-bearing masonry.
- **Source:** EN 15242; Givoni (1992), Energy and Buildings

### A6. interior_opening_improvement
- **Name:** Interior opening / transom addition
- **ΔT:** 0.5–1.5°C
- **Cost:** €15–30/m² (door modification only)
- **Carbon:** 1–3 kgCO₂e/m²
- **Applicability:** `secondary_path_possible = true`
- **3D change:** Transom or opening added above interior door element
- **Card visual:** Door elevation showing added transom opening with dimensions and air path arrow.
- **Note:** Creates partial stack-effect ventilation path through apartment. Low disruption, no structural work.
- **Source:** Allard (1998), Natural Ventilation in Buildings

### A7. stack_effect_roof_vent
- **Name:** Stack-effect roof vent / solar chimney
- **Applicable location:** Top floor only
- **ΔT:** 1–2°C
- **Cost:** €100–200/unit
- **Carbon:** 5–8 kgCO₂e/m²
- **Applicability:** `roof_exposed = true`; top floor or upper floors
- **3D change:** Vent/chimney element added to roof surface
- **Card visual:** Vertical section through roof slab and chimney showing air path upward, stack height, flap/damper detail.
- **Note:** Strongest geometry output in the library. Unique to top-floor use case. Directly addresses nocturnal recovery failure — frame this in the card.
- **Source:** Santamouris & Asimakopoulos (1996), Passive Cooling of Buildings

---

## Category B — Material changes
*Same geometry, different material or added layer. 3D viewer: highlight affected surface with color overlay + label annotation. No new IFC element generated. Card: section detail SVG showing layer composition before/after + U-value or SHGC delta.*

### B1. external_wall_insulation_etics
- **Name:** External wall insulation — ETICS system
- **ΔT:** 1–2°C
- **Cost:** €80–150/m² of wall
- **Carbon:** 8–12 kgCO₂e/m²
- **Applicability:** `wall_U_value > 1.2` on exterior façade; `heritage_protection = false`
- **3D highlight:** Exterior wall surface highlighted with label "ETICS insulation layer"
- **Card visual:** Wall cross-section before/after — existing assembly (plaster / brick / air gap / brick / render), then added EPS or mineral wool board + new render coat on exterior face. Annotate U-value before and after. The ≈10cm thickness addition is a material specification, not a meaningful geometry change at building scale.
- **Source:** IDAE (2016); CTE DB-HE 2022

### B2. internal_wall_insulation
- **Name:** Internal wall insulation
- **ΔT:** 0.5–1.5°C
- **Cost:** €30–60/m² of wall
- **Carbon:** 5–8 kgCO₂e/m²
- **Applicability:** `wall_U_value > 1.2` on exterior façade; primary route when `heritage_protection = true`
- **3D highlight:** Interior wall surface highlighted with label "internal insulation layer"
- **Card visual:** Wall cross-section before/after — same exterior, added insulated board (PIR/mineral wool) + plasterboard on interior face. Annotate U-value delta. Flag slight room area reduction in method steps.
- **Note:** No building permit required in most cases. Cold bridge risk at wall-floor and wall-ceiling junctions — flag in method card. Should rank above ETICS when `heritage_protection = true`.
- **Source:** IDAE (2016); CTE DB-HE 2022

### B3. roof_insulation
- **Name:** Roof insulation membrane
- **Applicable location:** Top floor only
- **ΔT:** 1–3°C
- **Cost:** €40–80/m² of roof
- **Carbon:** 6–10 kgCO₂e/m²
- **Applicability:** `roof_exposed = true` AND `roof_U_value > 1.5`
- **3D highlight:** Roof surface highlighted with label "insulation membrane added"
- **Card visual:** Roof cross-section before/after — existing slab / screed / waterproof membrane, then added rigid insulation board + new waterproof membrane on top. Annotate U-value delta.
- **Source:** IDAE (2016); Synnefa et al. (2007), Energy and Buildings

### B4. cool_roof_coating
- **Name:** Cool roof reflective coating
- **ΔT:** 1–2°C
- **Cost:** €15–30/m² of roof
- **Carbon:** 2–4 kgCO₂e/m²
- **Applicability:** `roof_exposed = true`; flat roof confirmed
- **3D highlight:** Roof surface highlighted in light blue/white with label "cool coating applied"
- **Card visual:** Roof surface before/after — same layer assembly, top surface changes from existing colour to white/reflective. Show albedo change using the room's actual `roof_colour` value vs. the reflective category (albedo 0.775, midpoint of the 0.70–0.85 LBNL/CRRC/EPA range — see HVRA_build_reference_4.md §2c). Cheapest roof intervention. Often combinable with roof insulation — show combined delta if both are in shortlist.
- **Source:** Synnefa et al. (2007); Santamouris et al. (2011), Solar Energy; LBNL Heat Island Group Pigment Database; CRRC product database (roof_colour albedo values — see HVRA_build_reference_4.md §2c)

### B5. solar_control_glazing
- **Name:** Solar control glazing replacement
- **Applicable façades:** SW, SE, S, W
- **ΔT:** 1–2°C
- **Cost:** €200–400/m² of window
- **Carbon:** 18–25 kgCO₂e/m²
- **Applicability:** `solar_gain_score > 0.5`; glazing era pre-2000
- **3D highlight:** Window element highlighted in blue tint with label "solar control glazing"
- **Card visual:** Glass cross-section before/after — single pane vs double with low-e coating. Same frame geometry, different glass specification. Show SHGC value change (e.g. 0.6 → 0.35).
- **Source:** CTE DB-HE 2022; Pérez-Lombard et al. (2008), Energy and Buildings

### B6. cool_facade_paint
- **Name:** Cool / reflective façade paint
- **ΔT:** 0.5–2°C (higher impact on currently dark façades)
- **Cost:** €8–20/m² of façade
- **Carbon:** 1–3 kgCO₂e/m²
- **Applicability:** `solar_gain_score > 0.5`; exterior wall exposed to direct solar radiation
- **3D highlight:** Façade surface highlighted in white/light color with label "reflective paint applied"
- **Card visual:** Exterior wall surface before/after — same assembly, outermost surface changes albedo. Show albedo value change. Cheapest material-change intervention in the library.
- **Note:** Heritage check required — heritage zones may restrict colour changes. Community/municipality approval often needed in Barcelona.
- **Source:** Synnefa et al. (2007); Santamouris et al. (2011), Solar Energy

### B7. phase_change_materials
- **Name:** Phase-change materials (PCM) in wall assembly
- **ΔT:** 0.5–1.5°C peak shift — delays peak by 2–4 hours, does not eliminate it
- **Cost:** €50–120/m² of wall
- **Carbon:** 10–18 kgCO₂e/m²
- **Applicability:** `nocturnal_recovery_fail = true`; most effective combined with night purge ventilation
- **3D highlight:** Wall surface highlighted with label "PCM layer integrated"
- **Card visual:** Wall cross-section showing PCM panel position in assembly. Include a small thermal mass delay curve diagram — flat line during phase change shows the delayed peak. Label phase-change temperature (typically 23–26°C for residential).
- **Note:** PCM shifts timing of peak temperature, not its magnitude. LLM justification MUST flag this distinction — do not imply ΔT reduction, imply ΔT delay.
- **Source:** Kuznik et al. (2011), Renewable and Sustainable Energy Reviews

### B8. internal_blinds
- **Name:** Internal roller blinds
- **Applicable façades:** Any with window
- **ΔT:** 0.5–1°C
- **Cost:** €20–50/m² of window
- **Carbon:** 2–4 kgCO₂e/m²
- **Applicability:** Always eligible as low-cost fallback
- **3D highlight:** Window highlighted with label "internal blinds installed"
- **Card visual:** Window elevation showing blind box at head and drop position. Include honest note: solar radiation already entered the room as heat before the blind intercepts it — explain in section why external shading is 3–4× more effective.
- **Note:** Rank last among all shading options.
- **Source:** ASHRAE Fundamentals Handbook — internal shading SHGC reduction tables

---

## Category C — Operational / behavioral
*No physical change to building fabric. 3D viewer: highlight relevant openings with animated airflow arrows. Card: floor plan airflow diagram + schedule/protocol + performance note.*

### C1. night_purge_ventilation
- **Name:** Night purge ventilation (behavioural protocol)
- **ΔT:** 1–2°C nocturnal only (not peak daytime)
- **Cost:** €0 (no construction)
- **Carbon:** 0
- **Applicability:** `nocturnal_recovery_fail = true` AND EPW July overnight minimum < 22°C
- **3D highlight:** All openable windows highlighted with animated outward arrows (night airflow direction)
- **Card visual:** Protocol card — which windows to open, time window (e.g. 23:00–06:00), condition check (open only if T_outdoor < T_indoor). Include EPW overnight temperature curve for July showing when protocol is effective.
- **Critical filter:** If EPW Barcelona July overnight minimum stays above 24°C during heatwave, exclude entirely — outdoor air too warm to provide cooling benefit.
- **Source:** Blondeau et al. (1997), Solar Energy

### C2. cross_ventilation_behaviour
- **Name:** Cross-ventilation behavioural protocol
- **ΔT:** 0.5–1.5°C
- **Cost:** €0 (no construction)
- **Carbon:** 0
- **Applicability:** `cross_ventilation_direct = true` ONLY — opposite condition to interior_opening_improvement
- **3D highlight:** All openings highlighted with animated airflow arrows showing cross-flow direction
- **Card visual:** Floor plan showing which windows to open simultaneously, airflow path, time of day (morning and evening when wind is favorable). The air path already exists — occupant is not using it.
- **Note:** Should always appear in shortlist when `cross_ventilation_direct = true`. Zero cost, zero disruption. Never recommend alongside interior_opening_improvement — opposite eligibility conditions.
- **Source:** Givoni (1992); Allard (1998)

---

## Category D — Urban / external
*Operates at block or building scale, not room scale. 3D viewer: flag at building level only. Not applicable to individual room view. Card: annotated site plan or street section + coordination note.*

### D1. courtyard_greening
- **Name:** Courtyard greening
- **ΔT:** 0.5–1°C ambient reduction in adjacent rooms
- **Cost:** €200–500/courtyard (project-dependent)
- **Carbon:** Negative lifecycle (carbon sequestration)
- **Applicability:** Building has interior courtyard in IFC
- **Card visual:** Plan view of courtyard with greening zones. Note coordination requirement (community decision, not individual tenant).
- **Source:** Santamouris et al. (2001), Solar Energy

### D2. street_tree_canopy
- **Name:** Street tree canopy on SW elevation
- **ΔT:** 0.5–1°C ambient
- **Cost:** Municipal budget item
- **Carbon:** Negative lifecycle
- **Applicability:** Urban context intervention; requires municipality coordination
- **Card visual:** Annotated street section showing canopy coverage of SW façade, indicative species + mature canopy width. Note: municipality-level action only.
- **Source:** Bowler et al. (2010), Landscape and Urban Planning

### D3. shared_cooling_refuge
- **Name:** Shared ground-floor cooling refuge
- **ΔT:** Not applicable to individual rooms — resilience metric only
- **Cost:** Highly variable
- **Applicability:** Portfolio-level intervention only; not applicable at room level
- **Card visual:** Building section showing designated refuge space (ground floor, north-facing, shaded). Relevant only in Layer 0 / municipality use case.
- **Source:** WHO (2011), Heat and Health

---

## Summary table for Claude Code

| strategy_id | Name | Category | 3D viewer behavior | Card visual type |
|---|---|---|---|---|
| external_shading_louvers | External louvers | A | New louver element added | Section detail + blade angle |
| operable_external_sunscreen | Retractable sunscreen | A | Screen element added | Window elevation + section |
| window_external_shutters | External shutters | A | Shutter panels added | Window elevation + section |
| green_pergola | Climbing vegetation screen | A | Vegetation screen added at façade | Section with vegetation layer |
| window_enlargement | Window enlargement | A | Window resized | Ventilation path floor plan |
| interior_opening_improvement | Transom / interior opening | A | Transom added to door | Door elevation detail |
| stack_effect_roof_vent | Stack-effect roof vent | A | Chimney added to roof | Roof + chimney section |
| external_wall_insulation_etics | ETICS wall insulation | B | Exterior wall highlighted | Wall cross-section before/after |
| internal_wall_insulation | Internal wall insulation | B | Interior wall highlighted | Wall cross-section before/after |
| roof_insulation | Roof insulation | B | Roof surface highlighted | Roof cross-section before/after |
| cool_roof_coating | Cool roof coating | B | Roof surface highlighted white | Albedo value diagram |
| solar_control_glazing | Solar control glazing | B | Window highlighted blue | Glass section + SHGC delta |
| cool_facade_paint | Cool façade paint | B | Façade highlighted white | Albedo value diagram |
| phase_change_materials | PCM wall assembly | B | Wall surface highlighted | Wall section + delay curve |
| internal_blinds | Internal roller blinds | B | Window highlighted | Window elevation + note |
| night_purge_ventilation | Night purge protocol | C | Windows + outward arrows | Protocol card + EPW temp curve |
| cross_ventilation_behaviour | Cross-ventilation protocol | C | All openings + flow arrows | Floor plan + airflow diagram |
| courtyard_greening | Courtyard greening | D | Courtyard flagged | Plan view annotated |
| street_tree_canopy | Street tree canopy | D | Building-level flag | Street section annotated |
| shared_cooling_refuge | Shared cooling refuge | D | Building-level flag | Building section annotated |

---

*This file is the ground truth for strategy card visualization logic. The `category` field drives which visual component the card renders. Never infer category from strategy name — always read it from this file.*
