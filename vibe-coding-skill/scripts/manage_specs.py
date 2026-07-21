#!/usr/bin/env python3
from __future__ import annotations
"""Manage multiple specs: list, detect conflicts, suggest priority."""

import argparse
import os
import re
from collections import defaultdict


def manage_specs(project_root: str, show_conflicts: bool = False, show_priority: bool = False) -> None:
    specs_dir = os.path.join(project_root, ".agents", "specs")
    if not os.path.exists(specs_dir):
        print("📭 暂无功能规格。")
        return

    spec_files = sorted([
        f for f in os.listdir(specs_dir)
        if f.endswith(".md") and f != ".gitkeep" and not f.endswith("-amendments.md")
    ])

    if not spec_files:
        print("📭 暂无功能规格。")
        return

    specs = []
    for sf in spec_files:
        path = os.path.join(specs_dir, sf)
        with open(path) as f:
            content = f.read()
        name = sf.replace(".md", "")
        status = _extract_status(content)
        new_files = _extract_list(content, "新增文件")
        mod_files = _extract_list(content, "修改文件")
        dont_touch = _extract_list(content, "不动文件")
        specs.append({
            "name": name,
            "status": status,
            "new_files": new_files,
            "mod_files": mod_files,
            "dont_touch": dont_touch,
            "path": path,
        })

    # Default: list all
    if not show_conflicts and not show_priority:
        _list_specs(specs)
        return

    # Conflict detection
    if show_conflicts:
        _detect_conflicts(specs)
        return

    # Priority suggestion
    if show_priority:
        _suggest_priority(specs)
        return


def _list_specs(specs: list) -> None:
    print(f"\n📂 功能规格 ({len(specs)}):\n")
    status_icons = {
        "draft": "📝", "spec-ready": "✅", "in-progress": "🔨",
        "review": "👀", "done": "🎉", "blocked": "🚫"
    }
    for s in specs:
        icon = status_icons.get(s["status"], "❓")
        new_str = ", ".join(s["new_files"]) if s["new_files"] else "无新增"
        mod_str = ", ".join(s["mod_files"]) if s["mod_files"] else "无修改"
        no_touch = ", ".join(s["dont_touch"]) if s["dont_touch"] else "无"
        print(f"  {icon} {s['name']}")
        print(f"      状态: {s['status']}")
        print(f"      新增: {new_str}")
        print(f"      修改: {mod_str}")
        print(f"      不动: {no_touch}")
        print()
    print(f"💡 使用 --conflicts 检测文件冲突，--priority 查看优先级建议。")


def _detect_conflicts(specs: list) -> None:
    print("\n🔍 文件冲突检测:\n")

    # Map file -> list of specs that touch it
    file_specs: dict[str, list[str]] = defaultdict(list)

    for s in specs:
        for f in s["new_files"]:
            if f and "(计划" not in f and "(描述" not in f:
                file_specs[f].append(s["name"])
        for f in s["mod_files"]:
            if f and "(计划" not in f and "(描述" not in f:
                file_specs[f].append(s["name"])

    conflicts_found = False
    for file_path, spec_names in sorted(file_specs.items()):
        if len(spec_names) > 1:
            conflicts_found = True
            print(f"  ⚠️  {file_path}")
            print(f"      被以下 spec 同时修改: {', '.join(spec_names)}")
            print()

    if not conflicts_found:
        print("  ✅ 未检测到文件冲突。所有 spec 的修改范围不重叠。")

    # Also check dont_touch violations
    dont_touch_map: dict[str, list[str]] = defaultdict(list)
    for s in specs:
        for f in s["dont_touch"]:
            if f and "(绝对" not in f and "(描述" not in f:
                dont_touch_map[f].append(s["name"])

    for s in specs:
        for f in s["new_files"] + s["mod_files"]:
            if f in dont_touch_map and s["name"] not in dont_touch_map[f]:
                conflicts_found = True
                print(f"  🚫 {f} 被 {s['name']} 计划修改，但被 {', '.join(dont_touch_map[f])} 标记为不动！")

    print()


def _suggest_priority(specs: list) -> None:
    print("\n📊 优先级建议 (基于依赖关系和影响范围):\n")

    # Simple heuristic: specs that other specs depend on go first
    # Also: "dont_touch" specs that produce files others need

    all_mod_files: dict[str, list[str]] = defaultdict(list)
    all_new_files: dict[str, list[str]] = defaultdict(list)

    for s in specs:
        for f in s["new_files"]:
            if f and "(计划" not in f and "(描述" not in f:
                all_new_files[f].append(s["name"])
        for f in s["mod_files"]:
            if f and "(计划" not in f and "(描述" not in f:
                all_mod_files[f].append(s["name"])

    # Score: mod-only (infra work) > new features > isolated
    scores = {}
    for s in specs:
        score = 0
        # Prefer specs that only modify (no new files) — likely refactors/infra
        if not s["new_files"] or all("(计划" in f for f in s["new_files"]):
            score += 2
        # Prefer specs that produce files others depend on
        for f in s["new_files"]:
            if f in all_mod_files:
                score += 1
        scores[s["name"]] = score

    ranked = sorted(specs, key=lambda s: (-scores[s["name"]], s["name"]))

    for i, s in enumerate(ranked, 1):
        icon = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"  {i}."
        print(f"  {icon} {s['name']} (状态: {s['status']})")
        if scores[s["name"]] > 0:
            reasons = []
            if scores[s["name"]] >= 2:
                reasons.append("基础设施/重构优先")
            if scores[s["name"]] % 2 == 1:
                reasons.append("其他 spec 依赖其产出")
            print(f"      理由: {', '.join(reasons)}")
        print()

    print(f"💡 原则: 基础设施先行，被依赖的 spec 先行。")


def _extract_status(content: str) -> str:
    m = re.search(r">\s*状态:\s*(\S+)", content)
    return m.group(1) if m else "draft"


def _extract_list(content: str, field: str) -> list[str]:
    """Extract file paths from a spec field like '新增文件'."""
    pattern = rf"- \*\*{field}\*\*: (.+)"
    m = re.search(pattern, content)
    if not m:
        return []
    raw = m.group(1).strip()
    if "(计划" in raw or "(描述" in raw or raw == "":
        return []
    # Split by comma or space
    items = [x.strip() for x in re.split(r"[;,，、]", raw) if x.strip()]
    return items


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Manage multiple feature specs")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--conflicts", action="store_true", help="Detect file conflicts between specs")
    p.add_argument("--priority", action="store_true", help="Suggest priority ordering")
    args = p.parse_args()
    manage_specs(os.path.abspath(args.project_root), args.conflicts, args.priority)
