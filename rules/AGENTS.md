# AGENTS.md —— AGY Autonomous MCP 3D Modeling Plugin 核心规则

> 本插件提炼自高完成度三视图与实景复合图纸自主建模实践。模型应根据目标复杂度自主判定，按 **L1 宏观轴网与体块 ➔ L2 结构型材截面与重复阵列 ➔ L3 细部节点与五金收口** 组织多次分步骤、分组件递进建模，充分利用 MCP 交互式建模与即时反馈能力，逐步分段推进直至完成高保真整体装配。
> 
> **官方参考底座与 6 行报文头渐进式披露（Progressive Disclosure）**：Blender 官方 MCP 完整脚本库（`examples/official_blender_mcp/`，官方正文原样保留）及模块化 CAD 配方（`examples/recipes/case_r01`~`case_r08`、`bin/*.py`、`references/*.md`）均在文件顶部配有 **6 行标准化报文头（`When / How / Out`）**。模型在全流程任意阶段可先跑 `head -n 6` 快速阅读报文头，决定是否需要调用或切片读取内部内容，保持上下文洁净。
>
> **Blender 内部 N 面板与外部资产/AI 3D 模型 API 继承（按需挂载，零常驻干扰）**：插件已继承 `addon/agy_blender_bridge.py`（`DSH Blender Bridge` 活动状态/暂停 AI 操作/`Selection -> AGY` 多选与集合投递 + `环境与角色模型API调用`：Poly Haven / Sketchfab / Poly Pizza / Hyper3D Rodin / 腾讯混元 3D）。常规建模无需加载；仅当需读取用户视口选中或调用外部资产/AI 模型 API 时，按需查阅 `head -n 6 examples/recipes/case_r07_npanel_bridge_and_apis.py`。

---

## 1. 建模指导原则

- **自主分步组织与三级特征拆解**：面对复杂形体，模型严禁只建粗略外壳或用实心方块敷衍细部，应自主将目标拆解为三级递进批次，分次调用 MCP `execute_blender_code` 逐步构建：
  - **L1 宏观轴网与主体体块**：柱网基准、楼板/车体主轮廓、主墙面与屋顶；
  - **L2 结构型材真实截面与重复阵列**：外露钢柱/钢梁（如 `HEB 220` / `HEA` / `IPE` 工字/H 型钢的上下翼缘与腹板、槽钢、角钢、方管）、立面木格栅阵列（含真实菱形/矩形截面与缝隙）、折叠百叶窗扇（含独立倾斜叶片与外框）、阳台栏杆（立柱+多道横杆+扶手）；
  - **L3 细部五金与节点收口**：凸窗/门窗框料与中梃、烟囱分段接缝与抱箍法兰、柱脚底板、檐口压顶滴水线。
- **截面保真准则（严禁方块替代型材）**：凡图纸或参考照片中可见的 H/I 型钢、槽钢、百叶叶片、格栅条、窗框中梃、管箍法兰，**必须构建真实二维截面并挤出为单连通闭合流形网格**（可直接调用 `case_r08_detail_profiles_and_ledger` 中的 `add_steel_member`、`add_slat_array`、`add_louver_leaf`、`add_railing`、`add_window` 或使用原生 `bmesh` 截面放样），严禁退化为 6 面实心长方体或用三个重叠长方体硬拼。
- **手性与空间一致性**：严格统一右手系，避免左右镜像反转；子部件挂载时保持世界坐标一致（`set_parent_keep_world`）。

---

## 2. 四阶段闭环工作流

### Stage 1：比例标定与三级细部特征清点（Calibration & Detail Inventory）
- **像素标尺网触发边界**：
  - **正交三视图、平面图（含立面图、剖面图）和带尺寸标注的轴测图**：运行 `bin/blueprint_grid_calib.py` 生成半透明红（X）蓝（Y）双色标尺网格 `blueprint_grid.png`（局部密集标高/文字可用 `--crop u0,v0,u1,v1 --zoom 2` 放大），提取主尺寸标注换算唯一比例尺 $s = \frac{L_{\text{real}}}{\Delta u_{\text{px}}}\; (\text{m/px})$ 并建立线性坐标映射函数。
  - **透视图（实景照片/透视效果图）或无尺寸标注的轴测图**：自动跳过全图红蓝线性像素网格换算，但**严禁跳过细部观察与特征清点**！当输入包含实景照片或高密度图纸时，应运行 `bin/reference_detail_tiles.py` 自动切分高梯度局部放大图与编号索引表 `contact_sheet.png`，逐一审视型材翼缘、百叶倾角、格栅分缝、栏杆与节点构造。
- **登记细部防漏台账（Feature Ledger）**：在进入建模前，梳理 L1/L2/L3 组件清单（可通过 `case_r08_detail_profiles_and_ledger.ledger_set` 写入场景台账），明确每类构件的目标数量与真实截面类型。

### Stage 2：右手系投影手性与视图约定对齐（Handedness & Convention Alignment）
- 统一右手系，支持在 `setup_workbench_studio_and_cameras` 中按目标类型选择对应投影约定：
  - **载具/机械约定 (`convention="vehicle"`)**：前向 $-Y$、上向 $+Z \Rightarrow$ 右舷（Starboard）为 $-X$、左舷（Port）为 $+X$；侧视相机位于 $+X$ 看向 $-X$（车头朝左），顶视车头朝左。
  - **建筑/场地平面北上约定 (`convention="plan_north_up"`)**：平面图上北 $+Y$、下南 $-Y$、右东 $+X$、左西 $-X$、上向 $+Z$；正立面（南立面）从 $-Y$ 看向 $+Y$，左侧立面（西立面）从 $-X$ 看向 $+X$。
- 对称与非对称部件建模前，交叉核对平面/顶视与立面/正视手性，确保左右朝向与凹凸进退准确。

### Stage 3：自主分段 BMesh 几何与真实截面建模（Autonomous Modeling）
- **开启原生随机分色**：建模开始时直接打开 Blender 自带“视图着色方式-物体-随机”（`scene.display.shading.color_type = 'RANDOM'` 及 `VIEW_3D` `shading.color_type = 'RANDOM'`，开启轮廓 `show_object_outline = True`），无需额外代码或上下文即可实现轻量化物体分色，辅助 VLM 清晰识别各构件。
- 模型按 **L1 ➔ L2 ➔ L3** 顺序分批次调用 MCP `execute_blender_code` 递进构建，由大到小，由粗到细，使用mcp逐个构件建模，直至全部构件完成。
- 首先根据llm自身的判断自主建模，并自主决定是否调用案例库的既有细部组件，如判断需要调用，则执行 `head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py` 按需选用标准型材/细部算子（`CASE_R08`）或曲面/履带算子（`CASE_R03`）。
- 薄壁细部（如 $12\text{ mm}$ 百叶叶片、$9.5\text{ mm}$ H 型钢腹板）使用自适应安全倒角（`create_mesh_object` / `finalize_object` 已内置薄壁倒角限幅，避免固定大倒角撑爆薄件）。

### Stage 4：视口视觉核验、节点特写与闭环调优（Visual Verification & Refinement）
1. **原生随机分色核验与材质切换交付**：
   - **几何核验期（`RANDOM`）**：保持“视图着色方式-物体-随机”（`color_type = 'RANDOM'`），调用 `CASE_R04` (`setup_workbench_studio_and_cameras`) 架设自适应包围盒距离的 Workbench Cavity + Outline 摄影棚，配合 `bin/compose_triview_sheet.py` 生成多视图总览图或 1:1 边缘轮廓叠合核验图，并对关键结构节点调用 `render_closeup()` 输出局部特写。
   - **材质观察与交付期（`MATERIAL`）**：当赋予模型材质后进行观察和最终交付时，仅需将 `color_type` 切换为 `'MATERIAL'`（视图着色方式-物体-材质）即可。
2. **几何体检与细部台账对账**：调用 `audit_scene_meshes()` 检查流形/法线方向，调用 `detail_audit()` 与 `ledger_check()` 排查是否存在遗漏子系统或用 6 面方块冒充型材/细部的情况。
3. **自主增删改查与修复**：使用 `read_file` 审视全景与特写渲染图，发现比例、位置或细部缺失后，通过 `CASE_R05` (`inspect_scene_components`, `transform_component`, `replace_component_geometry`) 或增补脚本闭环调优直至整体与细部均准确无误。
