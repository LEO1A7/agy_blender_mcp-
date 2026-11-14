# AGENTS.md — AGY Autonomous MCP 3D Modeling (v1.4.2 · Official MCP Full Parity)

> 核心原则：**官方 26 工具全能力 + Spec 锚定 + CLI 卸载几何算术 + 按需渐进披露 (`head -n 6`) + 原生 `RANDOM` 分色 + `bmesh` 剖切数值验收**。严禁修改 `addon/` 与 `examples/official_blender_mcp/`。

1. **单一真源 (`building_spec.json`)**：全流程用 `CASE_R09` (`spec_kit`) 维护 `./agy_work/building_spec.json`。每轮开始或上下文恢复先跑 `spec_digest()` 与 `phase_next()` 恢复状态。
2. **局部正交系与延迟偏航**：建模全程在正交局部系（`+X` 东、`+Y` 北、`+Z` 上，`Site_Yaw = 0°`）执行；偏航记在 `spec.frame.yaw_deg`，仅 P5 交付前调用 `apply_site_yaw()` 挂载（可逆归零）。
3. **图纸预处理与确定性算术**：严禁心算斜图坐标。斜平面先跑 `bin/plan_prep.py`（`scan`→`build --refine` 转正并铺米制网格）；剖面跑 `bin/section_levels.py` 拟合层高比例；细部跑 `bin/reference_detail_tiles.py`；轮廓统一用矩形布尔 DSL (`union/add/sub` / `base+add+sub`) 转环与编号边 `E1..En`。
4. **先定轮廓再建模 + 三级递进 (`L1→L2→L3`)**：`L1` 建多孔楼板与免布尔开洞外墙（`CASE_R10`）；`L2` 外露钢构（`HEB220`/`HEA`/`IPE`/方管）、格栅、百叶、栏杆与窗框必用 `CASE_R08` 或 `bmesh` 真实截面挤出（禁 6 面方块冒充）；`L3` 补收口五金与错层踏步墙。
5. **原生 `RANDOM` 分色**：建模与核验保持 Blender 原生 `shading.color_type = 'RANDOM'` + `show_object_outline = True`；严禁覆写诊断调色板；P5 调用 `finish_materials()` 赋材并切 `'MATERIAL'`。
6. **数值剖切先行，叠加按需渲染 (G3)**：每层跑 `CASE_R11` (`export_level_cuts`→`verify_levels`, IoU `>=0.90`, 偏差 `<=150mm`)；仅失败或终验渲染 `bin/level_plan_render.py` 叠加图定损。
7. **重叠穿模自动检测 · 统一隐藏并原位重生成铁律**：建模与任何验收前必跑 `CASE_R02` (`audit_scene_meshes(check_clashes=True)` / `audit_scene_clashes` / `audit_and_regenerate`) 检出非流形、自交及跨构件重叠穿模；**无论在任何验收（拓扑/穿模、G3 剖切、台账或 G4 视觉）发现不对，严禁直接修改原件，统一执行“隐藏不良构件 (`hide_defective_components`→`__hide_r<N>__`) + 原位重新生成正确构件 (`regenerate_component_in_place`) + 重新验收”**。
8. **两阶段 VLM 视觉验收 (G4)**：第 1 轮先用着色模式截图（Workbench `RANDOM` + 轮廓线，`render_vlm_verification_views(round_stage="r1_shaded")` / `get_screenshot_of_area_as_image`）验收几何与轮廓；**第 1 轮通过后再用第 2 轮带实际光照的渲染图**（`BLENDER_EEVEE` 三点太阳光 + 环境光 + PBR 材质，`render_vlm_verification_views(round_stage="r2_lit")` / `render_viewport_to_path`）验收一轮。
9. **渐进式披露与注意力预算**：先 `head -n 6` 扫描 `case_r*.py`、`bin/*.py`、`references/*.md` 再按需导入或切片读取；送入视觉图像长边 `<=1600 px`，CLI 标准输出 `<=20` 行。
10. **N 面板与双模兼容**：仅按需查阅 `CASE_R07` 访问视口选区或外部 AI 模型 API；载具/机械跳过 `plan_prep` 与楼层剖切，沿用 `blueprint_grid_calib.py`、`CASE_R03` 与 `CASE_R04(convention="vehicle")`。
11. **官方 MCP 26 工具全能力与优先级**：优先调官方专用工具，`execute_blender_code` / `execute_blender_code_for_cli` 仅用于无专用工具或执行建模脚本（用 `result = {...}` 返回字典）。场景/`.blend` 盘点用 `get_objects_summary`、`get_object_detail_summary`、`get_blendfile_summary_{datablocks,missing_files,of_linked_libraries,path_info,usage_guess}`（及 5 个离线 `*_for_cli`）；查 `bpy`/`bmesh` API 与手册用 `get_python_api_docs`、`search_api_docs`、`search_manual_docs`；视口/窗口预览与快渲用 `get_screenshot_of_{area_as_image,window_as_image,window_as_json}`、`render_{thumbnail,viewport}_to_path`；工作区/视口定位用 `jump_to_{tab_by_name,tab_by_space_type,view3d_object_by_name,view3d_object_data_by_name}`。
12. **官方 Blender 数据块与上下文守则 (`prompts.yml`)**：改动前先检查现有结构与命名，禁未经确认破坏性修改；区分 Object 与 Data-block（改共享网格前查 `users`）、`active_object` 与 `selected_objects` 及三种可见性（Viewport / View Layer / Render）；先确认 Mode 与 `rotation_mode`；布尔前应用非均匀缩放并更新 depsgraph；Edit 模式 `bmesh` 须 flush 回网格；避免 `WeakSandboxForLLM` 禁用的 `wm.read_factory_settings`（改用 `read_homefile`）。
