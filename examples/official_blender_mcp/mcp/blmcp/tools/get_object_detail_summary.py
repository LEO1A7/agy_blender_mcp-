"""[OFF_TOOL_OBJ_DETAIL] 官方 MCP 单对象详细拓扑/变换/材质/修改器查询工具定义 (get_object_detail_summary)
- 适用 (When): 需查询特定对象的世界矩阵、包围盒、顶点数、修改器与约束详情
- 用法 (How) : 直接调 MCP 工具 `get_object_detail_summary`；实现代码见 `get_object_detail_summary_toolcode.py`
- 产出 (Out) : 返回指定对象的详细结构化摘要字典
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
from blmcp.tools.get_object_detail_summary_toolcode import Params
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Object Detail Summary",
            readOnlyHint=True,
        )
    )
    def get_object_detail_summary(
        name: str,
    ) -> dict[str, object]:
        """
        Return a structured summary of the object identified by *name*.

        Includes type, transforms, parent, children, modifiers, constraints,
        materials, visibility, data-block name, and collections.
        """
        p = Params(name=name)
        code = toolcode_format_call(_TOOL_CALL, p)
        return send_code(code, strict_json=True)
