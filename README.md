# AGY Autonomous MCP 3D Modeling Plugin (`abmcp` · `agy-autonomous-mcp-modeling-plugin` v1.4.2)

> **设计理念**：完整集成 **Blender 官方 Lab MCP 全部 26 项原生能力 (`abmcp_mcp`)** 与 **Spec 驱动自主 CAD/建筑建模流水线**。通过插件自带隔离 `.venv` 与 `mcp_config.json`（短名 `abmcp` + 服务键 `mcp` → `abmcp_mcp`，全部 26 个工具标识符严格 `<= 63` 字符）直接提供官方 MCP 服务端与双扩展 `addon/blender_mcp_addon/` + `addon/agy_blender_bridge.py`；并以 `./agy_work/building_spec.json` 锚定全局坐标，通过 CLI 工具卸载几何算术、原生 `RANDOM` 着色 + `bmesh` 水平剖切验收实现高保真三维建模。

---

## 1. v1.4.2 核心集成与能力

1. **完整官方 Blender Lab MCP 服务 (`abmcp_mcp`，26 工具全覆盖)**：
   - 插件根目录直接通过 `mcp_config.json` 启动本地隔离 `.venv/bin/blender-mcp`，将官方上游 `examples/official_blender_mcp/`（`dbbf836` 原版未改动）全部 26 项工具注入 Antigravity（端口默认 `BLENDER_MCP_PORT=9875`，与默认 `9876` 的 N 面板插件隔离共存）：
     - **文档检索 (3)**：`get_python_api_docs`, `search_api_docs`, `search_manual_docs`
     - **场景与工程摘要 (14)**：`get_objects_summary`, `get_object_detail_summary`, `get_blendfile_summary_{datablocks,missing_files,of_linked_libraries,path_info,usage_guess}` 及对应 5 个无头 `*_for_cli`
     - **截图与渲染 (5)**：`get_screenshot_of_{area_as_image,window_as_image,window_as_json}`, `render_thumbnail_to_path`, `render_viewport_to_path`
     - **工作区与视口定位 (4)**：`jump_to_tab_by_name`, `jump_to_tab_by_space_type`, `jump_to_view3d_object_by_name`, `jump_to_view3d_object_data_by_name`
     - **Python 执行 (2)**：`execute_blender_code`, `execute_blender_code_for_cli`
   - 顶层 `addon/` 同时提供官方 `addon/blender_mcp_addon/`（接入 MCP 服务，需在 Blender 插件首选项设定端口与 `BLENDER_MCP_PORT` 一致，如 `9875`）与 `addon/agy_blender_bridge.py`（N 面板“暂停 AI 操作”/“发送选中到 AGY”及外部资产/AI 模型 API 桥接）。
2. **Building Spec 单一真源与矩形布尔 DSL (`CASE_R09` `spec_kit.py`)**：
   - 将偏航角 `yaw_deg`、比例尺 `scale_m_per_px`、分区分层 `levels`（支持错层 `zone`）、`outline`（矩形并差 `union/add/sub` + `base+add+sub` 层间增量）、`edge_rules`（`SOLID|GLAZED|OPEN|CANTILEVER|RECESS|STEP|LOUVER|SLAT`）与细部台账集中持久化至 `building_spec.json`；
   - 通过 `spec_digest()`（`<=40` 行）与 `phase_next()`（`<=20` 行）在轮次切换或上下文压缩后无损恢复状态。
3. **斜置平面转正、剖面拟合与米制红蓝网 (`bin/plan_prep.py` · `bin/section_levels.py`)**：
   - 正交建筑图纸先经 `plan_prep.py` 自动扫描主轴偏航角（`scan`），裁切转正并精化角度（`build --refine`），铺设局部正交米制坐标网格（图片长边 `<= 1600 px`）；
   - `section_levels.py` 自动识别剖面水平楼板条带、最小二乘拟合层高与比例并支持 `scale-from-section` 跨图传递比例；透视立面高密切片配合 `reference_detail_tiles.py` 与 `plan_meta.json` 定标。
4. **Spec 驱动多孔流形楼板与免布尔板块外墙 (`CASE_R10` `facade_kit.py` + `CASE_R08` `detail_kit.py`)**：
   - 建模全程在局部正交系（`Site_Yaw = 0°`）分段按 **L1 体块 ➔ L2 型材/表皮 ➔ L3 五金收口** 推进，P5 交付时再通过 `apply_site_yaw()` 挂载可逆偏航空物体；
   - 结构钢柱/梁（`HEB220`/`HEA`/`IPE`/方管）、菱形格栅、倾斜百叶扇、栏杆与窗框均构建真实闭合截面。
5. **Blender 原生 `RANDOM` 分色 + `bmesh` 真几何楼层剖切 + 重叠穿模自动隐藏重生成 + 两轮 VLM 视觉验收 (`CASE_R02/R04/R05/R11`)**：
   - 建模与初验保持 Blender 原生 `shading.color_type = 'RANDOM'` + 轮廓线；`audit_scene_meshes(check_clashes=True)` / `audit_and_regenerate()` 自动检出非流形、自交及跨构件重叠穿模并隐藏不良件 (`__hide_r<N>__`) 原位重生成；
   - 全流程任何验收发现问题统一执行“隐藏不良构件 + 原位重新生成 + 重新验收”；P4 视觉验收先跑第 1 轮着色模式截图 (`r1_shaded`)，通过后再跑第 2 轮 `BLENDER_EEVEE` 实际光照渲染 (`r2_lit`) 复验一轮。

---

## 2. 安装与启用

1. 在 Blender 中安装并启用 `addon/blender_mcp_addon/`（端口设与 `mcp_config.json` 中 `BLENDER_MCP_PORT` 一致，默认 `9875`，并在 Blender 偏好设置开启 Online Access），可选安装 `addon/agy_blender_bridge.py` 获取 N 面板控制。
2. 将本仓库链接为 Antigravity 短名插件 `abmcp`（避免长插件名触发 64 字符工具 schema 截断）：
   ```bash
   ln -s "$(pwd)" ~/.gemini/config/plugins/abmcp
   ```
3. 在本仓库创建隔离 `.venv` 并以可编辑模式安装官方 `examples/official_blender_mcp/mcp/`（已完成可跳过）：
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e ./examples/official_blender_mcp/mcp
   ```

---

## 3. 插件目录结构

```text
agy-autonomous-mcp-modeling-plugin/   (symlink ~/.gemini/config/plugins/abmcp)
├── plugin.json                                           # Antigravity 插件清单 (name: "abmcp", v1.4.2)
├── mcp_config.json                                       # 本地隔离 .venv 官方 blender-mcp 服务注册 (abmcp_mcp)
├── .venv/                                                # 隔离 Python 环境 (.venv/bin/blender-mcp)
├── README.md                                             # 架构说明与安装指南（本文件）
├── addon/
│   ├── blender_mcp_addon/                                # 官方 Blender Lab MCP 扩展 (与 examples 一致)
│   └── agy_blender_bridge.py                             # Blender N 面板与外部资产/AI 模型 API 桥接插件
├── assets/
│   └── logo.svg                                          # 插件图标
├── rules/
│   └── AGENTS.md                                         # 10 条建模与官方 MCP 宪法 (<=40行)
├── skills/
│   └── autonomous-mcp-blueprint-modeling/
│       ├── SKILL.md                                      # P0–P5 + G1–G5 + 官方 26 工具行动手册 (<=150行)
│       └── references/
│           ├── official_mcp_tools_and_prompts.md         # [REF_OFFICIAL_MCP] 官方 26 工具签名与 prompts.yml 原文
│           ├── plan_reading_playbook.md                  # [REF_PLAN_PLAYBOOK] 平立剖与实景读图核对清单
│           ├── spec_schema.md                            # [REF_SPEC_SCHEMA] building_spec.json 与边规则/错误码字典
│           ├── header_and_progressive_disclosure_spec.md # [REF_HEADER_SPEC] 6 行报文头规范
│           └── npanel_bridge_and_apis.md                 # [REF_NPANEL_BRIDGE] N 面板与外部 API 说明
├── bin/                                                  # plan_prep, section_levels, level_plan_render 等 CLI 工具
├── examples/
│   ├── README.md                                         # [REF_EXAMPLES_INDEX] 配方、CLI 与官方 MCP 索引
│   ├── official_blender_mcp/                             # 官方 Blender MCP 仓库 (dbbf836 100% 原样未动)
│   └── recipes/                                          # CASE_R01~CASE_R11 模块化 CAD 配方与底层 kit
└── tests/                                                # lint_plugin, test_plan_prep, test_section_levels, test_spec_kit, test_blender_suite
```
