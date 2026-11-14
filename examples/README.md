"""[REF_EXAMPLES_INDEX] Blender MCP 官方参考库与模块化 CAD 配方索引 (支持 head -n 6 快筛)
- 适用 (When): 需按需查找 Building Spec、板块开洞、楼层剖切验收、钢结构型材、5 机位摄影棚、N 面板桥接或官方 MCP 仓库
- 用法 (How) : 先跑 `head -n 6 examples/recipes/case_r*.py bin/*.py` 扫描报文头，再按需导入或切片读取
- 产出 (Out) : 零上下文污染地定位 `CASE_R01`~`CASE_R11`、`bin/*.py` 与官方 `official_blender_mcp/` 核心实现
"""

# Blender MCP 官方参考库与模块化配方索引 (`examples/`)

所有模块化配方 (`examples/recipes/`)、CLI 脚本 (`bin/`) 与参考文档 (`skills/autonomous-mcp-blueprint-modeling/references/`) 首部均配有 **6 行标准化报文头 (`When / How / Out`)**；`examples/official_blender_mcp/` 为官方 Blender Lab 仓库（100% 原生无改动）：

```bash
head -n 6 ~/.gemini/config/plugins/abmcp/examples/recipes/case_r*.py
head -n 6 ~/.gemini/config/plugins/abmcp/bin/*.py
head -n 6 ~/.gemini/config/plugins/abmcp/skills/autonomous-mcp-blueprint-modeling/references/*.md
```

---

## 1. 模块化 CAD / 建筑建造与验收配方 (`examples/recipes/case_r*.py`)

| 编号与文件 | 适用场景（`head -n 6` 可直读报文头） | 核心导出函数 / 一句话用法 |
| :--- | :--- | :--- |
| **`CASE_R01`** `recipes/case_r01_scene_and_diagnostic_colors.py` | 场景初始化、集合管理、零偏移父子挂载、原生 `RANDOM`/`MATERIAL` 着色切换与最终赋材 | `setup_clean_scene`, `set_shading_color_mode`, `finish_materials`, `create_mesh_object`, `set_parent_keep_world` |
| **`CASE_R02`** `recipes/case_r02_bmesh_topology_audit.py` | 纯 BMesh 流形/自交体检、BVHTree 跨构件重叠穿模检测、自动隐藏不良件并原位重生成 | `audit_scene_meshes`, `audit_object_topology`, `audit_scene_clashes`, `audit_and_regenerate` |
| **`CASE_R03`** `recipes/case_r03_parametric_bmesh_builders.py` | 五大 BMesh 参数化构造：侧视拉伸、波浪侧裙、多面体壳、Y轴锥柱、闭合履带环 | `extrude_side_profile`, `build_wavy_skirt_panels`, `build_layered_polyhedral_shell`, `add_cyl_along_y`, `build_contoured_track_loop` |
| **`CASE_R04`** `recipes/case_r04_workbench_5cam_studio.py` | P4 两阶段 VLM 视觉验收摄影棚（第1轮 Workbench 着色截图 `r1_shaded` + 第2轮 EEVEE 实光渲染 `r2_lit` + 特写） | `setup_workbench_studio_and_cameras`, `setup_lit_studio`, `render_views`, `render_lit_views`, `render_vlm_verification_views`, `render_closeup` |
| **`CASE_R05`** `recipes/case_r05_component_perception_crud.py` | 提取构件世界 AABB、隐藏不良件 (`__hide_r<N>__`) 与原位重新生成、无损网格替换 | `inspect_scene_components`, `hide_defective_components`, `regenerate_component_in_place`, `audit_and_regenerate`, `replace_component_geometry` |
| **`CASE_R06`** `recipes/case_r06_final_delivery_grouping.py` | P5 最终交付群组与隐藏过程归档 | `execute_grouping_in_blender` |
| **`CASE_R07`** `recipes/case_r07_npanel_bridge_and_apis.py` | Blender N 面板 (`DSH Blender Bridge`) 选中读取与外部资产/AI 模型 API 按需桥接 | `ensure_npanel_registered`, `get_npanel_selection`, `list_npanel_api_status`, `call_npanel_api` |
| **`CASE_R08`** `recipes/case_r08_detail_profiles_and_ledger.py` | 标准钢型材 (`HEB220`/`HEA`/`IPE`/`UPN`/方管/角钢)、木格栅、百叶扇、栏杆、窗框与细部审计台账 | `add_steel_member`, `add_slat_array`, `add_louver_leaf`, `add_railing`, `add_window`, `ledger_set`, `ledger_check`, `detail_audit` |
| **`CASE_R09`** `recipes/case_r09_building_spec.py` | **v1.4 Spec 状态机**：`building_spec.json` 读写、矩形布尔转环、CW 边编号、`<=40` 行摘要与可逆 `Site_Yaw` | `spec_init`, `spec_load`, `spec_patch`, `resolve_outline`, `outline_edges`, `spec_validate`, `spec_digest`, `phase_next`, `apply_site_yaw` |
| **`CASE_R10`** `recipes/case_r10_massing_envelope.py` | **v1.4 Spec 驱动建模**：多孔/悬挑流形楼板、免布尔开洞外墙、缩回/踏步/表皮封装 | `build_level_slab`, `wall_with_openings`, `build_envelope`, `add_cantilever`, `build_level`, `build_all_levels` |
| **`CASE_R11`** `recipes/case_r11_level_cut_verify.py` | **v1.4 真几何剖切验收**：`bmesh.ops.bisect_plane` 逐层切片、纯 NumPy 奇偶填充与 IoU/边偏差/虚实报告 | `export_level_cuts`, `verify_levels` |
| 底层实现库 | `cad_operator_recipes.py` · `detail_kit.py` · `spec_kit.py` · `facade_kit.py` · `level_cut_verify.py` | 模块化配方底层合集（按需切片读取） |

---

## 2. 预处理、标定与验收 CLI 工具 (`bin/*.py`)

| 脚本 | 核心能力 |
| :--- | :--- |
| `bin/plan_prep.py` | `scan` 自动偏航角候选、`build` 裁切转正 + 精化 + 米制红蓝网格、`px2m` / `scale-from-section`、`check-outline` 轮廓叠合校验 |
| `bin/section_levels.py` | 水平楼板条带抓取、人工 `--drop` 排扰、最小二乘高程标定与比例尺传递 JSON |
| `bin/level_plan_render.py` | `level_cuts.json` + `verify_L*.json` 剖切矢量叠加转正底图（仅失败层或终验渲染，`<=1600px`） |
| `bin/reference_detail_tiles.py` | 高梯度实景局部 slices + `plan_meta.json` 米制 ROI 坐标标注切片表 |
| `bin/blueprint_grid_calib.py` | 非建筑/正交三视图半透明红蓝像素坐标网格与 `--crop` 放大（纯参考校准） |
| `bin/compose_triview_sheet.py` | 多视图总览 (`mode=sheet`)、1:1 边缘叠合 (`mode=overlay`) 与高密拼图 (`mode=grid`) |

---

## 3. 官方 Blender MCP 仓库 (`examples/official_blender_mcp/`)

源自 Blender 官方实验室（[projects.blender.org/lab/blender_mcp](https://projects.blender.org/lab/blender_mcp.git)，commit `dbbf836`），**保持 100% 原样未动**，并通过根目录 `mcp_config.json` 与 `.venv/bin/blender-mcp` 作为插件内置服务 `abmcp_mcp` 运行：

| 目录 / 文件 | 用途 |
| :--- | :--- |
| `official_blender_mcp/mcp/` | 官方 Python MCP 服务端（26 个原生工具 + 随包 Blender 5.2 API 与手册 RST 库） |
| `official_blender_mcp/addon/blender_mcp_addon/` | 官方 Blender 5.1+ MCP TCP 桥接扩展（同步一份至顶层 `addon/blender_mcp_addon/`） |
| `official_blender_mcp/readme_tools.rst` | 官方 26 项 MCP 工具名称与说明（完整中文签名表见 `references/official_mcp_tools_and_prompts.md`） |
| `official_blender_mcp/mcp/blmcp/data/prompts.yml` | 官方 `initial_instructions` 与 Blender 数据块/上下文规则 |
| `official_blender_mcp/tests/` | 官方单测与端到端 Blender 集成测试集 |
