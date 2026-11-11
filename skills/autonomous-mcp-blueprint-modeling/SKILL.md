---
name: autonomous-mcp-blueprint-modeling
description: >-
  Autonomous 3D CAD and hard-surface modeling in Blender from multi-view
  blueprints via MCP (`execute_blender_code`). Covers pixel-grid calibration,
  handedness alignment, autonomous stepwise BMesh construction, visual inspection,
  and perception-driven refinement.
---

# Autonomous MCP Blueprint 3D Modeling Skill

## Overview

This skill provides an interactive, zero-boilerplate engineering workflow for modeling 3D assets in Blender directly from multi-view blueprints via MCP (`execute_blender_code`).

In successful modeling runs, the agent assesses the overall complexity and autonomously organizes the task into stepwise, component-by-component builds. Leveraging MCP's interactive feedback loop to construct, inspect, and refine parts progressively reduces cognitive load and allows early correction of proportions before final assembly:

1. **Pixel-Ruler Grid Calibration (On-Demand)**: Applicable when inputs include orthographic floor plans, tri-views, elevations, or sections — overlay a 50px/100px dual-color coordinate grid onto the input blueprint image to calculate the primary scale and establish linear pixel-to-meter mapping functions. Automatically skipped for perspective photos or dimensionless axonometric views.
2. **Handedness & Projection Alignment**: Lock the 3D right-hand coordinate system ($\mathbf{Forward} = -Y$, $\mathbf{Up} = +Z$, $\mathbf{Right/Starboard} = -X$, $\mathbf{Left/Port} = +X$) against the blueprint projections before placing asymmetric features.
3. **Autonomous Stepwise BMesh Modeling**: Model parts progressively using native `bmesh` / `bpy` statements. Advanced geometric algorithms and audit tools can be queried on-demand from `examples/`.
4. **Visual Inspection & MCP Refinement**: Render orthographic and isometric views to cross-reference alignments, inspect live object states over MCP, and adjust transforms or geometry in-place.

> **Official Repository & Recipe Base**:
> The complete official Blender MCP repository and auxiliary CAD operator/audit recipes are located under `examples/` (`examples/README.md` provides an index of lookup keywords and function signatures). Query them on-demand as needed.

---

## Quick Start

```bash
# Step 1: Generate a 50px/100px coordinate ruler grid on the input blueprint
python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/blueprint_grid_calib.py \
  --input /path/to/blueprint.png \
  --output /path/to/workspace/blueprint_grid.png \
  --step 50 --major 100

# Step 2: Read blueprint_grid.png, calculate scale s (m/px), and autonomously organize
# the modeling into progressive MCP calls (e.g., Hull -> Running Gear -> Turret/Body -> Details).

# Step 3: Stitch rendered views into a composite verification sheet
python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/compose_triview_sheet.py \
  --side /path/to/workspace/render_side.png \
  --top /path/to/workspace/render_top.png \
  --front /path/to/workspace/render_front.png \
  --iso /path/to/workspace/render_iso.png \
  --output /path/to/workspace/render_triview_sheet.png
```

---

## Detailed Workflow & Best Practices

### Stage 1: Blueprint Pixel-Ruler Calibration (On-Demand)

> **Applicability**: Apply this stage only when inputs include **orthographic floor plans, tri-views, elevations, or sections**. If the input consists solely of **perspective views/photos or dimensionless axonometric views**, automatically skip this calibration constraint and proceed using structural proportions.

Run `bin/blueprint_grid_calib.py` to draw coordinate grid lines every 50 pixels (bold every 100 pixels).

1. **Calculate Scale $s$**:
   Find the longest annotated dimension on the drawing (e.g., Length $L_{\text{real}} = 7.730\text{ m}$ across $\Delta u = 550\text{ px}$):
   $$s = \frac{L_{\text{real}}}{\Delta u_{\text{px}}} = \frac{7.730}{550} \approx 0.01405\text{ m/px}$$
2. **Define Conversion Functions**:
   ```python
   def px_to_y(u_px: float) -> float:
       return (u_px - u0_mid) * s          # -Y is Forward, +Y is Rear

   def px_to_z(v_px: float) -> float:
       return (v0_ground - v_px) * s       # +Z is Up, Z=0 at ground

   def top_py_to_x(v_px: float) -> float:
       return (v_px - v0_top_center) * s   # -X is Starboard, +X is Port
   ```

---

### Stage 2: Handedness & Coordinate Consistency

- With **Forward** $= (0, -1, 0)$ and **Up** $= (0, 0, 1)$, the right-hand rule defines:
  $$\mathbf{Starboard\; (Right)} = \mathbf{Forward} \times \mathbf{Up} = (-1, 0, 0) = -X$$
  $$\mathbf{Port\; (Left)} = +X$$
- When the vehicle points **Left** ($-Y$) in the Side and Top views:
  | View | Camera Location | Camera Euler XYZ (deg) | Image Left | Image Right | Image Top | Image Bottom |
  | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
  | **Side View (`Cam_Side_Left`)** | $(+15.0, y_c, z_c)$ | $(90^\circ, 0^\circ, +90^\circ)$ | Forward ($-Y$) | Rear ($+Y$) | Up ($+Z$) | Down ($-Z$) |
  | **Top View (`Cam_Top`)** | $(0.0, y_c, +15.0)$ | $(0^\circ, 0^\circ, +90^\circ)$ | Forward ($-Y$) | Rear ($+Y$) | Starboard ($-X$) | Port ($+X$) |
  | **Front View (`Cam_Front`)** | $(0.0, -15.0, z_c)$ | $(90^\circ, 0^\circ, 0^\circ)$ | Starboard ($-X$) | Port ($+X$) | Up ($+Z$) | Down ($-Z$) |

---

### Stage 3: Autonomous Stepwise BMesh Modeling

- The agent autonomously decides the decomposition granularity and build sequence, executing modular `bmesh` / `bpy` blocks via MCP.
- Avoid capping multi-vertex polygonal roofs with single concave N-gons; bridge symmetric vertex pairs into planar quads where appropriate to eliminate shading creases.
- Refer to `examples/README.md` for ready-to-use parametric snippets (e.g. track loops, polyhedral shells, or non-manifold topology checks) whenever specialized algorithms are required.

---

### Stage 4: Visual Inspection & MCP Refinement

1. **Workbench Technical Renders**:
   - Render orthographic side/top/front and perspective isometric views (Cavity + Outline).
   - Optionally enable high-contrast multi-subsystem coloring (`scene.display.shading.color_type = 'OBJECT'` or refer to recipe `set_diagnostic_color_mode`) to reveal part collisions and misalignments clearly in screenshots.
   - Run `compose_triview_sheet.py` to generate composite multi-view or 1:1 side-by-side contour sheets.
2. **State Perception & Direct Modification**:
   - Query live object dimensions and positions via MCP (e.g. using official summary tools or custom inspection scripts).
   - Apply translations, scale corrections, mesh replacements, or add missing secondary details directly through MCP calls.

---

## Practical Modeling Tips

1. **In-Place Refinement**: When visual review reveals minor alignment drifts (e.g., turret seated 5cm too far forward), query current coordinates and nudge the component via MCP transforms instead of restarting the build from scratch.
2. **Cross-View Verification**: Always cross-reference asymmetric elements (e.g., driver hatches, commander optics) between Top and Front views before committing detailed geometry.
3. **Clean Hierarchy**: When parenting secondary attachments to primary structures, maintain zero-offset transformations (`child.matrix_parent_inverse = parent.matrix_world.inverted()`).
