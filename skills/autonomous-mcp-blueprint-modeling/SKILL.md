---
name: autonomous-mcp-blueprint-modeling
description: Autonomous 3D CAD, architectural, and hard-surface modeling in Blender from multi-view blueprints and reference photos via full official Blender Lab MCP (all 26 tools via abmcp_mcp). Anchored on Building Spec JSON, rotated plan leveling, section slab detection, bmesh floor-cut IoU/rule verification, native RANDOM shading, and 3-tier structural profile fidelity.
---

# Autonomous MCP Blueprint & Reference Modeling (v1.4.1)

> 设变量 `$P=~/.gemini/config/plugins/abmcp`，工作目录 `$W=./agy_work`。本插件内置并启用 **Blender 官方 MCP 全部 26 项工具 (`abmcp_mcp`)** 与 **P0→P5 六阶段 + G1–G5 门禁**；上下文压缩后先跑 `spec_digest(); phase_next()`（`<=40+20` 行）恢复真源状态。

---

## 核心工作流：P0 – P5 六阶段与门禁

### P0 资产盘点与 Spec 初始化
- **场景与工程摸底（优先官方只读工具）**：操作现有场景或 `.blend` 前，先调 `get_blendfile_summary_path_info`、`get_blendfile_summary_datablocks`、`get_objects_summary`（离线文件用对应 `*_for_cli` 与 `get_blendfile_summary_missing_files_for_cli` / `get_blendfile_summary_of_linked_libraries_for_cli` / `get_blendfile_summary_usage_guess_for_cli`）确认单位、层级与资产状态。
- 分类输入图：**建筑平/立/剖 + 实景照片**走建筑通道（`plan_prep` + `spec_kit`）；**载具/机械/单体**跳至文末非建筑通道。
- 初始化 Spec：在本地/Blender 执行 `from spec_kit import *; spec_init(src="...")`。

### P1 定偏航 · 定比例 · 抓标高（**Gate G1**）
1. **斜置平面检出偏航**：
   `python3 $P/bin/plan_prep.py scan --input <plan.img> --out $W`
   查看 `$W/orient_candidates.png` 与 `$W/scan_sheet.png`，结合透视图南立面方向选定唯一角度 `<deg>`。
2. **裁切转正 + 精化 + 米制红蓝网**（单图多楼层加 `--layers`）：
   `python3 $P/bin/plan_prep.py build --input <plan.img> --angle <deg> --roi u0,v0,u1,v1 --refine --out $W`
3. **剖面楼板抓取与比例传递**：
   `python3 $P/bin/section_levels.py --input <sec.img> --elev z0,z1,... --mark $W/sec_mark.png --out-json $W/sec_meta.json`（杂波误判用 `--drop <v_px>`）
   `python3 $P/bin/plan_prep.py scale-from-section --meta $W/plan_meta.json --section-scale <s_sec> --section-span-px <Ls> --plan-span u0,v0,u1,v1 --update-spec $W/building_spec.json`（再用 `--scale` 重跑 `build` 生成米制 `$W/plan_roi.png`）。
4. **实景立面局部切片**：`python3 $P/bin/reference_detail_tiles.py --input <photo_or_plan_rot> --meta $W/plan_meta.json --outdir $W/tiles`。
5. **Gate G1 (`spec_validate`)**：写入 `frame.yaw_deg/scale_m_per_px` 与 `levels` (`id,z,slab,cut[,zone]`) 后 `spec_validate()` 零 `E_*` 错误方可进入 P2。

### P2 锁定各层外轮廓与立面虚实表（**Gate G2**）
- 读图先快查 `$P/skills/autonomous-mcp-blueprint-modeling/references/plan_reading_playbook.md` 与 `spec_schema.md`（防底层虚线投影误合并、未设 `zone` 错层冲突、内天井 `sub` 遗漏）。
- 用矩形并差 DSL 写入每层 `outline.<Lx>`（`union/add/sub` 或 `base+add+sub`），写入 `edge_rules`（`SOLID|GLAZED|OPEN|CANTILEVER|RECESS|STEP|LOUVER|SLAT`）及 `elements` 细部台账（`HEB220`、格栅、百叶、栏杆）。
- **Gate G2**：跑 `python3 $P/bin/plan_prep.py check-outline --meta $W/plan_meta.json --spec $W/building_spec.json --level L0` 校验边界支撑，并通过 `spec_validate()`。

### P3 分段建模 L1→L2→L3 与数值剖切门禁（**Gate G3**）
1. **API 查阅与场景初始化**：查未知 `bpy`/`bmesh` 签名先用 `get_python_api_docs` / `search_api_docs` / `search_manual_docs`。通过 `execute_blender_code` 开启原生 `RANDOM` 分色：`COR.setup_clean_scene()` + `COR.set_shading_color_mode('RANDOM')`。
2. **L1 宏观楼板与外围护**（在正交局部系建，保持 `Site_Yaw=0`）：
   调用 `CASE_R10` (`facade_kit.py`)：`build_all_levels()` 或逐层 `build_level_slab` + `build_envelope` + `add_cantilever`。
3. **L2/L3 真实型材与细部五金**：
   用 `CASE_R08` (`detail_kit.py`) 构造真实截面的 `add_steel_member("HEB220",...)`、`add_slat_array`、`add_louver_leaf`、`add_railing`、`add_window` 与檐口法兰，并运行 `DK.detail_audit()` + `DK.ledger_check()` 确认零 6 面方块冒充。检查单件属性优先 `get_object_detail_summary`，聚焦检查用 `jump_to_view3d_object_by_name` / `jump_to_view3d_object_data_by_name`。
4. **Gate G3（真几何水平剖切先行）**：
   调用 `CASE_R11`：`LCV.export_level_cuts()` → `res = LCV.verify_levels(tol_mm=150, iou_min=0.90)`。
   - **仅在失败层或终验确认时**渲染叠加图定损：
     `python3 $P/bin/level_plan_render.py --cuts $W/level_cuts.json --spec $W/building_spec.json --level L1 --plan $W/plan_rot.png --meta $W/plan_meta.json --verify $W/verify_L1.json --out $W/overlay_L1.png`
   - 发现问题后用 `CASE_R05` (`transform_component` / `replace_component_geometry`) 修复并重跑 `verify_levels` 直至全部 `PASS`。

### P4 多视图与节点微距视觉核验（**Gate G4**）
- 视口快览与工作区检查：可用 `jump_to_tab_by_name` / `jump_to_tab_by_space_type`、`get_screenshot_of_area_as_image`、`get_screenshot_of_window_as_image`、`get_screenshot_of_window_as_json`、`render_thumbnail_to_path`、`render_viewport_to_path`。
- 全景五机位 + 节点特写：调用 `CASE_R04` (`setup_workbench_studio_and_cameras(convention="plan_north_up", diagnostic_colors="RANDOM")`) 渲染多视图与 `render_closeup`，用 `bin/compose_triview_sheet.py` 拼图送入 `read_file` 审查；若修改构造须 `spec_patch()` + `spec_note()` 回写 Spec 并重过 `G3`。

### P5 材质赋予 · 现场偏航 · 交付（**Gate G5**）
1. `COR.finish_materials({"*Wall*": ..., "*Slab*": ...})` 赋予 PBR 材质并自动切换 `shading.color_type = 'MATERIAL'`；
2. `SK.apply_site_yaw()` 按 `spec.frame.yaw_deg` 挂载可逆偏航空物体 `Site_Yaw`（`verify_levels()` 在 `Site_Yaw` 下仍恒定通过）；
3. `CASE_R06` (`execute_grouping_in_blender`) 双层归档，调用 `render_viewport_to_path` / `CASE_R04` 渲染最终 `MATERIAL` 成图，保存 `.blend` 并可用 `execute_blender_code_for_cli` / `get_blendfile_summary_*_for_cli` 做离线无头终验。

---

## 官方 Blender MCP 26 项原生工具全集 (`abmcp_mcp`)

完整签名、参数及官方 `prompts.yml` 操作守则见 `$P/skills/autonomous-mcp-blueprint-modeling/references/official_mcp_tools_and_prompts.md`：
- **文档检索 (3)**：`get_python_api_docs`, `search_api_docs`, `search_manual_docs`
- **场景与工程摘要 (14)**：`get_objects_summary`, `get_object_detail_summary`, `get_blendfile_summary_datablocks[_for_cli]`, `get_blendfile_summary_missing_files[_for_cli]`, `get_blendfile_summary_of_linked_libraries[_for_cli]`, `get_blendfile_summary_path_info[_for_cli]`, `get_blendfile_summary_usage_guess[_for_cli]`
- **截图与渲染 (5)**：`get_screenshot_of_area_as_image`, `get_screenshot_of_window_as_image`, `get_screenshot_of_window_as_json`, `render_thumbnail_to_path`, `render_viewport_to_path`
- **工作区与视口定位 (4)**：`jump_to_tab_by_name`, `jump_to_tab_by_space_type`, `jump_to_view3d_object_by_name`, `jump_to_view3d_object_data_by_name`
- **代码执行 (2)**：`execute_blender_code`, `execute_blender_code_for_cli`（返回字典赋值给 `result`）

---

## 极速配方检索与上下文恢复

```bash
head -n 6 $P/examples/recipes/case_r*.py $P/bin/*.py $P/skills/autonomous-mcp-blueprint-modeling/references/*.md
```
- **核心配方表**：`R01` 场景/RANDOM染色 · `R02` BMesh流形体检 · `R03` 载具曲面算子 · `R04` 5机位+节点特写 · `R05` 位姿微调CRUD · `R06` 交付群组 · `R07` N面板/外部API · `R08` 钢型材/百叶/格栅/窗/台账 · **`R09`** `spec_kit` Spec状态机 · **`R10`** `facade_kit` 多孔楼板/免布尔开洞/悬挑错层 · **`R11`** `level_cut_verify` `z+cut`真几何剖切IoU验收。
- **非建筑通道（载具/机械）**：跳过 `plan_prep`/`section_levels`/`R10`/`R11`，用 `blueprint_grid_calib.py` 标定三视图、`reference_detail_tiles.py` 切细部、`R03`+`R08` 建模、`R04(convention="vehicle", diagnostic_colors="RANDOM")` 核验 + `finish_materials()` 交付。

---

## Flash 执行速览示例（斜置悬挑住宅）

```python
import sys; sys.path.insert(0, "/home/leo/.gemini/config/plugins/abmcp/examples/recipes")
import cad_operator_recipes as COR, detail_kit as DK, spec_kit as SK, facade_kit as FK, level_cut_verify as LCV
# P0-P2: cli 已转正+19.5deg 算得 scale=0.0565, 写入 building_spec.json 并通过 spec_validate()
COR.setup_clean_scene(); COR.set_shading_color_mode("RANDOM")
FK.build_all_levels(wall_t=0.28)
# P3: 添加外挑 L1 真实 HEB220 柱并校验 G3
bm = bmesh.new(); [DK.add_steel_member(bm, "HEB220", (x, y, 0.04), (x, y, 2.92)) for x, y in [(16.5,2.5),(16.5,7.5)]]
DK.finalize_object("HEB220_Cols", bm, COR.get_or_create_collection("L2_Envelope_Detail"))
assert COR.audit_scene_meshes()["passed"] and DK.detail_audit()["passed"]
print(LCV.verify_levels(tol_mm=150, iou_min=0.90)["report"])
# P4-P5: render_views/closeup -> finish_materials(...) -> SK.apply_site_yaw()
```
