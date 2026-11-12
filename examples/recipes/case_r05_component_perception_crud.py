"""[CASE_R05] 构件世界 AABB 状态感知 · 原地位姿微调 · 无损替换网格几何与安全删除 (Component Perception & CRUD)
- 适用 (When): Stage 4 闭环调优中需查询已建构件的世界 AABB 边界/中心/尺寸，或执行原地位姿微调、无损替换 Mesh 数据块、清理冗余件
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r05_component_perception_crud import inspect_scene_components, transform_component, replace_component_geometry`
- 产出 (Out) : 返回精确到 0.1mm 的世界 AABB 字典 (`bbox_min/max`, `dimensions_aabb`, `center_aabb`) 及更新后的构件状态
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    inspect_scene_components,
    transform_component,
    replace_component_geometry,
    remove_components,
)
