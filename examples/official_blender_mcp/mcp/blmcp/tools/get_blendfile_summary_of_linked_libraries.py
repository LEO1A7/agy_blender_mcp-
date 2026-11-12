"""[OFF_TOOL_LIBS] 官方 MCP 外部链接库摘要工具定义 (get_blendfile_summary_of_linked_libraries)
- 适用 (When): 检查当前工程引用的外部 `.blend` 库及关联数据块
- 用法 (How) : 直接调 MCP 工具 `get_blendfile_summary_of_linked_libraries`
- 产出 (Out) : 返回外部链接库摘要
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
from blmcp.tools_helpers.blender_cli import run_blender_cli, synced_blend_for_cli
from blmcp.tools_helpers.connection import send_code
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Blend-File Linked Library Summary",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_of_linked_libraries() -> dict[str, object]:
        """
        Return a tree of directly and indirectly linked library files.
        """
        return send_code(toolcode_format_call(_TOOL_CALL, None), strict_json=True)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Blend-File Linked Library Summary for Command-Line",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_of_linked_libraries_for_cli(blend_file: str) -> dict[str, object]:
        """
        Return linked-library info by opening *blend_file* in background Blender.
        """
        with synced_blend_for_cli(blend_file) as synced_path:
            return run_blender_cli(synced_path, toolcode_format_call(_TOOL_CALL, None))
