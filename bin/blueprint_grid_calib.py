#!/usr/bin/env python3
"""
blueprint_grid_calib.py — Overlays a dual-color pixel coordinate ruler grid onto an input
blueprint image and optionally computes real-world scale & view crop calibration JSON.
"""

import argparse
import json
import os
from PIL import Image, ImageDraw


def generate_grid_overlay(input_path: str, output_path: str, step: int = 50, major: int = 100):
    img = Image.open(input_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Vertical grid lines (X_px in red)
    for x in range(0, w, step):
        is_major = (x % major == 0)
        color = (255, 75, 75) if is_major else (255, 185, 185)
        draw.line([(x, 0), (x, h)], fill=color, width=1)
        if is_major:
            draw.text((x + 2, 2), str(x), fill=(200, 0, 0))
            if h > 300:
                draw.text((x + 2, h // 2), str(x), fill=(200, 0, 0))

    # Horizontal grid lines (Y_px in blue)
    for y in range(0, h, step):
        is_major = (y % major == 0)
        color = (75, 75, 255) if is_major else (185, 185, 255)
        draw.line([(0, y), (w, y)], fill=color, width=1)
        draw.text((2, y + 2), str(y), fill=(0, 0, 200))
        if w > 720:
            draw.text((int(w * 0.68), y + 2), str(y), fill=(0, 0, 200))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path)
    return w, h


def main():
    parser = argparse.ArgumentParser(description="Overlay pixel coordinate ruler grid on blueprint.")
    parser.add_argument("--input", required=True, help="Path to raw blueprint image.")
    parser.add_argument("--output", required=True, help="Path to output grid-overlaid PNG.")
    parser.add_argument("--step", type=int, default=50, help="Minor grid spacing in pixels.")
    parser.add_argument("--major", type=int, default=100, help="Major grid spacing in pixels.")
    parser.add_argument("--known-mm", type=float, default=None, help="Optional known reference length in mm.")
    parser.add_argument("--known-px", type=float, default=None, help="Optional pixel span for --known-mm.")
    parser.add_argument("--side-crop", default=None, help="Optional Side view crop box 'u0,v0,u1,v1'.")
    parser.add_argument("--top-crop", default=None, help="Optional Top view crop box 'u0,v0,u1,v1'.")
    parser.add_argument("--front-crop", default=None, help="Optional Front view crop box 'u0,v0,u1,v1'.")
    parser.add_argument("--calib-json", default=None, help="Optional output path for calibration JSON.")
    args = parser.parse_args()

    w, h = generate_grid_overlay(args.input, args.output, args.step, args.major)
    info = {
        "input": os.path.abspath(args.input),
        "output": os.path.abspath(args.output),
        "width_px": w,
        "height_px": h,
        "step_px": args.step,
        "major_px": args.major,
    }
    if args.known_mm and args.known_px:
        m_per_px = (args.known_mm / 1000.0) / args.known_px
        info["scale_m_per_px"] = round(m_per_px, 8)
        info["scale_mm_per_px"] = round(m_per_px * 1000.0, 4)
        info["px_per_m"] = round(1.0 / m_per_px, 3)

    crops = {}
    for k, val in [("side", args.side_crop), ("top", args.top_crop), ("front", args.front_crop)]:
        if val:
            crops[k] = [int(x.strip()) for x in val.split(",")]
    if crops:
        info["view_crops"] = crops

    if args.calib_json:
        with open(args.calib_json, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

    print(f"Success! Blueprint grid ({w}x{h}) written to: {args.output}")


if __name__ == "__main__":
    main()
