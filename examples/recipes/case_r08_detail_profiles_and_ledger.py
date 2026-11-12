"""[CASE_R08] 标准钢结构型材库 · 建筑/工业细部阵列算子 · 防漏建台账 (Detail Profiles & Feature Ledger)
- 适用 (When): 构建 H/I 型钢(HEB/HEA/IPE)、槽钢/角钢/方管、菱形格栅阵列、百叶折扇、栏杆、带框窗及细部防退化审计
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r08_detail_profiles_and_ledger import add_steel_member, add_slat_array, add_louver_leaf, add_railing, add_window, ledger_set, ledger_check, detail_audit`
- 产出 (Out) : 返回单连通闭合流形型材/细部构件（杜绝三盒叠加与方块替代），并提供 `ledger_check` 与 `detail_audit` 细部验收报告
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from detail_kit import (  # noqa: E402,F401
    STEEL_SECTIONS,
    steel_profile,
    profile_H,
    profile_channel,
    profile_angle,
    profile_tee,
    profile_rect,
    profile_diamond,
    profile_rect_tube,
    profile_round,
    profile_round_tube,
    add_prism,
    add_steel_member,
    add_cylinder,
    add_flange_ring,
    add_oriented_box,
    add_box,
    add_slat_array,
    add_louver_leaf,
    add_railing,
    add_window,
    finalize_object,
    ledger_set,
    ledger_get,
    ledger_check,
    detail_audit,
)
