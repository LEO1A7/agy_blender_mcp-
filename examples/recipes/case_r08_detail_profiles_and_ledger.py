"""[CASE_R08] 标准钢结构型材库 · 多边形墙体/斜切凸窗算子 · 细部阵列 · 防漏建台账 (Detail Profiles & Polygon/Bay Kit)
- 适用 (When): 构建 H/I 型钢(HEB/HEA/IPE)、多边形楼板(`add_polygon_slab`)、折线外墙(`add_polyline_wall`)、斜切/异形凸窗(`add_splayed_bay`)、格栅/百叶/栏杆/窗及细部审计
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r08_detail_profiles_and_ledger import add_steel_member, add_polygon_slab, add_polyline_wall, add_splayed_bay, add_slat_array, add_louver_leaf, add_railing, add_window, ledger_set, ledger_check, detail_audit`
- 产出 (Out) : 返回单连通闭合流形型材/斜切凸窗/细部构件（杜绝方块替代与正交简化），并提供 `ledger_check` 与 `detail_audit` 验收报告
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
    add_polygon_slab,
    add_polyline_wall,
    add_splayed_bay,
    finalize_object,
    ledger_set,
    ledger_get,
    ledger_check,
    detail_audit,
)
