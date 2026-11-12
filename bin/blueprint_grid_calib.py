"""[BIN_GRID_CALIB] 红蓝双色半透明像素标尺网格 · 线性坐标标定 · 局部放大读图 (立面/剖面/轴测专用；平面图请用 plan_prep.py)
- 适用 (When): 【仅对立面/剖面/传统三视图/带尺寸轴测图有效；倾斜或带场地底图的平面图请用 bin/plan_prep.py；透视照片用 --crop/--zoom 读细部】
- 用法 (How) : python3 bin/blueprint_grid_calib.py --input <raw.png> --output <grid.png> [--step 50 --major 100 --known-mm 7730 --known-px 550 --crop u0,v0,u1,v1 --zoom 3]
- 产出 (Out) : 带红(X)蓝(Y)标尺的 PNG（默认半透明，不遮挡细线；标注永远为原图像素坐标）+ 可选比例尺 JSON；--crop/--zoom 输出局部放大图
"""

import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_grid_overlay(input_path: str, output_path: str, step: int = 50, major: int = 100,
                          alpha: float = 0.55, crop=None, zoom: float = 1.0, font_size: int = 0):
    """Draw the ruler grid in SOURCE-pixel coordinates. alpha<1 keeps thin drawing lines visible under the
    grid (the old opaque grid hid exactly the fine details we need to read). crop=(u0,v0,u1,v1) + zoom>1
    upsamples a region first; labels still read source pixels so measurements stay valid."""
    src = Image.open(input_path).convert("RGB")
    u0, v0, u1, v1 = crop if crop else (0, 0, src.width, src.height)
    u0, v0 = max(0, u0), max(0, v0)
    u1, v1 = min(src.width, u1), min(src.height, v1)
    img = src.crop((u0, v0, u1, v1))
    if zoom != 1.0:
        img = img.resize((int(round(img.width * zoom)), int(round(img.height * zoom))), Image.Resampling.LANCZOS)
    w, h = img.size
    base = img.convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fs = font_size or max(11, min(w, h) // 70)
    font = _font(fs)
    a = int(255 * max(0.0, min(1.0, alpha)))

    first_x = (u0 // step) * step
    for sx in range(first_x, u1 + 1, step):
        if sx < u0:
            continue
        x = int(round((sx - u0) * zoom))
        is_major = (sx % major == 0)
        color = (255, 60, 60, a) if is_major else (255, 150, 150, int(a * 0.8))
        draw.line([(x, 0), (x, h)], fill=color, width=1)
        if is_major:
            draw.text((x + 2, 2), str(sx), fill=(200, 0, 0, 255), font=font)
            if h > 300:
                draw.text((x + 2, h // 2), str(sx), fill=(200, 0, 0, 255), font=font)

    first_y = (v0 // step) * step
    for sy in range(first_y, v1 + 1, step):
        if sy < v0:
            continue
        y = int(round((sy - v0) * zoom))
        is_major = (sy % major == 0)
        color = (60, 60, 255, a) if is_major else (150, 150, 255, int(a * 0.8))
        draw.line([(0, y), (w, y)], fill=color, width=1)
        if is_major:
            draw.text((2, y + 2), str(sy), fill=(0, 0, 200, 255), font=font)
            if w > 720:
                draw.text((int(w * 0.68), y + 2), str(sy), fill=(0, 0, 200, 255), font=font)

    out = Image.alpha_composite(base, layer).convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    out.save(output_path)
    return w, h


def main():
    parser = argparse.ArgumentParser(description="Overlay pixel coordinate ruler grid on blueprint (optionally zoomed crop).")
    parser.add_argument("--input", required=True, help="Path to raw blueprint image.")
    parser.add_argument("--output", required=True, help="Path to output grid-overlaid PNG.")
    parser.add_argument("--step", type=int, default=50, help="Minor grid spacing in SOURCE pixels.")
    parser.add_argument("--major", type=int, default=100, help="Major grid spacing in SOURCE pixels.")
    parser.add_argument("--alpha", type=float, default=0.55, help="Grid opacity 0..1 (1.0 = legacy opaque lines).")
    parser.add_argument("--crop", default=None, help="Region 'u0,v0,u1,v1' (source px) to grid/zoom instead of the full image.")
    parser.add_argument("--zoom", type=float, default=1.0, help="Upsample factor for --crop (e.g. 3 to read fine details).")
    parser.add_argument("--font-size", type=int, default=0, help="Label font size (0 = auto).")
    parser.add_argument("--known-mm", type=float, default=None, help="Optional known reference length in mm.")
    parser.add_argument("--known-px", type=float, default=None, help="Optional pixel span for --known-mm.")
    parser.add_argument("--calib-json", default=None, help="Optional output path for calibration JSON.")
    args = parser.parse_args()

    crop = tuple(int(x) for x in args.crop.split(",")) if args.crop else None
    w, h = generate_grid_overlay(args.input, args.output, args.step, args.major, args.alpha, crop, args.zoom, args.font_size)
    with Image.open(args.input) as src:
        src_w, src_h = src.size
    info = {
        "input": os.path.abspath(args.input),
        "output": os.path.abspath(args.output),
        "source_width_px": src_w,
        "source_height_px": src_h,
        "output_width_px": w,
        "output_height_px": h,
        "step_px": args.step,
        "major_px": args.major,
    }
    if crop:
        info["grid_crop"] = list(crop)
        info["zoom"] = args.zoom
    if args.known_mm and args.known_px:
        m_per_px = (args.known_mm / 1000.0) / args.known_px
        info["scale_m_per_px"] = round(m_per_px, 8)
        info["scale_mm_per_px"] = round(m_per_px * 1000.0, 4)
        info["px_per_m"] = round(1.0 / m_per_px, 3)

    # Crops removed in v1.4 (use plan_prep.py for floor-plan ROI calibration)

    if args.calib_json:
        with open(args.calib_json, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

    print(f"Success! Blueprint grid ({w}x{h}) written to: {args.output}")


if __name__ == "__main__":
    main()
