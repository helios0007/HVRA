"""
Cross-ventilation diagnosis — architect-facing evaluation overlay.

Rebuilt from scratch per explicit spec (see project notes). Does NOT modify
IFC geometry. Produces a JSON-serialisable diagnosis per room plus an
airflow-path polyline for visualisation, built in layers:

  1. Parse IfcSpace objects (id, name, level, centroid, footprint).
  2. Parse walls, classify exterior vs interior, compute orientation.
  3. Parse openings (windows/doors), link to host wall + space(s),
     classify exterior vs interior connection.
  4. Build a space connectivity graph: edges only via real door/opening
     centroids — never inferred from wall adjacency alone.
  5. Classify each room's DIRECT ventilation potential from its own
     exterior openings (single-sided / weak / moderate / strong / poor).
  6. For rooms without strong/moderate direct cross-ventilation, search the
     connectivity graph (depth ≤ 3) for an indirect path to a room with a
     differently-oriented exterior opening, penalising length and turns.
  7. Build an airflow-path polyline for each room that never cuts through a
     wall without a registered opening at that point — paths are built from
     real opening/room centroids only (graph edges), not straight lines
     between arbitrary points.
  8. Generate deterministic recommendations for poor/single-sided rooms.
  9. Return one CrossVentResult per room, matching the agreed JSON schema.
 10. Every classification is logged with its reasoning; missing geometry
     degrades to "unknown" / low confidence rather than fabricating a result.

SOURCE: EN 15242 — natural ventilation calculation methods.
SOURCE: Givoni (1992); Allard (1998) — cross-ventilation angle thresholds.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import ifcopenshell
    import ifcopenshell.util.placement
    import ifcopenshell.geom
    _IFC_AVAILABLE = True
    _geom_settings = ifcopenshell.geom.settings()
    _geom_settings.set(_geom_settings.USE_WORLD_COORDS, True)
except ImportError:
    _IFC_AVAILABLE = False
    _geom_settings = None


# ── Classification thresholds ──────────────────────────────────────────────
# SOURCE: Givoni (1992), Comfort, climate analysis and building design
#         guidelines — opening angle vs. cross-ventilation effectiveness.
# SOURCE: Allard (1998), Natural Ventilation in Buildings.
ANGLE_SINGLE_FACADE_MAX = 30.0     # 0–30°  same/near-same wall → single-sided
ANGLE_WEAK_MAX          = 75.0     # 30–75° → weak adjacent ventilation
ANGLE_MODERATE_MAX      = 135.0    # 75–135° → moderate cross-ventilation
# 135–180° → strong cross-ventilation

MAX_INDIRECT_DEPTH = 3             # max rooms traversed for indirect search
SAME_WALL_TOLERANCE_DEG = 5.0      # openings within this bearing diff = same wall direction


# ── Output dataclasses (mirror the agreed JSON schema) ──────────────────────

@dataclass
class OpeningInfo:
    id: str
    type: str                      # "window" | "door" | "opening"
    host_wall_id: Optional[str]
    space_ids: list[str] = field(default_factory=list)
    centroid: tuple[float, float, float] = (0.0, 0.0, 0.0)
    area_m2: float = 0.0
    orientation_deg: Optional[float] = None    # None for interior doors (no facade normal)
    is_exterior: bool = False
    operable_assumed: bool = False             # True if operability was assumed, not read from IFC

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "host_wall_id": self.host_wall_id,
            "space_ids": self.space_ids,
            "centroid": list(self.centroid),
            "area_m2": round(self.area_m2, 2),
            "orientation_deg": self.orientation_deg,
            "is_exterior": self.is_exterior,
            "operable_assumed": self.operable_assumed,
        }


@dataclass
class SpaceInfo:
    id: str
    name: str
    level: int
    centroid: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox: Optional[tuple[float, float, float, float]] = None   # (minx, miny, maxx, maxy)


@dataclass
class CrossVentResult:
    space_id: str
    space_name: str
    classification: str            # see CLASSIFICATIONS below
    confidence: float               # 0.0–1.0
    exterior_openings: list[dict] = field(default_factory=list)
    internal_connections: list[dict] = field(default_factory=list)
    airflow_path: list[list[float]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)   # debug log, why this classification

    def to_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "space_name": self.space_name,
            "classification": self.classification,
            "confidence": round(self.confidence, 2),
            "exterior_openings": self.exterior_openings,
            "internal_connections": self.internal_connections,
            "airflow_path": self.airflow_path,
            "assumptions": self.assumptions,
            "recommendations": self.recommendations,
            "reasoning": self.reasoning,
        }


CLASSIFICATIONS = {
    "strong_cross_ventilation",
    "moderate_cross_ventilation",
    "weak_adjacent_ventilation",
    "single_sided",
    "indirect_possible",
    "poor",
    "unknown",
}


# ── Public entry point ──────────────────────────────────────────────────────

def analyze_cross_ventilation(ifc_path: str) -> dict:
    """
    Run the full cross-ventilation diagnosis on an IFC file.
    Returns {"spaces": [CrossVentResult.to_dict(), ...]}.

    Never raises on missing/malformed IFC data for individual rooms — a room
    that cannot be analysed gets classification="unknown" with confidence 0
    and a reasoning note, rather than aborting the whole building.
    """
    if not _IFC_AVAILABLE:
        logger.error("ifcopenshell not available — cross-ventilation analysis skipped")
        return {"spaces": []}

    try:
        ifc = ifcopenshell.open(ifc_path)
    except Exception as exc:
        logger.error("Failed to open IFC for cross-ventilation analysis: %s", exc)
        return {"spaces": []}

    # ── Layer 1: spaces ──────────────────────────────────────────────────
    spaces = _parse_spaces(ifc)
    logger.info("Cross-vent: parsed %d spaces", len(spaces))

    # ── Layer 2: walls (exterior/interior + orientation) ────────────────
    wall_info = _parse_walls(ifc, spaces)
    logger.info("Cross-vent: parsed %d walls (%d exterior)",
                len(wall_info), sum(1 for w in wall_info.values() if w["is_exterior"]))

    # ── Layer 3: openings ────────────────────────────────────────────────
    openings = _parse_openings(ifc, wall_info, spaces)
    logger.info("Cross-vent: parsed %d openings (%d exterior, %d interior-connecting)",
                len(openings),
                sum(1 for o in openings.values() if o.is_exterior),
                sum(1 for o in openings.values() if not o.is_exterior and len(o.space_ids) == 2))

    # ── Layer 4: connectivity graph ──────────────────────────────────────
    graph = _build_connectivity_graph(openings)

    wall_segments = [w["segment_xy"] for w in wall_info.values() if w["segment_xy"]]

    # ── Layers 5–8: per-room classification + paths + recommendations ───
    results: list[CrossVentResult] = []
    for space_id, space in spaces.items():
        result = _classify_space(space, spaces, openings, graph, wall_segments)
        results.append(result)
        logger.info(
            "Cross-vent: room '%s' (%s) → %s (confidence=%.2f) — %s",
            space.name, space_id, result.classification, result.confidence,
            "; ".join(result.reasoning) if result.reasoning else "no reasoning recorded",
        )

    return {"spaces": [r.to_dict() for r in results]}


# ── Layer 1: spaces ───────────────────────────────────────────────────────

def _parse_spaces(ifc) -> dict[str, SpaceInfo]:
    spaces: dict[str, SpaceInfo] = {}
    storeys = sorted(
        ifc.by_type("IfcBuildingStorey"),
        key=lambda s: float(getattr(s, "Elevation", 0.0) or 0.0),
    )
    storey_index = {s.GlobalId: i for i, s in enumerate(storeys)}

    for space in ifc.by_type("IfcSpace"):
        gid = space.GlobalId
        name = str(getattr(space, "LongName", None) or getattr(space, "Name", None) or gid)

        level = 0
        for rel in getattr(space, "Decomposes", []) or []:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                level = storey_index.get(rel.RelatingObject.GlobalId, 0)
                break

        centroid, bbox = _world_centroid_and_bbox(space)
        spaces[gid] = SpaceInfo(id=gid, name=name, level=level,
                                 centroid=centroid or (0.0, 0.0, 0.0), bbox=bbox)
    return spaces


def _world_centroid_and_bbox(element):
    """Full-geometry world-space centroid + XY bbox. None if extraction fails."""
    try:
        shape = ifcopenshell.geom.create_shape(_geom_settings, element)
        verts = shape.geometry.verts
        if not verts:
            return None, None
        xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
        centroid = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        bbox = (min(xs), min(ys), max(xs), max(ys))
        return centroid, bbox
    except Exception:
        return None, None


# ── Layer 2: walls ────────────────────────────────────────────────────────

def _parse_walls(ifc, spaces: dict[str, SpaceInfo]) -> dict[str, dict]:
    """
    Returns wall_gid -> {
        is_exterior, orientation_deg, bound_space_ids, segment_xy
    }
    segment_xy: ((x1,y1), (x2,y2)) — the wall's plan footprint, used for the
    "does this path cross a wall" check in path-building.
    """
    wall_types = ("IfcWall", "IfcWallStandardCase")
    walls = []
    for wt in wall_types:
        walls.extend(ifc.by_type(wt))
    walls = list({w.GlobalId: w for w in walls}.values())  # dedupe by GlobalId

    # Space boundaries from IfcRelSpaceBoundary — primary source for
    # exterior/interior classification.
    wall_space_count: dict[str, int] = {}
    wall_bound_spaces: dict[str, list[tuple[str, bool]]] = {}
    for rel in ifc.by_type("IfcRelSpaceBoundary"):
        element = rel.RelatedBuildingElement
        if element is None or not (element.is_a("IfcWall") or element.is_a("IfcWallStandardCase")):
            continue
        wgid = element.GlobalId
        sgid = rel.RelatingSpace.GlobalId
        boundary_type = str(getattr(rel, "InternalOrExternalBoundary", "NOTDEFINED"))
        is_ext = boundary_type == "EXTERNAL"
        wall_space_count[wgid] = wall_space_count.get(wgid, 0) + 1
        wall_bound_spaces.setdefault(wgid, []).append((sgid, is_ext))

    # Plan footprint for the building (for perimeter fallback)
    wall_origins: dict[str, tuple[float, float, float]] = {}
    for wall in walls:
        try:
            m = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
            wall_origins[wall.GlobalId] = (float(m[0][3]), float(m[1][3]), float(m[2][3]))
        except Exception:
            pass
    if wall_origins:
        xs = [p[0] for p in wall_origins.values()]
        ys = [p[1] for p in wall_origins.values()]
        plan_bounds = (min(xs), min(ys), max(xs), max(ys))
    else:
        plan_bounds = None

    result: dict[str, dict] = {}
    for wall in walls:
        gid = wall.GlobalId
        boundary_entries = wall_bound_spaces.get(gid, [])

        if boundary_entries:
            is_exterior = any(is_ext for _, is_ext in boundary_entries)
            bound_space_ids = [sid for sid, _ in boundary_entries]
            confident = True
        else:
            # Geometric fallback: wall borders ≤1 space (or none recorded)
            # AND sits near the building's plan perimeter.
            is_exterior = wall_space_count.get(gid, 0) <= 1 and _near_perimeter(
                wall_origins.get(gid), plan_bounds
            )
            bound_space_ids = []
            confident = False

        orientation = _wall_orientation_world(wall, wall_origins.get(gid), plan_bounds)
        segment_xy = _wall_segment_xy(wall)

        result[gid] = {
            "is_exterior": is_exterior,
            "orientation_deg": orientation,
            "bound_space_ids": bound_space_ids,
            "segment_xy": segment_xy,
            "confident": confident,
        }
    return result


def _near_perimeter(origin, plan_bounds, tol_frac=0.06) -> bool:
    if origin is None or plan_bounds is None:
        return True
    x, y, _ = origin
    minx, miny, maxx, maxy = plan_bounds
    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        return True
    tol = span * tol_frac
    return abs(x - minx) < tol or abs(x - maxx) < tol or abs(y - miny) < tol or abs(y - maxy) < tol


def _wall_orientation_world(wall, origin, plan_bounds) -> Optional[float]:
    """Compass bearing of the wall's outward normal (0=N,90=E,180=S,270=W)."""
    try:
        m = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
        normal = (-m[1][0], -m[1][1])
        if origin is not None and plan_bounds is not None:
            cx = (plan_bounds[0] + plan_bounds[2]) / 2
            cy = (plan_bounds[1] + plan_bounds[3]) / 2
            outward = (origin[0] - cx, origin[1] - cy)
            mag = math.hypot(*outward)
            if mag > 1e-6:
                dot = normal[0] * outward[0] + normal[1] * outward[1]
                if dot < 0:
                    normal = (-normal[0], -normal[1])
        angle = math.degrees(math.atan2(normal[0], normal[1])) % 360
        return angle
    except Exception:
        return None


def _wall_segment_xy(wall):
    """
    Approximate the wall's plan footprint as a line segment (x1,y1)-(x2,y2)
    using the world-space geometry bounding box's longer axis. Used only for
    the "does an airflow path cross this wall" check — does not need to be
    exact, just a reasonable line representing the wall's run.
    """
    try:
        shape = ifcopenshell.geom.create_shape(_geom_settings, wall)
        verts = shape.geometry.verts
        if not verts:
            return None
        xs, ys = verts[0::3], verts[1::3]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        if (maxx - minx) >= (maxy - miny):
            midy = (miny + maxy) / 2
            return ((minx, midy), (maxx, midy))
        else:
            midx = (minx + maxx) / 2
            return ((midx, miny), (midx, maxy))
    except Exception:
        return None


# ── Layer 3: openings ─────────────────────────────────────────────────────

def _parse_openings(ifc, wall_info: dict[str, dict], spaces: dict[str, SpaceInfo]) -> dict[str, OpeningInfo]:
    openings: dict[str, OpeningInfo] = {}

    # Map opening element (window/door) -> host wall GlobalId, via the
    # standard IfcRelFillsElement -> IfcOpeningElement -> IfcRelVoidsElement chain.
    def _host_wall_id(element) -> Optional[str]:
        for fills_rel in getattr(element, "FillsVoids", []) or []:
            if not fills_rel.is_a("IfcRelFillsElement"):
                continue
            opening_el = fills_rel.RelatingOpeningElement
            for void_rel in getattr(opening_el, "VoidsElements", []) or []:
                if void_rel.is_a("IfcRelVoidsElement"):
                    host = void_rel.RelatingBuildingElement
                    if host is not None:
                        return host.GlobalId
        return None

    # Per-room attribution data: centroid (for XY distance), level (storey
    # index — full-height walls span several floors, so an opening at the
    # wrong elevation must never be attributed to a room on another floor),
    # and a search radius derived from the room's own footprint size. Ports
    # the same fix already proven in ifc_parser.py for this exact failure
    # mode (a wall bounding several rooms donating its windows to all of
    # them instead of just the one actually behind each window).
    space_meta: dict[str, dict] = {}
    for sid, s in spaces.items():
        if s.bbox is not None:
            w = s.bbox[2] - s.bbox[0]
            h = s.bbox[3] - s.bbox[1]
            radius = max((w * h) ** 0.5 * 0.75, 3.0)
        else:
            radius = 6.0  # no geometry — generous fallback, fails open
        space_meta[sid] = {"centroid": s.centroid, "level": s.level, "radius": radius}

    for entity_type, kind in (("IfcWindow", "window"), ("IfcDoor", "door")):
        for el in ifc.by_type(entity_type):
            gid = el.GlobalId
            host_wall = _host_wall_id(el)
            centroid, _ = _world_centroid_and_bbox(el)
            if centroid is None:
                logger.warning("Cross-vent: opening %s (%s) has no usable geometry — skipped", gid, kind)
                continue
            area = _opening_area(el)

            wmeta = wall_info.get(host_wall, {}) if host_wall else {}
            is_exterior_wall = wmeta.get("is_exterior", False)
            wall_orientation = wmeta.get("orientation_deg")
            candidate_spaces = wmeta.get("bound_space_ids", [])

            # Attribute to the space(s) whose own footprint the opening's
            # centroid actually falls near (XY distance within that room's
            # radius) — not blindly every space the host wall is recorded
            # against, and never a room on a different storey.
            near_spaces = _nearest_spaces(centroid, candidate_spaces, space_meta)

            operable_assumed = False
            if kind == "window":
                is_exterior = is_exterior_wall
                orientation = wall_orientation
                operability = getattr(el, "OperationType", None)
                if operability is None:
                    operable_assumed = True
            else:  # door
                # A door counts as "exterior" only if its host wall is
                # exterior AND it connects exactly one space to the outside
                # (not two interior spaces to each other).
                is_exterior = is_exterior_wall and len(near_spaces) <= 1
                orientation = wall_orientation if is_exterior else None

            openings[gid] = OpeningInfo(
                id=gid, type=kind, host_wall_id=host_wall,
                space_ids=near_spaces, centroid=centroid, area_m2=area,
                orientation_deg=orientation, is_exterior=is_exterior,
                operable_assumed=operable_assumed,
            )

    return openings


def _nearest_spaces(opening_centroid, candidate_space_ids, space_meta, max_count=2):
    """
    Of the spaces a wall is recorded as bounding, keep only those that are
    (a) on the same storey as the opening (within one storey height, since
    full-height walls span several floors) and (b) within that room's own
    footprint-derived radius in plan. Falls back to the single nearest
    candidate (ignoring radius) if none pass both filters, rather than
    silently dropping a real connection — but never crosses storeys.
    """
    if not candidate_space_ids:
        return []

    same_level = []
    for sid in candidate_space_ids:
        meta = space_meta.get(sid)
        if meta is None or meta["centroid"] is None:
            continue
        c = meta["centroid"]
        dz = abs(opening_centroid[2] - c[2])
        if dz > 2.2:   # opening's Z is far from this room's own elevation
            continue
        dxy = math.hypot(opening_centroid[0] - c[0], opening_centroid[1] - c[1])
        same_level.append((dxy, meta["radius"], sid))

    if not same_level:
        # No same-storey candidate had geometry — fall back to all
        # candidates rather than losing the opening entirely.
        return list(dict.fromkeys(candidate_space_ids))[:max_count]

    within_radius = [(d, sid) for d, r, sid in same_level if d <= r]
    if within_radius:
        within_radius.sort(key=lambda t: t[0])
        return [sid for _, sid in within_radius[:max_count]]

    # Nothing fell within any candidate's own radius — take the single
    # closest same-storey candidate instead of returning everything.
    same_level.sort(key=lambda t: t[0])
    return [same_level[0][2]]


def _opening_area(element) -> float:
    w = getattr(element, "OverallWidth", None)
    h = getattr(element, "OverallHeight", None)
    if w and h:
        return float(w) * float(h)
    return 0.0


# ── Layer 4: connectivity graph ──────────────────────────────────────────

def _build_connectivity_graph(openings: dict[str, OpeningInfo]) -> dict[str, list[dict]]:
    """
    Nodes = space ids (implicit). Edges = interior doors/openings connecting
    exactly two spaces. graph[space_id] = [{"to": other_space_id,
    "opening_id": ..., "centroid": (...)}, ...]

    Exterior openings and openings attributed to a single space never create
    an edge — an edge requires a real two-space connection.
    """
    graph: dict[str, list[dict]] = {}
    for op in openings.values():
        if op.is_exterior:
            continue
        if len(op.space_ids) != 2:
            continue
        a, b = op.space_ids
        graph.setdefault(a, []).append({"to": b, "opening_id": op.id, "centroid": op.centroid})
        graph.setdefault(b, []).append({"to": a, "opening_id": op.id, "centroid": op.centroid})
    return graph


# ── Layers 5–8: classification, indirect search, paths, recommendations ───

def _classify_space(
    space: SpaceInfo,
    spaces: dict[str, SpaceInfo],
    openings: dict[str, OpeningInfo],
    graph: dict[str, list[dict]],
    wall_segments: list[tuple],
) -> CrossVentResult:
    reasoning: list[str] = []
    assumptions: list[str] = []

    own_ext = [o for o in openings.values() if o.is_exterior and space.id in o.space_ids]
    own_ext_windows = [o for o in own_ext if o.type == "window"]

    for o in own_ext_windows:
        if o.operable_assumed:
            assumptions.append(
                f"Opening {o.id}: operability not specified in IFC — assumed operable."
            )

    if space.centroid is None or space.centroid == (0.0, 0.0, 0.0):
        reasoning.append("Space has no usable geometry (centroid extraction failed).")

    internal_connections = [
        {"opening_id": e["opening_id"], "connects_to_space": e["to"], "centroid": list(e["centroid"])}
        for e in graph.get(space.id, [])
    ]

    # ── §5: direct classification from own exterior openings ────────────
    if len(own_ext_windows) == 0:
        direct_class = "poor"
        direct_confidence = 0.85 if own_ext else 0.6
        reasoning.append("No exterior windows found for this room — no direct natural ventilation.")
    elif len(own_ext_windows) == 1:
        direct_class = "single_sided"
        direct_confidence = 0.8
        reasoning.append(f"Exactly one exterior window ({own_ext_windows[0].id}) — single-sided ventilation only.")
    else:
        # Compare every pair; keep the BEST (largest) angle as the room's
        # potential, but require the pair's openings to be on different
        # walls (same-wall windows must never count as cross-ventilation).
        best_angle = -1.0
        best_pair = None
        for i in range(len(own_ext_windows)):
            for j in range(i + 1, len(own_ext_windows)):
                wi, wj = own_ext_windows[i], own_ext_windows[j]
                if wi.host_wall_id is not None and wi.host_wall_id == wj.host_wall_id:
                    continue  # same physical wall — never cross-ventilation
                if wi.orientation_deg is None or wj.orientation_deg is None:
                    continue
                diff = abs(wi.orientation_deg - wj.orientation_deg) % 360
                angle = min(diff, 360 - diff)
                if angle > best_angle:
                    best_angle = angle
                    best_pair = (wi, wj)

        if best_pair is None:
            # All exterior windows are on the same wall (or orientation
            # unknown) — treat as single-sided, not cross-ventilation.
            direct_class = "single_sided"
            direct_confidence = 0.7
            reasoning.append(
                f"{len(own_ext_windows)} exterior windows found, but all on the same wall "
                "(or orientation undetermined) — treated as single-sided."
            )
        elif best_angle <= ANGLE_SINGLE_FACADE_MAX:
            direct_class = "single_sided"
            direct_confidence = 0.75
            reasoning.append(f"Best window pair angle {best_angle:.0f}° (≤{ANGLE_SINGLE_FACADE_MAX:.0f}°) — same/near-same facade.")
        elif best_angle <= ANGLE_WEAK_MAX:
            direct_class = "weak_adjacent_ventilation"
            direct_confidence = 0.65
            reasoning.append(f"Best window pair angle {best_angle:.0f}° — weak adjacent ventilation.")
        elif best_angle <= ANGLE_MODERATE_MAX:
            direct_class = "moderate_cross_ventilation"
            direct_confidence = 0.75
            reasoning.append(f"Best window pair angle {best_angle:.0f}° — moderate cross-ventilation.")
        else:
            direct_class = "strong_cross_ventilation"
            direct_confidence = 0.9
            reasoning.append(f"Best window pair angle {best_angle:.0f}° — strong cross-ventilation.")

    # ── §6: indirect search, only attempted for weaker direct results ───
    indirect_path = None
    if direct_class in ("poor", "single_sided"):
        indirect_path = _search_indirect_path(space, spaces, openings, graph)
        if indirect_path:
            reasoning.append(
                f"Indirect path found via {len(indirect_path['rooms']) - 1} hop(s) "
                f"through {indirect_path['via']} to room with exterior opening "
                f"at {indirect_path['angle']:.0f}° from this room's own opening."
            )

    if indirect_path:
        final_class = "indirect_possible"
        final_confidence = max(0.3, 0.7 - 0.15 * (len(indirect_path["rooms"]) - 2))
    else:
        final_class = direct_class
        final_confidence = direct_confidence

    # ── §7: airflow path (never crosses a wall without an opening) ──────
    airflow_path = _build_airflow_path(space, own_ext_windows, indirect_path, final_class)
    _verify_path_does_not_cross_walls(airflow_path, wall_segments, space, reasoning)

    # ── §8: recommendations ──────────────────────────────────────────────
    recommendations = _build_recommendations(
        final_class, space, own_ext_windows, openings, graph,
    )

    # Windows only — an exterior door is a building entrance/exit, not a
    # ventilation inlet/outlet, so it must never be reported here as if it
    # were an operable opening (it would otherwise get drawn in the 3D
    # overlay as a second "opening" alongside the room's real window).
    exterior_openings_out = [o.to_dict() for o in own_ext_windows]

    return CrossVentResult(
        space_id=space.id,
        space_name=space.name,
        classification=final_class,
        confidence=final_confidence,
        exterior_openings=exterior_openings_out,
        internal_connections=internal_connections,
        airflow_path=airflow_path,
        assumptions=assumptions,
        recommendations=recommendations,
        reasoning=reasoning,
    )


def _search_indirect_path(
    space: SpaceInfo,
    spaces: dict[str, SpaceInfo],
    openings: dict[str, OpeningInfo],
    graph: dict[str, list[dict]],
) -> Optional[dict]:
    """
    BFS over the connectivity graph, depth ≤ MAX_INDIRECT_DEPTH, looking for
    a room with an exterior window oriented significantly differently from
    this room's own exterior windows (if any). Only follows real graph
    edges (door/opening centroids) — never assumes adjacency from geometry
    alone. Penalises path length: shorter, straighter paths preferred.
    """
    own_ext_windows = [o for o in openings.values() if o.is_exterior and o.type == "window" and space.id in o.space_ids]
    own_orientations = [o.orientation_deg for o in own_ext_windows if o.orientation_deg is not None]

    # BFS: each frontier entry is (space_id, path_of_rooms, path_of_edges)
    visited = {space.id}
    frontier = [(space.id, [space.id], [])]
    best = None
    best_score = -1.0

    for depth in range(MAX_INDIRECT_DEPTH):
        next_frontier = []
        for sid, room_path, edge_path in frontier:
            for edge in graph.get(sid, []):
                nxt = edge["to"]
                if nxt in visited:
                    continue
                visited.add(nxt)
                new_room_path = room_path + [nxt]
                new_edge_path = edge_path + [edge]
                next_frontier.append((nxt, new_room_path, new_edge_path))

                other_space = spaces.get(nxt)
                if other_space is None:
                    continue
                other_ext_windows = [
                    o for o in openings.values()
                    if o.is_exterior and o.type == "window" and nxt in o.space_ids
                ]
                for ow in other_ext_windows:
                    if ow.orientation_deg is None:
                        continue
                    if own_orientations:
                        diffs = [min(abs(ow.orientation_deg - od) % 360, 360 - abs(ow.orientation_deg - od) % 360)
                                 for od in own_orientations]
                        angle = max(diffs)
                    else:
                        angle = 90.0  # this room has no exterior opening at all — any indirect outlet helps
                    if angle < ANGLE_WEAK_MAX:
                        continue  # not meaningfully different — not worth recommending as cross-vent

                    # Score: prefer larger angle, fewer hops, fewer turns
                    hops = len(new_room_path) - 1
                    score = angle - hops * 20.0
                    if score > best_score:
                        best_score = score
                        best = {
                            "rooms": new_room_path,
                            "edges": new_edge_path,
                            "target_opening": ow,
                            "angle": angle,
                            "via": " → ".join(spaces[r].name for r in new_room_path[1:-1]) or "direct door",
                        }
        frontier = next_frontier
        if not frontier:
            break

    return best


def _build_airflow_path(
    space: SpaceInfo,
    own_ext_windows: list[OpeningInfo],
    indirect_path: Optional[dict],
    classification: str,
) -> list[list[float]]:
    """
    §7 — build the path polyline from real centroids only (exterior opening
    → room centroid → door centroid → next room centroid → ...). Never
    interpolates a straight line between two openings without passing
    through the connecting room centroids / door centroids in between.
    """
    if space.centroid is None:
        return []
    room_c = list(space.centroid)

    if classification == "strong_cross_ventilation" or classification == "moderate_cross_ventilation":
        if len(own_ext_windows) >= 2:
            a, b = own_ext_windows[0], own_ext_windows[1]
            return [list(a.centroid), room_c, list(b.centroid)]
        return []

    if classification == "weak_adjacent_ventilation":
        if len(own_ext_windows) >= 2:
            a, b = own_ext_windows[0], own_ext_windows[1]
            return [list(a.centroid), room_c, list(b.centroid)]
        return []

    if classification == "single_sided":
        if own_ext_windows:
            return [list(own_ext_windows[0].centroid), room_c]
        return []

    if classification == "indirect_possible" and indirect_path:
        path = []
        if own_ext_windows:
            path.append(list(own_ext_windows[0].centroid))
        path.append(room_c)
        for edge in indirect_path["edges"]:
            path.append(list(edge["centroid"]))
            # the room centroid on the far side of this edge
            # (room_path[i+1]'s centroid would be added by caller if needed)
        path.append(list(indirect_path["target_opening"].centroid))
        return path

    return []  # "poor" / "unknown" — no fabricated path


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Standard 2D segment intersection test (p1-p2 vs p3-p4)."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _verify_path_does_not_cross_walls(
    airflow_path: list[list[float]],
    wall_segments: list[tuple],
    space: SpaceInfo,
    reasoning: list[str],
) -> None:
    """
    §10 debugging requirement — verify (in 2D plan / XY) that no leg of the
    airflow path crosses a wall segment. The path is built exclusively from
    opening/room centroids, so a crossing here indicates either bad input
    geometry or an unusually shaped (non-convex / L-shaped) room — logged
    as a warning so it's visible, rather than silently shown to the user.
    This does not block rendering the path; it flags it as a possible
    geometry edge case worth checking against the source IFC.
    """
    if len(airflow_path) < 2 or not wall_segments:
        return
    crossed = 0
    for i in range(len(airflow_path) - 1):
        p1 = (airflow_path[i][0], airflow_path[i][1])
        p2 = (airflow_path[i + 1][0], airflow_path[i + 1][1])
        for seg in wall_segments:
            if _segments_intersect(p1, p2, seg[0], seg[1]):
                crossed += 1
    if crossed:
        msg = f"Airflow path may cross {crossed} wall segment(s) in plan — verify against source IFC geometry."
        reasoning.append(msg)
        logger.warning("Cross-vent: room '%s' (%s): %s", space.name, space.id, msg)


def _build_recommendations(
    classification: str,
    space: SpaceInfo,
    own_ext_windows: list[OpeningInfo],
    openings: dict[str, OpeningInfo],
    graph: dict[str, list[dict]],
) -> list[str]:
    """§8 — deterministic recommendations, never suggesting a non-exterior wall."""
    recs: list[str] = []

    if classification in ("poor", "single_sided", "weak_adjacent_ventilation"):
        recs.append(
            "Add an operable opening on an opposite or adjacent exterior wall, "
            "if a second exterior facade exists or can be created for this room."
        )
        recs.append(
            "If a second exterior opening is not feasible, add a high-level vent "
            "or transom opening to support stack-effect airflow."
        )
        if not graph.get(space.id):
            recs.append(
                "No internal door/opening connects this room to another space — "
                "improving the internal connection to a room with an exterior "
                "outlet would enable indirect ventilation."
            )
        recs.append("Keep the door/opening path clear at night to support night purge ventilation.")

    if classification == "indirect_possible":
        recs.append(
            "Keep the connecting door open during ventilation hours — indirect "
            "cross-ventilation depends on this path remaining clear."
        )

    return recs
