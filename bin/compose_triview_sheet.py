#!/usr/bin/env python3
"""
compose_triview_sheet.py — Unified Stage 4 Visual Verification Compositor:
  Mode A (Multi-View Sheet): Stitches Blender's rendered Side, Top, Front, and Front/Rear
         Isometric views into a unified engineering verification sheet.
  Mode B (1:1 Side-by-Side 3-Column Verifier): Given a raw blueprint, crop box `u0,v0,u1,v1`,
         and a 1:1 orthographic RGBA render, generates:
         `[ 1:1 Blueprint Crop | 1:1 Solid Render | 1:1 Edge Contour ]`
         with continuous horizontal datum reference lines (no muddy alpha overlay).
"""

import argparse
import os
import numpy as np
from PIL import Image, ImageDraw


def extract_alpha_edge_contour(rgba_img: Image.Image) -> Image.Image:
    """Extracts crisp 1px morphological silhouette/edge contour from an RGBA render using pure numpy."""
    arr = np.array(rgba_img.convert("RGBA"))
    mask = arr[:, :, 3] > 20
    # 4-connected morphological dilation in pure numpy (no scipy dependency required)
    dilated = mask.copy()
    dilated[1:, :] |= mask[:-1, :]
    dilated[:-1, :] |= mask[1:, :]
    dilated[:, 1:] |= mask[:, :-1]
    dilated[:, :-1] |= mask[:, 1:]
    edge = dilated ^ mask

    h, w = mask.shape
    out = np.full((h, w, 3), 245, dtype=np.uint8)
    out[edge] = [20, 22, 30]
    return Image.fromarray(out)


def compose_1to1_side_by_side(
    blueprint_path: str,
    crop_box: tuple,
    render_path: str,
    output_path: str,
    view_label: str = "VIEW",
):
    """
    Generates a 3-column 1:1 pixel-aligned comparison sheet:
    [ 1:1 Blueprint Crop | 1:1 Solid/Diagnostic Render | 1:1 Edge Contour ]
    with continuous horizontal datum lines at 25%, 50%, 75% height.
    """
    bp = Image.open(blueprint_path).convert("RGB")
    ref_crop = bp.crop(crop_box)
    w_px, h_px = ref_crop.size

    solid_rgba = Image.open(render_path).convert("RGBA")
    if solid_rgba.size != (w_px, h_px):
        solid_rgba = solid_rgba.resize((w_px, h_px), Image.Resampling.LANCZOS)

    solid_bg = Image.new("RGB", (w_px, h_px), (40, 44, 52))
    solid_bg.paste(solid_rgba, (0, 0), solid_rgba)

    contour_img = extract_alpha_edge_contour(solid_rgba)

    header_h = 32
    sheet_w = w_px * 3 + 24
    sheet_h = h_px + header_h + 8
    sheet = Image.new("RGB", (sheet_w, sheet_h), (20, 22, 26))

    sheet.paste(ref_crop, (6, header_h))
    sheet.paste(solid_bg, (w_px + 12, header_h))
    sheet.paste(contour_img, (w_px * 2 + 18, header_h))

    draw = ImageDraw.Draw(sheet)
    draw.text((10, 8), f"[1] BLUEPRINT {view_label.upper()} (1:1 CROP)", fill=(230, 230, 230))
    draw.text((w_px + 16, 8), f"[2] 1:1 RENDER {view_label.upper()} (NO BLUR)", fill=(110, 210, 255))
    draw.text((w_px * 2 + 22, 8), f"[3] 1:1 EDGE CONTOUR {view_label.upper()}", fill=(255, 190, 90))

    for y_frac in (0.25, 0.50, 0.75):
        y_pos = int(header_h + h_px * y_frac)
        draw.line([(0, y_pos), (sheet_w, y_pos)], fill=(75, 85, 120), width=1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sheet.save(output_path)
    return sheet_w, sheet_h


def compose_sheet(
    side_path: str,
    top_path: str,
    front_path: str,
    iso_path: str,
    output_path: str,
    iso_rear_path: str = None,
):
    """Stitches Side, Top, Front, and Isometric renders into a unified multi-view sheet."""
    side = Image.open(side_path).convert("RGB")
    top = Image.open(top_path).convert("RGB")
    front = Image.open(front_path).convert("RGB")
    iso = Image.open(iso_path).convert("RGB")

    pad = 10
    left_w = max(side.width, top.width)
    right_w = front.width
    total_w = pad + left_w + pad + right_w + pad
    total_h = pad + side.height + pad + top.height + pad

    canvas = Image.new("RGB", (total_w, total_h), (240, 240, 238))
    canvas.paste(side, (pad, pad))
    canvas.paste(top, (pad, pad + side.height + pad))
    canvas.paste(front, (pad + left_w + pad, pad))

    if iso_rear_path and os.path.isfile(iso_rear_path):
        iso_rear = Image.open(iso_rear_path).convert("RGB")
        half_w = (right_w - pad) // 2
        h1 = int(iso.height * (half_w / iso.width))
        h2 = int(iso_rear.height * (half_w / iso_rear.width))
        iso_r1 = iso.resize((half_w, h1), Image.Resampling.LANCZOS)
        iso_r2 = iso_rear.resize((half_w, h2), Image.Resampling.LANCZOS)
        iso_y = max(pad + front.height + pad, total_h - pad - max(h1, h2))
        canvas.paste(iso_r1, (pad + left_w + pad, iso_y))
        canvas.paste(iso_r2, (pad + left_w + pad + half_w + pad, iso_y))
    else:
        iso_target_w = right_w
        iso_target_h = int(iso.height * (iso_target_w / iso.width))
        iso_resized = iso.resize((iso_target_w, iso_target_h), Image.Resampling.LANCZOS)
        iso_y = total_h - pad - iso_target_h
        canvas.paste(iso_resized, (pad + left_w + pad, max(pad + front.height + pad, iso_y)))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path)
    return total_w, total_h


def main():
    parser = argparse.ArgumentParser(description="Compose multi-view or 1:1 side-by-side verification sheets.")
    parser.add_argument("--side", help="Path to rendered Side view PNG.")
    parser.add_argument("--top", help="Path to rendered Top view PNG.")
    parser.add_argument("--front", help="Path to rendered Front view PNG.")
    parser.add_argument("--iso", help="Path to rendered Front-Isometric view PNG.")
    parser.add_argument("--iso-rear", default=None, help="Optional path to rendered Rear-Isometric view PNG.")
    parser.add_argument("--blueprint", default=None, help="Mode B: Path to original blueprint image for 1:1 side-by-side.")
    parser.add_argument("--crop", default=None, help="Mode B: Blueprint crop box 'u0,v0,u1,v1'.")
    parser.add_argument("--render", default=None, help="Mode B: Path to 1:1 orthographic RGBA render PNG.")
    parser.add_argument("--view-label", default="SIDE", help="Mode B: View label (SIDE/TOP/FRONT).")
    parser.add_argument("--output", required=True, help="Output composite PNG path.")
    args = parser.parse_args()

    if args.blueprint and args.crop and args.render:
        crop_box = tuple(int(x.strip()) for x in args.crop.split(","))
        w, h = compose_1to1_side_by_side(args.blueprint, crop_box, args.render, args.output, args.view_label)
        print(f"Success! 1:1 Side-by-Side 3-column sheet ({w}x{h}) written to: {args.output}")
    elif args.side and args.top and args.front and args.iso:
        w, h = compose_sheet(args.side, args.top, args.front, args.iso, args.output, args.iso_rear)
        print(f"Success! Multi-view composite sheet ({w}x{h}) written to: {args.output}")
    else:
        parser.error("Provide either (--side --top --front --iso) OR (--blueprint --crop --render).")


if __name__ == "__main__":
    main()
