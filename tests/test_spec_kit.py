#!/usr/bin/env python3
"""Unit tests for spec_kit (pure Python, zero Blender/shapely dependency)."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "examples", "recipes"))

import spec_kit as SK  # noqa: E402


def test_rect_union_l_shape_notch_hole_island():
    # L-shape + wing - notch - courtyard hole
    rings = SK.rect_union_to_rings(
        union=[[0, 0, 10, 8], [-2, 5, 0, 8]],
        sub=[[7, 0, 10, 2], [2, 3, 5, 6]],
    )
    assert len(rings["outers"]) == 1, rings
    assert len(rings["holes"]) == 1, rings
    # Area = 80 + 6 - 6 - 9 = 71.0
    a_out = SK._ring_area(rings["outers"][0])
    a_hole = SK._ring_area(rings["holes"][0])
    assert a_out > 0 and a_hole < 0
    assert abs((a_out + a_hole) - 71.0) < 1e-6, (a_out, a_hole)
    # Two disjoint islands
    r2 = SK.rect_union_to_rings(union=[[0, 0, 3, 3], [5, 0, 8, 3]])
    assert len(r2["outers"]) == 2
    assert len(r2["holes"]) == 0
    # Collinear points merged: 2 touching rects forming a plain 10x4 rectangle must have 4 verts
    r3 = SK.rect_union_to_rings(union=[[0, 0, 4, 4], [4, 0, 10, 4]])
    assert len(r3["outers"]) == 1 and len(r3["outers"][0]) == 4, r3
    # Diagonal pinch touching corners
    r4 = SK.rect_union_to_rings(union=[[0, 0, 2, 2], [2, 2, 4, 4]])
    assert len(r4["outers"]) == 2
    assert abs(sum(SK._ring_area(x) for x in r4["outers"]) - 8.0) < 1e-6


def test_base_add_sub_overrides_prior_recess():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "spec.json")
        SK.spec_init(path=p, yaw_deg=19.5, scale_m_per_px=0.05)
        SK.spec_set("levels", [
            {"id": "L1", "z": 0.0, "slab": 0.3, "cut": 1.5},
            {"id": "L2", "z": 3.2, "slab": 0.3, "cut": 1.5},
            {"id": "L3", "z": 6.4, "slab": 0.3, "cut": 1.0},
        ])
        SK.spec_set("outline", {
            "L1": {"union": [[0, 0, 10, 8]], "sub": [[4, 0, 6, 2], [2, 3, 4, 5]], "src": "plan", "conf": "H"},
            # L2 cantilevers back over the [4,0,6,2] front recess!
            "L2": {"base": "L1", "add": [[4, 0, 6, 2]], "sub": [], "src": "photo", "conf": "M"},
            "L3": {"base": "L2", "add": [], "sub": [[8, 6, 10, 8]], "src": "section", "conf": "M"},
        })
        o1 = SK.resolve_outline("L1")
        o2 = SK.resolve_outline("L2")
        o3 = SK.resolve_outline("L3")
        assert abs(o1["area"] - (80 - 4 - 4)) < 1e-6, o1
        assert abs(o2["area"] - (80 - 4)) < 1e-6, o2  # [4,0,6,2] restored!
        assert abs(o3["area"] - (80 - 4 - 4)) < 1e-6, o3
        edges = SK.outline_edges("L2", include_holes=True)
        hole_edges = [e for e in edges if e["is_hole"]]
        assert len(hole_edges) == 4
        # West wall of courtyard [2,4]x[3,5] faces East (+1, 0) into courtyard
        w_courtyard = [e for e in hole_edges if e["coord"] == 2.0][0]
        assert w_courtyard["side"] == "E" and w_courtyard["outward"] == (1.0, 0.0), w_courtyard


def test_validation_codes_digest_and_phase():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "spec.json")
        SK.spec_init(path=p, scale_m_per_px=0.056)
        SK.spec_set("levels", [
            {"id": "L0", "z": 0.0, "slab": 0.3},
            {"id": "L1", "z": 3.2, "slab": 0.3},
        ])
        SK.spec_set("outline", {
            "L0": {"union": [[0, 0, 11.2, 9.0], [-1.8, 6.0, 0.0, 9.0]], "sub": [[8.0, 0, 11.2, 1.2]], "src": "plan", "conf": "H"},
            "L1": {"base": "L0", "add": [[11.2, 1.0, 13.0, 6.0]], "src": "photo", "conf": "M"},
        })
        SK.spec_set("edge_rules", [
            {"level": "L0", "side": "S", "span": [0.0, 4.0], "kind": "SOLID"},
            {"level": "L0", "side": "S", "span": [4.0, 5.2], "kind": "OPEN"},
            {"level": "L1", "side": "E", "span": [1.0, 6.0], "kind": "CANTILEVER", "skin": "LOUVER",
             "openings": [{"u": [0.5, 4.5], "z": [0.0, 2.4]}]},
        ])
        res = SK.spec_validate()
        assert res["valid"], res
        dig = SK.spec_digest()
        assert len(dig.splitlines()) <= 40
        card = SK.phase_next()
        assert len(card.splitlines()) <= 20
        show = SK.spec_show("L0")
        assert "E1" in show

        # Trigger error codes deliberately
        bad = SK.spec_load(p)
        bad["levels"][1]["z"] = -1.0  # non-monotonic
        bad["outline"]["L2"] = {"base": "NO_SUCH", "add": []}
        bad["outline"]["L_tiny"] = {"union": [[0, 0, 0.1, 2.0]]}
        bad["levels"].append({"id": "L_tiny", "z": 5.0, "slab": 0.3})
        bad["edge_rules"].append({"level": "L0", "side": "S", "span": [0.0, 4.0], "kind": "WEIRD",
                                   "openings": [{"u": [0.0, 9.0], "z": [0.0, 12.0]}]})
        err = SK.spec_validate(bad)
        assert not err["valid"]
        codes = {e.split(":")[0] for e in err["errors"]}
        for expected in ("E_LEVEL_Z_NONMONO", "E_MISSING_BASE", "E_SHORT_EDGE", "E_UNKNOWN_KIND", "E_OPENING_OOB", "E_OPENING_Z_OOB"):
            assert expected in codes, f"Missing {expected} in {err['errors']}"

        # Split-level monotonic check isolated by zone
        split = SK.spec_init(path=os.path.join(tmp, "split.json"), scale_m_per_px=0.05)
        SK.spec_set("levels", [
            {"id": "L0_W", "z": 0.0, "slab": 0.3, "zone": [0, 0, 6, 8]},
            {"id": "L0_E", "z": 1.2, "slab": 0.3, "zone": [6, 0, 12, 8]},
            {"id": "L1_W", "z": 3.0, "slab": 0.3, "zone": [0, 0, 6, 8]},
            # Lower than L1_W in E zone is legal because zones are independent!
            {"id": "L1_E", "z": 2.7, "slab": 0.3, "zone": [6, 0, 12, 8]},
        ])
        SK.spec_patch({"op": "set", "path": "progress.phase", "value": "P2"})
        SK.spec_note("East wing shifted +1.2m up", src="section")
        s_res = SK.spec_validate()
        assert s_res["valid"], s_res


if __name__ == "__main__":
    test_rect_union_l_shape_notch_hole_island()
    test_base_add_sub_overrides_prior_recess()
    test_validation_codes_digest_and_phase()
    print("test_spec_kit: ALL PASS")
