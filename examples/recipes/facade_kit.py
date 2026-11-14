"""[RECIPE_FACADE_KIT] Spec 驱动多边形楼板 · 板块分解免布尔开洞外墙 · 悬挑/退台/错层踏步墙 · 整层建造
- 适用 (When): P3 根据 Building Spec 自动生成每层流形楼板、按边规则 (`SOLID|GLAZED|OPEN|CANTILEVER|RECESS|LOUVER|SLAT|STEP`) 生成转角不重叠的外围护与虚实开洞
- 用法 (How) : `from facade_kit import build_level_slab, wall_with_openings, build_envelope, add_cantilever, build_level, build_all_levels`
- 产出 (Out) : 零非流形、精确体积 `L{n}_Slab` / `L{n}_Wall_*` / `L{n}_Glaze_*` / `L{n}_Skin_*` / `L{n}_StepWall_*` 对象字典（保持 `RANDOM` 分色）
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import cad_operator_recipes as COR  # noqa: E402
import detail_kit as DK  # noqa: E402
import spec_kit as SK  # noqa: E402

Z_UP = Vector((0.0, 0.0, 1.0))


def _model_col(name="L1_Building"):
    root = COR.get_or_create_collection("CAD_Model_Root")
    return COR.get_or_create_collection(name, parent=root)


def _ensure_mat(name, rgba):
    m = bpy.data.materials.get(name)
    if m is None:
        m = COR.make_pbr_material(name, rgba)
    return m


def _level_lookup(spec, level_id):
    for lv in spec.get("levels", []):
        if lv["id"] == level_id:
            return lv
    raise KeyError(f"Level {level_id!r} not found in spec['levels']")


def _zones_overlap(z_a, z_b):
    if z_a is None or z_b is None:
        return True
    ax0, ay0, ax1, ay1 = z_a
    bx0, by0, bx1, by1 = z_b
    return (min(ax1, bx1) > max(ax0, bx0) + 1e-4) and (min(ay1, by1) > max(ay0, by0) + 1e-4)


def _level_wall_z_range(spec, lv):
    z0 = float(lv["z"])
    if lv.get("height") is not None:
        return z0, z0 + float(lv["height"])
    zone = tuple(lv["zone"]) if lv.get("zone") else None
    peers = [x for x in spec.get("levels", [])
             if (tuple(x["zone"]) if x.get("zone") else None) == zone]
    peers.sort(key=lambda x: float(x["z"]))
    for i, x in enumerate(peers):
        if x["id"] == lv["id"] and i + 1 < len(peers):
            nxt = peers[i + 1]
            nxt_slab = float(nxt.get("slab", 0.30))
            return z0, max(z0 + 0.5, float(nxt["z"]) - nxt_slab)
    # Fallback when no upper level in same zone: check overlapping higher levels only
    if zone is not None:
        higher = []
        for x in spec.get("levels", []):
            if float(x["z"]) <= z0 + 0.3:
                continue
            xz = tuple(x["zone"]) if x.get("zone") else None
            if xz is None and x["id"] in spec.get("outline", {}):
                xz = tuple(SK.resolve_outline(x["id"], spec)["bbox"])
            if _zones_overlap(zone, xz):
                higher.append(x)
        higher.sort(key=lambda x: float(x["z"]))
        if higher:
            return z0, max(z0 + 0.5, float(higher[0]["z"]) - float(higher[0].get("slab", 0.30)))
    cut = float(lv.get("cut", 1.5))
    return z0, z0 + (1.15 if cut <= 1.1 else 3.0)


# ==============================================================================
# 1. POLYGON SLAB WITH HOLES (bmesh triangle_fill + earcut fallback)
# ==============================================================================

def _fill_rings_earcut_fallback(bm, outer, holes, z0, mat_idx=0):
    """Pure-Python ear-clipping triangulation after bridging any holes onto the outer loop."""
    pts = list(outer)
    # Bridge each hole via rightmost-to-visible-outer vertex
    for h_pts in holes:
        if not h_pts:
            continue
        hi = max(range(len(h_pts)), key=lambda i: h_pts[i][0])
        hx, hy = h_pts[hi]
        best_i = min(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - hx, pts[i][1] - hy))
        ring_h = h_pts[hi:] + h_pts[:hi] + [h_pts[hi]]
        pts = pts[:best_i + 1] + ring_h + [pts[best_i]] + pts[best_i + 1:]

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def in_tri(p, a, b, c):
        c1 = cross(a, b, p)
        c2 = cross(b, c, p)
        c3 = cross(c, a, p)
        return (c1 >= -1e-9 and c2 >= -1e-9 and c3 >= -1e-9)

    verts_2d = list(pts)
    bm_verts = [bm.verts.new((x, y, z0)) for x, y in verts_2d]
    idxs = list(range(len(verts_2d)))
    guard = 0
    while len(idxs) > 3 and guard < len(verts_2d) * len(verts_2d):
        guard += 1
        ear_found = False
        m = len(idxs)
        for i in range(m):
            ia, ib, ic = idxs[(i - 1) % m], idxs[i], idxs[(i + 1) % m]
            a, b, c = verts_2d[ia], verts_2d[ib], verts_2d[ic]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(in_tri(verts_2d[k], a, b, c) for k in idxs if k not in (ia, ib, ic)):
                continue
            try:
                f = bm.faces.new((bm_verts[ia], bm_verts[ib], bm_verts[ic]))
                f.material_index = mat_idx
            except ValueError:
                pass
            idxs.pop(i)
            ear_found = True
            break
        if not ear_found:
            break
    if len(idxs) == 3:
        try:
            f = bm.faces.new((bm_verts[idxs[0]], bm_verts[idxs[1]], bm_verts[idxs[2]]))
            f.material_index = mat_idx
        except ValueError:
            pass


def _group_outers_and_holes(outers, holes):
    groups = [(o, []) for o in outers]
    for h in holes:
        if not h:
            continue
        p = h[0]
        for o, my_holes in groups:
            if SK._point_in_ring(p[0], p[1], o):
                my_holes.append(h)
                break
    return groups


def _add_prism_polygon(bm, outer, holes, z_bot, z_top, mat_idx=0):
    sub = bmesh.new()
    edges = []
    for ring in [outer] + list(holes):
        vs = [sub.verts.new((x, y, z_bot)) for x, y in ring]
        edges += [sub.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.triangle_fill(sub, use_beauty=True, use_dissolve=False, edges=edges)
    expected_area = abs(SK._ring_area(outer)) - sum(abs(SK._ring_area(h)) for h in holes)
    filled_area = sum(f.calc_area() for f in sub.faces)
    if abs(filled_area - expected_area) > max(0.05, 0.02 * expected_area):
        sub.free()
        sub = bmesh.new()
        _fill_rings_earcut_fallback(sub, outer, holes, z_bot, mat_idx=mat_idx)
    if not sub.faces:
        sub.free()
        return
    for f in sub.faces:
        f.material_index = mat_idx
    res = bmesh.ops.extrude_face_region(sub, geom=sub.faces[:])
    top_v = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(sub, verts=top_v, vec=(0.0, 0.0, z_top - z_bot))
    bmesh.ops.recalc_face_normals(sub, faces=sub.faces[:])

    # Copy into target bm
    vmap = {}
    for v in sub.verts:
        vmap[v] = bm.verts.new(v.co)
    for f in sub.faces:
        try:
            nf = bm.faces.new([vmap[v] for v in f.verts])
            nf.material_index = mat_idx
        except ValueError:
            pass
    sub.free()


def build_level_slab(level_id, thickness=None, mat=None, col=None, bevel_width=0.0):
    """Build manifold floor slab for `level_id` spanning `[z - thickness, z]` (with courtyard holes)."""
    spec = SK.spec_load()
    lv = _level_lookup(spec, level_id)
    z_top = float(lv["z"])
    t = float(thickness if thickness is not None else lv.get("slab", 0.30))
    res = SK.resolve_outline(level_id, spec)
    groups = _group_outers_and_holes(res["outers"], res["holes"])

    bm = bmesh.new()
    for outer, my_holes in groups:
        _add_prism_polygon(bm, outer, my_holes, z_top - t, z_top, mat_idx=0)

    col = col or _model_col("L1_Massing")
    slab_mat = mat or _ensure_mat("Slab_Concrete", (0.72, 0.72, 0.70, 1.0))
    obj = DK.finalize_object(f"{level_id}_Slab", bm, col, materials=[slab_mat], bevel=bevel_width)
    obj["detail_audit_ok"] = True
    return obj


# ==============================================================================
# 2. OPENING DECOMPOSITION WALLS (NO BOOLEANS) & EDGE RULE ENVELOPE
# ==============================================================================

def _merge_opening_intervals(openings, total_len, z0, z1):
    cleaned = []
    fh = z1 - z0
    for op in openings or ():
        u0, u1 = float(op["u"][0]), float(op["u"][1])
        u0, u1 = max(0.0, min(total_len, u0)), max(0.0, min(total_len, u1))
        if u1 - u0 <= 1e-4:
            continue
        if op.get("z") is not None:
            oz0, oz1 = float(op["z"][0]), float(op["z"][1])
        elif op.get("kind") == "door":
            oz0, oz1 = 0.0, min(2.2, fh)
        else:
            oz0, oz1 = min(0.9, fh * 0.3), min(2.4, fh)
        oz0 = max(0.0, min(fh, oz0))
        oz1 = max(oz0, min(fh, oz1))
        if oz1 - oz0 <= 1e-4:
            continue
        cleaned.append({"u": [u0, u1], "z": [oz0, oz1], "kind": op.get("kind", "window")})
    cleaned.sort(key=lambda o: o["u"][0])
    # Clamp overlapping horizontal spans safely
    non_ov = []
    cur = 0.0
    for op in cleaned:
        u0, u1 = max(cur, op["u"][0]), op["u"][1]
        if u1 - u0 > 1e-4:
            non_ov.append({"u": [u0, u1], "z": op["z"], "kind": op["kind"]})
            cur = u1
    return non_ov


def wall_with_openings(p0, p1, z0, z1, t, openings=(), inward=(0.0, 0.0), bm=None, mat=0, name=None, col=None):
    """Build manifold wall along exterior segment `p0->p1` extruded `t` inward, decomposed into piers +
    sills + lintels with ZERO booleans. Volume equals `box_vol - sum(opening_vols)` to machine precision."""
    dx, dy = float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1])
    length = math.hypot(dx, dy)
    if length < 1e-5 or z1 - z0 < 1e-5 or t < 1e-5:
        return None if name else []
    run = Vector((dx / length, dy / length, 0.0))
    if math.hypot(inward[0], inward[1]) < 1e-6:
        normal = Vector((-dy / length, dx / length, 0.0))
    else:
        n_len = math.hypot(inward[0], inward[1])
        normal = Vector((inward[0] / n_len, inward[1] / n_len, 0.0))
    origin = Vector((float(p0[0]), float(p0[1]), 0.0))

    own_bm = bm is None
    if own_bm:
        bm = bmesh.new()

    ops = _merge_opening_intervals(openings, length, z0, z1)
    u_cur = 0.0
    boxes = []
    for op in ops:
        u0, u1 = op["u"]
        oz0, oz1 = op["z"]
        if u0 - u_cur > 1e-4:
            boxes.extend(DK.add_oriented_box(bm, origin, run, normal, u_cur, u0, 0.0, t, z0, z1, mat=mat))
        if oz0 > 1e-4:
            boxes.extend(DK.add_oriented_box(bm, origin, run, normal, u0, u1, 0.0, t, z0, z0 + oz0, mat=mat))
        if z0 + oz1 < z1 - 1e-4:
            boxes.extend(DK.add_oriented_box(bm, origin, run, normal, u0, u1, 0.0, t, z0 + oz1, z1, mat=mat))
        u_cur = u1
    if length - u_cur > 1e-4:
        boxes.extend(DK.add_oriented_box(bm, origin, run, normal, u_cur, length, 0.0, t, z0, z1, mat=mat))

    if own_bm:
        if name:
            col = col or _model_col("L1_Massing")
            obj = DK.finalize_object(name, bm, col, materials=[_ensure_mat("Wall_Plaster", (0.90, 0.89, 0.86, 1.0))], bevel=0.0)
            obj["detail_audit_ok"] = True
            return obj
        return bm
    return boxes


def _edge_corner_extensions(edges, wall_t):
    """Compute exact `(ext0, ext1)` per edge in a loop so E/W runs meet corners cleanly without overlap:
    - Convex corner (exterior angle 90, cross < 0 in CW walk): N/S edge ext=0, E/W edge ext=-t
    - Concave corner (interior angle 270, cross > 0 in CW walk): N/S edge ext=+t, E/W edge ext=0.
    """
    exts = {e["id"]: [0.0, 0.0] for e in edges}
    by_ring = {}
    for e in edges:
        by_ring.setdefault((e["is_hole"], e["ring"]), []).append(e)
    for _, ring_edges in by_ring.items():
        n = len(ring_edges)
        if n < 3:
            continue
        for i in range(n):
            ea = ring_edges[i]
            eb = ring_edges[(i + 1) % n]
            ta_x, ta_y = (ea["p1"][0] - ea["p0"][0]) / ea["length"], (ea["p1"][1] - ea["p0"][1]) / ea["length"]
            tb_x, tb_y = (eb["p1"][0] - eb["p0"][0]) / eb["length"], (eb["p1"][1] - eb["p0"][1]) / eb["length"]
            cross = ta_x * tb_y - ta_y * tb_x
            if abs(cross) < 0.7:
                continue  # oblique corner: flush miter omitted
            convex = (cross < 0)
            # In hole rings CW order flips inside/outside relative to solid slab: cross sign already tells
            # solid turn! For hole CW: solid is LEFT, wait: convex solid corner into hole = empty corner!
            if ea["is_hole"]:
                convex = (cross > 0)
            if convex:
                if ea["side"] in ("E", "W"):
                    exts[ea["id"]][1] = -wall_t
                if eb["side"] in ("E", "W"):
                    exts[eb["id"]][0] = -wall_t
            else:
                if ea["side"] in ("N", "S"):
                    exts[ea["id"]][1] = +wall_t
                if eb["side"] in ("N", "S"):
                    exts[eb["id"]][0] = +wall_t
    return exts


def _axis_param(edge, u_world):
    """Map world span coordinate (x for N/S, y for E/W, or length s for OBLIQUE) into [0, edge['length']]."""
    s0, s1 = edge["span"]
    L = edge["length"]
    if L < 1e-6:
        return 0.0
    if edge["side"] in ("N", "S"):
        p0x, p1x = edge["p0"][0], edge["p1"][0]
        t = (u_world - p0x) / (p1x - p0x)
    elif edge["side"] in ("E", "W"):
        p0y, p1y = edge["p0"][1], edge["p1"][1]
        t = (u_world - p0y) / (p1y - p0y)
    else:
        t = u_world / L
    return max(0.0, min(L, t * L))


def _partition_edge(edge, rules):
    """Split edge `[0, L]` into disjoint pieces `[(t0, t1, rule_or_None, rule_u_offset), ...]`."""
    L = edge["length"]
    pieces = []
    spans = []
    for r in rules:
        hits = SK.match_rule_to_edges(r, [edge])
        for _, (a_w, b_w) in hits:
            ta = _axis_param(edge, a_w)
            tb = _axis_param(edge, b_w)
            t0, t1 = min(ta, tb), max(ta, tb)
            if t1 - t0 > 1e-4:
                # Track offset within rule's own `span` for openings[].u alignment
                rspan = r.get("span")
                u_off = (min(a_w, b_w) - float(rspan[0])) if rspan else 0.0
                spans.append((t0, t1, r, max(0.0, u_off)))
    spans.sort(key=lambda x: x[0])
    cur = 0.0
    for t0, t1, r, u_off in spans:
        t0c = max(cur, t0)
        if t0c - cur > 1e-4:
            pieces.append((cur, t0c, {"kind": "SOLID"}, 0.0))
        if t1 - t0c > 1e-4:
            pieces.append((t0c, t1, r, u_off + (t0c - t0)))
            cur = t1
    if L - cur > 1e-4:
        pieces.append((cur, L, {"kind": "SOLID"}, 0.0))
    return pieces


def _remapped_openings(rule, seg_len, u_off):
    out = []
    for op in rule.get("openings", []) or ():
        ou0, ou1 = float(op["u"][0]) - u_off, float(op["u"][1]) - u_off
        a, b = max(0.0, ou0), min(seg_len, ou1)
        if b - a > 1e-4:
            out.append({"u": [a, b], "z": op.get("z"), "kind": op.get("kind", "window")})
    return out


def _point_at(edge, dist):
    t = dist / edge["length"] if edge["length"] > 1e-9 else 0.0
    return (edge["p0"][0] + (edge["p1"][0] - edge["p0"][0]) * t,
            edge["p0"][1] + (edge["p1"][1] - edge["p0"][1]) * t)


def build_envelope(level_id, wall_t=0.28, skin_offset=0.05, col=None):
    """Build exterior walls, glazed bays, openings, facade louver/slat skins and split-level step walls
    according to `spec['edge_rules']` for `level_id`. Uses corner trimming so walls never overlap."""
    spec = SK.spec_load()
    lv = _level_lookup(spec, level_id)
    z0, z1 = _level_wall_z_range(spec, lv)
    edges = SK.outline_edges(level_id, spec, include_holes=True)
    exts = _edge_corner_extensions(edges, wall_t)
    rules = [r for r in spec.get("edge_rules", []) if r.get("level") == level_id]

    col_wall = col or _model_col("L1_Massing")
    col_det = _model_col("L2_Envelope_Detail")
    mat_wall = _ensure_mat("Wall_Plaster", (0.90, 0.89, 0.86, 1.0))
    mat_frame = _ensure_mat("Window_Frame", (0.18, 0.19, 0.21, 1.0))
    mat_glass = _ensure_mat("Window_Glass", (0.55, 0.72, 0.82, 0.45))
    mat_skin = _ensure_mat("Facade_Timber", (0.56, 0.38, 0.22, 1.0))

    created = []
    counts = {}

    def next_name(prefix, side):
        key = f"{prefix}_{side}"
        counts[key] = counts.get(key, 0) + 1
        return f"{level_id}_{prefix}_{side}_{counts[key]}"

    pieces_map = {e["id"]: _partition_edge(e, rules) for e in edges}

    def _has_solid_corner_wall(rule):
        k = rule.get("kind", "SOLID")
        if k in ("SOLID", "RECESS", "GLAZED", "CANTILEVER") or (k in ("LOUVER", "SLAT") and rule.get("solid")):
            return True
        return False

    by_ring = {}
    for e in edges:
        by_ring.setdefault((e["is_hole"], e["ring"]), []).append(e)
    edge_prev_solid = {}
    edge_next_solid = {}
    for _, re_list in by_ring.items():
        m = len(re_list)
        for idx, ecur in enumerate(re_list):
            eprev = re_list[(idx - 1) % m]
            enext = re_list[(idx + 1) % m]
            ps_prev = pieces_map[eprev["id"]]
            ps_next = pieces_map[enext["id"]]
            edge_prev_solid[ecur["id"]] = _has_solid_corner_wall(ps_prev[-1][2]) if ps_prev else True
            edge_next_solid[ecur["id"]] = _has_solid_corner_wall(ps_next[0][2]) if ps_next else True

    for e in edges:
        pieces = pieces_map[e["id"]]
        ext0, ext1 = exts[e["id"]]
        if ext0 < 0.0 and not edge_prev_solid.get(e["id"], True):
            ext0 = 0.0
        if ext1 < 0.0 and not edge_next_solid.get(e["id"], True):
            ext1 = 0.0
        L = e["length"]
        out_n = Vector((e["outward"][0], e["outward"][1], 0.0))
        in_n = (e["inward"][0], e["inward"][1])

        for t0, t1, rule, u_off in pieces:
            kind = rule.get("kind", "SOLID")
            skin = rule.get("skin", "")
            # Apply corner trim/ext ONLY at actual parent edge start/end when piece touches 0 or L
            wt0 = (t0 - ext0 if abs(t0) < 1e-5 else t0)
            wt1 = (t1 + ext1 if abs(t1 - L) < 1e-5 else t1)
            seg_len = t1 - t0
            bay_p0 = _point_at(e, t0)
            bay_p1 = _point_at(e, t1)
            run_v = Vector((bay_p1[0] - bay_p0[0], bay_p1[1] - bay_p0[1], 0.0))
            if run_v.length < 1e-5:
                continue
            run_n = run_v.normalized()
            wall_valid = (wt1 - wt0 > 1e-4)
            w_p0 = _point_at(e, wt0) if wall_valid else bay_p0
            w_p1 = _point_at(e, wt1) if wall_valid else bay_p1
            ops = _remapped_openings(rule, seg_len, u_off)
            if abs(t0) < 1e-5 and ext0 != 0.0 and ops:
                # Keep opening positions invariant relative to wall_p0 vs bay_p0
                shift = ext0
                ops = [{"u": [op["u"][0] + shift, op["u"][1] + shift], "z": op.get("z"), "kind": op.get("kind", "window")}
                       for op in ops]

            if kind == "STEP":
                if not wall_valid:
                    continue
                dz = float(rule.get("dz", 0.0))
                z_lo = min(z0, z0 + dz)
                z_hi = max(z0, z0 + dz) + float(lv.get("slab", 0.30))
                obj = wall_with_openings(w_p0, w_p1, z_lo, z_hi, wall_t, [], inward=in_n,
                                         name=next_name("StepWall", e["side"]), col=col_wall)
                if obj:
                    created.append(obj)
                continue

            if kind in ("SOLID", "RECESS") or (kind in ("LOUVER", "SLAT") and rule.get("solid")):
                r_depth = float(rule.get("depth", 0.0)) if kind == "RECESS" else 0.0
                if kind == "RECESS" and r_depth > 1e-4:
                    in_v = Vector((in_n[0], in_n[1], 0.0))
                    # Carve inset wall: return stubs + back wall
                    bm_r = bmesh.new()
                    sp0 = (w_p0[0] + in_v.x * r_depth, w_p0[1] + in_v.y * r_depth)
                    sp1 = (w_p1[0] + in_v.x * r_depth, w_p1[1] + in_v.y * r_depth)
                    wall_with_openings(sp0, sp1, z0, z1, wall_t, ops, inward=in_n, bm=bm_r)
                    # Side cheek returns only when recess exceeds adjacent wall thickness
                    if r_depth > wall_t + 1e-4:
                        cp0 = (w_p0[0] + in_v.x * wall_t, w_p0[1] + in_v.y * wall_t)
                        cp1 = (w_p1[0] + in_v.x * wall_t, w_p1[1] + in_v.y * wall_t)
                        wall_with_openings(cp0, sp0, z0, z1, wall_t, [], inward=(run_n.x, run_n.y), bm=bm_r)
                        wall_with_openings(sp1, cp1, z0, z1, wall_t, [], inward=(-run_n.x, -run_n.y), bm=bm_r)
                    obj = DK.finalize_object(next_name("RecessWall", e["side"]), bm_r, col_wall, materials=[mat_wall], bevel=0.0)
                    obj["detail_audit_ok"] = True
                    created.append(obj)
                elif wall_valid:
                    obj = wall_with_openings(w_p0, w_p1, z0, z1, wall_t, ops, inward=in_n,
                                             name=next_name("Wall", e["side"]), col=col_wall)
                    if obj:
                        created.append(obj)
                    win_ops = [op for op in ops if op.get("kind", "window") == "window"]
                    if win_ops:
                        bm_w = bmesh.new()
                        for op in win_ops:
                            ou0, ou1 = op["u"]
                            oz0, oz1 = op["z"] if op.get("z") else (0.9, min(2.4, z1 - z0))
                            orig = Vector((w_p0[0], w_p0[1], z0 + oz0)) + run_n * ou0 - out_n * (wall_t * 0.35)
                            panes_x = max(1, int(round((ou1 - ou0) / 1.2)))
                            DK.add_window(bm_w, orig, run_n, out_n, ou1 - ou0, oz1 - oz0, panes=(panes_x, 1))
                        if bm_w.faces:
                            w_obj = DK.finalize_object(next_name("Glaze", e["side"]), bm_w, col_det,
                                                       materials=[mat_frame, mat_glass], bevel=0.003)
                            w_obj["detail_audit_ok"] = True
                            created.append(w_obj)
                        else:
                            bm_w.free()

            elif kind == "GLAZED" or (kind == "CANTILEVER" and ops):
                if ops:
                    if wall_valid:
                        obj = wall_with_openings(w_p0, w_p1, z0, z1, wall_t, ops, inward=in_n,
                                                 name=next_name("Wall", e["side"]), col=col_wall)
                        if obj:
                            created.append(obj)
                    bm_g = bmesh.new()
                    for op in ops:
                        ou0, ou1 = op["u"]
                        oz0, oz1 = op["z"] if op.get("z") else (0.9, min(2.4, z1 - z0))
                        orig = Vector((w_p0[0], w_p0[1], z0 + oz0)) + run_n * ou0 - out_n * (wall_t * 0.35)
                        panes_x = max(1, int(round((ou1 - ou0) / 1.2)))
                        DK.add_window(bm_g, orig, run_n, out_n, ou1 - ou0, oz1 - oz0, panes=(panes_x, 1))
                    if bm_g.faces:
                        g_obj = DK.finalize_object(next_name("Glaze", e["side"]), bm_g, col_det,
                                                   materials=[mat_frame, mat_glass], bevel=0.003)
                        g_obj["detail_audit_ok"] = True
                        created.append(g_obj)
                    else:
                        bm_g.free()
                else:
                    # Full curtain-wall bay (solid parapet if sill_h set, else full floor-to-soffit)
                    sill_h = float(rule.get("sill_h", 0.0))
                    if sill_h > 0.05 and wall_valid:
                        obj = wall_with_openings(w_p0, w_p1, z0, z0 + sill_h, wall_t, [], inward=in_n,
                                                 name=next_name("Wall", e["side"]), col=col_wall)
                        if obj:
                            created.append(obj)
                    gt0 = (t0 - ext0 if abs(t0) < 1e-5 and ext0 < 0.0 else t0)
                    gt1 = (t1 + ext1 if abs(t1 - L) < 1e-5 and ext1 < 0.0 else t1)
                    g_p0 = _point_at(e, gt0)
                    g_len = max(0.1, gt1 - gt0)
                    bm_g = bmesh.new()
                    orig = Vector((g_p0[0], g_p0[1], z0 + sill_h)) - out_n * (wall_t * 0.35)
                    panes_x = max(1, int(round(g_len / 1.2)))
                    DK.add_window(bm_g, orig, run_n, out_n, g_len, (z1 - z0) - sill_h, panes=(panes_x, 1))
                    g_obj = DK.finalize_object(next_name("Glaze", e["side"]), bm_g, col_det,
                                               materials=[mat_frame, mat_glass], bevel=0.003)
                    g_obj["detail_audit_ok"] = True
                    created.append(g_obj)

            elif kind == "OPEN":
                if ops and wall_valid:
                    obj = wall_with_openings(w_p0, w_p1, z0, z1, wall_t, ops, inward=in_n,
                                             name=next_name("Wall", e["side"]), col=col_wall)
                    if obj:
                        created.append(obj)
                if rule.get("railing"):
                    bm_r = bmesh.new()
                    p_a = (bay_p0[0] - out_n.x * 0.05, bay_p0[1] - out_n.y * 0.05, z0)
                    p_b = (bay_p1[0] - out_n.x * 0.05, bay_p1[1] - out_n.y * 0.05, z0)
                    DK.add_railing(bm_r, [p_a, p_b], height=float(rule.get("rail_h", 1.0)))
                    r_obj = DK.finalize_object(next_name("Railing", e["side"]), bm_r, col_det, materials=[mat_frame])
                    created.append(r_obj)

            elif kind == "CANTILEVER":
                # Default cantilever edge builds glazed curtain or solid wall per `solid` / `glazed` flag
                if rule.get("glazed"):
                    gt0 = (t0 - ext0 if abs(t0) < 1e-5 and ext0 < 0.0 else t0)
                    gt1 = (t1 + ext1 if abs(t1 - L) < 1e-5 and ext1 < 0.0 else t1)
                    g_p0 = _point_at(e, gt0)
                    g_len = max(0.1, gt1 - gt0)
                    bm_g = bmesh.new()
                    orig = Vector((g_p0[0], g_p0[1], z0)) - out_n * (wall_t * 0.35)
                    DK.add_window(bm_g, orig, run_n, out_n, g_len, z1 - z0, panes=(max(1, int(round(g_len / 1.2))), 1))
                    created.append(DK.finalize_object(next_name("Glaze", e["side"]), bm_g, col_det,
                                                      materials=[mat_frame, mat_glass], bevel=0.003))
                elif wall_valid and (not skin or rule.get("solid", True)):
                    obj = wall_with_openings(w_p0, w_p1, z0, z1, wall_t, [], inward=in_n,
                                             name=next_name("Wall", e["side"]), col=col_wall)
                    if obj:
                        created.append(obj)

            # LOUVER / SLAT overlay skin (single object per facade bay for clean RANDOM shading)
            effective_skin = kind if kind in ("LOUVER", "SLAT") else skin
            if effective_skin in ("LOUVER", "SLAT"):
                bm_s = bmesh.new()
                if effective_skin == "LOUVER":
                    n_leaves = max(1, int(round(seg_len / float(rule.get("leaf_w", 0.9)))))
                    lw = seg_len / n_leaves
                    for i in range(n_leaves):
                        orig = Vector((bay_p0[0], bay_p0[1], z0)) + run_n * (i * lw) + out_n * skin_offset
                        DK.add_louver_leaf(bm_s, orig, run_n, out_n, lw - 0.01, z1 - z0,
                                           blades=int(rule.get("blades", 20)))
                else:
                    p_start = Vector((bay_p0[0], bay_p0[1], 0.0)) + out_n * skin_offset
                    p_end = Vector((bay_p1[0], bay_p1[1], 0.0)) + out_n * skin_offset
                    DK.add_slat_array(bm_s, p_start, p_end, z0, z1,
                                      pitch=float(rule.get("pitch", 0.12)),
                                      slat_w=float(rule.get("slat_w", 0.045)),
                                      slat_t=float(rule.get("slat_t", 0.06)),
                                      normal=out_n, rhombic=bool(rule.get("rhombic", True)))
                if bm_s.faces:
                    s_obj = DK.finalize_object(next_name("Skin", e["side"]), bm_s, col_det,
                                               materials=[mat_skin], bevel="auto")
                    created.append(s_obj)
                else:
                    bm_s.free()

    return created


def add_cantilever(level_id, rect, slab_t=None, support=None, name=None, col=None):
    """Build explicit cantilevered deck `[x0, y0, x1, y1]` under `level_id` FFL with optional steel support
    dict `{'section': 'HEB220', 'pts': [[x,y], ...], 'z_bot': float}`.
    """
    spec = SK.spec_load()
    lv = _level_lookup(spec, level_id)
    z_top = float(lv["z"])
    t = float(slab_t if slab_t is not None else lv.get("slab", 0.30))
    x0, y0, x1, y1 = SK._norm_rect(rect)
    col = col or _model_col("L1_Massing")
    bm = bmesh.new()
    _add_prism_polygon(bm, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z_top - t, z_top, mat_idx=0)
    oname = name or f"{level_id}_Cantilever_{abs(hash((x0, y0, x1, y1))) % 1000}"
    obj = DK.finalize_object(oname, bm, col, materials=[_ensure_mat("Slab_Concrete", (0.72, 0.72, 0.70, 1.0))], bevel=0.0)
    obj["detail_audit_ok"] = True

    created = [obj]
    if support:
        bm_sup = bmesh.new()
        sec = support.get("section", "HEB220")
        zb = float(support.get("z_bot", 0.0))
        for px, py in support.get("pts", []):
            DK.add_steel_member(bm_sup, sec, (px, py, zb), (px, py, z_top - t))
        if support.get("beams"):
            for ba, bb in support["beams"]:
                DK.add_steel_member(bm_sup, sec, (ba[0], ba[1], z_top - t * 1.4), (bb[0], bb[1], z_top - t * 1.4))
        if bm_sup.faces:
            sup_obj = DK.finalize_object(f"{oname}_Support", bm_sup, _model_col("L2_Envelope_Detail"),
                                         materials=[_ensure_mat("Steel_Dark", (0.20, 0.21, 0.23, 1.0))])
            created.append(sup_obj)
        else:
            bm_sup.free()
    return created


def build_level(level_id, wall_t=0.28, skin_offset=0.05):
    """Build slab + exterior envelope for one `level_id`."""
    spec = SK.spec_load()
    slab = None
    walls = []
    if level_id in spec.get("outline", {}):
        slab = build_level_slab(level_id)
        walls = build_envelope(level_id, wall_t=wall_t, skin_offset=skin_offset)
    return {
        "level": level_id,
        "slab": slab.name if slab else None,
        "envelope_objects": [o.name for o in walls],
        "count": (1 if slab else 0) + len(walls),
    }


def build_all_levels(wall_t=0.28, skin_offset=0.05, shading='RANDOM'):
    """Build all levels declared in `spec['levels']` with `outline` entries and ensure `RANDOM` shading."""
    spec = SK.spec_load()
    COR.set_shading_color_mode(shading)
    summary = {}
    for lv in spec.get("levels", []):
        lid = lv["id"]
        if lid in spec.get("outline", {}):
            summary[lid] = build_level(lid, wall_t=wall_t, skin_offset=skin_offset)
    return {
        "levels_built": list(summary.keys()),
        "total_objects": sum(v["count"] for v in summary.values()),
        "details": summary,
    }
