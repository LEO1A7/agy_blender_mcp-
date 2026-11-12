"""[BIN_LEVEL_PLAN_RENDER] 楼层剖切轮廓与 Building Spec 蓝图叠合渲染器 (仅失败排障或终验出图)
- 适用 (When): G3/G5 中 `verify_levels` 未通过需要视觉定位偏移/缺失悬挑/洞口错误，或终验交付生成剖切平面图对账叠合图
- 用法 (How) : python3 bin/level_plan_render.py --cuts agy_work/level_cuts.json --spec agy_work/building_spec.json --level L1 [--plan plan_rot.png --meta plan_meta.json] --out agy_work/overlay_L1.png
- 产出 (Out) : 黑线剖切轮廓 + 蓝色虚线 spec 轮廓 + 红色编号差异斑块 PNG（长边<=1600px）；提供 meta 时直接仿射对位叠加到源平面图上
"""

import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_RECIPE_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "examples", "recipes"))
if _RECIPE_DIR not in sys.path:
    sys.path.insert(0, _RECIPE_DIR)

import spec_kit as SK  # noqa: E402

MAX_IMAGE_SIDE = 1600


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_dashed_line(draw, p0, p1, fill, width=2, dash=8):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 1.0:
        return
    steps = max(1, int(L // dash))
    for i in range(0, steps, 2):
        t0 = i / steps
        t1 = min(1.0, (i + 1) / steps)
        draw.line([(p0[0] + dx * t0, p0[1] + dy * t0), (p0[0] + dx * t1, p0[1] + dy * t1)], fill=fill, width=width)


def render_overlay(cuts_path, spec_path, level_id, out_path, plan_path=None, meta_path=None, verify_path=None):
    with open(cuts_path, "r", encoding="utf-8") as f:
        cuts = json.load(f)
    if "cuts" in cuts:
        cuts = cuts["cuts"]
    spec = SK.spec_load(spec_path)
    res = SK.resolve_outline(level_id, spec)
    cinfo = cuts.get(level_id, {"objects": {}, "z_cut": 0.0})

    vinfo = None
    if verify_path and os.path.exists(verify_path):
        with open(verify_path, "r", encoding="utf-8") as vf:
            vinfo = json.load(vf)
    else:
        cand_v = os.path.join(os.path.dirname(os.path.abspath(cuts_path)), f"verify_{level_id}.json")
        if os.path.exists(cand_v):
            with open(cand_v, "r", encoding="utf-8") as vf:
                vinfo = json.load(vf)

    if plan_path and meta_path:
        with open(meta_path, "r", encoding="utf-8") as mf:
            meta = json.load(mf)
        base = Image.open(plan_path).convert("RGBA")
        rot_scale = float(meta.get("plan_rot_save_scale", 1.0))
        ox, oy = meta["origin_rot"]
        s_m = float(meta["scale_m_per_px"])

        def m2px(xm, ym):
            return ((ox + xm / s_m) * rot_scale, (oy - ym / s_m) * rot_scale)
    else:
        bb = list(res["bbox"])
        all_pts = [p for obj in cinfo.get("objects", {}).values() for seg in obj["segs"] for p in seg]
        if all_pts:
            bb[0] = min(bb[0], min(p[0] for p in all_pts))
            bb[1] = min(bb[1], min(p[1] for p in all_pts))
            bb[2] = max(bb[2], max(p[0] for p in all_pts))
            bb[3] = max(bb[3], max(p[1] for p in all_pts))
        span_w = max(4.0, (bb[2] - bb[0]) + 2.4)
        span_h = max(4.0, (bb[3] - bb[1]) + 2.4)
        ppm = min(1400.0 / max(span_w, span_h), 120.0)
        W = max(400, int(round(span_w * ppm)))
        H = max(400, int(round(span_h * ppm)))
        base = Image.new("RGBA", (W, H), (248, 248, 246, 255))
        x_off = bb[0] - 1.2
        y_top = bb[3] + 1.2

        def m2px(xm, ym):
            return ((xm - x_off) * ppm, (y_top - ym) * ppm)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(13, min(base.size) // 48))

    # 1. Blue dashed spec rings
    for ring in res["outers"] + res["holes"]:
        for i in range(len(ring)):
            p0 = m2px(*ring[i])
            p1 = m2px(*ring[(i + 1) % len(ring)])
            _draw_dashed_line(draw, p0, p1, fill=(30, 85, 235, 220), width=3, dash=10)

    # 2. Black cut walls / sections
    for odata in cinfo.get("objects", {}).values():
        col = (10, 10, 10, 255) if odata.get("solid", True) else (80, 130, 160, 210)
        w_line = 3 if odata.get("solid", True) else 2
        for a, b in odata["segs"]:
            draw.line([m2px(*a), m2px(*b)], fill=col, width=w_line)

    # 3. Red numbered discrepancy patches
    if vinfo:
        for idx, p in enumerate(vinfo.get("patches", []), 1):
            x0, y0, x1, y1 = p["bbox"]
            pa = m2px(x0, y1)
            pb = m2px(x1, y0)
            rx0, ry0, rx1, ry1 = min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1])
            draw.rectangle([rx0, ry0, rx1, ry1], fill=(235, 40, 40, 65), outline=(225, 20, 20, 245), width=3)
            draw.text((rx0 + 4, max(2, ry0 - 16)), f"#{idx} {p['kind']} {p['area_m2']}m2", fill=(200, 0, 0, 255), font=font)

    out_img = Image.alpha_composite(base, layer).convert("RGB")
    if max(out_img.size) > MAX_IMAGE_SIDE:
        s = MAX_IMAGE_SIDE / float(max(out_img.size))
        out_img = out_img.resize((int(round(out_img.width * s)), int(round(out_img.height * s))), Image.Resampling.LANCZOS)

    # Header bar
    d_fin = ImageDraw.Draw(out_img)
    iou_s = f"IoU={vinfo['iou']:.3f}" if vinfo else ""
    d_fin.rectangle([0, 0, out_img.width, 26], fill=(28, 32, 40))
    d_fin.text((8, 5), f"{level_id} @ z_cut={cinfo.get('z_cut',0):.2f}m {iou_s} | black=cut  blue=spec  red=diff",
               fill=(255, 230, 120), font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    out_img.save(out_path)
    return out_img.size


def main():
    ap = argparse.ArgumentParser(description="Overlay level geometric cuts onto spec outline / leveled plan.")
    ap.add_argument("--cuts", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--level", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--meta", default=None)
    ap.add_argument("--verify", default=None)
    args = ap.parse_args()
    w, h = render_overlay(args.cuts, args.spec, args.level, args.out, args.plan, args.meta, args.verify)
    print(f"Overlay {args.level} ({w}x{h}) -> {args.out}")


if __name__ == "__main__":
    main()
