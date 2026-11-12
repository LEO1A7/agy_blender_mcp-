"""[BIN_SECTION_LEVELS] 建筑剖面/立面楼板带检测 · 最小二乘标高比例解算 · Spec Levels 自动生成
- 适用 (When): P1 读取建筑剖面图，自动定位水平楼板黑带并结合已知层标高最小二乘反推 `scale_m_per_px` 与每层 FFL/板厚
- 用法 (How) : python3 bin/section_levels.py --input section.png [--xrange u0,u1 --elev "0.04,3.22,6.37,9.52" --drop v --mark out.png]
- 产出 (Out) : <=20 行标高/比例摘要、拟合残差(mm)、可直接写入 spec 的 `levels` JSON（多带歧义时列出候选 v 供 `--drop` 剔除）
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MAX_IMAGE_SIDE = 1600


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _max_dark_run(row_bool: np.ndarray, bridge_gap: int = 3) -> int:
    """Longest continuous True run in 1D bool array after closing tiny gaps <= bridge_gap."""
    r = row_bool.copy()
    if bridge_gap > 0 and len(r) > bridge_gap * 2:
        # Simple 1D dilation then erosion of radius `bridge_gap//2 + 1` or gap fill
        n = len(r)
        # Fill False gaps up to bridge_gap between Trues
        idx = np.where(r)[0]
        if len(idx) >= 2:
            diffs = np.diff(idx)
            for k, d in enumerate(diffs):
                if 1 < d <= bridge_gap + 1:
                    r[idx[k]:idx[k + 1] + 1] = True
    # Run lengths via diff
    padded = np.concatenate(([False], r, [False]))
    changes = np.diff(padded.astype(np.int8))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    if len(starts) == 0:
        return 0
    return int(np.max(ends - starts))


def detect_slab_bands(img_path: str, xrange=None, thresh: float = 0.35, drop=()):
    """Detect horizontal structural slab bands in section/elevation drawing."""
    src = Image.open(img_path).convert("L")
    g = np.array(src, dtype=np.float32)
    h, w = g.shape
    u0, u1 = xrange if xrange else (max(2, int(0.03 * w)), min(w - 2, int(0.97 * w)))
    u0, u1 = max(0, u0), min(w, u1)
    sub = g[:, u0:u1]
    med = float(np.median(sub))
    dark = sub < min(140.0, med * 0.62)

    scores = np.zeros(h, dtype=np.float64)
    # Ignore outermost 3% top/bottom frame lines
    my = max(2, int(0.03 * h))
    for v in range(my, h - my):
        row = dark[v]
        run = _max_dark_run(row, bridge_gap=4)
        cnt = int(np.sum(row))
        scores[v] = run * 0.75 + cnt * 0.25

    max_sc = float(np.max(scores))
    if max_sc <= 1e-3:
        return [], (w, h), (u0, u1)

    active = scores >= (max_sc * thresh)
    bands = []
    v = 0
    while v < h:
        if not active[v]:
            v += 1
            continue
        v0 = v
        while v + 1 < h and (active[v + 1] or (v + 3 < h and np.any(active[v + 1:v + 4]))):
            v += 1
        v1 = v
        sv = scores[v0:v1 + 1]
        weights = np.maximum(sv, 1e-6)
        vc = float(np.sum(np.arange(v0, v1 + 1) * weights) / np.sum(weights))
        bands.append({
            "v0": int(v0),
            "v1": int(v1),
            "v_center": round(vc, 2),
            "thickness_px": int(v1 - v0 + 1),
            "peak_score": round(float(np.max(sv)), 1),
        })
        v += 1

    # Filter out user `--drop` peaks
    drops = [float(d) for d in (drop or ())]
    if drops:
        kept = []
        for b in bands:
            if any((b["v0"] - 8 <= dv <= b["v1"] + 8) or abs(b["v_center"] - dv) <= 10.0 for dv in drops):
                continue
            kept.append(b)
        bands = kept

    # Sort bottom-to-top (decreasing v, increasing elevation Z)
    bands.sort(key=lambda b: -b["v_center"])
    return bands, (w, h), (u0, u1)


def fit_levels_scale(bands_bottom_up, elevs_asc):
    """Least-squares fit of `z = z0 + scale * (-v)` across matched bands & elevations."""
    vs = np.array([-b["v_center"] for b in bands_bottom_up], dtype=np.float64)
    zs = np.array(elevs_asc, dtype=np.float64)
    if len(vs) < 2:
        raise ValueError("Need at least 2 matched levels to compute scale.")
    A = np.vstack([vs, np.ones_like(vs)]).T
    slope, intercept = np.linalg.lstsq(A, zs, rcond=None)[0]
    scale = float(slope)
    if scale <= 0:
        raise ValueError(f"Non-positive fitted scale {scale:.6f}; check --elev order (bottom-to-top).")
    preds = slope * vs + intercept
    res_mm = [(float(z - p) * 1000.0) for z, p in zip(zs, preds)]
    levels = []
    for idx, (b, z_given) in enumerate(zip(bands_bottom_up, zs)):
        slab_m = round(max(0.18, min(0.60, b["thickness_px"] * scale)), 3)
        is_top = (idx == len(zs) - 1)
        levels.append({
            "id": f"L{idx}",
            "z": round(float(z_given), 3),
            "slab": slab_m,
            "cut": 1.0 if is_top else 1.5,
            "_v_px": b["v_center"],
        })
    return {
        "scale_m_per_px": round(scale, 6),
        "residuals_mm": [round(r, 1) for r in res_mm],
        "max_residual_mm": round(float(max(abs(r) for r in res_mm)), 1),
        "levels": levels,
    }


def _draw_mark(img_path: str, bands, xrange, out_path: str, fit_res=None):
    src = Image.open(img_path).convert("RGB")
    w, h = src.size
    scale = min(1.0, MAX_IMAGE_SIDE / max(w, h))
    if scale < 1.0:
        src = src.resize((int(round(w * scale)), int(round(h * scale))), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(src)
    font = _font(max(12, src.height // 45))
    ux0, ux1 = int(round(xrange[0] * scale)), int(round(xrange[1] * scale))
    draw.line([(ux0, 0), (ux0, src.height)], fill=(60, 180, 60), width=1)
    draw.line([(ux1, 0), (ux1, src.height)], fill=(60, 180, 60), width=1)
    lv_map = {lv["_v_px"]: lv for lv in (fit_res["levels"] if fit_res else [])}
    for i, b in enumerate(bands):
        vc = b["v_center"]
        py = int(round(vc * scale))
        draw.line([(ux0, py), (ux1, py)], fill=(230, 40, 40), width=2)
        lv = lv_map.get(vc)
        txt = f"#{i} v={vc:.1f} t={b['thickness_px']}px" + (f" -> {lv['id']} z={lv['z']}" if lv else "")
        draw.text((ux0 + 6, max(2, py - 16)), txt, fill=(210, 0, 0), font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    src.save(out_path)


def main():
    ap = argparse.ArgumentParser(description="Detect horizontal floor slab bands in architectural sections.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--xrange", default=None, help="Horizontal scan range u0,u1 (px)")
    ap.add_argument("--elev", default=None, help="Comma-separated FFL elevations in meters, ascending (e.g. 0.04,3.22,6.37,9.52)")
    ap.add_argument("--drop", action="append", type=float, default=[], help="Drop spurious band at v pixel (repeatable)")
    ap.add_argument("--thresh", type=float, default=0.35, help="Detection threshold fraction 0..1 (default 0.35)")
    ap.add_argument("--mark", default=None, help="Optional annotated PNG output")
    ap.add_argument("--out-json", default=None, help="Optional JSON output path")
    args = ap.parse_args()

    xr = tuple(int(float(x)) for x in args.xrange.split(",")) if args.xrange else None
    bands, (w, h), xr_used = detect_slab_bands(args.input, xrange=xr, thresh=args.thresh, drop=args.drop)

    elevs = sorted(float(x) for x in args.elev.split(",")) if args.elev else None
    fit_res = None
    ambiguous = False
    if elevs is not None:
        if len(bands) != len(elevs):
            ambiguous = True
        else:
            fit_res = fit_levels_scale(bands, elevs)

    if args.mark:
        _draw_mark(args.input, bands, xr_used, args.mark, fit_res=fit_res)

    payload = {
        "source": os.path.abspath(args.input),
        "size": [w, h],
        "xrange": list(xr_used),
        "bands_bottom_up": bands,
        "ambiguous": ambiguous,
        "fit": fit_res,
    }
    if args.out_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_json)), exist_ok=True)
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    if ambiguous:
        print(f"AMBIGUOUS: detected {len(bands)} slab bands vs {len(elevs)} elevations. Re-run with --drop <v> or --xrange:")
        for i, b in enumerate(bands):
            print(f"  Band {i} (bottom->up): v={b['v_center']}px [{b['v0']}..{b['v1']}] thick={b['thickness_px']}px score={b['peak_score']}")
        sys.exit(2)

    print(f"SECTION {w}x{h} xrange={xr_used} -> {len(bands)} slab bands detected")
    for i, b in enumerate(bands):
        print(f"  Band {i}: v={b['v_center']}px thick={b['thickness_px']}px")
    if fit_res:
        clean_levels = [{k: v for k, v in lv.items() if not k.startswith("_")} for lv in fit_res["levels"]]
        print(f"Fitted scale_m_per_px = {fit_res['scale_m_per_px']:.6f} (residuals_mm={fit_res['residuals_mm']})")
        print("Spec levels:", json.dumps(clean_levels, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
