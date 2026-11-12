"""[OFF_TOOL_OBJS] 官方 MCP 场景集合与对象层级摘要工具定义 (get_objects_summary)
- 适用 (When): 需快速获取全场景 Collection 树与对象列表（名称/类型/父级/可见性/选中状态）
- 用法 (How) : 直接调 MCP 工具 `get_objects_summary`；实现细节见同目录 `get_objects_summary_toolcode.py`
- 产出 (Out) : 返回场景集合树与对象状态 JSON
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
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Objects Summary",
            readOnlyHint=True,
        )
    )
    def get_objects_summary() -> dict[str, object]:
        """
        Return the scene's collection hierarchy and their objects.

        Each collection lists its objects (name, type, parent, data name,
        selection, visibility) and nested child collections.
        """
        return send_code(toolcode_format_call(_TOOL_CALL, None), strict_json=True)
