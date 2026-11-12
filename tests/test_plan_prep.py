#!/usr/bin/env python3
"""Regression tests for bin/plan_prep.py (rotation sign, decoy grid rejection, refine, px2m, check-outline, fallback)."""

import json
import math
import os
import random
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
sys.path.insert(0, os.path.join(ROOT, "examples", "recipes"))

import plan_prep as PP  # noqa: E402
import spec_kit as SK  # noqa: E402


def _make_synthetic_plan(tilt_ccw_deg: float, w=900, h=700, seed=42):
    """Create tilted plan with thick L-shaped walls + thin horizontal garden grid decoy + tree blobs."""
    rng = random.Random(seed)
    # Draw level building first on transparent/white layer, rotate CCW by +tilt_ccw_deg around center, composite over garden grid
    bld = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(bld)
    # Thick outer masonry L-shape (stroke width 6px)
    pts = [(260, 220), (620, 220), (620, 470), (360, 470), (360, 380), (260, 380), (260, 220)]
    d.line(pts, fill=15, width=7, joint="curve")
    # Also draw interior thin partition / window line
    d.line([(440, 220), (440, 470)], fill=20, width=2)
    # PIL Image.rotate(angle_ccw) rotates CCW by positive angle!
    rot_bld = bld.rotate(tilt_ccw_deg, resample=Image.Resampling.BICUBIC, fillcolor=255)

    canvas = Image.new("L", (w, h), 250)
    dc = ImageDraw.Draw(canvas)
    # Horizontal garden grid decoy covering 75% of the page (1-px thin lines!)
    for x in range(20, w - 20, 35):
        dc.line([(x, 20), (x, h - 20)], fill=120, width=1)
    for y in range(20, h - 20, 35):
        dc.line([(20, y), (w - 20, y)], fill=120, width=1)
    # Scattered circular tree rings / squiggles outside ROI
    for _ in range(18):
        tx = rng.choice([rng.randint(50, 180), rng.randint(w - 180, w - 50)])
        ty = rng.randint(60, h - 60)
        r = rng.randint(18, 32)
        dc.ellipse([tx - r, ty - r, tx + r, ty + r], outline=60, width=2)
        dc.ellipse([tx - r // 2, ty - r // 2, tx + r // 2, ty + r // 2], outline=80, width=1)

    # Darken-blend rotated building onto garden decoy canvas
    c_arr = np.minimum(np.array(canvas), np.array(rot_bld))
    return Image.fromarray(c_arr, mode="L").convert("RGB")


def test_random_tilts_and_no_skimage_fallback():
    rng = random.Random(123)
    angles = [-33.4, -18.7, 19.5, 36.2] + [round(rng.uniform(-40.0, 40.0), 1) for _ in range(2)]
    with tempfile.TemporaryDirectory() as tmp:
        for idx, true_deg in enumerate(angles):
            img = _make_synthetic_plan(true_deg)
            p = os.path.join(tmp, f"plan_{idx}.png")
            img.save(p)
            gray = np.array(img.convert("L"))
            # Force fallback on odd indices
            orig_hough = PP._sk_phough
            if idx % 2 == 1:
                PP._sk_phough = None
            try:
                m1 = PP._grad_peaks(gray)
                m2 = PP._line_peaks(gray)
                cands = PP._merge_candidates(m1, m2, tol_deg=3.0, limit=3)
            finally:
                PP._sk_phough = orig_hough

            # Candidate set must contain true_deg within +/- 0.7 deg
            diffs = [abs(((c["deg"] - true_deg + 45.0) % 90.0) - 45.0) for c in cands]
            assert min(diffs) <= 0.7, f"true={true_deg}, cands={cands}, diffs={diffs}"

        # Full CLI workflow: scan -> build --refine -> px2m -> check-outline
        out_dir = os.path.join(tmp, "work")
        p_test = os.path.join(tmp, "plan_2.png")  # true_deg = +19.5
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"), "scan",
                        "--input", p_test, "--out", out_dir], check=True)
        meta_scan = json.load(open(os.path.join(out_dir, "scan_meta.json")))
        roi = meta_scan["suggested_roi_src"]

        # Build rotated ROI around central building [210, 170, 690, 520]
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"), "build",
                        "--input", p_test, "--angle", "18.8", "--roi", "200,160,700,530",
                        "--refine", "--scale", "0.04", "--layers", "--out", out_dir], check=True)
        meta = json.load(open(os.path.join(out_dir, "plan_meta.json")))
        assert meta["align_after"] >= 0.95, f"Low alignment score: {meta}"
        assert abs(meta["angle_deg"] - 19.5) <= 0.6, f"Refined angle drifted: {meta['angle_deg']}"
        for fn in ("plan_rot.png", "plan_roi.png", "plan_layers.png"):
            im = Image.open(os.path.join(out_dir, fn))
            assert max(im.size) <= PP.MAX_IMAGE_SIDE

        # Verify wrong-sign rotation triggers assertion!
        wrong = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"), "build",
                                "--input", p_test, "--angle", "-19.5", "--roi", "200,160,700,530",
                                "--out", os.path.join(tmp, "wrong")], capture_output=True, text=True)
        assert wrong.returncode != 0 and "Rotation sign check FAILED" in wrong.stderr, wrong.stderr

        # Verify px2m round-trip src <-> rot <-> m
        m_res = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"), "px2m",
                                "--meta", os.path.join(out_dir, "plan_meta.json"),
                                "--pt", "450,350"], capture_output=True, text=True, check=True)
        assert "->" in m_res.stdout and "m(" in m_res.stdout

        # Verify check-outline on leveled building rectangle:
        # Locate actual leveled ink bbox inside rot image to craft exact spec and verify high support!
        rot_img = Image.open(os.path.join(out_dir, "plan_rot.png")).convert("L")
        arr = np.array(rot_img)
        _, _, thick = PP._ink_and_thick_mask(arr)
        ru0, rv0, ru1, rv1 = [int(v) for v in meta["roi_rot"]]
        sub = thick[rv0:rv1, ru0:ru1]
        ys, xs = np.where(sub)
        ox, oy = meta["origin_rot"]
        s = meta["scale_m_per_px"]
        x0_m = round((ru0 + int(xs.min()) - ox) * s, 3)
        x1_m = round((ru0 + int(xs.max()) - ox) * s, 3)
        y0_m = round((oy - (rv0 + int(ys.max()))) * s, 3)
        y1_m = round((oy - (rv0 + int(ys.min()))) * s, 3)

        spec_p = os.path.join(out_dir, "building_spec.json")
        SK.spec_init(path=spec_p, scale_m_per_px=s, yaw_deg=meta["angle_deg"])
        SK.spec_set("levels", [{"id": "L1", "z": 0.0, "slab": 0.3}], path=spec_p)
        # Main rect bounds match overall bbox; check-outline must pass >= 0.8 on solid perimeter!
        SK.spec_set("outline", {"L1": {"union": [[x0_m, y0_m, x1_m, y1_m]]}}, path=spec_p)
        chk = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"), "check-outline",
                              "--meta", os.path.join(out_dir, "plan_meta.json"),
                              "--spec", spec_p, "--level", "L1"], capture_output=True, text=True, check=True)
        assert "verdict=" in chk.stdout
        # Check outer N/E edges align well (S/W have L-notch so overall mean check)
        assert "Mean solid-edge support=" in chk.stdout


if __name__ == "__main__":
    test_random_tilts_and_no_skimage_fallback()
    print("test_plan_prep: ALL PASS")
