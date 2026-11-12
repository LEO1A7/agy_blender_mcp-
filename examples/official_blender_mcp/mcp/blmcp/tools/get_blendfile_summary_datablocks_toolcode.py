"""[OFF_CODE_DB_SUM] 官方 MCP 统计 `bpy.data` 全数据块数量的 Blender 端源码
- 适用 (When): 参考如何轻量遍历 `bpy.data` 统计各类型数据块规模
- 用法 (How) : 按需读取 `main()` 实现（原文件只读）
- 产出 (Out) : 返回数据块计数字典
"""
# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tool-code for data-block counts, active workspace, and render engine.
"""

__all__ = (
    "Result",
    "main",
)

from typing import NamedTuple


class Result(NamedTuple):
    status: str
    datablock_counts: dict[str, int]
    render_engine: str
    scene_name: str
    workspaces: list[str]
    active_workspace: str | None = None


def main(params: None) -> Result:
    del params
    import bpy  # pylint: disable=import-error,no-name-in-module

    counts: dict[str, int] = {}
    for attr in sorted(dir(bpy.data)):
        val = getattr(bpy.data, attr, None)
        if hasattr(val, "__len__") and hasattr(val, "keys"):
            try:
                n = len(val)  # type: ignore[arg-type]
                if n > 0:
                    counts[attr] = n
            except Exception:  # pylint: disable=broad-exception-caught
                # Some `bpy.data` attributes look like collections but
                # raise when accessed (e.g. during undo). Safe to skip.
                pass

    window = getattr(bpy.context, "window", None)

    return Result(
        status="ok",
        datablock_counts=counts,
        render_engine=bpy.context.scene.render.engine,
        scene_name=bpy.context.scene.name,
        workspaces=[ws.name for ws in bpy.data.workspaces],
        active_workspace=window.workspace.name if window else None,
    )
