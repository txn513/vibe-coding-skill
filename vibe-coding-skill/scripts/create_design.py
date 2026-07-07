#!/usr/bin/env python3
"""Create / iterate / rollback an architecture or design document.

Implements Rule 42 (UI design iteration must be versioned, not overwritten):

- First-time creation: writes `<name>.md` (current pointer) and a
  matching `<name>.versions/v1.md` (history). The main file is the
  rendered view of the latest version.
- Iteration: writes a new `<name>.versions/v<N+1>.md`, archives the
  previous `<name>.md` content into `<name>.versions/v<N>.md` (if it
  is not already there), and refreshes `<name>.md` so its
  `当前版本` / `历史版本` pointer reflects the latest version.
- Rollback: copies `<name>.versions/v<N>.md` over `<name>.md` and
  updates the pointer.
- Legacy migration: if `<name>.md` already exists in the old flat
  layout (no `当前版本:` line), treat the existing file as v1 and
  move it into `<name>.versions/v1.md` before laying down the new
  pointer file.

The CLI exposes three subcommands: `create` (default), `iteration`,
`rollback`. The legacy positional form `create_design.py <root> <name>`
remains an alias for `create`.

The main entry point `create_design(...)` keeps the historical
signature (`project_root, name -> str`) so existing tests and call
sites continue to work — it returns the path to the main pointer
file (`<name>.md`).
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


# Frontmatter line that tags a file as the current pointer; legacy
# files lack this and must be migrated. The match is anchored to a
# `>` line and finds `当前版本: vN |` anywhere inside that line, so
# it works whether the version field is the first or fourth token of
# the frontmatter summary.
_VERSION_POINTER_RE = re.compile(r"^>.*?当前版本:\s*v(\d+)\s*\|", re.MULTILINE)
_LEGACY_FRONT_RE = re.compile(r"^>\s*状态:\s*\S+.*$")


def _designs_dir(project_root: str) -> str:
    return os.path.join(project_root, ".agents", "designs")


def _main_path(project_root: str, name: str) -> str:
    return os.path.join(_designs_dir(project_root), f"{name}.md")


def _versions_dir(project_root: str, name: str) -> str:
    return os.path.join(_designs_dir(project_root), f"{name}.versions")


def _version_path(project_root: str, name: str, version: int) -> str:
    return os.path.join(_versions_dir(project_root, name), f"v{version}.md")


def _read_pointer_version(main_file: str) -> int:
    """Return the version declared in the pointer file, or 0 if missing."""
    if not os.path.exists(main_file):
        return 0
    with open(main_file, encoding="utf-8") as f:
        for line in f:
            m = _VERSION_POINTER_RE.match(line)
            if m:
                return int(m.group(1))
    return 0


def _migrate_legacy(project_root: str, name: str) -> int:
    """If the project has an old flat `<name>.md`, move it into
    `<name>.versions/v1.md` so the new layout can take over.

    Returns 1 if migration happened, 0 if there was nothing to do.
    """
    main_file = _main_path(project_root, name)
    if not os.path.exists(main_file):
        return 0
    if _read_pointer_version(main_file) > 0:
        return 0  # already in new layout
    versions_dir = _versions_dir(project_root, name)
    os.makedirs(versions_dir, exist_ok=True)
    legacy_version = _version_path(project_root, name, 1)
    shutil.move(main_file, legacy_version)
    print(f"📦 旧布局已迁移到: {legacy_version}")
    return 1


def _render_template(fields: dict) -> str:
    tmpl_path = os.path.join(TEMPLATE_DIR, "design.md")
    if not os.path.exists(tmpl_path):
        raise FileNotFoundError(f"模板不存在: {tmpl_path}")
    with open(tmpl_path, encoding="utf-8") as f:
        template = f.read()
    for k, v in fields.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def _build_fields(
    name: str,
    status: str,
    linked_spec: str,
    now: str,
    version_history_text: str = "(无历史版本；这是首次创建)",
) -> dict:
    return {
        "DESIGN_NAME": name, "STATUS": status,
        "CREATED_AT": now, "LINKED_SPEC": linked_spec,
        "VERSION_HISTORY": version_history_text,
        "PROBLEM_STATEMENT": "(用一段话描述要解决什么问题)",
        "CURRENT_CONTEXT": "(描述与本次设计有关的现状)",
        "IN_SCOPE_BOUNDARY": "(描述本次方案负责什么)",
        "OUT_OF_SCOPE_BOUNDARY": "(描述本次方案不负责什么)",
        "SOLUTION_OVERVIEW": "(用一段话描述方案及其工作方式)",
        "PART_1": "(组成部分)", "PART_1_RESPONSIBILITY": "(职责)",
        "PART_1_INPUT": "(输入)", "PART_1_OUTPUT": "(输出)",
        "PART_2": "(组成部分)", "PART_2_RESPONSIBILITY": "(职责)",
        "PART_2_INPUT": "(输入)", "PART_2_OUTPUT": "(输出)",
        "INTERACTION_FLOW": "(描述组成部分之间的交互或状态流转)",
        "STABLE_CONTRACTS": "(列出不得改变的契约)",
        "CHANGED_CONTRACTS": "(列出新增或改变的契约)",
        "COMPATIBILITY_REQUIREMENTS": "(说明兼容与迁移要求)",
        "DECISION_1_TITLE": "(决策标题)", "DECISION_1_OPTIONS": "(选项 A / 选项 B)",
        "DECISION_1_CHOICE": "(选择的方案)", "DECISION_1_RATIONALE": "(选择理由)",
        "DECISION_2_TITLE": "(决策标题)", "DECISION_2_OPTIONS": "(选项 A / 选项 B)",
        "DECISION_2_CHOICE": "(选择的方案)", "DECISION_2_RATIONALE": "(选择理由)",
        "VALIDATION_STRATEGY": "(描述如何验证设计目标)",
        "REQUIRED_EVIDENCE": "(描述完成时需要保留什么证据)",
        "RISK_1": "(风险描述)", "RISK_1_IMPACT": "(影响程度)", "RISK_1_MITIGATION": "(缓解措施)",
        "RISK_2": "(风险描述)", "RISK_2_IMPACT": "(影响程度)", "RISK_2_MITIGATION": "(缓解措施)",
        "OPEN_QUESTION_1": "(待澄清的问题)",
        "OPEN_QUESTION_2": "(待澄清的问题)",
    }


def _version_history_text(history_versions: list, current: int) -> str:
    """Render the human-readable version history block."""
    if not history_versions:
        return "(无历史版本；这是首次创建)"
    bullets = [f"- 当前: **v{current}** (active)"]
    for v in history_versions:
        bullets.append(f"- v{v} (archived)")
    return "\n".join(bullets)


def _pointer_frontmatter(version: int, history: list, linked_spec: str) -> str:
    history_str = ",".join(f"v{v}" for v in history) if history else "无"
    return (
        f"> 状态: draft | 当前版本: v{version} | 历史版本: {history_str} | "
        f"关联规格: {linked_spec}\n\n"
        f"<!-- vibe:design_version_pointer: current=v{version} "
        f"history={history_str} -->\n\n"
        f"## 版本历史\n\n"
        f"{_version_history_text(history, version)}\n"
    )


def create_design(project_root: str, name: str) -> str:
    """Create a new design document (Rule 42 first version).

    Returns the path to the main pointer file.
    """
    name = validate_artifact_name(name, "设计名称")
    os.makedirs(_designs_dir(project_root), exist_ok=True)

    main_file = _main_path(project_root, name)

    # If the design already exists, treat this call as an iteration
    # request (the user / agent probably forgot they were on v2
    # already). Rule 42 forbids silent overwrites.
    if os.path.exists(main_file) or any(
        os.path.exists(_version_path(project_root, name, v))
        for v in range(1, 32)
    ):
        current = _current_version(project_root, name)
        print(f"⚠️  设计文档已存在: {name} (当前版本 v{current})")
        print(f"   要迭代新版本请用: vibe design iteration {name}")
        return main_file

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = _build_fields(name, "draft", "(关联的 spec 名称)", now)
    rendered = _render_template(fields)

    versions_dir = _versions_dir(project_root, name)
    os.makedirs(versions_dir, exist_ok=True)

    # v1 lives both as the history record and as the rendered main file.
    atomic_write(_version_path(project_root, name, 1), rendered)
    atomic_write(main_file, rendered)

    print(f"✅ 设计文档已创建: {main_file}")
    print(f"📦 历史版本目录: {versions_dir}")
    print(f"📐 当前版本: v1 (frontmatter `当前版本: v1 | 历史版本: 无`)")
    print(f"📐 填写边界、职责、契约、关键决策和验证策略后再创建 spec。")
    return main_file


def _current_version(project_root: str, name: str) -> int:
    """Return the highest version present, or 0 if none."""
    versions_dir = _versions_dir(project_root, name)
    if not os.path.isdir(versions_dir):
        return 0
    highest = 0
    for entry in os.listdir(versions_dir):
        m = re.match(r"^v(\d+)\.md$", entry)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest


def design_iteration(project_root: str, name: str) -> str:
    """Create v{N+1} of an existing design, archiving the prior version.

    Returns the path to the new version file.
    """
    name = validate_artifact_name(name, "设计名称")
    os.makedirs(_designs_dir(project_root), exist_ok=True)

    # Handle legacy migration before checking current version.
    _migrate_legacy(project_root, name)

    current = _current_version(project_root, name)
    if current == 0:
        # No design exists yet — fall back to fresh creation.
        print(f"❌ 设计 {name} 不存在，请先创建再迭代。")
        sys.exit(2)

    next_version = current + 1
    versions_dir = _versions_dir(project_root, name)
    os.makedirs(versions_dir, exist_ok=True)
    main_file = _main_path(project_root, name)
    new_version_file = _version_path(project_root, name, next_version)

    # If the main pointer file holds content that is not yet archived
    # (e.g. it was migrated from legacy and never recorded under
    # versions/vN), archive it as v{current} first.
    existing_version_file = _version_path(project_root, name, current)
    if os.path.exists(main_file) and not os.path.exists(existing_version_file):
        shutil.copy2(main_file, existing_version_file)
        print(f"📦 已将当前主文件归档为 v{current}: {existing_version_file}")

    history = list(range(1, next_version))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = _build_fields(name, "draft", "(关联的 spec 名称)", now)
    # For iterations, render fresh template content; the agent will
    # fill in the v{N+1} delta. The pointer file shows history.
    rendered = _render_template(fields)
    atomic_write(new_version_file, rendered)

    # Refresh main pointer file with the new version metadata.
    pointer = (
        f"# {name} — 设计说明\n\n"
        + _pointer_frontmatter(next_version, history, "(关联的 spec 名称)")
        + "\n"
        + "\n".join(rendered.splitlines()[1:])  # strip duplicate H1
    )
    atomic_write(main_file, pointer)

    print(f"✅ 设计文档已迭代到 v{next_version}: {name}")
    print(f"📦 新版本: {new_version_file}")
    print(f"📌 历史版本目录: {versions_dir} (v1 .. v{current})")
    print(f"📐 请编辑 v{next_version} 内容后再 commit (Rule 42 + Rule 53)。")
    return new_version_file


def design_rollback(project_root: str, name: str, target_version: int) -> str:
    """Restore a previous version of a design as the current pointer.

    The target version file is copied over the main pointer file and
    the pointer's `当前版本` field is rewritten to reflect the
    rollback. History records are NOT modified.
    """
    name = validate_artifact_name(name, "设计名称")
    _migrate_legacy(project_root, name)

    if target_version < 1:
        print(f"❌ 版本号必须 ≥ 1，得到 {target_version}")
        sys.exit(2)

    target = _version_path(project_root, name, target_version)
    if not os.path.exists(target):
        print(f"❌ 版本不存在: {target}")
        sys.exit(2)

    main_file = _main_path(project_root, name)
    shutil.copy2(target, main_file)

    current = _current_version(project_root, name)
    history = [v for v in range(1, current + 1) if v != target_version]
    history_str = ",".join(f"v{v}" for v in history) if history else "无"

    # Rewrite only the frontmatter lines; keep the body intact.
    with open(main_file, encoding="utf-8") as f:
        body = f.read()
    body = re.sub(
        r"^>\s*状态:.*?\| 当前版本:.*?\| 历史版本:.*?\| 关联规格:.*?$",
        f"> 状态: draft | 当前版本: v{target_version} | 历史版本: {history_str} | "
        f"关联规格: (关联的 spec 名称)",
        body,
        count=1,
        flags=re.MULTILINE,
    )
    body = re.sub(
        r"<!-- vibe:design_version_pointer: current=v\d+ history=[^>]+ -->",
        f"<!-- vibe:design_version_pointer: current=v{target_version} "
        f"history={history_str} -->",
        body,
        count=1,
    )
    atomic_write(main_file, body)

    print(f"✅ 已回滚 {name} 到 v{target_version}: {main_file}")
    print(f"📦 历史版本仍保留在 {os.path.dirname(target)}/")
    return main_file


def _parse_args(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create / iterate / rollback a design document (Rule 42)")
    p.add_argument("project_root", help="Project root directory")
    sub = p.add_subparsers(dest="cmd")

    create = sub.add_parser("create", help="Create a new design (default)")
    create.add_argument("name", help="Design document name")

    iteration = sub.add_parser("iteration", help="Iterate to a new version (Rule 42)")
    iteration.add_argument("name", help="Design document name")

    rollback = sub.add_parser("rollback", help="Rollback to an earlier version")
    rollback.add_argument("name", help="Design document name")
    rollback.add_argument("version", type=int, help="Target version (e.g. 1)")

    return p.parse_args(argv)


def main(argv: list) -> int:
    args = _parse_args(argv)
    root = os.path.abspath(args.project_root)
    cmd = args.cmd or "create"
    if cmd == "create":
        create_design(root, args.name)
    elif cmd == "iteration":
        design_iteration(root, args.name)
    elif cmd == "rollback":
        design_rollback(root, args.name, args.version)
    return 0


if __name__ == "__main__":
    # Support legacy positional form: create_design.py <root> <name>
    if len(sys.argv) == 3 and not sys.argv[1].startswith("-"):
        root = os.path.abspath(sys.argv[1])
        create_design(root, sys.argv[2])
    else:
        sys.exit(main(sys.argv[1:]))
