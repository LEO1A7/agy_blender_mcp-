#!/usr/bin/env python3
"""Optional end-to-end sample acceptance test driven by `AGY_SAMPLE_DIR`.

Skips cleanly with exit 0 if `AGY_SAMPLE_DIR` is unset or sample files are absent.
When set, verifies the rotated architectural plan & section pipeline end-to-end.
"""

import json
import os
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_NAME = "media_1794305647911_e26b5ba6.jpg"
SEC_NAME = "media_1794305658610_1589dd14.jpg"
ALL_SAMPLES = (
    "media_1794305623326_f36a7b5e.jpg",
    "media_1794305637408_5107f2b9.jpg",
    PLAN_NAME,
    SEC_NAME,
    "media_1794305672022_6691d155.jpg",
)


def main():
    sample_dir = os.environ.get("AGY_SAMPLE_DIR", "").strip()
    if not sample_dir or not os.path.isdir(sample_dir):
        print("[SKIP] AGY_SAMPLE_DIR is unset or missing; skipping external sample acceptance.")
        return 0
    plan_p = os.path.join(sample_dir, PLAN_NAME)
    sec_p = os.path.join(sample_dir, SEC_NAME)
    if not (os.path.exists(plan_p) and os.path.exists(sec_p)):
        print(f"[SKIP] Sample plan/section not found inside {sample_dir}; skipping.")
        return 0

    for fn in ALL_SAMPLES:
        assert os.path.exists(os.path.join(sample_dir, fn)), f"Missing sample file: {fn}"

    with tempfile.TemporaryDirectory(prefix="agy_v14_sample_") as tmp:
        # 1. Plan scan -> expect candidate near +19.5 +/- 0.8 deg
        p_scan = subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"),
            "scan", "--input", plan_p, "--out", tmp,
        ], capture_output=True, text=True, check=True)
        assert len(p_scan.stdout.splitlines()) <= 20
        scan_meta = json.load(open(os.path.join(tmp, "scan_meta.json"), encoding="utf-8"))
        cands = scan_meta["candidates"]
        assert cands, f"No candidates in scan_meta: {scan_meta}"
        top_deg = float(cands[0]["deg"])
        assert abs(abs(top_deg) - 19.5) <= 0.8, f"Expected candidate ~19.5+/-0.8 deg, got {cands}"
        roi_str = ",".join(str(v) for v in scan_meta["suggested_roi_src"])

        # 2. Section slab detection with spurious band drops -> 4 slabs & scale ~0.0565 +/- 3%
        sec_json = os.path.join(tmp, "sec_meta.json")
        sec_mark = os.path.join(tmp, "sec_mark.png")
        p_sec = subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "section_levels.py"),
            "--input", sec_p, "--elev", "0.04,3.22,6.37,9.52",
            "--drop", "122", "--drop", "49.5",
            "--mark", sec_mark, "--out-json", sec_json,
        ], capture_output=True, text=True, check=True)
        assert len(p_sec.stdout.splitlines()) <= 20
        sec_data = json.load(open(sec_json, encoding="utf-8"))
        assert len(sec_data["bands_bottom_up"]) == 4, sec_data["bands_bottom_up"]
        sec_scale = float(sec_data["fit"]["scale_m_per_px"])
        assert abs(sec_scale - 0.0565) / 0.0565 <= 0.03, f"Section scale {sec_scale} outside +/-3% of 0.0565"

        # 3. Build rotated plan + refine -> align_after >= 0.90
        p_build = subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"),
            "build", "--input", plan_p, "--angle", str(top_deg),
            "--roi", roi_str, "--refine", "--layers", "--out", tmp,
        ], capture_output=True, text=True, check=True)
        assert len(p_build.stdout.splitlines()) <= 20
        plan_meta_p = os.path.join(tmp, "plan_meta.json")
        meta = json.load(open(plan_meta_p, encoding="utf-8"))
        assert meta["align_after"] >= 0.90, f"align_after={meta['align_after']} < 0.90"
        assert abs(meta["angle_deg"] - 19.5) <= 0.8, f"Refined angle={meta['angle_deg']}"

        # 4. Transfer scale from section + rebuild metric ROI grid <= 1600px
        subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"),
            "scale-from-section", "--meta", plan_meta_p,
            "--section-scale", str(sec_scale),
            "--section-span-px", "200",
            "--plan-span", "100,100,300,100",
        ], capture_output=True, text=True, check=True)
        meta_scaled = json.load(open(plan_meta_p, encoding="utf-8"))
        assert abs(float(meta_scaled["scale_m_per_px"]) - sec_scale) / sec_scale < 0.01

        subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "plan_prep.py"),
            "build", "--input", plan_p, "--angle", str(meta["angle_deg"]),
            "--roi", roi_str, "--scale", str(meta_scaled["scale_m_per_px"]), "--out", tmp,
        ], capture_output=True, text=True, check=True)
        meta_metric = json.load(open(plan_meta_p, encoding="utf-8"))
        assert meta_metric["grid_unit"] == "meters"

        # 5. Detail tiles on leveled plan + image cap <= 1600px across all outputs
        tiles_dir = os.path.join(tmp, "tiles")
        subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "reference_detail_tiles.py"),
            "--input", os.path.join(tmp, "plan_rot.png"),
            "--meta", plan_meta_p, "--outdir", tiles_dir,
        ], capture_output=True, text=True, check=True)

        for img_p in (
            os.path.join(tmp, "scan_sheet.png"),
            os.path.join(tmp, "orient_candidates.png"),
            os.path.join(tmp, "plan_rot.png"),
            os.path.join(tmp, "plan_roi.png"),
            os.path.join(tmp, "plan_layers.png"),
            sec_mark,
            os.path.join(tiles_dir, "contact_sheet.png"),
        ):
            assert os.path.exists(img_p), f"Missing output image: {img_p}"
            with Image.open(img_p) as im:
                assert max(im.size) <= 1600, f"Image {img_p} exceeds 1600px: {im.size}"

        print(
            f"sample_acceptance: ALL PASS | cand={top_deg:+.2f} refined={meta['angle_deg']:+.2f} "
            f"align={meta['align_before']:.3f}->{meta['align_after']:.3f} sec_scale={sec_scale:.6f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
