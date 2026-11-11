# AGY Autonomous MCP 3D Modeling Plugin (`agy-autonomous-mcp-modeling-plugin` v1.2.0)

> **设计理念**：提炼自高完成度三视图自主建模实践。摒弃强制挂载的冗余算子与固化质检，引导模型根据目标复杂度自主判定，自行组织分步骤、分组件建模，并自主在官方 MCP 库与案例配方中寻找最适合的语句完成构建、感知与修复。

---

## 1. 核心设计与工作范式

在实际建模任务中，面对复杂多部件形体，一次性生成数百行整体建模脚本往往会增加单次推演难度，且缺乏中间状态可见性。本插件倡导以下轻量化交互工作流：
1. **自主规划分步建模**：模型根据三视图特征自主划分组件层次与构建顺序，分次调用 MCP 进行交互式构建与即时核验。
2. **轻量通用基底（Zero-Clutter Context）**：主规则中不预置冗余算子库，不强制挂载特定体检函数，释放模型注意力与自主性。
3. **官方 MCP 库与按需配方查阅**：官方 MCP 具备极其丰富的工具与 API，模型自主按需选择；`examples/` 目录下收录了官方 MCP 完整仓库与精选 CAD 算子/质检配方，提供明确的代码定位字段供模型按需检索。
4. **统一 5 机位与视觉自愈闭环**：
   - 通过技术视口输出正交三视图与等轴测视图，支持多模块高对比度区分染色截图与 1:1 三列边缘轮廓核验；
   - 视觉审视发现偏差后，模型自主调用 MCP 语句查询构件状态、微调位姿、重构局部网格或增补部件。

---

## 2. 插件目录结构

```text
agy-autonomous-mcp-modeling-plugin/
├── plugin.json                                           # Antigravity 插件清单 (v1.2.0)
├── README.md                                             # 架构说明与设计理念（本文件）
├── assets/
│   └── logo.svg                                          # 插件图标
├── rules/
│   └── AGENTS.md                                         # 四阶段自主建模规则（零强制算子，专注自主决策）
├── skills/
│   └── autonomous-mcp-blueprint-modeling/
│       └── SKILL.md                                      # 像素标尺、手性门禁与工作流指南
├── bin/
│   ├── blueprint_grid_calib.py                           # 原图双色像素坐标网格生成与比例尺标定 CLI
│   └── compose_triview_sheet.py                          # 多视图拼合 (Mode A) & 1:1 三列边缘轮廓核验 (Mode B) CLI
└── examples/
    ├── README.md                                         # 官方仓库导读与快捷检索字段索引表
    ├── official_blender_mcp/                             # 官方 Blender MCP 完整脚本仓库（官方 API/工具参考底座）
    └── recipes/
        └── cad_operator_recipes.py                       # 归档的 CAD 参数化算子、质检与微调参考配方（按需读取）
```
