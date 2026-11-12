#!/usr/bin/env python3
"""Plugin static lint: 6-line When/How/Out headers, doc size budgets, dead diagnostic-color grep,
and dependency boundary checks (CLI must not import bpy; Blender recipes must not import PIL/scipy/skimage).
"""

import argparse
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEAD_PATTERNS = (
    "DIAGNOSTIC_COLOR_PALETTE",
    "GENERIC_GROUP_PALETTE",
    "infer_diagnostic_group",
    "diagnostic_group",
    "obj.color",
)

FORBIDDEN_IN_RECIPES = {"PIL", "scipy", "skimage", "cv2", "shapely"}
FORBIDDEN_IN_BIN = {"bpy", "bmesh", "mathutils"}


def _top_lines(path, n=6):
    with open(path, "r", encoding="utf-8") as f:
        lines = [next(f, "") for _ in range(n)]
    return "".join(lines), lines


def _check_header(path, is_md=False):
    text, lines = _top_lines(path, 6)
    errs = []
    if not text.strip():
        return [f"{path}: empty file"]
    if not any(tag in lines[0] for tag in ("[", "# ")):
        errs.append(f"{path}: line 1 missing [TAG] header")
    for token in ("When", "How", "Out"):
        if token not in text:
            errs.append(f"{path}: top 6 lines missing '{token}'")
    if not is_md and not any(l.strip() == '"""' for l in lines[:6]):
        errs.append(f"{path}: docstring header must close with '\"\"\"' within top 6 lines")
    return errs


def _check_imports(path, forbidden):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in forbidden:
                    hits.append(f"{path}:{node.lineno}: forbidden import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in forbidden:
                hits.append(f"{path}:{node.lineno}: forbidden import from '{node.module}'")
    return hits


def _grep_dead(paths):
    hits = []
    regex = re.compile("|".join(re.escape(p) for p in DEAD_PATTERNS))
    for path in paths:
        if os.path.basename(path) == "CHANGELOG.md":
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, 1):
                m = regex.search(line)
                if m:
                    hits.append(f"{path}:{idx}: stale symbol '{m.group(0)}'")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-m3", action="store_true", help="Warn instead of failing on M3 doc budgets/doc refs")
    args = ap.parse_args()

    errors = []
    warnings = []

    recipe_dir = os.path.join(ROOT, "examples", "recipes")
    bin_dir = os.path.join(ROOT, "bin")
    ref_dir = os.path.join(ROOT, "skills", "autonomous-mcp-blueprint-modeling", "references")

    code_files = []
    for fn in sorted(os.listdir(recipe_dir)):
        if fn.endswith(".py"):
            p = os.path.join(recipe_dir, fn)
            code_files.append(p)
            errors.extend(_check_header(p, is_md=False))
            errors.extend(_check_imports(p, FORBIDDEN_IN_RECIPES))
    for fn in sorted(os.listdir(bin_dir)):
        if fn.endswith(".py"):
            p = os.path.join(bin_dir, fn)
            code_files.append(p)
            errors.extend(_check_header(p, is_md=False))
            errors.extend(_check_imports(p, FORBIDDEN_IN_BIN))
    if os.path.isdir(ref_dir):
        for fn in sorted(os.listdir(ref_dir)):
            if fn.endswith(".md"):
                errors.extend(_check_header(os.path.join(ref_dir, fn), is_md=True))

    errors.extend(_grep_dead(code_files))

    doc_files = [
        os.path.join(ROOT, "rules", "AGENTS.md"),
        os.path.join(ROOT, "skills", "autonomous-mcp-blueprint-modeling", "SKILL.md"),
        os.path.join(ROOT, "README.md"),
        os.path.join(ROOT, "examples", "README.md"),
    ]
    doc_dead = _grep_dead([p for p in doc_files if os.path.exists(p)])
    agents_md = os.path.join(ROOT, "rules", "AGENTS.md")
    skill_md = os.path.join(ROOT, "skills", "autonomous-mcp-blueprint-modeling", "SKILL.md")
    agents_lines = sum(1 for _ in open(agents_md, encoding="utf-8"))
    skill_lines = sum(1 for _ in open(skill_md, encoding="utf-8"))

    budget_errs = list(doc_dead)
    if agents_lines > 40:
        budget_errs.append(f"rules/AGENTS.md is {agents_lines} lines (> 40 limit)")
    if skill_lines > 150:
        budget_errs.append(f"SKILL.md is {skill_lines} lines (> 150 limit)")

    if args.pre_m3:
        warnings.extend(budget_errs)
    else:
        errors.extend(budget_errs)

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"FAIL: {e}")

    print(f"lint_plugin: {len(code_files)} code files checked | AGENTS={agents_lines}L | SKILL={skill_lines}L | errors={len(errors)} warnings={len(warnings)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
