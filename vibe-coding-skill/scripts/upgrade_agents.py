#!/usr/bin/env python3
from __future__ import annotations
"""Upgrade project's AGENTS.md from template, preserving user content."""

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(SKILL_DIR, "templates", "agents-phase-gates.md")


def _parse_sections(text: str) -> dict[str, str]:
    """Parse markdown into sections keyed by heading."""
    sections: dict[str, str] = {}
    current_heading = "__header__"
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        heading_match = re.match(r"^(#{2,3})\s+(.+)$", line)
        if heading_match:
            # Save previous section
            if current_lines:
                sections[current_heading] = "".join(current_lines).rstrip("\n")
            current_heading = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        sections[current_heading] = "".join(current_lines).rstrip("\n")

    return sections


def _is_placeholder_content(text: str) -> bool:
    """Return True if section content is still mostly template placeholders."""
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return True
    placeholder_count = sum(
        1 for l in lines
        if re.search(r"\{\{[^}]+\}\}|（请|待确认|待填写|TODO|FIXME", l)
    )
    return placeholder_count > len(lines) * 0.5


def merge_agents(existing_text: str, template_text: str) -> tuple[str, list[str]]:
    """Merge existing AGENTS.md with template, preserving user content.

    Strategy:
    - Section exists in both -> keep existing (user may have edited it)
    - Section only in template -> append (new section from template)
    - Section only in existing -> keep (user custom section)
    - Existing section is placeholder-only -> replace with template
    """
    existing = _parse_sections(existing_text)
    template = _parse_sections(template_text)

    changes: list[str] = []
    result_sections: list[str] = []

    # Track which existing sections we've processed
    processed: set[str] = set()

    # First pass: iterate template sections in order
    for heading, tmpl_content in template.items():
        if heading == "__header__":
            if "__header__" in existing:
                result_sections.append(existing["__header__"])
                changes.append(f"保留: 文件头")
            else:
                result_sections.append(tmpl_content)
                changes.append(f"新增: 文件头")
            processed.add("__header__")
        elif heading in existing:
            # Section exists in both
            if _is_placeholder_content(existing[heading]) and not _is_placeholder_content(tmpl_content):
                # Existing is still placeholder -> replace with template
                result_sections.append(tmpl_content)
                changes.append(f"替换: {heading} (原内容仍是占位符)")
            else:
                # Keep existing user content
                result_sections.append(existing[heading])
                changes.append(f"保留: {heading}")
            processed.add(heading)
        else:
            # New section from template
            result_sections.append(tmpl_content)
            changes.append(f"新增: {heading}")

    # Second pass: find sections in existing that are not in template
    for heading, content in existing.items():
        if heading not in processed:
            result_sections.append(content)
            changes.append(f"保留自定义: {heading}")

    return "\n\n".join(result_sections), changes

def _inject_mandatory_section(existing_text: str, template_text: str) -> tuple[str, list[str]]:
    """Inject AGENT-MANDATORY section if missing from existing AGENTS.md.

    Extracts the Session Recovery section (marked by AGENT-MANDATORY comment)
    from templates/agents.md and prepends it to the existing AGENTS.md if not present.
    Returns (modified_text, changes).
    """
    changes = []

    if "<!-- AGENT-MANDATORY" in existing_text:
        return existing_text, changes

    # Read the section from templates/agents.md (not agents-phase-gates.md)
    import os
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agents_md_path = os.path.join(skill_dir, "templates", "agents.md")

    try:
        with open(agents_md_path, encoding="utf-8") as f:
            agents_md_text = f.read()
    except OSError:
        changes.append("无法读取 templates/agents.md")
        return existing_text, changes

    marker_idx = agents_md_text.find("<!-- AGENT-MANDATORY")
    if marker_idx == -1:
        changes.append("模板中未找到 AGENT-MANDATORY 标记")
        return existing_text, changes

    section_lines = []
    for i, line in enumerate(agents_md_text[marker_idx:].splitlines()):
        if i == 0:
            section_lines.append(line)
            continue
        if line.startswith("##") and "Session" not in line:
            break
        if line.startswith("###"):
            break
        section_lines.append(line)

    if not section_lines:
        changes.append("模板中未找到 Session 恢复节")
        return existing_text, changes

    mandatory_block = "\n".join(section_lines).rstrip() + "\n\n"

    existing_lines = existing_text.splitlines(keepends=True)
    result = existing_lines[0] + "\n" + mandatory_block + "".join(existing_lines[1:])

    changes.append("新增: AGENT-MANDATORY Session 恢复节 (老项目 retrofit)")
    return result, changes





def upgrade_agents(project_root: str, dry_run: bool = False) -> int:
    """Upgrade AGENTS.md from template. Returns exit code."""
    agents_path = os.path.join(project_root, "AGENTS.md")

    if not os.path.exists(agents_path):
        print(f"❌ AGENTS.md 不存在: {agents_path}")
        print("   先运行 `vibe init` 初始化项目")
        return 1

    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ 模板不存在: {TEMPLATE_PATH}")
        return 1

    with open(agents_path, encoding="utf-8") as f:
        existing = f.read()

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    merged, changes = merge_agents(existing, template)

    # Retrofit: inject AGENT-MANDATORY Session Recovery section if missing (2026-07-14)
    merged, mandatory_changes = _inject_mandatory_section(merged, template)
    changes += mandatory_changes

    if merged.strip() == existing.strip():
        print("✅ AGENTS.md 已是最新，无需更新")
        return 0

    print(f"📝 AGENTS.md 升级预览 ({len(changes)} 项变更):")
    for change in changes:
        prefix = change.split(":")[0]
        if "新增" in prefix:
            icon = "➕"
        elif "替换" in prefix:
            icon = "🔄"
        elif "自定义" in prefix:
            icon = "📌"
        else:
            icon = "✅"
        print(f"   {icon} {change}")

    if dry_run:
        print("\n(dry-run 模式，未写入)")
        return 0

    # Write merged content
    with open(agents_path, "w", encoding="utf-8") as f:
        f.write(merged)

    print(f"\n✅ AGENTS.md 已更新: {agents_path}")
    print("   请检查内容，特别是新增和替换的部分")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Upgrade AGENTS.md from template")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = p.parse_args()
    raise SystemExit(upgrade_agents(args.project_root, dry_run=args.dry_run))
