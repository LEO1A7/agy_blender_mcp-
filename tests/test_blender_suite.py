"""End-to-end Blender headless verification suite for v1.4.0 modeling & floor-cut verification.

Run with:
    /usr/local/bin/blender -b --factory-startup --python tests/test_blender_suite.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

import bmesh
import bpy
from mathutils import Vector

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
_RECIPES_DIR = os.path.join(_REPO_ROOT, "examples", "recipes")
_BIN_RENDER = os.path.join(_REPO_ROOT, "bin", "level_plan_render.py")

if _RECIPES_DIR not in sys.path:
    sys.path.insert(0, _RECIPES_DIR)

import cad_operator_recipes as COR  # noqa: E402
import detail_kit as DK  # noqa: E402
import facade_kit as FK  # noqa: E402
import level_cut_verify as LCV  # noqa: E402
import spec_kit as SK  # noqa: E402


def _reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0


def _bmesh_nonmanifold_and_volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    vol = abs(bm.calc_volume(signed=True))
    area = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return non_manifold, vol, area


def _make_synthetic_plan_png_and_meta(work_dir, spec):
    """Create a synthetic rotated plan PNG + plan_meta.json via system python3 matching plan_prep schema."""
    plan_png = os.path.join(work_dir, "plan_rot.png")
    meta_json = os.path.join(work_dir, "plan_meta.json")
    code = f"""
import json
from PIL import Image, ImageDraw
W, H = 900, 700
s = 0.04
ox, oy = 180.0, 520.0
im = Image.new("RGB", (W, H), (245, 245, 240))
dr = ImageDraw.Draw(im)
def w2px(x, y):
    return (ox + x / s, oy - y / s)
pts = [w2px(0,10), w2px(14,10), w2px(14,9), w2px(18,9), w2px(18,1), w2px(14,1), w2px(14,0), w2px(0,0)]
dr.polygon(pts, outline=(30, 30, 30), width=4)
im.save({plan_png!r})
meta = {{"rot_size": [W, H], "scale_m_per_px": s, "origin_rot": [ox, oy], "plan_rot_save_scale": 1.0}}
with open({meta_json!r}, "w") as f:
    json.dump(meta, f)
"""
    proc = subprocess.run(["python3", "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Synthetic plan helper failed: {proc.stderr}"
    return plan_png, meta_json


def _write_test_spec(work_dir):
    spec_path = os.path.join(work_dir, "building_spec.json")
    spec = SK.spec_init(path=spec_path, yaw_deg=19.5, scale_m_per_px=0.04, origin="ROI SW corner")
    spec["levels"] = [
        {"id": "L0", "name": "Ground", "z": 0.04, "slab": 0.30, "cut": 1.50, "zone": [0.0, 0.0, 18.5, 10.5]},
        {"id": "L1", "name": "Upper", "z": 3.22, "slab": 0.30, "cut": 1.50},
        {"id": "L2", "name": "Roof", "z": 6.37, "slab": 0.28, "cut": 1.00},
        {"id": "L0B", "name": "SplitWing", "z": 1.60, "slab": 0.28, "cut": 1.50, "zone": [-6.0, 0.0, 0.0, 6.0]},
    ]
    spec["outline"] = {
        "L0": {"union": [[0.0, 0.0, 14.0, 10.0]], "add": [], "sub": [[5.0, 3.0, 9.0, 7.0]]},
        "L1": {"union": [[0.0, 0.0, 14.0, 10.0]], "add": [[14.0, 1.0, 18.0, 9.0]], "sub": []},
        "L2": {"union": [[0.0, 0.0, 12.0, 8.0]], "add": [], "sub": []},
        "L0B": {"union": [[-6.0, 0.0, 0.0, 6.0]], "add": [], "sub": []},
    }
    spec["edge_rules"] = [
        {
            "level": "L0", "side": "N", "kind": "SOLID",
            "openings": [
                {"u": [2.0, 4.5], "z": [0.9, 2.4], "kind": "window"},
                {"u": [9.0, 10.2], "z": [0.0, 2.2], "kind": "door"},
            ],
        },
        {"level": "L0", "side": "S", "span": [4.0, 10.0], "kind": "OPEN"},
        {"level": "L0", "side": "W", "span": [0.0, 6.0], "kind": "STEP", "dz": 1.56},
        {"level": "L0", "side": "W", "span": [6.0, 10.0], "kind": "SLAT", "skin": "timber_slat", "depth": 0.20, "solid": True},
        {"level": "L1", "side": "N", "span": [10.0, 14.0], "kind": "GLAZED", "sill_h": 0.90},
        {"level": "L1", "side": "N", "span": [14.0, 18.0], "kind": "GLAZED", "sill_h": 0.0},
        {"level": "L1", "side": "E", "span": [1.0, 9.0], "kind": "GLAZED", "sill_h": 0.0},
        {"level": "L1", "side": "S", "span": [2.0, 12.0], "kind": "LOUVER", "skin": "louver_screen", "depth": 0.18, "openings": [{"u": [2.0, 6.0], "z": [0.9, 2.4], "kind": "window"}]},
        {"level": "L2", "side": "S", "span": [2.0, 8.0], "kind": "RECESS", "depth": 0.10},
        {"level": "L0B", "side": "N", "kind": "GLAZED", "sill_h": 0.90},
    ]
    spec["elements"] = [
        {"id": "cantilever_cols", "kind": "HEB220", "count": 2, "status": "ok"},
    ]
    spec["progress"] = {"phase": "P2", "gates": {"G1": True, "G2": True}, "iters": {}, "last_verify": None}
    SK.spec_save(spec, path=spec_path)
    return spec, spec_path


def test_wall_with_openings(work_dir):
    _reset_scene()
    col = COR.get_or_create_collection("Test_Openings")
    obj = FK.wall_with_openings(
        (0.0, 0.0), (10.0, 0.0), z0=0.0, z1=3.2, t=0.28,
        openings=[
            {"u": [2.0, 4.0], "z": [0.9, 2.4], "kind": "window"},
            {"u": [6.0, 7.2], "z": [0.0, 2.2], "kind": "door"},
        ],
        inward=(0.0, 1.0),
        name="Test_OpeningWall",
        col=col,
    )
    assert obj is not None, "wall_with_openings returned None"
    nm, vol, _ = _bmesh_nonmanifold_and_volume(obj)
    assert nm == 0, f"Test_OpeningWall has {nm} non-manifold edges"
    expected_vol = (10.0 * 3.2 - 2.0 * 1.5 - 1.2 * 2.2) * 0.28
    rel_err = abs(vol - expected_vol) / expected_vol
    assert rel_err < 0.005, f"Wall volume mismatch: got {vol:.4f}, expected {expected_vol:.4f} (rel={rel_err:.4f})"
    print(f"[PASS] test_wall_with_openings: nm={nm}, vol={vol:.4f} (expected {expected_vol:.4f})")


def test_slab_with_courtyard_hole(work_dir):
    _reset_scene()
    spec_path = os.path.join(work_dir, "building_spec.json")
    spec = SK.spec_init(path=spec_path)
    spec["levels"] = [{"id": "L0", "name": "L_Court", "z": 0.04, "slab": 0.30, "cut": 1.50}]
    spec["outline"] = {
        "L0": {"union": [[0.0, 0.0, 12.0, 10.0]], "add": [[0.0, 10.0, 5.0, 14.0]], "sub": [[3.0, 3.0, 7.0, 7.0]]},
    }
    SK.spec_save(spec, path=spec_path)

    slab = FK.build_level_slab("L0")
    nm, vol, area = _bmesh_nonmanifold_and_volume(slab)
    assert nm == 0, f"Slab has {nm} non-manifold edges"
    expected_area_2d = 12.0 * 10.0 + 5.0 * 4.0 - 4.0 * 4.0  # 124.0
    expected_vol = expected_area_2d * 0.30  # 37.2
    assert abs(vol - expected_vol) < 1e-3, f"Slab volume {vol:.4f} != {expected_vol:.4f}"
    # Perimeter = outer L-shape (12+14+5+4+7+10=52) + hole (16) = 68; side area = 68*0.30 = 20.4; top+bot = 248
    expected_surface = 2.0 * expected_area_2d + (52.0 + 16.0) * 0.30
    assert abs(area - expected_surface) < 0.05, f"Slab surface area {area:.4f} != {expected_surface:.4f}"
    audit = COR.audit_scene_meshes()
    assert audit["passed"], f"audit_scene_meshes failed: {audit}"
    print(f"[PASS] test_slab_with_courtyard_hole: nm={nm}, vol={vol:.4f}, area={area:.4f}")


def test_cantilever_heb220_and_detail_audit(work_dir):
    _reset_scene()
    spec_path = os.path.join(work_dir, "building_spec.json")
    spec = SK.spec_init(path=spec_path)
    spec["levels"] = [{"id": "L1", "z": 3.22, "slab": 0.30, "cut": 1.50}]
    spec["outline"] = {"L1": {"union": [[0.0, 0.0, 10.0, 8.0]], "add": [], "sub": []}}
    spec["elements"] = [{"id": "cantilever_cols", "kind": "HEB220", "count": 2}]
    SK.spec_save(spec, path=spec_path)
    objs = FK.add_cantilever(
        "L1", [10.0, 2.0, 13.0, 6.0], slab_t=0.30,
        support={"section": "HEB220", "pts": [[12.5, 2.4], [12.5, 5.6]], "z_bot": 0.04},
    )
    assert len(objs) == 2, f"Expected slab + Support object, got {len(objs)}: {[o.name for o in objs]}"
    for o in objs:
        nm, vol, _ = _bmesh_nonmanifold_and_volume(o)
        assert nm == 0 and vol > 1e-4, f"{o.name} nm={nm}, vol={vol}"
    # Verify real 2x H-profile geometry (>12 faces per column => >=28 faces in Support)
    sup = [o for o in objs if o.name.endswith("_Support")]
    assert sup and len(sup[0].data.polygons) >= 28, f"Expected real 2x I-profile (>=28 faces), got {[len(o.data.polygons) for o in sup]}"
    da = DK.detail_audit()
    assert da["passed"], f"detail_audit failed: {da}"
    print(f"[PASS] test_cantilever_heb220_and_detail_audit: sup_faces={len(sup[0].data.polygons)}, audit OK")


def test_multi_level_build_verify_render_errors_and_site_yaw(work_dir):
    _reset_scene()
    spec, spec_path = _write_test_spec(work_dir)
    built = FK.build_all_levels(wall_t=0.28, skin_offset=0.05, shading="RANDOM")
    assert set(built["levels_built"]) == {"L0", "L1", "L2", "L0B"}, f"Built keys: {built}"

    # 3D geometry & detail audit
    mesh_audit = COR.audit_scene_meshes()
    assert mesh_audit["passed"], f"audit_scene_meshes failed: {mesh_audit}"
    da = DK.detail_audit()
    assert da["passed"], f"detail_audit failed: {da}"

    # Verify floor cuts PASS baseline
    cuts_out = LCV.export_level_cuts(spec=spec)
    assert set(cuts_out["levels"]) == {"L0", "L1", "L2", "L0B"}
    res = LCV.verify_levels(cuts_json=cuts_out["path"], spec=spec)
    print(res["report"])
    assert res["passed"], f"Baseline verify_levels failed:\n{res['report']}"
    for lid in ("L0", "L1", "L2", "L0B"):
        lv_res = res["levels"][lid]
        assert lv_res["iou"] >= 0.90, f"{lid} IoU={lv_res['iou']} < 0.90"
        assert lv_res["max_edge_err_mm"] <= 150.0, f"{lid} max_edge_err={lv_res['max_edge_err_mm']}"
        assert not lv_res["rule_violations"], f"{lid} rule_violations={lv_res['rule_violations']}"

    # Render overlay with and without --plan/--meta via bin/level_plan_render.py
    plan_png, meta_json = _make_synthetic_plan_png_and_meta(work_dir, spec)
    out_overlay_clean = os.path.join(work_dir, "overlay_L1_clean.png")
    out_overlay_plan = os.path.join(work_dir, "overlay_L1_plan.png")
    verify_l1 = os.path.join(work_dir, "verify_L1.json")
    for extra, out_img in [([], out_overlay_clean), (["--plan", plan_png, "--meta", meta_json], out_overlay_plan)]:
        cmd = [
            "python3", _BIN_RENDER,
            "--cuts", cuts_out["path"], "--spec", spec_path, "--level", "L1",
            "--verify", verify_l1, "--out", out_img,
        ] + extra
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert p.returncode == 0, f"level_plan_render failed: {p.stdout}\n{p.stderr}"
        assert len(p.stdout.strip().splitlines()) <= 20, f"stdout > 20 lines: {p.stdout}"
        assert os.path.exists(out_img), f"Missing {out_img}"
    # Verify max dimension <= 1600
    dim_check = subprocess.run(
        ["python3", "-c", f"from PIL import Image; im=Image.open({out_overlay_plan!r}); assert max(im.size)<=1600, im.size; print(im.size)"],
        capture_output=True, text=True, check=True,
    )
    print(f"[PASS] overlay render size: {dim_check.stdout.strip()}")

    # --- Error Injection (i): Shift L1 N outer wall +0.25m North ---
    n_walls = [o for o in bpy.data.objects if o.name.startswith("L1_Wall_N_") or o.name.startswith("L1_Glaze_N_")]
    assert n_walls, "No L1 N objects found"
    for o in n_walls:
        o.location.y += 0.25
    bpy.context.view_layer.update()
    res_shift = LCV.verify_levels(spec=spec)
    assert not res_shift["passed"] and not res_shift["levels"]["L1"]["passed"], f"Shift +250mm was not caught: {res_shift['levels']['L1']}"
    assert res_shift["levels"]["L1"]["max_edge_err_mm"] >= 180.0, f"Expected >=180mm err, got {res_shift['levels']['L1']['max_edge_err_mm']}"
    print(f"[PASS] error injection (i) +250mm shift caught: max_edge_err={res_shift['levels']['L1']['max_edge_err_mm']}mm")
    for o in n_walls:
        o.location.y -= 0.25
    bpy.context.view_layer.update()

    # --- Error Injection (ii): Remove cantilever objects around x > 14 on L1 ---
    cant_objs = [o for o in bpy.data.objects if o.name.startswith("L1_") and max(v.co.x + o.location.x for v in o.data.vertices) > 15.0 and o.name != "L1_Slab"]
    assert cant_objs, "No L1 cantilever walls/glazing found"
    saved_cant = []
    for o in cant_objs:
        o.hide_viewport = True
        saved_cant.append(o)
    res_cant = LCV.verify_levels(spec=spec)
    assert not res_cant["levels"]["L1"]["passed"], f"Missing cantilever was not caught: {res_cant['levels']['L1']}"
    assert res_cant["levels"]["L1"]["iou"] < 0.90, f"Expected IoU < 0.90, got {res_cant['levels']['L1']['iou']}"
    assert any(p["kind"] == "MISSING" for p in res_cant["levels"]["L1"]["patches"]), f"Expected MISSING patch: {res_cant['levels']['L1']['patches']}"
    print(f"[PASS] error injection (ii) missing cantilever caught: IoU={res_cant['levels']['L1']['iou']}")
    for o in saved_cant:
        o.hide_viewport = False

    # --- Error Injection (iii): Block L0 OPEN bay with solid wall ---
    blocker = FK.wall_with_openings((10.0, 0.0), (4.0, 0.0), z0=0.04, z1=2.92, t=0.28, openings=[], inward=(0.0, 1.0), name="L0_BadSolidBlocker")
    res_open = LCV.verify_levels(spec=spec)
    assert not res_open["levels"]["L0"]["passed"], f"Blocked OPEN bay was not caught: {res_open['levels']['L0']}"
    assert any("OPEN" in v for v in res_open["levels"]["L0"]["rule_violations"]), f"Missing OPEN violation: {res_open['levels']['L0']['rule_violations']}"
    print(f"[PASS] error injection (iii) blocked OPEN caught: {res_open['levels']['L0']['rule_violations']}")
    bpy.data.objects.remove(blocker, do_unlink=True)

    # --- Error Injection (iv): z_cut slab avoidance ---
    spec_adj = json.loads(json.dumps(spec))
    spec_adj["levels"][0]["cut"] = 0.0  # z_cut = 0.04, flush with L0 slab top z=0.04!
    cuts_adj = LCV.export_level_cuts(spec=spec_adj)
    l0_cut_info = cuts_adj["cuts"]["L0"]
    assert l0_cut_info["z_cut_adjusted"] is True, f"Expected z_cut adjustment near slab top: {l0_cut_info}"
    assert abs(l0_cut_info["z_cut"] - 0.04) >= 0.10, f"Expected >=0.10m shift, got {l0_cut_info['z_cut']}"
    print(f"[PASS] z_cut slab avoidance: 0.04 -> {l0_cut_info['z_cut']}")

    # --- Site_Yaw reversibility + verify_levels invariant + Studio + RANDOM -> MATERIAL ---
    cams = COR.setup_workbench_studio_and_cameras(convention="plan_north_up", diagnostic_colors="RANDOM")
    assert bpy.context.scene.display.shading.color_type == "RANDOM"
    yaw_res = SK.apply_site_yaw(19.5)
    assert abs(yaw_res["yaw_deg"] - 19.5) < 1e-4
    # verify_levels must STILL pass under active Site_Yaw!
    res_yaw = LCV.verify_levels(spec=spec)
    assert res_yaw["passed"], f"verify_levels failed under Site_Yaw:\n{res_yaw['report']}"

    # Render FRONT viewport in RANDOM shading and check color diversity
    cam_front = cams.get("Cam_Front") or bpy.data.objects.get("Cam_Front")
    assert cam_front is not None, f"Missing Cam_Front in {list(cams.keys())}"
    bpy.context.scene.camera = cam_front
    bpy.context.scene.render.resolution_x = 400
    bpy.context.scene.render.resolution_y = 300
    rand_png = os.path.join(work_dir, "random_front.png")
    bpy.context.scene.render.filepath = rand_png
    bpy.ops.render.render(write_still=True)
    div_p = subprocess.run(
        ["python3", "-c",
         f"import numpy as np; from PIL import Image; a=np.array(Image.open({rand_png!r}).convert('RGB'))//32; "
         f"cols=np.unique(a.reshape(-1,3),axis=0); print(len(cols)); assert len(cols)>=4"],
        capture_output=True, text=True, check=True,
    )
    print(f"[PASS] RANDOM shading color buckets: {div_p.stdout.strip()}")

    # Reset yaw and verify reversible zeroing
    reset_res = SK.apply_site_yaw(reset=True)
    assert abs(reset_res["yaw_deg"]) < 1e-6 and abs(bpy.data.objects["Site_Yaw"].rotation_euler.z) < 1e-6
    fm = COR.finish_materials()
    assert fm["shading_color_type"] == "MATERIAL", f"Expected MATERIAL, got {fm}"
    assert bpy.context.scene.display.shading.color_type == "MATERIAL"
    print(f"[PASS] Site_Yaw reversible & finish_materials -> {fm['shading_color_type']}")


def test_benchmark_3000_objects(work_dir):
    _reset_scene()
    spec_path = os.path.join(work_dir, "building_spec.json")
    spec = SK.spec_init(path=spec_path)
    spec["levels"] = [{"id": "L0", "z": 0.0, "slab": 0.30, "cut": 1.50}]
    spec["outline"] = {"L0": {"union": [[0, 0, 20, 20]], "add": [], "sub": []}}
    SK.spec_save(spec, path=spec_path)
    col = COR.get_or_create_collection("Bench_3000")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.4)
    mesh = bpy.data.meshes.new("BenchCubeMesh")
    bm.to_mesh(mesh)
    bm.free()

    for i in range(3000):
        o = bpy.data.objects.new(f"B_{i}", mesh)
        o.location = ((i % 60) * 0.5, (i // 60) * 0.5, 1.5)
        col.objects.link(o)
    bpy.context.view_layer.update()

    t0 = time.perf_counter()
    cuts = LCV.export_level_cuts(levels=["L0"], spec=spec)
    dt = time.perf_counter() - t0
    assert len(cuts["cuts"]["L0"]["objects"]) == 3000, f"Expected 3000 sliced objects, got {len(cuts['cuts']['L0']['objects'])}"
    assert dt < 3.0, f"Benchmark took {dt:.3f}s >= 3.0s"
    print(f"[PASS] test_benchmark_3000_objects: {dt:.3f}s (< 3.0s)")


def test_clash_and_topology_auto_hide_regen(work_dir):
    _reset_scene()
    import case_r06_final_delivery_grouping as R6

    # 1. Verify DetailKit railing & COR track loop builders have zero self-overlap
    col_clean = COR.get_or_create_collection("Struct_Frame")
    bm_rail = bmesh.new()
    DK.add_railing(bm_rail, [(0.0, 0.0, 0.0), (2.4, 0.0, 0.0), (2.4, 1.2, 0.0)], closed=False, kick_h=0.1)
    COR.create_mesh_object("Struct_Railing", bm_rail, col_clean, bevel_width=0.0)

    pts_yz = [(0.0, 0.2), (1.5, 0.2), (2.0, 0.6), (1.8, 0.9), (0.2, 0.9), (-0.3, 0.6)]
    bm_trk = COR.build_contoured_track_loop(pts_yz, x_center=5.0, loop_interior_yz=(0.85, 0.55), add_grousers=True)
    COR.create_mesh_object("Mech_Track", bm_trk, col_clean, bevel_width=0.0)

    bm_win22 = bmesh.new()
    DK.add_window(bm_win22, (8.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), 2.0, 1.6, panes=(2, 2))
    COR.create_mesh_object("Window_2x2", bm_win22, col_clean, bevel_width=0.0)

    audit_clean = COR.audit_scene_meshes(expected_names=["Struct_Railing", "Mech_Track", "Window_2x2"], check_clashes=True)
    assert audit_clean["passed"], f"Expected clean builders with 0 clashes, got: {audit_clean}"
    assert audit_clean["clash_count"] == 0, f"Unexpected clashes in clean builders: {audit_clean['clashes']}"

    # 2. Flush boundary contact = NO false positive; injected penetration + bad topology = FAIL -> auto-hide + regen
    _reset_scene()
    col = COR.get_or_create_collection("L0_Struct")

    bm_slab = bmesh.new()
    bmesh.ops.create_cube(bm_slab, size=1.0)
    bmesh.ops.scale(bm_slab, vec=(6.0, 4.0, 0.30), verts=bm_slab.verts)
    bmesh.ops.translate(bm_slab, vec=(3.0, 2.0, -0.15), verts=bm_slab.verts)
    COR.create_mesh_object("L0_Slab", bm_slab, col, bevel_width=0.0)

    bm_wall = bmesh.new()
    bmesh.ops.create_cube(bm_wall, size=1.0)
    bmesh.ops.scale(bm_wall, vec=(4.0, 0.20, 2.60), verts=bm_wall.verts)
    bmesh.ops.translate(bm_wall, vec=(3.0, 0.10, 1.30), verts=bm_wall.verts)  # bottom z=0.0 flush on L0_Slab top
    COR.create_mesh_object("L0_Wall_Clean", bm_wall, col, bevel_width=0.0)

    flush_audit = COR.audit_scene_meshes(expected_names=["L0_Slab", "L0_Wall_Clean"], check_clashes=True)
    assert flush_audit["passed"] and flush_audit["clash_count"] == 0, f"Flush contact false positive: {flush_audit}"

    # Inject penetrating column (z in [-0.20, 2.60] cuts 0.20m into L0_Slab)
    bm_col = bmesh.new()
    bmesh.ops.create_cube(bm_col, size=1.0)
    bmesh.ops.scale(bm_col, vec=(0.40, 0.40, 2.80), verts=bm_col.verts)
    bmesh.ops.translate(bm_col, vec=(3.0, 2.0, 1.20), verts=bm_col.verts)
    COR.create_mesh_object("Bad_Column", bm_col, col, bevel_width=0.0)

    # Inject self-overlapping twin boxes + open face + unapplied scale
    bm_twin = bmesh.new()
    b1 = bmesh.ops.create_cube(bm_twin, size=0.8)
    bmesh.ops.translate(bm_twin, vec=(1.0, 1.0, 0.4), verts=b1["verts"])
    b2 = bmesh.ops.create_cube(bm_twin, size=0.8)
    bmesh.ops.translate(bm_twin, vec=(1.2, 1.0, 0.4), verts=b2["verts"])
    bad_twin = COR.create_mesh_object("Bad_TwinBoxes", bm_twin, col, bevel_width=0.0)
    bad_twin.scale = (1.5, 1.0, 1.0)

    # Inject BURIED_INSIDE block completely enclosed inside L0_Wall_Clean (y in [0.0, 0.20], z in [0.0, 2.6])
    bm_buried = bmesh.new()
    bmesh.ops.create_cube(bm_buried, size=1.0)
    bmesh.ops.scale(bm_buried, vec=(0.6, 0.12, 0.8), verts=bm_buried.verts)
    bmesh.ops.translate(bm_buried, vec=(3.0, 0.10, 1.30), verts=bm_buried.verts)
    COR.create_mesh_object("Bad_Buried_Block", bm_buried, col, bevel_width=0.0)

    # Empty 0-face mesh must fail topology audit
    empty_mesh = bpy.data.meshes.new("Bad_Empty_M")
    empty_obj = bpy.data.objects.new("Bad_Empty", empty_mesh)
    col.objects.link(empty_obj)
    assert not COR.audit_object_topology(empty_obj)["passed"], "0-face mesh must fail topology audit"
    bpy.data.objects.remove(empty_obj, do_unlink=True)
    bpy.context.view_layer.update()

    bad_audit = COR.audit_scene_meshes(check_clashes=True)
    assert not bad_audit["passed"], f"Expected failure on injected defects, got: {bad_audit}"
    assert bad_audit["clash_count"] >= 2, f"Expected clash count >= 2, got: {bad_audit}"
    assert "Bad_TwinBoxes" in bad_audit["failed_objects"], f"Expected Bad_TwinBoxes in failed_objects: {bad_audit}"

    regen_res = COR.audit_and_regenerate(max_rounds=2)
    assert regen_res["passed"], f"Expected audit_and_regenerate to pass, got: {regen_res}"
    assert "__hide_r1__Bad_Column" in bpy.data.objects
    assert "__hide_r1__Bad_TwinBoxes" in bpy.data.objects
    assert "__hide_r1__Bad_Buried_Block" in bpy.data.objects
    assert bpy.data.objects.get("Bad_Buried_Block") is None, "Buried block should remain archived, not a 0-face zombie"
    assert bpy.data.objects["__hide_r1__Bad_Column"].hide_viewport is True
    assert bpy.data.objects["__hide_r1__Bad_Column"].hide_render is True
    assert bpy.data.objects["__hide_r1__Bad_TwinBoxes"].hide_viewport is True
    assert bpy.data.objects["__hide_r1__Bad_TwinBoxes"].hide_render is True

    active_col = bpy.data.objects.get("Bad_Column")
    active_twin = bpy.data.objects.get("Bad_TwinBoxes")
    assert active_col is not None and not active_col.hide_viewport
    assert active_twin is not None and not active_twin.hide_viewport
    assert COR.audit_object_topology(active_col)["passed"]
    assert COR.audit_object_topology(active_twin)["passed"]

    # Second round regeneration on Bad_Column must increment archive slot to __hide_r2__Bad_Column
    def _build_col_v2(slot):
        bm_v2 = bmesh.new()
        bmesh.ops.create_cube(bm_v2, size=1.0)
        bmesh.ops.scale(bm_v2, vec=(0.35, 0.35, 2.60), verts=bm_v2.verts)
        bmesh.ops.translate(bm_v2, vec=(3.0, 2.0, 1.30), verts=bm_v2.verts)
        return bm_v2

    r2_res = COR.regenerate_component_in_place("Bad_Column", builder_fn=_build_col_v2, reason="manual_v2")
    assert r2_res["ok"] and r2_res["archived"] == "__hide_r2__Bad_Column", f"Unexpected r2 slot: {r2_res}"
    assert "__hide_r2__Bad_Column" in bpy.data.objects
    assert bpy.data.objects["__hide_r2__Bad_Column"].hide_viewport is True
    assert COR.audit_scene_meshes(check_clashes=True)["passed"]

    # CASE_R06 grouping must archive __hide_r* objects into *_WIP collections
    grp_res = R6.execute_grouping_in_blender()
    assert "__hide_r1__Bad_Column" in bpy.data.collections["Bad_Column_WIP"].objects or any(
        c.name.endswith("_WIP") and "__hide_r1__Bad_Column" in c.objects for c in bpy.data.collections
    ), f"Expected __hide_r1__Bad_Column inside a *_WIP collection: {grp_res}"

    # Verify adjacent CANTILEVER glazed corner produces 0 clash and LCV rejects empty spec
    _reset_scene()
    sp_empty = SK.spec_init(path=os.path.join(work_dir, "cant_spec.json"))
    assert LCV.verify_levels(spec=sp_empty)["passed"] is False, "Empty spec must not silently PASS"
    SK.spec_set("levels", [{"id": "L1", "z": 3.0, "slab": 0.30, "cut": 1.50}])
    SK.spec_set("outline", {"L1": {"union": [[0.0, 0.0, 6.0, 4.0]], "add": [], "sub": []}})
    SK.spec_set("edge_rules", [
        {"level": "L1", "side": "S", "span": [0.0, 6.0], "kind": "CANTILEVER", "glazed": True},
        {"level": "L1", "side": "E", "span": [0.0, 4.0], "kind": "CANTILEVER", "glazed": True},
    ])
    FK.build_all_levels(wall_t=0.28)
    cant_audit = COR.audit_scene_meshes(check_clashes=True)
    assert cant_audit["passed"] and cant_audit["clash_count"] == 0, f"Cantilever glazed corner clash: {cant_audit}"
    print("[PASS] test_clash_and_topology_auto_hide_regen")


def test_two_stage_vlm_renders(work_dir):
    _reset_scene()
    col = COR.get_or_create_collection("VLM_Test")
    mat_wall = COR.make_pbr_material("Mat_Wall", (0.85, 0.82, 0.78, 1.0), metallic=0.0, roughness=0.75)
    mat_wood = COR.make_pbr_material("Mat_Wood", (0.45, 0.28, 0.14, 1.0), metallic=0.0, roughness=0.55)
    mat_glass = COR.make_pbr_material("Mat_Glass", (0.65, 0.82, 0.90, 0.35), metallic=0.0, roughness=0.08, alpha=0.35)

    bm1 = bmesh.new()
    bmesh.ops.create_cube(bm1, size=1.0)
    bmesh.ops.scale(bm1, vec=(4.0, 0.25, 2.4), verts=bm1.verts)
    bmesh.ops.translate(bm1, vec=(0.0, 1.5, 1.2), verts=bm1.verts)
    COR.create_mesh_object("Wall_Back", bm1, col, mat=mat_wall, bevel_width=0.0)

    bm2 = bmesh.new()
    bmesh.ops.create_cube(bm2, size=1.0)
    bmesh.ops.scale(bm2, vec=(4.4, 3.6, 0.20), verts=bm2.verts)
    bmesh.ops.translate(bm2, vec=(0.0, 0.0, -0.10), verts=bm2.verts)
    COR.create_mesh_object("Floor_Wood", bm2, col, mat=mat_wood, bevel_width=0.0)

    bm3 = bmesh.new()
    bmesh.ops.create_cube(bm3, size=1.0)
    bmesh.ops.scale(bm3, vec=(1.8, 0.04, 1.8), verts=bm3.verts)
    bmesh.ops.translate(bm3, vec=(0.0, -1.2, 0.9), verts=bm3.verts)
    COR.create_mesh_object("Window_Glass", bm3, col, mat=mat_glass, bevel_width=0.0)

    vlm_dir = os.path.join(work_dir, "vlm_two_stage")
    r1 = COR.render_vlm_verification_views(
        vlm_dir, round_stage="r1_shaded", names=["Cam_Iso"], convention="plan_north_up", resolution=(320, 240)
    )
    assert r1["round_stage"] == "r1_shaded"
    assert r1["engine"] == "BLENDER_WORKBENCH"
    assert bpy.context.scene.display.shading.color_type == "RANDOM"
    p1 = r1["renders"]["Cam_Iso"]
    assert os.path.exists(p1) and os.path.getsize(p1) > 1000, f"Missing/empty r1 render: {p1}"

    r2 = COR.render_vlm_verification_views(
        vlm_dir, round_stage="r2_lit", names=["Cam_Iso"], resolution=(320, 240)
    )
    assert r2["round_stage"] == "r2_lit"
    assert r2["engine"] == "BLENDER_EEVEE"
    assert bpy.context.scene.display.shading.color_type == "MATERIAL"
    for lname in ("Key_Sun", "Fill_Sun", "Rim_Sun"):
        assert lname in bpy.data.objects and bpy.data.objects[lname].type == "LIGHT", f"Missing light {lname}"
    assert bpy.context.scene.world is not None and bpy.context.scene.world.node_tree is not None
    assert any(n.type == "BACKGROUND" for n in bpy.context.scene.world.node_tree.nodes)
    p2 = r2["renders"]["Cam_Iso"]
    assert os.path.exists(p2) and os.path.getsize(p2) > 1000, f"Missing/empty r2 render: {p2}"
    print("[PASS] test_two_stage_vlm_renders")


def main():
    with tempfile.TemporaryDirectory(prefix="agy_v14_blender_") as tmp:
        os.environ["AGY_WORK_DIR"] = tmp
        test_wall_with_openings(tmp)
        test_slab_with_courtyard_hole(tmp)
        test_cantilever_heb220_and_detail_audit(tmp)
        test_multi_level_build_verify_render_errors_and_site_yaw(tmp)
        test_benchmark_3000_objects(tmp)
        test_clash_and_topology_auto_hide_regen(tmp)
        test_two_stage_vlm_renders(tmp)
    print("test_blender_suite: ALL PASS")


if __name__ == "__main__":
    main()
