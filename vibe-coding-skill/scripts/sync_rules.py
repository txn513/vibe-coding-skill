#!/usr/bin/env python3
"""Compare project rules with skill templates without losing project changes."""

from __future__ import annotations

import argparse
import difflib
import os
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write, read_text

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_RULES = SCRIPT_DIR.parent / "templates" / "rules"
PROJECT_ONLY_MARKER = "自动生成自回顾分析"


def sync_rules(project_root: str, apply: bool = False, force: bool = False) -> dict:
    project_rules = Path(project_root).resolve() / ".agents" / "rules"
    if not project_rules.exists():
        raise FileNotFoundError("项目 .agents/rules/ 不存在，请先初始化或接手项目")
    if not SKILL_RULES.exists():
        raise FileNotFoundError("Skill 模板目录不存在")

    skill_files = {path.name for path in SKILL_RULES.glob("*.md")}
    project_files = {path.name for path in project_rules.glob("*.md")}
    missing = sorted(skill_files - project_files)
    project_only = sorted(project_files - skill_files)
    changed = []

    for name in sorted(skill_files & project_files):
        skill_content = read_text(SKILL_RULES / name) or ""
        project_content = read_text(project_rules / name) or ""
        if skill_content != project_content:
            changed.append((name, skill_content, project_content))

    result = {
        "missing": missing,
        "project_only": project_only,
        "changed": [name for name, _, _ in changed],
        "copied": [],
        "staged": [],
        "replaced": [],
    }

    print("规则同步: 项目 vs Skill 模板\n")

    if missing:
        print(f"Skill 新增规则 ({len(missing)}):")
        for name in missing:
            print(f"  + {name}")
            if apply:
                atomic_write(project_rules / name, read_text(SKILL_RULES / name) or "")
                result["copied"].append(name)
        print()

    if project_only:
        print(f"项目特有规则 ({len(project_only)}):")
        for name in project_only:
            content = read_text(project_rules / name) or ""
            source = "自动生成" if PROJECT_ONLY_MARKER in content else "项目维护"
            print(f"  - {name} ({source})")
        print()

    if changed:
        print(f"存在差异的共有规则 ({len(changed)}):")
        for name, skill_content, project_content in changed:
            print(f"  ~ {name}")
            if not apply:
                diff = difflib.unified_diff(
                    project_content.splitlines(),
                    skill_content.splitlines(),
                    fromfile=f"project/{name}",
                    tofile=f"skill/{name}",
                    lineterm="",
                )
                for line in list(diff)[:12]:
                    print(f"    {line}")
            elif force:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                backup = project_rules / ".backups" / timestamp / name
                atomic_write(backup, project_content)
                atomic_write(project_rules / name, skill_content)
                result["replaced"].append(name)
                print(f"    已替换；原文件备份到 {backup}")
            else:
                staged = project_rules / ".skill-updates" / name
                atomic_write(staged, skill_content)
                result["staged"].append(name)
                print(f"    未覆盖项目版本；新模板暂存到 {staged}")
        print()
    else:
        print("共有规则均为最新。\n")

    if not apply and (missing or changed):
        print("使用 --apply 复制缺失规则并暂存模板更新。")
        print("只有 --apply --force 才会覆盖项目规则，并会先备份。")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync project rules with skill templates")
    parser.add_argument("project_root", help="Project root directory")
    parser.add_argument("--apply", action="store_true", help="Copy missing rules and stage updates")
    parser.add_argument("--force", action="store_true", help="Replace changed rules after backup")
    arguments = parser.parse_args()

    if arguments.force and not arguments.apply:
        parser.error("--force requires --apply")

    try:
        sync_rules(arguments.project_root, arguments.apply, arguments.force)
    except FileNotFoundError as error:
        print(f"错误: {error}")
        raise SystemExit(1)
