"""[OFF_TOOL_SEARCH_API] 官方 MCP 关键字检索 Blender Python API 工具定义 (search_api_docs)
- 适用 (When): 不确定精确 API 名称时按关键字搜索 `bpy` / `bmesh` 文档
- 用法 (How) : 直接调 MCP 工具 `search_api_docs`
- 产出 (Out) : 返回匹配的 API 条目列表
"""
# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=C0114  # See tool doc-string.

__all__ = (
    "register",
)

from blmcp.tools_helpers.rst_doc_search import (
    SEARCH_TOOL_DESCRIPTION,
    search,
    with_doc,
)
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Search API Docs",
            readOnlyHint=True,
        )
    )
    @with_doc(SEARCH_TOOL_DESCRIPTION.format(scope_name="Python API reference"))
    def search_api_docs(
        query: str,
        max_results: int = 20,
        context: int = 0,
        index: int | None = None,
    ) -> dict[str, object]:
        """
        Full-text search over the bundled Blender Python API reference.
        """
        return search(
            query=query,
            scope="api",
            max_results=max_results,
            context=context,
            index=index,
        )
