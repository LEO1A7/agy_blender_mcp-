# AGENTS.md — AGY Autonomous MCP 3D Modeling (v1.4.0)

> 核心原则：**Spec 锚定 + CLI 卸载几何算术 + 按需渐进披露 (`head -n 6`) + 原生 `RANDOM` 分色 + `bmesh` 剖切数值验收**。严禁修改 `addon/` 与 `examples/official_blender_mcp/`。

1. **单一真源 (`building_spec.json`)**：全流程用 `CASE_R09` (`spec_kit`) 维护 `./agy_work/building_spec.json`。每轮开始或上下文恢复先跑 `spec_digest()` 与 `phase_next()` 恢复状态。
2. **局部正交系与延迟偏航**：建模全程在正交局部系（`+X` 东、`+Y` 北、`+Z` 上，`Site_Yaw = 0°`）执行；偏航记在 `spec.frame.yaw_deg`，仅 P5 交付前调用 `apply_site_yaw()` 挂载（可逆归零）。
3. **图纸预处理与确定性算术**：严禁心算斜图坐标。斜平面先跑 `bin/plan_prep.py`（`scan`→`build --refine` 转正并铺米制网格）；剖面跑 `bin/section_levels.py` 拟合层高比例；细部跑 `bin/reference_detail_tiles.py`；轮廓统一用矩形布尔 DSL (`union/add/sub` / `base+add+sub`) 转环与编号边 `E1..En`。
4. **先定轮廓再建模 + 三级递进 (`L1→L2→L3`)**：`L1` 建多孔楼板与免布尔开洞外墙（`CASE_R10`）；`L2` 外露钢构（`HEB220`/`HEA`/`IPE`/方管）、格栅、百叶、栏杆与窗框必用 `CASE_R08` 或 `bmesh` 真实截面挤出（禁 6 面方块冒充）；`L3` 补收口五金与错层踏步墙。
5. **原生 `RANDOM` 分色**：建模与核验保持 Blender 原生 `shading.color_type = 'RANDOM'` + `show_object_outline = True`；严禁覆写诊断调色板；P5 调用 `finish_materials()` 赋材并切 `'MATERIAL'`。
6. **数值剖切先行，叠加按需渲染 (G3)**：每层跑 `CASE_R11` (`export_level_cuts`→`verify_levels`, IoU `>=0.90`, 偏差 `<=150mm`)；仅失败或终验渲染 `bin/level_plan_render.py` 叠加图定损。
7. **渐进式披露与注意力预算**：先 `head -n 6` 扫描 `case_r*.py`、`bin/*.py`、`references/*.md` 再按需导入或切片读取；送入视觉图像长边 `<=1600 px`，CLI 标准输出 `<=20` 行。
8. **N 面板与双模兼容**：仅按需查阅 `CASE_R07` 访问视口选区或外部 AI 模型 API；载具/机械跳过 `plan_prep` 与楼层剖切，沿用 `blueprint_grid_calib.py`、`CASE_R03` 与 `CASE_R04(convention="vehicle")`。
