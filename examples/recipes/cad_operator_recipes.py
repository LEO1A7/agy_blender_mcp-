"""
bmesh_cad_kit.py — Reusable BMesh Parametric CAD Primitives, Pure-BMesh Topology Audit,
Component Perception & Refinement, and Unified 5-Camera Workbench Studio for Blender MCP Modeling.

The operators and design patterns in this kit originate from the official Blender MCP script
repository (mirrored in `examples/official_blender_mcp/` for LLM architectural reference).

Can be imported directly inside Blender Python (`execute_blender_code`) by adding
the plugin's `lib/` directory to `sys.path`.
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

# High-contrast diagnostic palette for L1 Coarse-to-Fine decoupled group inspection
DIAGNOSTIC_COLOR_PALETTE = {
    "hull_macro":        (0.88, 0.22, 0.28, 1.0),  # Crimson Red
    "turret_macro":      (0.12, 0.68, 0.45, 1.0),  # Emerald Green
    "gun_mantlet":       (0.15, 0.52, 0.92, 1.0),  # Cobalt Blue
    "tracks_loop":       (0.85, 0.52, 0.12, 1.0),  # Amber Orange
    "wheels_repetitive": (0.62, 0.28, 0.88, 1.0),  # Amethyst Purple
    "rollers_sprocket":  (0.10, 0.72, 0.78, 1.0),  # Cyan Teal
    "hull_detail":       (0.92, 0.76, 0.18, 1.0),  # Gold Yellow
    "turret_detail":     (0.90, 0.28, 0.65, 1.0),  # Magenta Pink
}


def setup_clean_scene(root_collection_name="CAD_Model_Root"):
    """Deletes default objects, purges orphan datablocks, sets metric units (1.0m)."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

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
    """Removes all objects inside a collection for clean iterative rebuilding."""
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def link_exclusively(obj, col):
    """Links `obj` exclusively to collection `col`."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def set_parent_keep_world(child_obj, parent_obj):
    """Parents `child_obj` to `parent_obj` with zero world-space offset."""
    child_obj.parent = parent_obj
    child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()


def make_pbr_material(name, rgba, metallic=0.2, roughness=0.55):
    """Creates or updates a Principled BSDF material and sets viewport diffuse color."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = rgba
    return mat


def add_angle_bevel(obj, width=0.008, segments=2, angle_deg=30.0):
    """Adds a non-destructive angle-limited Bevel modifier to highlight hard edges."""
    bev = obj.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = width
    bev.segments = segments
    bev.limit_method = 'ANGLE'
    bev.angle_limit = math.radians(angle_deg)
    return bev


def infer_diagnostic_group(obj_name: str, col_name: str = "") -> str:
    """Infers L1 Coarse-to-Fine diagnostic color group from object/collection name."""
    low = obj_name.lower()
    clow = col_name.lower()
    if "track" in low:
        return "tracks_loop"
    if "wheel" in low or "torsion" in low or "hub" in low:
        return "wheels_repetitive"
    if "roller" in low or "sprocket" in low or "idler" in low:
        return "rollers_sprocket"
    if "gun" in low or "barrel" in low or "mantlet" in low or "bore" in low or "muzzle" in low:
        return "gun_mantlet"
    if "hull" in low or "hull" in clow:
        if any(k in low for k in ("tub", "upperbody", "main", "glacis", "skirt")):
            return "hull_macro"
        return "hull_detail"
    if "turret" in low or "turret" in clow:
        if any(k in low for k in ("main", "body", "shell", "cheek", "bustle")):
            return "turret_macro"
        return "turret_detail"
    return "hull_detail"


def create_mesh_object(name, bm, col, mat=None, bevel_width=0.008, bevel_segments=2, color_group=None):
    """
    Converts a BMesh `bm` into a Blender Mesh Object, frees `bm`, applies angle-limited bevel,
    and assigns its diagnostic object color (`obj.color`) for instant L4 inspection toggling.
    """
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    link_exclusively(obj, col)
    if mat is not None:
        obj.data.materials.append(mat)
    if bevel_width > 0:
        add_angle_bevel(obj, width=bevel_width, segments=bevel_segments)

    grp = color_group or infer_diagnostic_group(name, col.name if col else "")
    obj["diagnostic_group"] = grp
    obj.color = DIAGNOSTIC_COLOR_PALETTE.get(grp, (0.75, 0.75, 0.75, 1.0))
    return obj


def set_diagnostic_color_mode(enable: bool = True, palette: dict = None) -> dict:
    """
    Toggles Workbench shading between high-contrast decoupled category colors (`OBJECT`)
    to expose interpenetrations/misalignments, and standard PBR material colors (`MATERIAL`).
    """
    pal = dict(DIAGNOSTIC_COLOR_PALETTE)
    if palette:
        pal.update(palette)

    counts = {}
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        col_name = obj.users_collection[0].name if obj.users_collection else ""
        grp = obj.get("diagnostic_group") or infer_diagnostic_group(obj.name, col_name)
        obj["diagnostic_group"] = grp
        obj.color = pal.get(grp, (0.75, 0.75, 0.75, 1.0))
        counts[grp] = counts.get(grp, 0) + 1

    scene = bpy.context.scene
    if hasattr(scene, "display") and hasattr(scene.display, "shading"):
        scene.display.shading.color_type = 'OBJECT' if enable else 'MATERIAL'

    return {
        "diagnostic_mode": enable,
        "shading_color_type": 'OBJECT' if enable else 'MATERIAL',
        "group_counts": counts,
    }


# ==============================================================================
# 2. PURE-BMESH TOPOLOGY & TRANSFORM AUDIT (ZERO EXTERNAL DEPENDENCIES)
# ==============================================================================

def audit_object_topology(obj) -> dict:
    """
    Audits a single Blender Mesh object for:
      - Unapplied scale != (1, 1, 1)
      - Non-manifold edges (must be 0 for watertight solids)
      - Degenerate zero-area faces (< 1e-7 m^2)
      - Isolated loose vertices
    """
    if not obj or obj.type != 'MESH':
        return {"object": getattr(obj, "name", None), "passed": True, "issues": []}

    issues = []
    s = obj.scale
    if not (abs(s.x - 1.0) < 1e-4 and abs(s.y - 1.0) < 1e-4 and abs(s.z - 1.0) < 1e-4):
        issues.append(f"Unapplied scale ({s.x:.3f}, {s.y:.3f}, {s.z:.3f}) != (1,1,1)")

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    zero_area = sum(1 for f in bm.faces if f.calc_area() < 1e-7)
    loose_verts = sum(1 for v in bm.verts if len(v.link_edges) == 0)
    bm.free()

    if non_manifold > 0:
        issues.append(f"{non_manifold} non-manifold edges")
    if zero_area > 0:
        issues.append(f"{zero_area} zero-area faces")
    if loose_verts > 0:
        issues.append(f"{loose_verts} isolated vertices")

    return {
        "object": obj.name,
        "passed": len(issues) == 0,
        "issues": issues,
        "verts": len(mesh.vertices),
        "faces": len(mesh.polygons),
    }


def audit_scene_meshes(expected_names: list = None) -> dict:
    """
    Runs `audit_object_topology` across all scene meshes and optionally checks against
    an `expected_names` checklist to detect any omitted parts.
    """
    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.startswith("BBOX_")]
    defective = []
    total_verts = 0
    total_faces = 0

    for obj in mesh_objs:
        res = audit_object_topology(obj)
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
                bevel_width=0.006, color_group="hull_macro"
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
# 4. UNIFIED 5-CAMERA WORKBENCH STUDIO (1:1 ORTHO + AUTO-LOCKED DUAL-ISO)
# ==============================================================================

def compute_or_lock_iso_distance(
    target_center=(0.0, -0.5, 1.35),
    default_d=9.5,
    lock_file=None,
    force_relock=False,
) -> float:
    """
    Computes the optimal 50mm isometric camera distance `d` from the scene's actual
    mesh bounding sphere around `target_center`, and optionally locks it to `lock_file`
    for pixel-comparable iterative verification across modeling steps.
    """
    if lock_file and not force_relock and os.path.isfile(lock_file):
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "distance_d" in data:
                    return float(data["distance_d"])
        except Exception:
            pass

    center_vec = Vector(target_center)
    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.startswith("BBOX_")]
    d = default_d
    if mesh_objs:
        max_r = 0.0
        for obj in mesh_objs:
            for corner in obj.bound_box:
                world_co = obj.matrix_world @ Vector(corner)
                r = (world_co - center_vec).length
                if r > max_r:
                    max_r = r
        if max_r > 0.1:
            # For 50mm lens on 36mm sensor, 1.65 * R along each axis (distance ~ 2.6 * R) frames full model cleanly
            d = max(round(max_r * 1.68, 3), 4.0)

    if lock_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(lock_file)), exist_ok=True)
            with open(lock_file, "w", encoding="utf-8") as f:
                json.dump({
                    "distance_d": d,
                    "lens_mm": 50.0,
                    "sensor_width_mm": 36.0,
                    "target_center": list(target_center),
                }, f, indent=2)
        except Exception:
            pass

    return d


def setup_workbench_studio_and_cameras(
    col_studio,
    target_center=(0.0, -0.5, 1.35),
    ortho_span=10.2,
    front_span=4.5,
    scale_m_per_px=None,
    view_crops=None,
    iso_lock_file=None,
    force_relock_iso=False,
    iso_lens=50.0,
    diagnostic_colors=False,
):
    """
    Unified Stage 4 Studio & 5-Camera Rig:
      - Configures Blender Workbench Cavity + Object Outline shading & 3-point Sun lighting.
      - Orthographic Tri-View Cameras (`Cam_Side_Left`, `Cam_Top`, `Cam_Front`):
        If `scale_m_per_px` and `view_crops` (dict of `"side"`, `"top"`, `"front"` -> `(u0,v0,u1,v1)`)
        are provided, automatically sets exact 1:1 mathematical `ortho_scale = W_px * scale_m_per_px`.
      - Unified Dual-Isometric Fixed-Lens Cameras (`Cam_Iso` [SE Front-Right] & `Cam_Iso_Rear` [NW Rear-Left]):
        Automatically computes (and optionally locks) camera distance `d` from the scene bounding sphere
        with a 50mm fixed lens, eliminating redundant camera rigs.
    """
    clear_collection(col_studio)
    scene = bpy.context.scene

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
    scene.display.shading.color_type = 'OBJECT' if diagnostic_colors else 'MATERIAL'
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.cavity_ridge_factor = 1.0
    scene.display.shading.cavity_valley_factor = 1.0
    scene.display.shading.show_object_outline = True
    scene.display.shading.object_outline_color = (0.05, 0.05, 0.05)
    scene.display.shading.show_shadows = True
    scene.display.shading.shadow_intensity = 0.35
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = (0.94, 0.94, 0.93)

    def make_cam(name, loc, rot_deg=None, look_at=None, ortho=True, ortho_scale=10.2, lens=50.0):
        cdata = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
        cdata.sensor_width = 36.0
        if ortho:
            cdata.type = 'ORTHO'
            cdata.ortho_scale = ortho_scale
        else:
            cdata.type = 'PERSP'
            cdata.lens = lens
        cdata.clip_start = 0.1
        cdata.clip_end = 200.0
        cobj = bpy.data.objects.get(name) or bpy.data.objects.new(name, cdata)
        cobj.location = Vector(loc)
        if look_at is not None:
            direction = (Vector(look_at) - Vector(loc)).normalized()
            cobj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler('XYZ')
        elif rot_deg is not None:
            cobj.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
        link_exclusively(cobj, col_studio)
        return cobj

    # Compute 1:1 orthographic scales if blueprint crop boxes and scale are supplied
    side_scale = ortho_span
    top_scale = ortho_span
    front_scale = front_span
    if scale_m_per_px and view_crops:
        if "side" in view_crops:
            c = view_crops["side"]
            side_scale = (c[2] - c[0]) * scale_m_per_px
        if "top" in view_crops:
            c = view_crops["top"]
            top_scale = (c[2] - c[0]) * scale_m_per_px
        if "front" in view_crops:
            c = view_crops["front"]
            front_scale = (c[2] - c[0]) * scale_m_per_px

    # Compute unified bounding-sphere auto-locked distance d for Dual-Isometric cameras
    xc, yc, zc = target_center
    d = compute_or_lock_iso_distance(
        target_center=target_center,
        default_d=9.2,
        lock_file=iso_lock_file,
        force_relock=force_relock_iso,
    )

    cams = {
        "Cam_Side_Left": make_cam("Cam_Side_Left", (15.0, yc, zc), rot_deg=(90.0, 0.0, 90.0), ortho=True, ortho_scale=side_scale),
        "Cam_Top":       make_cam("Cam_Top",       (0.0, yc, 15.0), rot_deg=(0.0, 0.0, 90.0), ortho=True, ortho_scale=top_scale),
        "Cam_Front":     make_cam("Cam_Front",     (0.0, -15.0, zc), rot_deg=(90.0, 0.0, 0.0), ortho=True, ortho_scale=front_scale),
        "Cam_Iso":       make_cam("Cam_Iso",       (xc + d, yc - d, zc + 0.55 * d), look_at=target_center, ortho=False, lens=iso_lens),
        "Cam_Iso_Rear":  make_cam("Cam_Iso_Rear",  (xc - d, yc + d, zc + 0.55 * d), look_at=target_center, ortho=False, lens=iso_lens),
    }
    scene.camera = cams["Cam_Iso"]
    return cams


# ==============================================================================
# 5. MCP COMPONENT STATE PERCEPTION & IN-PLACE REFINEMENT (CRUD & TRANSFORMS)
# ==============================================================================

def inspect_scene_components(names=None, collection_name=None) -> dict:
    """
    Extracts precise transform, AABB bounding box, and hierarchy state of scene
    objects via MCP. Returns a structured dict for comparing against visual renders.
    """
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
            "collection": obj.users_collection[0].name if obj.users_collection else None,
        }

    return results


def transform_component(name, delta_loc=None, new_loc=None, scale_factor=None, delta_rot_deg=None, apply_scale=True) -> dict:
    """
    In-place translation, scaling, or rotation of an existing component.
    Preserves parent hierarchy and automatically re-applies scale transforms if requested.
    """
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Component '{name}' not found"}

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
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.select_set(False)

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
