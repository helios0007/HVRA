"""
IFC geometry parser — Stage 2 prerequisite.

Extracts per-room data from an IFC model:
  - Room name, type, floor index, area (IfcSpace + IfcBuildingStorey)
  - Exterior facades: compass bearing, wall area, window area, WWR
    (wall placement matrix → orientation per HVRA_build_reference_4.md §Stage 1)
  - Wall U-value from IFC material properties, or era lookup fallback
  - External shading element flag (IFC louvers/overhangs)
  - Interior door flag (drives secondary_path_possible in ventilation)
  - Top-floor flag (drives roof_exposed in envelope)

SOURCE: ifcopenshell wall placement matrix — HVRA_build_reference_4.md §Stage 1
SOURCE: CTE DB-HE + IVE typology database — U-value defaults by era
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.util.placement
    import ifcopenshell.util.element
    import ifcopenshell.util.unit  # [urban-fix] length-unit scale for geometry fallback
    import ifcopenshell.geom
    _IFC_AVAILABLE = True
    _geom_settings = ifcopenshell.geom.settings()
    _geom_settings.set(_geom_settings.USE_WORLD_COORDS, True)
except ImportError:
    _IFC_AVAILABLE = False
    _geom_settings = None


# ── U-value defaults by construction era ───────────────────────────────────────
# SOURCE: CTE DB-HE historical compliance requirements +
#         IVE (Institut Valencià de l'Edificació) Mediterranean typology database.
# Mid-point of reported ranges used as the single default value.
U_VALUE_DEFAULTS: dict[str, dict[str, float]] = {
    "pre-1960":  {"wall": 2.25, "roof": 2.75},
    "1960-1979": {"wall": 1.75, "roof": 2.25},
    "1980-2006": {"wall": 1.15, "roof": 1.25},
    "post-2006": {"wall": 0.60, "roof": 0.50},
}

# SHGC defaults by glazing era — ASHRAE Fundamentals Handbook Ch.18
SHGC_DEFAULTS: dict[str, float] = {
    "pre-1960":  0.60,   # single glazing
    "1960-1979": 0.60,   # single glazing
    "1980-2006": 0.45,   # basic double glazing
    "post-2006": 0.35,   # low-e double glazing
}


@dataclass
class WallLayer:
    name: str           # material name from IFC
    thickness_mm: float


@dataclass
class FacadeData:
    orientation_degrees: float      # compass bearing, 0=N 90=E 180=S 270=W
    orientation_label: str          # N / NE / E / SE / S / SW / W / NW
    wall_area_m2: float
    window_area_m2: float
    wwr: float                      # window-to-wall ratio
    has_external_shading: bool      # IFC louvers / overhangs flag
    wall_u_value: float             # W/m²K
    shgc: float                     # solar heat gain coefficient
    wall_id: str
    window_ids: list = field(default_factory=list)      # GlobalIds of windows on this wall
    wall_layers: list = field(default_factory=list)     # WallLayer list, exterior→interior
    wall_thickness_mm: float = 0.0                      # overall thickness fallback


@dataclass
class RoomData:
    room_id: str
    ifc_global_id: str
    room_name: str
    room_type: str
    floor: int
    floor_elevation_m: float
    area_m2: float
    is_top_floor: bool
    has_interior_doors: bool
    facades: list[FacadeData] = field(default_factory=list)
    door_ids: list = field(default_factory=list)   # GlobalIds of doors on boundary walls


# ── Public entry point ──────────────────────────────────────────────────────────

def parse_ifc(ifc_path: str, construction_year: str) -> list[RoomData]:
    """
    Open an IFC file and return one RoomData per IfcSpace found.

    Parameters
    ----------
    ifc_path : str
        Absolute path to .ifc file.
    construction_year : str
        One of 'pre-1960' | '1960-1979' | '1980-2006' | 'post-2006'.
        Used as fallback when U-value or SHGC not found in IFC materials.
    """
    if not _IFC_AVAILABLE:
        raise RuntimeError(
            "ifcopenshell is not installed. Run: pip install ifcopenshell"
        )

    ifc = ifcopenshell.open(ifc_path)

    # [urban-fix] length-unit scale (file units → metres) for the geometry-based
    # wall-area fallback below. 1.0 for metre files; 0.001 for millimetre files.
    try:
        _unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    except Exception:
        _unit_scale = 1.0

    # ── 1. Build storey index (sorted by elevation) ─────────────────────────
    storeys = sorted(
        ifc.by_type("IfcBuildingStorey"),
        key=lambda s: float(getattr(s, "Elevation", 0.0) or 0.0),
    )
    storey_index: dict[str, int] = {s.GlobalId: i for i, s in enumerate(storeys)}
    max_storey_idx = max(storey_index.values(), default=0)

    # ── 2. Map wall GlobalId → windows hosted on it ─────────────────────────
    wall_to_windows: dict[str, list] = {}
    for window in ifc.by_type("IfcWindow"):
        for fills_rel in getattr(window, "FillsVoids", []) or []:
            if not fills_rel.is_a("IfcRelFillsElement"):
                continue
            opening = fills_rel.RelatingOpeningElement
            for void_rel in getattr(opening, "VoidsElements", []) or []:
                if void_rel.is_a("IfcRelVoidsElement"):
                    host = void_rel.RelatingBuildingElement
                    wall_to_windows.setdefault(host.GlobalId, []).append(window)

    # ── 2b. World-space XY centroids for windows + spaces ───────────────────
    # A single long wall can bound several rooms (Revit "EXTERNAL" boundary
    # flags are sometimes set for every room the wall geometrically touches,
    # not just the room directly behind a given window). Without a position
    # check, a window physically in room B gets attributed to room A too,
    # because they share the same host wall. World-space centroids (full
    # shape geometry, not the local placement matrix — IfcSpace placements
    # are often relative/zeroed in Revit exports) let us require a window be
    # near the room's own footprint before counting it as that room's.
    def _world_centroid_xy(element) -> Optional[tuple[float, float]]:
        try:
            shape = ifcopenshell.geom.create_shape(_geom_settings, element)
            verts = shape.geometry.verts
            if not verts:
                return None
            xs = verts[0::3]
            ys = verts[1::3]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
        except Exception:
            return None

    window_xy: dict[str, Optional[tuple[float, float]]] = {
        w.GlobalId: _world_centroid_xy(w) for w in ifc.by_type("IfcWindow")
    }
    space_xy: dict[str, Optional[tuple[float, float]]] = {
        s.GlobalId: _world_centroid_xy(s) for s in ifc.by_type("IfcSpace")
    }

    # ── 3. Map wall GlobalId → doors hosted on it ───────────────────────────
    walls_with_doors: set[str] = set()
    wall_to_doors: dict[str, list] = {}
    for door in ifc.by_type("IfcDoor"):
        for fills_rel in getattr(door, "FillsVoids", []) or []:
            if not fills_rel.is_a("IfcRelFillsElement"):
                continue
            opening = fills_rel.RelatingOpeningElement
            for void_rel in getattr(opening, "VoidsElements", []) or []:
                if void_rel.is_a("IfcRelVoidsElement"):
                    host_gid = void_rel.RelatingBuildingElement.GlobalId
                    walls_with_doors.add(host_gid)
                    wall_to_doors.setdefault(host_gid, []).append(door)

    # ── 4. Build per-space boundary maps ────────────────────────────────────
    #   space_gid → list of (wall_element, is_external)
    space_boundaries: dict[str, list[tuple]] = {}
    # Count how many spaces each wall borders (to infer exterior status)
    wall_space_count: dict[str, int] = {}

    for rel in ifc.by_type("IfcRelSpaceBoundary"):
        space = rel.RelatingSpace
        element = rel.RelatedBuildingElement
        if element is None or not element.is_a("IfcWall"):
            continue
        gid = space.GlobalId
        wall_gid = element.GlobalId
        wall_space_count[wall_gid] = wall_space_count.get(wall_gid, 0) + 1

        boundary_type = str(getattr(rel, "InternalOrExternalBoundary", "NOTDEFINED"))
        is_external = boundary_type == "EXTERNAL"
        space_boundaries.setdefault(gid, []).append((element, is_external, boundary_type))

    # ── 4b. Wall positions for perimeter + storey-based exterior detection ──
    wall_origins: dict[str, tuple[float, float, float]] = {}
    for wall in ifc.by_type("IfcWall"):
        try:
            m = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
            wall_origins[wall.GlobalId] = (float(m[0][3]), float(m[1][3]), float(m[2][3]))
        except Exception:
            pass

    # Window / door elevations — walls are often modelled full-height through
    # several storeys, so openings must be assigned to rooms by their own Z.
    def _element_z(el) -> Optional[float]:
        try:
            m = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)
            return float(m[2][3])
        except Exception:
            return None

    window_z: dict[str, Optional[float]] = {
        w.GlobalId: _element_z(w) for w in ifc.by_type("IfcWindow")
    }
    door_z: dict[str, Optional[float]] = {
        d.GlobalId: _element_z(d) for d in ifc.by_type("IfcDoor")
    }

    # Storey height per index (difference to next storey; fallback 3.5 m)
    _elevs = [float(getattr(s, "Elevation", 0.0) or 0.0) for s in storeys]
    storey_heights: dict[int, float] = {}
    for i in range(len(_elevs)):
        if i + 1 < len(_elevs) and _elevs[i + 1] > _elevs[i]:
            storey_heights[i] = _elevs[i + 1] - _elevs[i]
        else:
            storey_heights[i] = 3.5

    def _on_storey(gid: str, zmap: dict, elev: float, height: float) -> bool:
        z = zmap.get(gid)
        if z is None:
            return True  # no geometry info — keep rather than lose the opening
        return (elev - 0.5) <= z < (elev + height - 0.3)

    def _near_room(
        window_gid: str,
        win_xy: Optional[tuple],
        room_xy: Optional[tuple],
        radius_m: float,
    ) -> bool:
        """
        True if window_gid's world-space centroid lies within radius_m of
        the room's centroid. Missing geometry on either side keeps the
        window (fails open) rather than silently dropping real windows.
        """
        wxy = win_xy
        if wxy is None or room_xy is None:
            return True
        dx = wxy[0] - room_xy[0]
        dy = wxy[1] - room_xy[1]
        return (dx * dx + dy * dy) ** 0.5 <= radius_m

    if wall_origins:
        xs = [p[0] for p in wall_origins.values()]
        ys = [p[1] for p in wall_origins.values()]
        plan_bounds = (min(xs), min(ys), max(xs), max(ys))
        plan_centroid = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    else:
        plan_bounds = None
        plan_centroid = None

    # ── 5. Iterate IfcSpace → build RoomData ────────────────────────────────
    rooms: list[RoomData] = []

    for space in ifc.by_type("IfcSpace"):
        gid = space.GlobalId
        name = str(
            getattr(space, "LongName", None) or getattr(space, "Name", None) or gid
        )
        obj_type = str(getattr(space, "ObjectType", "") or "").lower()
        room_type = _infer_room_type(name, obj_type)

        floor_idx, floor_elev = _get_floor_level(space, storey_index, storeys)
        is_top = floor_idx == max_storey_idx
        area_m2 = _get_space_area(space)

        # Determine which walls bound this space and whether they are exterior
        boundary_walls = space_boundaries.get(gid, [])

        # Fallback: if no IfcRelSpaceBoundary found for this space,
        # check IfcRelContainedInSpatialStructure — the space itself may enumerate walls
        if not boundary_walls:
            for rel in getattr(space, "ContainsElements", []) or []:
                if rel.is_a("IfcRelContainedInSpatialStructure"):
                    for el in rel.RelatedElements:
                        if el.is_a("IfcWall"):
                            boundary_walls.append((el, True, "ASSUMED_EXTERIOR"))

        has_interior_doors = _room_has_interior_doors(boundary_walls, walls_with_doors)

        # Door GlobalIds on this room's boundary walls (for ventilation path viz)
        # — only doors at this room's storey elevation
        _storey_h = storey_heights.get(floor_idx, 3.5)
        door_ids: list[str] = []
        _seen_doors: set[str] = set()
        for bwall, _, _ in boundary_walls:
            for d in wall_to_doors.get(bwall.GlobalId, []):
                if d.GlobalId in _seen_doors:
                    continue
                if not _on_storey(d.GlobalId, door_z, floor_elev, _storey_h):
                    continue
                _seen_doors.add(d.GlobalId)
                door_ids.append(d.GlobalId)

        # Determine exterior walls
        exterior_walls, boundaries_explicit = _select_exterior_walls(
            boundary_walls, wall_space_count, wall_origins, plan_bounds
        )

        # Deduplicate by wall GlobalId — a single physical wall can appear as
        # multiple IfcRelSpaceBoundary entries (Revit sometimes splits one
        # wall's boundary into several segments). Without this, the same
        # south-facing wall would produce several FacadeData entries: one
        # genuinely carrying its windows, and duplicates with window_ids=[]
        # — which then score 0 solar gain (gain ∝ window area) and get
        # silently dropped by any orientation/solar-score filter downstream,
        # even though they're the same physical façade as the windowed one.
        seen_wall_ids: set[str] = set()
        deduped_exterior_walls = []
        for wall in exterior_walls:
            if wall.GlobalId in seen_wall_ids:
                continue
            seen_wall_ids.add(wall.GlobalId)
            deduped_exterior_walls.append(wall)

        facades: list[FacadeData] = []
        for wall in deduped_exterior_walls:
            wo = wall_origins.get(wall.GlobalId)
            # Heuristic mode: wall must belong to this room's storey — walls
            # of other floors share the same plan position and would donate
            # their windows to the wrong room. Skipped when EXTERNAL is
            # explicit: full-height walls are often modelled once (at the
            # ground-floor storey's Z) and legitimately serve every floor
            # they pass through, so storey-Z is not a valid exterior/interior
            # signal once the IFC has already told us this wall is external.
            if not boundaries_explicit and wo is not None and abs(wo[2] - floor_elev) > 1.8:
                continue
            orientation = _wall_orientation(wall, wo, plan_centroid)
            if boundaries_explicit:
                # An explicit EXTERNAL flag is trustworthy in the vast
                # majority of cases, but Revit/IFC exports sometimes
                # mis-tag an interior partition wall as EXTERNAL. Catch
                # that specific failure mode with a direction-agnostic
                # perimeter check (near ANY plan edge) rather than the
                # heuristic path's stricter "near the edge matching this
                # wall's own orientation" check — the latter is too strict
                # here because orientation can be ambiguous/noisy for
                # walls that are valid but not axis-aligned with the
                # simple plan bbox (e.g. walls near a corner), and
                # wrongly rejecting a real facade is worse than missing
                # the rare genuinely-interior mistagged wall.
                if not _near_perimeter(wall.GlobalId, wall_origins, plan_bounds):
                    continue
            else:
                # Heuristic mode: wall must sit on the plan edge it faces
                # (drops interior partitions misread as facades)
                if not _on_matching_edge(
                    wall.GlobalId, orientation, wall_origins, plan_bounds
                ):
                    continue
            wall_area = _wall_area(wall, _unit_scale)  # [urban-fix] pass unit scale
            if wall_area <= 0.0:
                continue  # cannot use zero-area walls

            # Only windows at this room's storey — full-height walls host
            # openings of several floors. Also only windows actually near
            # THIS room's footprint — a single wall can bound several rooms
            # (Revit "EXTERNAL" boundary flags are sometimes set for every
            # room a long wall geometrically touches), so without this a
            # window physically inside a neighbouring room would be
            # attributed here too just for sharing the same host wall.
            room_xy = space_xy.get(gid)
            room_radius = max((area_m2 ** 0.5) * 1.5, 4.0)  # generous: room "radius" + margin
            windows = [
                w for w in wall_to_windows.get(wall.GlobalId, [])
                if _on_storey(w.GlobalId, window_z, floor_elev, _storey_h)
                and _near_room(w.GlobalId, window_xy.get(w.GlobalId), room_xy, room_radius)
            ]
            window_area = sum(_window_area(w) for w in windows)
            window_area = min(window_area, wall_area)
            wwr = round(window_area / wall_area, 3) if wall_area > 0 else 0.0

            u_val = _wall_u_value(wall, construction_year)
            shgc = SHGC_DEFAULTS.get(construction_year, 0.6)
            has_shading = _has_external_shading(wall, ifc)

            layers, thickness_mm = _wall_layers(wall, construction_year)
            window_ids = [w.GlobalId for w in windows]

            facades.append(FacadeData(
                orientation_degrees=round(orientation, 1),
                orientation_label=_compass_label(orientation),
                wall_area_m2=round(wall_area, 2),
                window_area_m2=round(window_area, 2),
                wwr=wwr,
                has_external_shading=has_shading,
                wall_u_value=u_val,
                shgc=shgc,
                wall_id=wall.GlobalId,
                window_ids=window_ids,
                wall_layers=layers,
                wall_thickness_mm=round(thickness_mm, 1),
            ))

        rooms.append(RoomData(
            # Use the LAST 8 chars: Revit GlobalIds share a common prefix
            # (derived from the project GUID) and only differ at the end.
            room_id=f"R_{gid[-8:]}",
            ifc_global_id=gid,
            room_name=name,
            room_type=room_type,
            floor=floor_idx,
            floor_elevation_m=round(floor_elev, 2),
            area_m2=round(area_m2, 2),
            is_top_floor=is_top,
            has_interior_doors=has_interior_doors,
            facades=facades,
            door_ids=door_ids,
        ))

    # Re-derive top-floor flag from the highest storey that actually contains
    # rooms — models often have an empty roof storey above the last occupied
    # floor, which would otherwise make no room count as top-floor.
    if rooms:
        max_occupied = max(r.floor for r in rooms)
        for r in rooms:
            r.is_top_floor = r.floor == max_occupied

    return rooms


def get_roof_element_ids(ifc_path: str) -> list[str]:
    """
    GlobalIds of roof elements, for 3D highlighting of roof strategies.
    Priority: IfcRoof entities, then IfcSlab with PredefinedType ROOF,
    then (fallback) the highest-placed slabs in the model.
    """
    if not _IFC_AVAILABLE:
        return []
    try:
        ifc = ifcopenshell.open(ifc_path)
    except Exception:
        return []

    ids: list[str] = [r.GlobalId for r in ifc.by_type("IfcRoof")]

    slabs = ifc.by_type("IfcSlab")
    for s in slabs:
        if str(getattr(s, "PredefinedType", "")) == "ROOF":
            ids.append(s.GlobalId)

    if ids:
        return list(dict.fromkeys(ids))

    # Fallback: slabs at the highest elevation (flat-roof models often export
    # the roof as a plain floor slab)
    slab_z: list[tuple[float, str]] = []
    for s in slabs:
        try:
            m = ifcopenshell.util.placement.get_local_placement(s.ObjectPlacement)
            slab_z.append((float(m[2][3]), s.GlobalId))
        except Exception:
            pass
    if not slab_z:
        return []
    zs = [z for z, _ in slab_z]
    z_max, z_min = max(zs), min(zs)
    tol = max((z_max - z_min) * 0.05, 0.3)
    return [gid for z, gid in slab_z if z >= z_max - tol]


# ── Internal helpers ────────────────────────────────────────────────────────────

def _wall_orientation(wall, origin=None, centroid=None) -> float:
    """
    Compute compass bearing (0=N, 90=E, 180=S, 270=W) of the wall's outward face.
    Extracts the Y-axis normal from the wall placement matrix.

    The placement Y-axis flips depending on the direction the wall was drawn
    in Revit, so when the wall position and plan centroid are known the normal
    is disambiguated to point AWAY from the building centre (exterior face).

    SOURCE: HVRA_build_reference_4.md §Stage 1 — IFC wall placement matrix.
    """
    try:
        matrix = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
        # Wall local Y-axis = wall normal direction in world XY plane
        normal = np.array([-matrix[1][0], -matrix[1][1]])
        if origin is not None and centroid is not None:
            outward = np.array([origin[0] - centroid[0], origin[1] - centroid[1]])
            if np.linalg.norm(outward) > 1e-6 and float(np.dot(normal, outward)) < 0:
                normal = -normal
        angle = float(np.degrees(np.arctan2(normal[0], normal[1])) % 360)
        return angle
    except Exception:
        return 180.0  # default South if matrix unavailable


def _wall_area(wall, unit_scale: float = 1.0) -> float:
    """Try IfcQuantityArea (Net > Gross); fall back to wall geometry.

    [urban-fix] Many IFC exports (e.g. the buildingSMART Duplex model, most
    Revit/ArchiCAD outputs without base quantities) carry NO IfcElementQuantity,
    so the quantity path returned 0.0 and every façade was dropped downstream
    (caller: `if wall_area <= 0: continue`). When no quantity exists, estimate
    the façade area from the wall's bounding box: largest horizontal extent ×
    height, converted to m² via the file's length-unit scale.
    """
    for rel in getattr(wall, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not pset.is_a("IfcElementQuantity"):
            continue
        net = gross = None
        for q in pset.Quantities:
            if not q.is_a("IfcQuantityArea"):
                continue
            name_lower = q.Name.lower()
            if "net" in name_lower:
                net = float(q.AreaValue)
            elif "gross" in name_lower or net is None:
                gross = float(q.AreaValue)
        val = net if net is not None else gross
        if val is not None and val > 0:
            return val

    # [urban-fix] geometry fallback — façade area ≈ horizontal extent × height.
    if _geom_settings is not None:
        try:
            shape = ifcopenshell.geom.create_shape(_geom_settings, wall)
            v = shape.geometry.verts  # flat [x,y,z, x,y,z, ...] in file units
            xs = v[0::3]
            ys = v[1::3]
            zs = v[2::3]
            length = max(max(xs) - min(xs), max(ys) - min(ys))
            height = max(zs) - min(zs)
            area = length * height * (unit_scale ** 2)
            if 0.0 < area < 100000.0:  # sanity clamp
                return round(area, 2)
        except Exception:
            pass
    return 0.0


def _window_area(window) -> float:
    """OverallWidth × OverallHeight, or IfcQuantityArea fallback."""
    w = getattr(window, "OverallWidth", None)
    h = getattr(window, "OverallHeight", None)
    if w and h:
        return float(w) * float(h)
    for rel in getattr(window, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if pset.is_a("IfcElementQuantity"):
            for q in pset.Quantities:
                if q.is_a("IfcQuantityArea"):
                    return float(q.AreaValue)
    return 0.0


def _wall_u_value(wall, era: str) -> float:
    """
    Try to read U-value from IFC property sets first.
    Falls back to era lookup table.
    SOURCE: CTE DB-HE + IVE typology database (era lookup).
    """
    for rel in getattr(wall, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not pset.is_a("IfcPropertySet"):
            continue
        for prop in getattr(pset, "HasProperties", []) or []:
            if not hasattr(prop, "NominalValue"):
                continue
            name = (prop.Name or "").lower()
            if any(k in name for k in ("u-value", "u_value", "thermaltr", "u value")):
                try:
                    val = float(prop.NominalValue.wrappedValue)
                    if 0.1 < val < 5.0:  # sanity check W/m²K
                        return round(val, 3)
                except (TypeError, AttributeError, ValueError):
                    pass
    return U_VALUE_DEFAULTS.get(era, U_VALUE_DEFAULTS["pre-1960"])["wall"]


def _get_space_area(space) -> float:
    """Extract net floor area (m²) from IfcElementQuantity."""
    for rel in getattr(space, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not pset.is_a("IfcElementQuantity"):
            continue
        for q in pset.Quantities:
            if q.is_a("IfcQuantityArea") and "net" in q.Name.lower():
                return float(q.AreaValue)
        for q in pset.Quantities:
            if q.is_a("IfcQuantityArea"):
                return float(q.AreaValue)
    return 0.0


def _get_floor_level(
    space, storey_index: dict[str, int], storeys: list
) -> tuple[int, float]:
    """Walk Decomposes relations to find the parent IfcBuildingStorey."""
    for rel in getattr(space, "Decomposes", []) or []:
        if not rel.is_a("IfcRelAggregates"):
            continue
        parent = rel.RelatingObject
        if parent.is_a("IfcBuildingStorey"):
            idx = storey_index.get(parent.GlobalId, 0)
            elev = float(getattr(parent, "Elevation", 0.0) or 0.0)
            return idx, elev
    return 0, 0.0


def _near_perimeter(
    gid: str,
    wall_origins: dict[str, tuple[float, float]],
    plan_bounds: Optional[tuple],
) -> bool:
    """
    True if the wall's plan position lies close to the building's plan outline.
    Tolerance is relative to building size so it works in mm or m projects.
    Walls without geometry data are not excluded (returns True).
    """
    if not plan_bounds or gid not in wall_origins:
        return True
    x, y = wall_origins[gid][0], wall_origins[gid][1]
    minx, miny, maxx, maxy = plan_bounds
    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        return True
    tol = span * 0.06
    return (
        abs(x - minx) < tol or abs(x - maxx) < tol
        or abs(y - miny) < tol or abs(y - maxy) < tol
    )


def _select_exterior_walls(
    boundary_walls: list[tuple],
    wall_space_count: dict[str, int],
    wall_origins: dict[str, tuple[float, float]],
    plan_bounds: Optional[tuple],
) -> tuple[list, bool]:
    """
    Return (walls, explicit) — exterior walls and whether they came from
    explicit EXTERNAL space-boundary flags (trustworthy) or the heuristic.

    Priority:
      1. Explicitly marked EXTERNAL in IfcRelSpaceBoundary.
      2. Heuristic: borders only one space AND not marked INTERNAL
         AND sits near the building's plan perimeter. The caller applies a
         further direction-vs-edge check per wall.
    """
    explicit_exterior = [
        wall for wall, is_ext, btype in boundary_walls if is_ext
    ]
    if explicit_exterior:
        return explicit_exterior, True

    # Heuristic candidates: border one space, not explicitly internal
    candidates = [
        wall
        for wall, _, btype in boundary_walls
        if btype != "INTERNAL" and wall_space_count.get(wall.GlobalId, 1) == 1
    ]
    if not candidates:
        candidates = [w for w, _, btype in boundary_walls if btype != "INTERNAL"]
    if not candidates:
        candidates = [w for w, _, _ in boundary_walls]

    # Keep only walls near the plan outline (drops interior partitions that
    # merely border an unmodelled space like a shaft or corridor)
    near = [w for w in candidates if _near_perimeter(w.GlobalId, wall_origins, plan_bounds)]
    return (near if near else candidates), False


def _on_matching_edge(
    gid: str,
    bearing: float,
    wall_origins: dict[str, tuple[float, float]],
    plan_bounds: Optional[tuple],
) -> bool:
    """
    True if the wall sits near the plan edge its outward normal points to —
    a real south facade lies on the south edge of the plan. Interior
    partitions that merely touch the perimeter at one end fail this test.
    """
    if not plan_bounds or gid not in wall_origins:
        return True
    x, y = wall_origins[gid][0], wall_origins[gid][1]
    minx, miny, maxx, maxy = plan_bounds
    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        return True
    tol = span * 0.08
    near = {
        "N": abs(y - maxy) < tol,
        "S": abs(y - miny) < tol,
        "E": abs(x - maxx) < tol,
        "W": abs(x - minx) < tol,
    }
    required = {
        "N": ["N"], "S": ["S"], "E": ["E"], "W": ["W"],
        "NE": ["N", "E"], "SE": ["S", "E"], "SW": ["S", "W"], "NW": ["N", "W"],
    }[_compass_label(bearing)]
    return any(near[r] for r in required)


def _room_has_interior_doors(
    boundary_walls: list[tuple],
    walls_with_doors: set[str],
) -> bool:
    """True if any wall bounding this space has an IfcDoor hosted on it."""
    return any(
        wall.GlobalId in walls_with_doors for wall, _, _ in boundary_walls
    )


def _has_external_shading(wall, ifc) -> bool:
    """Check IFC for louver / overhang / brise-soleil elements near this wall."""
    shading_keywords = ("shade", "shad", "louver", "brise", "overhang", "pergola", "jalousie")
    # IfcShadingDevice only exists in IFC4+ — skip types missing from the schema
    for shade_type in ("IfcShadingDevice", "IfcBuildingElementProxy", "IfcRoof"):
        try:
            elements = ifc.by_type(shade_type)
        except Exception:
            continue
        for el in elements:
            name = (getattr(el, "Name", "") or "").lower()
            if any(k in name for k in shading_keywords):
                return True
    return False


def _infer_room_type(name: str, obj_type: str) -> str:
    """Classify room type from name / objectType string."""
    combined = (name + " " + obj_type).lower()
    mapping = [
        (("bed", "sleep", "dormit", "habi"), "bedroom"),
        (("living", "salon", "lounge", "sala"), "living_room"),
        (("kitchen", "cocina", "cuina"), "kitchen"),
        (("bath", "wc", "toilet", "baño", "bany"), "bathroom"),
        (("corridor", "hall", "pasillo", "passad"), "corridor"),
        (("office", "study", "desp"), "office"),
    ]
    for keywords, rtype in mapping:
        if any(k in combined for k in keywords):
            return rtype
    return "room"


# Era-based wall layer defaults for Barcelona/Mediterranean typology
# Ordered exterior → interior. Thicknesses in mm.
_ERA_WALL_LAYERS: dict[str, list[dict]] = {
    "pre-1960": [
        {"name": "Lime render",        "thickness_mm": 15},
        {"name": "Solid brick",        "thickness_mm": 290},
        {"name": "Lime plaster",       "thickness_mm": 15},
    ],
    "1960-1979": [
        {"name": "Cement render",      "thickness_mm": 15},
        {"name": "Perforated brick",   "thickness_mm": 115},
        {"name": "Air gap",            "thickness_mm": 50},
        {"name": "Perforated brick",   "thickness_mm": 70},
        {"name": "Gypsum plaster",     "thickness_mm": 15},
    ],
    "1980-2006": [
        {"name": "Cement render",      "thickness_mm": 15},
        {"name": "Perforated brick",   "thickness_mm": 115},
        {"name": "Mineral wool",       "thickness_mm": 40},
        {"name": "Perforated brick",   "thickness_mm": 70},
        {"name": "Gypsum plaster",     "thickness_mm": 15},
    ],
    "post-2006": [
        {"name": "Cement render",      "thickness_mm": 15},
        {"name": "Perforated brick",   "thickness_mm": 115},
        {"name": "Mineral wool",       "thickness_mm": 60},
        {"name": "Perforated brick",   "thickness_mm": 70},
        {"name": "Gypsum plaster",     "thickness_mm": 15},
    ],
}


def _wall_layers(wall, era: str) -> tuple[list[WallLayer], float]:
    """
    Extract wall layer composition from IfcMaterialLayerSet/IfcMaterialLayerSetUsage.
    Falls back to overall thickness from IfcElementQuantity or extrusion geometry.
    Falls back to era-based Barcelona typology defaults if no IFC data available.

    Returns (layers, total_thickness_mm).
    Layers are ordered exterior → interior.
    """
    # ── Try IfcMaterialLayerSet ────────────────────────────────────────────
    for rel in getattr(wall, "HasAssociations", []) or []:
        if not rel.is_a("IfcRelAssociatesMaterial"):
            continue
        mat = rel.RelatingMaterial
        layer_set = None
        if mat.is_a("IfcMaterialLayerSet"):
            layer_set = mat
        elif mat.is_a("IfcMaterialLayerSetUsage"):
            layer_set = mat.ForLayerSet
        if layer_set is None:
            continue
        layers_raw = getattr(layer_set, "MaterialLayers", []) or []
        if not layers_raw:
            continue
        layers = []
        for lyr in layers_raw:
            mat_name = "Unknown"
            if hasattr(lyr, "Material") and lyr.Material:
                mat_name = str(getattr(lyr.Material, "Name", "Unknown") or "Unknown")
            t = float(getattr(lyr, "LayerThickness", 0.0) or 0.0)
            # IFC thickness is in model units — usually mm, occasionally m
            if t > 0 and t < 1.0:
                t *= 1000  # convert m → mm
            layers.append(WallLayer(name=mat_name, thickness_mm=round(t, 1)))
        if layers:
            total = sum(l.thickness_mm for l in layers)
            return layers, total

    # ── Try overall thickness from IfcElementQuantity ─────────────────────
    for rel in getattr(wall, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not pset.is_a("IfcElementQuantity"):
            continue
        for q in pset.Quantities:
            name_lower = (q.Name or "").lower()
            if q.is_a("IfcQuantityLength") and any(
                k in name_lower for k in ("width", "thickness", "depth")
            ):
                t = float(q.LengthValue or 0.0)
                if 0 < t < 2.0:
                    t *= 1000  # m → mm
                if t > 0:
                    layers = _era_layers_scaled_to(era, t)
                    return layers, t

    # ── Try extrusion profile geometry (IfcRectangleProfileDef.YDim) ──────
    try:
        rep = getattr(wall, "Representation", None)
        if rep:
            for shape in rep.Representations or []:
                for item in shape.Items or []:
                    if item.is_a("IfcExtrudedAreaSolid"):
                        profile = item.SweptArea
                        if profile.is_a("IfcRectangleProfileDef"):
                            t = float(getattr(profile, "YDim", 0.0) or 0.0)
                            if 0 < t < 2.0:
                                t *= 1000  # m → mm
                            if t > 0:
                                layers = _era_layers_scaled_to(era, t)
                                return layers, t
    except Exception:
        pass

    # ── Era default fallback ───────────────────────────────────────────────
    default = _ERA_WALL_LAYERS.get(era, _ERA_WALL_LAYERS["pre-1960"])
    layers = [WallLayer(name=d["name"], thickness_mm=d["thickness_mm"]) for d in default]
    total = sum(l.thickness_mm for l in layers)
    return layers, total


def _era_layers_scaled_to(era: str, target_mm: float) -> list[WallLayer]:
    """Scale era-default layers proportionally to match a known total thickness."""
    default = _ERA_WALL_LAYERS.get(era, _ERA_WALL_LAYERS["pre-1960"])
    default_total = sum(d["thickness_mm"] for d in default)
    if default_total <= 0:
        return [WallLayer(name="Wall", thickness_mm=target_mm)]
    scale = target_mm / default_total
    return [
        WallLayer(name=d["name"], thickness_mm=round(d["thickness_mm"] * scale, 1))
        for d in default
    ]


def _compass_label(degrees: float) -> str:
    """Convert compass bearing to 8-point label."""
    octants = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return octants[int((degrees + 22.5) / 45) % 8]
