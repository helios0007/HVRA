"""
Stage 5 — IFC Retrofit Geometry Generator.

Adds simplified schematic geometry for Category A retrofit strategies to a copy
of the original IFC model.  The geometry is representative / diagrammatic —
positioned relative to each IfcSpace origin, not resolved to exact window or
wall positions (full mesh extraction is outside this prototype scope).

Category A strategies (visualization_category == 'geometry'):
  external_shading_louvers       horizontal louver panels on south face
  window_external_shutters       shutter panels on south face
  window_enlargement             wide frame plate on south face
  interior_opening_improvement   transom plate on north face
  stack_effect_roof_vent         short square column on roof
  green_pergola                  thin slab on south at high level
  roof_insulation                thin slab above space (z +2.8 m)
  external_wall_insulation_etics thick plate on south exterior face
  internal_wall_insulation       thin plate on south interior face
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

CATEGORY_A: set[str] = {
    "external_shading_louvers",
    "window_external_shutters",
    "window_enlargement",
    "interior_opening_improvement",
    "stack_effect_roof_vent",
    "green_pergola",
    "roof_insulation",
    "external_wall_insulation_etics",
    "internal_wall_insulation",
}


def generate_after_model(
    input_ifc: str,
    shortlist: list[dict],
    output_path: str,
) -> None:
    """
    Open input_ifc, add Category A retrofit geometry for rooms in shortlist,
    write modified model to output_path.

    Parameters
    ----------
    input_ifc : str
        Path to the original input.ifc file.
    shortlist : list[dict]
        Contents of shortlist.json — list of per-room dicts:
        [{"room_id": str, "shortlist": [{"strategy_id": str, ...}]}, ...]
    output_path : str
        Destination path for the modified IFC.
    """
    try:
        import ifcopenshell
        import ifcopenshell.guid
        import ifcopenshell.util.placement
    except ImportError as exc:
        raise RuntimeError(f"ifcopenshell not available: {exc}") from exc

    model = ifcopenshell.open(input_ifc)

    # Build lookup key → list of Category A strategy IDs.
    # Prefer the full IFC GlobalId; fall back to room_id ("R_" + last 8 chars
    # of the GlobalId) for older shortlist files.
    room_strats: dict[str, list[str]] = {}
    for room_data in shortlist:
        key = room_data.get("ifc_global_id") or room_data.get("room_id", "")
        sids = [
            s["strategy_id"]
            for s in room_data.get("shortlist", [])
            if s.get("strategy_id") in CATEGORY_A
        ]
        if sids:
            room_strats[key] = sids

    if not room_strats:
        model.write(output_path)
        return

    space_index: dict[str, Any] = {
        sp.GlobalId: sp for sp in model.by_type("IfcSpace")
    }

    def find_space(key: str):
        if key in space_index:
            return space_index[key]
        # room_id fallback: match GlobalId suffix
        suffix = key[2:] if key.startswith("R_") else key
        for gid, sp in space_index.items():
            if gid.endswith(suffix):
                return sp
        return None

    ctx = _body_context(model)
    owner = model.by_type("IfcOwnerHistory")[0] if model.by_type("IfcOwnerHistory") else None

    added = 0
    for room_id, sids in room_strats.items():
        space = find_space(room_id)
        if space is None:
            logger.warning("retrofit_geometry: IfcSpace %s not found — skipped", room_id)
            continue

        try:
            mat = ifcopenshell.util.placement.get_local_placement(space.ObjectPlacement)
            origin = mat[:3, 3]
        except Exception as exc:
            logger.warning("retrofit_geometry: placement error %s: %s — skipped", room_id, exc)
            continue

        for sid in sids:
            try:
                _dispatch(model, space, sid, ctx, owner)
                added += 1
            except Exception as exc:
                logger.warning("retrofit_geometry: %s / %s failed: %s", room_id, sid, exc)

    logger.info("retrofit_geometry: %d elements added → %s", added, output_path)
    model.write(output_path)


# ── Internal helpers ────────────────────────────────────────────────────────────

def _body_context(model):
    """Return the best 3-D body representation context available."""
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body":
            return ctx
    for ctx in model.by_type("IfcGeometricRepresentationContext"):
        if ctx.ContextType == "Model":
            return ctx
    return None


def _rect_solid(model, w: float, d: float, h: float, ox: float = 0.0, oy: float = 0.0):
    """IfcExtrudedAreaSolid: axis-aligned rectangle w×d extruded by h."""
    pt2 = model.createIfcCartesianPoint([float(ox), float(oy)])
    profile = model.createIfcRectangleProfileDef(
        "AREA", None,
        model.createIfcAxis2Placement2D(pt2, None),
        float(w), float(d),
    )
    origin = model.createIfcCartesianPoint([0.0, 0.0, 0.0])
    ax3 = model.createIfcAxis2Placement3D(origin, None, None)
    return model.createIfcExtrudedAreaSolid(
        profile, ax3,
        model.createIfcDirection([0.0, 0.0, 1.0]),
        float(h),
    )


def _placement(model, parent, dx: float, dy: float, dz: float):
    """IfcLocalPlacement offset from parent by (dx, dy, dz)."""
    pt = model.createIfcCartesianPoint([float(dx), float(dy), float(dz)])
    ax3 = model.createIfcAxis2Placement3D(
        pt,
        model.createIfcDirection([0.0, 0.0, 1.0]),
        model.createIfcDirection([1.0, 0.0, 0.0]),
    )
    return model.createIfcLocalPlacement(parent, ax3)


def _shape(model, ctx, solid):
    rep = model.createIfcShapeRepresentation(ctx, "Body", "SweptSolid", [solid])
    return model.createIfcProductDefinitionShape(None, None, [rep])


def _guid():
    import ifcopenshell.guid
    return ifcopenshell.guid.new()


def _slab(model, owner, name, pl, shape, ptype="NOTDEFINED"):
    if model.schema == "IFC2X3":
        return model.createIfcSlab(_guid(), owner, name, None, None, pl, shape, None, ptype)
    return model.createIfcSlab(_guid(), owner, name, None, None, pl, shape, None, ptype)


def _plate(model, owner, name, pl, shape):
    if model.schema == "IFC2X3":
        return model.createIfcPlate(_guid(), owner, name, None, None, pl, shape, None)
    return model.createIfcPlate(_guid(), owner, name, None, None, pl, shape, None, "NOTDEFINED")


def _column(model, owner, name, pl, shape):
    if model.schema == "IFC2X3":
        return model.createIfcColumn(_guid(), owner, name, None, None, pl, shape, None)
    return model.createIfcColumn(_guid(), owner, name, None, None, pl, shape, None, "NOTDEFINED")


def _dispatch(model, space, strategy_id: str, ctx, owner) -> None:
    """Add representative geometry for one strategy on one IfcSpace."""
    pp = space.ObjectPlacement  # parent placement

    if strategy_id == "roof_insulation":
        pl = _placement(model, pp, 0, 0, 2.8)
        _slab(model, owner, "HVRA_roof_insulation", pl, _shape(model, ctx, _rect_solid(model, 4, 4, 0.12, -2, -2)), "ROOF")

    elif strategy_id == "cool_roof_coating":
        pl = _placement(model, pp, 0, 0, 2.93)
        _slab(model, owner, "HVRA_cool_roof_coating", pl, _shape(model, ctx, _rect_solid(model, 4, 4, 0.03, -2, -2)), "ROOF")

    elif strategy_id == "stack_effect_roof_vent":
        pl = _placement(model, pp, 0.4, 0.4, 2.8)
        _column(model, owner, "HVRA_stack_vent", pl, _shape(model, ctx, _rect_solid(model, 0.3, 0.3, 0.7)))

    elif strategy_id in ("external_shading_louvers", "window_external_shutters"):
        for z in (1.0, 1.7):
            pl = _placement(model, pp, -0.6, 2.5, z)
            _plate(model, owner, f"HVRA_{strategy_id}", pl, _shape(model, ctx, _rect_solid(model, 1.2, 0.14, 0.03)))

    elif strategy_id == "window_enlargement":
        pl = _placement(model, pp, -0.8, 2.5, 0.7)
        _plate(model, owner, "HVRA_window_enlarged", pl, _shape(model, ctx, _rect_solid(model, 1.6, 0.08, 1.5)))

    elif strategy_id == "external_wall_insulation_etics":
        pl = _placement(model, pp, -1.5, 2.5, 0.05)
        _plate(model, owner, "HVRA_etics", pl, _shape(model, ctx, _rect_solid(model, 3.0, 0.10, 2.5)))

    elif strategy_id == "internal_wall_insulation":
        pl = _placement(model, pp, -1.5, 2.2, 0.05)
        _plate(model, owner, "HVRA_int_insulation", pl, _shape(model, ctx, _rect_solid(model, 3.0, 0.06, 2.5)))

    elif strategy_id == "green_pergola":
        pl = _placement(model, pp, -1.0, 2.5, 2.4)
        _slab(model, owner, "HVRA_green_pergola", pl, _shape(model, ctx, _rect_solid(model, 2.0, 2.0, 0.08, -1, -1)), "FLOOR")

    elif strategy_id == "interior_opening_improvement":
        pl = _placement(model, pp, -0.5, -2.2, 2.0)
        _plate(model, owner, "HVRA_transom", pl, _shape(model, ctx, _rect_solid(model, 1.0, 0.05, 0.4)))
