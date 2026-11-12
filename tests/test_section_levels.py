#!/usr/bin/env python3
"""Unit tests for bin/section_levels.py (slab band detection & scale least-squares fitting)."""

import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_synthetic_section_and_drop_ambiguity():
    with tempfile.TemporaryDirectory() as tmp:
        w, h = 800, 420
        img = Image.new("L", (w, h), 250)
        d = ImageDraw.Draw(img)
        # True scale: 0.05 m/px => 20 px per meter. Draw 4 slabs at z=0.0, 3.2, 6.4, 9.6m (slab=0.30m => 6px thick)
        # Let base v = 350 -> v = 350, 286, 222, 158
        true_vs = [350, 286, 222, 158]
        for v in true_vs:
            d.rectangle([160, v - 3, 640, v + 3], fill=15)
        # Add spurious ground overhang/roof trellis dark band at v=90
        d.rectangle([160, 90 - 3, 640, 90 + 3], fill=15)
        # Thin vertical facade walls & dimension ticks
        d.line([(160, 155), (160, 353)], fill=30, width=2)
        d.line([(640, 155), (640, 353)], fill=30, width=2)

        sec_p = os.path.join(tmp, "sec.png")
        img.save(sec_p)

        # Without --drop, 5 bands vs 4 elevs -> AMBIGUOUS (exit code 2)
        amb = subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "section_levels.py"),
            "--input", sec_p, "--elev", "0.0,3.2,6.4,9.6"
        ], capture_output=True, text=True)
        assert amb.returncode == 2 and "AMBIGUOUS" in amb.stdout, amb.stdout

        # With --drop 90, fits s=0.0500 +/- 2%
        out_json = os.path.join(tmp, "sec.json")
        mark_png = os.path.join(tmp, "mark.png")
        res = subprocess.run([
            sys.executable, os.path.join(ROOT, "bin", "section_levels.py"),
            "--input", sec_p, "--elev", "0.0,3.2,6.4,9.6", "--drop", "90",
            "--mark", mark_png, "--out-json", out_json
        ], capture_output=True, text=True, check=True)
        data = json.load(open(out_json))
        s = data["fit"]["scale_m_per_px"]
        assert abs(s - 0.05) / 0.05 < 0.02, f"Scale error too high: {s}"
        assert os.path.exists(mark_png)
        assert len(res.stdout.splitlines()) <= 20


if __name__ == "__main__":
    test_synthetic_section_and_drop_ambiguity()
    print("test_section_levels: ALL PASS")
