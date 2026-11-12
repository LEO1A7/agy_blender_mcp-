"""[CASE_R03] 五大核心 BMesh 参数化几何构造算子 (侧视拉伸/波浪侧裙/平面四边面多面体壳/同轴锥柱/闭合履带环)
- 适用 (When): 构建对称截面拉伸首尾收窄、余弦平滑下缘侧裙板、防 N-gon 折痕的多层多面体壳封顶、沿 Y 轴锥柱管段或闭合连续履带
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r03_parametric_bmesh_builders import extrude_side_profile, build_layered_polyhedral_shell, build_contoured_track_loop`
- 产出 (Out) : 返回法线朝外、闭合流形 (0 non-manifold) 的 `bmesh.types.BMesh` 或已挂载场景的构件列表
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    extrude_side_profile,
    build_wavy_skirt_panels,
    build_layered_polyhedral_shell,
    add_cyl_along_y,
    build_contoured_track_loop,
)
