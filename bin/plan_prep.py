"""[BIN_PLAN_PREP] 平面图旋转配准 · ROI 裁剪淡化 · 米制红蓝网格 · 结构分层 · 轮廓边墨迹支持度预检
- 适用 (When): P1/P2 处理倾斜或含周边干扰的 PNG 平面图：scan 找候选倾角与 ROI → build 旋平并生成米制网格 → px2m/scale-from-section 算尺度 → check-outline 预检规格边
- 用法 (How) : python3 bin/plan_prep.py scan --input plan.png --out agy_work/ | build --input plan.png --angle 19.5 --roi u0,v0,u1,v1 --refine [--scale s --layers] | check-outline --meta plan_meta.json --spec building_spec.json --level L1
- 产出 (Out) : <=20 行摘要 + agy_work/{scan_sheet.png, orient_candidates.png, plan_rot.png, plan_roi.png, plan_meta.json}; 长边<=1600px
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    from skimage.transform import probabilistic_hough_line as _sk_phough  # type: ignore
except Exception:
    _sk_phough = None

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_RECIPE_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "examples", "recipes"))
if _RECIPE_DIR not in sys.path:
    sys.path.insert(0, _RECIPE_DIR)

MAX_IMAGE_SIDE = 1600


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _cap_image(img: Image.Image, max_side: int = MAX_IMAGE_SIDE):
    w, h = img.size
    m = max(w, h)
    if m <= max_side:
        return img, 1.0
    s = max_side / float(m)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    return img.resize((nw, nh), Image.Resampling.LANCZOS), s


def _affine_rot_params(w: int, h: int, angle_deg: float):
    """angle_deg is visual CCW tilt of the building's main axis (screen +u right, +v down).
    Leveling rotates CW by `angle_deg`. Returns (w_rot, h_rot, M_src_to_rot_2x3, M_rot_to_src_2x3).
    """
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = w * 0.5, h * 0.5
    corners = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
    rot_pts = [(ca * (u - cx) - sa * (v - cy), sa * (u - cx) + ca * (v - cy)) for u, v in corners]
    min_u = min(p[0] for p in rot_pts)
    max_u = max(p[0] for p in rot_pts)
    min_v = min(p[1] for p in rot_pts)
    max_v = max(p[1] for p in rot_pts)
    w_rot = int(math.ceil(max_u - min_u))
    h_rot = int(math.ceil(max_v - min_v))
    cx_r, cy_r = -min_u, -min_v
    m_fwd = [
        [ca, -sa, cx_r - ca * cx + sa * cy],
        [sa, ca, cy_r - sa * cx - ca * cy],
    ]
    m_inv = [
        [ca, sa, cx - ca * cx_r - sa * cy_r],
        [-sa, ca, cy + sa * cx_r - ca * cy_r],
    ]
    return w_rot, h_rot, m_fwd, m_inv


def _apply_affine(m, u: float, v: float):
    return (m[0][0] * u + m[0][1] * v + m[0][2], m[1][0] * u + m[1][1] * v + m[1][2])


def _rotate_image(img: Image.Image, angle_deg: float, bg=(248, 248, 246)):
    w_rot, h_rot, m_fwd, m_inv = _affine_rot_params(img.width, img.height, angle_deg)
    coeffs = (m_inv[0][0], m_inv[0][1], m_inv[0][2], m_inv[1][0], m_inv[1][1], m_inv[1][2])
    rot = img.transform((w_rot, h_rot), Image.Transform.AFFINE, coeffs, resample=Image.Resampling.BICUBIC, fillcolor=bg)
    return rot, m_fwd, m_inv


def _morph3(arr: np.ndarray, mode: str) -> np.ndarray:
    """Fast 3x3 binary/bool erode or dilate using pure numpy slicing."""
    p = np.pad(arr, 1, mode="edge")
    slices = (
        p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:],
        p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:],
        p[2:, :-2], p[2:, 1:-1], p[2:, 2:],
    )
    out = slices[0].copy()
    fn = np.minimum if mode == "erode" else np.maximum
    for s in slices[1:]:
        out = fn(out, s)
    return out


def _sobel(gray: np.ndarray, blur_radius: float = 1.2):
    """Gaussian-smoothed Scharr gradient to eliminate 3x3 pixel-staircase angular bias."""
    if blur_radius > 0:
        pil_g = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=blur_radius)
        )
        g = np.array(pil_g, dtype=np.float32)
    else:
        g = gray.astype(np.float32)
    p = np.pad(g, 1, mode="edge")
    gx = 3.0 * p[:-2, 2:] + 10.0 * p[1:-1, 2:] + 3.0 * p[2:, 2:] - (3.0 * p[:-2, :-2] + 10.0 * p[1:-1, :-2] + 3.0 * p[2:, :-2])
    gy = 3.0 * p[2:, :-2] + 10.0 * p[2:, 1:-1] + 3.0 * p[2:, 2:] - (3.0 * p[:-2, :-2] + 10.0 * p[:-2, 1:-1] + 3.0 * p[:-2, 2:])
    return gx / 16.0, gy / 16.0


def _ink_and_thick_mask(gray: np.ndarray):
    med = float(np.median(gray))
    ink = np.clip(med - gray.astype(np.float32), 0.0, 255.0)
    dark = ink > max(28.0, 0.22 * med)
    thick = _morph3(_morph3(dark, "erode"), "dilate")
    if int(np.sum(thick)) < 40:
        thick = dark
    return ink, dark, thick


def _fold90(deg: float) -> float:
    x = ((deg + 45.0) % 90.0) - 45.0
    if x <= -45.0:
        x += 90.0
    return x


def _grad_peaks(gray: np.ndarray, mask_region=None):
    """M1: Thick-stroke Scharr gradient histogram mod 90 -> sorted [(angle_deg, share)]."""
    h, w = gray.shape
    my, mx = max(2, int(0.03 * h)), max(2, int(0.03 * w))
    _, dark, thick = _ink_and_thick_mask(gray)
    # Use thick-stroke neighborhood (excluding outer 3% border) so wall boundaries beat grid lines/frames
    support = _morph3(_morph3(thick, "dilate"), "dilate")
    support[:my, :] = False
    support[h - my:, :] = False
    support[:, :mx] = False
    support[:, w - mx:] = False
    if mask_region is not None:
        support = support & mask_region
    gx, gy = _sobel(gray, blur_radius=1.2)
    mag = np.hypot(gx, gy)
    sel = support & (mag > 12.0)
    if int(np.sum(sel)) < 30:
        sel = _morph3(dark, "dilate") & (mag > 10.0)
        if mask_region is not None:
            sel = sel & mask_region
    if int(np.sum(sel)) < 10:
        return [(0.0, 1.0)]
    ang = np.degrees(np.arctan2(gx[sel], gy[sel]))
    ang90 = (ang + 45.0) % 90.0 - 45.0
    w = mag[sel]
    bins = 180  # 0.5 deg per bin across [-45, 45)
    hist, edges = np.histogram(ang90, bins=bins, range=(-45.0, 45.0), weights=w)
    ext = np.concatenate([hist[-2:], hist, hist[:2]])
    sm = (ext[:-4] + 2 * ext[1:-3] + 3 * ext[2:-2] + 2 * ext[3:-1] + ext[4:]) / 9.0
    total = float(np.sum(sm)) + 1e-9
    mean_bin = total / bins
    peaks = []
    for i in range(bins):
        if sm[i] > sm[(i - 1) % bins] and sm[i] >= sm[(i + 1) % bins] and sm[i] > 1.6 * mean_bin:
            idxs = [(i + d) % bins for d in range(-4, 5)]
            share = float(np.sum(hist[idxs])) / (float(np.sum(hist)) + 1e-9)
            if share < 0.045:
                continue
            loc = [(d, float(hist[(i + d) % bins])) for d in range(-2, 3)]
            wsum = sum(v for _, v in loc) + 1e-9
            d_off = sum(d * v for d, v in loc) / wsum
            ctr = 0.5 * (edges[i] + edges[i + 1]) + d_off * 0.5
            peaks.append((round(_fold90(float(ctr)), 2), round(share, 4)))
    peaks.sort(key=lambda x: -x[1])
    return peaks or [(0.0, 1.0)]


def _line_peaks(gray: np.ndarray):
    """M2: Long-segment Hough (if skimage present) or tiled structure-tensor fallback (border excluded 3%)."""
    h, w = gray.shape
    my, mx = max(2, int(0.03 * h)), max(2, int(0.03 * w))
    interior = np.zeros((h, w), dtype=bool)
    interior[my:h - my, mx:w - mx] = True
    _, dark, thick = _ink_and_thick_mask(gray)
    edges = dark & (~_morph3(dark, "erode")) & interior

    if _sk_phough is not None:
        min_len = max(20, int(min(h, w) * 0.05))
        lines = _sk_phough(edges, threshold=10, line_length=min_len, line_gap=6)
        # Also include thick boundary segments so thin grid intersections cannot split masonry walls
        thick_edges = thick & (~_morph3(thick, "erode")) & interior
        lines = list(lines) + list(_sk_phough(thick_edges, threshold=8, line_length=min_len, line_gap=8))
        if lines:
            hist = np.zeros(180, dtype=np.float64)
            for (x0, y0), (x1, y1) in lines:
                dx, dy = float(x1 - x0), float(y1 - y0)
                L = math.hypot(dx, dy)
                if L < 1.0:
                    continue
                deg = _fold90(math.degrees(math.atan2(-dy, dx)))
                b = int((deg + 45.0) * 2.0) % 180
                hist[b] += L
            total = float(np.sum(hist)) + 1e-9
            ext = np.concatenate([hist[-2:], hist, hist[:2]])
            sm = (ext[:-4] + 2 * ext[1:-3] + 3 * ext[2:-2] + 2 * ext[3:-1] + ext[4:]) / 9.0
            peaks = []
            for i in range(180):
                if sm[i] > sm[(i - 1) % 180] and sm[i] >= sm[(i + 1) % 180] and sm[i] > 0.03 * np.sum(sm):
                    idxs = [(i + d) % 180 for d in range(-4, 5)]
                    share = float(np.sum(hist[idxs])) / total
                    loc = [(d, float(hist[(i + d) % 180])) for d in range(-2, 3)]
                    d_off = sum(d * v for d, v in loc) / (sum(v for _, v in loc) + 1e-9)
                    ctr = -45.0 + (i + 0.5 + d_off) * 0.5
                    peaks.append((round(_fold90(ctr), 2), round(share, 4)))
            peaks.sort(key=lambda x: -x[1])
            if peaks:
                return peaks

    # Pure-numpy structure-tensor fallback over medium patches (jyy - jxx matches atan2(gx, gy)!)
    gx, gy = _sobel(gray, blur_radius=1.2)
    gx = np.where(interior, gx, 0.0)
    gy = np.where(interior, gy, 0.0)
    step = max(16, min(h, w) // 16)
    hist = np.zeros(180, dtype=np.float64)
    for v0 in range(my, h - my, step):
        for u0 in range(mx, w - mx, step):
            px, py = gx[v0:v0 + step, u0:u0 + step], gy[v0:v0 + step, u0:u0 + step]
            jxx = float(np.sum(px * px))
            jyy = float(np.sum(py * py))
            jxy = float(np.sum(px * py))
            tr = jxx + jyy
            if tr < 200.0:
                continue
            coh = math.hypot(jyy - jxx, 2.0 * jxy) / (tr + 1e-9)
            if coh < 0.35:
                continue
            ang = 0.5 * math.degrees(math.atan2(2.0 * jxy, jyy - jxx))
            deg = _fold90(ang)
            b = int((deg + 45.0) * 2.0) % 180
            hist[b] += coh * math.sqrt(tr)
    total = float(np.sum(hist)) + 1e-9
    peaks = []
    for i in range(180):
        if hist[i] > hist[(i - 1) % 180] and hist[i] >= hist[(i + 1) % 180] and hist[i] > 0.04 * total:
            idxs = [(i + d) % 180 for d in range(-4, 5)]
            share = float(np.sum(hist[idxs])) / total
            loc = [(d, float(hist[(i + d) % 180])) for d in range(-2, 3)]
            d_off = sum(d * v for d, v in loc) / (sum(v for _, v in loc) + 1e-9)
            peaks.append((round(_fold90(-45.0 + (i + 0.5 + d_off) * 0.5), 2), round(share, 4)))
    peaks.sort(key=lambda x: -x[1])
    return peaks


def _merge_candidates(m1, m2, tol_deg=3.0, limit=3):
    items = [{"deg": d, "share": s, "src": "M1(thick)"} for d, s in m1[:4]]
    items += [{"deg": d, "share": s, "src": "M2(line)"} for d, s in m2[:4]]
    merged = []
    for it in items:
        hit = None
        for m in merged:
            diff = abs(((it["deg"] - m["deg"] + 45.0) % 90.0) - 45.0)
            if diff <= tol_deg:
                hit = m
                break
        if hit:
            if it["src"] not in hit["src"]:
                hit["src"] = "M1+M2"
                hit["share"] = round(max(hit["share"], it["share"]), 4)
            # Prefer M1 angle when both agree (walls beat decoy lines)
            if "M1" in it["src"] and "M1" not in hit["src"]:
                hit["deg"] = it["deg"]
        else:
            merged.append(dict(it))
    # Prioritize M1 candidates first, then share
    merged.sort(key=lambda c: (-int("M1" in c["src"]), -c["share"]))
    return merged[:limit]


def _suggest_roi(gray: np.ndarray):
    _, _, thick = _ink_and_thick_mask(gray)
    h, w = thick.shape
    # Restrict thick-ink bbox via percentiles to ignore outer title border/stray specks
    mx, my = max(2, int(0.03 * w)), max(2, int(0.03 * h))
    core = thick.copy()
    core[:my, :] = False
    core[h - my:, :] = False
    core[:, :mx] = False
    core[:, w - mx:] = False
    ys, xs = np.where(core)
    if len(xs) < 20:
        return [0, 0, w, h]
    pad_x, pad_y = int(0.05 * w), int(0.05 * h)
    u0 = max(0, int(np.percentile(xs, 3)) - pad_x)
    u1 = min(w, int(np.percentile(xs, 97)) + pad_x)
    v0 = max(0, int(np.percentile(ys, 3)) - pad_y)
    v1 = min(h, int(np.percentile(ys, 97)) + pad_y)
    return [u0, v0, u1, v1]


def align_score(gray: np.ndarray, roi_box=None, deg_tol=2.5) -> float:
    """Excess thick-stroke orthogonal energy within +/-`deg_tol` of 0/90 deg relative to peak excess in ROI."""
    sub = gray if roi_box is None else gray[roi_box[1]:roi_box[3], roi_box[0]:roi_box[2]]
    if sub.size < 16:
        return 0.0
    _, dark, thick = _ink_and_thick_mask(sub)
    sup = _morph3(_morph3(thick, "dilate"), "dilate")
    gx, gy = _sobel(sub, blur_radius=1.2)
    mag = np.hypot(gx, gy)
    sel = sup & (mag > 12.0)
    if int(np.sum(sel)) < 20:
        sel = _morph3(dark, "dilate") & (mag > 10.0)
    if int(np.sum(sel)) < 5:
        return 0.0
    ang = np.degrees(np.arctan2(gx[sel], gy[sel]))
    ang90 = (ang + 45.0) % 90.0 - 45.0
    w = mag[sel]
    bins = 180  # 0.5 deg/bin over [-45, 45)
    hist, _ = np.histogram(ang90, bins=bins, range=(-45.0, 45.0), weights=w)
    baseline = float(np.percentile(hist, 25))
    excess = np.maximum(hist - baseline, 0.0)
    half_w = max(1, int(round(deg_tol / 0.5)))
    win_w = 2 * half_w
    ext = np.concatenate([excess[-half_w:], excess, excess[:half_w]])
    cs = np.cumsum(np.concatenate(([0.0], ext)))
    win = cs[win_w:] - cs[:-win_w]  # length bins+1; win[90] sums excess[85:95] == [-2.5, +2.5) deg
    e_zero = float(win[bins // 2])
    e_max = float(np.max(win[:-1]))
    if e_max <= 1e-6:
        return 0.0
    return float(min(1.0, e_zero / e_max))


def _draw_scan_sheet(src: Image.Image, roi, out_path: str):
    img, s = _cap_image(src.convert("RGB"), MAX_IMAGE_SIDE)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    font = _font(max(13, min(w, h) // 45))
    for i in range(1, 3):
        x = int(round(w * i / 3))
        y = int(round(h * i / 3))
        draw.line([(x, 0), (x, h)], fill=(210, 60, 60), width=1)
        draw.line([(0, y), (w, y)], fill=(60, 60, 210), width=1)
    labels = [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]]
    for r in range(3):
        for c in range(3):
            u_src = int(round((c * src.width) / 3))
            v_src = int(round((r * src.height) / 3))
            px, py = int(w * c / 3) + 6, int(h * r / 3) + 4
            draw.rectangle([px - 2, py - 1, px + 95, py + font.size + 4 if hasattr(font, "size") else py + 18], fill=(255, 255, 240))
            draw.text((px, py), f"{labels[r][c]} ({u_src},{v_src})", fill=(20, 20, 120), font=font)
    # Border pixel markers
    for sx in range(0, src.width, max(100, (src.width // 6 // 50) * 50)):
        px = int(round(sx * s))
        draw.text((px + 2, h - 18), str(sx), fill=(180, 0, 0), font=font)
    for sy in range(0, src.height, max(100, (src.height // 5 // 50) * 50)):
        py = int(round(sy * s))
        draw.text((4, py + 2), str(sy), fill=(0, 0, 180), font=font)
    ru = [int(round(v * s)) for v in roi]
    draw.rectangle([ru[0], ru[1], max(ru[0] + 1, ru[2] - 1), max(ru[1] + 1, ru[3] - 1)], outline=(20, 170, 50), width=3)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)


def _draw_orient_candidates(src: Image.Image, candidates, roi, out_path: str):
    crop = src.convert("RGB").crop(tuple(roi))
    panels = []
    pw, ph = 480, 420
    font = _font(15)
    for c in candidates:
        rot, _, _ = _rotate_image(crop, c["deg"])
        rot.thumbnail((pw - 20, ph - 40), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (pw, ph), (248, 248, 246))
        ox, oy = (pw - rot.width) // 2, 30 + (ph - 34 - rot.height) // 2
        tile.paste(rot, (ox, oy))
        d = ImageDraw.Draw(tile)
        for gx in range(20, pw, 48):
            d.line([(gx, 30), (gx, ph - 4)], fill=(230, 180, 180), width=1)
        for gy in range(30, ph, 48):
            d.line([(10, gy), (pw - 10, gy)], fill=(180, 180, 230), width=1)
        d.rectangle([0, 0, pw, 26], fill=(30, 34, 42))
        d.text((8, 5), f"angle={c['deg']:+.2f}deg | share={c['share']:.1%} | {c['src']}", fill=(255, 225, 110), font=font)
        panels.append(tile)
    sheet = Image.new("RGB", (pw * len(panels), ph), (240, 240, 240))
    for i, p in enumerate(panels):
        sheet.paste(p, (i * pw, 0))
    sheet, _ = _cap_image(sheet, MAX_IMAGE_SIDE)
    sheet.save(out_path)


def cmd_scan(args):
    src = Image.open(args.input).convert("RGB")
    gray = np.array(src.convert("L"))
    roi = [int(x) for x in args.roi.split(",")] if args.roi else _suggest_roi(gray)
    m1 = _grad_peaks(gray)
    m2 = _line_peaks(gray)
    cands = _merge_candidates(m1, m2, tol_deg=3.0, limit=3)

    os.makedirs(args.out, exist_ok=True)
    sheet_p = os.path.join(args.out, "scan_sheet.png")
    cand_p = os.path.join(args.out, "orient_candidates.png")
    meta_p = os.path.join(args.out, "scan_meta.json")
    _draw_scan_sheet(src, roi, sheet_p)
    _draw_orient_candidates(src, cands, roi, cand_p)
    data = {
        "source": os.path.abspath(args.input),
        "size": [src.width, src.height],
        "suggested_roi_src": roi,
        "candidates": cands,
    }
    with open(meta_p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"SCAN {src.width}x{src.height} -> {sheet_p} | {cand_p}")
    print(f"Suggested ROI (src px, confirm visually): {roi[0]},{roi[1]},{roi[2]},{roi[3]}")
    for i, c in enumerate(cands, 1):
        print(f"  Cand {i}: --angle {c['deg']:+.2f} | share={c['share']:.1%} | {c['src']}")
    return 0


def _refine_angle(src_gray: np.ndarray, init_deg: float, roi_src):
    x0, y0, x1, y1 = roi_src
    src_sub = src_gray[max(0, y0):min(src_gray.shape[0], y1), max(0, x0):min(src_gray.shape[1], x1)]
    raw_score = align_score(src_sub)

    best_deg, best_sc = init_deg, -1.0
    crop_img = Image.fromarray(src_sub, mode="L")
    for delta in np.linspace(-3.0, 3.0, 25):
        cand = init_deg + float(delta)
        rot_l, _, _ = _rotate_image(crop_img, cand, bg=248)
        sc = align_score(np.array(rot_l), deg_tol=1.0)
        if sc > best_sc:
            best_sc, best_deg = sc, cand
    # Fine pass +/-0.3 deg
    for delta in np.linspace(-0.3, 0.3, 13):
        cand = best_deg + float(delta)
        rot_l, _, _ = _rotate_image(crop_img, cand, bg=248)
        sc = align_score(np.array(rot_l), deg_tol=0.5)
        if sc > best_sc:
            best_sc, best_deg = sc, cand
    return best_deg, raw_score, best_sc


def _draw_roi_overlay(rot_img: Image.Image, roi_rot, scale_m_per_px, origin_rot, zoom: float):
    """Crop tightly with padding around `roi_rot`, dim pixels outside ROI, draw metric or pixel grid."""
    u0, v0, u1, v1 = [int(round(v)) for v in roi_rot]
    pad = 40
    c0, d0 = max(0, u0 - pad), max(0, v0 - pad)
    c1, d1 = min(rot_img.width, u1 + pad), min(rot_img.height, v1 + pad)
    crop = rot_img.crop((c0, d0, c1, d1)).convert("RGBA")

    # Dim outside-ROI margin softly while preserving context lines
    arr = np.array(crop, dtype=np.float32)
    mask = np.zeros((crop.height, crop.width), dtype=bool)
    mask[max(0, v0 - d0):max(0, v1 - d0), max(0, u0 - c0):max(0, u1 - c0)] = True
    arr[~mask, :3] = arr[~mask, :3] * 0.35 + 245.0 * 0.65
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")

    if zoom != 1.0:
        base = base.resize((int(round(base.width * zoom)), int(round(base.height * zoom))), Image.Resampling.LANCZOS)
    base, cap_s = _cap_image(base, MAX_IMAGE_SIDE)
    eff_z = zoom * cap_s
    w, h = base.size

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(12, min(w, h) // 55))

    if scale_m_per_px:
        s = float(scale_m_per_px)
        ox, oy = origin_rot
        x_min_m = (c0 - ox) * s
        x_max_m = (c1 - ox) * s
        y_min_m = (oy - d1) * s
        y_max_m = (oy - d0) * s
        xm0 = math.floor(x_min_m)
        xm1 = math.ceil(x_max_m)
        for xm in range(xm0, xm1 + 1):
            u_r = ox + xm / s
            px = int(round((u_r - c0) * eff_z))
            if 0 <= px < w:
                major = (xm % 5 == 0)
                col = (225, 35, 35, 175) if major else (240, 120, 120, 95)
                draw.line([(px, 0), (px, h)], fill=col, width=2 if major else 1)
                if major or xm % 2 == 0:
                    draw.text((px + 2, h - 18), f"{xm}m", fill=(190, 0, 0, 255), font=font)
                    draw.text((px + 2, 2), f"{xm}", fill=(190, 0, 0, 255), font=font)
        ym0 = math.floor(y_min_m)
        ym1 = math.ceil(y_max_m)
        for ym in range(ym0, ym1 + 1):
            v_r = oy - ym / s
            py = int(round((v_r - d0) * eff_z))
            if 0 <= py < h:
                major = (ym % 5 == 0)
                col = (35, 55, 225, 175) if major else (120, 140, 240, 95)
                draw.line([(0, py), (w, py)], fill=col, width=2 if major else 1)
                if major or ym % 2 == 0:
                    draw.text((3, max(0, py - 15)), f"{ym}m", fill=(0, 0, 200, 255), font=font)
                    if w > 520:
                        draw.text((w - 36, max(0, py - 15)), f"{ym}", fill=(0, 0, 200, 255), font=font)
    else:
        step, major = 50, 100
        for sx in range((c0 // step) * step, c1 + 1, step):
            px = int(round((sx - c0) * eff_z))
            if 0 <= px < w:
                is_maj = (sx % major == 0)
                col = (230, 50, 50, 140) if is_maj else (240, 140, 140, 85)
                draw.line([(px, 0), (px, h)], fill=col, width=1)
                if is_maj:
                    draw.text((px + 2, 2), str(sx), fill=(190, 0, 0, 255), font=font)
        for sy in range((d0 // step) * step, d1 + 1, step):
            py = int(round((sy - d0) * eff_z))
            if 0 <= py < h:
                is_maj = (sy % major == 0)
                col = (50, 50, 230, 140) if is_maj else (140, 140, 240, 85)
                draw.line([(0, py), (w, py)], fill=col, width=1)
                if is_maj:
                    draw.text((2, py + 2), str(sy), fill=(0, 0, 200, 255), font=font)

    # Outline ROI box in crisp green
    rx0, ry0 = int(round((u0 - c0) * eff_z)), int(round((v0 - d0) * eff_z))
    rx1, ry1 = int(round((u1 - c0) * eff_z)), int(round((v1 - d0) * eff_z))
    draw.rectangle([rx0, ry0, rx1, ry1], outline=(20, 165, 50, 220), width=2)
    return Image.alpha_composite(base, layer).convert("RGB")


def _draw_layers_image(rot_img: Image.Image, roi_rot, out_path: str):
    """Visualize thick walls (red), thin glazing/lines (blue), and dense hatch/louver ink (green) in ROI."""
    u0, v0, u1, v1 = [int(round(v)) for v in roi_rot]
    crop = rot_img.crop((max(0, u0), max(0, v0), min(rot_img.width, u1), min(rot_img.height, v1))).convert("L")
    gray = np.array(crop)
    _, dark, thick = _ink_and_thick_mask(gray)
    thin = dark & (~thick)
    # High-frequency hatch proxy: dark pixels with many nearby transitions
    p = np.pad(dark.astype(np.int16), 2, mode="edge")
    cnt = sum(p[2 + dy:p.shape[0] - 2 + dy or None, 2 + dx:p.shape[1] - 2 + dx or None]
              for dy in range(-2, 3) for dx in range(-2, 3))
    dense_thin = thin & (cnt >= 7) & (cnt <= 18)

    rgb = np.full((gray.shape[0], gray.shape[1], 3), 248, dtype=np.uint8)
    rgb[thin] = (40, 110, 235)
    rgb[dense_thin] = (30, 165, 65)
    rgb[thick] = (210, 40, 40)
    out = Image.fromarray(rgb, mode="RGB")
    out, _ = _cap_image(out, MAX_IMAGE_SIDE)
    out.save(out_path)


def cmd_build(args):
    src = Image.open(args.input).convert("RGB")
    src_gray = np.array(src.convert("L"))
    if args.roi:
        roi_src = [int(float(x)) for x in args.roi.split(",")]
    else:
        roi_src = _suggest_roi(src_gray)

    angle_deg = float(args.angle)
    raw_sc = align_score(src_gray, roi_src)
    if args.refine:
        angle_deg, raw_sc, _ = _refine_angle(src_gray, angle_deg, roi_src)

    rot_img, m_fwd, m_inv = _rotate_image(src, angle_deg)
    # Transform src ROI corners -> axis-aligned bbox in rotated space
    sx0, sy0, sx1, sy1 = roi_src
    corners_r = [_apply_affine(m_fwd, u, v) for u, v in ((sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1))]
    ru0 = max(0.0, min(p[0] for p in corners_r))
    rv0 = max(0.0, min(p[1] for p in corners_r))
    ru1 = min(float(rot_img.width), max(p[0] for p in corners_r))
    rv1 = min(float(rot_img.height), max(p[1] for p in corners_r))
    roi_rot = [round(ru0, 2), round(rv0, 2), round(ru1, 2), round(rv1, 2)]

    rot_gray = np.array(rot_img.convert("L"))
    rot_box_i = [int(math.floor(ru0)), int(math.floor(rv0)), int(math.ceil(ru1)), int(math.ceil(rv1))]
    rot_sc = align_score(rot_gray, rot_box_i)

    # Hard sign assertion: if significantly rotated (>3 deg), verify improvement or check opposite sign
    if abs(angle_deg) > 3.0:
        bad = (rot_sc + 0.02 < raw_sc)
        if not bad and rot_sc < 0.5:
            opp_img, _, _ = _rotate_image(src.crop(tuple(roi_src)), -angle_deg)
            opp_sc = align_score(np.array(opp_img.convert("L")))
            if opp_sc > rot_sc + 0.15:
                bad = True
        if bad:
            raise AssertionError(
                f"Rotation sign check FAILED: angle={angle_deg:+.2f}deg produced align={rot_sc:.3f} "
                f"(raw={raw_sc:.3f}). Remember angle_deg is visual CCW tilt; try negating angle."
            )

    os.makedirs(args.out, exist_ok=True)
    rot_out, rot_cap = _cap_image(rot_img, MAX_IMAGE_SIDE)
    rot_p = os.path.join(args.out, "plan_rot.png")
    rot_out.save(rot_p)

    if args.origin:
        origin_rot = [float(x) for x in args.origin.split(",")]
    else:
        origin_rot = [roi_rot[0], roi_rot[3]]  # ROI SW corner (+X East right, +Y North up)

    scale = float(args.scale) if args.scale else None
    roi_img = _draw_roi_overlay(rot_img, roi_rot, scale, origin_rot, float(args.zoom))
    roi_p = os.path.join(args.out, "plan_roi.png")
    roi_img.save(roi_p)

    layers_p = None
    if args.layers:
        layers_p = os.path.join(args.out, "plan_layers.png")
        _draw_layers_image(rot_img, roi_rot, layers_p)

    meta_p = os.path.join(args.out, "plan_meta.json")
    meta = {
        "source": os.path.abspath(args.input),
        "src_size": [src.width, src.height],
        "rot_size": [rot_img.width, rot_img.height],
        "plan_rot_save_scale": rot_cap,
        "angle_deg": round(angle_deg, 4),
        "roi_src": roi_src,
        "roi_rot": roi_rot,
        "M_src_to_rot": m_fwd,
        "M_rot_to_src": m_inv,
        "scale_m_per_px": scale,
        "origin_rot": origin_rot,
        "align_before": round(raw_sc, 4),
        "align_after": round(rot_sc, 4),
        "grid_unit": "meters" if scale else "rot_px",
    }
    with open(meta_p, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"BUILD angle={angle_deg:+.2f}deg | align {raw_sc:.3f} -> {rot_sc:.3f} | rot={rot_img.width}x{rot_img.height}")
    print(f"roi_rot={roi_rot} | grid={meta['grid_unit']} | scale={scale}")
    print(f"Outputs: {roi_p} | {rot_p} | {meta_p}" + (f" | {layers_p}" if layers_p else ""))
    return 0


def cmd_px2m(args):
    with open(args.meta, "r", encoding="utf-8") as f:
        meta = json.load(f)
    s = meta.get("scale_m_per_px")
    if not s:
        raise ValueError("scale_m_per_px is not set in plan_meta.json; run scale-from-section or pass --scale first.")
    ox, oy = meta["origin_rot"]
    for raw in args.pt:
        vals = [float(x) for x in raw.split(",")]
        if args.mode == "m2rot":
            ur, vr = ox + vals[0] / s, oy - vals[1] / s
            us, vs = _apply_affine(meta["M_rot_to_src"], ur, vr)
            print(f"m({vals[0]:.3f},{vals[1]:.3f}) -> rot({ur:.1f},{vr:.1f}) -> src({us:.1f},{vs:.1f})")
        elif args.from_rot or args.mode == "rot2m":
            ur, vr = vals
            xm, ym = (ur - ox) * s, (oy - vr) * s
            print(f"rot({ur:.1f},{vr:.1f}) -> m({xm:.3f},{ym:.3f})")
        else:
            ur, vr = _apply_affine(meta["M_src_to_rot"], vals[0], vals[1])
            xm, ym = (ur - ox) * s, (oy - vr) * s
            print(f"src({vals[0]:.1f},{vals[1]:.1f}) -> rot({ur:.1f},{vr:.1f}) -> m({xm:.3f},{ym:.3f})")
    return 0


def cmd_scale_from_section(args):
    with open(args.meta, "r", encoding="utf-8") as f:
        meta = json.load(f)
    span_m = float(args.section_scale) * float(args.section_span_px)
    u0, v0, u1, v1 = (float(x) for x in args.plan_span.split(","))
    if args.src_coords:
        p0 = _apply_affine(meta["M_src_to_rot"], u0, v0)
        p1 = _apply_affine(meta["M_src_to_rot"], u1, v1)
    else:
        p0, p1 = (u0, v0), (u1, v1)
    px_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if px_len <= 1e-6:
        raise ValueError("Zero plan span")
    s_plan = span_m / px_len
    meta["scale_m_per_px"] = round(s_plan, 6)
    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"Span={span_m:.3f}m / {px_len:.2f}px => plan scale_m_per_px = {s_plan:.6f}")
    print(f"Sanity anchors: 0.30m wall={0.30/s_plan:.1f}px | 0.90m door={0.90/s_plan:.1f}px | 3.0m bay={3.0/s_plan:.1f}px")
    if args.update_spec:
        import spec_kit as SK
        SK.spec_set("frame.scale_m_per_px", round(s_plan, 6), path=args.update_spec)
        SK.spec_set("frame.yaw_deg", meta["angle_deg"], path=args.update_spec)
        print(f"Updated spec: {args.update_spec}")
    return 0


def cmd_check_outline(args):
    import spec_kit as SK
    with open(args.meta, "r", encoding="utf-8") as f:
        meta = json.load(f)
    s = meta.get("scale_m_per_px")
    if not s:
        raise ValueError("scale_m_per_px unset in plan_meta.json")
    ox, oy = meta["origin_rot"]
    src = Image.open(meta["source"]).convert("L")
    rot_l, _, _ = _rotate_image(src, meta["angle_deg"], bg=248)
    gray = np.array(rot_l)
    _, dark, _ = _ink_and_thick_mask(gray)
    # Allow +/-3 px tolerance around spec edge line
    dark_tol = _morph3(_morph3(_morph3(dark, "dilate"), "dilate"), "dilate")

    spec = SK.spec_load(args.spec)
    edges = SK.outline_edges(args.level, spec)
    rules = [r for r in spec.get("edge_rules", []) if r.get("level") == args.level]

    non_solid_intervals = {e["id"]: [] for e in edges}
    for r in rules:
        k = r.get("kind", "SOLID")
        if k in ("OPEN", "GLAZED", "CANTILEVER"):
            for e, (a, b) in SK.match_rule_to_edges(r, edges):
                non_solid_intervals[e["id"]].append((a, b, k))

    h, w = dark_tol.shape
    low_edges = []
    solid_supports = []
    print(f"check-outline {args.level} ({len(edges)} edges):")
    for e in edges:
        x0, y0 = e["p0"]
        x1, y1 = e["p1"]
        u0, v0 = ox + x0 / s, oy - y0 / s
        u1, v1 = ox + x1 / s, oy - y1 / s
        px_len = math.hypot(u1 - u0, v1 - v0)
        n_pts = max(3, int(round(px_len / 3.0)) + 1)
        hits = 0
        for i in range(n_pts):
            t = i / (n_pts - 1)
            uu = int(round(u0 + t * (u1 - u0)))
            vv = int(round(v0 + t * (v1 - v0)))
            if 0 <= uu < w and 0 <= vv < h and dark_tol[vv, uu]:
                hits += 1
        sup = hits / n_pts
        # Determine if edge is majority covered by OPEN/GLAZED/CANTILEVER
        void_len = sum(b - a for a, b, _ in non_solid_intervals[e["id"]])
        is_void_edge = e["length"] > 0 and (void_len / e["length"]) > 0.45
        if not is_void_edge:
            solid_supports.append(sup)
        flag = "info(void/cant)" if is_void_edge else ("LOW!" if sup < 0.5 else "ok")
        if sup < 0.5 and not is_void_edge:
            low_edges.append(e["id"])
        if sup < 0.8 or is_void_edge:
            print(f"  {e['id']} {e['side']} len={e['length']:.2f}m support={sup:.2f} [{flag}]")
    mean_sup = float(np.mean(solid_supports)) if solid_supports else 1.0
    verdict = "PASS" if mean_sup >= 0.8 and not low_edges else "REVIEW"
    print(f"Mean solid-edge support={mean_sup:.3f} | low={low_edges} | verdict={verdict}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Floor-plan rotation, ROI dimming, metric grid & outline support check.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--input", required=True)
    p_scan.add_argument("--out", default="agy_work")
    p_scan.add_argument("--roi", default=None, help="Optional manual src ROI u0,v0,u1,v1")
    p_scan.set_defaults(func=cmd_scan)

    p_b = sub.add_parser("build")
    p_b.add_argument("--input", required=True)
    p_b.add_argument("--angle", required=True, type=float)
    p_b.add_argument("--roi", default=None, help="Source image ROI u0,v0,u1,v1")
    p_b.add_argument("--out", default="agy_work")
    p_b.add_argument("--refine", action="store_true")
    p_b.add_argument("--scale", type=float, default=None)
    p_b.add_argument("--origin", default=None, help="Origin in rotated px u,v (default ROI SW)")
    p_b.add_argument("--layers", action="store_true")
    p_b.add_argument("--zoom", type=float, default=1.0)
    p_b.set_defaults(func=cmd_build)

    p_p2m = sub.add_parser("px2m")
    p_p2m.add_argument("--meta", required=True)
    p_p2m.add_argument("--pt", action="append", required=True)
    p_p2m.add_argument("--from-rot", action="store_true")
    p_p2m.add_argument("--mode", choices=["auto", "src2m", "rot2m", "m2rot"], default="auto")
    p_p2m.set_defaults(func=cmd_px2m)

    p_sc = sub.add_parser("scale-from-section")
    p_sc.add_argument("--meta", required=True)
    p_sc.add_argument("--section-scale", required=True, type=float)
    p_sc.add_argument("--section-span-px", required=True, type=float)
    p_sc.add_argument("--plan-span", required=True, help="u0,v0,u1,v1")
    p_sc.add_argument("--src-coords", action="store_true")
    p_sc.add_argument("--update-spec", default=None)
    p_sc.set_defaults(func=cmd_scale_from_section)

    p_chk = sub.add_parser("check-outline")
    p_chk.add_argument("--meta", required=True)
    p_chk.add_argument("--spec", required=True)
    p_chk.add_argument("--level", required=True)
    p_chk.set_defaults(func=cmd_check_outline)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
