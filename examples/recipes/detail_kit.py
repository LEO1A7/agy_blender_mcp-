"""[RECIPE_DETAIL_KIT] 通用细部构件库 · 型钢截面(H/I/槽/角/管) · 百叶/板条/栏杆/窗框阵列 · 细部清单台账与细部体检
- 适用 (When): 建筑/工业/机械外立面与结构建模需保真细部——H型钢(HEB220等)真实截面、竖向板条、倾斜百叶、栏杆立柱、窗框分格、管道法兰；或需对账“清单 vs 已建构件”防漏建
- 用法 (How) : `import sys,os; sys.path.insert(0, os.path.expanduser('~/.gemini/config/plugins/abmcp/examples/recipes')); import detail_kit as DK`；向同一个 `bm` 累积多个构件后 `DK.finalize_object(name, bm, col, materials=[...])`
- 产出 (Out) : 法线朝外的闭合流形 BMesh 构件(单一截面棱柱而非多盒叠加)、按面分配的多材质、`ledger_check()` 漏建/弱细节报告、`detail_audit()` 盒子占位件与重复阵列统计
"""

import fnmatch
import json
import math
import re

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

Z_UP = Vector((0.0, 0.0, 1.0))


# ==============================================================================
# 1. STEEL / SECTION PROFILE LIBRARY (2D outlines in metres, centred on bbox)
# ==============================================================================

# name -> ("H"|"C", h, b, tw, tf, r) in millimetres.  H = I/H beams, C = channels (UPN).
STEEL_SECTIONS = {
    # Wide-flange (HE-A/B) — h = overall depth, b = flange width, tw = web, tf = flange, r = root fillet
    "HEA160": ("H", 152, 160, 6.0, 9.0, 15), "HEA200": ("H", 190, 200, 6.5, 10.0, 18),
    "HEA240": ("H", 230, 240, 7.5, 12.0, 21), "HEA300": ("H", 290, 300, 8.5, 14.0, 27),
    "HEB100": ("H", 100, 100, 6.0, 10.0, 12), "HEB120": ("H", 120, 120, 6.5, 11.0, 12),
    "HEB140": ("H", 140, 140, 7.0, 12.0, 12), "HEB160": ("H", 160, 160, 8.0, 13.0, 15),
    "HEB180": ("H", 180, 180, 8.5, 14.0, 15), "HEB200": ("H", 200, 200, 9.0, 15.0, 18),
    "HEB220": ("H", 220, 220, 9.5, 16.0, 18), "HEB240": ("H", 240, 240, 10.0, 17.0, 21),
    "HEB260": ("H", 260, 260, 10.0, 17.5, 24), "HEB300": ("H", 300, 300, 11.0, 19.0, 27),
    # I-beams (IPE)
    "IPE120": ("H", 120, 64, 4.4, 6.3, 7), "IPE160": ("H", 160, 82, 5.0, 7.4, 9),
    "IPE200": ("H", 200, 100, 5.6, 8.5, 12), "IPE220": ("H", 220, 110, 5.9, 9.2, 12),
    "IPE240": ("H", 240, 120, 6.2, 9.8, 15), "IPE270": ("H", 270, 135, 6.6, 10.2, 15),
    "IPE300": ("H", 300, 150, 7.1, 10.7, 15), "IPE360": ("H", 360, 170, 8.0, 12.7, 18),
    # Channels (UPN)
    "UPN80": ("C", 80, 45, 6.0, 8.0, 8), "UPN100": ("C", 100, 50, 6.0, 8.5, 8.5),
    "UPN120": ("C", 120, 55, 7.0, 9.0, 9), "UPN160": ("C", 160, 65, 7.5, 10.5, 10.5),
    "UPN200": ("C", 200, 75, 8.5, 11.5, 11.5), "UPN240": ("C", 240, 85, 9.5, 13.0, 13),
}

_RE_SHS = re.compile(r"^SHS(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_RHS = re.compile(r"^RHS(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_CHS = re.compile(r"^CHS(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_L_EQ = re.compile(r"^L(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_L_NE = re.compile(r"^L(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_FLAT = re.compile(r"^FLAT(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)
_RE_TEE = re.compile(r"^T(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.I)


def profile_rect(w, h):
    """Solid rectangle w (u) x h (v)."""
    return {"outer": [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], "inner": None}


def profile_diamond(w, t):
    """Rhombic (diamond) batten section, w across the long diagonal (u), t across the short one (v)."""
    return {"outer": [(-w / 2, 0.0), (0.0, -t / 2), (w / 2, 0.0), (0.0, t / 2)], "inner": None}


def profile_rect_tube(w, h, t):
    """Hollow rectangular tube (SHS/RHS)."""
    o = profile_rect(w, h)["outer"]
    i = profile_rect(w - 2 * t, h - 2 * t)["outer"]
    return {"outer": o, "inner": i}


def profile_round(r, segs=24):
    return {"outer": [(r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs)) for k in range(segs)],
            "inner": None}


def profile_round_tube(r, t, segs=24):
    ri = max(r - t, r * 0.05)
    o = [(r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs)) for k in range(segs)]
    i = [(ri * math.cos(2 * math.pi * k / segs), ri * math.sin(2 * math.pi * k / segs)) for k in range(segs)]
    return {"outer": o, "inner": i}


def _fillet_corner(prev, corner, nxt, r, n):
    """Quarter-circle fillet replacing a 90-degree polygon corner (axis-aligned outlines only)."""
    p, c, q = Vector(prev), Vector(corner), Vector(nxt)
    d1 = (c - p).normalized()
    d2 = (q - c).normalized()
    t1 = c - d1 * r
    centre = t1 + d2 * r
    a_hat, b_hat = -d2, d1
    pts = []
    for k in range(n + 1):
        phi = (math.pi / 2) * (k / n)
        pts.append(tuple(centre + (a_hat * math.cos(phi) + b_hat * math.sin(phi)) * r))
    return pts


def profile_H(h, b, tw, tf, r=0.0, fillet_segs=0):
    """I/H section (metres). Flanges are perpendicular to v, web lies in the u=0 plane. CCW outline."""
    B, H, w = b / 2, h / 2, tw / 2
    pts = [(-B, -H), (B, -H), (B, -H + tf), (w, -H + tf), (w, H - tf), (B, H - tf),
           (B, H), (-B, H), (-B, H - tf), (-w, H - tf), (-w, -H + tf), (-B, -H + tf)]
    if fillet_segs and r > 0:
        rr = min(r, (B - w) * 0.98, (H - tf) * 0.98)
        inner_idx = {3, 4, 9, 10}
        out = []
        n = len(pts)
        for i, pt in enumerate(pts):
            if i in inner_idx:
                out.extend(_fillet_corner(pts[i - 1], pt, pts[(i + 1) % n], rr, fillet_segs))
            else:
                out.append(pt)
        pts = out
    return {"outer": pts, "inner": None}


def profile_channel(h, b, tw, tf):
    """C/U channel: web on the -u side, flanges toward +u."""
    B, H = b / 2, h / 2
    pts = [(-B, -H), (B, -H), (B, -H + tf), (-B + tw, -H + tf), (-B + tw, H - tf), (B, H - tf), (B, H), (-B, H)]
    return {"outer": pts, "inner": None}


def profile_angle(a, b, t):
    """L angle (legs a along u, b along v, thickness t), centred on its bbox."""
    pts = [(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)]
    return {"outer": [(x - a / 2, y - b / 2) for x, y in pts], "inner": None}


def profile_tee(h, b, tw, tf):
    B, H, w = b / 2, h / 2, tw / 2
    return {"outer": [(-w, -H), (w, -H), (w, H - tf), (B, H - tf), (B, H), (-B, H), (-B, H - tf), (-w, H - tf)],
            "inner": None}


def steel_profile(name, fillet_segs=0):
    """Resolve a designation such as 'HEB220', 'IPE200', 'UPN160', 'SHS80x5', 'RHS100x50x4', 'CHS114.3x4',
    'L80x8', 'L100x65x8', 'FLAT100x10' into a metre profile dict."""
    key = name.replace(" ", "").upper()
    mm = 0.001
    if key in STEEL_SECTIONS:
        kind, h, b, tw, tf, r = STEEL_SECTIONS[key]
        if kind == "H":
            return profile_H(h * mm, b * mm, tw * mm, tf * mm, r * mm, fillet_segs)
        return profile_channel(h * mm, b * mm, tw * mm, tf * mm)
    m = _RE_SHS.match(key)
    if m:
        a, t = float(m.group(1)), float(m.group(2))
        return profile_rect_tube(a * mm, a * mm, t * mm)
    m = _RE_RHS.match(key)
    if m:
        h, b, t = (float(x) for x in m.groups())
        return profile_rect_tube(b * mm, h * mm, t * mm)
    m = _RE_CHS.match(key)
    if m:
        d, t = float(m.group(1)), float(m.group(2))
        return profile_round_tube(d * mm / 2, t * mm)
    m = _RE_L_NE.match(key)
    if m:
        a, b, t = (float(x) for x in m.groups())
        return profile_angle(a * mm, b * mm, t * mm)
    m = _RE_L_EQ.match(key)
    if m:
        a, t = float(m.group(1)), float(m.group(2))
        return profile_angle(a * mm, a * mm, t * mm)
    m = _RE_FLAT.match(key)
    if m:
        return profile_rect(float(m.group(1)) * mm, float(m.group(2)) * mm)
    m = _RE_TEE.match(key)
    if m:
        h, b, tw, tf = (float(x) for x in m.groups())
        return profile_tee(h * mm, b * mm, tw * mm, tf * mm)
    raise ValueError(f"Unknown steel section '{name}'. Known tabled: {sorted(STEEL_SECTIONS)}; "
                     f"parametric: SHSaxt, RHShxbxt, CHSdxt, Laxt, Laxbxt, FLATbxt, Thxbxtwxtf")


# ==============================================================================
# 2. CORE LOFT / PRISM PRIMITIVES (all accumulate into a caller-owned BMesh)
# ==============================================================================

def _frame(axis_n, up, roll_deg=0.0):
    """Right-handed section frame (u, v, axis): u = v x axis, v = projected `up`."""
    up = Vector(up)
    v = up - axis_n * up.dot(axis_n)
    if v.length < 1e-6:
        alt = Vector((0.0, 1.0, 0.0)) if abs(axis_n.y) < 0.9 else Vector((1.0, 0.0, 0.0))
        v = alt - axis_n * alt.dot(axis_n)
    v.normalize()
    u = v.cross(axis_n)
    u.normalize()
    if roll_deg:
        rot = Matrix.Rotation(math.radians(roll_deg), 3, axis_n)
        u, v = rot @ u, rot @ v
    return u, v


def _face(bm, verts, mat):
    try:
        f = bm.faces.new(verts)
    except ValueError:
        return None
    f.material_index = mat
    return f


def _loft(bm, o0, o1, i0=None, i1=None, caps=True, mat=0):
    """Connect start ring(s) o0/i0 to end ring(s) o1/i1. Outline is CCW seen from +axis => outward normals."""
    faces = []
    n = len(o0)
    for k in range(n):
        j = (k + 1) % n
        faces.append(_face(bm, [o0[k], o0[j], o1[j], o1[k]], mat))
    if i0 is not None:
        for k in range(n):
            j = (k + 1) % n
            faces.append(_face(bm, [i0[j], i0[k], i1[k], i1[j]], mat))   # bore wall faces the void
    if caps:
        if i0 is None:
            faces.append(_face(bm, list(o1), mat))
            faces.append(_face(bm, list(reversed(o0)), mat))
        else:
            for k in range(n):
                j = (k + 1) % n
                faces.append(_face(bm, [o1[k], o1[j], i1[j], i1[k]], mat))
                faces.append(_face(bm, [i0[k], i0[j], o0[j], o0[k]], mat))
    return [f for f in faces if f is not None]


def add_prism(bm, profile, p0, p1, up=Z_UP, roll_deg=0.0, extend=(0.0, 0.0), mat=0, caps=True):
    """Extrude a 2D `profile` (dict from profile_*/steel_profile) along p0->p1.

    `up` fixes the section's v direction (projected perpendicular to the axis); u = v x axis.
    One watertight solid — use this for H/I beams, tubes, rails, battens instead of stacking boxes.
    Returns the list of created faces.
    """
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    length = axis.length
    if length < 1e-9:
        return []
    axis_n = axis / length
    u, v = _frame(axis_n, up, roll_deg)
    c0 = p0 - axis_n * extend[0]
    c1 = p1 + axis_n * extend[1]
    outer = profile["outer"] if isinstance(profile, dict) else profile
    inner = profile.get("inner") if isinstance(profile, dict) else None

    def ring(c, pts):
        return [bm.verts.new(c + u * a + v * b) for a, b in pts]

    o0, o1 = ring(c0, outer), ring(c1, outer)
    i0 = i1 = None
    if inner:
        if len(inner) != len(outer):
            raise ValueError("hollow profile needs inner/outer with equal vertex counts")
        i0, i1 = ring(c0, inner), ring(c1, inner)
    return _loft(bm, o0, o1, i0, i1, caps, mat)


def add_steel_member(bm, section, p0, p1, up=Z_UP, roll_deg=0.0, extend=(0.0, 0.0), mat=0, fillet_segs=0):
    """H/I/channel/angle/tube member by designation, e.g. add_steel_member(bm, 'HEB220', (x,y,0), (x,y,12))."""
    return add_prism(bm, steel_profile(section, fillet_segs), p0, p1, up, roll_deg, extend, mat)


def add_cylinder(bm, p0, p1, r0, r1=None, wall=None, segs=24, caps=True, mat=0):
    """Cylinder / cone / tube along an arbitrary axis p0->p1 (wall => hollow tube, radius shrinks with r)."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    if axis.length < 1e-9:
        return []
    axis_n = axis.normalized()
    u, v = _frame(axis_n, Z_UP)
    r1 = r0 if r1 is None else r1

    def ring(c, r):
        return [bm.verts.new(c + (u * math.cos(2 * math.pi * k / segs) + v * math.sin(2 * math.pi * k / segs)) * r)
                for k in range(segs)]

    o0, o1 = ring(p0, r0), ring(p1, r1)
    i0 = i1 = None
    if wall:
        i0, i1 = ring(p0, max(r0 - wall, r0 * 0.05)), ring(p1, max(r1 - wall, r1 * 0.05))
    return _loft(bm, o0, o1, i0, i1, caps, mat)


def add_flange_ring(bm, centre, axis, r_in, r_out, thickness, segs=24, mat=0):
    """Flat collar/flange ring (pipe joint, clamp) of `thickness` centred on `centre`, normal along `axis`."""
    a = Vector(axis).normalized() * (thickness / 2)
    c = Vector(centre)
    return add_cylinder(bm, c - a, c + a, r_out, wall=r_out - r_in, segs=segs, mat=mat)


def add_oriented_box(bm, origin, run, normal, a0, a1, n0, n1, z0, z1, mat=0):
    """Box in a local facade frame: a along `run`, n along `normal`, z along world Z (all in metres,
    measured from `origin`). Orientation-agnostic (flips winding for left-handed frames)."""
    origin, run, normal = Vector(origin), Vector(run).normalized(), Vector(normal).normalized()
    right_handed = run.cross(normal).dot(Z_UP) > 0
    V = {}
    for ia, a in ((0, a0), (1, a1)):
        for in_, n in ((0, n0), (1, n1)):
            for iz, z in ((0, z0), (1, z1)):
                V[(ia, in_, iz)] = bm.verts.new(origin + run * a + normal * n + Z_UP * z)
    quads = [
        [V[0, 0, 0], V[0, 1, 0], V[1, 1, 0], V[1, 0, 0]],   # bottom
        [V[0, 0, 1], V[1, 0, 1], V[1, 1, 1], V[0, 1, 1]],   # top
        [V[0, 0, 0], V[0, 0, 1], V[0, 1, 1], V[0, 1, 0]],   # a0
        [V[1, 0, 0], V[1, 1, 0], V[1, 1, 1], V[1, 0, 1]],   # a1
        [V[0, 0, 0], V[1, 0, 0], V[1, 0, 1], V[0, 0, 1]],   # n0
        [V[0, 1, 0], V[0, 1, 1], V[1, 1, 1], V[1, 1, 0]],   # n1
    ]
    out = []
    for q in quads:
        out.append(_face(bm, q if right_handed else list(reversed(q)), mat))
    return [f for f in out if f]


def add_box(bm, centre, size, rot_z_deg=0.0, mat=0):
    """Axis-aligned (optionally Z-rotated) box centred at `centre` with full `size` (sx, sy, sz)."""
    mtx = Matrix.LocRotScale(Vector(centre), Euler((0.0, 0.0, math.radians(rot_z_deg))), Vector(size))
    g = bmesh.ops.create_cube(bm, size=1.0, matrix=mtx)
    for f in {f for v in g["verts"] for f in v.link_faces}:
        f.material_index = mat
    return g


# ==============================================================================
# 3. FACADE / ARCHITECTURAL DETAIL BUILDERS
# ==============================================================================

def add_slat_array(bm, p0, p1, z0, z1, pitch, slat_w, slat_t, normal, margin=0.0, rhombic=False, mat=0):
    """Vertical battens/cladding boards along the wall run p0->p1 (plan points), from z0 to z1.

    pitch = centre-to-centre spacing, slat_w = width along the wall, slat_t = depth along `normal` (outward).
    rhombic=True => diamond-section boards (planed 'Raute' battens). Returns count.
    """
    p0, p1 = Vector(p0), Vector(p1)
    run = p1 - p0
    length = run.length
    run_n = run / length
    normal = Vector(normal).normalized()
    count = 0
    s = margin + slat_w / 2
    while s <= length - margin - slat_w / 2 + 1e-9:
        base = p0 + run_n * s
        if rhombic:
            add_prism(bm, profile_diamond(slat_w, slat_t), base + Vector((0, 0, z0)), base + Vector((0, 0, z1)),
                      up=normal, mat=mat)
        else:
            add_oriented_box(bm, base, run_n, normal, -slat_w / 2, slat_w / 2, 0.0, slat_t, z0, z1, mat)
        count += 1
        s += pitch
    return count


def add_louver_leaf(bm, origin, run, normal, width, height, blades=24, blade_depth=0.07, blade_t=0.012,
                    tilt_deg=35.0, frame_w=0.05, frame_t=0.045, mat=0):
    """One shutter leaf: 2 stiles + 2 rails + `blades` TILTED slats (real louvers, not flat plates).

    origin = bottom-left corner on the facade plane, `run` along the leaf width, `normal` outward.
    """
    origin, run, normal = Vector(origin), Vector(run).normalized(), Vector(normal).normalized()
    add_oriented_box(bm, origin, run, normal, 0, frame_w, 0, frame_t, 0, height, mat)                       # left stile
    add_oriented_box(bm, origin, run, normal, width - frame_w, width, 0, frame_t, 0, height, mat)           # right stile
    add_oriented_box(bm, origin, run, normal, frame_w, width - frame_w, 0, frame_t, 0, frame_w, mat)        # bottom rail
    add_oriented_box(bm, origin, run, normal, frame_w, width - frame_w, 0, frame_t, height - frame_w, height, mat)  # top rail
    inner_h = height - 2 * frame_w
    pitch = inner_h / blades
    for i in range(blades):
        zc = frame_w + pitch * (i + 0.5)
        a = origin + run * frame_w + normal * (frame_t / 2) + Z_UP * zc
        b = origin + run * (width - frame_w) + normal * (frame_t / 2) + Z_UP * zc
        add_prism(bm, profile_rect(blade_t, min(blade_depth, frame_t * 1.6)), a, b, up=normal, roll_deg=tilt_deg, mat=mat)
    return blades


def add_railing(bm, path, height=1.0, post_pitch=1.2, post_size=0.04, rail_size=0.04, mid_rails=3,
                baluster_pitch=None, baluster_size=0.012, kick_h=0.0, closed=False, mat=0):
    """Guard-rail along a 3D `path` (points on the walking surface): posts at vertices + every ~post_pitch,
    top handrail, `mid_rails` horizontal bars (or vertical balusters if baluster_pitch), optional kick plate.
    Bars span cleanly between post faces so the railing has 0 self-overlap."""
    pts = [Vector(p) for p in path]
    segs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    top_z = height - rail_size * 0.5
    posts = []
    bays = []
    for a, b in segs:
        d = b - a
        if d.length < 1e-6:
            continue
        n_div = max(1, int(round(d.length / post_pitch)))
        for k in range(n_div):
            p0 = a + d * (k / n_div)
            p1 = a + d * ((k + 1) / n_div)
            posts.append(p0)
            bays.append((p0, p1))
    if segs and not closed:
        posts.append(segs[-1][1])
    seen = []
    for p in posts:
        if any((p - q).length < 1e-4 for q in seen):
            continue
        seen.append(p)
        add_box(bm, p + Vector((0, 0, height / 2)), (post_size, post_size, height), mat=mat)
    for pa, pb in bays:
        d = pb - pa
        if d.length <= post_size + 1e-4:
            continue
        dn = d.normalized()
        s_a = pa + dn * (post_size * 0.5)
        s_b = pb - dn * (post_size * 0.5)
        span_len = (s_b - s_a).length
        add_prism(bm, profile_rect(rail_size, rail_size),
                  s_a + Vector((0, 0, top_z)), s_b + Vector((0, 0, top_z)), up=Z_UP, mat=mat)
        if baluster_pitch:
            s = baluster_pitch
            bal_h = max(0.01, height - rail_size)
            while s < span_len - 1e-6:
                q = s_a + dn * s
                add_box(bm, q + Vector((0, 0, bal_h / 2)), (baluster_size, baluster_size, bal_h), mat=mat)
                s += baluster_pitch
        else:
            for i in range(mid_rails):
                zc = height * (i + 1) / (mid_rails + 1)
                add_prism(bm, profile_rect(rail_size * 0.5, rail_size * 0.5),
                          s_a + Vector((0, 0, zc)), s_b + Vector((0, 0, zc)), mat=mat)
        if kick_h > 0:
            add_prism(bm, profile_rect(0.012, kick_h),
                      s_a + Vector((0, 0, kick_h / 2)), s_b + Vector((0, 0, kick_h / 2)), mat=mat)


def add_window(bm, origin, run, normal, width, height, frame=0.06, depth=0.08, panes=(2, 1), bar=0.04,
               glass_t=0.012, mat_frame=0, mat_glass=1):
    """Window/curtain-wall bay: perimeter frame + (cols-1) vertical and (rows-1) horizontal bars + glass panes.
    Use materials=[frame_mat, glass_mat] in finalize_object so one mesh carries both."""
    origin, run, normal = Vector(origin), Vector(run).normalized(), Vector(normal).normalized()
    ob = lambda a0, a1, z0, z1, n0=0.0, n1=depth, m=mat_frame: add_oriented_box(bm, origin, run, normal, a0, a1, n0, n1, z0, z1, m)
    ob(0, frame, 0, height)
    ob(width - frame, width, 0, height)
    ob(frame, width - frame, 0, frame)
    ob(frame, width - frame, height - frame, height)
    cols, rows = panes
    inner_w, inner_h = width - 2 * frame, height - 2 * frame
    for c in range(1, cols):
        x = frame + inner_w * c / cols
        ob(x - bar / 2, x + bar / 2, frame, height - frame)
    for r in range(1, rows):
        z = frame + inner_h * r / rows
        for c in range(cols):
            a0 = frame + inner_w * c / cols + (bar / 2 if c > 0 else 0)
            a1 = frame + inner_w * (c + 1) / cols - (bar / 2 if c < cols - 1 else 0)
            if a1 - a0 > 1e-4:
                ob(a0, a1, z - bar / 2, z + bar / 2)
    for c in range(cols):
        for r in range(rows):
            a0 = frame + inner_w * c / cols + (bar / 2 if c > 0 else 0)
            a1 = frame + inner_w * (c + 1) / cols - (bar / 2 if c < cols - 1 else 0)
            z0 = frame + inner_h * r / rows + (bar / 2 if r > 0 else 0)
            z1 = frame + inner_h * (r + 1) / rows - (bar / 2 if r < rows - 1 else 0)
            ob(a0, a1, z0, z1, n0=depth / 2 - glass_t / 2, n1=depth / 2 + glass_t / 2, m=mat_glass)


# ==============================================================================
# 4. OBJECT FINALISER (thin-member-aware bevel, multi-material)
# ==============================================================================

def _auto_bevel_width(bm, cap=0.006):
    """Bevel ~30% of the 10th-percentile edge length so thin louvers/rails never get rounded away."""
    lengths = sorted(e.calc_length() for e in bm.edges if e.calc_length() > 1e-5)
    if not lengths:
        return 0.0
    w = min(cap, 0.3 * lengths[len(lengths) // 10])
    return w if w >= 0.0005 else 0.0


def finalize_object(name, bm, col, materials=None, bevel="auto", smooth=False, group=None, merge_dist=0.0, archive_existing=True):
    """BMesh -> object in `col` (archives any existing same-name object as `__hide_r<N>__<name>` when `archive_existing=True`).
    materials: list of bpy Materials mapped to face.material_index. bevel='auto' | metres | 0.
    merge_dist>0 welds coincident verts (off by default). `group` is ignored (RANDOM shading is used). Frees `bm`."""
    _ = group  # deprecated: RANDOM shading does not use per-object color groups
    old = bpy.data.objects.get(name)
    if old:
        if archive_existing and not name.startswith("_"):
            import os as _os, sys as _sys
            _d = _os.path.dirname(_os.path.abspath(__file__))
            if _d not in _sys.path:
                _sys.path.insert(0, _d)
            import cad_operator_recipes as _COR
            _COR.hide_defective_components([name], reason="finalize_object_regen")
        else:
            bpy.data.objects.remove(old, do_unlink=True)
    if merge_dist:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=merge_dist)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bevel_w = _auto_bevel_width(bm) if bevel == "auto" else float(bevel or 0.0)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in (materials or []):
        mesh.materials.append(m)
    if smooth:
        mesh.shade_smooth()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    if bevel_w > 0:
        b = obj.modifiers.new("Bevel", 'BEVEL')
        b.width, b.segments = bevel_w, 1
        b.limit_method, b.angle_limit = 'ANGLE', math.radians(35.0)
    return obj


# ==============================================================================
# 5. FEATURE LEDGER (anti-omission checklist) & DETAIL AUDIT
# ==============================================================================

LEDGER_KEY = "agy_feature_ledger"


def ledger_set(items):
    """Register the feature inventory read from the references BEFORE modelling.

    items: list of dicts {id, label, tier: 'L1'|'L2'|'L3', match: [fnmatch patterns on object names],
           min_objects: 1, min_verts: 0, expect_profile: False, src: 'photo2 / section / ...'}.
    Stored on the scene (survives .blend save) and returned for echo.
    """
    bpy.context.scene[LEDGER_KEY] = json.dumps(items, ensure_ascii=False)
    return {"registered": len(items), "tiers": _count_by(items, "tier")}


def ledger_get():
    raw = bpy.context.scene.get(LEDGER_KEY)
    return json.loads(raw) if raw else []


def _count_by(items, key):
    out = {}
    for it in items:
        out[it.get(key, "?")] = out.get(it.get(key, "?"), 0) + 1
    return out


def _is_primitive_box(obj):
    return obj.type == 'MESH' and len(obj.data.vertices) <= 8 and len(obj.data.polygons) <= 6


def ledger_check(scene=None):
    """Compare the registered inventory with live active objects. Returns per-tier coverage plus
    `missing` (no matching object) and `weak` (too few verts / box standing in for a section member)."""
    scene = scene or bpy.context.scene
    items = ledger_get()
    objs = [o for o in scene.objects if o.type == 'MESH' and not o.hide_viewport and not o.hide_render and not o.name.startswith(("__hide_r", "__wip__", "BBOX_"))]
    rows, missing, weak = [], [], []
    tier_total, tier_ok = {}, {}
    for it in items:
        pats = it.get("match") or []
        hits = [o for o in objs if any(fnmatch.fnmatch(o.name, p) for p in pats)]
        verts = sum(len(o.data.vertices) for o in hits)
        status = "ok"
        if len(hits) < int(it.get("min_objects", 1)):
            status = "MISSING"
            missing.append(it["id"])
        elif verts < int(it.get("min_verts", 0)):
            status = "WEAK(verts)"
            weak.append(f'{it["id"]}: {verts} verts < {it["min_verts"]}')
        elif it.get("expect_profile") and hits and all(_is_primitive_box(o) for o in hits):
            status = "WEAK(box-standin)"
            weak.append(f'{it["id"]}: only primitive boxes, expected real section/profile')
        t = it.get("tier", "?")
        tier_total[t] = tier_total.get(t, 0) + 1
        tier_ok[t] = tier_ok.get(t, 0) + (1 if status == "ok" else 0)
        rows.append({"id": it["id"], "tier": t, "status": status, "objects": [o.name for o in hits][:6], "verts": verts})
    return {
        "coverage": {t: f"{tier_ok.get(t, 0)}/{tier_total[t]}" for t in sorted(tier_total)},
        "passed": not missing and not weak,
        "missing": missing,
        "weak": weak,
        "rows": rows,
    }


_PROFILE_HINTS = ("beam", "column", "rail", "mullion", "slat", "batten", "louver", "shutter",
                  "chimney", "joist", "purlin", "stringer", "heb", "hea", "ipe", "upn")
_DEFAULT_AUDIT_WHITELIST = ("*Wall*", "*Slab*", "*Roof*", "*Glass*", "*Sill*", "*Lintel*", "*Parapet*", "*Stair*", "*Step*")


def _is_whitelisted(obj, patterns):
    if obj.get("detail_audit_ok"):
        return True
    return any(fnmatch.fnmatch(obj.name, p) for p in patterns)


def detail_audit(scene=None, big_box_min_dim=0.4, whitelist=()):
    """Heuristic detail-fidelity audit of the live scene:
      - `box_standins`: primitive-box meshes whose NAME suggests a profiled/repeated member (beam, slat, rail...)
        excluding objects matching `whitelist`, built-in architectural shell defaults, or `obj['detail_audit_ok']`
      - `large_plain_boxes`: plain boxes with a side > big_box_min_dim (legit for massing, confirm vs references)
      - `repeat_groups`: object families by stripped numeric suffix (proves arrays were really modelled)
      - `tris_total` and object counts.
    """
    scene = scene or bpy.context.scene
    extra = json.loads(scene.get("detail_audit_whitelist", "[]")) if scene.get("detail_audit_whitelist") else []
    patterns = tuple(_DEFAULT_AUDIT_WHITELIST) + tuple(whitelist or ()) + tuple(extra)
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_viewport and not o.hide_render and not o.name.startswith(("__hide_r", "__wip__", "BBOX_"))]
    stand, big = [], []
    fam = {}
    tris = 0
    for o in meshes:
        tris += sum(max(1, len(p.vertices) - 2) for p in o.data.polygons)
        low = o.name.lower()
        if _is_primitive_box(o):
            if any(h in low for h in _PROFILE_HINTS) and not _is_whitelisted(o, patterns):
                stand.append(o.name)
            if max(o.dimensions) > big_box_min_dim:
                big.append(f"{o.name} {tuple(round(d, 2) for d in o.dimensions)}")
        base = re.sub(r"[._]?\d+$", "", o.name)
        fam[base] = fam.get(base, 0) + 1
    repeats = {k: v for k, v in sorted(fam.items(), key=lambda kv: -kv[1]) if v > 1}
    return {
        "passed": len(stand) == 0,
        "mesh_objects": len(meshes),
        "tris_total": tris,
        "box_standins": stand,
        "large_plain_boxes": big,
        "repeat_groups": repeats,
        "verdict": "OK" if not stand else "REVIEW: box stand-ins for profiled members",
    }
