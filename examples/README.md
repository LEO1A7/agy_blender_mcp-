"""[REF_EXAMPLES_INDEX] Blender MCP 官方参考库与模块化 CAD 配方索引 (支持 head -n 6 快筛)
- 适用 (When): 需按需查找标准钢结构型材/建筑细部算子、BMesh 参数化算子、5 机位摄影棚、拓扑体检、群组归档、N 面板 API 桥接或官方 MCP 工具源码
- 用法 (How) : 先跑 `head -n 6 examples/recipes/case_r*.py` 或查阅下表，按需导入函数或切片读取
- 产出 (Out) : 零上下文污染地定位 `CASE_R01`~`CASE_R08` 与官方 `official_blender_mcp/` 核心实现
"""

# Blender MCP 官方参考库与模块化配方索引 (`examples/`)

本目录存放 **模块化 CAD 算子/细部型材/质检/N面板桥接配方 (`examples/recipes/`)** 与 **Blender 官方 MCP 脚本仓库 (`examples/official_blender_mcp/`)**。
所有文件顶部均配有 **6 行标准化报文头 (`When / How / Out`)**，模型可通过 `head -n 6` 极速扫描报文头决定是否调用内部内容，无需预先加载至上下文。

```bash
# 一键快筛全部模块化配方与工具报文头（仅耗 ~150 tokens）：
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/*.py
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/official_blender_mcp/mcp/blmcp/tools/*.py
```

---

## 1. 模块化 CAD 算子、型材细部库、群组兜底与 N 面板 API 配方 (`examples/recipes/case_r*.py`)

| 编号与文件 | 适用场景（`head -n 6` 可直读报文头） | 核心导出函数 / 一句话用法 |
| :--- | :--- | :--- |
| **`CASE_R01`** `recipes/case_r01_scene_and_diagnostic_colors.py` | 场景初始化、集合管理、零偏移父子挂载、跨领域通用多模块高对比度 `OBJECT` 诊断染色 | `setup_clean_scene`, `set_diagnostic_color_mode`, `create_mesh_object`, `set_parent_keep_world`, `GENERIC_GROUP_PALETTE` |
| **`CASE_R02`** `recipes/case_r02_bmesh_topology_audit.py` | 纯 BMesh 检查非流形边、零面积退化面、孤立顶点、未归零缩放与法线反壳（负体积） | `audit_scene_meshes`, `audit_object_topology` |
| **`CASE_R03`** `recipes/case_r03_parametric_bmesh_builders.py` | 五大 BMesh 参数化构造：侧视拉伸首尾收窄、波浪侧裙、平面四边面多面体壳、Y轴锥柱、闭合履带环 | `extrude_side_profile`, `build_wavy_skirt_panels`, `build_layered_polyhedral_shell`, `add_cyl_along_y`, `build_contoured_track_loop` |
| **`CASE_R04`** `recipes/case_r04_workbench_5cam_studio.py` | Stage 4 统一 5 机位 Workbench Cavity+Outline 摄影棚（支持载具与建筑北上平面双约定、自适应包围盒视距及局部节点特写） | `setup_workbench_studio_and_cameras`, `compute_or_lock_iso_distance`, `render_views`, `render_closeup`, `scene_bounds` |
| **`CASE_R05`** `recipes/case_r05_component_perception_crud.py` | 提取已建构件世界 AABB 包围盒/中心/尺寸、无上下文依赖原地位姿微调、保留材质槽的无损网格替换 | `inspect_scene_components`, `transform_component`, `replace_component_geometry`, `remove_components` |
| **`CASE_R06`** `recipes/case_r06_final_delivery_grouping.py` | 最终交付最后一步兜底：构建 `<Class>/<Class>_<Sub>` 交付群组与紧贴 `<Class>_WIP` 隐藏过程群组 | `execute_grouping_in_blender` |
| **`CASE_R07`** `recipes/case_r07_npanel_bridge_and_apis.py` | **Blender N 面板 (`DSH Blender Bridge` + `环境与角色模型API调用`) 协同桥接**（纯 MCP 下自动抑制 TCP 端口自启） | `ensure_npanel_registered`, `get_npanel_selection`, `list_npanel_api_status`, `call_npanel_api` |
| **`CASE_R08`** `recipes/case_r08_detail_profiles_and_ledger.py` | **标准钢结构型材库 (`HEB220`/`HEA`/`IPE`/`UPN`/方管/角钢)、木格栅阵列、倾斜百叶扇、栏杆、带框窗及细部防退化审计台账** | `add_steel_member`, `add_slat_array`, `add_louver_leaf`, `add_railing`, `add_window`, `ledger_set`, `ledger_check`, `detail_audit` |
| **`RECIPE_CAD_KIT`** `recipes/cad_operator_recipes.py` | `CASE_R01`~`CASE_R05` 的底层完整实现单文件合集（支持按函数定义字段切片读取） | `import cad_operator_recipes` |
| **`RECIPE_DETAIL_KIT`** `recipes/detail_kit.py` | `CASE_R08` 的底层完整型材截面放样、建筑细部阵列与防漏建台账单文件实现 | `import detail_kit` |

---

## 2. 官方 Blender MCP 仓库索引 (`examples/official_blender_mcp/`)

源自 Blender 官方实验室（[projects.blender.org/lab/blender_mcp](https://projects.blender.org/lab/blender_mcp.git)），**官方正文与源码保持 100% 原样未动**，仅在文件顶部添加 6 行 `[OFF_*]` 报文头便于 `head -n 6` 快速检索：

| 报文头 ID | 对应官方文件路径 | 核心参考价值 |
| :--- | :--- | :--- |
| **`[OFF_README]`** | `official_blender_mcp/readme.md` | 官方 Blender MCP 架构总览与双端通信说明 |
| **`[OFF_TOOLS_DOC]`** | `official_blender_mcp/readme_tools.rst` | 官方 23 项原生 MCP 工具名称与参数速查手册 |
| **`[OFF_TOOL_EXEC]`** | `official_blender_mcp/mcp/blmcp/tools/execute_blender_code.py` | 官方 Python 执行协议、上下文封装与返回消息结构 |
| **`[OFF_CODE_OBJS]`** | `official_blender_mcp/mcp/blmcp/tools/get_objects_summary_toolcode.py` | 官方遍历场景集合树与提取对象状态的轻量写法 |
| **`[OFF_CODE_OBJ_DETAIL]`** | `official_blender_mcp/mcp/blmcp/tools/get_object_detail_summary_toolcode.py` | 官方提取网格顶点、面、材质与修改器配置的标准实现 |
| **`[OFF_CODE_RENDER_VP]`** | `official_blender_mcp/mcp/blmcp/tools/render_viewport_to_path_toolcode.py` | 官方视口渲染、属性备份恢复与多区域截图模式 |
| **`[OFF_TEST_BLENDER]`** | `official_blender_mcp/tests/test_blender_mcp_with_blender.py` | 官方与 Blender 交互的自动化测试用例与标准调用示范 |
