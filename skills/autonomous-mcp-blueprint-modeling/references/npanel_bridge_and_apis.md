"""[REF_NPANEL_APIS] Blender 内部 N 面板 (DSH Blender Bridge + 环境与角色模型API调用) 继承与按需调用指南
- 适用 (When): 用户在 Blender 视口 N 面板点击「发送选中到 AGY」「暂停 AI 操作」或要求调用 PolyHaven/Sketchfab/PolyPizza/Rodin/混元3D
- 用法 (How) : 在 `execute_blender_code` 中导入 `examples/recipes/case_r07_npanel_bridge_and_apis.py` 即可一键调用，平时无需加载
- 产出 (Out) : 读取用户在视口发送的多选物体/集合、检测 AI 暂停安全锁、直接调用 5 大外部环境资产与角色/模型生成 API
"""

# Blender 内部 N 面板小插件（DSH Blender Bridge + 环境与角色模型 API 调用）MCP 按需指南

本插件已完整继承来自 DSH-TCP 项目的 Blender 内部视口侧边栏（`N` 面板）小插件 `addon/agy_blender_bridge.py`，包含两大面板：
1. **`DSH Blender Bridge` 主面板**：
   - **活动状态 & `暂停 AI 操作`**：实时显示人机活动状态；当用户点击「暂停 AI 操作」时，`dshbb_ai_paused = True`。
   - **`Selection → DSH`（多选 / 集合 → `发送选中到 AGY`）**：支持在 Blender 视口中框选多个物体或直接选择一个大装配体集合，点击「发送选中到 AGY」（自动同时写入 Blender 内存 `bpy.types.dshbb_last_sent_selection` 与本地缓存 `/tmp/agy_blender_selection.json`，无需启动 TCP 9877 守护进程即可在纯 MCP 模式下工作）。
2. **`环境与角色模型API调用` 折叠面板**：
   - **环境生成（资产库）**：`Poly Haven`（CC0 HDRI/材质/模型）、`Sketchfab`、`Poly Pizza`。
   - **模型生成（AI 3D 模型 API）**：`Hyper3D Rodin`、`Tencent Hunyuan 3D（腾讯混元 3D）`（及 Premium 模式下的 `Tripo`）。

---

## 在 MCP (`execute_blender_code`) 中的极简调用方式

无需预加载冗长代码，仅在需要与 N 面板交互或调用外部资产/AI 模型 API 时，在 `execute_blender_code` 中运行：

```python
import sys
sys.path.append("/home/leo/.gemini/config/plugins/abmcp/examples/recipes")
from case_r07_npanel_bridge_and_apis import (
    ensure_npanel_registered,
    is_ai_paused,
    get_npanel_selection,
    list_npanel_api_status,
    call_npanel_api,
)

# 1. 确保 Blender 3D 视口 N 面板已挂载并查看状态
print(ensure_npanel_registered())

# 2. 读取用户在 N 面板点击「发送选中到 AGY」投递的多选物体或集合
sel_info = get_npanel_selection()
print(sel_info)

# 3. 查询 5 大外部资产与 AI 建模 API 开关及配置状态
print(list_npanel_api_status())

# 4. 直接调用任意外部资产库或 AI 3D 模型生成 API（自动开启对应开关）：
# 示例 A：搜索并下载 Poly Haven HDRI 或模型
# res = call_npanel_api("search_polyhaven_assets", asset_type="hdris", categories="outdoor")
# res = call_npanel_api("download_polyhaven_asset", asset_id="industrial_sunset_puresky", asset_type="hdris", resolution="2k")

# 示例 B：调用 Hyper3D Rodin 或腾讯混元 3D 生成角色/道具模型
# job = call_npanel_api("create_hunyuan_job", text_prompt="a vintage carved wooden chair")
```
