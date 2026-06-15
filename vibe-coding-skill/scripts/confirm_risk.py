#!/usr/bin/env python3
"""Confirm a spec's risk after creation or requirements amendment."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write, validate_artifact_name

RISKS = {"low", "medium", "high"}


def confirm_risk(
    project_root: str,
    spec_name: str,
    risk: str,
    reason: str,
) -> str | None:
    name = validate_artifact_name(spec_name, "规格名称")
    if risk not in RISKS:
        raise ValueError(f"无效风险等级: {risk}")
    if not reason.strip():
        raise ValueError("风险确认必须记录理由")
    path = Path(project_root) / ".agents" / "specs" / f"{name}.md"
    if not path.exists():
        print(f"❌ 规格不存在: {name}")
        return None
    content = path.read_text(encoding="utf-8")
    old_match = re.search(r"^>\s*风险:\s*(\S+)", content, re.MULTILINE)
    old_risk = old_match.group(1) if old_match else "medium"
    if old_match:
        content = (
            content[:old_match.start()]
            + f"> 风险: {risk}"
            + content[old_match.end():]
        )
    else:
        status = re.search(r"^>\s*状态:.*$", content, re.MULTILINE)
        insert_at = status.end() if status else 0
        content = content[:insert_at] + f"\n> 风险: {risk}" + content[insert_at:]

    confirmation = re.search(r"^>\s*风险确认:\s*\S+.*$", content, re.MULTILINE)
    confirmed_line = "> 风险确认: confirmed"
    if confirmation:
        content = content[:confirmation.start()] + confirmed_line + content[confirmation.end():]
    else:
        risk_line = re.search(r"^>\s*风险:.*$", content, re.MULTILINE)
        insert_at = risk_line.end() if risk_line else 0
        content = content[:insert_at] + "\n" + confirmed_line + content[insert_at:]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = content.rstrip() + (
        f"\n\n## 风险确认记录\n\n- {now}: {old_risk} → {risk} — {reason.strip()}\n"
    )
    atomic_write(path, content)
    print(f"✅ {name}: 风险已确认 {old_risk} → {risk}")
    return risk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Confirm spec risk")
    parser.add_argument("project_root")
    parser.add_argument("spec_name")
    parser.add_argument("risk", choices=sorted(RISKS))
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    confirm_risk(args.project_root, args.spec_name, args.risk, args.reason)
