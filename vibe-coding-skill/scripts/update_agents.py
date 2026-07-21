#!/usr/bin/env python3
from __future__ import annotations
"""Update project's AGENTS.md with the latest phase-gates template from Skill.

Supports project-level overrides via the `## 阶段覆盖声明` section in AGENTS.md.

Usage:
    vibe update-agents [--force]

The command:
1. Reads the latest agents-phase-gates.md template from Skill
2. Extracts the "阶段强制规范" section from the template
3. Reads project's "阶段覆盖声明" section (if any)
4. Merges: Skill template + project overrides = final AGENTS.md
5. Records the Skill version used for the update

Merge rules:
- Project override takes precedence over Skill default
- If no override, use Skill default
- If conflict, project wins but warns
"""

import argparse
import os
import re
from datetime import datetime, timezone

from common import atomic_write, backup_file

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")

# Marker for the phase-gates section in AGENTS.md
PHASE_GATES_START_MARKER = "## 阶段强制规范（Phase Gates）"
OVERRIDE_SECTION_MARKER = "## 阶段覆盖声明（Phase Gates Override）"
PHASE_GATES_END_MARKER = "## 技术栈"

# Template file name
PHASE_GATES_TEMPLATE = "agents-phase-gates.md"

# Version marker file
VERSION_MARKER = "<!-- vibe:phase-gates-version:"


def _read_template() -> str:
    """Read the latest phase-gates template from Skill."""
    path = os.path.join(TEMPLATE_DIR, PHASE_GATES_TEMPLATE)
    if not os.path.exists(path):
        path = os.path.join(TEMPLATE_DIR, "agents.md")
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到模板文件: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_phase_gates_section(template_content: str) -> str:
    """Extract the phase-gates section from the template."""
    start_idx = template_content.find(PHASE_GATES_START_MARKER)
    if start_idx == -1:
        raise ValueError(f"模板中找不到 '{PHASE_GATES_START_MARKER}' 标记")
    
    after_start = template_content[start_idx + len(PHASE_GATES_START_MARKER):]
    end_match = re.search(r"\n## ", after_start)
    if end_match:
        section = template_content[start_idx:start_idx + len(PHASE_GATES_START_MARKER) + end_match.start()]
    else:
        section = template_content[start_idx:]
    
    return section.strip()


def _extract_project_overrides(agents_content: str) -> str | None:
    """Extract the phase-gates override section from project's AGENTS.md."""
    start_idx = agents_content.find(OVERRIDE_SECTION_MARKER)
    if start_idx == -1:
        return None
    
    after_start = agents_content[start_idx + len(OVERRIDE_SECTION_MARKER):]
    end_match = re.search(r"\n## ", after_start)
    if end_match:
        section = agents_content[start_idx:start_idx + len(OVERRIDE_SECTION_MARKER) + end_match.start()]
    else:
        section = agents_content[start_idx:]
    
    return section.strip()


def _merge_phase_gates(skill_section: str, project_overrides: str | None) -> str:
    """Merge Skill phase-gates with project overrides."""
    if not project_overrides:
        return skill_section
    
    merged = skill_section + "\n\n"
    merged += "---\n\n"
    merged += "> **阶段覆盖声明**: 本项目对标准阶段强制规范有覆盖。"
    merged += "标准规则仍然适用，除非满足覆盖条件。\n\n"
    merged += project_overrides + "\n"
    
    return merged


def _get_skill_version() -> str:
    """Read the current Skill version."""
    version_path = os.path.join(SKILL_DIR, "VERSION")
    if os.path.exists(version_path):
        try:
            with open(version_path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return "unknown"


def _extract_existing_version(agents_content: str) -> str | None:
    """Extract the phase-gates version from existing AGENTS.md."""
    match = re.search(rf"{re.escape(VERSION_MARKER)}([^\n]+)", agents_content)
    if match:
        return match.group(1).strip()
    return None


def update_agents(project_root: str, force: bool = False) -> dict:
    """Update the phase-gates section in project's AGENTS.md.
    
    Returns:
        dict with keys: success (bool), message (str), version (str), updated (bool)
    """
    agents_path = os.path.join(project_root, "AGENTS.md")
    
    if not os.path.exists(agents_path):
        return {
            "success": False,
            "message": "AGENTS.md 不存在，请先运行 `vibe init` 初始化项目",
            "version": "",
            "updated": False,
        }
    
    with open(agents_path, encoding="utf-8") as f:
        existing_content = f.read()
    
    try:
        template_content = _read_template()
    except (FileNotFoundError, ValueError) as e:
        return {
            "success": False,
            "message": f"读取模板失败: {e}",
            "version": "",
            "updated": False,
        }
    
    try:
        phase_gates_section = _extract_phase_gates_section(template_content)
    except ValueError as e:
        return {
            "success": False,
            "message": f"解析模板失败: {e}",
            "version": "",
            "updated": False,
        }
    
    project_overrides = _extract_project_overrides(existing_content)
    merged_section = _merge_phase_gates(phase_gates_section, project_overrides)
    
    skill_version = _get_skill_version()
    existing_version = _extract_existing_version(existing_content)
    
    if not force and existing_version == skill_version and not project_overrides:
        return {
            "success": True,
            "message": f"AGENTS.md 阶段强制规范已是最新 (版本: {skill_version})，无需更新",
            "version": skill_version,
            "updated": False,
        }
    
    version_line = f"{VERSION_MARKER}{skill_version} -->"
    section_with_version = f"{merged_section}\n\n{version_line}\n"
    
    start_idx = existing_content.find(PHASE_GATES_START_MARKER)
    
    if start_idx != -1:
        after_start = existing_content[start_idx + len(PHASE_GATES_START_MARKER):]
        end_match = re.search(r"\n## ", after_start)
        
        if end_match:
            end_pos = start_idx + len(PHASE_GATES_START_MARKER) + end_match.start()
            new_content = existing_content[:start_idx] + section_with_version + "\n\n" + existing_content[end_pos:]
        else:
            new_content = existing_content[:start_idx] + section_with_version
    else:
        tech_stack_idx = existing_content.find("## 技术栈")
        if tech_stack_idx != -1:
            new_content = existing_content[:tech_stack_idx] + section_with_version + "\n\n" + existing_content[tech_stack_idx:]
        else:
            new_content = existing_content + "\n\n" + section_with_version
    
    agents_dir = os.path.join(project_root, ".agents")
    backup_file(agents_path, os.path.join(agents_dir, "backups", "agents-update"))
    atomic_write(agents_path, new_content)
    
    action = "更新" if start_idx != -1 else "新增"
    override_note = "（含项目覆盖声明）" if project_overrides else ""
    return {
        "success": True,
        "message": f"AGENTS.md 阶段强制规范已{action}{override_note} (Skill 版本: {skill_version})",
        "version": skill_version,
        "updated": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Update project's AGENTS.md with latest phase-gates template")
    p.add_argument("--project-root", default=".", help="Project root path")
    p.add_argument("--force", action="store_true", help="Force update even if version matches")
    args = p.parse_args()
    
    result = update_agents(os.path.abspath(args.project_root), args.force)
    print(result["message"])
    if not result["success"]:
        raise SystemExit(1)
