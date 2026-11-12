"""[OFF_TOOL_RENDER_VP] 官方 MCP 视口渲染落盘工具定义 (render_viewport_to_path)
- 适用 (When): 需将当前 3D 视口或相机视角渲染并保存为指定路径图像并自动缩放至尺寸上限
- 用法 (How) : 直接调 MCP 工具 `render_viewport_to_path`；底层实现见 `render_viewport_to_path_toolcode.py`
- 产出 (Out) : 在目标路径生成渲染图像文件并返回状态字典
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
from blmcp.tools.render_viewport_to_path_toolcode import Params
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Render Viewport to Path",
            readOnlyHint=True,
        )
    )
    def render_viewport_to_path(output_path: str) -> dict[str, object]:
        """
        Render the current scene to *output_path* using current render settings.
        """
        p = Params(output_path=output_path)
        code = toolcode_format_call(_TOOL_CALL, p)
        return send_code(code, strict_json=True)
