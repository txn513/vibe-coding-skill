#!/usr/bin/env python3
"""Update project's AGENTS.md with the latest phase-gates template from Skill.

This command allows existing projects to receive updates to the phase-gates
section without losing their project-specific content (tech stack, architecture
constraints, etc.).

Usage:
    vibe update-agents [--force]

The command:
1. Reads the latest agents-phase-gates.md template from Skill
2. Extracts the "阶段强制规范" section from the template
3. Replaces or appends this section in the project's AGENTS.md
4. Records the Skill version used for the update

If AGENTS.md doesn't exist, suggests running init_project.py first.
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
PHASE_GATES_END_MARKER = "## 技术栈"

# Template file name
PHASE_GATES_TEMPLATE = "agents-phase-gates.md"

# Version marker file
VERSION_MARKER = "<!-- vibe:phase-gates-version:"


def _read_template() -> str:
    """Read the latest phase-gates template from Skill."""
    path = os.path.join(TEMPLATE_DIR, PHASE_GATES_TEMPLATE)
    if not os.path.exists(path):
        # Fallback: try the old template
        path = os.path.join(TEMPLATE_DIR, "agents.md")
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到模板文件: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_phase_gates_section(template_content: str) -> str:
    """Extract the phase-gates section from the template."""
    # Find the section between PHASE_GATES_START_MARKER and PHASE_GATES_END_MARKER
    start_idx = template_content.find(PHASE_GATES_START_MARKER)
    if start_idx == -1:
        raise ValueError(f"模板中找不到 '{PHASE_GATES_START_MARKER}' 标记")
    
    # Find the end marker - look for the next ## 标题 after the start marker
    after_start = template_content[start_idx + len(PHASE_GATES_START_MARKER):]
    # Find the next ## heading
    end_match = re.search(r"\n## ", after_start)
    if end_match:
        # Include everything up to but not including the next ## heading
        section = template_content[start_idx:start_idx + len(PHASE_GATES_START_MARKER) + end_match.start()]
    else:
        # No next heading, take everything to the end
        section = template_content[start_idx:]
    
    return section.strip()


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
    
    # Read existing AGENTS.md
    with open(agents_path, encoding="utf-8") as f:
        existing_content = f.read()
    
    # Read latest template
    try:
        template_content = _read_template()
    except (FileNotFoundError, ValueError) as e:
        return {
            "success": False,
            "message": f"读取模板失败: {e}",
            "version": "",
            "updated": False,
        }
    
    # Extract phase-gates section from template
    try:
        phase_gates_section = _extract_phase_gates_section(template_content)
    except ValueError as e:
        return {
            "success": False,
            "message": f"解析模板失败: {e}",
            "version": "",
            "updated": False,
        }
    
    # Get versions
    skill_version = _get_skill_version()
    existing_version = _extract_existing_version(existing_content)
    
    # Check if update is needed
    if not force and existing_version == skill_version:
        return {
            "success": True,
            "message": f"AGENTS.md 阶段强制规范已是最新 (版本: {skill_version})，无需更新",
            "version": skill_version,
            "updated": False,
        }
    
    # Add version marker to the section
    version_line = f"{VERSION_MARKER}{skill_version} -->"
    phase_gates_section_with_version = f"{phase_gates_section}\n\n{version_line}\n"
    
    # Replace or append the phase-gates section in AGENTS.md
    # Find if the section already exists
    start_idx = existing_content.find(PHASE_GATES_START_MARKER)
    
    if start_idx != -1:
        # Section exists, replace it
        # Find where the section ends (next ## heading or end of file)
        after_start = existing_content[start_idx + len(PHASE_GATES_START_MARKER):]
        end_match = re.search(r"\n## ", after_start)
        
        if end_match:
            end_pos = start_idx + len(PHASE_GATES_START_MARKER) + end_match.start()
            new_content = existing_content[:start_idx] + phase_gates_section_with_version + "\n\n" + existing_content[end_pos:]
        else:
            # Section is at the end, replace everything from start
            new_content = existing_content[:start_idx] + phase_gates_section_with_version
    else:
        # Section doesn't exist, append before "## 技术栈" or at the end
        tech_stack_idx = existing_content.find("## 技术栈")
        if tech_stack_idx != -1:
            new_content = existing_content[:tech_stack_idx] + phase_gates_section_with_version + "\n\n" + existing_content[tech_stack_idx:]
        else:
            # Append at the end
            new_content = existing_content + "\n\n" + phase_gates_section_with_version
    
    # Backup existing file
    agents_dir = os.path.join(project_root, ".agents")
    backup_file(agents_path, os.path.join(agents_dir, "backups", "agents-update"))
    
    # Write updated content
    atomic_write(agents_path, new_content)
    
    action = "更新" if start_idx != -1 else "新增"
    return {
        "success": True,
        "message": f"AGENTS.md 阶段强制规范已{action} (Skill 版本: {skill_version})",
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
