# Blender MCP 官方参考库与参考配方索引 (`examples/`)

本目录作为外部知识库，存放 **Blender 官方 MCP 脚本仓库** 与 **精选 CAD 算子/质检配方**，供模型在建模、排错与调优过程中**按需查阅，无需预先加载至上下文**。

---

## 1. 官方 Blender MCP 仓库索引 (`examples/official_blender_mcp/`)

源自 Blender 官方实验室（[projects.blender.org/lab/blender_mcp](https://projects.blender.org/lab/blender_mcp.git)），展示官方标准工具实现与测试范式：

| 关注能力 | 对应源码路径 | 核心参考价值 |
| :--- | :--- | :--- |
| **代码执行与环境安全** | `official_blender_mcp/mcp/blmcp/tools/execute_blender_code.py` | 官方 Python 执行协议、上下文封装与返回消息结构 |
| **场景与对象摘要感知** | `official_blender_mcp/mcp/blmcp/tools/get_objects_summary.py` | 官方遍历场景对象、提取包围盒与几何类型的轻量写法 |
| **构件详细拓扑查询** | `official_blender_mcp/mcp/blmcp/tools/get_object_detail_summary.py` | 官方提取网格顶点、面、材质与修改器配置的标准实现 |
| **视口捕获与渲染** | `official_blender_mcp/mcp/blmcp/tools/render_viewport_to_path.py` | 官方视口截图、多区域渲染与参数传递模式 |
| **官方测试与操作范式** | `official_blender_mcp/tests/test_blender_mcp_with_blender.py` | 官方与 Blender 交互的自动化测试用例与标准调用示范 |

---

## 2. 精选 CAD 参数化算子与辅助配方 (`examples/recipes/cad_operator_recipes.py`)

当遇到复杂几何、需要局部网格微调或独立拓扑体检时，可直接读取本文件中的成熟实现（按需阅读对应函数）：

| 需求场景 | 推荐函数 / 关键字 | 代码定位字段（便于直接检索提取） | 功能简要说明 |
| :--- | :--- | :--- | :--- |
| **网格流形与缩放体检** | `audit_scene_meshes` | `def audit_scene_meshes(` | 纯 BMesh 检查全场景非流形边、零面积退化面与未归零缩放 |
| **闭合连续履带环** | `build_contoured_track_loop` | `def build_contoured_track_loop(` | 沿闭合导引点自动计算切线与外法线，生成带体、履带板与诱导齿 |
| **多面体壳与平面四边面封顶** | `build_layered_polyhedral_shell` | `def build_layered_polyhedral_shell(` | 多层截面放样，对称顶点对横向平面四边面封顶，根除 N-gon 阴影伪影 |
| **波浪下缘侧裙板** | `build_wavy_skirt_panels` | `def build_wavy_skirt_panels(` | 余弦插值平滑下缘分段侧裙板 |
| **截面拉伸与首尾收窄** | `extrude_side_profile` | `def extrude_side_profile(` | 侧视多边形拉伸，支持车首收窄 |
| **多模块区分染色截图** | `set_diagnostic_color_mode` | `def set_diagnostic_color_mode(` | 为车体/炮塔/履带/轮组赋予高对比度区分色 (`OBJECT`)，截图时直观暴露穿插错位 |
| **构件状态感知 (AABB)** | `inspect_scene_components` | `def inspect_scene_components(` | 提取已建构件的世界坐标、AABB 包围盒中心与尺寸、旋转度数 |
| **原地微调与平移缩放** | `transform_component` | `def transform_component(` | 原地微调位姿，自动保持 `scale=(1,1,1)` 归零 |
| **原地更新网格几何** | `replace_component_geometry` | `def replace_component_geometry(` | 无损替换构件 Mesh，完整保留现有材质、父子装配与集合关系 |
| **统一 5 机位配置** | `setup_workbench_studio_and_cameras` | `def setup_workbench_studio_and_cameras(` | 3 个正交机位 + 2 个包围球自动算距定焦等轴测机位 |

---

## 3. 按需读取代码片段示例（Convenient Read Field）

模型可使用 `read_file` 直接按需切片读取，例如需要闭合履带带体算法时：
```python
# 检索特定函数定义位置
Target: "def build_contoured_track_loop("
Path: ".../examples/recipes/cad_operator_recipes.py"
```
无需在主提示词中常驻，实现按需即取、精准聚焦。
