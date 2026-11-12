"""[OFF_TOOL_DB_SUM] 官方 MCP 场景数据块统计摘要工具定义 (get_blendfile_summary_datablocks)
- 适用 (When): 需快速统计当前 `.blend` 中各类 datablock（meshes, materials, collections 等）数量
- 用法 (How) : 直接调 MCP 工具 `get_blendfile_summary_datablocks`
- 产出 (Out) : 返回非空数据块计数、当前工作区与渲染引擎名称
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
            title="Get Blend-File Data-blocks Summary",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_datablocks() -> dict[str, object]:
        """
        Return a summary of the blend file: data-block counts, active workspace, and render engine.
        """
        return send_code(toolcode_format_call(_TOOL_CALL, None), strict_json=True)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Blend-File Data-blocks Summary for Command-Line",
            readOnlyHint=True,
        )
    )
    def get_blendfile_summary_datablocks_for_cli(blend_file: str) -> dict[str, object]:
        """
        Return a data-block summary by opening *blend_file* in background Blender.
        """
        with synced_blend_for_cli(blend_file) as synced_path:
            return run_blender_cli(synced_path, toolcode_format_call(_TOOL_CALL, None))
