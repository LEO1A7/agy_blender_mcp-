# AGY Autonomous MCP 3D Modeling Plugin (`agy-autonomous-mcp-modeling-plugin` v1.4.0)

> **设计理念**：面向单 Agent 多轮执行与轻量化模型（Flash LLM）打造的高保真自主建模插件。以单一真源 `./agy_work/building_spec.json` 锚定全局坐标与标高，通过 CLI 工具卸载旋转/比例/布尔转环/剖切验收等几何算术，全程沿用 Blender 原生 `RANDOM` 着色 + `finish_materials()` 材质切换与 6 行报文头渐进式披露，在严控上下文注意力的同时杜绝斜置错位、虚实混淆、悬挑遗漏与方块退化。

---

## 1. v1.4.0 核心设计升级

1. **Building Spec 单一真源与矩形布尔 DSL (`CASE_R09` `spec_kit.py`)**：
   - 将偏航角 `yaw_deg`、比例尺 `scale_m_per_px`、分区分层 `levels`（支持错层 `zone`）、`outline`（矩形并差 `union/add/sub` + `base+add+sub` 层间增量）、`edge_rules`（`SOLID|GLAZED|OPEN|CANTILEVER|RECESS|STEP|LOUVER|SLAT`）与细部台账集中持久化至 `building_spec.json`；
   - 通过 `spec_digest()`（`<=40` 行）与 `phase_next()`（`<=20` 行）在轮次切换或上下文压缩后无损恢复状态。
2. **斜置平面转正、剖面拟合与米制红蓝网 (`bin/plan_prep.py` · `bin/section_levels.py`)**：
   - 正交建筑图纸先经 `plan_prep.py` 自动扫描主轴偏航角（`scan`），裁切转正并精化角度（`build --refine`），铺设局部正交米制坐标网格（所有图片长边 `<= 1600 px`）；
   - `section_levels.py` 自动识别剖面水平楼板条带、最小二乘拟合层高与比例并支持 `scale-from-section` 跨图传递比例；透视立面高密切片配合 `reference_detail_tiles.py` 与 `plan_meta.json` 定标。
3. **Spec 驱动多孔流形楼板与免布尔板块外墙 (`CASE_R10` `facade_kit.py` + `CASE_R08` `detail_kit.py`)**：
   - 建模全程在局部正交系（`Site_Yaw = 0°`）分段按 **L1 体块 ➔ L2 型材/表皮 ➔ L3 五金收口** 推进，P5 交付时再通过 `apply_site_yaw()` 挂载可逆偏航空物体；
   - 以窗间墙+窗台+过梁板块分解构建流形开洞墙体，杜绝布尔碎片；结构钢柱/梁（`HEB220`/`HEA`/`IPE`/方管）、菱形格栅、倾斜百叶扇、栏杆与窗框均构建真实闭合截面。
4. **Blender 原生 `RANDOM` 分色 + `bmesh` 真几何楼层剖切验收 (`CASE_R11` + `bin/level_plan_render.py`)**：
   - 弃用额外 `OBJECT` 诊断调色板与物体属性色覆盖：建模与几何核验期保持 Blender 原生 `shading.color_type = 'RANDOM'` + 对象轮廓线，P5 赋材后调用 `finish_materials()` 自动切至 `'MATERIAL'`；
   - 用 `bmesh.ops.bisect_plane` 沿每层 `z + cut` 真几何剖切，经纯 NumPy 奇偶扫描线计算 **包络 IoU（`>=0.90`）、外墙偏移误差（`<=150mm`）与虚实 rule 覆盖率**，仅在 Gate G3 失败或终验时按需渲染矢量叠合图。
5. **渐进式披露与 N 面板继承**：
   - 全部 `examples/recipes/case_r*.py`、`bin/*.py`、`references/*.md` 与 `examples/official_blender_mcp/` 配标准化 6 行 `When / How / Out` 报文头支持 `head -n 6` 快筛；
   - 原样保留 `addon/agy_blender_bridge.py` 与 `examples/official_blender_mcp/`，仅按需通过 `CASE_R07` 调用视口选区或外部资产/AI 模型 API。

---

## 2. 插件目录结构

```text
agy-autonomous-mcp-modeling-plugin/
├── plugin.json                                           # Antigravity 插件清单 (v1.4.0)
├── README.md                                             # 架构说明与设计理念（本文件）
├── addon/
│   └── agy_blender_bridge.py                             # 继承的 Blender 内部 N 面板与外部资产/AI 模型 API 桥接插件
├── assets/
│   └── logo.svg                                          # 插件图标
├── rules/
│   └── AGENTS.md                                         # 8 条轻量建模宪法 (<=40行)
├── skills/
│   └── autonomous-mcp-blueprint-modeling/
│       ├── SKILL.md                                      # P0–P5 六阶段 + G1–G5 门禁行动手册 (<=150行)
│       └── references/
│           ├── plan_reading_playbook.md                  # [REF_PLAN_PLAYBOOK] 平立剖与实景读图核对清单
│           ├── spec_schema.md                            # [REF_SPEC_SCHEMA] building_spec.json 与边规则/错误码字典
│           ├── header_and_progressive_disclosure_spec.md # [REF_HEADER_SPEC] 6 行报文头规范
│           └── npanel_bridge_and_apis.md                 # [REF_NPANEL_BRIDGE] N 面板与外部 API 说明
├── bin/
│   ├── plan_prep.py                                      # [BIN_PLAN_PREP] 偏航扫描/裁切转正/精化/米制网格/轮廓叠合
│   ├── section_levels.py                                 # [BIN_SECTION_LEVELS] 剖面楼板抓取/高程拟合/比例计算
│   ├── level_plan_render.py                              # [BIN_LEVEL_RENDER] 剖切矢量与转正底图叠加验收渲染
│   ├── blueprint_grid_calib.py                           # [BIN_GRID_CALIB] 正交三视图红蓝像素网格标定
│   ├── reference_detail_tiles.py                         # [BIN_DETAIL_TILES] 高密度细部切片与 ROI 米制坐标表
│   └── compose_triview_sheet.py                          # [BIN_COMPOSE_SHEET] 多视图总览/轮廓叠合与拼图
├── examples/
│   ├── README.md                                         # [REF_EXAMPLES_INDEX] 配方与 CLI 索引表
│   ├── official_blender_mcp/                             # [OFF_*] 官方 Blender MCP 仓库（正文零改动）
│   └── recipes/
│       ├── case_r01_scene_and_diagnostic_colors.py       # [CASE_R01] 场景初始化与 RANDOM/MATERIAL 着色切换
│       ├── case_r02_bmesh_topology_audit.py              # [CASE_R02] 纯 BMesh 非流形/退化/反壳体检
│       ├── case_r03_parametric_bmesh_builders.py         # [CASE_R03] 五大载具/机械 BMesh 参数化构造算子
│       ├── case_r04_workbench_5cam_studio.py             # [CASE_R04] P4 自适应 5 机位摄影棚与节点特写
│       ├── case_r05_component_perception_crud.py         # [CASE_R05] 构件世界 AABB 感知与无损 CRUD 微调
│       ├── case_r06_final_delivery_grouping.py           # [CASE_R06] P5 双层交付群组与 WIP 归档
│       ├── case_r07_npanel_bridge_and_apis.py            # [CASE_R07] N 面板选中读取与外部资产/AI API 桥接
│       ├── case_r08_detail_profiles_and_ledger.py        # [CASE_R08] 钢型材库(HEB220等)/格栅/百叶/栏杆/窗与台账
│       ├── case_r09_building_spec.py                     # [CASE_R09] building_spec 状态机/矩形布尔转环/Site_Yaw
│       ├── case_r10_massing_envelope.py                  # [CASE_R10] 多孔楼板/免布尔开洞外墙/悬挑错层整层建造
│       ├── case_r11_level_cut_verify.py                  # [CASE_R11] 真几何水平剖切与 IoU/边偏差/虚实验收
│       ├── cad_operator_recipes.py                       # [RECIPE_CAD_KIT] CASE_R01~R05 底层实现
│       ├── detail_kit.py                                 # [RECIPE_DETAIL_KIT] CASE_R08 底层实现
│       ├── spec_kit.py                                   # [RECIPE_SPEC_KIT] CASE_R09 底层实现
│       ├── facade_kit.py                                 # [RECIPE_FACADE_KIT] CASE_R10 底层实现
│       └── level_cut_verify.py                           # [RECIPE_LEVEL_CUT_VERIFY] CASE_R11 底层实现
└── tests/
    ├── lint_plugin.py                                    # 报文头、文档字数上限、失效符号与依赖边界静态检查
    ├── test_plan_prep.py                                 # 平面偏航扫描/转正符号断言/比例传递测试
    ├── test_section_levels.py                            # 剖面楼板抓取与人工排扰测试
    ├── test_spec_kit.py                                  # 矩形布尔转环/层间继承/校验码/摘要卡片测试
    ├── test_blender_suite.py                             # Blender 无头造洞/多孔楼板/IoU剖切/误差注入/基准测试
    └── sample_acceptance.py                              # 用户示例工程实图端到端验收测试 (需 AGY_SAMPLE_DIR)
```
