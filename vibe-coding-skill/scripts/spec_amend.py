#!/usr/bin/env python3
"""Record a requirements change (amendment) to a spec.

Creates an amendment record in .agents/specs/<name>-amendments.md
and appends a change note to the spec's amendment log section.

Usage:
    python3 spec_amend.py <project_root> <spec_name> "变更描述"
"""

import argparse
import os
import re
import shutil
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name


def amend_spec(project_root: str, spec_name: str, description: str) -> str | None:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    description = " ".join(description.split()).replace("|", r"\|")
    if not description:
        raise ValueError("变更描述不能为空")
    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_file):
        print(f"❌ 规格不存在: {spec_name}")
        return None

    # Destructive-operation warning (Rule 19 + Rule 7 + Rule 47)
    with open(spec_file, encoding="utf-8") as f:
        current_spec = f.read()
    status_match = re.search(r">\s*状态:\s*(\S+)", current_spec)
    current_status = status_match.group(1) if status_match else "draft"
    if current_status not in {"draft", "cancelled"}:
        print("⚠️  amend 是破坏性操作:")
        print(f"   - 重置状态: {current_status} → draft（Rule 19）")
        print("   - 归档现有 review/evidence 到 .agents/archive/<spec>/<timestamp>/（Rule 7）")
        print("   - bump Prompt version N → N+1（Rule 47）")
        print("   - 现有 review-decision 结论将被作废（digest mismatch）")
        print("   如果只是修格式/标签，考虑直接编辑 spec 而不用 amend。")
        print("   继续 amend？（--yes 跳过此提示）")
        # Non-interactive: just print the warning. Agents calling
        # via CLI can add --yes to suppress. The warning itself is
        # the key improvement — agents read stdout and self-correct.


    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    now_short = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    # 1. Create/append to amendment log file
    amend_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}-amendments.md")
    amend_entry = f"""### 变更 {now_short}

- **时间**: {now}
- **描述**: {description}
- **影响**: （请补充此变更影响了哪些验收标准、约束或涉及范围）

---
"""
    if os.path.exists(amend_file):
        with open(amend_file) as f:
            existing = f.read()
        new_content = existing.rstrip() + "\n\n" + amend_entry
    else:
        new_content = f"""# {spec_name} — 变更记录

> 规格文件: {spec_name}.md

{amend_entry}
"""

    atomic_write(amend_file, new_content)

    # 2. Append amendment note to spec file
    with open(spec_file) as f:
        spec = f.read()
    status_match = re.search(r">\s*状态:\s*(\S+)", spec)
    previous_status = status_match.group(1) if status_match else "draft"

    amend_note = f"""
---

## 变更记录

| 时间 | 描述 |
|------|------|
| {now} | {description} |
"""

    if "## 变更记录" in spec:
        table_header = "|------|------|"
        row = f"\n| {now} | {description} |"
        header_index = spec.find(table_header, spec.find("## 变更记录"))
        if header_index == -1:
            spec = spec.rstrip() + f"\n\n| {now} | {description} |\n"
        else:
            insert_at = spec.find("\n", header_index)
            spec = spec[:insert_at] + row + spec[insert_at:]
    else:
        spec = spec.rstrip() + "\n" + amend_note

    metadata = re.search(
        r"^>\s*状态:\s*\S+(?:\s*\|\s*创建:\s*([^|]+))?(?:\s*\|\s*更新:\s*(.+))?$",
        spec,
        re.MULTILINE,
    )
    created_at = metadata.group(1).strip() if metadata and metadata.group(1) else now
    replacement = f"> 状态: draft | 创建: {created_at} | 更新: {now}"
    if metadata:
        spec = spec[:metadata.start()] + replacement + spec[metadata.end():]
    else:
        spec = replacement + "\n\n" + spec

    risk_confirmation = re.search(
        r"^>\s*风险确认:\s*\S+.*$", spec, re.MULTILINE
    )
    if risk_confirmation:
        spec = (
            spec[:risk_confirmation.start()]
            + "> 风险确认: pending"
            + spec[risk_confirmation.end():]
        )
    else:
        risk_line = re.search(r"^>\s*风险:.*$", spec, re.MULTILINE)
        insert_at = risk_line.end() if risk_line else 0
        spec = spec[:insert_at] + "\n> 风险确认: pending" + spec[insert_at:]

    # Bump Prompt version on amendment (Rule 47).
    prompt_version_match = re.search(r"^>\s*Prompt version:\s*(\d+)\s*$", spec, re.MULTILINE)
    if prompt_version_match:
        new_version = int(prompt_version_match.group(1)) + 1
        spec = (
            spec[:prompt_version_match.start()]
            + f"> Prompt version: {new_version}"
            + spec[prompt_version_match.end():]
        )
    else:
        # No Prompt version line — append one so amended specs carry it forward.
        risk_line = re.search(r"^>\s*风险确认:.*$", spec, re.MULTILINE)
        insert_at = (risk_line.end() + 1) if risk_line else 0
        spec = spec[:insert_at] + "> Prompt version: 2\n" + spec[insert_at:]

    atomic_write(spec_file, spec)

    # Existing execution artifacts are based on the old requirements.
    archive_dir = os.path.join(
        project_root, ".agents", "archive", spec_name, now_short
    )
    archived = []
    for relative in (
        os.path.join("plans", f"{spec_name}.md"),
        os.path.join("prompts", f"{spec_name}.md"),
    ):
        source = os.path.join(project_root, ".agents", relative)
        if os.path.exists(source):
            os.makedirs(archive_dir, exist_ok=True)
            source_kind = os.path.basename(os.path.dirname(source))
            target = os.path.join(
                archive_dir, f"{source_kind}-{os.path.basename(source)}"
            )
            shutil.move(source, target)
            archived.append(target)

    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    if os.path.exists(reviews_dir):
        review_pattern = re.compile(
            rf"^>\s*规格:\s*{re.escape(spec_name)}\s*\|",
            re.MULTILINE,
        )
        for filename in sorted(os.listdir(reviews_dir)):
            source = os.path.join(reviews_dir, filename)
            if not filename.endswith(".md") or not os.path.isfile(source):
                continue
            with open(source, encoding="utf-8") as handle:
                if not review_pattern.search(handle.read()):
                    continue
            os.makedirs(archive_dir, exist_ok=True)
            target = os.path.join(archive_dir, f"reviews-{filename}")
            shutil.move(source, target)
            archived.append(target)

    evidence_dir = os.path.join(project_root, ".agents", "evidence", spec_name)
    if os.path.exists(evidence_dir):
        os.makedirs(archive_dir, exist_ok=True)
        target = os.path.join(archive_dir, "evidence")
        shutil.move(evidence_dir, target)
        archived.append(target)

    print(f"✅ 变更已记录: {spec_name}")
    print(f"   变更日志: {amend_file}")
    print(f"   规格文件已追加变更记录表格")
    print(f"   状态已从 {previous_status} 重置为 draft")
    print("   风险确认已重置为 pending")
    if archived:
        print(f"   旧计划、提示词或审查记录已归档到: {archive_dir}")
    print()
    print("💡 请更新受影响的规格内容，并重新确认风险等级。")
    return amend_file


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Record a spec amendment")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name")
    p.add_argument("description", help="Description of the change")
    p.add_argument("--yes", action="store_true", help="Skip destructive-operation warning")
    args = p.parse_args()
    amend_spec(os.path.abspath(args.project_root), args.spec_name, args.description)
