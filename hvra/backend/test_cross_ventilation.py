"""
Synthetic test suite for cross_ventilation.py — exercises the classification,
indirect-search, and recommendation logic directly against hand-built
SpaceInfo/OpeningInfo/graph fixtures (no real IFC file needed), per the 5
required scenarios:

  a) room with opposite windows           -> strong_cross_ventilation
  b) room with adjacent windows           -> moderate or weak
  c) room with two same-wall windows      -> single_sided
  d) two rooms connected by a door,
     each with an exterior window         -> indirect_possible (from the
                                              single-window room's side)
  e) internal room with no windows        -> poor

Run directly: .venv\\Scripts\\python.exe test_cross_ventilation.py
"""

import sys
sys.path.insert(0, ".")

from analysis.cross_ventilation import (
    SpaceInfo, OpeningInfo, _classify_space, _build_connectivity_graph,
)


def make_window(id_, space_id, orientation_deg, wall_id, centroid):
    return OpeningInfo(
        id=id_, type="window", host_wall_id=wall_id, space_ids=[space_id],
        centroid=centroid, area_m2=2.0, orientation_deg=orientation_deg,
        is_exterior=True, operable_assumed=False,
    )


def make_door(id_, space_a, space_b, centroid):
    return OpeningInfo(
        id=id_, type="door", host_wall_id=f"wall_{id_}", space_ids=[space_a, space_b],
        centroid=centroid, area_m2=1.8, orientation_deg=None,
        is_exterior=False, operable_assumed=False,
    )


def run_case(name, spaces, openings, expect_classification, expect_room="A"):
    graph = _build_connectivity_graph(openings)
    space = spaces[expect_room]
    result = _classify_space(space, spaces, openings, graph, wall_segments=[])
    status = "PASS" if result.classification == expect_classification else "FAIL"
    print(f"[{status}] {name}")
    print(f"       expected={expect_classification!r}  got={result.classification!r}  confidence={result.confidence}")
    for r in result.reasoning:
        print(f"       reasoning: {r}")
    if result.recommendations:
        for rec in result.recommendations:
            print(f"       recommend: {rec}")
    print(f"       airflow_path points: {len(result.airflow_path)}")
    print()
    return status == "PASS"


def main():
    results = []

    # ── (a) opposite windows (0° and 180°) → strong ─────────────────────
    spaces = {"A": SpaceInfo(id="A", name="Room A", level=0, centroid=(5, 5, 1.2))}
    openings = {
        "w1": make_window("w1", "A", 0.0,   "wallN", (5, 9, 1.2)),
        "w2": make_window("w2", "A", 180.0, "wallS", (5, 1, 1.2)),
    }
    results.append(run_case("(a) opposite windows", spaces, openings, "strong_cross_ventilation"))

    # ── (b) adjacent windows (0° and 90°) → moderate ────────────────────
    spaces = {"A": SpaceInfo(id="A", name="Room B", level=0, centroid=(5, 5, 1.2))}
    openings = {
        "w1": make_window("w1", "A", 0.0,  "wallN", (5, 9, 1.2)),
        "w2": make_window("w2", "A", 90.0, "wallE", (9, 5, 1.2)),
    }
    results.append(run_case("(b) adjacent windows (90°)", spaces, openings, "moderate_cross_ventilation"))

    # ── (b2) weak adjacent (0° and 50°) → weak ──────────────────────────
    spaces = {"A": SpaceInfo(id="A", name="Room B2", level=0, centroid=(5, 5, 1.2))}
    openings = {
        "w1": make_window("w1", "A", 0.0,  "wallN", (5, 9, 1.2)),
        "w2": make_window("w2", "A", 50.0, "wallNE", (8, 8, 1.2)),
    }
    results.append(run_case("(b2) weak adjacent windows (50°)", spaces, openings, "weak_adjacent_ventilation"))

    # ── (c) two windows on the SAME wall → single_sided ─────────────────
    spaces = {"A": SpaceInfo(id="A", name="Room C", level=0, centroid=(5, 5, 1.2))}
    openings = {
        "w1": make_window("w1", "A", 0.0, "wallN", (3, 9, 1.2)),
        "w2": make_window("w2", "A", 0.0, "wallN", (7, 9, 1.2)),  # SAME wall_id as w1
    }
    results.append(run_case("(c) two windows, same wall", spaces, openings, "single_sided"))

    # ── (d) two rooms connected by a door, each with an exterior window,
    #        differently oriented → indirect_possible (from room A's side,
    #        which only has ONE window of its own) ─────────────────────
    spaces = {
        "A": SpaceInfo(id="A", name="Room D1", level=0, centroid=(5, 5, 1.2)),
        "B": SpaceInfo(id="B", name="Room D2", level=0, centroid=(15, 5, 1.2)),
    }
    openings = {
        "w1": make_window("w1", "A", 0.0,   "wallN_A", (5, 9, 1.2)),    # room A: north window only
        "w2": make_window("w2", "B", 180.0, "wallS_B", (15, 1, 1.2)),   # room B: south window — very different orientation
        "door1": make_door("door1", "A", "B", (10, 5, 1.2)),
    }
    results.append(run_case("(d) indirect via connecting door", spaces, openings, "indirect_possible", expect_room="A"))

    # ── (e) internal room with no windows at all → poor ──────────────────
    spaces = {"A": SpaceInfo(id="A", name="Room E (internal)", level=0, centroid=(5, 5, 1.2))}
    openings = {}
    results.append(run_case("(e) no exterior openings", spaces, openings, "poor"))

    total = len(results)
    passed = sum(results)
    print(f"{'='*50}\n{passed}/{total} test cases passed")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
