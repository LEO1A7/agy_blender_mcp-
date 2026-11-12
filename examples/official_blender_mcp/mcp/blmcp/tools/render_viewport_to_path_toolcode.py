"""[OFF_CODE_RENDER_VP] 官方 MCP 视口/相机渲染与属性安全备份恢复的 Blender 端源码
- 适用 (When): 需参考官方如何在渲染前后无损备份并恢复 `scene.render` 参数及延迟检查输出文件
- 用法 (How) : 按需读取 `main()` 实现（原文件只读）
- 产出 (Out) : 安全执行视口渲染并将结果写入 `output_path`
"""
# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tool-code for rendering the current scene.
"""

__all__ = (
    "Params",
    "Result",
    "main",
)

from collections.abc import Callable
from typing import NamedTuple


class Params(NamedTuple):
    output_path: str


class Result(NamedTuple):
    status: str
    filepath: str | None = None
    message: str | None = None


# @include_begin: _template_deferred_tool_check_for_file_output.py
def _deferred_tool_check_for_file_output(
        job_type: str,
        output_path: str,
        restore_attrs: list[tuple[object, str, object]] | None = None,
) -> Callable[[], dict[str, object] | None]:
    return lambda: None
# @include_end


def main(params: Params) -> Result | Callable[[], dict[str, object] | None]:
    import os
    import bpy  # pylint: disable=import-error,no-name-in-module

    use_deferred = not bpy.app.background

    # Resolve the output path inside the MCP scratch directory.
    output_path = os.path.join(bpy.app.tempdir, "blender_mcp", os.path.basename(params.output_path))

    scene = bpy.context.scene

    # NOTE: `filepath` is set manually (not via context manager) because
    # `write_still` reads it after the render completes.
    # With `INVOKE_DEFAULT` a context manager would restore it too early.
    rd = scene.render
    orig_filepath = rd.filepath
    rd.filepath = output_path

    render_args = ('INVOKE_DEFAULT',) if use_deferred else ()

    try:
        bpy.ops.render.render(*render_args, write_still=True)
    except RuntimeError as ex:
        rd.filepath = orig_filepath
        return Result(status="error", message=str(ex))

    if use_deferred:
        return _deferred_tool_check_for_file_output(
            'RENDER', output_path, restore_attrs=[(rd, "filepath", orig_filepath)],
        )

    rd.filepath = orig_filepath
    return Result(status="ok", filepath=output_path)
