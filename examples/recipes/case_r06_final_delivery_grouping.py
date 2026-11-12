"""[CASE_R06] 最终交付双层群组构建与过程组件(__hide_r*__)紧贴归档兜底配方 (Final Delivery Grouping Fallback)
- 适用 (When): 整体建模与视觉调优完成后、最终保存 `.blend` 前的最后一步按需调用（建模期允许自由建集合或保持扁平，最后一步兜底归整）
- 用法 (How) : 在 `execute_blender_code` 中 `from case_r06_final_delivery_grouping import execute_grouping_in_blender; print(execute_grouping_in_blender()["ascii_tree"])`
- 产出 (Out) : 自动建立 `<Class>/<Class>_<Sub>` 交付群组与紧贴的 `<Class>_WIP/<Class>_<Sub>_WIP` 隐藏过程群组并清理空集合
"""

import fnmatch
import re
import bpy

HIDE_RE = re.compile(r"^__hide_r(\d+)__(.+)$")
AUX_PREFIXES = ("camera", "cam", "light", "sun", "lamp", "ref", "env", "helper", "axis", "grid", "key_sun", "fill_sun", "rim_sun")


def _strip_wip_prefix(obj_name: str):
    m = HIDE_RE.match(obj_name)
    if m:
        return True, int(m.group(1)), m.group(2)
    if obj_name.startswith("__wip__"):
        return True, 1, obj_name[len("__wip__"):]
    return False, 0, obj_name


def _classify_object(obj, custom_map=None):
    is_wip, r_num, base_name = _strip_wip_prefix(obj.name)
    custom_map = custom_map or {}

    for c_name, sub_spec in custom_map.items():
        if isinstance(sub_spec, dict):
            for s_name, patterns in sub_spec.items():
                pats = patterns if isinstance(patterns, list) else [patterns]
                for pat in pats:
                    if fnmatch.fnmatch(base_name, pat) or base_name.startswith(pat):
                        cat = f"{c_name}_WIP" if is_wip else c_name
                        sub_base = s_name if s_name.startswith(f"{c_name}_") else f"{c_name}_{s_name}"
                        sub = f"{sub_base}_WIP" if is_wip else sub_base
                        return c_name, cat, sub, is_wip, r_num

    low = base_name.lower()
    if obj.type in {"CAMERA", "LIGHT", "LIGHT_PROBE", "SPEAKER"} or any(
        low == p or low.startswith(p + "_") for p in AUX_PREFIXES
    ):
        c_name = "00_Scene_Env"
        if obj.type == "CAMERA" or low.startswith(("camera", "cam")):
            sub_base = "00_Scene_Env_Camera"
        elif obj.type in {"LIGHT", "LIGHT_PROBE"} or low.startswith(("light", "sun", "lamp", "key_sun", "fill_sun", "rim_sun")):
            sub_base = "00_Scene_Env_Light"
        else:
            sub_base = "00_Scene_Env_Aux"
        cat = f"{c_name}_WIP" if is_wip else c_name
        sub = f"{sub_base}_WIP" if is_wip else sub_base
        return c_name, cat, sub, is_wip, r_num

    tokens = [t for t in base_name.split("_") if t]
    c_name = tokens[0] if tokens else "Model"
    sub_tok = tokens[1] if len(tokens) >= 2 else "Main"
    sub_base = f"{c_name}_{sub_tok}"
    cat = f"{c_name}_WIP" if is_wip else c_name
    sub = f"{sub_base}_WIP" if is_wip else sub_base
    return c_name, cat, sub, is_wip, r_num


def _get_or_create_collection(name: str):
    return bpy.data.collections.get(name) or bpy.data.collections.new(name)


def _set_layer_collection_hidden(layer_col, target_names: set):
    for child in layer_col.children:
        if child.name in target_names:
            child.hide_viewport = True
        _set_layer_collection_hidden(child, target_names)


def execute_grouping_in_blender(custom_map=None, dry_run=False, always_create_wip=False) -> dict:
    scene = bpy.context.scene
    root_col = scene.collection
    all_objs = list(scene.objects)

    plan = {}
    for obj in all_objs:
        c_name, _, sub_col, is_wip, _ = _classify_object(obj, custom_map)
        entry = plan.setdefault(c_name, {"deliver": {}, "wip": {}})
        bucket = entry["wip"] if is_wip else entry["deliver"]
        bucket.setdefault(sub_col, []).append(obj.name)

    sorted_classes = sorted(plan.keys(), key=lambda x: (0 if x == "00_Scene_Env" else 1, x.lower()))

    if not dry_run:
        wip_col_names = set()
        ordered_top_cols = []

        for c_name in sorted_classes:
            info = plan[c_name]
            if info["deliver"] or not info["wip"]:
                deliv_col = _get_or_create_collection(c_name)
                deliv_col.hide_viewport = False
                deliv_col.hide_render = False
                if deliv_col.name not in root_col.children:
                    root_col.children.link(deliv_col)
                ordered_top_cols.append(deliv_col)

                for sub_name in sorted(info["deliver"].keys(), key=lambda s: s.lower()):
                    sub_col = _get_or_create_collection(sub_name)
                    sub_col.hide_viewport = False
                    sub_col.hide_render = False
                    if sub_col.name not in deliv_col.children:
                        deliv_col.children.link(sub_col)
                    for o_name in sorted(info["deliver"][sub_name]):
                        obj = bpy.data.objects.get(o_name)
                        if obj is None:
                            continue
                        for old_c in list(obj.users_collection):
                            if old_c != sub_col:
                                old_c.objects.unlink(obj)
                        if obj.name not in sub_col.objects:
                            sub_col.objects.link(obj)
                        obj.hide_viewport = False
                        obj.hide_render = False

            if info["wip"] or (always_create_wip and c_name != "00_Scene_Env"):
                wip_c_name = f"{c_name}_WIP"
                wip_col = _get_or_create_collection(wip_c_name)
                wip_col.hide_viewport = True
                wip_col.hide_render = True
                if wip_col.name not in root_col.children:
                    root_col.children.link(wip_col)
                ordered_top_cols.append(wip_col)
                wip_col_names.add(wip_c_name)

                for sub_wip_name in sorted(info["wip"].keys(), key=lambda s: s.lower()):
                    sub_wip_col = _get_or_create_collection(sub_wip_name)
                    sub_wip_col.hide_viewport = True
                    sub_wip_col.hide_render = True
                    if sub_wip_col.name not in wip_col.children:
                        wip_col.children.link(sub_wip_col)
                    wip_col_names.add(sub_wip_name)
                    for o_name in sorted(info["wip"][sub_wip_name]):
                        obj = bpy.data.objects.get(o_name)
                        if obj is None:
                            continue
                        for old_c in list(obj.users_collection):
                            if old_c != sub_wip_col:
                                old_c.objects.unlink(obj)
                        if obj.name not in sub_wip_col.objects:
                            sub_wip_col.objects.link(obj)
                        obj.hide_viewport = True
                        obj.hide_render = True

        managed = {c.name for c in ordered_top_cols}
        for c_name in sorted_classes:
            managed.update(plan[c_name]["deliver"].keys())
            managed.update(plan[c_name]["wip"].keys())
        removed_empty = []
        while True:
            removed_in_pass = False
            for col in list(bpy.data.collections):
                if col.name not in managed and len(col.objects) == 0 and len(col.children) == 0:
                    removed_empty.append(col.name)
                    bpy.data.collections.remove(col)
                    removed_in_pass = True
            if not removed_in_pass:
                break

        for col in ordered_top_cols:
            if col.name in root_col.children:
                root_col.children.unlink(col)
            root_col.children.link(col)

        try:
            _set_layer_collection_hidden(bpy.context.view_layer.layer_collection, wip_col_names)
        except Exception:
            pass
    else:
        removed_empty = []

    lines = ["Scene Collection (场景集合)"]
    top_entries = []
    for c_name in sorted_classes:
        info = plan[c_name]
        if info["deliver"] or not info["wip"]:
            top_entries.append((c_name, False, info["deliver"]))
        if info["wip"] or (always_create_wip and c_name != "00_Scene_Env"):
            top_entries.append((f"{c_name}_WIP", True, info["wip"]))

    for idx, (col_title, is_wip_col, sub_dict) in enumerate(top_entries):
        is_last_top = (idx == len(top_entries) - 1)
        branch = "└── " if is_last_top else "├── "
        tag = "[🚫隐藏过程群组]" if is_wip_col else "[👁️交付群组]"
        lines.append(f"{branch}{col_title}  {tag}")
        sub_keys = sorted(sub_dict.keys(), key=lambda s: s.lower())
        for s_idx, s_name in enumerate(sub_keys):
            is_last_sub = (s_idx == len(sub_keys) - 1)
            prefix = "    " if is_last_top else "│   "
            s_branch = "└── " if is_last_sub else "├── "
            objs = sorted(sub_dict[s_name])
            preview = ", ".join(objs[:3]) + (f" ... (+{len(objs)-3})" if len(objs) > 3 else "")
            lines.append(f"{prefix}{s_branch}{s_name} ({len(objs)}): {preview}")

    return {
        "ok": True,
        "delivered_count": sum(len(v) for c in plan.values() for v in c["deliver"].values()),
        "wip_archived_count": sum(len(v) for c in plan.values() for v in c["wip"].values()),
        "top_collections_order": [t[0] for t in top_entries],
        "removed_empty_collections": removed_empty,
        "ascii_tree": "\n".join(lines),
    }
