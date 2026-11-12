"""[CASE_R10] 建筑体块与外立面自动建造 · 板块开洞 · 悬挑退台 · 错层踏步墙 (Massing & Envelope)
- 适用 (When): P3 读取 Building Spec，调用 `build_all_levels()` / `build_level()` 一键生成无布尔闭合流形楼板、转角不重叠墙体与虚实立面
- 用法 (How) : `from case_r10_massing_envelope import build_level_slab, wall_with_openings, build_envelope, add_cantilever, build_level, build_all_levels`
- 产出 (Out) : 返回 `L{n}_Slab` / `L{n}_Wall_*` / `L{n}_Glaze_*` / `L{n}_Skin_*` / `L{n}_StepWall_*` 构件字典（原生 RANDOM 随机分色）
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from facade_kit import (  # noqa: E402,F401
    build_level_slab,
    wall_with_openings,
    build_envelope,
    add_cantilever,
    build_level,
    build_all_levels,
)
