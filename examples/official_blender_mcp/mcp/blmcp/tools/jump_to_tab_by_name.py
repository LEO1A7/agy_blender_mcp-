"""[OFF_TOOL_JUMP_TAB] 官方 MCP 切换 Blender 工作区标签页工具定义 (jump_to_tab_by_name)
- 适用 (When): 需切换 Blender 顶部 Workspace 标签页（如 Layout, Modeling, Shading）
- 用法 (How) : 直接调 MCP 工具 `jump_to_tab_by_name`
- 产出 (Out) : 切换至目标工作区并返回状态
"""
# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=C0114  # See tool doc-string.

__all__ = (
    "register",
)

from blmcp.tools_helpers import (
    toolcode_format_call,
    toolcode_load_from_filepath,
    toolcode_wrap_with_calling_convention,
)
from blmcp.tools_helpers.connection import send_code
from blmcp.tools.jump_to_tab_by_name_toolcode import Params
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Switch to Workspace",
            destructiveHint=True,
        )
    )
    def jump_to_tab_by_name(name: str) -> dict[str, object]:
        """
        Switch the active workspace tab to *name*.
        """
        p = Params(name=name)
        code = toolcode_format_call(_TOOL_CALL, p)
        return send_code(code, strict_json=True)
