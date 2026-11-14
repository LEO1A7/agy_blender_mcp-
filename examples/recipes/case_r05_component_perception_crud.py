"""[CASE_R05] 构件世界 AABB 感知 · 隐藏不良件 (__hide_r<N>__) 与原位重新生成 · 无损替换与清理 (Hide & Regenerate CRUD)
- 适用 (When): 任何验收阶段发现不良/穿模/错位构件时，严禁直接局部微调，应隐藏不良件并原位重新生成后复验
- 用法 (How) : `from case_r05_component_perception_crud import inspect_scene_components, hide_defective_components, regenerate_component_in_place, audit_and_regenerate`
- 产出 (Out) : 返回精确世界 AABB 字典、隐藏归档记录 (`__hide_r<N>__`) 与原位重建后的新构件状态
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    inspect_scene_components,
    hide_defective_components,
    get_hidden_component_slot,
    regenerate_component_in_place,
    audit_and_regenerate,
    transform_component,
    replace_component_geometry,
    remove_components,
)
