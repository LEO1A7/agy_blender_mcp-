"""[CASE_R11] Blender 真几何楼层剖切导出 · 数值 IoU/边偏差/虚实覆盖率验收 (Level Cut Verify)
- 适用 (When): P3/P5 替代“顶视相机裁剪”，用 `bmesh.ops.bisect_plane` 真剖切各层标高并做逐对象奇偶填充数值验收
- 用法 (How) : `from case_r11_level_cut_verify import export_level_cuts, verify_levels; r = verify_levels(); print(r['report'])`
- 产出 (Out) : `agy_work/level_cuts.json`、`verify_L*.json` 以及 `<=25` 行数值验收报告（不 pass 时再调用 `level_plan_render.py` 看图定位）
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from level_cut_verify import (  # noqa: E402,F401
    export_level_cuts,
    verify_levels,
)
