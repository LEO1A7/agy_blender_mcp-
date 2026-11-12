"""[RECIPE_SPEC_KIT] Architectural Building Spec JSON 唯一真源 · 矩形并差布尔转环 · 轮廓边规则校验 · 摘要再注入
- 适用 (When): P0~P5 全流程锚定楼层标高/比例/偏航、以 `[x0,y0,x1,y1]` 矩形并差 DSL 定义轮廓与层间增量 (`base+add+sub`)、校验边规则并输出 ≤40 行状态摘要
- 用法 (How) : 系统 Python 或 Blender 内 `from spec_kit import spec_init, spec_set, spec_patch, spec_note, resolve_outline, outline_edges, spec_validate, spec_digest, phase_next`
- 产出 (Out) : 持久化 `./agy_work/building_spec.json`(+Blender `scene["agy_spec"]` 镜像)、精确外环/孔环顶点、校验错误码与 ≤40 行上下文恢复卡
"""

import copy
import json
import math
import os
import re

try:
    import bpy  # type: ignore
except ImportError:  # Pure-Python CLI / unit test mode
    bpy = None

SPEC_SCENE_KEY = "agy_spec"
SPEC_PATH_KEY = "agy_spec_path"
DEFAULT_WORK_DIR = "agy_work"

VALID_EDGE_KINDS = ("SOLID", "GLAZED", "OPEN", "CANTILEVER", "RECESS", "STEP", "LOUVER", "SLAT")
VALID_SKIN_KINDS = ("LOUVER", "SLAT", "GLAZED", "NONE", "")
VALID_SIDES = ("N", "S", "E", "W")
VALID_CONFS = ("H", "M", "L")
EDGE_OBLIQUE_DIR_TOL = 1e-4

_ACTIVE_SPEC_PATH = None


def default_spec_path():
    if _ACTIVE_SPEC_PATH:
        return _ACTIVE_SPEC_PATH
    if bpy is not None and getattr(bpy, "context", None) and getattr(bpy.context, "scene", None):
        p = bpy.context.scene.get(SPEC_PATH_KEY)
        if p:
            return str(p)
    work = os.environ.get("AGY_WORK_DIR", DEFAULT_WORK_DIR)
    return os.path.join(work, "building_spec.json")


def _set_active_path(path):
    global _ACTIVE_SPEC_PATH
    _ACTIVE_SPEC_PATH = os.path.abspath(path)
    if bpy is not None and getattr(bpy, "context", None) and getattr(bpy.context, "scene", None):
        bpy.context.scene[SPEC_PATH_KEY] = _ACTIVE_SPEC_PATH
    return _ACTIVE_SPEC_PATH


def _mirror_to_scene(spec):
    if bpy is not None and getattr(bpy, "context", None) and getattr(bpy.context, "scene", None):
        bpy.context.scene[SPEC_SCENE_KEY] = json.dumps(spec, ensure_ascii=False)


def spec_save(spec_or_path=None, path=None):
    """Save spec dict to JSON file and mirror into `scene['agy_spec']` if inside Blender."""
    if isinstance(spec_or_path, dict):
        spec = spec_or_path
        target = path or default_spec_path()
    elif isinstance(spec_or_path, str):
        target = spec_or_path
        spec = spec_load(target) if path is None else path
    else:
        target = path or default_spec_path()
        spec = spec_load(target)
    target = _set_active_path(target)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    _mirror_to_scene(spec)
    return target


def spec_load(path=None):
    """Load spec dict from JSON file or Blender `scene['agy_spec']`."""
    if path:
        ap = _set_active_path(path)
        if os.path.exists(ap):
            with open(ap, "r", encoding="utf-8") as f:
                data = json.load(f)
            _mirror_to_scene(data)
            return data
    if bpy is not None and getattr(bpy, "context", None) and getattr(bpy.context, "scene", None):
        raw = bpy.context.scene.get(SPEC_SCENE_KEY)
        if raw:
            return json.loads(raw)
    ap = default_spec_path()
    if os.path.exists(ap):
        with open(ap, "r", encoding="utf-8") as f:
            data = json.load(f)
        _set_active_path(ap)
        _mirror_to_scene(data)
        return data
    raise FileNotFoundError(f"Building spec not found at {ap!r}; call spec_init() first.")


def spec_init(path=None, **frame):
    """Initialize a fresh v1 Building Spec JSON (and Blender scene mirror)."""
    target = _set_active_path(path or default_spec_path())
    fr = {
        "yaw_deg": float(frame.get("yaw_deg", 0.0)),
        "scale_m_per_px": frame.get("scale_m_per_px"),
        "origin": frame.get("origin", "ROI SW corner"),
        "src": frame.get("src", ""),
    }
    for k, v in frame.items():
        if k not in fr:
            fr[k] = v
    spec = {
        "v": 1,
        "frame": fr,
        "levels": [],
        "outline": {},
        "edge_rules": [],
        "elements": [],
        "notes": [],
        "progress": {"phase": "P0", "gates": {}, "iters": {}, "last_verify": None},
        "deviations": [],
    }
    spec_save(spec, target)
    return spec


def _ensure_spec(path=None):
    try:
        return spec_load(path)
    except FileNotFoundError:
        return spec_init(path)


def spec_set(section, data, path=None, replace=False):
    """Update a top-level section or dotted key (e.g. `'outline.L1'`, `'frame.scale_m_per_px'`).
    When updating a dict section cleanly without `replace=True`, keys are merged rather than wiped."""
    spec = _ensure_spec(path)
    parts = [p for p in str(section).replace("/", ".").split(".") if p]
    if not parts:
        raise ValueError("section cannot be empty")
    cur = spec
    for key in parts[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    last = parts[-1]
    if not replace and isinstance(cur.get(last), dict) and isinstance(data, dict):
        cur[last].update(copy.deepcopy(data))
    else:
        cur[last] = copy.deepcopy(data)
    spec_save(spec, path)
    return spec


def _resolve_parent_container(spec, ptr):
    parts = [p for p in str(ptr).strip("/").replace("/", ".").split(".") if p]
    if not parts:
        raise ValueError(f"Invalid patch path: {ptr!r}")
    cur = spec
    for p in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(p)]
        else:
            if p not in cur:
                cur[p] = {}
            cur = cur[p]
    return cur, parts[-1]


def spec_patch(ops, path=None):
    """Apply patch op(s) `{op: 'set'|'add'|'replace'|'append'|'remove', path: 'a.b', value: ...}`."""
    spec = _ensure_spec(path)
    if isinstance(ops, dict):
        ops = [ops]
    for item in ops:
        op = item.get("op", "set").lower()
        target_path = item["path"]
        parent, key = _resolve_parent_container(spec, target_path)
        if op in ("set", "add", "replace"):
            val = copy.deepcopy(item.get("value"))
            if isinstance(parent, list):
                idx = len(parent) if key == "-" else int(key)
                if idx == len(parent):
                    parent.append(val)
                else:
                    parent[idx] = val
            else:
                parent[key] = val
        elif op == "append":
            val = copy.deepcopy(item.get("value"))
            if isinstance(parent, list):
                parent.append(val)
            else:
                parent.setdefault(key, [])
                if isinstance(val, list) and item.get("extend"):
                    parent[key].extend(val)
                else:
                    parent[key].append(val)
        elif op in ("remove", "del", "delete"):
            if isinstance(parent, list):
                parent.pop(int(key))
            else:
                parent.pop(key, None)
        else:
            raise ValueError(f"Unsupported patch op: {op!r}")
    spec_save(spec, path)
    return spec


def spec_note(text, src=None, tag=None, path=None):
    """Append a concise observation note (Read -> Note -> Release discipline)."""
    spec = _ensure_spec(path)
    entry = {"text": str(text).strip()}
    if src:
        entry["src"] = src
    if tag:
        entry["tag"] = tag
    spec.setdefault("notes", []).append(entry)
    spec_save(spec, path)
    return entry


# ==============================================================================
# 2. EXACT COORDINATE-COMPRESSED RECTANGLE BOOLEAN -> RINGS (NO SHAPELY)
# ==============================================================================

def _norm_rect(r):
    x0, y0, x1, y1 = (float(r[0]), float(r[1]), float(r[2]), float(r[3]))
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _unique_sorted(vals, tol=1e-7):
    if not vals:
        return []
    s = sorted(vals)
    out = [s[0]]
    for v in s[1:]:
        if v - out[-1] > tol:
            out.append(v)
    return out


def _snap_idx(val, arr, tol=1e-6):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(arr[mid] - val) <= tol:
            return mid
        if arr[mid] < val:
            lo = mid + 1
        else:
            hi = mid - 1
    raise ValueError(f"Value {val} not found in coordinate grid")


def _ring_area(pts):
    if len(pts) < 3:
        return 0.0
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def _ensure_winding(pts, ccw=True):
    area = _ring_area(pts)
    if (ccw and area < 0) or (not ccw and area > 0):
        return list(reversed(pts))
    return list(pts)


def _prune_collinear(pts, tol=1e-8):
    if len(pts) < 3:
        return pts
    cur = list(pts)
    changed = True
    while changed and len(cur) >= 3:
        changed = False
        nxt = []
        n = len(cur)
        for i in range(n):
            ax, ay = cur[(i - 1) % n]
            bx, by = cur[i]
            cx, cy = cur[(i + 1) % n]
            if math.hypot(bx - ax, by - ay) <= tol:
                changed = True
                continue
            cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
            dot = (bx - ax) * (cx - bx) + (by - ay) * (cy - by)
            if abs(cross) <= tol * (math.hypot(bx - ax, by - ay) + math.hypot(cx - bx, cy - by)) and dot >= -tol:
                changed = True
                continue
            nxt.append((bx, by))
        cur = nxt
    return cur


def _trace_grid_rings(grid, xs, ys):
    """Extract non-intersecting CCW outer rings and CW hole rings from boolean cell grid[i][j].
    Cell (i, j) spans [xs[i], xs[i+1]] x [ys[j], ys[j+1]]."""
    nx = len(xs) - 1
    ny = len(ys) - 1
    if nx <= 0 or ny <= 0:
        return {"outers": [], "holes": []}

    # Directed edges with interior cell on the LEFT: dir in 0=E(1,0), 1=N(0,1), 2=W(-1,0), 3=S(0,-1)
    adj = {}

    def add_edge(u, v, d):
        adj.setdefault(u, []).append((v, d))

    for i in range(nx):
        col = grid[i]
        for j in range(ny):
            if not col[j]:
                continue
            if j == 0 or not grid[i][j - 1]:
                add_edge((i, j), (i + 1, j), 0)
            if i == nx - 1 or not grid[i + 1][j]:
                add_edge((i + 1, j), (i + 1, j + 1), 1)
            if j == ny - 1 or not grid[i][j + 1]:
                add_edge((i + 1, j + 1), (i, j + 1), 2)
            if i == 0 or not grid[i - 1][j]:
                add_edge((i, j + 1), (i, j), 3)

    outers, holes = [], []
    # Deterministic start order
    for start in sorted(list(adj.keys())):
        while adj.get(start):
            v, d = adj[start].pop(0)
            if not adj[start]:
                adj.pop(start, None)
            loop_idx = [start]
            cur = v
            d_in = d
            while cur != start:
                loop_idx.append(cur)
                choices = adj.get(cur)
                if not choices:
                    break
                # Turn left first ((d_in+1)%4) to keep connected solid quadrant closed around pinch vertices
                pref = [(d_in + 1) % 4, d_in, (d_in - 1) % 4, (d_in + 2) % 4]
                pick_i = 0
                for pd in pref:
                    found = next((k for k, (_, cd) in enumerate(choices) if cd == pd), None)
                    if found is not None:
                        pick_i = found
                        break
                nxt_v, nxt_d = choices.pop(pick_i)
                if not choices:
                    adj.pop(cur, None)
                cur = nxt_v
                d_in = nxt_d
            pts = _prune_collinear([(round(xs[ix], 6), round(ys[iy], 6)) for ix, iy in loop_idx])
            area = _ring_area(pts)
            if len(pts) >= 3 and abs(area) > 1e-8:
                if area > 0:
                    outers.append(pts)
                else:
                    holes.append(pts)
    return {"outers": outers, "holes": holes}


def _apply_rect_grid_ops(ops):
    """Evaluate sequence of ('add'|'sub', rect) with exact sequential constructive boolean on compressed grid."""
    all_x, all_y = [], []
    clean_ops = []
    for mode, rect in ops:
        x0, y0, x1, y1 = _norm_rect(rect)
        if x1 - x0 <= 1e-7 or y1 - y0 <= 1e-7:
            continue
        clean_ops.append((mode, (x0, y0, x1, y1)))
        all_x.extend((x0, x1))
        all_y.extend((y0, y1))
    if not clean_ops:
        return {"outers": [], "holes": []}
    xs = _unique_sorted(all_x)
    ys = _unique_sorted(all_y)
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx <= 0 or ny <= 0:
        return {"outers": [], "holes": []}
    grid = [[False] * ny for _ in range(nx)]
    for mode, (x0, y0, x1, y1) in clean_ops:
        ix0, ix1 = _snap_idx(x0, xs), _snap_idx(x1, xs)
        iy0, iy1 = _snap_idx(y0, ys), _snap_idx(y1, ys)
        val = (mode == "add")
        for ix in range(ix0, ix1):
            row = grid[ix]
            for iy in range(iy0, iy1):
                row[iy] = val
    return _trace_grid_rings(grid, xs, ys)


def rect_union_to_rings(union, sub=()):
    """Compute exact 2D boundary rings from rectangular `(union) - (sub)` without shapely.
    Returns `{'outers': [CCW rings], 'holes': [CW rings]}` with collinear vertices merged.
    """
    ops = [("add", r) for r in (union or ())] + [("sub", r) for r in (sub or ())]
    return _apply_rect_grid_ops(ops)


# ==============================================================================
# 3. BASE+ADD+SUB OUTLINE RESOLUTION & EDGE SELECTORS
# ==============================================================================

def _point_in_ring(px, py, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        if (y0 > py) != (y1 > py):
            x_int = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
            if px < x_int:
                inside = not inside
    return inside


def _outline_chain(level_id, outline_map):
    chain = []
    seen = set()
    cur = level_id
    while cur:
        if cur in seen:
            raise ValueError(f"E_BASE_CYCLE: cycle at outline {cur!r}")
        if cur not in outline_map:
            raise ValueError(f"E_MISSING_BASE: outline level {cur!r} not found")
        seen.add(cur)
        chain.append(cur)
        cur = outline_map[cur].get("base")
    chain.reverse()
    return chain


def resolve_outline(level_id, spec=None):
    """Resolve `outline[level_id]` including recursive `base+add+sub` chains or explicit `poly`/`holes`.
    Returns `{'outers': [...], 'holes': [...], 'area': float, 'bbox': [x0,y0,x1,y1], 'chain': [...], 'src', 'conf'}`.
    """
    spec = spec or spec_load()
    outline_map = spec.get("outline", {})
    chain = _outline_chain(level_id, outline_map)
    root_entry = outline_map[chain[0]]

    if "poly" in root_entry and root_entry["poly"]:
        if len(chain) == 1 and not root_entry.get("add") and not root_entry.get("union") and not root_entry.get("sub"):
            outer = _prune_collinear(_ensure_winding([(float(p[0]), float(p[1])) for p in root_entry["poly"]], ccw=True))
            holes = [_prune_collinear(_ensure_winding([(float(p[0]), float(p[1])) for p in h], ccw=False))
                     for h in root_entry.get("holes", [])]
            rings = {"outers": [outer] if outer else [], "holes": [h for h in holes if h]}
        else:
            # Explicit polygon inherited or modified cleanly only if no oblique truncation conflicts
            outer = _prune_collinear(_ensure_winding([(float(p[0]), float(p[1])) for p in root_entry["poly"]], ccw=True))
            holes = [_prune_collinear(_ensure_winding([(float(p[0]), float(p[1])) for p in h], ccw=False))
                     for h in root_entry.get("holes", [])]
            ops = []
            for lid in chain[1:]:
                ent = outline_map[lid]
                for r in ent.get("union", ()) or ():
                    ops.append(("add", r))
                for r in ent.get("add", ()) or ():
                    ops.append(("add", r))
                for r in ent.get("sub", ()) or ():
                    ops.append(("sub", r))
            if not ops:
                rings = {"outers": [outer] if outer else [], "holes": [h for h in holes if h]}
            else:
                raise ValueError(f"Level {level_id!r}: rect add/sub on top of non-rect 'poly' base {chain[0]!r} is unsupported; specify rect union or level 'poly'.")
    else:
        ops = []
        for lid in chain:
            ent = outline_map[lid]
            for r in ent.get("union", ()) or ():
                ops.append(("add", r))
            for r in ent.get("add", ()) or ():
                ops.append(("add", r))
            for r in ent.get("sub", ()) or ():
                ops.append(("sub", r))
        rings = _apply_rect_grid_ops(ops)

    area = sum(_ring_area(r) for r in rings["outers"]) + sum(_ring_area(h) for h in rings["holes"])
    all_pts = [p for r in rings["outers"] for p in r]
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        bbox = [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)]
    else:
        bbox = [0.0, 0.0, 0.0, 0.0]

    leaf = outline_map[level_id]
    return {
        "level": level_id,
        "outers": rings["outers"],
        "holes": rings["holes"],
        "area": round(area, 6),
        "bbox": bbox,
        "chain": chain,
        "src": leaf.get("src", root_entry.get("src", "")),
        "conf": leaf.get("conf", root_entry.get("conf", "M")),
    }


def _classify_edge_side(dx, dy, length):
    nx_out = dy / length
    ny_out = -dx / length
    if abs(dx) <= EDGE_OBLIQUE_DIR_TOL * length:
        return "E" if nx_out > 0 else "W"
    if abs(dy) <= EDGE_OBLIQUE_DIR_TOL * length:
        return "N" if ny_out > 0 else "S"
    return "OBLIQUE"


def _rotate_ring_to_nw(ring_ccw):
    """Rotate vertex list so vertex 0 is NW-most (max y, tie-break min x) and walk CW for stable E1..En IDs."""
    ring_cw = list(reversed(ring_ccw))
    nw_idx = max(range(len(ring_cw)), key=lambda i: (round(ring_cw[i][1], 5), -round(ring_cw[i][0], 5)))
    return ring_cw[nw_idx:] + ring_cw[:nw_idx]


def outline_edges(level_id, spec=None, include_holes=False):
    """Return ordered edge dicts `{id, side, p0, p1, length, span, outward, inward, is_hole}`.
    `id` (`E1..En` or `H1_1..`) orders clockwise from the NW vertex of each outer ring.
    For cardinal edges N/S: `span = [xmin, xmax]`; E/W: `span = [ymin, ymax]`; OBLIQUE: `[0, length]`.
    """
    res = resolve_outline(level_id, spec)
    edges = []
    eid = 1

    # Number edges CW from NW for human-readable E1..En, while recording exact outward/inward normals
    for ring_idx, ring_ccw in enumerate(res["outers"]):
        cw = _rotate_ring_to_nw(ring_ccw)
        n = len(cw)
        for i in range(n):
            p0 = cw[i]
            p1 = cw[(i + 1) % n]
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            length = math.hypot(dx, dy)
            if length < 1e-8:
                continue
            # Walking CW: outward normal is LEFT of p0->p1 = (-dy/L, dx/L); inward is (dy/L, -dx/L)
            outward = (-dy / length, dx / length)
            inward = (dy / length, -dx / length)
            if abs(dx) <= EDGE_OBLIQUE_DIR_TOL * length:
                side = "E" if outward[0] > 0 else "W"
                span = [round(min(p0[1], p1[1]), 6), round(max(p0[1], p1[1]), 6)]
                axis = "Y"
                coord = round(0.5 * (p0[0] + p1[0]), 6)
            elif abs(dy) <= EDGE_OBLIQUE_DIR_TOL * length:
                side = "N" if outward[1] > 0 else "S"
                span = [round(min(p0[0], p1[0]), 6), round(max(p0[0], p1[0]), 6)]
                axis = "X"
                coord = round(0.5 * (p0[1] + p1[1]), 6)
            else:
                side = "OBLIQUE"
                span = [0.0, round(length, 6)]
                axis = "L"
                coord = None
            edges.append({
                "id": f"E{eid}",
                "ring": ring_idx,
                "is_hole": False,
                "side": side,
                "axis": axis,
                "coord": coord,
                "span": span,
                "p0": p0,
                "p1": p1,
                "length": round(length, 6),
                "outward": (round(outward[0], 6), round(outward[1], 6)),
                "inward": (round(inward[0], 6), round(inward[1], 6)),
            })
            eid += 1

    if include_holes:
        for h_idx, hole_cw in enumerate(res["holes"]):
            # For CW hole, solid is OUTSIDE the hole (to the LEFT of CW edges? Wait: CW loop has hole on RIGHT!
            # So solid is on LEFT of CW edge -> normal pointing into hole (outward from solid) is RIGHT = (dy/L, -dx/L))
            n = len(hole_cw)
            for i in range(n):
                p0 = hole_cw[i]
                p1 = hole_cw[(i + 1) % n]
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                length = math.hypot(dx, dy)
                if length < 1e-8:
                    continue
                outward = (dy / length, -dx / length)
                inward = (-dy / length, dx / length)
                side = _classify_edge_side(dx, dy, length)  # matches outward normal convention
                if side in ("E", "W"):
                    span = [round(min(p0[1], p1[1]), 6), round(max(p0[1], p1[1]), 6)]
                    axis, coord = "Y", round(0.5 * (p0[0] + p1[0]), 6)
                elif side in ("N", "S"):
                    span = [round(min(p0[0], p1[0]), 6), round(max(p0[0], p1[0]), 6)]
                    axis, coord = "X", round(0.5 * (p0[1] + p1[1]), 6)
                else:
                    span, axis, coord = [0.0, round(length, 6)], "L", None
                edges.append({
                    "id": f"H{h_idx + 1}_{i + 1}",
                    "ring": h_idx,
                    "is_hole": True,
                    "side": side,
                    "axis": axis,
                    "coord": coord,
                    "span": span,
                    "p0": p0,
                    "p1": p1,
                    "length": round(length, 6),
                    "outward": (round(outward[0], 6), round(outward[1], 6)),
                    "inward": (round(inward[0], 6), round(inward[1], 6)),
                })
    return edges


def match_rule_to_edges(rule, edges, tol=1e-3):
    """Return list of `(edge_dict, local_sub_span_world_or_len)` matched by an edge_rule."""
    hits = []
    rid = rule.get("id")
    if rid:
        for e in edges:
            if e["id"] == rid:
                s0, s1 = rule.get("span") or [0.0, e["length"]]
                a0, a1 = max(0.0, float(s0)), min(e["length"], float(s1))
                if a1 - a0 > tol:
                    hits.append((e, (a0, a1)))
        return hits

    side = rule.get("side")
    rspan = rule.get("span")
    coord = rule.get("coord")
    for e in edges:
        if e["side"] != side:
            continue
        if coord is not None and e["coord"] is not None and abs(e["coord"] - float(coord)) > tol:
            continue
        es0, es1 = e["span"]
        if rspan is None:
            hits.append((e, (es0, es1)))
        else:
            a0, a1 = max(es0, float(rspan[0])), min(es1, float(rspan[1]))
            if a1 - a0 > tol:
                hits.append((e, (a0, a1)))
    return hits


def spec_show(level_id, spec=None):
    """Compact numbered edge table + ASCII bounding diagram for `level_id` (<= 25 lines)."""
    spec = spec or spec_load()
    res = resolve_outline(level_id, spec)
    edges = outline_edges(level_id, spec)
    lines = [f"{level_id} area={res['area']:.2f}m2 bbox={res['bbox']} chain={'->'.join(res['chain'])}"]
    for e in edges:
        lines.append(
            f"  {e['id']:<3} {e['side']:<7} span=[{e['span'][0]:.2f},{e['span'][1]:.2f}] "
            f"len={e['length']:.2f}m ({e['p0'][0]:.2f},{e['p0'][1]:.2f})->({e['p1'][0]:.2f},{e['p1'][1]:.2f})"
        )
    return "\n".join(lines[:30])


# ==============================================================================
# 4. VALIDATION, COMPACT DIGEST, PHASE CARD & SITE YAW
# ==============================================================================

def spec_validate(spec=None):
    """Validate Building Spec schema, monotonic levels, base chains, min edge length, and edge rules."""
    spec = spec or spec_load()
    errors, warnings = [], []

    fr = spec.get("frame", {})
    if not fr.get("scale_m_per_px"):
        warnings.append("W_NO_SCALE: frame.scale_m_per_px is unset")

    levels = spec.get("levels", [])
    seen_ids = set()
    last_z_by_zone = {}
    level_by_id = {}
    for idx, lv in enumerate(levels):
        lid = lv.get("id")
        if not lid:
            errors.append(f"E_LEVEL_NO_ID: level[{idx}] missing id")
            continue
        if lid in seen_ids:
            errors.append(f"E_DUP_LEVEL: duplicate level id {lid!r}")
        seen_ids.add(lid)
        level_by_id[lid] = lv
        z = lv.get("z")
        slab = lv.get("slab", 0.3)
        if z is None:
            errors.append(f"E_LEVEL_NO_Z: {lid} missing z")
        else:
            zone_key = tuple(lv["zone"]) if lv.get("zone") else "__main__"
            if zone_key in last_z_by_zone and float(z) <= last_z_by_zone[zone_key]:
                errors.append(f"E_LEVEL_Z_NONMONO: {lid}.z={z} <= previous {last_z_by_zone[zone_key]} in zone {zone_key}")
            last_z_by_zone[zone_key] = float(z)
        if slab <= 0:
            errors.append(f"E_BAD_SLAB: {lid}.slab={slab} <= 0")
        elif slab < 0.15 or slab > 0.65:
            warnings.append(f"W_SLAB_RANGE: {lid}.slab={slab} outside typical 0.15..0.65m")

    outlines = spec.get("outline", {})
    edges_cache = {}
    for lid in outlines:
        try:
            res = resolve_outline(lid, spec)
            if not res["outers"] or res["area"] <= 1e-4:
                errors.append(f"E_EMPTY_OUTLINE: outline {lid!r} has empty geometry")
                continue
            ed = outline_edges(lid, spec)
            edges_cache[lid] = ed
            for e in ed:
                if e["length"] < 0.15 - 1e-6:
                    errors.append(f"E_SHORT_EDGE: {lid}.{e['id']} length={e['length']:.3f}m < 0.15m")
        except Exception as exc:
            msg = str(exc)
            code = msg.split(":")[0] if msg.startswith("E_") else "E_OUTLINE_ERR"
            errors.append(f"{code}: {lid}: {msg}")

    # Floor heights for Z bounds check
    zone_levels = {}
    for lv in levels:
        zk = tuple(lv["zone"]) if lv.get("zone") else "__main__"
        zone_levels.setdefault(zk, []).append(lv)
    floor_h_map = {}
    for zk, zls in zone_levels.items():
        zls_s = sorted(zls, key=lambda x: x["z"])
        for i, lv in enumerate(zls_s):
            floor_h_map[lv["id"]] = (zls_s[i + 1]["z"] - lv["z"]) if i + 1 < len(zls_s) else 4.0

    for idx, rule in enumerate(spec.get("edge_rules", [])):
        rlv = rule.get("level")
        if rlv not in level_by_id:
            errors.append(f"E_RULE_UNKNOWN_LEVEL: edge_rules[{idx}].level={rlv!r} not in levels")
            continue
        kind = rule.get("kind", "SOLID")
        if kind not in VALID_EDGE_KINDS:
            errors.append(f"E_UNKNOWN_KIND: edge_rules[{idx}].kind={kind!r}")
        skin = rule.get("skin", "")
        if skin and skin not in VALID_SKIN_KINDS:
            errors.append(f"E_UNKNOWN_SKIN: edge_rules[{idx}].skin={skin!r}")
        if not rule.get("id"):
            if rule.get("side") not in VALID_SIDES:
                errors.append(f"E_UNKNOWN_SIDE: edge_rules[{idx}].side={rule.get('side')!r}")
        rspan = rule.get("span")
        if rspan is not None:
            if len(rspan) != 2 or float(rspan[0]) >= float(rspan[1]):
                errors.append(f"E_BAD_SPAN: edge_rules[{idx}].span={rspan!r}")
                continue
        ed = edges_cache.get(rlv)
        if ed is None:
            continue
        hits = match_rule_to_edges(rule, ed)
        if not hits:
            errors.append(f"E_SPAN_OOB: edge_rules[{idx}] matched no edge on {rlv} ({rule.get('side') or rule.get('id')} {rspan})")
            continue
        span_len = sum(b - a for _, (a, b) in hits)
        if rspan is not None and span_len < (float(rspan[1]) - float(rspan[0])) - 0.05:
            errors.append(
                f"E_SPAN_OOB: edge_rules[{idx}] span={rspan} exceeds matched edge length "
                f"(covered {span_len:.2f}m vs {float(rspan[1]) - float(rspan[0]):.2f}m)"
            )
        fh = floor_h_map.get(rlv, 4.0)
        for oidx, op in enumerate(rule.get("openings", []) or []):
            ou = op.get("u")
            oz = op.get("z")
            if not ou or len(ou) != 2 or float(ou[0]) < -1e-4 or float(ou[1]) > span_len + 1e-4 or float(ou[0]) >= float(ou[1]):
                errors.append(f"E_OPENING_OOB: edge_rules[{idx}].openings[{oidx}].u={ou} outside [0, {span_len:.2f}]")
            if oz is not None:
                if len(oz) != 2 or float(oz[0]) < -1e-4 or float(oz[1]) > fh + 1e-4 or float(oz[0]) >= float(oz[1]):
                    errors.append(f"E_OPENING_Z_OOB: edge_rules[{idx}].openings[{oidx}].z={oz} outside [0, {fh:.2f}]")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _format_diff_hint(ent):
    parts = []
    if ent.get("base"):
        parts.append(f"base={ent['base']}")
    a = len(ent.get("add", []) or [])
    u = len(ent.get("union", []) or [])
    s = len(ent.get("sub", []) or [])
    if u:
        parts.append(f"U{u}")
    if a:
        parts.append(f"+{a}")
    if s:
        parts.append(f"-{s}")
    if ent.get("poly"):
        parts.append(f"poly({len(ent['poly'])})")
    return " ".join(parts) or "-"


def spec_digest(max_lines=40, spec=None):
    """Return compact <=40-line status digest of the Building Spec for zero-drift context recovery."""
    spec = spec or spec_load()
    fr = spec.get("frame", {})
    prog = spec.get("progress", {})
    lines = [
        f"[SPEC v{spec.get('v',1)}] phase={prog.get('phase','P0')} | scale={fr.get('scale_m_per_px')}m/px | yaw={fr.get('yaw_deg',0)}deg | origin={fr.get('origin','')}",
    ]
    levels = spec.get("levels", [])
    outlines = spec.get("outline", {})
    if levels:
        lines.append("Levels:")
        for lv in levels:
            lid = lv["id"]
            zinfo = f"z={lv['z']:.2f}(slab={lv.get('slab',0.3):.2f},cut={lv.get('cut',1.5):.2f})"
            if lv.get("zone"):
                zinfo += f" zone={lv['zone']}"
            if lid in outlines:
                try:
                    r = resolve_outline(lid, spec)
                    ed = outline_edges(lid, spec)
                    oinfo = f"A={r['area']:.1f}m2 box={r['bbox']} E={len(ed)} [{_format_diff_hint(outlines[lid])}] ({r['conf']}/{r['src']})"
                except Exception as exc:
                    oinfo = f"ERR:{exc}"
            else:
                oinfo = "no-outline"
            lines.append(f"  {lid}: {zinfo} | {oinfo}")
    else:
        lines.append("Levels: (none)")

    rules = spec.get("edge_rules", [])
    by_kind = {}
    for r in rules:
        k = r.get("kind", "SOLID")
        by_kind[k] = by_kind.get(k, 0) + 1
    lines.append(f"Rules({len(rules)}): {by_kind} | Elements({len(spec.get('elements',[]))})")

    gates = prog.get("gates", {})
    lv = prog.get("last_verify")
    vstr = f" | verify={lv}" if lv else ""
    lines.append(f"Gates: {gates}{vstr} | Deviations({len(spec.get('deviations',[]))})")

    notes = spec.get("notes", [])
    for n in notes[-2:]:
        lines.append(f"Note[{n.get('src','-')}]: {n.get('text','')[:90]}")

    if len(lines) > max_lines:
        keep = lines[: max_lines - 1]
        keep.append(f"... (+{len(lines) - max_lines + 1} truncated)")
        lines = keep
    return "\n".join(lines)


_PHASE_CARDS = {
    "P0": (
        "P0 输入盘点",
        "分类平面/立剖面/照片(去重) -> spec_init -> plan_prep.py scan",
        "G1: align_score>=0.9, scale & levels set",
    ),
    "P1": (
        "P1 读图与尺度标定",
        "plan_prep.py build --refine -> section_levels.py -> scale-from-section -> 米制网格",
        "G1: align_score>=0.9 & 标高递增 & slab 0.2..0.5m",
    ),
    "P2": (
        "P2 规格锚定与边支持预检",
        "写 outline(矩形并+增量)+edge_rules -> spec_validate() -> plan_prep.py check-outline",
        "G2: spec_validate 0 err & 参考层边支持度>=0.8",
    ),
    "P3": (
        "P3 L1 体块与楼层剖切验收",
        "build_all_levels() -> verify_levels() -> 1张 RANDOM 等轴测",
        "G3: IoU>=0.92 & max_edge_err<=150mm & rule_violations==0 & audit passed",
    ),
    "P4": (
        "P4 L2/L3 细部构建与台账对账",
        "detail_kit(HEB/slat/louver/railing/window) + ledger_set/check + detail_audit + render_closeup(<=3)",
        "G4: ledger_check.passed & box_standins==[]",
    ),
    "P5": (
        "P5 终验与交付",
        "重跑 verify_levels -> finish_materials() -> 切 MATERIAL -> apply_site_yaw() -> triview",
        "G5: G3通过 + 材质已赋(MATERIAL) + Site_Yaw就位",
    ),
}


def phase_next(spec=None):
    """Return a <=20-line actionable card for the current phase and gate criteria."""
    spec = spec or spec_load()
    prog = spec.get("progress", {})
    phase = prog.get("phase", "P0")
    title, cmds, gate = _PHASE_CARDS.get(phase, _PHASE_CARDS["P0"])
    iters = prog.get("iters", {}).get(phase, 0)
    rem = max(0, 2 - int(iters))
    lines = [
        f"== {title} ==",
        f"Next : {cmds}",
        f"Gate : {gate}",
        f"Iters: {iters}/2 used (remaining={rem}; after 2 record in deviations)",
    ]
    devs = spec.get("deviations", [])
    if devs:
        lines.append(f"Deviations({len(devs)}): {devs[-1]}")
    return "\n".join(lines[:20])


def apply_site_yaw(deg=None, root_name="CAD_Model_Root", reset=False):
    """Parent all top-level model objects under `root_name` to Empty `Site_Yaw` and rotate +Z by `deg`.
    Reversible at any time via `apply_site_yaw(reset=True)`. Must be called only at P5 delivery."""
    if bpy is None:
        raise RuntimeError("apply_site_yaw requires Blender (bpy)")
    if deg is None and not reset:
        deg = float(spec_load().get("frame", {}).get("yaw_deg", 0.0))
    angle_deg = 0.0 if reset else float(deg or 0.0)

    scene = bpy.context.scene
    root_col = bpy.data.collections.get(root_name)
    if root_col is None:
        raise ValueError(f"Collection {root_name!r} not found")

    def _collect_col_objs(col):
        res = list(col.objects)
        for ch in col.children:
            res.extend(_collect_col_objs(ch))
        return res

    model_objs = [o for o in _collect_col_objs(root_col) if o.name != "Site_Yaw"]
    model_set = set(model_objs)

    yaw_obj = bpy.data.objects.get("Site_Yaw")
    if yaw_obj is None:
        yaw_obj = bpy.data.objects.new("Site_Yaw", None)
        yaw_obj.empty_display_type = 'ARROWS'
        yaw_obj.empty_display_size = 2.0
        scene.collection.objects.link(yaw_obj)

    # Zero before parenting so object world matrices match local building frame cleanly
    prev_z = yaw_obj.rotation_euler.z
    yaw_obj.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    parented = 0
    for o in model_objs:
        if o.parent is None or (o.parent is not yaw_obj and o.parent not in model_set):
            mw = o.matrix_world.copy()
            o.parent = yaw_obj
            o.matrix_parent_inverse = yaw_obj.matrix_world.inverted()
            o.matrix_world = mw
            parented += 1

    yaw_obj.rotation_euler = (0.0, 0.0, math.radians(angle_deg))
    bpy.context.view_layer.update()
    _ = prev_z
    return {
        "site_yaw": yaw_obj.name,
        "yaw_deg": round(angle_deg, 4),
        "children_direct": sum(1 for o in bpy.data.objects if o.parent is yaw_obj),
        "newly_parented": parented,
    }
