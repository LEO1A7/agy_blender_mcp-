"""[RECIPE_LEVEL_CUT_VERIFY] Blender 真几何楼层剖切导出 · 逐对象奇偶扫描线填充 · 包络IoU/边偏差/虚实规则数值验收
- 适用 (When): P3/P5 用 `bmesh.ops.bisect_plane` 沿每层 `z+cut` 导出剖切线段并输出 `verify_L*.json` 数值报告（仅失败或终验才渲染叠加图）
- 用法 (How) : `from level_cut_verify import export_level_cuts, verify_levels`
- 产出 (Out) : `agy_work/level_cuts.json`、`verify_L*.json` 以及 `<=25` 行数值验收摘要（包络 IoU、边偏差 mm、差异斑块与虚实违例）
"""

import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import spec_kit as SK  # noqa: E402

_THIN_OR_SKIN_TOKENS = ("glaze", "glass", "window", "skin", "louver", "slat", "railing", "batten", "baluster")


def _work_dir():
    return os.environ.get("AGY_WORK_DIR", SK.DEFAULT_WORK_DIR)


def _building_frame_inv_matrix():
    yaw_obj = bpy.data.objects.get("Site_Yaw")
    if yaw_obj is not None:
        return yaw_obj.matrix_world.inverted()
    return Matrix.Identity(4)


def _world_z_span(obj, inv_yaw):
    mw = inv_yaw @ obj.matrix_world
    zs = [(mw @ Vector(c)).z for c in obj.bound_box]
    return min(zs), max(zs)


def _should_ignore(obj, ignore_prefixes):
    if obj.type != 'MESH' or obj.hide_viewport or obj.hide_render:
        return True
    if obj.name.startswith(("__hide_r", "__wip__", "_tmp_")):
        return True
    for p in ignore_prefixes:
        base = p.rstrip("*")
        if obj.name.startswith(base):
            return True
    cols = list(obj.users_collection)
    if cols and all(c.name.endswith("_WIP") or c.name.startswith(("__hide_r", "__wip__")) for c in cols):
        return True
    for c in cols:
        for p in ignore_prefixes:
            base = p.rstrip("*")
            if c.name.startswith(base):
                return True
    return False


def _slice_object_at_z(obj, inv_yaw, z_cut, zone=None):
    """Slice one mesh object horizontally at `z_cut` in local building coordinates.
    Returns `(segments, horizontal_face_near_cut)`.
    """
    mw = inv_yaw @ obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(mw)

    horiz_hit = False
    for f in bm.faces:
        if abs(f.normal.z) > 0.95 and f.calc_area() > 0.05:
            fz = f.verts[0].co.z
            if abs(fz - z_cut) < 0.08:
                horiz_hit = True
                break

    ret = bmesh.ops.bisect_plane(
        bm,
        geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
        plane_co=(0.0, 0.0, z_cut),
        plane_no=(0.0, 0.0, 1.0),
        dist=1e-5,
    )
    segs = []
    for g in ret.get("geom_cut", []):
        if isinstance(g, bmesh.types.BMEdge):
            a = g.verts[0].co
            b = g.verts[1].co
            if (a.xy - b.xy).length < 1e-6:
                continue
            if zone is not None:
                mx, my = 0.5 * (a.x + b.x), 0.5 * (a.y + b.y)
                zx0, zy0, zx1, zy1 = zone
                if not (zx0 - 0.05 <= mx <= zx1 + 0.05 and zy0 - 0.05 <= my <= zy1 + 0.05):
                    continue
            segs.append(((round(a.x, 5), round(a.y, 5)), (round(b.x, 5), round(b.y, 5))))
    bm.free()
    return segs, horiz_hit


def _is_solid_struct_name(name: str) -> bool:
    low = name.lower()
    return not any(tok in low for tok in _THIN_OR_SKIN_TOKENS)


def export_level_cuts(out_json=None, levels=None, ignore=("Studio", "Cam_*", "BBOX_*", "Site_Yaw", "__hide_r*", "__wip*"), spec=None):
    """Slice scene geometry at each level's `z + cut` (auto-shifting +/-0.12m if within 0.08m of a horizontal face)
    and write segments grouped per object to `level_cuts.json`.
    """
    spec = spec or SK.spec_load()
    inv_yaw = _building_frame_inv_matrix()
    candidates = [o for o in bpy.data.objects if not _should_ignore(o, ignore)]
    z_cache = {o.name: _world_z_span(o, inv_yaw) for o in candidates}

    level_list = spec.get("levels", [])
    if levels:
        wanted = set(levels)
        level_list = [lv for lv in level_list if lv["id"] in wanted]

    cuts = {}
    for lv in level_list:
        lid = lv["id"]
        if lid not in spec.get("outline", {}):
            continue
        z_floor = float(lv["z"])
        slab_t = float(lv.get("slab", 0.30))
        z_cut_base = z_floor + float(lv.get("cut", 1.5))
        zone = lv.get("zone")
        lv_bb = SK.resolve_outline(lid, spec)["bbox"]
        z_cut = z_cut_base
        adjusted = False
        reason = ""

        def _overlaps_level_xy(obj):
            mw = inv_yaw @ obj.matrix_world
            pts = [mw @ Vector(c) for c in obj.bound_box]
            ox0, ox1 = min(p.x for p in pts), max(p.x for p in pts)
            oy0, oy1 = min(p.y for p in pts), max(p.y for p in pts)
            dom = zone if zone is not None else [lv_bb[0] - 0.5, lv_bb[1] - 0.5, lv_bb[2] + 0.5, lv_bb[3] + 0.5]
            return (min(ox1, dom[2]) > max(ox0, dom[0]) + 0.05 and
                    min(oy1, dom[3]) > max(oy0, dom[1]) + 0.05)

        def run_pass(zc):
            by_obj = {}
            any_horiz = False
            for o in candidates:
                zlo, zhi = z_cache[o.name]
                if zlo - 0.09 > zc or zhi + 0.09 < zc:
                    continue
                segs, h_hit = _slice_object_at_z(o, inv_yaw, zc, zone=zone)
                if h_hit and _overlaps_level_xy(o):
                    any_horiz = True
                if segs:
                    by_obj[o.name] = {
                        "solid": _is_solid_struct_name(o.name),
                        "segs": segs,
                    }
            return by_obj, any_horiz

        by_obj, any_horiz = run_pass(z_cut)
        if any_horiz:
            # Prefer +0.12 m shift unless it also collides with a slab face, else -0.12 m
            alt_plus, hit_plus = run_pass(z_cut_base + 0.12)
            if not hit_plus:
                z_cut, by_obj, adjusted, reason = round(z_cut_base + 0.12, 4), alt_plus, True, "shifted +0.12m away from horizontal slab face"
            else:
                alt_minus, hit_minus = run_pass(z_cut_base - 0.12)
                if not hit_minus:
                    z_cut, by_obj, adjusted, reason = round(z_cut_base - 0.12, 4), alt_minus, True, "shifted -0.12m away from horizontal slab face"

        # Slice slabs at mid-slab elevation so verify_levels can validate courtyard cutouts cleanly
        z_slab = z_floor - 0.5 * max(0.06, slab_t)
        slab_segs = []
        for o in candidates:
            zlo, zhi = z_cache[o.name]
            if zlo <= z_slab <= zhi and ("slab" in o.name.lower() or "cantilever" in o.name.lower()):
                segs, _ = _slice_object_at_z(o, inv_yaw, z_slab, zone=zone)
                slab_segs.extend(segs)

        cuts[lid] = {
            "level": lid,
            "z_floor": z_floor,
            "z_cut": z_cut,
            "z_cut_requested": z_cut_base,
            "z_cut_adjusted": adjusted,
            "adjust_reason": reason,
            "zone": zone,
            "objects": by_obj,
            "slab_segs": slab_segs,
        }

    out_path = out_json or os.path.join(_work_dir(), "level_cuts.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cuts, f, indent=2, ensure_ascii=False)
    return {"path": out_path, "levels": {k: len(v["objects"]) for k, v in cuts.items()}, "cuts": cuts}


# ==============================================================================
# 2. PURE-NUMPY EVEN-ODD RASTERIZER, ENVELOPE IOU & EDGE VERIFICATION
# ==============================================================================

def _draw_seg_thick(mask, ax, ay, bx, by, x0, y0, step, H, W):
    dist = math.hypot(bx - ax, by - ay)
    n = max(2, int(math.ceil(dist / (step * 0.5))) + 1)
    xs = np.linspace(ax, bx, n)
    ys = np.linspace(ay, by, n)
    cs = np.clip(((xs - x0) / step).astype(np.int32), 0, W - 1)
    rs = np.clip(((ys - y0) / step).astype(np.int32), 0, H - 1)
    mask[rs, cs] = True


def _rasterize_segments_even_odd(segs, x0, y0, step, H, W, stroke=True):
    """Per-object even-odd scanline fill across Y range of `segs`, plus optional boundary stroke."""
    mask = np.zeros((H, W), dtype=bool)
    if not segs:
        return mask
    arr = np.array(segs, dtype=np.float64)  # (N, 2, 2)
    ymin_s = float(np.min(arr[:, :, 1]))
    ymax_s = float(np.max(arr[:, :, 1]))
    r0 = max(0, int(math.floor((ymin_s - y0) / step)))
    r1 = min(H - 1, int(math.ceil((ymax_s - y0) / step)))
    ax, ay = arr[:, 0, 0], arr[:, 0, 1]
    bx, by = arr[:, 1, 0], arr[:, 1, 1]
    dy = by - ay

    for r in range(r0, r1 + 1):
        yc = y0 + (r + 0.5) * step
        cross = ((ay <= yc) & (yc < by)) | ((by <= yc) & (yc < ay))
        if not np.any(cross):
            continue
        x_int = ax[cross] + (yc - ay[cross]) * (bx[cross] - ax[cross]) / dy[cross]
        x_int.sort()
        for k in range(0, len(x_int) - 1, 2):
            c0 = max(0, int(math.floor((x_int[k] - x0) / step)))
            c1 = min(W, max(c0 + 1, int(math.ceil((x_int[k + 1] - x0) / step))))
            mask[r, c0:c1] = True

    if stroke:
        for (p0, p1) in segs:
            _draw_seg_thick(mask, p0[0], p0[1], p1[0], p1[1], x0, y0, step, H, W)
    return mask


def _rasterize_rings(outers, holes, x0, y0, step, H, W):
    segs = []
    for ring in list(outers) + list(holes):
        n = len(ring)
        for i in range(n):
            segs.append((ring[i], ring[(i + 1) % n]))
    return _rasterize_segments_even_odd(segs, x0, y0, step, H, W, stroke=False)


def _box_morph_1d(arr, r, op):
    if r <= 0:
        return arr.copy()
    H, W = arr.shape
    w = 2 * r + 1
    # Horizontal pass
    a_int = arr.astype(np.int32)
    ph = np.pad(a_int, ((0, 0), (r, r)), mode="edge")
    cs = np.cumsum(np.pad(ph, ((0, 0), (1, 0)), mode="constant"), axis=1)
    s_h = cs[:, w:] - cs[:, :-w]
    h_out = (s_h > 0) if op == "dilate" else (s_h == w)
    # Vertical pass
    pv = np.pad(h_out.astype(np.int32), ((r, r), (0, 0)), mode="edge")
    csv = np.cumsum(np.pad(pv, ((1, 0), (0, 0)), mode="constant"), axis=0)
    s_v = csv[w:, :] - csv[:-w, :]
    return (s_v > 0) if op == "dilate" else (s_v == w)


def _morph_close(mask, r):
    return _box_morph_1d(_box_morph_1d(mask, r, "dilate"), r, "erode")


def _fill_enclosed_holes(mask, extra_seeds=()):
    """Scanline-run exterior flood fill -> returns `~exterior` (pure numpy/Python, zero scipy)."""
    H, W = mask.shape
    blocked = mask
    visited = np.zeros((H, W), dtype=bool)
    from collections import deque
    q = deque()

    def seed_point(r0, c0):
        if not (0 <= r0 < H and 0 <= c0 < W) or blocked[r0, c0] or visited[r0, c0]:
            return
        s = c0
        while s > 0 and not blocked[r0, s - 1]:
            s -= 1
        e = c0 + 1
        while e < W and not blocked[r0, e]:
            e += 1
        visited[r0, s:e] = True
        q.append((r0, s, e))

    def push_runs(r, c_start, c_end):
        row_b = blocked[r]
        row_v = visited[r]
        c = c_start
        while c < c_end:
            while c < c_end and (row_b[c] or row_v[c]):
                c += 1
            if c >= c_end:
                break
            s = c
            while c < c_end and not row_b[c]:
                row_v[c] = True
                c += 1
            q.append((r, s, c))

    # Seed top/bottom rows, left/right borders, plus any verified courtyard interior points
    for r in (0, H - 1):
        push_runs(r, 0, W)
    for r in range(1, H - 1):
        for c in (0, W - 1):
            seed_point(r, c)
    for r0, c0 in extra_seeds:
        seed_point(r0, c0)

    while q:
        r, s, e = q.popleft()
        # Expand full unobstructed span left/right in row r if seeded partially
        while s > 0 and not blocked[r, s - 1] and not visited[r, s - 1]:
            s -= 1
            visited[r, s] = True
        while e < W and not blocked[r, e] and not visited[r, e]:
            visited[r, e] = True
            e += 1
        if r > 0:
            push_runs(r - 1, s, e)
        if r + 1 < H:
            push_runs(r + 1, s, e)
    return ~visited


def _connected_patches(diff_mask, spec_mask, live_env, x0, y0, step, edges, min_area_m2=0.15):
    """Extract connected discrepancy blobs from `diff_mask` via row-run BFS."""
    H, W = diff_mask.shape
    seen = np.zeros((H, W), dtype=bool)
    cell_area = step * step
    min_cells = max(4, int(round(min_area_m2 / cell_area)))
    from collections import deque
    patches = []

    ys, xs = np.where(diff_mask)
    for r0, c0 in zip(ys.tolist(), xs.tolist()):
        if seen[r0, c0]:
            continue
        q = deque([(r0, c0)])
        seen[r0, c0] = True
        cells = []
        while q:
            r, c = q.popleft()
            cells.append((r, c))
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < H and 0 <= nc < W and diff_mask[nr, nc] and not seen[nr, nc]:
                    seen[nr, nc] = True
                    q.append((nr, nc))
        if len(cells) < min_cells:
            continue
        rs = [p[0] for p in cells]
        cs = [p[1] for p in cells]
        r_min, r_max, c_min, c_max = min(rs), max(rs), min(cs), max(cs)
        in_spec = sum(1 for r, c in cells if spec_mask[r, c])
        kind = "MISSING" if in_spec >= len(cells) * 0.5 else "EXTRA"
        bbox = [
            round(x0 + c_min * step, 2),
            round(y0 + r_min * step, 2),
            round(x0 + (c_max + 1) * step, 2),
            round(y0 + (r_max + 1) * step, 2),
        ]
        cx, cy = 0.5 * (bbox[0] + bbox[2]), 0.5 * (bbox[1] + bbox[3])
        nearest = min(edges, key=lambda e: _pt_seg_dist(cx, cy, e["p0"], e["p1"])) if edges else None
        side_str = f"{nearest['id']}({nearest['side']})" if nearest else "?"
        patches.append({
            "kind": kind,
            "area_m2": round(len(cells) * cell_area, 2),
            "bbox": bbox,
            "near_edge": side_str,
            "hint": f"{'build missing volume' if kind == 'MISSING' else 'trim over-projection'} near {side_str} {bbox}",
        })
    patches.sort(key=lambda p: -p["area_m2"])
    return patches[:8]


def _pt_seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / l2))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _edge_offset_error_mm(edge, live_env, x0, y0, step, search_m=0.65):
    """Measure signed outer boundary offset along normal of `edge` from `live_env`."""
    H, W = live_env.shape
    n_samples = max(3, int(round(edge["length"] / 0.15)))
    ox, oy = edge["outward"]
    ix, iy = edge["inward"]
    d_steps = np.arange(-search_m, search_m + 0.5 * step, step)
    errs_mm = []
    # Trim endpoints by 0.35m so corner junctions don't skew straight-edge measurement
    trim = min(0.35, edge["length"] * 0.15)
    for k in range(n_samples):
        u = trim + (edge["length"] - 2 * trim) * (k + 0.5) / n_samples
        t = u / edge["length"]
        px = edge["p0"][0] + (edge["p1"][0] - edge["p0"][0]) * t
        py = edge["p0"][1] + (edge["p1"][1] - edge["p0"][1]) * t
        xs = px + ox * d_steps
        ys = py + oy * d_steps
        cs = np.clip(((xs - x0) / step).astype(np.int32), 0, W - 1)
        rs = np.clip(((ys - y0) / step).astype(np.int32), 0, H - 1)
        vals = live_env[rs, cs]
        # Outer boundary is the transition from True (inside) to False (outside) along outward normal
        true_idxs = np.where(vals)[0]
        if len(true_idxs) == 0 or len(true_idxs) == len(vals):
            continue
        last_true = int(true_idxs[-1])
        d_est = float(d_steps[last_true]) + 0.5 * step
        errs_mm.append(abs(d_est) * 1000.0)
    if not errs_mm:
        return None
    return round(float(np.percentile(errs_mm, 85)), 1)


def _sub_interval_solid_frac(edge, s0, s1, cut_solid, x0, y0, step, wall_t=0.35, d_offset=0.0):
    """Fraction of length `[s0, s1]` along `edge` covered by solid cut pixels in inward band `[d_offset, d_offset+wall_t+0.15]`."""
    H, W = cut_solid.shape
    span_len = s1 - s0
    if span_len <= 1e-4:
        return 1.0
    n_u = max(3, int(round(span_len / 0.06)))
    n_n = max(3, int(round((wall_t + 0.15) / step)))
    ns = np.linspace(d_offset + 0.02, d_offset + wall_t + 0.15, n_n)
    ix, iy = edge["inward"]
    hits = 0
    for k in range(n_u):
        u = s0 + span_len * (k + 0.5) / n_u
        t = u / edge["length"]
        px = edge["p0"][0] + (edge["p1"][0] - edge["p0"][0]) * t
        py = edge["p0"][1] + (edge["p1"][1] - edge["p0"][1]) * t
        xs = px + ix * ns
        ys = py + iy * ns
        cs = np.clip(((xs - x0) / step).astype(np.int32), 0, W - 1)
        rs = np.clip(((ys - y0) / step).astype(np.int32), 0, H - 1)
        if np.any(cut_solid[rs, cs]):
            hits += 1
    return round(hits / n_u, 3)


def _match_edge_rule_pieces(e, rules):
    """Partition edge `[0, L]` into `[(seg_a, seg_b, rule, aw), ...]` using spec rules, defaulting rest to SOLID."""
    L = e["length"]
    covered = []
    for r in rules:
        for _, (a_w, b_w) in SK.match_rule_to_edges(r, [e]):
            if e["side"] in ("N", "S"):
                p0x, p1x = e["p0"][0], e["p1"][0]
                t0, t1 = (a_w - p0x) / (p1x - p0x) * L, (b_w - p0x) / (p1x - p0x) * L
            elif e["side"] in ("E", "W"):
                p0y, p1y = e["p0"][1], e["p1"][1]
                t0, t1 = (a_w - p0y) / (p1y - p0y) * L, (b_w - p0y) / (p1y - p0y) * L
            else:
                t0, t1 = a_w, b_w
            ta, tb = max(0.0, min(t0, t1)), min(L, max(t0, t1))
            if tb - ta > 0.15:
                covered.append((ta, tb, r, min(a_w, b_w)))

    covered.sort(key=lambda x: x[0])
    cur = 0.0
    full_segs = []
    for ta, tb, r, aw in covered:
        if ta - cur > 0.25:
            full_segs.append((cur, ta, {"kind": "SOLID"}, 0.0))
        full_segs.append((ta, tb, r, aw))
        cur = max(cur, tb)
    if L - cur > 0.25:
        full_segs.append((cur, L, {"kind": "SOLID"}, 0.0))
    return full_segs


def _check_edge_rules(level_id, spec, lv, edges, z_cut, cut_solid, x0, y0, step):
    rules = [r for r in spec.get("edge_rules", []) if r.get("level") == level_id]
    z_floor = float(lv["z"])
    slab_t = float(lv.get("slab", 0.30))
    z_rel = z_cut - z_floor
    violations = []
    for e in edges:
        L = e["length"]
        pad_c = min(0.32, L * 0.32)
        full_segs = _match_edge_rule_pieces(e, rules)

        for seg_a, seg_b, rule, aw in full_segs:
            qa = max(seg_a, pad_c if abs(seg_a) < 1e-4 else seg_a)
            qb = min(seg_b, L - pad_c if abs(seg_b - L) < 1e-4 else seg_b)
            if qb - qa < 0.25:
                continue
            kind = rule.get("kind", "SOLID")
            d_off = float(rule.get("depth", 0.0)) if kind == "RECESS" else 0.0
            if kind == "STEP":
                dz = float(rule.get("dz", 0.0))
                z_lo, z_hi = min(z_floor, z_floor + dz), max(z_floor, z_floor + dz) + slab_t
                if z_lo <= z_cut <= z_hi:
                    cov = _sub_interval_solid_frac(e, qa, qb, cut_solid, x0, y0, step)
                    if cov < 0.85:
                        violations.append(f"{e['id']}({e['side']}) [{qa:.1f},{qb:.1f}] STEP missing riser cov={cov:.2f}")
                continue
            if kind in ("SOLID", "RECESS"):
                # Subtract openings intersecting z_cut!
                open_spans = []
                rspan = rule.get("span")
                u_off = (aw - float(rspan[0])) if rspan else 0.0
                for op in rule.get("openings", []) or ():
                    oz = op.get("z", [0.9, 2.4])
                    if oz[0] <= z_rel <= oz[1]:
                        oa = seg_a + float(op["u"][0]) - u_off
                        ob = seg_a + float(op["u"][1]) - u_off
                        open_spans.append((max(qa, oa), min(qb, ob)))
                open_spans.sort()
                # Measure expected-solid sub-intervals
                scur = qa
                for oa, ob in open_spans:
                    if oa - scur > 0.25:
                        cov = _sub_interval_solid_frac(e, scur, oa, cut_solid, x0, y0, step, d_offset=d_off)
                        if cov < 0.90:
                            violations.append(f"{e['id']}({e['side']}) [{scur:.1f},{oa:.1f}] {kind} cov={cov:.2f} (<0.90)")
                    if ob - oa > 0.25:
                        cov_o = _sub_interval_solid_frac(e, oa, ob, cut_solid, x0, y0, step, d_offset=d_off)
                        if cov_o > 0.35:
                            violations.append(f"{e['id']}({e['side']}) [{oa:.1f},{ob:.1f}] OPENING blocked cov={cov_o:.2f} (>0.35)")
                    scur = max(scur, ob)
                if qb - scur > 0.25:
                    cov = _sub_interval_solid_frac(e, scur, qb, cut_solid, x0, y0, step, d_offset=d_off)
                    if cov < 0.90:
                        violations.append(f"{e['id']}({e['side']}) [{scur:.1f},{qb:.1f}] {kind} cov={cov:.2f} (<0.90)")
            elif kind == "OPEN" or (kind == "GLAZED" and not rule.get("openings")):
                cov = _sub_interval_solid_frac(e, qa, qb, cut_solid, x0, y0, step)
                if cov > 0.35:
                    violations.append(f"{e['id']}({e['side']}) [{qa:.1f},{qb:.1f}] {kind} has solid wall cov={cov:.2f} (>0.35)")
            elif kind == "GLAZED" and rule.get("openings"):
                rspan = rule.get("span")
                u_off = (aw - float(rspan[0])) if rspan else 0.0
                for op in rule.get("openings", []):
                    oz = op.get("z", [0.9, 2.4])
                    if oz[0] <= z_rel <= oz[1]:
                        oa = max(qa, seg_a + float(op["u"][0]) - u_off)
                        ob = min(qb, seg_a + float(op["u"][1]) - u_off)
                        if ob - oa > 0.25:
                            cov = _sub_interval_solid_frac(e, oa, ob, cut_solid, x0, y0, step)
                            if cov > 0.35:
                                violations.append(f"{e['id']}({e['side']}) [{oa:.1f},{ob:.1f}] GLAZED opening blocked cov={cov:.2f} (>0.35)")
    return violations


def verify_levels(cuts_json=None, spec=None, tol_mm=150, iou_min=0.90, px_mm=20):
    """Run numerical floor-cut verification against Building Spec (per-object even-odd rasterization +
    envelope IoU + edge offsets + solid/void rule coverage). Writes `verify_L*.json` & returns <=25-line report.
    """
    spec = spec or SK.spec_load()
    if cuts_json is None:
        cut_data = export_level_cuts(spec=spec)["cuts"]
    elif isinstance(cuts_json, dict) and "cuts" in cuts_json:
        cut_data = cuts_json["cuts"]
    elif isinstance(cuts_json, dict):
        cut_data = cuts_json
    else:
        with open(cuts_json, "r", encoding="utf-8") as f:
            cut_data = json.load(f)

    step = float(px_mm) / 1000.0
    close_r = max(1, int(round(0.70 / step)))  # 0.70m seals doors <=1.4m without creating missing wings
    all_passed = True
    reports = {}
    lines = [f"VERIFY_LEVELS tol={tol_mm}mm iou>={iou_min:.2f} grid={px_mm}mm:"]

    for lv in spec.get("levels", []):
        lid = lv["id"]
        if lid not in spec.get("outline", {}):
            continue
        cinfo = cut_data.get(lid, {"objects": {}, "z_cut": float(lv["z"]) + float(lv.get("cut", 1.5))})
        res = SK.resolve_outline(lid, spec)
        edges = SK.outline_edges(lid, spec, include_holes=False)
        bb = list(res["bbox"])
        all_pts = [p for obj in cinfo["objects"].values() for seg in obj["segs"] for p in seg]
        if all_pts:
            bb[0] = min(bb[0], min(p[0] for p in all_pts))
            bb[1] = min(bb[1], min(p[1] for p in all_pts))
            bb[2] = max(bb[2], max(p[0] for p in all_pts))
            bb[3] = max(bb[3], max(p[1] for p in all_pts))
        x0, y0 = bb[0] - 1.0, bb[1] - 1.0
        x1, y1 = bb[2] + 1.0, bb[3] + 1.0
        W = max(16, int(math.ceil((x1 - x0) / step)))
        H = max(16, int(math.ceil((y1 - y0) / step)))

        spec_mask = _rasterize_rings(res["outers"], res["holes"], x0, y0, step, H, W)
        cut_shell = np.zeros((H, W), dtype=bool)
        cut_solid = np.zeros((H, W), dtype=bool)
        for odata in cinfo["objects"].values():
            omask = _rasterize_segments_even_odd(odata["segs"], x0, y0, step, H, W, stroke=True)
            cut_shell |= omask
            if odata.get("solid", True):
                cut_solid |= omask

        # Fill enclosed interior between outer cut walls, bridging declared & wall-anchored OPEN bays
        # and seeding flood-fill inside verified empty courtyard holes (absent from slab_segs).
        if np.any(cut_shell):
            shell_for_fill = cut_shell.copy()
            lv_rules = [r for r in spec.get("edge_rules", []) if r.get("level") == lid]
            r_anchor = max(1, int(round(0.85 / step)))
            for e in edges:
                L = e["length"]
                if L < 1e-6:
                    continue
                for seg_a, seg_b, rule, _ in _match_edge_rule_pieces(e, lv_rules):
                    if rule.get("kind") != "OPEN":
                        continue
                    pa = (e["p0"][0] + (e["p1"][0] - e["p0"][0]) * (seg_a / L),
                          e["p0"][1] + (e["p1"][1] - e["p0"][1]) * (seg_a / L))
                    pb = (e["p0"][0] + (e["p1"][0] - e["p0"][0]) * (seg_b / L),
                          e["p0"][1] + (e["p1"][1] - e["p0"][1]) * (seg_b / L))

                    def _has_cut_near(pt):
                        cc = max(0, min(W - 1, int(round((pt[0] - x0) / step))))
                        rr = max(0, min(H - 1, int(round((pt[1] - y0) / step))))
                        return bool(np.any(cut_shell[max(0, rr - r_anchor):min(H, rr + r_anchor + 1),
                                                     max(0, cc - r_anchor):min(W, cc + r_anchor + 1)]))

                    if _has_cut_near(pa) and _has_cut_near(pb):
                        _draw_seg_thick(shell_for_fill, pa[0], pa[1], pb[0], pb[1], x0, y0, step, H, W)

            dil = _box_morph_1d(shell_for_fill, close_r, "dilate")
            extra_seeds = []
            if res["holes"]:
                slab_segs = cinfo.get("slab_segs", [])
                slab_mask = (_rasterize_segments_even_odd(slab_segs, x0, y0, step, H, W, stroke=False)
                             if slab_segs else np.zeros((H, W), dtype=bool))
                for h_ring in res["holes"]:
                    h_mask = _rasterize_rings([h_ring], [], x0, y0, step, H, W)
                    cand_rc = np.argwhere(h_mask & (~dil) & (~slab_mask))
                    if len(cand_rc) > 0:
                        mid = cand_rc[len(cand_rc) // 2]
                        extra_seeds.append((int(mid[0]), int(mid[1])))
            filled = _fill_enclosed_holes(dil, extra_seeds=extra_seeds)
            live_env = _box_morph_1d(filled, close_r, "erode")
        else:
            live_env = np.zeros((H, W), dtype=bool)

        inter = int(np.sum(spec_mask & live_env))
        union = int(np.sum(spec_mask | live_env))
        iou = round(inter / union, 4) if union > 0 else 0.0

        edge_errs = {}
        max_edge_mm = 0.0
        for e in edges:
            err = _edge_offset_error_mm(e, live_env, x0, y0, step)
            if err is not None:
                edge_errs[f"{e['id']}({e['side']})"] = err
                if err > max_edge_mm:
                    max_edge_mm = err

        patches = _connected_patches(spec_mask ^ live_env, spec_mask, live_env, x0, y0, step, edges)
        violations = _check_edge_rules(lid, spec, lv, edges, float(cinfo["z_cut"]), cut_solid, x0, y0, step)

        lv_pass = (iou >= iou_min) and (max_edge_mm <= tol_mm) and (len(violations) == 0)
        if not lv_pass:
            all_passed = False

        rep = {
            "level": lid,
            "z_cut": cinfo["z_cut"],
            "z_cut_adjusted": cinfo.get("z_cut_adjusted", False),
            "passed": lv_pass,
            "iou": iou,
            "max_edge_err_mm": max_edge_mm,
            "edge_errs_mm": edge_errs,
            "rule_violations": violations,
            "patches": patches,
        }
        reports[lid] = rep
        v_path = os.path.join(_work_dir(), f"verify_{lid}.json")
        os.makedirs(os.path.dirname(os.path.abspath(v_path)), exist_ok=True)
        with open(v_path, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)

        status = "PASS" if lv_pass else "FAIL"
        adj_tag = "*" if rep["z_cut_adjusted"] else ""
        lines.append(f"  {lid}@{cinfo['z_cut']:.2f}{adj_tag}: {status} IoU={iou:.3f} max_err={max_edge_mm:.0f}mm viol={len(violations)} patch={len(patches)}")
        if not lv_pass:
            for p in patches[:2]:
                lines.append(f"    [{p['kind']}] {p['area_m2']}m2 {p['hint']}")
            for v in violations[:2]:
                lines.append(f"    [RULE] {v}")

    if not reports:
        all_passed = False
        lines.append("  (FAIL: no levels with valid outlines found in spec)")

    # Persist summary into spec
    try:
        SK.spec_set("progress.last_verify", {k: ("PASS" if v["passed"] else f"FAIL(IoU={v['iou']:.2f})") for k, v in reports.items()})
    except Exception:
        pass

    lines.append(f"OVERALL: {'PASS' if all_passed else 'FAIL'}")
    report_text = "\n".join(lines[:25])
    return {"passed": all_passed, "report": report_text, "levels": reports}
