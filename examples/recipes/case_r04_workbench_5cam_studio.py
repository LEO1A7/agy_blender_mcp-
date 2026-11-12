"""[CASE_R04] Stage 4 统一 5 机位 Workbench 摄影棚 · 水平剖切平面图 (`render_plan_section`) · 局部特写
- 适用 (When): Stage 4 视觉核验，一键架设 5 机位(载具/建筑北上双约定)、渲染水平剖切平面图(`render_plan_section` 切掉屋顶对账平面图)及节点特写
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r04_workbench_5cam_studio import setup_workbench_studio_and_cameras, render_views, render_plan_section, render_closeup`
- 产出 (Out) : 返回相机字典，支持 `render_views`、`render_plan_section(out, cut_z=1.5)` (用于 Mode B 1:1 平面图叠合) 与 `render_closeup`
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
    render_plan_section,
    render_closeup,
)
