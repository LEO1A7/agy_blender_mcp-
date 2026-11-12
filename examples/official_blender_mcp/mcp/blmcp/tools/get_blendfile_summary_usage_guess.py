"""[OFF_TOOL_USAGE] 官方 MCP 工程用途智能推断工具定义 (get_blendfile_summary_usage_guess)
- 适用 (When): 快速判断未知 `.blend` 文件的主要用途（建模/动画/合成/雕刻等）
- 用法 (How) : 直接调 MCP 工具 `get_blendfile_summary_usage_guess`
- 产出 (Out) : 返回工程用途特征摘要
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
            title="Get Blend-File Usage Summary",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_usage_guess() -> dict[str, object]:
        """
        Guess the primary use-cases of the current blend file (scored 0-100 with certainty).
        """
        return send_code(toolcode_format_call(_TOOL_CALL, None), strict_json=True)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Blend-File Usage Summary for Command-Line",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_usage_guess_for_cli(blend_file: str) -> dict[str, object]:
        """
        Guess use-cases by opening *blend_file* in background Blender.
        """
        with synced_blend_for_cli(blend_file) as synced_path:
            return run_blender_cli(synced_path, toolcode_format_call(_TOOL_CALL, None))
