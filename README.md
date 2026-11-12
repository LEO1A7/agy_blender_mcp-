# AGY Autonomous MCP 3D Modeling Plugin (`agy-autonomous-mcp-modeling-plugin` v1.3.0)

> **设计理念**：提炼自高完成度三视图与实景复合图纸自主建模实践。引导模型按 **L1 宏观轴网与体块 ➔ L2 结构型材真实截面与重复阵列 ➔ L3 细部五金与节点收口** 自主分步递进建模，并通过 6 行报文头渐进式披露、标准钢结构/建筑细部算子库（`CASE_R08`）与全景+节点微距特写闭环核验，杜绝“用实心方块敷衍型材与细部”的退化现象。

---

## 1. 核心设计与工作范式

1. **三级递进分步建模与截面保真**：
   - 面对建筑外立面、钢结构、工业硬表面与载具，模型按 `L1 宏观体块 ➔ L2 型材截面/阵列 ➔ L3 节点细部` 分批次调用 MCP 构建；
   - 提供 `CASE_R08` (`detail_kit.py`) 标准型材截面库（`HEB100`~`HEB300` 含 `HEB220`、`HEA`、`IPE`、`UPN`、方管、圆管、角钢、丁字钢）与建筑细部算子（菱形/矩形木格栅阵列 `add_slat_array`、带独立倾角叶片的折叠百叶扇 `add_louver_leaf`、多横杆栏杆 `add_railing`、带中梃与双材质的窗框 `add_window`、法兰抱箍 `add_flange_ring`），直接放样生成单连通闭合流形实体，杜绝用 6 面长方体或三盒硬拼替代型材。
2. **双模参考图解析（正交标尺网格 + 透视细部高密切片）**：
   - 正交三视图/平立剖面图：通过 `bin/blueprint_grid_calib.py` 生成半透明红蓝像素坐标网（支持 `--crop` 与 `--zoom` 局部放大且保留原图坐标）；
   - 透视实景照片/复合图纸：跳过全图线性网格换算，但通过 `bin/reference_detail_tiles.py` 自动切分高梯度局部放大切片与 `contact_sheet.png`，配合 `ledger_set` / `ledger_check` 细部防漏台账，确保照片中的型材翼缘、百叶与节点细部零遗漏。
3. **6 行报文头渐进式披露（`head -n 6` Progressive Disclosure）**：
   - 所有模块化配方（`examples/recipes/case_r01`~`case_r08`）、CLI 工具（`bin/*.py`）、参考文档（`references/*.md`）以及官方 Blender MCP 库（`examples/official_blender_mcp/`，官方正文 100% 原样保留）均提供标准化 6 行 `When / How / Out` 报文头，模型仅需 ~150 tokens 即可通过 `head -n 6` 快速按需调用。
4. **继承 Blender 内部 N 面板与外部资产/AI 3D 模型 API（纯 MCP 零端口冲突）**：
   - 完整继承 `addon/agy_blender_bridge.py`（`DSH Blender Bridge` 活动状态/暂停 AI 操作/`Selection -> AGY` + Poly Haven / Sketchfab / Poly Pizza / Hyper3D Rodin / 腾讯混元 3D），在纯 MCP 模式下调用 `case_r07_npanel_bridge_and_apis.py` 时自动抑制后台 TCP 定时器抢占端口。
5. **自适应 5 机位摄影棚、双投影约定与节点特写闭环**：
   - 支持载具约定 (`convention="vehicle"`) 与建筑北上平面约定 (`convention="plan_north_up"`)，自动根据场景包围盒计算相机视距与裁剪面（防止大型建筑相机陷入室内）；
   - 支持跨领域通用高对比度子系统染色 (`GENERIC_GROUP_PALETTE`)、不透明/透明双兼容边缘轮廓提取 (`compose_triview_sheet.py`)、关键节点微距特写 (`render_closeup`) 以及流形/法线/方块退化审计 (`audit_scene_meshes` + `detail_audit`)。

---

## 2. 插件目录结构

```text
agy-autonomous-mcp-modeling-plugin/
├── plugin.json                                           # Antigravity 插件清单 (v1.3.0)
├── README.md                                             # 架构说明与设计理念（本文件）
├── addon/
│   └── agy_blender_bridge.py                             # 继承的 Blender 内部 N 面板与外部资产/AI模型 API 桥接插件
├── assets/
│   └── logo.svg                                          # 插件图标
├── rules/
│   └── AGENTS.md                                         # 四阶段自主建模规则（三级细部拆解 + 截面保真 + 6行报文头快筛）
├── skills/
│   └── autonomous-mcp-blueprint-modeling/
│       ├── SKILL.md                                      # 标尺标定、细部切片、双投影手性与细部保真工作流指南
│       └── references/                                   # 6 行报文头渐进式披露参考文档（N 面板/API 与报文头规范）
├── bin/
│   ├── blueprint_grid_calib.py                           # [BIN_GRID_CALIB] 半透明红蓝双色像素坐标网与局部裁剪放大标定 CLI
│   ├── reference_detail_tiles.py                         # [BIN_DETAIL_TILES] 透视照片/图纸高梯度细部放大切片与索引表生成 CLI
│   └── compose_triview_sheet.py                          # [BIN_COMPOSE_SHEET] 多视图总览 (Mode A)、1:1 轮廓叠合核验 (Mode B) & 网格拼图 (Mode C)
└── examples/
    ├── README.md                                         # [REF_EXAMPLES_INDEX] 6行报文头快筛索引表
    ├── official_blender_mcp/                             # [OFF_*] 官方 Blender MCP 仓库（正文零改动，首部配6行报文头）
    └── recipes/
        ├── case_r01_scene_and_diagnostic_colors.py       # [CASE_R01] 场景初始化、集合/父子层级与跨领域 OBJECT 诊断染色
        ├── case_r02_bmesh_topology_audit.py              # [CASE_R02] 纯 BMesh 非流形/退化面/孤立点/缩放/负体积反壳体检
        ├── case_r03_parametric_bmesh_builders.py         # [CASE_R03] 五大核心 BMesh 参数化构造算子
        ├── case_r04_workbench_5cam_studio.py             # [CASE_R04] Stage 4 自适应 5 机位摄影棚（双约定）与局部节点特写
        ├── case_r05_component_perception_crud.py         # [CASE_R05] 构件世界 AABB 感知、无算子依赖位姿微调与保材质网格替换
        ├── case_r06_final_delivery_grouping.py           # [CASE_R06] 最终交付双层群组与 __hide_r*__ 紧贴归档兜底
        ├── case_r07_npanel_bridge_and_apis.py            # [CASE_R07] Blender N 面板选中读取与 5 大外部资产/AI 模型 API 桥接
        ├── case_r08_detail_profiles_and_ledger.py        # [CASE_R08] 标准钢结构型材库(HEB220等)、格栅/百叶/栏杆/窗细部与防漏台账
        ├── cad_operator_recipes.py                       # [RECIPE_CAD_KIT] CASE_R01~CASE_R05 底层完整算子实现
        └── detail_kit.py                                 # [RECIPE_DETAIL_KIT] CASE_R08 底层真实截面放样与细部审计实现
```
