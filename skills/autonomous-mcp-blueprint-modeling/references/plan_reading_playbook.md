"""[REF_PLAN_PLAYBOOK] 建筑平立剖面与实景图读图核对清单 · 斜置转正 · 虚实悬挑与错层辨识
- 适用 (When): P1/P2 从平面、剖面与透视照片提取比例尺、偏航角、各层轮廓矩形及立面虚实规则时查阅
- 用法 (How) : 先阅读 6 行报文头，按需精读各条目避免虚线投影、绿化遮挡或错层分区误判
- 产出 (Out) : 零错位地填写 `building_spec.json` 的 `levels`、`outline` 与 `edge_rules`
"""

# 建筑平立剖面与实景复合图读图核对清单 (P1–P2)

## 1. 斜置平面图处理准则 (`plan_prep.py`)
1. **不要直接手量斜图**：凡建筑主轴与画幅水平/垂直轴不平行的平面图，必须先运行：
   `python3 bin/plan_prep.py scan --input <plan.jpg> --out agy_work`
   观察带编号候选偏航框的缩略拼图（如 `+19.5°` 与其 `-90°/+90°` 等价朝向），结合指北针或透视图朝向选出“主入口/南立面朝下方 (`-Y`)、北向朝上方 (`+Y`)”的唯一角度。
2. **裁切 + 精化 + 米制坐标网格**：
   `python3 bin/plan_prep.py build --input <plan.jpg> --angle <deg> --roi u0,v0,u1,v1 --refine --layers --out agy_work`
   若总图绿化/等高线噪点多导致全局角度微偏，优先先标 `--roi` 建筑核心框再加 `--refine`（ROI 内高分辨率角点+方向梯度精细拟合），生成已转正的 `plan_rot.png`、带像素/米制刻度的 `plan_roi.png` 与可选双层分图 `plan_layers.png`。
3. **像素与真实尺度映射**：所有平面直角坐标一律用旋转后且带 `m` 格网的 `plan_roi.png` 直接读取，禁止用原斜图坐标做正交估算。

## 2. 剖面图与标高带拟合 (`section_levels.py`)
1. **自动抓楼板中心线**：
   `python3 bin/section_levels.py --input <section.jpg> --elev 0.04,3.22,6.37,9.52 --mark agy_work/sec_mark.png --out-json agy_work/sec_meta.json`
   工具自动识别水平楼板强响应带并最小二乘拟合 `scale_m_per_px` 与截距；若地形条带、窗框横挺或屋面斜坡混入候选，按终端返回的索引编号用 `--drop <v_px>` 剔除干扰带后重跑。
2. **剖面→平面比例尺传递**：
   `python3 bin/plan_prep.py scale-from-section --meta agy_work/plan_meta.json --section-scale <s_sec> --section-span-px <L_sec_px> --plan-span u0,v0,u1,v1 --update-spec agy_work/building_spec.json`
   若已知点像素与真实距离转换，可用 `px2m` 核对点坐标，再用 `--scale` 重跑 `build` 绘制米制红蓝网 `plan_roi.png`。

## 3. 平面虚实与凹凸进退四条硬规则
1. **实墙线 (`SOLID`) vs 虚线 (`OVERHANG/CANTILEVER`)**：
   - 底层平面中**长点划线/双虚线包围、但内部无闭合实体粗墙体**的区域，是二层**外挑悬挑楼板**在地面的投影——**不得并入 `L0.outline`**，应写入 `L1.outline.add` 并保留 `L0` 下方开敞投影区！
   - 反之，底层沿外轮廓内凹的区域（如门廊入口、架空灰空间）用 `L0.outline.sub` 扣除，二层若外挑覆盖该区域则在 `L1.outline` 中设置 `{"base": "L0", "add": [...]}` 加回。
2. **内天井与采光井 (`holes`)**：由周围实墙围合、无首层楼板覆盖的中庭必须写入 `sub` 列表（不可事后用纯矩形凑整吞并）。
3. **玻璃幕墙 / 落地窗 / 开敞廊 (`GLAZED` / `OPEN`)**：
   - 双细平行线 + 无实墙填充且透视图可见大面积玻璃：设 `kind="GLAZED"`（全高落底设 `sill_h: 0.0`，半高窗台设 `sill_h: 0.9`）；
   - 仅柱廊/挑檐覆盖且无玻璃封堵：设 `kind="OPEN"`（`Verify` 阶段将检验其柱位与无实墙堵死）。
4. **外挂木格栅 (`SLAT`) 与折扇百叶 (`LOUVER`)**：根据 `reference_detail_tiles.py` 高密切片确认立面表皮是“竖向格栅阵 (`SLAT`)”还是“带框多叶折叠百叶 (`LOUVER`)”，并注意其 `solid: true|false`（身后是实墙开洞还是落地玻璃）。

## 4. 错层（Split-Level）与多区域 (`zone`)
当平面同一高程区间存在不同半层（例如主楼首层 `z=0.04` 与西侧错层半层 `z=1.60`）时：
- 必须为互不重叠的两个分区分别填写 `"zone": [x0, y0, x1, y1]`；
- 错层分界处的台阶/错台高差立壁用 `kind="STEP", dz=±(Δz)` 描述，防止跨区楼板误触剖切高度或互相截断层高。
