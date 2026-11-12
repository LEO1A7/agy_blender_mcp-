"""[CASE_R09] Architectural Building Spec 唯一真源 · 矩形并差布尔转环 · 状态校验与摘要恢复 (Building Spec)
- 适用 (When): P0~P5 锚定标高/比例/朝向、用矩形并差 DSL 描述各层轮廓与增量 (`base+add+sub`)、执行 `spec_validate()` 或上下文压缩后用 `spec_digest()`/`phase_next()` 恢复
- 用法 (How) : `from case_r09_building_spec import spec_init, spec_set, spec_patch, spec_note, resolve_outline, outline_edges, spec_validate, spec_digest, phase_next, apply_site_yaw`
- 产出 (Out) : 持久化 `./agy_work/building_spec.json`(+scene 镜像)、CCW 外环/CW 孔环、≤40 行摘要与阶段行动卡
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from spec_kit import (  # noqa: E402,F401
    VALID_EDGE_KINDS,
    VALID_SKIN_KINDS,
    spec_init,
    spec_load,
    spec_save,
    spec_set,
    spec_patch,
    spec_note,
    rect_union_to_rings,
    resolve_outline,
    outline_edges,
    match_rule_to_edges,
    spec_show,
    spec_validate,
    spec_digest,
    phase_next,
    apply_site_yaw,
)
