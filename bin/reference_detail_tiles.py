"""[BIN_DETAIL_TILES] 参考图细部读图工具：自动分块放大 + 总览接触表 + 细节密度排序 + 单区域精读
- 适用 (When): Stage 0 读参考图（尤其透视照片/低分辨率图）时系统性挖掘细部——型钢截面、百叶、栏杆、窗分格、管道接头；避免只看“整体印象”
- 用法 (How) : python3 bin/reference_detail_tiles.py --input photo.jpg --outdir out/ [--grid 3x3 --zoom 2.5 --overlap 0.15 --top 4] | --crop u0,v0,u1,v1 --zoom 4 --outdir out/
- 产出 (Out) : outdir/contact_sheet.png(带编号总览) + tile_rXcY.png(放大块) + tiles.json(块→原图像素映射、细节密度排名)；终端打印“最富细节的前N块”路径供优先精读
"""

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def edge_density(img: Image.Image) -> float:
    """Mean gradient magnitude (0..255) — a cheap proxy for how much fine detail a tile contains."""
    g = np.array(img.convert("L")).astype(np.float32)
    gx = np.abs(g[:, 2:] - g[:, :-2])[1:-1, :]
    gy = np.abs(g[2:, :] - g[:-2, :])[:, 1:-1]
    return float(np.mean(gx) + np.mean(gy))


def make_tiles(src: Image.Image, rows: int, cols: int, overlap: float, zoom: float, sharpen: bool):
    W, H = src.size
    tw = W / (cols - (cols - 1) * overlap) if cols > 1 else W
    th = H / (rows - (rows - 1) * overlap) if rows > 1 else H
    step_x = tw * (1 - overlap) if cols > 1 else 0
    step_y = th * (1 - overlap) if rows > 1 else 0
    tiles = []
    for r in range(rows):
        for c in range(cols):
            u0 = int(round(c * step_x))
            v0 = int(round(r * step_y))
            u1 = min(W, int(round(u0 + tw)))
            v1 = min(H, int(round(v0 + th)))
            crop = src.crop((u0, v0, u1, v1))
            big = crop.resize((int(crop.width * zoom), int(crop.height * zoom)), Image.Resampling.LANCZOS)
            if sharpen:
                big = big.filter(ImageFilter.UnsharpMask(radius=1.6, percent=130, threshold=2))
            tiles.append({"row": r, "col": c, "box": [u0, v0, u1, v1], "image": big, "density": edge_density(crop)})
    return tiles


def stamp(img: Image.Image, text: str) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    f = _font(max(14, out.width // 45))
    tw = d.textlength(text, font=f)
    d.rectangle([4, 4, 14 + tw, 14 + f.size if hasattr(f, "size") else 30], fill=(20, 22, 28))
    d.text((9, 7), text, fill=(255, 220, 90), font=f)
    return out


def contact_sheet(src: Image.Image, tiles, rows: int, cols: int, out_path: str, max_w: int = 1800):
    scale = min(1.0, max_w / src.width)
    base = src.resize((int(src.width * scale), int(src.height * scale)), Image.Resampling.LANCZOS).convert("RGB")
    d = ImageDraw.Draw(base)
    f = _font(max(16, base.width // 40))
    ranked = sorted(tiles, key=lambda t: -t["density"])
    rank_of = {id(t): i + 1 for i, t in enumerate(ranked)}
    for t in tiles:
        u0, v0, u1, v1 = [int(x * scale) for x in t["box"]]
        hot = rank_of[id(t)] <= max(1, len(tiles) // 3)
        d.rectangle([u0, v0, u1 - 1, v1 - 1], outline=(255, 60, 60) if hot else (60, 200, 255), width=2)
        d.text((u0 + 6, v0 + 4), f"r{t['row']}c{t['col']} #{rank_of[id(t)]}", fill=(255, 255, 0), font=f)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    base.save(out_path)


def main():
    ap = argparse.ArgumentParser(description="Split a reference image into zoomed tiles for systematic detail reading.")
    ap.add_argument("--input", required=True, help="Reference photo/drawing.")
    ap.add_argument("--outdir", "--out-dir", dest="outdir", required=True, help="Output directory.")
    ap.add_argument("--grid", default="3x3", help="ROWSxCOLS tiling, e.g. 3x3 (ignored with --crop).")
    ap.add_argument("--overlap", type=float, default=0.15, help="Tile overlap fraction 0..0.5.")
    ap.add_argument("--zoom", type=float, default=2.5, help="Upsample factor for each tile.")
    ap.add_argument("--no-sharpen", action="store_true", help="Disable unsharp mask after upsampling.")
    ap.add_argument("--top", type=int, default=4, help="Print the N most detail-rich tiles.")
    ap.add_argument("--crop", default=None, help="Single-region mode 'u0,v0,u1,v1' (source px): output one zoomed image.")
    ap.add_argument("--prefix", default="tile", help="Tile filename prefix.")
    args = ap.parse_args()

    src = Image.open(args.input).convert("RGB")
    os.makedirs(args.outdir, exist_ok=True)

    if args.crop:
        u0, v0, u1, v1 = (int(x) for x in args.crop.split(","))
        crop = src.crop((u0, v0, u1, v1))
        big = crop.resize((int(crop.width * args.zoom), int(crop.height * args.zoom)), Image.Resampling.LANCZOS)
        if not args.no_sharpen:
            big = big.filter(ImageFilter.UnsharpMask(radius=1.6, percent=130, threshold=2))
        path = os.path.join(args.outdir, f"crop_u{u0}-{u1}_v{v0}-{v1}_x{args.zoom:g}.png")
        stamp(big, f"src px u{u0}-{u1} v{v0}-{v1} x{args.zoom:g}").save(path)
        print(f"Success! zoomed crop written to: {path}")
        return

    rows, cols = (int(x) for x in args.grid.lower().split("x"))
    tiles = make_tiles(src, rows, cols, args.overlap, args.zoom, not args.no_sharpen)
    meta = []
    ranked = sorted(tiles, key=lambda t: -t["density"])
    for i, t in enumerate(ranked):
        t["rank"] = i + 1
    for t in tiles:
        u0, v0, u1, v1 = t["box"]
        name = f"{args.prefix}_r{t['row']}c{t['col']}.png"
        path = os.path.join(args.outdir, name)
        stamp(t["image"], f"r{t['row']}c{t['col']} src u{u0}-{u1} v{v0}-{v1} x{args.zoom:g}").save(path)
        meta.append({"file": path, "row": t["row"], "col": t["col"], "src_box_uv": t["box"],
                     "zoom": args.zoom, "detail_density": round(t["density"], 3), "rank": t["rank"]})
    sheet = os.path.join(args.outdir, "contact_sheet.png")
    contact_sheet(src, tiles, rows, cols, sheet)
    with open(os.path.join(args.outdir, "tiles.json"), "w", encoding="utf-8") as f:
        json.dump({"source": os.path.abspath(args.input), "size": list(src.size), "grid": [rows, cols], "tiles": meta},
                  f, indent=2, ensure_ascii=False)
    print(f"Success! {len(tiles)} tiles + contact sheet written to: {args.outdir}")
    print(f"contact_sheet: {sheet}")
    for m in sorted(meta, key=lambda m: m["rank"])[:args.top]:
        print(f"  detail-rich #{m['rank']}: {m['file']}  (density {m['detail_density']})")


if __name__ == "__main__":
    main()
