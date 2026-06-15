#!/usr/bin/env python3
"""Manage lifecycle states for project-local rules."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from common import RULE_STATUSES, atomic_write, project_rule_status, validate_artifact_name

TRANSITIONS = {
    "proposed": {"adopted", "deprecated"},
    "adopted": {"deprecated"},
    "deprecated": {"adopted"},
}


def set_rule_status(
    project_root: str,
    rule_name: str,
    new_status: str | None = None,
    reason: str = "",
) -> str | None:
    name = validate_artifact_name(rule_name.removesuffix(".md"), "规则名称")
    path = Path(project_root) / ".agents" / "rules" / f"{name}.md"
    if not path.exists():
        print(f"❌ 项目规则不存在: {path}")
        return None
    content = path.read_text(encoding="utf-8")
    current = project_rule_status(content)
    if new_status is None:
        print(f"{name}: {current}")
        return current
    if new_status not in RULE_STATUSES:
        raise ValueError(f"无效规则状态: {new_status}")
    if new_status == current:
        return current
    if new_status not in TRANSITIONS.get(current, set()):
        print(f"❌ 不允许的规则状态流转: {current} → {new_status}")
        return None
    if not reason.strip():
        print("❌ 规则状态变更必须记录原因")
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    metadata = re.search(r"^>.*\b状态:\s*\S+.*$", content, re.MULTILINE)
    if metadata:
        line = metadata.group(0)
        replacement = re.sub(r"\b状态:\s*\S+", f"状态: {new_status}", line)
        content = content[:metadata.start()] + replacement + content[metadata.end():]
    else:
        heading_end = content.find("\n")
        marker = f"\n\n> 状态: {new_status}"
        content = content[:heading_end] + marker + content[heading_end:]
    content = content.rstrip() + f"\n\n## 生命周期记录\n\n- {now}: {current} → {new_status} — {reason.strip()}\n"
    atomic_write(path, content)
    print(f"✅ {name}: {current} → {new_status}")
    return new_status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage project rule lifecycle")
    parser.add_argument("project_root")
    parser.add_argument("rule_name")
    parser.add_argument("status", nargs="?", choices=sorted(RULE_STATUSES))
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    set_rule_status(args.project_root, args.rule_name, args.status, args.reason)
