# AGY Autonomous MCP 3D Modeling Plugin (混合MCP插件01版 / v2.0.0)

> **设计理念**：提炼自高完成度三视图与实景复合图纸自主建模工程实践。引导模型按 **L1 宏观轴网与体块 ➔ L2 结构型材真实截面与重复阵列 ➔ L3 细部五金与节点收口** 自主分步递进建模，并通过 6 行报文头渐进式披露、标准钢结构/建筑细部与多边形算子库（`CASE_R08`）、水平剖切图与 Mode B 1:1 蓝图轮廓叠合门禁、全景+节点微距特写闭环核验，杜绝“用实心方块敷衍型材与细部”的退化现象。

---

## 本次版本修订核心内容（版本名：混合MCP插件01版）

本版本重点解决在复杂建筑图纸与复合图纸建模过程中发现的**“照片视角幸存者偏差导致背面细部漏建”、“默认正交盒子导致斜切/异形凸窗退化”、“屋顶遮挡平面导致无法1:1核验”、“对齐阻力导致用网格画廊敷衍叠合对账”**等关键问题，实现从读图、轴网、几何算子到视觉核验的全流程闭环升级：

### 1. 添加原生随机分色显示机制（Native Random Shading）
- **零上下文与调色盘开销**：建模开始时，自动开启 Blender 原生“视图着色方式-物体-随机”功能（`color_type = 'RANDOM'`，轮廓线 `show_object_outline = True`），无需额外代码或调色盘上下文即可实现轻量化逐物体分色，极大辅助 VLM 清晰识别模型各构件边界、装配关系与几何进退。
- **几何与材质双阶段无缝切换**：
  - **几何核验期**：保持 `RANDOM` 状态进行视口交互、5 机位总览与节点特写核验；
  - **材质交付期**：当赋予模型材质后进行观察与最终交付时，仅需将 `color_type` 切换回 `'MATERIAL'`（视图着色方式-物体-材质）状态即可。

### 2. 添加水平剖切面截图检查机制（Horizontal Plan Section Inspection）
- **新增水平剖切平面图算子**：在 `cad_operator_recipes.py` 与 `case_r04_workbench_5cam_studio.py` 中新增 `render_plan_section(out_path, cut_z=1.5, floor_z=0.0)`。
- **物理切除屋顶遮挡**：利用正交顶视相机的 `clip_start` 动态裁切，物理切掉屋顶与上层遮挡楼板，渲染任意标高（如 $z=1.5\text{ m}$）处的真实水平剖切平面图。
- **消除图纸对对账阻力**：彻底解决顶视图（Roof Plan）因屋顶遮挡无法与一层平面图（Grundriss）各房间外墙折线及室内外构件做 1:1 叠合对比的痛点。

### 3. 逆时针 `--crop` 逐个细部放大与 360° 外轮廓闭环清点（Perimeter Walk）
- **平面图一键纠偏摆正**：`blueprint_grid_calib.py` 新增 `--rotate <deg>` 参数，支持在打红蓝像素标尺网或裁剪前，将图纸上倾斜排版的平面图一键纠偏摆正至建筑自身主轴方向。
- **强制 360° 外墙闭环周游**：在 `rules/AGENTS.md` 与 `SKILL.md` 中确立规则——严禁仅凭全图概览或透视照片可见面建模！必须沿着放大后的平面图外墙按逆时针顺序（例如：`WF ➔ GAST ➔ HAUSWIRTSCHAFT ➔ KÜCHE ➔ ESSEN ➔ WOHNEN ➔ BIBLIOTHEK`）逐个房间执行高倍率放大切片（`--crop u0,v0,u1,v1 --zoom 2.5+`），逐段核查凹凸进退、斜切折角与所有凸窗/开口，悉数登记至细部防漏台账（`ledger_set`），彻底杜绝照片盲区（背面/侧后方）漏建构件。

### 4. Mode B 1:1 叠合机制全面升级与强制验收门禁（Blueprint Overlay Gate）
- **自动对齐消除裁剪错位**：`compose_triview_sheet.py` 新增 `--auto-align` 参数，自动提取图纸墨线边界（Ink Bounding Box）与渲染前景包围盒（Foreground Bounding Box）精准对齐，消除因人工裁剪边缘留白差异产生的平移与缩放误差。
- **支持蓝图旋转叠合**：新增 `--rotate-bp <deg>` 参数，支持将旋转图纸与渲染图以相同角度精准叠合。
- **4 列 1:1 像素级对比核验图**：输出 `[1] 蓝图 1:1 局部 ➔ [2] 渲染图 ➔ [3] 结构边缘线框 ➔ [4] 蓝图 + 红色渲染轮廓高亮叠加`。
- **设立强制验收门禁**：凡有平面图与立面图输入的任务，交付前必须执行 Mode B 1:1 叠合核验（平面图结合 `render_plan_section` 剖切图），只有当红色渲染线框与图纸线稿完全重合时方可交付，严禁仅以 `--panel` 网格画廊敷衍。

### 5. 新增 2D 平面多边形与异形/斜切凸窗建模算子（Polygon & Splayed Bay Kit）
- **算子级支持非正交构件**：在 `detail_kit.py` 与 `case_r08_detail_profiles_and_ledger.py` 中新增：
  - `add_polygon_slab(bm, poly_xy, z0, z1)`：根据平面拐点坐标直接生成任意非直角多边形楼板/悬挑板；
  - `add_polyline_wall(bm, pts_xy, z0, z1, thickness)`：沿平面折线生成连续斜接（Mitered）外墙，保留真实拐角；
  - `add_splayed_bay(bm, poly_xy, z0, z1, open_edge=0, panes=(2,1))`：直接根据平面折线顶点生成梯形/三角形斜切凸窗（含顶底窗台板、中梃外框与玻璃双材质）。
- **消除工具诱导偏差**：确立“平面多边形顶点提取先于体块建模”原则，杜绝因缺乏斜切算子而退化为正交长方体的现象。

### 6. Blender N 面板与外部 3D 资产/生成式 AI API 桥接集成
- 完整继承 `addon/agy_blender_bridge.py` 与 `case_r07_npanel_bridge_and_apis.py`，打通视口选择双向投递及 Poly Haven / Sketchfab / Poly Pizza / Rodin / 腾讯混元 3D 模型 API，纯 MCP 模式下自动抑制后台 TCP 定时器冲突。

### 7. 6 行标准化报文头渐进式披露（Progressive Disclosure）
- 所有配方模块（`CASE_R01`~`CASE_R08`）、CLI 工具（`bin/*.py`）及官方 Blender MCP 库（`official_blender_mcp/`）均在文件首部配备 6 行 `When / How / Out` 报文头，支持 `head -n 6` 极速快筛（仅耗 ~150 tokens），杜绝上下文污染。

---

## 核心设计与工作范式

1. **三级递进分步建模与截面保真**：
   - 面对建筑外立面、钢结构、工业硬表面与载具，模型按 `L1 宏观体块 ➔ L2 型材截面/阵列 ➔ L3 节点细部` 分批次调用 MCP 构建；
   - 提供 `CASE_R08` (`detail_kit.py`) 标准型材截面库（`HEB100`~`HEB300` 含 `HEB220`、`HEA`、`IPE`、`UPN`、方管、圆管、角钢、丁字钢）与建筑细部算子（菱形/矩形木格栅阵列 `add_slat_array`、带独立倾角叶片的折叠百叶扇 `add_louver_leaf`、多横杆栏杆 `add_railing`、带中梃与双材质的窗框 `add_window`、法兰抱箍 `add_flange_ring`），直接放样生成单连通闭合流形实体，杜绝用 6 面长方体或三盒硬拼替代型材。
2. **双模参考图解析（正交标尺网格 + 透视细部高密切片）**：
   - 正交三视图/平立剖面图：通过 `bin/blueprint_grid_calib.py` 生成半透明红蓝像素坐标网（支持 `--rotate` 纠偏与 `--crop`、`--zoom` 局部放大且保留原图坐标）；
   - 透视实景照片/复合图纸：跳过全图线性网格换算，但通过 `bin/reference_detail_tiles.py` 自动切分高梯度局部放大切片与 `contact_sheet.png`，配合 `ledger_set` / `ledger_check` 细部防漏台账，确保照片与图纸盲区的型材翼缘、百叶与节点细部零遗漏。
3. **自适应 5 机位摄影棚、双投影约定与节点特写闭环**：
   - 支持载具约定 (`convention="vehicle"`) 与建筑北上平面约定 (`convention="plan_north_up"`)，自动根据场景包围盒计算相机视距与裁剪面（防止大型建筑相机陷入室内）；
   - 支持跨领域通用高对比度子系统染色 (`GENERIC_GROUP_PALETTE`)、不透明/透明双兼容边缘轮廓提取 (`compose_triview_sheet.py`)、关键节点微距特写 (`render_closeup`)、水平剖切平面图 (`render_plan_section`) 以及流形/法线/方块退化审计 (`audit_scene_meshes` + `detail_audit`)。

---

## 插件目录结构

```text
agy-autonomous-mcp-modeling-plugin/
├── plugin.json                                           # Antigravity 插件清单 (混合MCP插件01版 / v2.0.0)
├── README.md                                             # 架构说明、更新日志与设计理念（本文件）
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
│   ├── blueprint_grid_calib.py                           # [BIN_GRID_CALIB] 半透明红蓝像素标尺网、局部裁剪放大与旋转纠偏 CLI
│   ├── reference_detail_tiles.py                         # [BIN_DETAIL_TILES] 透视照片/图纸高梯度细部放大切片与索引表生成 CLI
│   └── compose_triview_sheet.py                          # [BIN_COMPOSE_SHEET] 多视图总览 (Mode A)、1:1 轮廓叠合自动对齐 (Mode B) & 网格拼图 (Mode C)
└── examples/
    ├── README.md                                         # [REF_EXAMPLES_INDEX] 6行报文头快筛索引表
    ├── official_blender_mcp/                             # [OFF_*] 官方 Blender MCP 仓库（正文零改动，首部配6行报文头）
    └── recipes/
        ├── case_r01_scene_and_diagnostic_colors.py       # [CASE_R01] 场景初始化、集合管理与原生 RANDOM 随机分色/MATERIAL 切换
        ├── case_r02_bmesh_topology_audit.py              # [CASE_R02] 纯 BMesh 非流形/退化面/孤立点/缩放/负体积反壳体检
        ├── case_r03_parametric_bmesh_builders.py         # [CASE_R03] 五大核心 BMesh 参数化构造算子
        ├── case_r04_workbench_5cam_studio.py             # [CASE_R04] Stage 4 自适应 5 机位摄影棚、水平剖切平面图与局部节点特写
        ├── case_r05_component_perception_crud.py         # [CASE_R05] 构件世界 AABB 感知、无算子依赖位姿微调与保材质网格替换
        ├── case_r06_final_delivery_grouping.py           # [CASE_R06] 最终交付双层群组与 __hide_r*__ 紧贴归档兜底
        ├── case_r07_npanel_bridge_and_apis.py            # [CASE_R07] Blender N 面板选中读取与 5 大外部资产/AI 模型 API 桥接
        ├── case_r08_detail_profiles_and_ledger.py        # [CASE_R08] 标准钢结构型材库、多边形楼板/折线墙/斜切凸窗、细部阵列与防漏台账
        ├── cad_operator_recipes.py                       # [RECIPE_CAD_KIT] CASE_R01~CASE_R05 底层完整算子实现
        └── detail_kit.py                                 # [RECIPE_DETAIL_KIT] CASE_R08 底层真实截面放样与多边形/斜切细部实现
```
