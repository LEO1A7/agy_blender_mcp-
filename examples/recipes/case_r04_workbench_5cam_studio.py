"""[CASE_R04] Stage 4 统一 5 机位 Workbench Cavity+Outline 摄影棚 (1:1 正交三视图 + 自动锁距双等轴测 + 局部特写)
- 适用 (When): Stage 4 视口视觉核验，需一键架设三点太阳光、Workbench Cavity+Outline 浅灰底渲染、5 机位(支持载具与建筑北上平面双约定)及节点特写
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r04_workbench_5cam_studio import setup_workbench_studio_and_cameras, render_views, render_closeup`
- 产出 (Out) : 返回 `{"Cam_Side_Left", "Cam_Top", "Cam_Front", "Cam_Iso", "Cam_Iso_Rear"}` 相机字典，并支持 `render_views` 与 `render_closeup`
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
    describe_studio,
    render_views,
    render_closeup,
)
