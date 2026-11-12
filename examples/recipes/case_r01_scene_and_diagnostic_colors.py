"""[CASE_R01] 场景初始化 · 集合/父子层级管理 · 原生 RANDOM 随机分色与 MATERIAL 材质切换 (Scene & Shading Colors)
- 适用 (When): 初始化公制场景(默认开启原生 `RANDOM` 物体随机分色+轮廓)、创建/清理集合、零偏移父子挂载 (`set_parent_keep_world`)、切换 `RANDOM`/`MATERIAL` 着色
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r01_scene_and_diagnostic_colors import setup_clean_scene, set_diagnostic_color_mode, create_mesh_object`
- 产出 (Out) : 返回干净公制场景/集合、自动赋倒角的 Mesh 对象，或一键切换 `RANDOM`(建模核验)/`MATERIAL`(材质观察与交付) 视口着色字典
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    DIAGNOSTIC_COLOR_PALETTE,
    GENERIC_GROUP_PALETTE,
    setup_clean_scene,
    get_or_create_collection,
    clear_collection,
    link_exclusively,
    set_parent_keep_world,
    make_pbr_material,
    add_angle_bevel,
    infer_diagnostic_group,
    create_mesh_object,
    set_diagnostic_color_mode,
)
