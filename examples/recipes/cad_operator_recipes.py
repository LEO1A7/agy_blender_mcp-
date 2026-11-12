"""[RECIPE_CAD_KIT] BMesh 参数化 CAD 算子全集 · 纯 BMesh 拓扑体检 · 5 机位 Workbench 摄影棚 · 构件状态感知与微调
- 适用 (When): 需一站式导入或按行切片查阅场景/随机分色与材质交付(L19)、拓扑体检、5大BMesh算子、5机位摄影棚、构件AABB感知与微调
- 用法 (How) : 优先 `head -n 6 examples/recipes/case_r*.py` 按子模块调取；或 `sys.path.append(".../examples/recipes"); import cad_operator_recipes`
- 产出 (Out) : 提供闭合流形 BMesh 构造、0 非流形体检报告、1:1 正交+双等轴测 5 机位及无损几何替换/位姿微调
"""

import json
import math
import os
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler


# ==============================================================================
# 1. SCENE, COLLECTION, HIERARCHY & MATERIAL MANAGEMENT
# ==============================================================================

def setup_clean_scene(root_collection_name="CAD_Model_Root"):
    """Deletes ALL objects (hidden/excluded included), purges orphan datablocks, sets metric units (1.0m).

    Uses the data API instead of `bpy.ops.object.delete`, which raises a poll error when Blender is in
    Edit/Sculpt mode or the active object is hidden — the usual state of an interactive MCP session.
    """
    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    set_shading_color_mode('RANDOM')

    root_col = get_or_create_collection(root_collection_name)
    return scene, root_col


def get_or_create_collection(name, parent=None):
    """Creates or retrieves a Blender collection under `parent` (or scene root)."""
    scene = bpy.context.scene
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
    else:
        col = bpy.data.collections.new(name)
        if parent is None:
            scene.collection.children.link(col)
        else:
            parent.children.link(col)
    return col


def clear_collection(col):
    """Removes all objects inside a collection for clean iterative rebuilding (and their orphaned
    camera/light datablocks, so repeated studio setups do not leak `Cam_Iso.001`-style data)."""
    for obj in list(col.objects):
        data = obj.data
        d_name = data.name if data is not None else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if d_name:
            for coll in (bpy.data.cameras, bpy.data.lights, bpy.data.meshes):
                if d_name in coll and coll[d_name].users == 0:
                    coll.remove(coll[d_name])


def link_exclusively(obj, col):
    """Links `obj` exclusively to collection `col`."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def set_parent_keep_world(child_obj, parent_obj):
    """Parents `child_obj` to `parent_obj` with zero world-space offset."""
    child_obj.parent = parent_obj
    child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()


def make_pbr_material(name, rgba, metallic=0.2, roughness=0.55, alpha=None):
    """Creates or updates a Principled BSDF material and sets viewport diffuse color (accepts 3-tuple RGB or 4-tuple RGBA)."""
    color4 = (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]) if len(rgba) >= 4 else (float(alpha) if alpha is not None else 1.0))
    if alpha is not None:
        color4 = (color4[0], color4[1], color4[2], float(alpha))
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color4
        bsdf.inputs["Metallic"].default_value = float(metallic)
        bsdf.inputs["Roughness"].default_value = float(roughness)
        if "Alpha" in bsdf.inputs and color4[3] < 1.0:
            bsdf.inputs["Alpha"].default_value = color4[3]
    mat.diffuse_color = color4
    return mat


def add_angle_bevel(obj, width=0.008, segments=2, angle_deg=30.0):
    """Adds a non-destructive angle-limited Bevel modifier to highlight hard edges."""
    bev = obj.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = width
    bev.segments = segments
    bev.limit_method = 'ANGLE'
    bev.angle_limit = math.radians(angle_deg)
    return bev


def _thin_safe_bevel(bm, requested):
    """Clamp a requested bevel width to 30% of the 10th-percentile edge length of `bm` so thin members
    (louver blades, 12 mm rails, battens) are not rounded into mush by a fixed 8 mm bevel."""
    lengths = sorted(e.calc_length() for e in bm.edges if e.calc_length() > 1e-5)
    if not lengths:
        return 0.0
    w = min(requested, 0.3 * lengths[len(lengths) // 10])
    return w if w >= 0.0005 else 0.0


def create_mesh_object(name, bm, col, mat=None, bevel_width=0.008, bevel_segments=2, thin_safe=True):
    """
    Converts a BMesh `bm` into a Blender Mesh Object, frees `bm`, and applies an angle-limited bevel.

    `thin_safe=True` (default) clamps `bevel_width` to the object's thinnest features; pass
    `thin_safe=False` to force the exact width. `mat` may be a single material or a list of materials
    (slots map to face.material_index).
    """
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    if bevel_width > 0 and thin_safe:
        bevel_width = _thin_safe_bevel(bm, bevel_width)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    link_exclusively(obj, col)
    if mat is not None:
        for m in (mat if isinstance(mat, (list, tuple)) else [mat]):
            obj.data.materials.append(m)
    if bevel_width > 0:
        add_angle_bevel(obj, width=bevel_width, segments=bevel_segments)
    return obj


def _sync_shading_color_type(color_type: str, outline: bool = True):
    """Syncs `color_type` ('RANDOM' | 'MATERIAL') across Workbench render and all 3D Viewports."""
    scene = bpy.context.scene
    if hasattr(scene, "display") and hasattr(scene.display, "shading"):
        scene.display.shading.color_type = color_type
        if outline:
            scene.display.shading.show_object_outline = True
    for s in getattr(bpy.data, "screens", []):
        for a in s.areas:
            if a.type == 'VIEW_3D':
                for sp in a.spaces:
                    if sp.type == 'VIEW_3D':
                        sp.shading.color_type = color_type
                        if outline:
                            sp.shading.show_object_outline = True


def set_shading_color_mode(mode='RANDOM') -> dict:
    """
    Switches Workbench & 3D Viewport shading color mode:
      - `'RANDOM'` (or True): Blender built-in random per-object color for geometry verification
      - `'MATERIAL'` (or False): PBR material color for material observation & final delivery
    """
    if isinstance(mode, bool):
        ctype = 'RANDOM' if mode else 'MATERIAL'
    elif isinstance(mode, str):
        ctype = mode.upper()
    else:
        raise ValueError(f"mode must be 'RANDOM', 'MATERIAL', or bool, got {mode!r}")
    if ctype not in ('RANDOM', 'MATERIAL'):
        raise ValueError(f"mode must be 'RANDOM' or 'MATERIAL', got {mode!r}")

    _sync_shading_color_type(ctype, outline=True)
    return {
        "shading_color_type": ctype,
        "diagnostic_mode": ctype == 'RANDOM',
    }


set_diagnostic_color_mode = set_shading_color_mode


def _resolve_mat(val):
    if isinstance(val, str):
        mat = bpy.data.materials.get(val)
        if mat is None:
            raise ValueError(f"Material not found: {val!r}")
        return mat
    return val


def finish_materials(rules: dict = None, default=None, ignore_prefixes=("Studio", "Cam_", "BBOX_")) -> dict:
    """Assign materials to MESH objects by prefix/fnmatch rules, apply optional `default` to unmatched
    meshes lacking a material, and switch viewport shading to `'MATERIAL'`."""
    import fnmatch
    resolved = [(k, _resolve_mat(v)) for k, v in (rules or {}).items()]
    wildcard_rules = [(k, m) for k, m in resolved if "*" in k or "?" in k]
    prefix_rules = sorted([(k, m) for k, m in resolved if "*" not in k and "?" not in k], key=lambda kv: -len(kv[0]))
    default_mat = _resolve_mat(default) if default is not None else None

    assigned, kept_existing = 0, 0
    unmatched = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or any(obj.name.startswith(p) for p in ignore_prefixes):
            continue
        matched_mat = None
        for pat, mat in wildcard_rules:
            if fnmatch.fnmatch(obj.name, pat):
                matched_mat = mat
                break
        if matched_mat is None:
            for pref, mat in prefix_rules:
                if obj.name.startswith(pref):
                    matched_mat = mat
                    break
        if matched_mat is not None:
            obj.data.materials.clear()
            obj.data.materials.append(matched_mat)
            for poly in obj.data.polygons:
                poly.material_index = 0
            assigned += 1
        else:
            unmatched.append(obj.name)
            has_mat = any(m is not None for m in obj.data.materials)
            if has_mat:
                kept_existing += 1
            elif default_mat is not None:
                obj.data.materials.clear()
                obj.data.materials.append(default_mat)
                for poly in obj.data.polygons:
                    poly.material_index = 0

    _sync_shading_color_type('MATERIAL', outline=True)
    return {
        "assigned": assigned,
        "kept_existing": kept_existing,
        "unmatched": unmatched,
        "shading_color_type": "MATERIAL",
    }


# ==============================================================================
# 2. PURE-BMESH TOPOLOGY & TRANSFORM AUDIT (ZERO EXTERNAL DEPENDENCIES)
# ==============================================================================

def _island_stats(bm):
    """Connected components of `bm` -> list of (face_count, signed_volume). Negative volume => inverted normals."""
    seen, islands = set(), []
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        stack, comp = [f0], []
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                for nb in e.link_faces:
                    if nb.index not in seen:
                        seen.add(nb.index)
                        stack.append(nb)
        vol = 0.0
        for f in comp:
            vs = f.verts
            for k in range(1, len(vs) - 1):
                vol += vs[0].co.dot(vs[k].co.cross(vs[k + 1].co)) / 6.0
        islands.append((len(comp), vol))
    return islands


def audit_object_topology(obj, allow_open=False) -> dict:
    """
    Audits a single Blender Mesh object for:
      - Unapplied scale != (1, 1, 1)
      - Non-manifold edges (must be 0 for watertight solids; pass allow_open=True for intentional
        single-sheet parts such as glass panes / gratings)
      - Degenerate zero-area faces (< 1e-7 m^2)
      - Isolated loose vertices
      - Inverted shells (negative signed volume => normals point inward)
    Also reports `islands` (separate solids merged in the mesh) for information.
    """
    if not obj or obj.type != 'MESH':
        return {"object": getattr(obj, "name", None), "passed": True, "issues": [], "verts": 0, "faces": 0}

    issues = []
    s = obj.scale
    if not (abs(s.x - 1.0) < 1e-4 and abs(s.y - 1.0) < 1e-4 and abs(s.z - 1.0) < 1e-4):
        issues.append(f"Unapplied scale ({s.x:.3f}, {s.y:.3f}, {s.z:.3f}) != (1,1,1)")

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.index_update()

    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    zero_area = sum(1 for f in bm.faces if f.calc_area() < 1e-7)
    loose_verts = sum(1 for v in bm.verts if len(v.link_edges) == 0)
    islands = _island_stats(bm) if len(bm.faces) < 60000 else []
    bm.free()

    inverted = sum(1 for _, vol in islands if vol < -1e-9)
    if non_manifold > 0 and not allow_open:
        issues.append(f"{non_manifold} non-manifold edges")
    if zero_area > 0:
        issues.append(f"{zero_area} zero-area faces")
    if loose_verts > 0:
        issues.append(f"{loose_verts} isolated vertices")
    if inverted > 0 and non_manifold == 0:
        issues.append(f"{inverted} inverted shell(s) (negative volume — normals point inward)")

    return {
        "object": obj.name,
        "passed": len(issues) == 0,
        "issues": issues,
        "verts": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "islands": len(islands),
    }


def audit_scene_meshes(expected_names: list = None, allow_open_patterns=("*glass*", "*pane*", "*grating*")) -> dict:
    """
    Runs `audit_object_topology` across all scene meshes and optionally checks against
    an `expected_names` checklist to detect any omitted parts. Objects whose name matches
    `allow_open_patterns` may be open sheets (glass panes etc.).
    """
    import fnmatch
    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.startswith("BBOX_")]
    defective = []
    total_verts = 0
    total_faces = 0

    for obj in mesh_objs:
        open_ok = any(fnmatch.fnmatch(obj.name.lower(), p) for p in allow_open_patterns)
        res = audit_object_topology(obj, allow_open=open_ok)
        total_verts += res["verts"]
        total_faces += res["faces"]
        if not res["passed"]:
            defective.append(res)

    live_names = {o.name for o in mesh_objs}
    missing = [name for name in (expected_names or []) if name not in live_names]

    return {
        "passed": (len(defective) == 0 and len(missing) == 0),
        "mesh_count": len(mesh_objs),
        "total_verts": total_verts,
        "total_faces": total_faces,
        "defective_count": len(defective),
        "defective_objects": defective,
        "failed_objects": [d["object"] for d in defective],
        "missing_parts": missing,
    }


# ==============================================================================
# 3. FIVE CORE BMESH PARAMETRIC GEOMETRY BUILDERS
# ==============================================================================

def extrude_side_profile(profile_yz, half_width_x, nose_taper_indices=None, nose_half_width_x=None):
    """
    Builder 1: Extrudes a 2D (Y, Z) side profile symmetrically across X in [-half_width_x, +half_width_x].
    Optionally tapers specified vertex indices (e.g., front nose beak) to `nose_half_width_x`.
    Returns a manifold BMesh.
    """
    bm = bmesh.new()
    verts_neg = [bm.verts.new((-half_width_x, y, z)) for (y, z) in profile_yz]
    verts_pos = [bm.verts.new(( half_width_x, y, z)) for (y, z) in profile_yz]

    if nose_taper_indices and nose_half_width_x is not None:
        for idx in nose_taper_indices:
            verts_neg[idx].co.x = -nose_half_width_x
            verts_pos[idx].co.x =  nose_half_width_x

    bm.faces.new(verts_neg)
    bm.faces.new(list(reversed(verts_pos)))
    n = len(profile_yz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([verts_neg[i], verts_pos[i], verts_pos[j], verts_neg[j]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_wavy_skirt_panels(
    col,
    mat,
    panel_splits_y,
    bottom_control_pts_yz,
    top_z_fn,
    outer_x=1.735,
    front_thickness=0.065,
    std_thickness=0.045,
    subdivisions_per_panel=8,
    prefix="Hull_SideSkirt",
):
    """
    Builder 2: Generates segmented left/right side skirt armor plates with a cosine-interpolated
    wavy bottom edge and panel seam gaps.
    """
    def interp_bottom_z(y_val):
        for k in range(len(bottom_control_pts_yz) - 1):
            ya, za = bottom_control_pts_yz[k]
            yb, zb = bottom_control_pts_yz[k + 1]
            if ya <= y_val <= yb:
                t = (y_val - ya) / max(1e-6, (yb - ya))
                t_smooth = 0.5 - 0.5 * math.cos(t * math.pi)
                return za + t_smooth * (zb - za)
        return bottom_control_pts_yz[-1][1]

    created = []
    for side_sign, side_tag in [(-1.0, "R"), (1.0, "L")]:
        for p_idx in range(len(panel_splits_y) - 1):
            ya = panel_splits_y[p_idx]
            yb = panel_splits_y[p_idx + 1] - 0.015  # 15mm seam gap between panels
            ys = [ya + (yb - ya) * (i / subdivisions_per_panel) for i in range(subdivisions_per_panel + 1)]

            bm = bmesh.new()
            thick = front_thickness if p_idx < 2 else std_thickness
            x_out = side_sign * outer_x
            x_in = side_sign * (outer_x - thick)

            ring_out, ring_in = [], []
            for yv in ys:
                zb = interp_bottom_z(yv)
                ring_out.append(bm.verts.new((x_out, yv, zb)))
                ring_in.append(bm.verts.new((x_in, yv, zb)))
            for yv in reversed(ys):
                zt = top_z_fn(yv)
                ring_out.append(bm.verts.new((x_out, yv, zt)))
                ring_in.append(bm.verts.new((x_in, yv, zt)))

            bm.faces.new(ring_out)
            bm.faces.new(list(reversed(ring_in)))
            m_len = len(ring_out)
            for i in range(m_len):
                j = (i + 1) % m_len
                bm.faces.new([ring_out[i], ring_in[i], ring_in[j], ring_out[j]])

            obj = create_mesh_object(
                f"{prefix}_{side_tag}_{p_idx+1}", bm, col, mat,
                bevel_width=0.006,
            )
            created.append(obj)
    return created


def build_layered_polyhedral_shell(layer_bot, layer_mid, layer_top):
    """
    Builder 3: Lofts a 3-layer polyhedral shell (bottom skirt chine, mid widest crease, top roof edge)
    and caps both top and bottom using explicit transverse planar quads (avoiding N-gon shading creases).
    Assumes vertices 0..N-1 are ordered symmetrically from front-right around rear to front-left (N even).
    """
    bm = bmesh.new()
    v_bot = [bm.verts.new(co) for co in layer_bot]
    v_mid = [bm.verts.new(co) for co in layer_mid]
    v_top = [bm.verts.new(co) for co in layer_top]

    n_st = len(layer_bot)
    for i in range(n_st):
        j = (i + 1) % n_st
        bm.faces.new([v_bot[i], v_bot[j], v_mid[j], v_mid[i]])
        bm.faces.new([v_mid[i], v_mid[j], v_top[j], v_top[i]])

    # Transverse planar quad caps pairing station k with station (n_st - 1 - k)
    half_n = n_st // 2
    pairs = [(k, n_st - 1 - k) for k in range(half_n)]
    for k in range(len(pairs) - 1):
        a0, b0 = pairs[k]
        a1, b1 = pairs[k + 1]
        bm.faces.new([v_top[a0], v_top[b0], v_top[b1], v_top[a1]])
        bm.faces.new([v_bot[a1], v_bot[b1], v_bot[b0], v_bot[a0]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def add_cyl_along_y(bm, y_start, y_end, r_start, r_end, x_center=0.0, z_center=0.0, segs=32):
    """
    Builder 4: Adds a coaxial or offset conical/cylindrical segment along the Y axis into `bm`.
    """
    length = abs(y_end - y_start)
    yc = 0.5 * (y_start + y_end)
    g = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segs,
        radius1=r_start, radius2=r_end, depth=length
    )
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-90), 3, 'X'), verts=g["verts"])
    bmesh.ops.translate(bm, vec=(x_center, yc, z_center), verts=g["verts"])
    return g


def build_contoured_track_loop(
    loop_pts_yz,
    x_center,
    track_width=0.635,
    belt_thickness=0.042,
    loop_interior_yz=(0.0, 0.55),
    add_grousers=True,
):
    """
    Builder 5: Sweeps a closed track belt along `loop_pts_yz` using tangent-normal frames,
    and attaches dual exterior track shoes (grousers) + interior center guide horns.
    """
    bm = bmesh.new()
    half_tw = track_width * 0.5
    n_pts = len(loop_pts_yz)
    rings = []
    interior_pt = Vector(loop_interior_yz)

    for i in range(n_pts):
        p_prev = Vector(loop_pts_yz[(i - 1) % n_pts])
        p_curr = Vector(loop_pts_yz[i])
        p_next = Vector(loop_pts_yz[(i + 1) % n_pts])
        tangent = (p_next - p_prev).normalized()
        normal = Vector((tangent.y, -tangent.x)).normalized()
        if normal.dot(p_curr - interior_pt) < 0:
            normal = -normal

        p_in = p_curr - normal * (belt_thickness * 0.5)
        p_out = p_curr + normal * (belt_thickness * 0.5)

        v0 = bm.verts.new((x_center - half_tw, p_in.x, p_in.y))
        v1 = bm.verts.new((x_center + half_tw, p_in.x, p_in.y))
        v2 = bm.verts.new((x_center + half_tw, p_out.x, p_out.y))
        v3 = bm.verts.new((x_center - half_tw, p_out.x, p_out.y))
        rings.append((v0, v1, v2, v3, p_out, normal, tangent))

    for i in range(n_pts):
        j = (i + 1) % n_pts
        rA, rB = rings[i], rings[j]
        for k in range(4):
            k2 = (k + 1) % 4
            bm.faces.new([rA[k], rB[k], rB[k2], rA[k2]])

    if add_grousers:
        shoe_offset = track_width * 0.26
        shoe_w = track_width * 0.43
        for i in range(n_pts):
            _, _, _, _, p_out, normal, tangent = rings[i]
            ang_x = math.atan2(tangent.y, tangent.x)
            for shoe_dx in [-shoe_offset, shoe_offset]:
                g_pad = bmesh.ops.create_cube(bm, size=1.0)
                bmesh.ops.scale(bm, vec=(shoe_w, 0.085, 0.024), verts=g_pad["verts"])
                bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(ang_x, 3, 'X'), verts=g_pad["verts"])
                pos_yz = p_out + normal * 0.012
                bmesh.ops.translate(bm, vec=(x_center + shoe_dx, pos_yz.x, pos_yz.y), verts=g_pad["verts"])

            g_tooth = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(0.035, 0.06, 0.065), verts=g_tooth["verts"])
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(ang_x, 3, 'X'), verts=g_tooth["verts"])
            pos_in = p_out - normal * (belt_thickness + 0.03)
            bmesh.ops.translate(bm, vec=(x_center, pos_in.x, pos_in.y), verts=g_tooth["verts"])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# ==============================================================================
# 4. UNIFIED WORKBENCH STUDIO (AUTO-FRAMED ORTHO VIEWS + AUTO-LOCKED ISO + CLOSE-UPS)
# ==============================================================================

# Image-axis mapping of each camera, per drawing convention. Read it BEFORE comparing renders with a
# blueprint; the wrong convention silently mirrors asymmetric features.
VIEW_AXES = {
    "vehicle": {   # vehicle nose = -Y, port/left = +X
        "Cam_Side_Left": "camera +X looking -X | image left=-Y(front) right=+Y(rear) up=+Z",
        "Cam_Top":       "camera +Z looking -Z | image up=-X(starboard) right=+Y(rear) [plan rotated 90deg]",
        "Cam_Front":     "camera -Y looking +Y | image left=-X right=+X up=+Z",
    },
    "plan_north_up": {   # architecture: plan north-up (+Y), south elevation from -Y
        "Cam_Top":        "camera +Z looking -Z | image up=+Y(north) right=+X(east)",
        "Cam_Front":      "camera -Y looking +Y (south elevation) | image left=-X right=+X up=+Z",
        "Cam_Back":       "camera +Y looking -Y (north elevation) | image left=+X right=-X up=+Z",
        "Cam_Side_Left":  "camera -X looking +X (west elevation) | image left=+Y right=-Y(south) up=+Z",
        "Cam_Side_Right": "camera +X looking -X (east elevation) | image left=-Y(south) right=+Y up=+Z",
    },
}
LAST_STUDIO_META = {}


def scene_bounds():
    """World AABB (min, max) of all renderable mesh objects, or None for an empty scene."""
    bpy.context.view_layer.update()
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    found = False
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name.startswith("BBOX_") or o.hide_render:
            continue
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            mn = Vector((min(mn.x, w.x), min(mn.y, w.y), min(mn.z, w.z)))
            mx = Vector((max(mx.x, w.x), max(mx.y, w.y), max(mx.z, w.z)))
            found = True
    return (mn, mx) if found else None


def compute_or_lock_iso_distance(
    target_center=(0.0, -0.5, 1.35),
    default_d=9.5,
    lock_file=None,
    force_relock=False,
    lens=50.0,
    sensor_width=36.0,
    margin=1.08,
) -> float:
    """
    Computes the iso-camera offset `d` (cameras sit at target + (±d, ±d, 0.55 d)) so the scene's bounding
    sphere fits the lens FOV: distance = R / sin(half_fov) * margin, |offset| = d * sqrt(2.3025).

    A lock file keeps `d` stable across modelling iterations for pixel-comparable renders. The lock is
    only reused when its target_center and lens match; otherwise it is recomputed (a stale lock used to
    leave the model cropped after the target moved).
    """
    center_vec = Vector(target_center)
    if lock_file and not force_relock and os.path.isfile(lock_file):
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            same_c = (Vector(data.get("target_center", (1e9, 1e9, 1e9))) - center_vec).length < 1e-3
            same_l = abs(float(data.get("lens_mm", -1)) - lens) < 1e-6
            if "distance_d" in data and same_c and same_l:
                return float(data["distance_d"])
        except Exception:
            pass

    d = default_d
    b = scene_bounds()
    if b:
        max_r = 0.0
        for o in bpy.data.objects:
            if o.type != 'MESH' or o.name.startswith("BBOX_") or o.hide_render:
                continue
            for corner in o.bound_box:
                max_r = max(max_r, ((o.matrix_world @ Vector(corner)) - center_vec).length)
        if max_r > 0.05:
            half_fov = math.atan((sensor_width * 0.5) / lens)
            dist = max_r / math.sin(half_fov) * margin
            d = max(round(dist / math.sqrt(2.0 + 0.55 ** 2), 3), 0.5)

    if lock_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(lock_file)), exist_ok=True)
            with open(lock_file, "w", encoding="utf-8") as f:
                json.dump({
                    "distance_d": d,
                    "lens_mm": lens,
                    "sensor_width_mm": sensor_width,
                    "target_center": list(target_center),
                }, f, indent=2)
        except Exception:
            pass

    return d


def _fit_ortho(h_extent, v_extent, res, margin=1.08):
    """Blender's ortho_scale spans the LARGER image dimension. Return the scale that frames an
    h_extent x v_extent (metres) region in a res=(w, h) image."""
    aspect = res[0] / float(res[1])
    if aspect >= 1.0:
        return max(h_extent, v_extent * aspect) * margin
    return max(v_extent, h_extent / aspect) * margin


def setup_workbench_studio_and_cameras(
    col_studio=None,
    target_center=None,
    ortho_span=None,
    front_span=None,
    scale_m_per_px=None,
    view_crops=None,
    crop_boxes_px=None,
    center_x=None,
    center_y=None,
    center_z=None,
    iso_lock_file=None,
    force_relock_iso=False,
    iso_lens=50.0,
    diagnostic_colors=None,
    convention="vehicle",
    standoff=None,
    with_lights=False,
    resolution=(1280, 960),
    views=None,
):
    """
    Unified Stage 4 Studio & Camera Rig (Workbench Cavity + Object Outline, flat light-grey background).

    convention = "vehicle"        : nose -Y; cameras Cam_Side_Left(+X), Cam_Top(rotated plan), Cam_Front, Cam_Iso(SE), Cam_Iso_Rear(NW)
                 "plan_north_up"  : architecture; Cam_Top north-up, Cam_Front(S), Cam_Back(N), Cam_Side_Left(W), Cam_Side_Right(E),
                                    Cam_Iso(SW), Cam_Iso_SE, Cam_Iso_Rear(NE), Cam_Iso_NW
    target_center / ortho spans : default to the live scene bounds (auto-framed); camera stand-off defaults to
                 max(15 m, 1.6 x model size) so large buildings are never cut by a camera inside the model.
    scale_m_per_px + view_crops : dict {"side"|"top"|"front": (u0, v0, u1, v1)} -> exact 1:1 framing
                 (ortho_scale = max(w_px, h_px) * s, per-view resolution = crop size, applied by `render_views`).
    views       : optional list of camera names to create (default: all of the convention).
    Returns {camera_name: camera_object}. `describe_studio()` returns axis mapping + per-view resolution.
    """
    if convention not in VIEW_AXES:
        raise ValueError(f"convention must be one of {list(VIEW_AXES)}")
    if col_studio is None:
        col_studio = get_or_create_collection("Studio")
    elif isinstance(col_studio, str):
        col_studio = get_or_create_collection(col_studio)
    clear_collection(col_studio)
    scene = bpy.context.scene

    if view_crops is None and crop_boxes_px is not None:
        view_crops = crop_boxes_px

    b = scene_bounds()
    if target_center is None:
        default_c = tuple((b[0] + b[1]) * 0.5) if b else (0.0, -0.5, 1.35)
        target_center = (
            default_c[0] if center_x is None else float(center_x),
            default_c[1] if center_y is None else float(center_y),
            default_c[2] if center_z is None else float(center_z),
        )
    xc, yc, zc = target_center
    ext = (b[1] - b[0]) if b else Vector((10.0, 10.0, 3.0))
    max_ext = max(ext.x, ext.y, ext.z)
    if standoff is None:
        standoff = max(15.0, 1.6 * max_ext)
        if b:
            standoff = max(standoff, 0.5 * max(ext.x, ext.y) + 5.0, ext.z * 0.5 + 5.0)

    if with_lights:
        lights_spec = [
            ("Key_Sun",  ( 8.0, -8.0, 12.0), (38.0,  15.0, -35.0), 3.2),
            ("Fill_Sun", (-8.0,  6.0,  9.0), (48.0, -20.0, 140.0), 1.4),
            ("Rim_Sun",  ( 0.0, 10.0,  8.0), (-42.0,  0.0,   0.0), 1.1),
        ]
        for lname, loc, rot_deg, energy in lights_spec:
            ldata = bpy.data.lights.new(name=lname, type='SUN')
            ldata.energy = energy
            ldata.angle = math.radians(8.0)
            lobj = bpy.data.objects.new(name=lname, object_data=ldata)
            lobj.location = loc
            lobj.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
            link_exclusively(lobj, col_studio)

    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    if diagnostic_colors is None:
        cur = getattr(scene.display.shading, "color_type", "RANDOM")
        ctype = cur if cur in ('RANDOM', 'MATERIAL') else 'RANDOM'
    elif isinstance(diagnostic_colors, str) and diagnostic_colors.upper() in ('RANDOM', 'MATERIAL'):
        ctype = diagnostic_colors.upper()
    else:
        raise ValueError("diagnostic_colors must be None, 'RANDOM', or 'MATERIAL'")
    _sync_shading_color_type(ctype, outline=True)
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.cavity_ridge_factor = 1.0
    scene.display.shading.cavity_valley_factor = 1.0
    scene.display.shading.show_object_outline = True
    scene.display.shading.object_outline_color = (0.05, 0.05, 0.05)
    scene.display.shading.show_shadows = True
    scene.display.shading.shadow_intensity = 0.35
    scene.render.film_transparent = False
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = (0.94, 0.94, 0.93)

    clip_end = max(200.0, standoff * 6.0)

    def make_cam(name, loc, rot_deg=None, look_at=None, ortho=True, ortho_scale=10.2, lens=50.0):
        stale = bpy.data.objects.get(name)
        if stale:
            bpy.data.objects.remove(stale, do_unlink=True)
        cdata = bpy.data.cameras.new(name)
        cdata.sensor_width = 36.0
        if ortho:
            cdata.type = 'ORTHO'
            cdata.ortho_scale = ortho_scale
        else:
            cdata.type = 'PERSP'
            cdata.lens = lens
        cdata.clip_start = 0.1
        cdata.clip_end = clip_end
        cobj = bpy.data.objects.new(name, cdata)
        cobj.location = Vector(loc)
        if look_at is not None:
            direction = (Vector(look_at) - Vector(loc)).normalized()
            cobj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler('XYZ')
        elif rot_deg is not None:
            cobj.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
        link_exclusively(cobj, col_studio)
        return cobj

    # ---- per-view framing ------------------------------------------------------------------
    crops = view_crops or {}
    per_view_res = {}
    view_key = {"Cam_Side_Left": "side", "Cam_Side_Right": "side", "Cam_Top": "top",
                 "Cam_Front": "front", "Cam_Back": "front"}

    def frame(cam_name, h_ext, v_ext, legacy_span):
        key = view_key[cam_name]
        if scale_m_per_px and key in crops:
            c = crops[key]
            w_px, h_px = c[2] - c[0], c[3] - c[1]
            per_view_res[cam_name] = (int(w_px), int(h_px))
            return max(w_px, h_px) * scale_m_per_px        # ortho_scale spans the LARGER dimension
        if b is not None:
            return _fit_ortho(h_ext, v_ext, resolution)
        return legacy_span if legacy_span is not None else 10.2

    d = compute_or_lock_iso_distance(
        target_center=target_center, default_d=9.2, lock_file=iso_lock_file,
        force_relock=force_relock_iso, lens=iso_lens)

    cams = {}
    if convention == "vehicle":
        spec = [
            ("Cam_Side_Left", (xc + standoff, yc, zc), (90.0, 0.0, 90.0), ext.y, ext.z, ortho_span),
            ("Cam_Top",       (xc, yc, zc + standoff), (0.0, 0.0, 90.0), ext.y, ext.x, ortho_span),
            ("Cam_Front",     (xc, yc - standoff, zc), (90.0, 0.0, 0.0), ext.x, ext.z, front_span),
        ]
        iso_spec = [("Cam_Iso", (xc + d, yc - d, zc + 0.55 * d)), ("Cam_Iso_Rear", (xc - d, yc + d, zc + 0.55 * d))]
    else:
        spec = [
            ("Cam_Top",        (xc, yc, zc + standoff), (0.0, 0.0, 0.0),    ext.x, ext.y, ortho_span),
            ("Cam_Front",      (xc, yc - standoff, zc), (90.0, 0.0, 0.0),   ext.x, ext.z, front_span),
            ("Cam_Back",       (xc, yc + standoff, zc), (90.0, 0.0, 180.0), ext.x, ext.z, front_span),
            ("Cam_Side_Left",  (xc - standoff, yc, zc), (90.0, 0.0, -90.0), ext.y, ext.z, ortho_span),
            ("Cam_Side_Right", (xc + standoff, yc, zc), (90.0, 0.0, 90.0),  ext.y, ext.z, ortho_span),
        ]
        iso_spec = [("Cam_Iso", (xc - d, yc - d, zc + 0.55 * d)), ("Cam_Iso_SE", (xc + d, yc - d, zc + 0.55 * d)),
                    ("Cam_Iso_Rear", (xc + d, yc + d, zc + 0.55 * d)), ("Cam_Iso_NW", (xc - d, yc + d, zc + 0.55 * d))]

    for name, loc, rot, h_e, v_e, legacy in spec:
        if views and name not in views:
            continue
        cams[name] = make_cam(name, loc, rot_deg=rot, ortho=True, ortho_scale=frame(name, h_e, v_e, legacy))
    for name, loc in iso_spec:
        if views and name not in views:
            continue
        cams[name] = make_cam(name, loc, look_at=target_center, ortho=False, lens=iso_lens)

    if cams:
        scene.camera = cams.get("Cam_Iso") or next(iter(cams.values()))
    LAST_STUDIO_META.clear()
    LAST_STUDIO_META.update({
        "convention": convention,
        "target_center": [round(x, 4) for x in target_center],
        "standoff": round(standoff, 3),
        "iso_d": d,
        "resolution_default": list(resolution),
        "resolution_per_view": {k: list(v) for k, v in per_view_res.items()},
        "axes": {k: v for k, v in VIEW_AXES[convention].items() if k in cams},
    })
    return cams


def describe_studio() -> dict:
    """Axis mapping / framing of the last `setup_workbench_studio_and_cameras` call (print it before
    comparing renders with blueprints)."""
    meta = dict(LAST_STUDIO_META)
    yaw_obj = bpy.data.objects.get("Site_Yaw")
    meta["site_yaw_deg"] = round(math.degrees(yaw_obj.rotation_euler.z), 3) if yaw_obj else 0.0
    meta["yaw_note"] = "Orthogonal building frame (+X East, +Y North); Site_Yaw applied at delivery only."
    return meta


_VIEW_FILE_TAG = {"Cam_Side_Left": "side", "Cam_Side_Right": "side_right", "Cam_Top": "top", "Cam_Front": "front",
                  "Cam_Back": "back", "Cam_Iso": "iso", "Cam_Iso_Rear": "iso_rear", "Cam_Iso_SE": "iso_se",
                  "Cam_Iso_NW": "iso_nw"}


def render_views(out_dir, names=None, prefix="render_", transparent=False, resolution=None) -> dict:
    """Render the studio cameras to `out_dir/<prefix><tag>.png` with the per-view resolution that
    matches the blueprint crops (exact 1:1 when `scale_m_per_px`+`view_crops` were given).
    Restores the scene's previous camera/resolution. Returns {camera_name: path}."""
    scene = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    prev = (scene.camera, scene.render.resolution_x, scene.render.resolution_y,
            scene.render.film_transparent, scene.render.filepath)
    per = LAST_STUDIO_META.get("resolution_per_view", {})
    dflt = tuple(resolution or LAST_STUDIO_META.get("resolution_default", (1280, 960)))
    out = {}
    try:
        scene.render.film_transparent = transparent
        scene.render.image_settings.file_format = 'PNG'
        for cam in [o for o in bpy.data.objects if o.type == 'CAMERA' and o.name.startswith("Cam_")]:
            if names and cam.name not in names:
                continue
            res = tuple(per.get(cam.name, dflt)) if not resolution else dflt
            scene.camera = cam
            scene.render.resolution_x, scene.render.resolution_y = res
            path = os.path.join(out_dir, f"{prefix}{_VIEW_FILE_TAG.get(cam.name, cam.name[4:].lower())}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            out[cam.name] = path
    finally:
        (scene.camera, scene.render.resolution_x, scene.render.resolution_y,
         scene.render.film_transparent, scene.render.filepath) = prev
    return out


def render_closeup(out_path, target, size, direction=(0.0, 1.0, 0.0), up=(0.0, 0.0, 1.0),
                   resolution=(1400, 1050), ortho=True, distance=None) -> str:
    """Detail close-up of a region (e.g. a column/beam joint, a louver leaf, a railing corner) for
    verifying section profiles, not just silhouettes.

    target = world point at the image centre, size = metres spanned by the larger image side (ortho),
    direction = view direction (camera looks along it). Uses a temporary camera and removes it.
    """
    scene = bpy.context.scene
    tgt = Vector(target)
    dirn = Vector(direction).normalized()
    dist = distance or max(5.0, size * 3.0)
    cdata = bpy.data.cameras.new("_closeup_tmp")
    cdata.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        cdata.ortho_scale = size
    else:
        cdata.lens = 50.0
    cdata.clip_start, cdata.clip_end = 0.01, dist * 10 + 100
    cam = bpy.data.objects.new("_closeup_tmp", cdata)
    scene.collection.objects.link(cam)
    cam.location = tgt - dirn * dist
    z_axis = -dirn                                   # camera +Z points backwards
    x_axis = Vector(up).cross(z_axis)
    if x_axis.length < 1e-6:                         # looking straight along `up`: pick any right vector
        x_axis = Vector((1.0, 0.0, 0.0)).cross(z_axis)
        if x_axis.length < 1e-6:
            x_axis = Vector((0.0, 1.0, 0.0)).cross(z_axis)
    x_axis.normalize()
    y_axis = z_axis.cross(x_axis)
    cam.rotation_euler = Matrix((x_axis, y_axis, z_axis)).transposed().to_euler()
    prev = (scene.camera, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath)
    try:
        scene.camera = cam
        scene.render.resolution_x, scene.render.resolution_y = resolution
        scene.render.filepath = out_path
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        bpy.ops.render.render(write_still=True)
    finally:
        (scene.camera, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath) = prev
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cdata)
    return out_path


# ==============================================================================
# 5. MCP COMPONENT STATE PERCEPTION & IN-PLACE REFINEMENT (CRUD & TRANSFORMS)
# ==============================================================================

def inspect_scene_components(names=None, collection_name=None) -> dict:
    """
    Extracts precise transform, AABB bounding box, and hierarchy state of scene
    objects via MCP. Returns a structured dict for comparing against visual renders.
    """
    bpy.context.view_layer.update()      # parenting/transform edits are invisible to matrix_world until updated
    if collection_name and collection_name in bpy.data.collections:
        candidates = bpy.data.collections[collection_name].objects
    else:
        candidates = bpy.data.objects

    if names is not None:
        target_names = set(names)
        target_objs = [o for o in candidates if o.name in target_names]
    else:
        target_objs = [o for o in candidates if o.type == 'MESH' and not o.name.startswith("BBOX_")]

    results = {}
    for obj in target_objs:
        world_mat = obj.matrix_world
        loc = world_mat.translation
        corners = [world_mat @ Vector(corner) for corner in obj.bound_box]
        min_x = min(c.x for c in corners)
        max_x = max(c.x for c in corners)
        min_y = min(c.y for c in corners)
        max_y = max(c.y for c in corners)
        min_z = min(c.z for c in corners)
        max_z = max(c.z for c in corners)

        rot_deg = [round(math.degrees(a), 2) for a in obj.rotation_euler]
        dim = [round(max_x - min_x, 4), round(max_y - min_y, 4), round(max_z - min_z, 4)]
        center = [round((min_x + max_x) * 0.5, 4), round((min_y + max_y) * 0.5, 4), round((min_z + max_z) * 0.5, 4)]

        mesh = obj.data if obj.type == 'MESH' else None
        results[obj.name] = {
            "type": obj.type,
            "location_world": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
            "dimensions_aabb": dim,
            "center_aabb": center,
            "bbox_min": [round(min_x, 4), round(min_y, 4), round(min_z, 4)],
            "bbox_max": [round(max_x, 4), round(max_y, 4), round(max_z, 4)],
            "scale": [round(obj.scale.x, 4), round(obj.scale.y, 4), round(obj.scale.z, 4)],
            "rotation_deg": rot_deg,
            "parent": obj.parent.name if obj.parent else None,
            "verts": len(mesh.vertices) if mesh else 0,
            "faces": len(mesh.polygons) if mesh else 0,
            "materials": [m.name for m in mesh.materials if m] if mesh else [],
            "collection": obj.users_collection[0].name if obj.users_collection else None,
        }

    return results


def transform_component(name, delta_loc=None, new_loc=None, scale_factor=None, delta_rot_deg=None, apply_scale=True, translate=None) -> dict:
    """
    In-place translation, scaling, or rotation of an existing component.
    Preserves parent hierarchy; when `apply_scale` the scale is baked into the mesh data directly
    (no `bpy.ops`, so it cannot fail on hidden objects / non-Object modes, and multi-user meshes are
    made single-user first so sibling instances are not distorted).
    """
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Component '{name}' not found"}

    if delta_loc is None and translate is not None:
        delta_loc = translate
    if delta_loc is not None:
        obj.location += Vector(delta_loc)
    if new_loc is not None:
        obj.location = Vector(new_loc)

    if scale_factor is not None:
        if isinstance(scale_factor, (int, float)):
            s_vec = Vector((scale_factor, scale_factor, scale_factor))
        else:
            s_vec = Vector(scale_factor)
        obj.scale = Vector((obj.scale.x * s_vec.x, obj.scale.y * s_vec.y, obj.scale.z * s_vec.z))

    if delta_rot_deg is not None:
        delta_rad = [math.radians(a) for a in delta_rot_deg]
        obj.rotation_euler = Euler([a + b for a, b in zip(obj.rotation_euler, delta_rad)], 'XYZ')

    if apply_scale and obj.type == 'MESH':
        sc = obj.scale
        if abs(sc.x - 1) > 1e-9 or abs(sc.y - 1) > 1e-9 or abs(sc.z - 1) > 1e-9:
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            obj.data.transform(Matrix.Diagonal((sc.x, sc.y, sc.z)).to_4x4())
            obj.data.update()
            obj.scale = (1.0, 1.0, 1.0)

    return inspect_scene_components([name]).get(name, {})


def replace_component_geometry(name, new_bm, bevel_width=None) -> dict:
    """
    Non-destructively replaces the mesh geometry of an existing component with `new_bm`.
    Retains existing object transforms, materials, parenting, and collections.
    """
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != 'MESH':
        return {"error": f"Mesh component '{name}' not found"}

    old_mesh = obj.data
    new_mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bmesh.ops.recalc_face_normals(new_bm, faces=new_bm.faces)
    new_bm.normal_update()
    new_bm.to_mesh(new_mesh)
    new_bm.free()
    for m in old_mesh.materials:          # material slots belong to the Mesh datablock: carry them over
        new_mesh.materials.append(m)

    obj.data = new_mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    if bevel_width is not None:
        bev = next((m for m in obj.modifiers if m.type == 'BEVEL'), None)
        if not bev and bevel_width > 0:
            add_angle_bevel(obj, width=bevel_width)
        elif bev:
            bev.width = bevel_width

    return inspect_scene_components([name]).get(name, {})


def remove_components(names: list) -> dict:
    """
    Safely removes components from the scene and purges orphan mesh datablocks.
    """
    removed = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj:
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            removed.append(name)
    return {"removed": removed, "count": len(removed)}
