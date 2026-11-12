"""[BIN_COMPOSE_SHEET] Stage 4 多视图总览 · 任意面板网格 · 1:1 蓝图/渲染/边缘/叠加 对账合成器
- 适用 (When): 渲染后对账——总览拼图(Mode A) | 任意多机位带标签网格(`--panel LABEL=PATH`) | 1:1 蓝图裁剪+渲染+边缘轮廓[+红色叠加]对比(Mode B, 含内部细节边缘)
- 用法 (How) : python3 bin/compose_triview_sheet.py --side s.png --top t.png --front f.png --iso i.png --output sheet.png | --panel Front=f.png --panel Iso=i.png --output g.png | --blueprint bp.png --crop u0,v0,u1,v1 --render r.png [--overlay] --output b.png
- 产出 (Out) : 带标签总览 PNG / 网格 PNG / 三列(或四列含叠加)1:1 核验 PNG；尺寸/比例不符时在图头与终端给出 ASPECT MISMATCH 告警（不再静默拉伸）
"""

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)       # Pillow >= 10.1: scalable default font
    except TypeError:
        return ImageFont.load_default()


def foreground_mask(img: Image.Image, bg_tol: int = 24) -> np.ndarray:
    """Boolean object mask of a render.

    Uses real alpha when the render is transparent; for opaque renders (the default Workbench studio has
    film_transparent=False) it falls back to colour distance from the dominant border colour. The old
    alpha-only logic returned an all-True mask for opaque renders => a completely BLANK contour column.
    """
    arr = np.array(img.convert("RGBA")).astype(np.int16)
    alpha = arr[:, :, 3]
    if alpha.min() < 250:
        return alpha > 20
    border = np.concatenate([arr[0, :, :3], arr[-1, :, :3], arr[:, 0, :3], arr[:, -1, :3]])
    vals, counts = np.unique(border.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[counts.argmax()]
    return np.abs(arr[:, :, :3] - bg).sum(axis=2) > bg_tol


def _dilate4(mask: np.ndarray) -> np.ndarray:
    d = mask.copy()
    d[1:, :] |= mask[:-1, :]
    d[:-1, :] |= mask[1:, :]
    d[:, 1:] |= mask[:, :-1]
    d[:, :-1] |= mask[:, 1:]
    return d


def edge_maps(img: Image.Image, internal_thresh: float = 28.0):
    """Return (silhouette_edge, internal_edge) boolean maps (pure numpy, no scipy)."""
    mask = foreground_mask(img)
    sil = _dilate4(mask) ^ mask
    gray = np.array(img.convert("L")).astype(np.float32)
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    mag = np.hypot(gx, gy) * 0.5
    internal = (mag > internal_thresh) & mask & ~sil
    return sil, internal


def extract_edge_contour(img: Image.Image, internal: bool = True) -> Image.Image:
    """White sheet; silhouette in near-black, internal detail edges (flanges, slats, mullions) in blue-grey."""
    sil, inner = edge_maps(img)
    h, w = sil.shape
    out = np.full((h, w, 3), 245, dtype=np.uint8)
    if internal:
        out[inner] = [95, 110, 150]
    out[sil] = [20, 22, 30]
    return Image.fromarray(out)


def extract_alpha_edge_contour(rgba_img: Image.Image) -> Image.Image:
    """Backward-compatible alias (silhouette only) — now works for opaque renders as well."""
    return extract_edge_contour(rgba_img, internal=False)


def _fit_letterbox(img: Image.Image, size, fill):
    """Resize preserving aspect into `size`, letterboxing; returns (image, aspect_mismatch_bool)."""
    w, h = size
    if img.size == (w, h):
        return img, False
    ar_src, ar_dst = img.width / img.height, w / h
    mismatch = abs(ar_src - ar_dst) / ar_dst > 0.01
    scale = min(w / img.width, h / img.height)
    nw, nh = max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale)))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new(img.mode, (w, h), fill)
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas, mismatch


def compose_1to1_side_by_side(
    blueprint_path: str,
    crop_box: tuple,
    render_path: str,
    output_path: str,
    view_label: str = "VIEW",
    overlay: bool = False,
):
    """
    Generates a 3-column (4 with `overlay`) 1:1 pixel-aligned comparison sheet:
    [ Blueprint crop | Render | Edge contour (silhouette + internal edges) | (Blueprint + red render edges) ]
    with continuous horizontal datum lines at 25%, 50%, 75% height.
    """
    bp = Image.open(blueprint_path).convert("RGB")
    ref_crop = bp.crop(crop_box)
    w_px, h_px = ref_crop.size

    render = Image.open(render_path).convert("RGBA")
    render_fit, mismatch = _fit_letterbox(render, (w_px, h_px), (240, 240, 238, 255))
    if mismatch:
        print(f"WARNING: ASPECT MISMATCH render {render.size} vs blueprint crop {(w_px, h_px)} — render letterboxed, "
              f"NOT stretched. Re-render at the crop resolution (render_views does this when scale+crops are set).")

    render_rgb = render_fit.convert("RGB")
    contour_img = extract_edge_contour(render_fit, internal=True)

    n_cols = 4 if overlay else 3
    header_h = 32
    sheet_w = w_px * n_cols + 6 * (n_cols + 1)
    sheet_h = h_px + header_h + 8
    sheet = Image.new("RGB", (sheet_w, sheet_h), (20, 22, 26))

    xs = [6 + i * (w_px + 6) for i in range(n_cols)]
    sheet.paste(ref_crop, (xs[0], header_h))
    sheet.paste(render_rgb, (xs[1], header_h))
    sheet.paste(contour_img, (xs[2], header_h))
    if overlay:
        sil, inner = edge_maps(render_fit)
        base = np.array(ref_crop).astype(np.float32)
        red = np.array([255, 30, 30], dtype=np.float32)
        m = _dilate4(sil) | inner
        base[m] = base[m] * 0.25 + red * 0.75
        sheet.paste(Image.fromarray(base.astype(np.uint8)), (xs[3], header_h))

    draw = ImageDraw.Draw(sheet)
    f = _font(14)
    lab = view_label.upper()
    draw.text((xs[0] + 4, 8), f"[1] BLUEPRINT {lab} (1:1 CROP)", fill=(230, 230, 230), font=f)
    draw.text((xs[1] + 4, 8), f"[2] RENDER {lab}" + ("  !ASPECT" if mismatch else ""), fill=(110, 210, 255), font=f)
    draw.text((xs[2] + 4, 8), f"[3] EDGES {lab} (dark=silhouette, blue=internal)", fill=(255, 190, 90), font=f)
    if overlay:
        draw.text((xs[3] + 4, 8), f"[4] OVERLAY {lab} (red=render edges)", fill=(255, 120, 120), font=f)

    for y_frac in (0.25, 0.50, 0.75):
        y_pos = int(header_h + h_px * y_frac)
        draw.line([(0, y_pos), (sheet_w, y_pos)], fill=(75, 85, 120), width=1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sheet.save(output_path)
    return sheet_w, sheet_h


def _label(img: Image.Image, text: str, size: int = 18) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    f = _font(size)
    tw = d.textlength(text, font=f)
    d.rectangle([4, 4, 12 + tw, 10 + size], fill=(25, 28, 36))
    d.text((8, 6), text, fill=(240, 240, 240), font=f)
    return out


def compose_grid(panels, output_path: str, cols: int = 3, cell_w: int = 900):
    """Arbitrary labelled panels -> grid (all cells scaled to the same width; heights padded)."""
    cells = []
    for label, path in panels:
        im = Image.open(path).convert("RGB")
        h = int(round(im.height * cell_w / im.width))
        cells.append(_label(im.resize((cell_w, h), Image.Resampling.LANCZOS), label))
    pad = 10
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    row_h = [max(c.height for c in r) for r in rows]
    W = pad + cols * (cell_w + pad)
    H = pad + sum(row_h) + pad * len(rows)
    canvas = Image.new("RGB", (W, H), (240, 240, 238))
    y = pad
    for r, rh in zip(rows, row_h):
        for k, c in enumerate(r):
            canvas.paste(c, (pad + k * (cell_w + pad), y))
        y += rh + pad
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path)
    return W, H


def compose_sheet(
    side_path: str,
    top_path: str,
    front_path: str,
    iso_path: str,
    output_path: str,
    iso_rear_path: str = None,
):
    """Stitches Side, Top, Front, and Isometric renders into one labelled multi-view sheet
    (canvas height = the taller of the two columns, so nothing is clipped)."""
    side = _label(Image.open(side_path).convert("RGB"), "SIDE")
    top = _label(Image.open(top_path).convert("RGB"), "TOP")
    front = _label(Image.open(front_path).convert("RGB"), "FRONT")
    iso = Image.open(iso_path).convert("RGB")

    pad = 10
    left_w = max(side.width, top.width)
    right_w = front.width
    left_h = pad + side.height + pad + top.height + pad

    if iso_rear_path and os.path.isfile(iso_rear_path):
        iso_rear = Image.open(iso_rear_path).convert("RGB")
        half_w = (right_w - pad) // 2
        isos = [_label(iso.resize((half_w, int(iso.height * half_w / iso.width)), Image.Resampling.LANCZOS), "ISO FRONT"),
                _label(iso_rear.resize((half_w, int(iso_rear.height * half_w / iso_rear.width)), Image.Resampling.LANCZOS), "ISO REAR")]
        iso_h = max(i.height for i in isos)
    else:
        isos = [_label(iso.resize((right_w, int(iso.height * right_w / iso.width)), Image.Resampling.LANCZOS), "ISO")]
        iso_h = isos[0].height
    right_h = pad + front.height + pad + iso_h + pad

    total_w = pad + left_w + pad + right_w + pad
    total_h = max(left_h, right_h)
    canvas = Image.new("RGB", (total_w, total_h), (240, 240, 238))
    canvas.paste(side, (pad, pad))
    canvas.paste(top, (pad, pad + side.height + pad))
    canvas.paste(front, (pad + left_w + pad, pad))
    x = pad + left_w + pad
    for im in isos:
        canvas.paste(im, (x, pad + front.height + pad))
        x += im.width + pad

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path)
    return total_w, total_h


def main():
    parser = argparse.ArgumentParser(description="Compose multi-view / grid / 1:1 verification sheets.")
    parser.add_argument("--side", help="Path to rendered Side view PNG.")
    parser.add_argument("--top", help="Path to rendered Top view PNG.")
    parser.add_argument("--front", help="Path to rendered Front view PNG.")
    parser.add_argument("--iso", help="Path to rendered Front-Isometric view PNG.")
    parser.add_argument("--iso-rear", default=None, help="Optional path to rendered Rear-Isometric view PNG.")
    parser.add_argument("--panel", action="append", default=[], metavar="LABEL=PATH",
                        help="Grid mode: repeat for any number of labelled panels (e.g. --panel South=f.png).")
    parser.add_argument("--cols", type=int, default=3, help="Grid mode: columns.")
    parser.add_argument("--blueprint", default=None, help="Mode B: Path to original blueprint image for 1:1 side-by-side.")
    parser.add_argument("--crop", default=None, help="Mode B: Blueprint crop box 'u0,v0,u1,v1'.")
    parser.add_argument("--render", default=None, help="Mode B: Path to 1:1 orthographic render PNG.")
    parser.add_argument("--overlay", action="store_true", help="Mode B: add a 4th column, blueprint with red render edges.")
    parser.add_argument("--view-label", default="SIDE", help="Mode B: View label (SIDE/TOP/FRONT).")
    parser.add_argument("--output", required=True, help="Output composite PNG path.")
    args = parser.parse_args()

    if args.blueprint and args.crop and args.render:
        crop_box = tuple(int(x.strip()) for x in args.crop.split(","))
        w, h = compose_1to1_side_by_side(args.blueprint, crop_box, args.render, args.output, args.view_label, args.overlay)
        print(f"Success! 1:1 Side-by-Side sheet ({w}x{h}) written to: {args.output}")
    elif args.panel:
        panels = []
        for p in args.panel:
            if "=" not in p:
                parser.error("--panel expects LABEL=PATH")
            lab, path = p.split("=", 1)
            panels.append((lab, path))
        w, h = compose_grid(panels, args.output, args.cols)
        print(f"Success! Grid sheet ({w}x{h}, {len(panels)} panels) written to: {args.output}")
    elif args.side and args.top and args.front and args.iso:
        w, h = compose_sheet(args.side, args.top, args.front, args.iso, args.output, args.iso_rear)
        print(f"Success! Multi-view composite sheet ({w}x{h}) written to: {args.output}")
    else:
        parser.error("Provide (--side --top --front --iso) OR (--panel L=P ...) OR (--blueprint --crop --render).")


if __name__ == "__main__":
    main()
