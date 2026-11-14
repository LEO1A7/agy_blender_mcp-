"""[CASE_R04] P4 两阶段 VLM 视觉验收摄影棚 (第1轮 Workbench 着色截图 + 第2轮 EEVEE 实际光照渲染)
- 适用 (When): P4 视觉核验：第1轮用着色模式截图(`r1_shaded`)检查几何，通过后第2轮用实际光照渲染(`r2_lit`)验收材质/光影/开口
- 用法 (How) : `from case_r04_workbench_5cam_studio import setup_workbench_studio_and_cameras, setup_lit_studio, render_views, render_lit_views, render_vlm_verification_views, render_closeup`
- 产出 (Out) : 返回 5/9 机位相机字典，及 `r1_shaded_*.png`（着色截图）与 `r2_lit_*.png`（EEVEE 实光渲染）
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    VIEW_AXES,
    scene_bounds,
    compute_or_lock_iso_distance,
    setup_workbench_studio_and_cameras,
    setup_lit_studio,
    describe_studio,
    render_views,
    render_lit_views,
    render_vlm_verification_views,
    render_closeup,
)
