"""[REF_OFFICIAL_MCP] Blender 官方 MCP 26 项原生工具完整参数字典与 prompts.yml 规范
- 适用 (When): 调用官方 26 项 MCP 工具（文档检索/场景摘要/截图渲染/视口跳转/CLI无头执行）或查阅官方操作守则
- 用法 (How) : 先 `head -n 6` 快筛，按需查阅 26 工具签名表与官方 `initial_instructions` 全文
- 产出 (Out) : 零遗漏掌握全部 26 个官方 MCP 工具、无头 `_for_cli` 同步机制、延迟响应与 Blender 数据块铁律
"""

# Blender 官方 MCP 26 项原生工具与运行规范 (`abmcp_mcp`)

本插件内置未改动官方上游 `examples/official_blender_mcp/`（commit `dbbf836`）及顶层 `addon/blender_mcp_addon/`，并通过 `mcp_config.json` 注册服务 `abmcp_mcp`（端口可通过 `BLENDER_MCP_PORT` 配置，当前默认 `9875` 以避免与 `addon/agy_blender_bridge.py` 的 `9876` 端口冲突）。

---

## 1. 官方 26 项原生 MCP 工具签名全表

### A. 文档检索与查询（3 个）
| 工具名 | 参数与默认值 | 功能说明 |
| :--- | :--- | :--- |
| `get_python_api_docs` | `identifier: str` | 查询随包 Blender Python API RST 文档（支持 `*`、`<mod>.*`、精确标识符及模糊候选；>32KB 自动摘要顶层定义） |
| `search_api_docs` | `query: str, max_results: int=20, context: int=0, index: int \| None=None` | 在 `mcp/blmcp/data/api/` 中全文搜索 Blender Python API 文档 |
| `search_manual_docs` | `query: str, max_results: int=20, context: int=0, index: int \| None=None` | 在 `mcp/blmcp/data/manual/` 中全文搜索 Blender 官方用户手册 |

### B. 场景与 `.blend` 工程只读摘要（14 个：9 在线 + 5 离线 `_for_cli`）
| 工具名 | 参数与默认值 | 功能说明 |
| :--- | :--- | :--- |
| `get_objects_summary` | 无参数 | 返回当前场景 Collection 层级树及对象列表（名称、类型、父子、选区、可见性） |
| `get_object_detail_summary` | `name: str` | 返回指定对象的变换、包围盒、约束、修改器、材质、Data-block 摘要与自定义属性 |
| `get_blendfile_summary_datablocks` | 无参数 | 返回当前 `.blend` 各类数据块计数、活动工作区与渲染引擎 |
| `get_blendfile_summary_datablocks_for_cli` | `blend_file: str` | 在后台 Blender 进程打开指定 `.blend` 并返回数据块摘要 |
| `get_blendfile_summary_missing_files` | 无参数 | 检查磁盘缺失的外部引用（贴图、链接库、字体、音频、缓存等） |
| `get_blendfile_summary_missing_files_for_cli` | `blend_file: str` | 在后台 Blender 打开指定 `.blend` 检查缺失外部文件 |
| `get_blendfile_summary_of_linked_libraries` | 无参数 | 返回直接与间接链接外部 `.blend` 库树 |
| `get_blendfile_summary_of_linked_libraries_for_cli` | `blend_file: str` | 在后台 Blender 打开指定 `.blend` 返回外部链接库树 |
| `get_blendfile_summary_path_info` | 无参数 | 返回当前工程文件路径、保存状态、修改时间与备份信息 |
| `get_blendfile_summary_path_info_for_cli` | `blend_file: str` | 在后台 Blender 打开指定 `.blend` 返回路径与保存信息 |
| `get_blendfile_summary_usage_guess` | 无参数 | 启发式推断当前 `.blend` 主要用途（0–100 评分与置信度） |
| `get_blendfile_summary_usage_guess_for_cli` | `blend_file: str` | 在后台 Blender 打开指定 `.blend` 推断工程用途 |

### C. 截图与渲染出图（5 个）
| 工具名 | 参数与默认值 | 功能说明 |
| :--- | :--- | :--- |
| `get_screenshot_of_area_as_image` | `area_ui_type: str, size_limit_in_bytes: int=0` | 对单个 Blender 区域（如 `VIEW_3D`、`OUTLINER`、`IMAGE_EDITOR`）截图返回 PNG |
| `get_screenshot_of_window_as_image` | `size_limit_in_bytes: int=0` | 对整个 Blender 主窗口截图返回 PNG |
| `get_screenshot_of_window_as_json` | 无参数 | 返回 Blender 窗口布局、工作区、各 Area 矩形与当前选中/活动对象 JSON |
| `render_thumbnail_to_path` | `output_path: str` | 临时覆盖采样/分辨率，快速渲染低开销缩略图至 `output_path` |
| `render_viewport_to_path` | `output_path: str` | 按当前渲染设置将场景渲染至 `output_path`（交互模式下支持延迟等待） |

### D. 工作区与 3D 视口跳转（4 个）
| 工具名 | 参数与默认值 | 功能说明 |
| :--- | :--- | :--- |
| `jump_to_tab_by_name` | `name: str` | 切换当前活动工作区标签页到指定名称 |
| `jump_to_tab_by_space_type` | `space_type: str, allow_edits: bool=False` | 跳转到包含指定编辑器类型的工作区（`allow_edits=True` 时可按需复制/新建区域） |
| `jump_to_view3d_object_by_name` | `name: str, allow_edits: bool=False` | 将 3D 视口镜头聚焦至指定名称对象（`allow_edits=True` 时可自动取消隐藏/启用集合） |
| `jump_to_view3d_object_data_by_name` | `name: str, allow_edits: bool=False` | 定位并聚焦使用指定数据块（Mesh/Curve 等）的 3D 对象 |

### E. Python 代码执行（2 个）
| 工具名 | 参数与默认值 | 功能说明 |
| :--- | :--- | :--- |
| `execute_blender_code` | `code: str` | 在当前已连接的 Blender 实例中执行 Python 代码（`result = {...}` 返回结构化字典） |
| `execute_blender_code_for_cli` | `blend_file: str, code: str` | 启动 `blender --background` 打开指定 `.blend` 执行 Python 代码 |

---

## 2. 官方运行时关键机制

1. **结构化返回值（`result = {...}`）**：`execute_blender_code` 与 `execute_blender_code_for_cli` 通过给全局变量 `result` 赋值字典返回结果（`strict_json=False` 时对无法 JSON 序列化的 Blender 对象回退 `repr()`）；尽量返回结构化字典而非仅靠 `print()`。
2. **安全护栏（`WeakSandboxForLLM`）**：在线执行期间拦截 `sys.exit()` 及会破坏插件/首选项的操作符：`wm.quit_blender`、`wm.read_factory_settings`、`wm.read_factory_userpref`、`wm.read_userpref`（新建空场景请用 `bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)`）。
3. **交互式延迟响应（`check_is_finished`）**：如 `render_viewport_to_path` 等耗时作业在交互模式下通过定时器异步轮询完成；纯后台模式（`--command blender_mcp`）要求同步完成并拒绝延迟任务。
4. **未保存修改同步（`synced_blend_for_cli`）**：所有 6 个 `*_for_cli` 工具在目标 `.blend` 正被前台 Blender 打开且存在未保存修改时，会自动保存临时镜像供后台 Blender 读取并在退出后清理。

---

## 3. 官方 `prompts.yml` (`initial_instructions`) 原文

```text
You have access to Blender tools to interact with a Blender scene directly.
Blender must be running with the MCP add-on enabled and connected.

IMPORTANT: Respect existing structure and naming conventions.
NEVER assume missing values - inspect the scene first.
Do not destructively modify objects without confirmation.

# Bundled Manuals

Reference documentation is bundled alongside this server as plain-text RST files.
Search and read them directly with standard text tools (grep, file read, etc.):
  * `data/api/` - Blender Python API reference (RST files per module/class).
    Consult when writing or debugging `bpy` code: operator signatures, type
    properties, enum values, etc.
  * `data/manual/` - Blender user manual (RST files mirroring the official manual structure).
    Consult for conceptual explanations, workflow guidance, and feature overviews.

# Executing Code

The `execute_blender_code` tool runs Python code via `bpy` in the connected Blender instance.

The `execute_blender_code` tool is a last resort, if there are other tools that provide
the functionality you need, use those instead.

Prefer operators (`bpy.ops`) for standard actions (adding primitives, applying modifiers,
setting origins) - they handle defaults and context. Use the data API (`bpy.data`) for
precise control or to avoid side effects.

Many operators depend on the current mode (Object, Edit, Sculpt, etc.) and which objects
are active/selected. Verify or set the mode first - wrong mode either fails or silently
does nothing.

The **active object** and **selection** are distinct. Many operators require both.
Set them explicitly - do not assume the current state. Operators change selection and
active state as a side effect, so re-set both between sequential operator calls on
different objects.

Update the dependency graph after changes before reading computed properties
(world matrices, modifier results, etc.).

In edit mode, access mesh geometry through the bmesh API, not the regular mesh data API.
Flush bmesh changes back to the mesh - forgetting this silently loses all edits.

Return structured data (dicts, lists) from executed code, not print output.

# Scene & Data Structure

Blender uses a datablock system - objects and their underlying data (meshes, materials,
cameras, etc.) are separate entities.

Hierarchy:
  * **Scene** - top-level container. A .blend can have multiple.
  * **View Layer** - controls collection visibility/selectability.
  * **Collection** - organizational tree. Objects live in collections; can be nested;
    objects can belong to multiple collections.
  * **Object** - has a transform (location, rotation, scale) and references underlying data
    (Mesh, Curve, Camera, etc.). Multiple objects can share the same data (linked duplicates).
  * **Datablocks** - the actual data: geometry, materials, textures, etc.

Key concepts:
  * Objects and data are separate - deleting one does not delete the other.
  * Orphaned datablocks (zero users) are purged on save/reload or manual purge.
  * Objects created via the data API must be linked to a collection to appear in a scene.
  * Shared data: check user count before modifying a datablock - editing a shared mesh
    affects all objects referencing it. Make single-user first if needed.
  * In most cases file assets:
    * Images, Fonts, Sounds, other `.blend` files -  corraspond to a data-block.

Visibility has three independent states:
  * **Viewport hidden** - still fully scriptable.
  * **Disabled in view layer** - excluded; may be inaccessible to view-layer-dependent operators.
  * **Disabled for render** - skipped during render, otherwise normal.
Check these when objects seem "missing" or operators skip them.

Blender defaults to meters. Check scene unit settings before creating dimensioned objects.

Exploring scenes:
  * Walk the collection hierarchy for an overview first.
  * Don't dump entire scenes - inspect progressively for large scenes.
  * Check object types, parenting, modifiers, and materials before making changes.

# Object Types & Creation

Object types: Mesh, Curve, Surface, Metaball, Text (Font), Armature, Lattice,
Empty, Camera, Light, Light Probe, Grease Pencil.

Creating objects:
  * Operators for standard primitives - handle defaults and collection linking.
  * Data API for procedural/batch creation - avoids side effects (selection changes, etc.).
  * Always link new objects to a collection.
  * Names auto-append `.001`, `.002` on collision - capture references immediately
    after creation, never look up by assumed name.

Delete with unlinking enabled to cleanly remove from all collections.

Prefer non-destructive workflows: modifiers over direct mesh edits where possible,
keeping changes adjustable. Apply or edit directly only when final or unavoidable.

# Transformations & Coordinate Spaces

Location, rotation, and scale are in local space (parent-relative, or world if unparented).

Rotation mode determines which property to use (Euler, Quaternion, Axis-Angle).
Always check rotation mode first - writing to the wrong property is silently ignored.

Coordinate spaces:
  * **World** - global. Use the world matrix for reliable positions.
  * **Local** - relative to parent. Location/rotation/scale operate here.
  * **Object** - the object's own system. Mesh vertices are in object space;
    multiply by world matrix for world positions.

Strategies:
  * The origin is the reference point for location; vertices are relative to it.
  * Apply transforms (especially scale) before geometry-dependent operations
    (booleans, physics) - non-uniform scale causes unexpected results.
  * Set the parent inverse matrix when parenting to preserve visual position.
  * Use the world matrix for world-space reads, not manual composition of
    location/rotation/scale.
  * The 3D cursor is a persistent world-space reference used by many operations.
```
