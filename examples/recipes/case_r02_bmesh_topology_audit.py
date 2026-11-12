"""[CASE_R02] 纯 BMesh 网格流形 · 零面积退化面 · 孤立顶点 · 未归零缩放体检 (Pure-BMesh Topology Audit)
- 适用 (When): 分段建模或终验阶段需检查全场景/单构件是否存在非流形边、零面积面、孤立点或未应用 Scale (!=1,1,1)
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r02_bmesh_topology_audit import audit_scene_meshes, audit_object_topology; print(audit_scene_meshes())`
- 产出 (Out) : 返回结构化字典 `{"passed": bool, "defective_objects": [...], "missing_parts": [...], "total_verts": int, "total_faces": int}`
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cad_operator_recipes import (  # noqa: E402,F401
    audit_object_topology,
    audit_scene_meshes,
)
