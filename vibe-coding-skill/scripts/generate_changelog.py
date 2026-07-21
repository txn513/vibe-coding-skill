#!/usr/bin/env python3
from __future__ import annotations
"""Generate a changelog from completed specs and plans.

Usage:
    python3 generate_changelog.py <project_root> [--version v1.2.0]
"""

import argparse
import os
import re
from datetime import datetime, timezone

from common import atomic_write, backup_file, validate_artifact_name

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def generate_changelog(
    project_root: str,
    version: str = "",
    force: bool = False,
    release_group: str = "",
) -> str:
    project_root = os.path.abspath(project_root)
    specs_dir = os.path.join(project_root, ".agents", "specs")
    plans_dir = os.path.join(project_root, ".agents", "plans")
    version = validate_artifact_name(version or "unreleased", "版本名称")
    prior_specs = _released_spec_names(
        os.path.join(project_root, ".agents", "changelogs"),
        f"CHANGELOG-{version}.md",
    )

    if not os.path.exists(specs_dir):
        print("📭 暂无规格目录。")
        return ""

    spec_files = sorted([
        f for f in os.listdir(specs_dir)
        if f.endswith(".md") and f != ".gitkeep" and not f.endswith("-amendments.md")
    ])

    if not spec_files:
        print("📭 暂无功能规格。")
        return ""

    # Categorize specs by status
    new_features = []
    bug_fixes = []
    refactors = []
    in_progress = []

    for sf in spec_files:
        path = os.path.join(specs_dir, sf)
        with open(path) as f:
            content = f.read()
        name = sf.replace(".md", "")
        if name in prior_specs:
            continue
        if release_group:
            group = re.search(r"^>\s*发布组:\s*(.+)$", content, re.MULTILINE)
            if not group or group.group(1).strip() != release_group:
                continue
        status = _extract_status(content)
        intent = _extract_intent(content)
        spec_type = _detect_spec_type(content, name)

        entry = f"- **{name}**: {intent}" if intent else f"- **{name}**"

        if status in ("done", "complete", "released", "🎉"):
            if spec_type == "bug":
                bug_fixes.append(entry)
            elif spec_type == "refactor":
                refactors.append(entry)
            else:
                new_features.append(entry)
        elif status in ("in-progress", "🔨"):
            in_progress.append(entry)

    # Also check plans for phase completion
    plan_summaries = []
    if os.path.exists(plans_dir):
        for pf in sorted(os.listdir(plans_dir)):
            if pf.endswith(".md") and pf != ".gitkeep":
                with open(os.path.join(plans_dir, pf)) as f:
                    plan = f.read()
                completed = len(re.findall(r"- \[x\]", plan))
                total = len(re.findall(r"- \[.\]", plan))
                if total > 0:
                    pct = int(completed / total * 100)
                    plan_summaries.append(f"- {pf.replace('.md', '')}: {completed}/{total} tasks ({pct}%)")

    # Load template
    tmpl_path = os.path.join(TEMPLATE_DIR, "changelog.md")
    if not os.path.exists(tmpl_path):
        print(f"❌ 模板不存在: {tmpl_path}")
        return ""

    with open(tmpl_path) as f:
        template = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    import subprocess
    branch = "unknown"
    try:
        r = subprocess.run(["git", "-C", project_root, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5)
        branch = r.stdout.strip() or "unknown"
    except Exception:
        pass

    content = template
    replacements = {
        "VERSION": version,
        "RELEASE_DATE": now,
        "BRANCH": branch,
        "NEW_FEATURES": "\n".join(new_features) if new_features else "（无）",
        "BUG_FIXES": "\n".join(bug_fixes) if bug_fixes else "（无）",
        "REFACTORS": "\n".join(refactors) if refactors else "（无）",
        "BREAKING_CHANGES": "（请手动列出破坏性变更）",
        "DEPENDENCY_UPDATES": "（请手动列出依赖更新）",
        "MIGRATION_GUIDE": "（如有破坏性变更，请补充迁移步骤）",
    }
    for k, v in replacements.items():
        content = content.replace("{{" + k + "}}", v)

    # Save
    changelog_dir = os.path.join(project_root, ".agents", "changelogs")
    os.makedirs(changelog_dir, exist_ok=True)
    changelog_file = os.path.join(changelog_dir, f"CHANGELOG-{version}.md")
    if os.path.exists(changelog_file) and not force:
        print(f"⚠️  Changelog 已存在，未覆盖: {changelog_file}")
        with open(changelog_file, encoding="utf-8") as handle:
            return handle.read()
    if force:
        backup_file(
            changelog_file,
            os.path.join(project_root, ".agents", "archive", "changelogs"),
        )
    atomic_write(changelog_file, content)

    print(f"✅ Changelog 已生成: {changelog_file}")
    print()
    print(f"📊 统计:")
    print(f"   新增功能: {len(new_features)}")
    print(f"   Bug 修复: {len(bug_fixes)}")
    print(f"   重构: {len(refactors)}")
    print(f"   进行中: {len(in_progress)}")
    if plan_summaries:
        print(f"   任务完成度:")
        for ps in plan_summaries:
            print(f"     {ps}")

    return content


def _extract_status(content: str) -> str:
    m = re.search(r">\s*状态:\s*(\S+)", content)
    return m.group(1) if m else "draft"


def _extract_intent(content: str) -> str:
    """Extract first meaningful line from intent section."""
    # Try bug format first
    m = re.search(r"修复 (.+?) 的 Bug", content)
    if m:
        return f"修复 {m.group(1)}"
    # Try refactor format
    m = re.search(r"重构 (.+)", content)
    if m:
        return f"重构 {m.group(1)}"
    # Try feature format
    m = re.search(r"\*\*要解决什么问题.*?\*\*\s*\n+(.+)", content)
    if m:
        line = m.group(1).strip()
        if line and "(描述" not in line:
            return line[:80]
    return ""


def _detect_spec_type(content: str, name: str) -> str:
    """Detect whether a spec is a feature, bug, or refactor."""
    explicit = re.search(r"^>\s*类型:\s*(feature|bug|refactor)\s*$", content, re.MULTILINE)
    if explicit:
        return explicit.group(1)
    if "修复" in content and "复现步骤" in content:
        return "bug"
    if "重构" in content and "重构目标" in content:
        return "refactor"
    # Check the name
    if name.startswith("fix-") or name.startswith("bug-"):
        return "bug"
    if name.startswith("refactor-"):
        return "refactor"
    return "feature"


def _released_spec_names(changelogs_dir: str, current_filename: str) -> set[str]:
    if not os.path.exists(changelogs_dir):
        return set()
    names = set()
    for filename in os.listdir(changelogs_dir):
        if (
            not filename.endswith(".md")
            or filename == current_filename
            or filename == ".gitkeep"
        ):
            continue
        with open(os.path.join(changelogs_dir, filename), encoding="utf-8") as handle:
            names.update(re.findall(r"^-\s+\*\*([^*]+)\*\*", handle.read(), re.MULTILINE))
    return names


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate changelog from completed specs")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--version", default="", help="Version number (e.g. v1.2.0)")
    p.add_argument("--force", action="store_true", help="Replace an existing changelog after backup")
    p.add_argument("--release-group", default="", help="Only include this release group")
    args = p.parse_args()
    generate_changelog(
        os.path.abspath(args.project_root),
        args.version,
        args.force,
        args.release_group,
    )
