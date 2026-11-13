# 版本说明 — v1.4.1（`修复mcp工具完整性+N面板工具显示AI正在操作+v1.4.1`）

- **插件标识**：`abmcp`（`AGY Autonomous MCP 3D Modeling`）
- **版本号**：`1.4.1`
- **发布标签**：`修复mcp工具完整性+N面板工具显示AI正在操作+v1.4.1`
- **目标仓库**：`https://github.com/LEO1A7/agy_blender_mcp-`

---

## 一、核心更新摘要

### 1. 完整补齐并暴露官方 Blender Lab MCP 全部 26 项原生工具（`abmcp_mcp`）
- **还原官方上游源码纯净度**：将 `examples/official_blender_mcp/` 内此前被修改文件头的 42 个文件原样还原至官方 Blender Lab MCP 上游版本，与纯官方对照组完全一致。
- **补齐顶层 Blender 官方扩展**：将完整官方扩展 `addon/blender_mcp_addon/` 复制到仓库顶层 `addon/`，与 N 面板扩展 `addon/agy_blender_bridge.py` 并存。
- **独立 `.venv` 与 `mcp_config.json` 注册**：
  - 新增根级 `mcp_config.json`（服务键 `"mcp"`，启动本插件隔离 `.venv/bin/blender-mcp`，默认 `BLENDER_MCP_HOST=localhost`、`BLENDER_MCP_PORT=9875`、`BLENDER_PATH=/usr/local/bin/blender`）。
  - 更新 `plugin.json` 短名为 `"abmcp"`、版本 `"1.4.1"`，确保 Antigravity 生成的 `mcp_abmcp_mcp_<toolName>` 标识符最大长度严格 `<= 64` 字符（实测最长 63 字符：`mcp_abmcp_mcp_get_blendfile_summary_of_linked_libraries_for_cli`）。
- **全部 26 项工具清单**：
  - **文档检索（3）**：`get_python_api_docs`、`search_api_docs`、`search_manual_docs`
  - **实时场景与工程摘要（7）**：`get_objects_summary`、`get_object_detail_summary`、`get_blendfile_summary_datablocks`、`get_blendfile_summary_missing_files`、`get_blendfile_summary_of_linked_libraries`、`get_blendfile_summary_path_info`、`get_blendfile_summary_usage_guess`
  - **截图与渲染（5）**：`get_screenshot_of_area_as_image`、`get_screenshot_of_window_as_image`、`get_screenshot_of_window_as_json`、`render_thumbnail_to_path`、`render_viewport_to_path`
  - **工作区与视口定位（4）**：`jump_to_tab_by_name`、`jump_to_tab_by_space_type`、`jump_to_view3d_object_by_name`、`jump_to_view3d_object_data_by_name`
  - **代码执行与离线 CLI 后台能力（7）**：`execute_blender_code`、`execute_blender_code_for_cli` 及 5 项 `get_blendfile_summary_*_for_cli`

### 2. N 面板（`agy_blender_bridge.py`）与官方 MCP（`9875`）实时联动
- **自动挂钩官方 MCP 执行入口**：在 `addon/agy_blender_bridge.py` 的 `register()` 与 `_dshbb_ui_list_timer()` 中自动扫描并挂钩 `sys.modules` 中已加载的官方 `mcp_to_blender_server._execute_code`（`unregister()` 时完整还原，不修改任何官方扩展源码）。
- **实时点亮「AI 正在操作 Blender」**：通过 `abmcp_mcp`（端口 `9875`）执行任何工具时，自动进入 `UserEditRecorder.agent_command()` 并在结束/轮询时刷新 `note_agent_end()` 与 `_redraw_view3d_panels()`（含 `check_is_finished` 异步延迟任务），使 N 面板顶部实时亮起红色警示 **「AI 正在操作 Blender」**，同时避免 AI 改动选区被误判为人手操作。
- **「暂停 AI 操作」跨通道拦截**：在 N 面板点击「暂停 AI 操作」时，自动拦截来自 `9875` 的 `execute_blender_code`、工作区/视口跳转与渲染请求（返回 `AI_PAUSED` 错误），同时继续放行纯只读场景摘要与截图查询。
- **修复 UI 活动快照计数**：将 `_dshbb_ui_list_timer` 与 `DSHBB_PT_Panel._draw_impl` 的状态读取统一为 `snapshot(include_current_command=True)`，修复同步执行期间红色警告显示延迟/遗漏问题。

### 3. 文档与工作流规范集成
- 新增 `skills/autonomous-mcp-blueprint-modeling/references/official_mcp_tools_and_prompts.md`（收录 26 个官方工具签名、沙盒/延迟返回约束与官方 `prompts.yml` `initial_instructions`）。
- 更新 `rules/AGENTS.md`（14 行）、`skills/autonomous-mcp-blueprint-modeling/SKILL.md`（94 行）、`header_and_progressive_disclosure_spec.md`、`README.md`、`examples/README.md`、`npanel_bridge_and_apis.md`、`examples/recipes/detail_kit.py`。

---

## 二、安装与环境说明

1. **隔离 Python 环境**（`.venv/` 不入库）：
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e examples/official_blender_mcp/mcp
   ```
   确保 `mcp_config.json` 中的 `command` 指向本插件 `.venv/bin/blender-mcp`，`BLENDER_MCP_PORT` 与 Blender 官方扩展端口一致（默认 `9875`）。
2. **Blender 端扩展**：
   - 安装并启用 `addon/blender_mcp_addon/`（端口设 `9875`，开启 Online Access）。
   - 安装并启用 `addon/agy_blender_bridge.py`（N 面板与外部模型 API 桥接，默认端口 `9876`）。

---

## 三、验证记录（v1.4.1 实测通过）

- **插件静态与单测**：
  - `python3 tests/lint_plugin.py`：`22 code files checked | AGENTS=14L | SKILL=94L | errors=0 warnings=0`
  - `python3 tests/test_spec_kit.py` / `test_plan_prep.py` / `test_section_levels.py`：全部 `ALL PASS`
- **官方 MCP 合规与单元测试**（`examples/official_blender_mcp/`）：
  - `_misc/check_ascii.py`、`_misc/check_license.py`（57 个 SPDX 文件）、`_misc/check_namespace.py`（56 文件 0 错误）：全部通过
  - `../../.venv/bin/python -m unittest tests.test_tool_listing tests.test_rst_search tests.test_mcp_server`：95 tests `OK`
- **实时 Blender 5.2.1 联调实测**：
  - `abmcp_mcp` 全部 26 个工具实时调用通过（含 `execute_blender_code`、`*_for_cli` 后台模式、截图、渲染与视口跳转），JSON Schema 与 `blmcp_mcp` 0 差异。
  - N 面板 `DSH Blender Bridge` 实测：`execute_blender_code` 触发实时 `state="agent"` 红色 **`▲ AI 正在操作 Blender`** 警示且 `human_active=False`；开启暂停锁后 `execute_blender_code`/工作区切换返回 `AI_PAUSED`、纯只读查询正常放行。
