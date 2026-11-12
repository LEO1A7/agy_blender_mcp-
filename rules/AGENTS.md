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

### Stage 1：比例标定、局部放大与 360° 外轮廓闭环清点（Calibration & Perimeter Walk）
- **像素标尺网与平面高倍局部切片**：
  - **正交三视图、平面图（含立面图、剖面图）和带尺寸标注的轴测图**：运行 `bin/blueprint_grid_calib.py` 生成半透明红（X）蓝（Y）双色标尺网格 `blueprint_grid.png`（若平面图在图纸上带排版旋转角，用 `--rotate <deg>` 先摆正），提取主尺寸标注换算唯一比例尺 $s = \frac{L_{\text{real}}}{\Delta u_{\text{px}}}\; (\text{m/px})$。**针对含多子图的复合图纸，严禁仅看全图概览**，必须用 `--crop u0,v0,u1,v1 --zoom 2.5` 对平面图及密集节点区域做高倍率放大标尺切片。
  - **透视图（实景照片/透视效果图）或无尺寸标注的轴测图**：跳过全图红蓝线性网格换算，运行 `bin/reference_detail_tiles.py` 自动切分高梯度局部放大图与 `contact_sheet.png`，逐一审视型材翼缘、百叶倾角、格栅分缝、栏杆与节点构造。
- **强制 360° 外墙闭环周游（Perimeter Walk，防照片盲区漏建）**：严禁只看透视照片可见面！必须沿着放大后的平面图外墙按逆时针/顺时针完整闭环遍历一圈（逐个相邻房间/分区外墙，包含透视照片拍不到的背面与侧后方盲区），逐段核查外墙的**凹凸进退、斜切折角（非 $90^\circ$ 斜边）与全部凸窗/开口**，悉数登记至细部防漏台账（`case_r08_detail_profiles_and_ledger.ledger_set`）。

### Stage 2：右手系投影手性、视图约定与平面折线顶点提取（Handedness & Polygon Extraction）
- 统一右手系，支持在 `setup_workbench_studio_and_cameras` 中按目标类型选择对应投影约定：
  - **载具/机械约定 (`convention="vehicle"`)**：前向 $-Y$、上向 $+Z \Rightarrow$ 右舷（Starboard）为 $-X$、左舷（Port）为 $+X$；侧视相机位于 $+X$ 看向 $-X$（车头朝左），顶视车头朝左。
  - **建筑/场地平面北上约定 (`convention="plan_north_up"`)**：平面图上北 $+Y$、下南 $-Y$、右东 $+X$、左西 $-X$、上向 $+Z$；正立面（南立面）从 $-Y$ 看向 $+Y$，左侧立面（西立面）从 $-X$ 看向 $+X$。
- **平面多边形顶点提取先于体块建模（严禁默认正交长方体）**：建模前必须先从高倍平面图提取主体外墙及各凸出体块（如斜切凸窗、转角耳房、退台）的 2D 闭合多边形拐点坐标 `[(x0,y0), (x1,y1), ...]`，显式识别非 $90^\circ$ 斜切边（如平面上呈直角梯形/三角形的斜切凸窗），严禁未经坐标核对直接用正交长方体替代建筑主体或凸窗。

### Stage 3：自主分段 BMesh 几何与真实截面建模（Autonomous Modeling）
- **开启原生随机分色**：建模开始时直接打开 Blender 自带“视图着色方式-物体-随机”（`scene.display.shading.color_type = 'RANDOM'` 及 `VIEW_3D` `shading.color_type = 'RANDOM'`，开启轮廓 `show_object_outline = True`），无需额外代码或上下文即可实现轻量化物体分色，辅助 VLM 清晰识别各构件。
- 模型按 **L1 ➔ L2 ➔ L3** 顺序分批次调用 MCP `execute_blender_code` 递进构建，由大到小，由粗到细，使用mcp逐个构件建模，直至全部构件完成。
- 首先根据llm自身的判断自主建模，并自主决定是否调用案例库的既有细部组件，如判断需要调用，则执行 `head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py` 按需选用标准型材/多边形楼板/折线外墙/斜切凸窗算子（`CASE_R08` 的 `add_polygon_slab`、`add_polyline_wall`、`add_splayed_bay`、`add_steel_member` 等）或曲面/履带算子（`CASE_R03`）。
- 薄壁细部（如 $12\text{ mm}$ 百叶叶片、$9.5\text{ mm}$ H 型钢腹板）使用自适应安全倒角（`create_mesh_object` / `finalize_object` 已内置薄壁倒角限幅，避免固定大倒角撑爆薄件）。

### Stage 4：视口视觉核验、1:1 蓝图剖切叠合门禁与闭环调优（Visual Verification & Overlay Gate）
1. **原生随机分色核验与强制 Mode B 1:1 蓝图轮廓叠加门禁（Blueprint Overlay Gate）**：
   - **几何核验期（`RANDOM`）**：保持“视图着色方式-物体-随机”（`color_type = 'RANDOM'`），调用 `CASE_R04` (`setup_workbench_studio_and_cameras`) 渲染多视图与关键节点 `render_closeup()`。
   - **强制 Mode B 1:1 叠合对账（严禁仅用 `--panel` 网格画廊敷衍）**：凡有平面图/立面图输入的任务，交付前**必须**执行 `bin/compose_triview_sheet.py --blueprint <bp.png> --crop u0,v0,u1,v1 --render <render.png> --overlay [--rotate-bp <deg> --auto-align]` 生成四列 1:1 红色边缘叠合核验图（针对有屋顶遮挡的建筑平面图，调用 `CASE_R04.render_plan_section(out_path, cut_z=1.5)` 渲染水平剖切平面图后再与原平面图叠合），逐边比对渲染红线与图纸黑线是否完全重合（重点核查凸窗数量、斜切角度与外墙凹凸）。
   - **材质观察与交付期（`MATERIAL`）**：几何与叠合对账全部吻合、赋予模型材质后，仅需将 `color_type` 切换为 `'MATERIAL'`（视图着色方式-物体-材质）即可观察与最终交付。
2. **几何体检与细部台账对账**：调用 `audit_scene_meshes()` 检查流形/法线方向，调用 `detail_audit()` 与 `ledger_check()` 排查是否存在遗漏子系统或用 6 面方块冒充型材/细部的情况。
3. **自主增删改查与修复**：使用 `read_file` 审视全景与特写渲染图，发现比例、位置或细部缺失后，通过 `CASE_R05` (`inspect_scene_components`, `transform_component`, `replace_component_geometry`) 或增补脚本闭环调优直至整体与细部均准确无误。
