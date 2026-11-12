"""[CASE_R07] Blender 内部 N 面板 (活动状态实时预警 · 暂停锁 · 选区透传与外部模型 API) MCP 协同桥接器
- 适用 (When): 需在 MCP 模式下激活/同步 Blender 视口 N 面板「AI 正在操作 Blender」实时显示、「暂停 AI 操作」安全锁或调用外部 API
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r07_npanel_bridge_and_apis import ensure_npanel_registered, ai_operating, mark_ai_active, get_npanel_selection`
- 产出 (Out) : 自动挂载 N 面板 UI、实时向视口广播 AI 运行中状态、读取用户选区/集合 payload，或直接执行外部模型生成/检索 API
"""

from contextlib import contextmanager
import importlib.util
import json
import os
import sys
import tempfile
import bpy

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_ADDON_PATH = os.path.join(_PLUGIN_ROOT, "addon", "agy_blender_bridge.py")
_SELECTION_CACHE_PATH = os.path.join(tempfile.gettempdir(), "agy_blender_selection.json")


def _load_bridge_module():
    """Loads or retrieves the `agy_blender_bridge` module inside Blender."""
    if "agy_blender_bridge" in sys.modules:
        return sys.modules["agy_blender_bridge"]
    if not os.path.isfile(_ADDON_PATH):
        raise FileNotFoundError(f"Addon file not found at {_ADDON_PATH}")
    spec = importlib.util.spec_from_file_location("agy_blender_bridge", _ADDON_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agy_blender_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def ai_operating(task_name: str = None):
    """
    Context manager that marks AI as actively operating Blender.
    Bridges MCP execution to the N-panel ActivityTracker and triggers an immediate redraw
    so 'AI 正在操作 Blender' (with red warning alert) is displayed in real-time in the Viewport.
    """
    mod = _load_bridge_module()
    recorder = getattr(mod, "get_edit_recorder", lambda: None)()
    tracker = getattr(mod, "get_activity_tracker", lambda: None)()

    if is_ai_paused():
        raise RuntimeError("AI 操作已暂停：请在 Blender N 面板「活动状态」里点「继续 AI 操作」")

    cm = recorder.agent_command() if recorder else None
    if cm:
        cm.__enter__()
    try:
        if mod and hasattr(mod, "_redraw_view3d_panels"):
            mod._redraw_view3d_panels()
        yield
    finally:
        if cm:
            cm.__exit__(None, None, None)
        if tracker:
            tracker.note_agent_end()
            tracker._resync()
        if mod and hasattr(mod, "_redraw_view3d_panels"):
            mod._redraw_view3d_panels()


def mark_ai_active(duration_sec: float = 1.5, task_name: str = None) -> dict:
    """
    Directly marks AI as active right now and triggers an immediate N-panel redraw.
    Useful for standalone MCP statements where bracketing via 'with' is inconvenient.
    """
    mod = _load_bridge_module()
    tracker = getattr(mod, "get_activity_tracker", lambda: None)()
    if tracker:
        tracker.note_agent_end()
        tracker._resync()
    if mod and hasattr(mod, "_redraw_view3d_panels"):
        mod._redraw_view3d_panels()
    return get_ai_activity_status()


def get_ai_activity_status() -> dict:
    """
    Returns the real-time activity state from Blender N-panel ActivityTracker.
    """
    mod = _load_bridge_module()
    tracker = getattr(mod, "get_activity_tracker", lambda: None)()
    if tracker:
        snap = tracker.snapshot(include_current_command=True)
        return {
            "state": snap.get("state", "idle"),
            "agent_active": bool(snap.get("agent_active")),
            "human_active": bool(snap.get("human_active")),
            "ai_paused": is_ai_paused(),
            "last_human_kind": snap.get("last_human_kind"),
        }
    return {
        "state": "idle",
        "agent_active": False,
        "human_active": False,
        "ai_paused": is_ai_paused(),
    }


def _find_mcp_server_module():
    """Locates the official Blender MCP execution server module in sys.modules, ignoring bpy.*."""
    for name, m in list(sys.modules.items()):
        if name.startswith("bpy") or name.startswith("bmesh") or name.startswith("mathutils"):
            continue
        if m and hasattr(m, "_execute_code"):
            mod_file = getattr(m, "__file__", "") or ""
            if "mcp_to_blender_server" in name or "blender_mcp" in name or mod_file.endswith("mcp_to_blender_server.py"):
                return m
    return None


def _hook_official_mcp_server() -> bool:
    """
    Automatically hooks the official Blender MCP execution endpoint (if loaded in Blender)
    so that ANY MCP `execute_blender_code` invocation automatically lights up the
    'AI 正在操作 Blender' visual alert in the N-panel and respects '暂停 AI 操作'.
    """
    target = _find_mcp_server_module()
    if not target or getattr(target, "_dshbb_mcp_hooked", False):
        return bool(target and getattr(target, "_dshbb_mcp_hooked", False))

    orig_execute_code = target._execute_code

    def _instrumented_execute_code(code: str, strict_json: bool):
        if is_ai_paused():
            res_cls = getattr(target, "_ExecResult", None)
            err_dict = {
                "status": "error",
                "error": "AI_PAUSED",
                "message": "AI 操作已暂停：请在 Blender N 面板「活动状态」里点「继续 AI 操作」",
            }
            return res_cls(err_dict) if res_cls else err_dict
        with ai_operating():
            return orig_execute_code(code, strict_json)

    target._execute_code = _instrumented_execute_code
    target._dshbb_mcp_hooked = True
    return True


def ensure_npanel_registered(start_tcp_server: bool = False, hook_mcp_execute: bool = True) -> dict:
    """
    Ensures the `DSH Blender Bridge` + `环境与角色模型API调用` N-Panel is registered in Blender's
    3D Viewport Sidebar (`View3D > Sidebar > DSH Blender Bridge`) and optionally hooks the
    MCP execution pipeline so that AI activity is reflected in real-time on the N-panel.
    """
    mod = _load_bridge_module()
    scene = bpy.context.scene
    already_registered = hasattr(scene, "dshbb_ai_paused") and hasattr(bpy.types, "DSHBB_PT_Panel")
    if not already_registered:
        if not start_tcp_server:
            # Prevent TCP auto-start timer from binding port 9876 in pure MCP mode
            mod._user_stopped_server = True
            mod.register()
            if hasattr(mod, "_dshbb_unregister_auto_start"):
                mod._dshbb_unregister_auto_start()
            if hasattr(scene, "dshbb_auto_start_server"):
                scene.dshbb_auto_start_server = False
            if hasattr(bpy.types, "dshbb_server") and bpy.types.dshbb_server and getattr(bpy.types.dshbb_server, "running", False):
                bpy.types.dshbb_server.stop()
        else:
            mod._user_stopped_server = False
            mod.register()
    elif not start_tcp_server:
        mod._user_stopped_server = True
        if hasattr(mod, "_dshbb_unregister_auto_start"):
            mod._dshbb_unregister_auto_start()
        if hasattr(scene, "dshbb_auto_start_server"):
            scene.dshbb_auto_start_server = False

    # Ensure a bridge server instance exists in-memory so handler methods can be invoked directly via MCP
    if not hasattr(bpy.types, "dshbb_server") or bpy.types.dshbb_server is None:
        bpy.types.dshbb_server = mod.DSHBlenderBridgeServer(port=getattr(scene, "dshbb_port", 9876))

    mcp_hooked = _hook_official_mcp_server() if hook_mcp_execute else False

    return {
        "npanel_registered": hasattr(bpy.types, "DSHBB_PT_Panel"),
        "env_model_api_panel_registered": hasattr(bpy.types, "DSHBB_PT_EnvModelAPI"),
        "ai_paused": bool(getattr(scene, "dshbb_ai_paused", False)),
        "ai_activity_state": get_ai_activity_status()["state"],
        "mcp_execute_hooked": mcp_hooked,
        "selection_mode": getattr(scene, "dshbb_selection_mode", "MULTI"),
    }


def is_ai_paused() -> bool:
    """Returns True if the user clicked '暂停 AI 操作' in the Blender N-panel."""
    scene = getattr(bpy.context, "scene", None)
    return bool(getattr(scene, "dshbb_ai_paused", False)) if scene else False


def get_npanel_selection(prefer_sent: bool = True) -> dict:
    """
    Reads the selection or collection sent by the user via '发送选中到 AGY' in the N-panel
    (falls back to current live viewport selection if none was explicitly sent yet).
    """
    ensure_npanel_registered()
    scene = bpy.context.scene

    # 1. Check in-memory sent selection (`bpy.types.dshbb_last_sent_selection`)
    if prefer_sent:
        sent = getattr(bpy.types, "dshbb_last_sent_selection", None)
        if isinstance(sent, dict) and sent.get("selection"):
            return {"source": "npanel_sent_memory", **sent}

        # 2. Check scene custom property or `/tmp/agy_blender_selection.json`
        raw_scene = scene.get("dshbb_last_sent_selection_json") if scene else None
        if raw_scene:
            try:
                data = json.loads(raw_scene)
                if isinstance(data, dict) and data.get("selection"):
                    return {"source": "npanel_sent_scene_prop", **data}
            except Exception:
                pass

        if os.path.isfile(_SELECTION_CACHE_PATH):
            try:
                with open(_SELECTION_CACHE_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and data.get("selection"):
                    return {"source": "npanel_sent_cache_file", **data}
            except Exception:
                pass

    # 3. Fallback to live selection / active collection target from the N-panel
    server = bpy.types.dshbb_server
    mode = str(getattr(scene, "dshbb_selection_mode", "MULTI") or "MULTI")
    if mode == "COLLECTION" and getattr(scene, "dshbb_collection_target", None) is not None:
        mod = _load_bridge_module()
        col_name = scene.dshbb_collection_target.name
        payload = mod.build_collection_payload(col_name)
        return {"source": "npanel_live_collection", **(payload or {})}

    return {
        "source": "npanel_live_selection",
        "ai_paused": is_ai_paused(),
        "selection": server.get_selection(),
    }


def list_npanel_api_status() -> dict:
    """
    Queries the enabled/configured status of all 5 external asset & AI 3D model APIs
    in the N-panel (`环境与角色模型API调用`):
      - Environment Generation: Poly Haven, Sketchfab, Poly Pizza
      - Model Generation: Hyper3D Rodin, Tencent Hunyuan 3D (plus Tripo in Premium)
    """
    ensure_npanel_registered()
    s = bpy.types.dshbb_server
    return {
        "ai_paused": is_ai_paused(),
        "polyhaven": s.get_polyhaven_status(),
        "sketchfab": s.get_sketchfab_status(),
        "polypizza": s.get_polypizza_status(),
        "hyper3d_rodin": s.get_hyper3d_status(),
        "hunyuan3d": s.get_hunyuan3d_status(),
    }


def call_npanel_api(command_type: str, enable_if_needed: bool = True, **params) -> dict:
    """
    Directly executes any N-panel command or external asset/AI 3D generation API inside
    Blender via MCP (`execute_blender_code`), honoring the N-panel's '暂停 AI 操作' lock.
    """
    ensure_npanel_registered()
    scene = bpy.context.scene

    if enable_if_needed:
        if "polyhaven" in command_type or command_type == "set_texture":
            scene.dshbb_use_polyhaven = True
        elif "sketchfab" in command_type:
            scene.dshbb_use_sketchfab = True
        elif "polypizza" in command_type:
            scene.dshbb_use_polypizza = True
        elif "rodin" in command_type or command_type == "import_generated_asset":
            scene.dshbb_use_hyper3d = True
        elif "hunyuan" in command_type:
            scene.dshbb_use_hunyuan3d = True

    server = bpy.types.dshbb_server
    with ai_operating(task_name=command_type):
        return server.execute_command({"type": command_type, "params": params})

