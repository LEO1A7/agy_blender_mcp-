"""[CASE_R02] 纯 BMesh 流形 · 几何重叠穿模检测 (BVHTree) · 自动隐藏不良构件与原位重新生成 (Topology & Clash Audit)
- 适用 (When): 分段建模或验收阶段需检查非流形边/零面/孤立点/自交/跨构件实体穿模重叠，并自动隐藏不良件原位重生成
- 用法 (How) : `from case_r02_bmesh_topology_audit import audit_scene_meshes, audit_object_topology, audit_scene_clashes, audit_and_regenerate`
- 产出 (Out) : 返回流形+穿模双体检报告 (`clashes`, `defective_targets`)，或一键隐藏 `__hide_r<N>__` 并原位重生成后复验
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    audit_object_topology,
    audit_scene_clashes,
    audit_scene_meshes,
    hide_defective_components,
    regenerate_component_in_place,
    audit_and_regenerate,
)
