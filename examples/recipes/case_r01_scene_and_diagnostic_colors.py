"""[CASE_R01] 场景初始化 · 集合/父子层级管理 · 原生 RANDOM 分色与 finish_materials 材质交付 (Scene & Shading)
- 适用 (When): 初始化公制场景(默认原生 `RANDOM` 随机分色+轮廓)、创建/清理集合、零偏移父子挂载 (`set_parent_keep_world`)、切换 `RANDOM`/`MATERIAL` 或批量赋材质交付
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r01_scene_and_diagnostic_colors import setup_clean_scene, set_shading_color_mode, finish_materials, create_mesh_object`
- 产出 (Out) : 返回干净公制场景/集合、自动赋倒角的 Mesh 对象、`set_shading_color_mode` 状态字典，或 `finish_materials` 批量材质交付汇总
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    setup_clean_scene,
    get_or_create_collection,
    clear_collection,
    link_exclusively,
    set_parent_keep_world,
    make_pbr_material,
    add_angle_bevel,
    create_mesh_object,
    set_shading_color_mode,
    set_diagnostic_color_mode,
    finish_materials,
)
