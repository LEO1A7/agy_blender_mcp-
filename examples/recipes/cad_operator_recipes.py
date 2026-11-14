"""[RECIPE_CAD_KIT] BMesh 参数化 CAD 算子全集 · 纯 BMesh 拓扑体检 · 5 机位 Workbench 摄影棚 · 构件状态感知与微调
- 适用 (When): 需一站式导入或按行切片查阅场景/随机分色与材质交付(L19)、拓扑体检、5大BMesh算子、5机位摄影棚、构件AABB感知与微调
- 用法 (How) : 优先 `head -n 6 examples/recipes/case_r*.py` 按子模块调取；或 `sys.path.append(".../examples/recipes"); import cad_operator_recipes`
- 产出 (Out) : 提供闭合流形 BMesh 构造、0 非流形体检报告、1:1 正交+双等轴测 5 机位及无损几何替换/位姿微调
"""

import json
import math
import os
import re
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree


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


def _find_principled_bsdf(mat):
    """Locate Principled BSDF node regardless of Blender UI language."""
    if not mat or not getattr(mat, "use_nodes", False) or not mat.node_tree:
        return None
    return (
        next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        or mat.node_tree.nodes.get("Principled BSDF")
    )


def make_pbr_material(name, rgba, metallic=0.2, roughness=0.55, alpha=None):
    """Creates or updates a Principled BSDF material and sets viewport diffuse color (accepts 3-tuple RGB or 4-tuple RGBA)."""
    color4 = (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]) if len(rgba) >= 4 else (float(alpha) if alpha is not None else 1.0))
    if alpha is not None:
        color4 = (color4[0], color4[1], color4[2], float(alpha))
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = _find_principled_bsdf(mat)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color4
        bsdf.inputs["Metallic"].default_value = float(metallic)
        bsdf.inputs["Roughness"].default_value = float(roughness)
        if color4[3] < 1.0:
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = color4[3]
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = round(1.0 - color4[3], 4)
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = 'BLENDED'
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


def create_mesh_object(name, bm, col, mat=None, bevel_width=0.008, bevel_segments=2, thin_safe=True, archive_existing=True):
    """
    Converts a BMesh `bm` into a Blender Mesh Object, frees `bm`, and applies an angle-limited bevel.

    `thin_safe=True` (default) clamps `bevel_width` to the object's thinnest features; pass
    `thin_safe=False` to force the exact width. `mat` may be a single material or a list of materials
    (slots map to face.material_index). When `archive_existing=True`, any existing object named `name`
    is archived in place as `__hide_r<N>__<name>` instead of deleted.
    """
    if name in bpy.data.objects:
        if archive_existing and not name.startswith("_"):
            hide_defective_components([name], reason="recreate_in_place")
        else:
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


def _sync_shading_color_type(color_type: str, outline: bool = True, view_type: str = None):
    """Syncs `color_type` ('RANDOM' | 'MATERIAL') and optional `view_type` across Workbench & 3D Viewports."""
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
                        if view_type:
                            try:
                                sp.shading.type = view_type
                            except Exception:
                                pass
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

    _sync_shading_color_type(ctype, outline=True, view_type='SOLID')
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


def _sync_material_nodes(mat):
    """Ensure material's Principled BSDF Base Color & transparency match `mat.diffuse_color`."""
    if not mat:
        return
    mat.use_nodes = True
    bsdf = _find_principled_bsdf(mat)
    if bsdf:
        dc = tuple(mat.diffuse_color)
        bc = tuple(bsdf.inputs["Base Color"].default_value)
        if bc == (0.8, 0.8, 0.8, 1.0) and dc != (0.8, 0.8, 0.8, 1.0):
            bsdf.inputs["Base Color"].default_value = dc
        if dc[3] < 1.0:
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = dc[3]
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = round(1.0 - dc[3], 4)
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = 'BLENDED'


def finish_materials(
    rules: dict = None,
    default=None,
    ignore_prefixes=("Studio", "Cam_", "BBOX_", "__hide_r", "__wip__", "Site_Yaw"),
) -> dict:
    """Assign materials to active MESH objects by prefix/fnmatch rules, apply optional `default`
    to unmatched meshes lacking a material, sync Principled BSDF nodes, and switch shading to `'MATERIAL'`."""
    import fnmatch
    resolved = [(k, _resolve_mat(v)) for k, v in (rules or {}).items()]
    wildcard_rules = [(k, m) for k, m in resolved if "*" in k or "?" in k]
    prefix_rules = sorted([(k, m) for k, m in resolved if "*" not in k and "?" not in k], key=lambda kv: -len(kv[0]))
    default_mat = _resolve_mat(default) if default is not None else None

    assigned, kept_existing = 0, 0
    unmatched = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.hide_viewport or obj.hide_render or any(obj.name.startswith(p) for p in ignore_prefixes):
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
            _sync_material_nodes(matched_mat)
            obj.data.materials.clear()
            obj.data.materials.append(matched_mat)
            for poly in obj.data.polygons:
                poly.material_index = 0
            assigned += 1
        else:
            unmatched.append(obj.name)
            existing = [m for m in obj.data.materials if m is not None]
            if existing:
                for m in existing:
                    _sync_material_nodes(m)
                kept_existing += 1
            elif default_mat is not None:
                _sync_material_nodes(default_mat)
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
# 2. PURE-BMESH TOPOLOGY, SELF-INTERSECTION & CROSS-OBJECT CLASH AUDIT
# ==============================================================================

_ACTIVE_IGNORE_PREFIXES = ("Studio", "Cam_", "BBOX_", "Site_Yaw", "__hide_r", "__wip__", "_tmp_")


def _is_active_model_mesh(obj, ignore_prefixes=_ACTIVE_IGNORE_PREFIXES) -> bool:
    """Return True if `obj` is an active, visible model MESH (excludes hidden/archived/studio helpers)."""
    if not obj or obj.type != 'MESH' or obj.hide_viewport or obj.hide_render:
        return False
    if any(obj.name.startswith(p) for p in ignore_prefixes):
        return False
    cols = list(obj.users_collection)
    if cols and all(c.name.endswith("_WIP") or any(c.name.startswith(p) for p in ignore_prefixes) for c in cols):
        return False
    return True


def _build_shrunk_bvh_from_bmesh(bm, eps=0.003):
    """Build a BVHTree from an inward-shrunk copy of `bm` to ignore flush surface contacts."""
    if len(bm.faces) == 0:
        return None
    bm.faces.ensure_lookup_table()
    bm_c = bm.copy()
    bm_c.normal_update()
    if eps > 0.0:
        for v in bm_c.verts:
            if v.link_faces:
                n = Vector((0.0, 0.0, 0.0))
                for f in v.link_faces:
                    n += f.normal
                if n.length > 1e-6:
                    n.normalize()
                    min_e = min((e.calc_length() for e in v.link_edges if e.calc_length() > 1e-6), default=eps * 4.0)
                    v.co -= n * min(eps * 1.75, 0.25 * min_e)
    bm_c.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm_c)
    bm_c.free()
    return tree


def _count_self_overlap_pairs(bm, clearance_m=0.002) -> int:
    """Count non-adjacent face pairs within a single BMesh that penetrate or self-intersect."""
    if len(bm.faces) < 2 or len(bm.faces) > 25000:
        return 0
    tree = _build_shrunk_bvh_from_bmesh(bm, eps=clearance_m)
    if tree is None:
        return 0
    bm.faces.ensure_lookup_table()
    count = 0
    for i, j in tree.overlap(tree):
        if i >= j:
            continue
        if set(bm.faces[i].verts).isdisjoint(bm.faces[j].verts):
            count += 1
    return count


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


def audit_object_topology(obj, allow_open=False, check_self_overlap=True, clearance_m=0.002) -> dict:
    """
    Audits a single Blender Mesh object for:
      - Unapplied scale != (1, 1, 1)
      - Non-manifold edges (must be 0 for watertight solids; pass allow_open=True for intentional
        single-sheet parts such as glass panes / gratings)
      - Degenerate zero-area faces (< 1e-7 m^2)
      - Isolated loose vertices
      - Inverted shells (negative signed volume => normals point inward)
      - Intra-object self-overlapping / penetrating face pairs
    """
    if not obj or obj.type != 'MESH':
        return {"object": getattr(obj, "name", None), "passed": True, "issues": [], "verts": 0, "faces": 0, "self_overlap_pairs": 0}

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
    self_overlap = _count_self_overlap_pairs(bm, clearance_m=clearance_m) if check_self_overlap else 0
    bm.free()

    inverted = sum(1 for _, vol in islands if vol < -1e-9)
    if len(mesh.polygons) == 0:
        issues.append("Empty mesh (0 faces)")
    if non_manifold > 0 and not allow_open:
        issues.append(f"{non_manifold} non-manifold edges")
    if zero_area > 0:
        issues.append(f"{zero_area} zero-area faces")
    if loose_verts > 0:
        issues.append(f"{loose_verts} isolated vertices")
    if inverted > 0 and non_manifold == 0:
        issues.append(f"{inverted} inverted shell(s) (negative volume — normals point inward)")
    if self_overlap > 0:
        issues.append(f"{self_overlap} self-overlapping/penetrating face pairs")

    return {
        "object": obj.name,
        "passed": len(issues) == 0,
        "issues": issues,
        "verts": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "islands": len(islands),
        "self_overlap_pairs": self_overlap,
    }


def _clash_priority_key(obj_name: str, aabb_vol: float) -> tuple:
    """Lower tuple = higher structural priority (kept while subordinate overlapping part is regenerated)."""
    low = obj_name.lower()
    if "slab" in low:
        tier = 0
    elif "wall" in low and "recess" not in low and "step" not in low:
        tier = 1
    elif any(k in low for k in ("cantilever", "support", "col", "beam", "heb", "hea", "ipe", "hull", "chassis")):
        tier = 2
    elif any(k in low for k in ("recess", "stepwall")):
        tier = 3
    elif any(k in low for k in ("glaze", "window", "skin", "louver", "slat")):
        tier = 4
    else:
        tier = 5
    dir_rank = 0 if ("_n_" in low or "_s_" in low) else (1 if ("_e_" in low or "_w_" in low) else 2)
    return (tier, dir_rank, -round(aabb_vol, 4), obj_name)


def _world_aabb(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = [min(p[k] for p in pts) for k in range(3)]
    mx = [max(p[k] for p in pts) for k in range(3)]
    vol = max(0.0, mx[0] - mn[0]) * max(0.0, mx[1] - mn[1]) * max(0.0, mx[2] - mn[2])
    return mn, mx, vol


def audit_scene_clashes(
    clearance_m=0.003,
    tolerance_face_pairs=0,
    ignore_prefixes=_ACTIVE_IGNORE_PREFIXES,
    allow_pairs=(),
    auto_hide=False,
) -> dict:
    """Detect cross-object geometric overlaps, penetrations, duplicates, and buried solids via BVHTree.

    Flush boundary contacts (0 mm penetration) are ignored via inward-shrunk BVH (`clearance_m`);
    intersections deeper than `clearance_m` are flagged with primary/defective attribution.
    When `auto_hide=True`, defective objects are automatically hidden as `__hide_r<N>__<name>`.
    """
    import fnmatch
    bpy.context.view_layer.update()
    objs = [o for o in bpy.data.objects if _is_active_model_mesh(o, ignore_prefixes)]
    aabbs = {o.name: _world_aabb(o) for o in objs}
    shrunk_cache = {}
    raw_cache = {}

    def _get_bvh(obj, shrunk=True):
        cache = shrunk_cache if shrunk else raw_cache
        if obj.name not in cache:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.transform(obj.matrix_world)
            if shrunk:
                cache[obj.name] = _build_shrunk_bvh_from_bmesh(bm, eps=clearance_m)
            else:
                bm.normal_update()
                cache[obj.name] = BVHTree.FromBMesh(bm) if len(bm.faces) else None
            bm.free()
        return cache[obj.name]

    def _pair_allowed(a, b):
        for pa, pb in allow_pairs or ():
            if (fnmatch.fnmatch(a, pa) and fnmatch.fnmatch(b, pb)) or (fnmatch.fnmatch(b, pa) and fnmatch.fnmatch(a, pb)):
                return True
        return False

    clashes = []
    for i in range(len(objs)):
        o1 = objs[i]
        mn1, mx1, v1 = aabbs[o1.name]
        for j in range(i + 1, len(objs)):
            o2 = objs[j]
            if _pair_allowed(o1.name, o2.name):
                continue
            mn2, mx2, v2 = aabbs[o2.name]
            ov_mn = [max(mn1[k], mn2[k]) for k in range(3)]
            ov_mx = [min(mx1[k], mx2[k]) for k in range(3)]
            dims = [ov_mx[k] - ov_mn[k] for k in range(3)]
            if any(d <= clearance_m for d in dims):
                continue

            t1, t2 = _get_bvh(o1, True), _get_bvh(o2, True)
            if t1 is None or t2 is None:
                continue
            ov_faces = t1.overlap(t2)
            is_dup = all(abs(mn1[k] - mn2[k]) < 0.002 and abs(mx1[k] - mx2[k]) < 0.002 for k in range(3))
            kind = None
            if len(ov_faces) > tolerance_face_pairs:
                kind = "COINCIDENT_DUPLICATE" if is_dup else "PENETRATION"
            elif is_dup and len(o1.data.vertices) == len(o2.data.vertices) and len(o1.data.vertices) > 0:
                rt2 = _get_bvh(o2, False)
                p0 = o1.matrix_world @ o1.data.vertices[0].co
                if rt2 and rt2.find_nearest(p0, 0.003)[0] is not None:
                    kind = "COINCIDENT_DUPLICATE"
            if kind is None:
                small, large = (o1, o2) if v1 <= v2 else (o2, o1)
                s_mn, s_mx, _ = aabbs[small.name]
                l_mn, l_mx, _ = aabbs[large.name]
                if all(s_mn[k] >= l_mn[k] + clearance_m and s_mx[k] <= l_mx[k] - clearance_m for k in range(3)) and len(small.data.vertices):
                    rt_large = _get_bvh(large, False)
                    probe = Vector(((s_mn[0] + s_mx[0]) * 0.5, (s_mn[1] + s_mx[1]) * 0.5, (s_mn[2] + s_mx[2]) * 0.5))
                    if rt_large:
                        dirs = (
                            Vector((1.0, 0.0, 0.0)), Vector((-1.0, 0.0, 0.0)),
                            Vector((0.0, 1.0, 0.0)), Vector((0.0, -1.0, 0.0)),
                            Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0)),
                        )
                        inside_all = True
                        for rdir in dirs:
                            loc, norm, _, _ = rt_large.ray_cast(probe, rdir, 1e6)
                            if loc is None or norm is None or norm.dot(rdir) <= 1e-4:
                                inside_all = False
                                break
                        if inside_all:
                            kind = "BURIED_INSIDE"
            if kind is None:
                continue

            keep, target = (o1, o2) if _clash_priority_key(o1.name, v1) <= _clash_priority_key(o2.name, v2) else (o2, o1)
            clashes.append({
                "pair": [o1.name, o2.name],
                "kind": kind,
                "overlap_face_pairs": len(ov_faces),
                "overlap_dims_m": [round(d, 4) for d in dims],
                "overlap_bbox": [round(x, 4) for x in (ov_mn + ov_mx)],
                "overlap_vol_aabb_m3": round(dims[0] * dims[1] * dims[2], 6),
                "primary_keep": keep.name,
                "defective_target": target.name,
            })

    defective_targets = sorted({c["defective_target"] for c in clashes})
    hidden = hide_defective_components(defective_targets, reason="clash_detected") if (auto_hide and defective_targets) else None
    return {
        "passed": len(clashes) == 0,
        "checked_objects": len(objs),
        "clash_count": len(clashes),
        "clashes": clashes,
        "defective_targets": defective_targets,
        "hidden": hidden,
    }


def audit_scene_meshes(
    expected_names: list = None,
    allow_open_patterns=("*glass*", "*pane*", "*grating*"),
    check_clashes: bool = True,
    clearance_m: float = 0.003,
    auto_hide_defective: bool = False,
) -> dict:
    """
    Runs `audit_object_topology` (including self-overlap check) and optional `audit_scene_clashes`
    across all active scene meshes, and checks `expected_names` for omitted parts.
    When `auto_hide_defective=True`, defective/clashing objects are archived via `__hide_r<N>__`.
    """
    import fnmatch
    mesh_objs = [o for o in bpy.data.objects if _is_active_model_mesh(o)]
    defective = []
    total_verts = 0
    total_faces = 0

    for obj in mesh_objs:
        open_ok = any(fnmatch.fnmatch(obj.name.lower(), p) for p in allow_open_patterns)
        res = audit_object_topology(obj, allow_open=open_ok, clearance_m=min(0.002, clearance_m))
        total_verts += res["verts"]
        total_faces += res["faces"]
        if not res["passed"]:
            defective.append(res)

    live_names = {o.name for o in mesh_objs}
    missing = [name for name in (expected_names or []) if name not in live_names]
    clash_res = audit_scene_clashes(clearance_m=clearance_m) if check_clashes else {
        "passed": True, "clash_count": 0, "clashes": [], "defective_targets": []
    }
    defective_targets = sorted({d["object"] for d in defective} | set(clash_res["defective_targets"]))
    hidden = hide_defective_components(defective_targets, reason="audit_scene_meshes") if (auto_hide_defective and defective_targets) else None

    return {
        "passed": (len(defective) == 0 and len(missing) == 0 and clash_res["passed"]),
        "mesh_count": len(mesh_objs),
        "total_verts": total_verts,
        "total_faces": total_faces,
        "defective_count": len(defective),
        "defective_objects": defective,
        "failed_objects": [d["object"] for d in defective],
        "missing_parts": missing,
        "clash_count": clash_res["clash_count"],
        "clashes": clash_res["clashes"],
        "defective_targets": defective_targets,
        "hidden": hidden,
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
            j = (i + 1) % n_pts
            pi = Vector(loop_pts_yz[i])
            pj = Vector(loop_pts_yz[j])
            seg = pj - pi
            seg_len = seg.length
            if seg_len < 1e-5:
                continue
            seg_t = seg / seg_len
            seg_n = Vector((seg_t.y, -seg_t.x)).normalized()
            p_mid = 0.5 * (pi + pj)
            if seg_n.dot(p_mid - interior_pt) < 0:
                seg_n = -seg_n
            # Keep pad/tooth tangent & normal flush on the segment surface (zero corner overlap)
            ang_x = math.atan2(seg_t.y, seg_t.x)
            pad_len = min(0.085, seg_len * 0.80)
            tooth_len = min(0.06, seg_len * 0.70)
            for shoe_dx in [-shoe_offset, shoe_offset]:
                g_pad = bmesh.ops.create_cube(bm, size=1.0)
                bmesh.ops.scale(bm, vec=(shoe_w, pad_len, 0.024), verts=g_pad["verts"])
                bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(ang_x, 3, 'X'), verts=g_pad["verts"])
                pos_yz = p_mid + seg_n * (belt_thickness * 0.5 + 0.012)
                bmesh.ops.translate(bm, vec=(x_center + shoe_dx, pos_yz.x, pos_yz.y), verts=g_pad["verts"])

            g_tooth = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(0.035, tooth_len, 0.065), verts=g_tooth["verts"])
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(ang_x, 3, 'X'), verts=g_tooth["verts"])
            pos_in = p_mid - seg_n * (belt_thickness * 0.5 + 0.0325)
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


def setup_lit_studio(
    col_studio=None,
    sun_energy=3.0,
    fill_energy=0.55,
    rim_energy=0.45,
    sun_angle_deg=2.0,
    ambient_strength=0.25,
    ambient_color=(0.80, 0.86, 0.94),
) -> dict:
    """Configure actual-lighting EEVEE render studio (raking key sun + cool fill/rim + sky ambient + PBR materials)
    for Round-2 VLM visual verification after Round-1 shaded geometry verification passes."""
    scene = bpy.context.scene
    if col_studio is None:
        col_studio = get_or_create_collection("Studio")
    elif isinstance(col_studio, str):
        col_studio = get_or_create_collection(col_studio)

    lights_spec = [
        ("Key_Sun",  ( 10.0, -8.0, 12.0), ( 46.0,   0.0,   32.0), sun_energy,  True,  (1.0, 0.96, 0.90)),
        ("Fill_Sun", (-10.0,  6.0,  9.0), ( 50.0,   0.0, -135.0), fill_energy, False, (0.84, 0.91, 1.0)),
        ("Rim_Sun",  (  0.0, 10.0,  8.0), (-45.0,   0.0,   15.0), rim_energy,  False, (0.95, 0.97, 1.0)),
    ]
    created_lights = []
    for lname, loc, rot_deg, energy, shadow, lcol in lights_spec:
        lobj = bpy.data.objects.get(lname)
        if lobj is None or lobj.type != 'LIGHT':
            if lobj is not None:
                bpy.data.objects.remove(lobj, do_unlink=True)
            ldata = bpy.data.lights.new(name=lname, type='SUN')
            lobj = bpy.data.objects.new(name=lname, object_data=ldata)
        ldata = lobj.data
        ldata.type = 'SUN'
        ldata.energy = float(energy)
        ldata.color = lcol
        ldata.angle = math.radians(sun_angle_deg)
        if hasattr(ldata, "use_shadow"):
            ldata.use_shadow = bool(shadow)
        lobj.location = loc
        lobj.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
        lobj.hide_viewport = False
        lobj.hide_render = False
        link_exclusively(lobj, col_studio)
        created_lights.append(lname)

    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = ambient_color
    scene.world.use_nodes = True
    if scene.world.node_tree:
        bg = (
            next((n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND'), None)
            or scene.world.node_tree.nodes.get("Background")
        )
        if bg:
            bg.inputs[0].default_value = (ambient_color[0], ambient_color[1], ambient_color[2], 1.0)
            bg.inputs[1].default_value = float(ambient_strength)

    for mat in bpy.data.materials:
        _sync_material_nodes(mat)

    scene.render.engine = 'BLENDER_EEVEE'
    _sync_shading_color_type('MATERIAL', outline=True, view_type='RENDERED')
    return {
        "engine": scene.render.engine,
        "shading_color_type": "MATERIAL",
        "lights": created_lights,
        "ambient_strength": float(ambient_strength),
    }


def render_lit_views(out_dir, names=None, prefix="render_lit_", transparent=False, resolution=None) -> dict:
    """Switch to `BLENDER_EEVEE` actual-lighting studio (`setup_lit_studio`) and render studio cameras."""
    setup_lit_studio()
    return render_views(out_dir, names=names, prefix=prefix, transparent=transparent, resolution=resolution)


def render_vlm_verification_views(
    out_dir,
    round_stage="r1_shaded",
    names=None,
    convention=None,
    resolution=(1280, 960),
) -> dict:
    """Two-stage VLM visual verification renderer:
      - `round_stage='r1_shaded'`: Round 1 Workbench RANDOM shaded model screenshots (geometry/silhouette check)
      - `round_stage='r2_lit'`:    Round 2 EEVEE actual-lighting PBR renders (run after Round 1 passes)
      - `round_stage='both'`:      Renders both Round 1 and Round 2 sets.
    """
    has_cams = any(o.type == 'CAMERA' and o.name.startswith("Cam_") for o in bpy.data.objects)
    if not has_cams or convention is not None:
        setup_workbench_studio_and_cameras(
            convention=convention or LAST_STUDIO_META.get("convention", "plan_north_up"),
            resolution=resolution,
            diagnostic_colors="RANDOM",
        )
    stage = str(round_stage).lower()
    scene = bpy.context.scene
    if stage in ("both", "all"):
        scene.render.engine = 'BLENDER_WORKBENCH'
        _sync_shading_color_type('RANDOM', outline=True, view_type='SOLID')
        r1 = render_views(out_dir, names=names, prefix="r1_shaded_", resolution=resolution)
        r2 = render_lit_views(out_dir, names=names, prefix="r2_lit_", resolution=resolution)
        return {"r1_shaded": r1, "r2_lit": r2}
    if stage in ("r2_lit", "2", "lit"):
        r2 = render_lit_views(out_dir, names=names, prefix="r2_lit_", resolution=resolution)
        return {"round_stage": "r2_lit", "engine": scene.render.engine, "renders": r2}
    scene.render.engine = 'BLENDER_WORKBENCH'
    _sync_shading_color_type('RANDOM', outline=True, view_type='SOLID')
    r1 = render_views(out_dir, names=names, prefix="r1_shaded_", resolution=resolution)
    return {"round_stage": "r1_shaded", "engine": scene.render.engine, "renders": r1}


def render_closeup(out_path, target, size, direction=(0.0, 1.0, 0.0), up=(0.0, 0.0, 1.0),
                   resolution=(1400, 1050), ortho=True, distance=None, lit=False) -> str:
    """Detail close-up of a region (e.g. a column/beam joint, a louver leaf, a railing corner) for
    verifying section profiles, not just silhouettes.

    target = world point at the image centre, size = metres spanned by the larger image side (ortho),
    direction = view direction (camera looks along it), lit = True uses EEVEE actual lighting.
    """
    if lit:
        setup_lit_studio()
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
# 5. MCP COMPONENT PERCEPTION, AUTO-HIDE & IN-PLACE REGENERATION (CRUD)
# ==============================================================================

_HIDE_PREFIX_RE = re.compile(r"^(?:__hide_r\d+__|__wip__)(.+)$")
_HIDDEN_SLOTS_KEY = "agy_hidden_slots"


def _base_component_name(name: str) -> str:
    cur = str(name)
    while True:
        m = _HIDE_PREFIX_RE.match(cur)
        if not m:
            return cur
        cur = m.group(1)


def _next_hide_name(base_name: str) -> str:
    r = 1
    while f"__hide_r{r}__{base_name}" in bpy.data.objects:
        r += 1
    return f"__hide_r{r}__{base_name}"


def _load_hidden_slots() -> dict:
    raw = bpy.context.scene.get(_HIDDEN_SLOTS_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_hidden_slots(slots: dict):
    bpy.context.scene[_HIDDEN_SLOTS_KEY] = json.dumps(slots, ensure_ascii=False)


def get_hidden_component_slot(name: str) -> dict:
    """Return recorded in-place slot metadata (`collection`, `parent`, `bbox_min/max`, `materials`, etc.)
    for a previously hidden/archived component."""
    base = _base_component_name(name)
    return dict(_load_hidden_slots().get(base, {}))


def _find_latest_archived(base_name: str):
    """Find the most recent `__hide_r<N>__<base_name>` object in `bpy.data.objects`."""
    pat = re.compile(rf"^__hide_r(\d+)__{re.escape(base_name)}$")
    matches = []
    for obj in bpy.data.objects:
        m = pat.match(obj.name)
        if m:
            matches.append((int(m.group(1)), obj))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0])
    return matches[-1][1]


def hide_defective_components(names, reason: str = "acceptance_regen") -> dict:
    """Archive defective/clashing component(s) in place as `__hide_r<N>__<name>`, hiding them from
    both viewport and render while saving their exact world slot metadata for in-place regeneration."""
    bpy.context.view_layer.update()
    name_list = [names] if isinstance(names, str) else list(names or [])
    slots = _load_hidden_slots()
    hidden = []

    for raw_name in name_list:
        obj = bpy.data.objects.get(raw_name)
        if obj is None:
            continue
        base = _base_component_name(obj.name)
        archived_name = _next_hide_name(base)

        mn, mx, _ = _world_aabb(obj)
        loc = obj.matrix_world.translation
        bev = next((m for m in obj.modifiers if m.type == 'BEVEL'), None)
        custom_props = {}
        for k in obj.keys():
            if not k.startswith("_"):
                val = obj[k]
                if isinstance(val, (bool, int, float, str)):
                    custom_props[k] = val

        entry = slots.get(base, {})
        history = list(entry.get("archived_history", []))
        history.append({"archived_name": archived_name, "reason": str(reason)})
        slots[base] = {
            "base_name": base,
            "collection": obj.users_collection[0].name if obj.users_collection else None,
            "parent": obj.parent.name if obj.parent else None,
            "matrix_world": [[round(v, 6) for v in row] for row in obj.matrix_world],
            "location_world": [round(loc.x, 5), round(loc.y, 5), round(loc.z, 5)],
            "bbox_min": [round(x, 5) for x in mn],
            "bbox_max": [round(x, 5) for x in mx],
            "materials": [m.name for m in obj.data.materials if m] if obj.type == 'MESH' and obj.data else [],
            "bevel_width": round(float(bev.width), 6) if bev else None,
            "bevel_segments": int(bev.segments) if bev else None,
            "custom_props": custom_props,
            "archived_history": history,
        }

        obj.name = archived_name
        obj.hide_viewport = True
        obj.hide_render = True
        if obj.type == 'MESH' and obj.data and obj.data.users == 1:
            obj.data.name = f"{archived_name}_Mesh"
        hidden.append({"original": raw_name, "archived": archived_name, "reason": reason})

    _save_hidden_slots(slots)
    return {"hidden": hidden, "count": len(hidden)}


def _extract_face_islands(bm):
    """Split a BMesh into connected face-index lists."""
    bm.faces.index_update()
    seen = set()
    islands = []
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
        islands.append(comp)
    return islands


def _boolean_eval_bmesh(target_obj, cutter_objs, operation="DIFFERENCE", use_self=False):
    """Evaluate Boolean modifiers on `target_obj` (temporarily muting Bevel on cutters) into a fresh BMesh."""
    muted = []
    for c in cutter_objs:
        for m in c.modifiers:
            if m.type == 'BEVEL' and m.show_viewport:
                m.show_viewport = False
                muted.append(m)
    try:
        for idx, c in enumerate(cutter_objs):
            mod = target_obj.modifiers.new(f"_AgyBool_{idx}", 'BOOLEAN')
            mod.operation = operation
            mod.solver = 'EXACT'
            mod.object = c
            if hasattr(mod, "use_self"):
                mod.use_self = bool(use_self)
        deps = bpy.context.evaluated_depsgraph_get()
        ev = target_obj.evaluated_get(deps)
        bm_out = bmesh.new()
        bm_out.from_mesh(ev.to_mesh())
        ev.to_mesh_clear()
        return bm_out
    finally:
        for m in muted:
            m.show_viewport = True


def _sanitize_bmesh_topology(bm, allow_open=False):
    """Strip loose verts/degenerate faces, fill open boundary holes if watertight, and recalc normals."""
    if not bm.faces and not bm.verts:
        return
    degen = [f for f in bm.faces if f.calc_area() < 1e-7]
    if degen:
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges[:])
    degen_left = [f for f in bm.faces if f.calc_area() < 1e-7]
    if degen_left:
        bmesh.ops.delete(bm, geom=degen_left, context='FACES')
    loose = [v for v in bm.verts if len(v.link_edges) == 0]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    if not allow_open and len(bm.faces) > 0:
        boundary_edges = [e for e in bm.edges if e.is_boundary]
        if boundary_edges:
            bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
    if len(bm.faces) > 0:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()


def _clean_and_trim_bmesh_from_archived(archived_obj, trim_cutter_objs, allow_open=False, fix_self_overlap=True, clearance_m=0.002):
    """Build a repaired & clash-trimmed world-space BMesh from an archived defective object."""
    bm = bmesh.new()
    bm.from_mesh(archived_obj.data)
    bm.transform(archived_obj.matrix_world)

    _sanitize_bmesh_topology(bm, allow_open=allow_open)
    scene_col = bpy.context.scene.collection

    # 3. Resolve self-overlapping islands via EXACT Boolean UNION (use_self=True)
    if fix_self_overlap and _count_self_overlap_pairs(bm, clearance_m=clearance_m) > 0:
        tmp_m = bpy.data.meshes.new("_tmp_self_m")
        bm.to_mesh(tmp_m)
        bm.free()
        tmp_o = bpy.data.objects.new("_tmp_self_o", tmp_m)
        empty_m = bpy.data.meshes.new("_tmp_self_helper_m")
        helper_o = bpy.data.objects.new("_tmp_self_helper_o", empty_m)
        scene_col.objects.link(tmp_o)
        scene_col.objects.link(helper_o)
        try:
            bm = _boolean_eval_bmesh(tmp_o, [helper_o], operation='UNION', use_self=True)
        finally:
            bpy.data.objects.remove(tmp_o, do_unlink=True)
            bpy.data.objects.remove(helper_o, do_unlink=True)
            bpy.data.meshes.remove(tmp_m)
            bpy.data.meshes.remove(empty_m)
        _sanitize_bmesh_topology(bm, allow_open=allow_open)

    # 4. Per-island Boolean DIFFERENCE against primary keeper objects to remove cross-object overlap
    if trim_cutter_objs and len(bm.faces) > 0:
        cutter_aabbs = [(c, *_world_aabb(c)[:2]) for c in trim_cutter_objs]
        islands = _extract_face_islands(bm)
        bm_out = bmesh.new()
        for comp in islands:
            vs = list({v for f in comp for v in f.verts})
            imn = [min(v.co[k] for v in vs) for k in range(3)]
            imx = [max(v.co[k] for v in vs) for k in range(3)]
            hits = [
                c for c, cmn, cmx in cutter_aabbs
                if all(min(imx[k], cmx[k]) - max(imn[k], cmn[k]) > clearance_m for k in range(3))
            ]
            bm_isl = bmesh.new()
            vmap = {v: bm_isl.verts.new(v.co) for v in vs}
            for f in comp:
                try:
                    nf = bm_isl.faces.new([vmap[v] for v in f.verts])
                    nf.material_index = f.material_index
                except ValueError:
                    pass
            if hits:
                tmp_m = bpy.data.meshes.new("_tmp_isl_m")
                bm_isl.to_mesh(tmp_m)
                bm_isl.free()
                tmp_o = bpy.data.objects.new("_tmp_isl_o", tmp_m)
                scene_col.objects.link(tmp_o)
                try:
                    bm_isl = _boolean_eval_bmesh(tmp_o, hits, operation='DIFFERENCE', use_self=False)
                finally:
                    bpy.data.objects.remove(tmp_o, do_unlink=True)
                    bpy.data.meshes.remove(tmp_m)
                _sanitize_bmesh_topology(bm_isl, allow_open=allow_open)
            if bm_isl.faces:
                vmap2 = {v: bm_out.verts.new(v.co) for v in bm_isl.verts}
                for f in bm_isl.faces:
                    try:
                        nf = bm_out.faces.new([vmap2[v] for v in f.verts])
                        nf.material_index = f.material_index
                    except ValueError:
                        pass
            bm_isl.free()
        bm.free()
        bm = bm_out

    _sanitize_bmesh_topology(bm, allow_open=allow_open)
    return bm


def regenerate_component_in_place(
    name: str,
    new_bm=None,
    builder_fn=None,
    trim_against=None,
    bevel_width=None,
    reason: str = "acceptance_regen",
    fix_topology: bool = True,
    clearance_m: float = 0.002,
    allow_open_patterns=("*glass*", "*pane*", "*grating*"),
) -> dict:
    """
    Universal acceptance remediation: hides any defective/clashing object `name` as `__hide_r<N>__<name>`
    and generates a fresh, clean object `<name>` in its exact slot.
      - If `builder_fn` is provided, invokes `builder_fn(slot)` (or `builder_fn()`).
      - Else if `new_bm` is provided, builds the new object using `new_bm` + preserved slot transform/materials.
      - Else autonomously repairs topology (unapplied scale, loose verts, holes, inverted normals,
        self-overlap) and trims cross-object penetration against `trim_against`.
    """
    import fnmatch
    base = _base_component_name(name)
    archived_name = None
    if base in bpy.data.objects:
        h_res = hide_defective_components([base], reason=reason)
        if h_res["hidden"]:
            archived_name = h_res["hidden"][0]["archived"]

    archived_obj = bpy.data.objects.get(archived_name) if archived_name else _find_latest_archived(base)
    slot = get_hidden_component_slot(base)
    col_name = slot.get("collection")
    col = bpy.data.collections.get(col_name) if col_name else bpy.context.scene.collection
    if col is None:
        col = bpy.context.scene.collection

    allow_open = any(fnmatch.fnmatch(base.lower(), p) for p in allow_open_patterns)

    if builder_fn is not None:
        try:
            built = builder_fn(slot)
        except TypeError:
            built = builder_fn()
        if isinstance(built, bpy.types.Object):
            if built.name != base:
                built.name = base
            return {
                "ok": True,
                "regenerated": base,
                "archived": archived_obj.name if archived_obj else None,
                "component": inspect_scene_components([base]).get(base, {}),
                "topology": audit_object_topology(built, allow_open=allow_open),
            }
        new_bm = built
        preserve_local_xform = False
    else:
        preserve_local_xform = new_bm is not None

    if new_bm is None:
        if archived_obj is None or archived_obj.type != 'MESH':
            return {"ok": False, "error": f"Component '{base}' not found and no archived slot exists"}
        cutters = []
        for cname in (trim_against or []):
            co = bpy.data.objects.get(cname)
            if co and co.type == 'MESH' and not co.hide_viewport:
                cutters.append(co)
        new_bm = _clean_and_trim_bmesh_from_archived(
            archived_obj, cutters, allow_open=allow_open, fix_self_overlap=fix_topology, clearance_m=clearance_m
        )
        if len(new_bm.faces) == 0:
            new_bm.free()
            return {
                "ok": True,
                "regenerated": None,
                "archived_only": True,
                "archived": archived_obj.name,
                "reason": "empty_after_trim_archived_redundant",
            }

    new_mesh = bpy.data.meshes.new(f"{base}_Mesh")
    bmesh.ops.recalc_face_normals(new_bm, faces=new_bm.faces)
    new_bm.normal_update()
    new_bm.to_mesh(new_mesh)
    new_bm.free()

    mat_names = slot.get("materials", [])
    if archived_obj and archived_obj.type == 'MESH' and archived_obj.data.materials:
        for m in archived_obj.data.materials:
            if m:
                new_mesh.materials.append(m)
    else:
        for mn in mat_names:
            m = bpy.data.materials.get(mn)
            if m:
                new_mesh.materials.append(m)

    new_obj = bpy.data.objects.new(base, new_mesh)
    link_exclusively(new_obj, col)

    parent_name = slot.get("parent")
    parent_obj = bpy.data.objects.get(parent_name) if parent_name else None
    if preserve_local_xform and archived_obj is not None:
        new_obj.location = archived_obj.location.copy()
        new_obj.rotation_mode = archived_obj.rotation_mode
        if archived_obj.rotation_mode == 'QUATERNION':
            new_obj.rotation_quaternion = archived_obj.rotation_quaternion.copy()
        elif archived_obj.rotation_mode == 'AXIS_ANGLE':
            new_obj.rotation_axis_angle = tuple(archived_obj.rotation_axis_angle)
        else:
            new_obj.rotation_euler = archived_obj.rotation_euler.copy()
        new_obj.scale = archived_obj.scale.copy()
        if parent_obj is not None:
            new_obj.parent = parent_obj
            new_obj.matrix_parent_inverse = archived_obj.matrix_parent_inverse.copy()
    elif parent_obj is not None:
        set_parent_keep_world(new_obj, parent_obj)

    for k, v in (slot.get("custom_props") or {}).items():
        new_obj[k] = v

    bw = bevel_width if bevel_width is not None else slot.get("bevel_width")
    if bw is not None and bw > 0:
        add_angle_bevel(new_obj, width=bw, segments=slot.get("bevel_segments") or 2)

    bpy.context.view_layer.update()
    return {
        "ok": True,
        "regenerated": base,
        "archived": archived_obj.name if archived_obj else None,
        "component": inspect_scene_components([base]).get(base, {}),
        "topology": audit_object_topology(new_obj, allow_open=allow_open),
    }


def audit_and_regenerate(
    expected_names: list = None,
    clearance_m: float = 0.003,
    max_rounds: int = 2,
    builders: dict = None,
) -> dict:
    """
    Detect topology, self-overlap, and cross-object clash defects across the active scene,
    automatically hide defective components as `__hide_r<N>__<name>`, regenerate clean
    replacements in place, and re-verify up to `max_rounds` iterations.
    """
    builders = builders or {}
    regenerated = []
    archived_redundant = []
    needs_builder = []
    expected_set = set(expected_names or ())
    rounds_run = 0

    for _ in range(max_rounds):
        audit = audit_scene_meshes(expected_names=expected_names, check_clashes=True, clearance_m=clearance_m)
        if audit["passed"]:
            break
        rounds_run += 1

        clash_map = {}
        for c in audit["clashes"]:
            clash_map.setdefault(c["defective_target"], []).append(c["primary_keep"])
        targets = sorted(set(audit["failed_objects"]) | set(clash_map.keys()))

        for tname in targets:
            res = regenerate_component_in_place(
                tname,
                builder_fn=builders.get(tname),
                trim_against=clash_map.get(tname),
                reason="audit_and_regenerate",
                fix_topology=True,
                clearance_m=min(0.002, clearance_m),
            )
            if res.get("archived_only"):
                archived_redundant.append({"object": tname, "archived": res.get("archived")})
                if tname in expected_set:
                    needs_builder.append(tname)
            else:
                regenerated.append({"object": tname, "archived": res.get("archived"), "ok": res.get("ok", False)})

        for mname in audit.get("missing_parts", []):
            if mname in builders:
                res = regenerate_component_in_place(
                    mname,
                    builder_fn=builders[mname],
                    reason="missing_part_regen",
                )
                regenerated.append({"object": mname, "archived": res.get("archived"), "ok": res.get("ok", False)})
            else:
                needs_builder.append(mname)

    final_audit = audit_scene_meshes(expected_names=expected_names, check_clashes=True, clearance_m=clearance_m)
    hidden_objs = [o.name for o in bpy.data.objects if o.name.startswith("__hide_r")]
    return {
        "passed": final_audit["passed"],
        "rounds": rounds_run,
        "regenerated": regenerated,
        "archived_redundant": archived_redundant,
        "needs_builder": sorted(set(needs_builder)),
        "hidden_objects": sorted(hidden_objs),
        "final_audit": final_audit,
    }


def inspect_scene_components(names=None, collection_name=None, include_hidden=False) -> dict:
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
        target_objs = [
            o for o in candidates
            if (o.type == 'MESH' and (include_hidden or _is_active_model_mesh(o)))
        ]

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
    Archives the existing component `name` as `__hide_r<N>__<name>` and regenerates a fresh
    object `<name>` in place from `new_bm`, retaining transforms, materials, parenting, and collections.
    """
    res = regenerate_component_in_place(name, new_bm=new_bm, bevel_width=bevel_width, reason="replace_component_geometry")
    if not res.get("ok"):
        return {"error": res.get("error", f"Mesh component '{name}' not found")}
    return res.get("component", {})


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
