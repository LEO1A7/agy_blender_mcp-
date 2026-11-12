---
name: autonomous-mcp-blueprint-modeling
description: >-
  Autonomous 3D CAD, architectural, and hard-surface modeling in Blender from
  multi-view blueprints and reference photos via MCP (`execute_blender_code`).
  Covers pixel-grid calibration, reference detail tiling, handedness alignment,
  3-tier stepwise BMesh & true structural profile construction, visual closeup
  inspection, and perception-driven refinement.
---

# Autonomous MCP Blueprint 3D Modeling Skill

## Overview

This skill provides an interactive, high-precision engineering workflow for modeling 3D assets (architecture, structural steelwork, vehicles, and industrial hardware) in Blender directly from multi-view blueprints and reference photos via MCP (`execute_blender_code`).

To prevent detail loss on complex targets, the agent organizes every build into a **3-Tier Progressive Decomposition (L1 Macro Massing ➔ L2 Structural Profiles & Repetitive Arrays ➔ L3 Fine Hardware & Joints)** and verifies both global proportions and close-up structural details:

1. **Scale Calibration & Detail Inventory**:
   - **Orthographic blueprints / floor plans / sections / dimensioned axonometrics**: Overlay a semi-transparent 50px/100px red/blue coordinate grid (`bin/blueprint_grid_calib.py`) to compute the scale $s$ ($\text{m/px}$) and linear coordinate mappings.
   - **Perspective photos / dimensionless views**: Skip full-image linear grid mapping, **but NEVER skip detail extraction** — run `bin/reference_detail_tiles.py` to generate zoomed, sharpened detail tiles (`contact_sheet.png`) and record a 3-tier **Feature Ledger** (`ledger_set` in `CASE_R08`) covering every visible structural profile (e.g., HEB 220 H-beams), louver shutter, slat array, railing, and joint.
2. **Handedness & Dual Convention Alignment**: Lock the 3D right-hand coordinate system under either `"vehicle"` convention ($\mathbf{Forward} = -Y$, $\mathbf{Starboard} = -X$, $\mathbf{Port} = +X$) or `"plan_north_up"` architectural convention ($\mathbf{North} = +Y$, $\mathbf{East} = +X$, $\mathbf{South/Front} = -Y$, $\mathbf{West/Left} = -X$).
3. **Autonomous Stepwise BMesh & True-Profile Modeling**: Build components progressively across MCP calls. **Never substitute profiled members (H/I-beams, channels, louver blades, rhombic slats, window frames, railings) with plain 6-face bounding boxes or 3 overlapping cubes** — use `CASE_R08` (`case_r08_detail_profiles_and_ledger.py`) or native 2D profile extrusion to produce watertight single-manifold solids.
4. **Visual Inspection, Closeup Verification & MCP Refinement**: Render full-scene 5-camera views (`CASE_R04`) plus close-up renders (`render_closeup`) of key structural joints, run `audit_scene_meshes()`, `detail_audit()`, and `ledger_check()`, and refine components in-place (`CASE_R05`).

> **6-Line Header Progressive Disclosure & Inherited Blender N-Panel Addon**:
> - Every recipe (`examples/recipes/case_r01`..`case_r08`), CLI utility (`bin/*.py`), reference (`references/*.md`), and official Blender MCP file (`examples/official_blender_mcp/`, body untouched) starts with a standardized 6-line `When / How / Out` header. Run `head -n 6` to screen capabilities in ~150 tokens before loading internal content.
> - The Blender N-Panel addon (`addon/agy_blender_bridge.py`: `DSH Blender Bridge` activity/AI-pause lock/`Selection -> AGY` + `环境与角色模型API调用` for Poly Haven, Sketchfab, Poly Pizza, Hyper3D Rodin, Tencent Hunyuan 3D) is available on-demand via `examples/recipes/case_r07_npanel_bridge_and_apis.py` with automatic TCP auto-start suppression in pure MCP mode.

---

## Quick Start

```bash
# Step 0: Fast-screen all modular recipes and CLI utilities (~150 tokens)
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/*.py

# Step 1A (For orthographic blueprints/plans/sections): Generate semi-transparent coordinate grid
python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/blueprint_grid_calib.py \
  --input /path/to/blueprint.png \
  --output /path/to/workspace/blueprint_grid.png \
  --step 50 --major 100 --alpha 0.55

# Step 1B (For perspective reference photos / high-detail façades): Generate zoomed detail tiles + contact sheet
python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/reference_detail_tiles.py \
  --input /path/to/photo.jpg \
  --out-dir /path/to/workspace/detail_tiles \
  --grid 3x3 --zoom 2.0

# Step 2: Stitch rendered views into a composite verification sheet (Mode A, Mode B 1:1 with overlay, or Mode C grid)
python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/compose_triview_sheet.py \
  --side /path/to/workspace/render_side.png \
  --top /path/to/workspace/render_top.png \
  --front /path/to/workspace/render_front.png \
  --iso /path/to/workspace/render_iso.png \
  --iso-rear /path/to/workspace/render_iso_rear.png \
  --output /path/to/workspace/render_triview_sheet.png
```

---

## Detailed Workflow & Best Practices

### Stage 1: Scale Calibration, High-Zoom Plan Crops & 360° Perimeter Walk

1. **Orthographic Drawings (`bin/blueprint_grid_calib.py`) & Mandatory High-Zoom Plan Crops**:
   - Valid for **orthographic tri-views, floor plans, elevations, sections, and dimensioned axonometric views**.
   - If the floor plan is rotated on the sheet relative to the building's main axes, pass `--rotate <deg>` to rectify it first.
   - **Never rely solely on the full-sheet overview**: on composite sheets, always run `--crop u0,v0,u1,v1 --zoom 2.5` (or `3.0`) on the floor plan and sections so room labels, wall steps, and angled bay windows are clearly legible while coordinate labels remain in source pixels.
   - Calculate $s = L_{\text{real}} / \Delta u_{\text{px}}\; (\text{m/px})$ and define `px_to_x`, `px_to_y`, `px_to_z`.
2. **Mandatory 360° Perimeter Walk (Preventing "Photo Bias")**:
   - Perspective photos only show 1–2 visible facades and hide rear/side walls. You **MUST** perform a closed-loop **360° Perimeter Walk** (CCW or CW around the zoomed floor plan, room by room along all exterior walls) and record every wall step, recess, bay window (including oblique/splayed angles $\ne 90^\circ$), and opening on both visible and photo-blind facades into `ledger_set([...])`.
3. **Perspective Photos & Detail Extraction (`bin/reference_detail_tiles.py`)**:
   - Run `bin/reference_detail_tiles.py` and read `contact_sheet.png` + top-ranked detail tiles to inventory every subsystem across three tiers:
     - **L1 (Macro Massing & Polygon Footprint)**: Primary column axes, closed exterior wall polygon vertices (including non-orthogonal turns), floor slab elevations, roof planes.
     - **L2 (Structural Profiles & Repetitive Arrays)**: Exposed steel columns/beams (`HEB220`, `HEA`, `IPE`, `UPN`, `RHS`, `SHS`, `L`), timber slat cladding arrays (`add_slat_array`), folding louver shutters (`add_louver_leaf`), railings (`add_railing`).
     - **L3 (Fine Hardware, Splayed Bays & Joints)**: Splayed/polygonal or stepped bay windows (`add_splayed_bay`), multi-mullion window frames & recessed glazing (`add_window`), chimney rings/flanges (`add_flange_ring`), base plates, flashing caps.
   - Register all planned features in the scene ledger via `ledger_set([...])` from `case_r08_detail_profiles_and_ledger`.

---

### Stage 2: Handedness, Coordinate Conventions & Polygon Vertex Extraction

- **Extract 2D Plan Polygon Vertices Before Modeling Massing**:
  - Never default to an axis-aligned rectangular box for a building footprint or bay window without first extracting the corner coordinates `[(x0,y0), (x1,y1), ...]` from the zoomed floor plan. Explicitly check whether any wall segment or bay window has a non-$90^\circ$ splayed/oblique edge.
- `setup_workbench_studio_and_cameras(..., convention=...)` supports two standard right-handed conventions and automatically computes camera `standoff` and `clip_end` from the live scene bounding box so cameras never clip inside large buildings:

| Convention | Primary Use | `Cam_Front` looks from | `Cam_Side_Left` looks from | `Cam_Top` Up-on-Image |
| :--- | :--- | :--- | :--- | :--- |
| **`"vehicle"`** (default) | Vehicles, aircraft, machinery (Nose = $-Y$, Up = $+Z$, Starboard = $-X$, Port = $+X$) | $-Y \to +Y$ (Left=$-X$, Right=$+X$) | $+X \to -X$ (Left=$-Y$ Nose, Right=$+Y$ Rear) | $-X$ (Starboard at top, Nose $-Y$ at left) |
| **`"plan_north_up"`** | Architecture & site plans (North = $+Y$, South = $-Y$, East = $+X$, West = $-X$, Up = $+Z$) | $-Y \to +Y$ South elevation (Left=$-X$ West, Right=$+X$ East) | $-X \to +X$ West elevation (Left=$+Y$ North, Right=$-Y$ South) | $+Y$ (North at top, East $+X$ at right) |

---

### Stage 3: Autonomous Stepwise BMesh & True-Profile Modeling

- **Native Random Object Color at Modeling Start (Zero Context Overhead)**:
  - As soon as modeling begins, switch Blender's built-in Viewport/Workbench Shading to **Object -> Random** (`color_type = 'RANDOM'`, `show_object_outline = True`) so every object is automatically differentiated for VLM inspection without extra code or palette context:
    ```python
    bpy.context.scene.display.shading.color_type = 'RANDOM'
    for a in [a for s in bpy.data.screens for a in s.areas if a.type == 'VIEW_3D']:
        a.spaces.active.shading.color_type = 'RANDOM'
        a.spaces.active.shading.show_object_outline = True
    ```
- **Never Use Box Stand-Ins for Profiled or Splayed Members**:
  - Use `from case_r08_detail_profiles_and_ledger import add_steel_member, add_polygon_slab, add_polyline_wall, add_splayed_bay, add_slat_array, add_louver_leaf, add_railing, add_window, add_flange_ring, finalize_object`:
    - `add_polygon_slab(bm, poly_xy, z0, z1)` & `add_polyline_wall(bm, pts_xy, z0, z1, thickness)`: Extrude arbitrary 2D floor/wall polygons with non-$90^\circ$ corners directly from plan coordinates.
    - `add_splayed_bay(bm, poly_xy, z0, z1, open_edge=0, panes=(2,1))`: Builds a trapezoidal/splayed or stepped bay window (sill slab + head slab + multi-pane window frames along each exterior edge) directly from its plan polygon `poly_xy`.
    - `add_steel_member(bm, "HEB220", p0, p1, up=(1,0,0), fillet_segs=2)`: Extrudes a true 12-vertex (or filleted) single-manifold H-section between any two 3D points `p0` and `p1` with zero internal overlapping faces.
    - `add_slat_array(bm, p0, p1, z0, z1, pitch, slat_w, slat_t, normal, rhombic=True)`: Generates an array of individual rhombic or rectangular timber slats along a wall span.
    - `add_louver_leaf(bm, origin, run, normal, width, height, blades=24, tilt_deg=35.0)`: Builds a perimeter shutter frame populated with individually tilted louver blades.
    - `add_railing(bm, path, height=1.0, mid_rails=3)`: Builds end/intermediate posts, top handrail, and multiple horizontal intermediate bars along a 3D path.
    - `add_window(bm, origin, run, normal, width, height, panes=(2,2))`: Builds outer frame, mullions, transoms, and recessed glass panes (`materials=[mat_frame, mat_glass]` in `finalize_object`).
- **Thin-Member Safe Bevel**: Both `create_mesh_object` (`CASE_R01`) and `finalize_object` (`CASE_R08`) automatically clamp bevel width to $\le 30\%$ of the 10th-percentile edge length so thin louver blades or web plates are never distorted.

---

### Stage 4: Visual Inspection, Mandatory Mode B Overlay Gate & Refinement

1. **Global, Horizontal Plan-Section & Closeup Renders (`CASE_R04`) + Mandatory Mode B Overlay**:
   - **Geometry Verification (`'RANDOM'`)**: Keep `color_type = 'RANDOM'` while calling `setup_workbench_studio_and_cameras(col_studio, convention="plan_north_up" | "vehicle")` and `render_views(output_dir)`.
   - **Mandatory Mode B 1:1 Blueprint Overlay Gate (Never substitute `--panel` gallery for Mode B)**:
     - Whenever orthographic floor plans or elevations exist, you **MUST** verify 1:1 contour alignment before delivery using Mode B `--overlay`.
     - For buildings where the roof hides floor-plan walls/bays in `Cam_Top`, call `render_plan_section(out_path, cut_z=1.5)` (`CASE_R04`) to slice off the roof at $z=1.5\text{ m}$ and render a true horizontal plan section, then run:
       ```bash
       python3 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/compose_triview_sheet.py \
         --blueprint /path/to/blueprint.png --crop u0,v0,u1,v1 \
         --render /path/to/render_plan_sec.png --overlay --auto-align \
         --view-label PLAN --output /path/to/overlay_plan_check.png
       ```
       (Pass `--rotate-bp <deg>` if the floor plan on the blueprint is tilted.) Verify that every exterior wall angle and bay window on `[4] OVERLAY` coincides with the blueprint lines.
   - **Closeup Inspection**: Call `render_closeup(out_path, target=(x,y,z), size=1.8, direction=(1,1,-0.3))` on 1–2 key structural joints or bay windows.
   - **Material Inspection & Final Delivery (`'MATERIAL'`)**: Once overlay alignment and details are verified and materials are assigned, switch `color_type = 'MATERIAL'` on `scene.display.shading` and `VIEW_3D` `shading`.
2. **Automated Topology & Detail Audit (`CASE_R02` + `CASE_R08`)**:
   - Run `audit_scene_meshes()` (checks non-manifold edges, degenerate faces, unapplied scales, and inverted-normal negative-volume shells).
   - Run `detail_audit()` (flags any object named `column`, `beam`, `heb`, `louver`, `slat`, `railing`, etc. that was modeled as a 6-face bounding box) and `ledger_check()` (verifies every registered L1/L2/L3 feature exists in the scene).
3. **In-Place Perception & Refinement (`CASE_R05`)**:
   - Use `inspect_scene_components`, `transform_component` (mesh-level transform without `bpy.ops` context errors), and `replace_component_geometry` (preserves material slots and world matrix) to fix any alignment or detail discrepancies before final delivery.
