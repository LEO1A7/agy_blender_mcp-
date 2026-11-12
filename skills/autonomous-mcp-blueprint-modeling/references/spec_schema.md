"""[REF_SPEC_SCHEMA] Building Spec JSON Schema · 矩形并差 DSL (`base+add+sub`) · 边规则与校验码字典
- 适用 (When): P1~P5 构造或修补 `./agy_work/building_spec.json` 轮廓、边规则与细部清单前快速查表
- 用法 (How) : 先 `head -n 6` 检索，再按需查阅 JSON 字段格式、CW 边编号 `E1..En` 与 `E_*` 校验错误码
- 产出 (Out) : 一次写出通过 `spec_validate()` 且可直接驱动 `CASE_R10` 与 `CASE_R11` 的零歧义规范 JSON
"""

# Building Spec JSON Schema 与矩形并差 DSL 规范

所有工作状态唯一持久化于 `./agy_work/building_spec.json`（及 Blender 内 `scene["agy_spec"]` 镜像），由 `CASE_R09` (`examples/recipes/spec_kit.py`) 管理。

## 1. JSON 顶层结构示例

```json
{
  "v": 1,
  "frame": {"yaw_deg": 19.5, "scale_m_per_px": 0.0565, "origin": "ROI SW corner", "src": "plan_roi.png"},
  "levels": [
    {"id": "L0", "name": "Ground", "z": 0.04, "slab": 0.30, "cut": 1.50, "zone": [0, 0, 18, 12]},
    {"id": "L1", "name": "Upper",  "z": 3.22, "slab": 0.30, "cut": 1.50},
    {"id": "L2", "name": "Roof",   "z": 6.37, "slab": 0.28, "cut": 1.00}
  ],
  "outline": {
    "L0": {"union": [[0, 0, 14, 10]], "add": [], "sub": [[5, 3, 9, 7]], "src": "plan", "conf": "H"},
    "L1": {"base": "L0", "add": [[14, 1, 18, 9]], "sub": [], "src": "photo", "conf": "M"},
    "L2": {"union": [[0, 0, 12, 8]], "add": [], "sub": [], "src": "section", "conf": "M"}
  },
  "edge_rules": [
    {"level": "L0", "side": "N", "kind": "SOLID", "openings": [
      {"u": [2.0, 4.5], "z": [0.9, 2.4], "kind": "window"},
      {"u": [9.0, 10.2], "z": [0.0, 2.2], "kind": "door"}
    ]},
    {"level": "L0", "side": "S", "span": [4.0, 10.0], "kind": "OPEN"},
    {"level": "L1", "side": "E", "span": [1.0, 9.0], "kind": "GLAZED", "sill_h": 0.0},
    {"level": "L1", "side": "S", "span": [2.0, 12.0], "kind": "LOUVER", "skin": "LOUVER", "solid": false}
  ],
  "elements": [
    {"id": "HEB220_cols", "kind": "HEB220", "min_objects": 4, "tier": "L2"}
  ],
  "progress": {"phase": "P2", "gates": {"G1": true, "G2": true}, "iters": {}, "last_verify": null},
  "notes": [],
  "deviations": []
}
```

## 2. 轮廓矩形并差 DSL 与边编号规则
1. **局部坐标轴**：正交建筑系 `+X` 东、`+Y` 北、`+Z` 上；单位米（`m`）。`rect` 统一写 `[x0, y0, x1, y1]`。
2. **并差求解顺序**：若指定 `"base": "L0"`，先递归继承 `base` 的 `union/add/sub` 队列，再按序执行本层的 `add`（矩形并）与 `sub`（凹槽扣减或内天井孔洞）——保证后层悬挑可用 `add` 无歧义回填前层 `sub` 凹口。非轴对齐斜边可直接改用 `{"poly": [[x,y],...], "holes": [...]}`。
3. **轮廓环绕与边编号 (`outline_edges`)**：
   - 外环从西北角 (`min_x, max_y`) 起**顺时针**编号为 `E1..En`，内天井孔环编号 `H1_1..`；
   - `side` 按**外法向**标定：`N (+Y)`, `S (-Y)`, `E (+X)`, `W (-X)`, `OBLIQUE`。`span` 为该边在世界轴上的投影区间（`N/S` 取 `X`、`E/W` 取 `Y`、`OBLIQUE` 取边长 `[0, L]`）。
4. **`edge_rules` 字段说明**：
   - `kind`: `"SOLID" | "GLAZED" | "OPEN" | "CANTILEVER" | "RECESS" | "STEP" | "LOUVER" | "SLAT"`
   - `skin`: `"LOUVER" | "SLAT" | "GLAZED" | "NONE" | ""`（需在 `SOLID` 墙外加百叶/格栅表皮时填写）
   - 按 `side`（可选叠加 `span` / `coord`）默认只匹配外环 `E*`；若需单独作用于内天井孔环，设 `"hole": true` 或直写 `"id": "H1_1"`。
   - `RECESS` 浅凹缝填 `"depth": 0.10`（深退台请在 `outline.sub` 扣减）；`STEP` 错台墙填 `"dz": ±Δz`。

## 3. 核心 API 与校验错误码
- 初始化与更新：`spec_init()`, `spec_load()`, `spec_set("outline.L1", ...)`, `spec_patch([{"op": "replace", "path": "...", "value": ...}])`, `spec_note(msg)`
- 轮廓解算与可视化卡片：`resolve_outline("L1")`, `outline_edges("L1")`, `spec_show("L1")`, `spec_digest()`（`<=40` 行恢复卡）, `phase_next()`（`<=20` 行行动卡）
- 结构验证 `spec_validate()` 错误码：`E_LEVEL_NO_ID`、`E_DUP_LEVEL`、`E_LEVEL_NO_Z`、`E_LEVEL_Z_NONMONO`、`E_BAD_SLAB`、`E_MISSING_BASE`、`E_BASE_CYCLE`、`E_EMPTY_OUTLINE`、`E_SHORT_EDGE` (`<0.15m`)、`E_RULE_UNKNOWN_LEVEL`、`E_UNKNOWN_KIND`、`E_UNKNOWN_SKIN`、`E_UNKNOWN_SIDE`、`E_BAD_SPAN`、`E_SPAN_OOB`、开洞越界等。
