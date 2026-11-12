"""[REF_EXAMPLES_INDEX] Blender MCP 官方参考库与模块化 CAD 配方索引 (支持 head -n 6 快筛)
- 适用 (When): 需按需查找 Building Spec、板块开洞、楼层剖切验收、钢结构型材、5 机位摄影棚、N 面板桥接或 CLI 工具
- 用法 (How) : 先跑 `head -n 6 examples/recipes/case_r*.py bin/*.py` 扫描报文头，再按需导入或切片读取
- 产出 (Out) : 零上下文污染地定位 `CASE_R01`~`CASE_R11`、`bin/*.py` 与官方 `official_blender_mcp/` 核心实现
"""

# Blender MCP 官方参考库与模块化配方索引 (`examples/`)

所有模块化配方 (`examples/recipes/`)、CLI 脚本 (`bin/`)、参考文档 (`references/`) 与官方 Blender MCP 脚本 (`examples/official_blender_mcp/`，官方正文 100% 原样未动) 首部均配有 **6 行标准化报文头 (`When / How / Out`)**：

```bash
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/*.py
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/official_blender_mcp/mcp/blmcp/tools/*.py
```

---

## 1. 模块化 CAD / 建筑建造与验收配方 (`examples/recipes/case_r*.py`)

| 编号与文件 | 适用场景（`head -n 6` 可直读报文头） | 核心导出函数 / 一句话用法 |
| :--- | :--- | :--- |
| **`CASE_R01`** `recipes/case_r01_scene_and_diagnostic_colors.py` | 场景初始化、集合管理、零偏移父子挂载、原生 `RANDOM`/`MATERIAL` 着色切换与最终赋材 | `setup_clean_scene`, `set_shading_color_mode`, `finish_materials`, `create_mesh_object`, `set_parent_keep_world` |
| **`CASE_R02`** `recipes/case_r02_bmesh_topology_audit.py` | 纯 BMesh 检查非流形边、零面积退化面、孤立顶点、未归零缩放与法线反壳（负体积） | `audit_scene_meshes`, `audit_object_topology` |
| **`CASE_R03`** `recipes/case_r03_parametric_bmesh_builders.py` | 五大 BMesh 参数化构造：侧视拉伸、波浪侧裙、多面体壳、Y轴锥柱、闭合履带环 | `extrude_side_profile`, `build_wavy_skirt_panels`, `build_layered_polyhedral_shell`, `add_cyl_along_y`, `build_contoured_track_loop` |
| **`CASE_R04`** `recipes/case_r04_workbench_5cam_studio.py` | P4 自适应 5 机位 Workbench Cavity+Outline 摄影棚（双投影约定、原生 `RANDOM`/`MATERIAL` 与节点特写） | `setup_workbench_studio_and_cameras`, `compute_or_lock_iso_distance`, `render_views`, `render_closeup`, `describe_studio` |
| **`CASE_R05`** `recipes/case_r05_component_perception_crud.py` | 提取构件世界 AABB、零上下文位姿微调与保留材质槽的无损网格替换 | `inspect_scene_components`, `transform_component`, `replace_component_geometry`, `remove_components` |
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

## 3. 官方 Blender MCP 仓库索引 (`examples/official_blender_mcp/`)

源自 Blender 官方实验室（[projects.blender.org/lab/blender_mcp](https://projects.blender.org/lab/blender_mcp.git)），**官方正文保持 100% 原样未动**，首部配 `[OFF_*]` 6 行报文头：

| 报文头 ID | 对应官方文件路径 | 核心参考价值 |
| :--- | :--- | :--- |
| **`[OFF_README]`** | `official_blender_mcp/readme.md` | 官方 Blender MCP 架构总览与双端通信说明 |
| **`[OFF_TOOLS_DOC]`** | `official_blender_mcp/readme_tools.rst` | 官方原生 MCP 工具名称与参数速查手册 |
| **`[OFF_TOOL_EXEC]`** | `official_blender_mcp/mcp/blmcp/tools/execute_blender_code.py` | 官方 Python 执行协议、上下文封装与返回消息结构 |
| **`[OFF_CODE_OBJS]`** | `official_blender_mcp/mcp/blmcp/tools/get_objects_summary_toolcode.py` | 官方遍历场景集合树与提取对象状态的轻量写法 |
| **`[OFF_CODE_OBJ_DETAIL]`** | `official_blender_mcp/mcp/blmcp/tools/get_object_detail_summary_toolcode.py` | 官方提取网格顶点、面、材质与修改器配置的标准实现 |
| **`[OFF_CODE_RENDER_VP]`** | `official_blender_mcp/mcp/blmcp/tools/render_viewport_to_path_toolcode.py` | 官方视口渲染、属性备份恢复与多区域截图模式 |
| **`[OFF_TEST_BLENDER]`** | `official_blender_mcp/tests/test_blender_mcp_with_blender.py` | 官方与 Blender 交互的自动化测试用例与标准调用示范 |
