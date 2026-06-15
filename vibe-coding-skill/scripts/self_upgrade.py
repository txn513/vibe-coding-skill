#!/usr/bin/env python3
"""Apply skill improvement suggestions from self_analyze.py.

IMPORTANT: All additions go to the PROJECT's .agents/ directory, NOT to the skill itself.
- Checklist items → .agents/checklists/custom.md
- Rule files → .agents/rules/
- Template fields → .agents/specs/ (via updated spec template)

The skill's own SKILL.md and templates/ remain as the universal baseline.
Only human review should promote project-specific knowledge to the skill level.

Usage:
    python3 self_upgrade.py --dry-run        # preview changes only
    python3 self_upgrade.py --apply           # apply to project
    python3 self_upgrade.py --apply --auto    # auto-apply medium+ priority
    python3 self_upgrade.py --apply --prune   # also run self_prune after
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name
from knowledge_gate import classify_knowledge, require_project_destination

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def upgrade(project_root: str, dry_run: bool = True, auto: bool = False) -> list[dict]:
    """Run self-analysis and apply improvements to the PROJECT."""
    sys.path.insert(0, SCRIPT_DIR)
    import self_analyze

    findings = self_analyze.analyze(project_root)

    if "error" in findings:
        print(f"📭 {findings['error']}")
        return []

    suggestions = findings.get("suggestions", [])
    if not suggestions:
        print("✅ 无改进建议。")
        return []

    # Ensure project directories exist
    _ensure_dirs(project_root)

    applied = []

    for s in suggestions:
        if auto and s["priority"] == "low":
            print(f"⏭️  跳过 (low priority): {s['issue'][:60]}...")
            continue

        result = _apply_suggestion(project_root, s, dry_run)
        if result:
            applied.append(result)

    return applied


def _ensure_dirs(project_root: str) -> None:
    """Ensure project .agents/ subdirectories exist."""
    for sub in ["checklists", "rules", "specs"]:
        d = os.path.join(project_root, ".agents", sub)
        os.makedirs(d, exist_ok=True)


def _apply_suggestion(project_root: str, s: dict, dry_run: bool) -> dict | None:
    """Apply a single suggestion to the PROJECT (not the skill)."""
    stype = s["type"]
    action = s["action"]
    ownership = classify_knowledge(
        f"{s.get('issue', '')}\n{action}",
        s.get("target", ""),
    )

    label = "🔍 预览" if dry_run else "🔧 应用"
    print(f"\n{label}: [{s['priority'].upper()}] {stype}")
    print(f"   问题: {s['issue']}")
    print(f"   操作: {action}")
    print(
        f"   知识归属: {ownership['kind']} "
        f"({ownership['confidence']}) — {ownership['reason']}"
    )

    if ownership["kind"] != "project":
        print("   ⛔ 已阻止：self_upgrade 只处理项目本地知识。")
        if ownership["kind"] == "external":
            print("   📝 请通过项目配置或外部工具集成处理。")
        else:
            print("   📝 通用治理候选必须单独审查，不能从单个项目自动晋升。")
        return {
            "type": stype,
            "classification": ownership["kind"],
            "blocked": True,
            "applied": False,
        }

    if stype == "checklist":
        return _add_to_project_checklist(project_root, s, dry_run)
    elif stype == "rule":
        return _add_to_project_rules(project_root, s, dry_run)
    elif stype == "template":
        return _add_to_project_spec_template(project_root, s, dry_run)
    elif stype == "script":
        print(f"   ⚠️  脚本类改进需人工处理，已跳过。")
        print(f"   📝 建议: {action}")
        return None
    else:
        print(f"   ⚠️  未知类型: {stype}")
        return None


def _add_to_project_checklist(project_root: str, s: dict, dry_run: bool) -> dict | None:
    """Add an item to the project's custom checklist."""
    m = re.search(r"增加一项:\s*['\"](.+?)['\"]", s["action"])
    if not m:
        print(f"   ❌ 无法解析 checklist 项")
        return None

    new_item = m.group(1)

    # Determine which phase checklist
    target = s["target"]
    if "implementation" in target.lower():
        section = "Implementation"
    elif "review" in target.lower():
        section = "Review"
    elif "deploy" in target.lower():
        section = "Deploy"
    elif "pre-code" in target.lower():
        section = "Pre-Code"
    elif "pre-design" in target.lower():
        section = "Pre-Design"
    else:
        section = "General"

    checklist_file = os.path.join(project_root, ".agents", "checklists", "custom.md")
    require_project_destination(checklist_file, project_root)

    # Read existing or create
    if os.path.exists(checklist_file):
        with open(checklist_file) as f:
            content = f.read()
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        content = f"# 项目自定义检查项\n\n> 自动生成自回顾分析 — {now}\n> 这些是本项目特有的检查项，随项目积累自动演化。\n\n"

    # Find or create the section
    section_header = f"## {section}"
    if section_header in content:
        # Check if item already exists
        if new_item in content:
            print(f"   ⚠️  检查项已存在: {new_item}")
            return None
        # Add after section header
        idx = content.find(section_header)
        insert_pos = content.find("\n", idx) + 1
        new_line = f"- [ ] {new_item}\n"
    else:
        # Add new section at end
        new_line = f"\n{section_header}\n- [ ] {new_item}\n"

    if dry_run:
        print(f"   → 将添加到: {checklist_file}")
        print(f"   → 内容: {new_line.strip()}")
        return {"type": "checklist", "target": checklist_file, "item": new_item, "applied": False}

    if section_header in content:
        new_content = content[:insert_pos] + new_line + content[insert_pos:]
    else:
        new_content = content + new_line

    atomic_write(checklist_file, new_content)

    print(f"   ✅ 已添加到项目 checklist: {new_item.strip()}")
    return {"type": "checklist", "target": checklist_file, "item": new_item, "applied": True}


def _add_to_project_rules(project_root: str, s: dict, dry_run: bool) -> dict | None:
    """Create a new rule file in the project's .agents/rules/."""
    rule_name = s["action"].split("覆盖:")[-1].strip() if "覆盖:" in s["action"] else ""
    if not rule_name:
        rule_name = s["issue"].split("缺少规则:")[-1].strip() if "缺少规则:" in s["issue"] else ""

    if not rule_name:
        print(f"   ❌ 无法解析规则名称")
        return None

    slug = re.sub(r"[^\w.-]+", "-", rule_name.lower(), flags=re.UNICODE).strip("-")[:60]
    slug = validate_artifact_name(slug or "custom-rule", "规则名称")
    rule_file = os.path.join(project_root, ".agents", "rules", f"{slug}.md")
    require_project_destination(rule_file, project_root)

    new_content = f"""# {rule_name}

> 自动生成自回顾分析 — {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | 状态: proposed

## 项目规则

- {rule_name}

## 采用条件

- [ ] 项目负责人确认该规则表述准确且可执行
- [ ] 至少一个后续任务使用该规则并在回顾中评估效果
"""

    if os.path.exists(rule_file):
        print(f"   ⚠️  规则文件已存在: {rule_file}")
        return None

    if dry_run:
        print(f"   → 将创建: {rule_file}")
        print(f"   → 内容预览: {new_content[:150]}...")
        return {"type": "rule", "file": rule_file, "applied": False}

    atomic_write(rule_file, new_content)

    print(f"   ✅ 已创建项目规则: {rule_file}")
    return {"type": "rule", "file": rule_file, "applied": True}


def _add_to_project_spec_template(project_root: str, s: dict, dry_run: bool) -> dict | None:
    """Add a hint field to the project's spec template (or create a project-local one)."""
    # Extract field name
    m = re.search(r"提醒填写:\s*(.+)", s["action"])
    if not m:
        print(f"   ❌ 无法解析字段名")
        return None

    field_hint = m.group(1).strip()

    # Create/update a project-local spec hints file
    hints_file = os.path.join(project_root, ".agents", "checklists", "spec-hints.md")
    require_project_destination(hints_file, project_root)

    if os.path.exists(hints_file):
        with open(hints_file) as f:
            content = f.read()
    else:
        content = "# Spec 填写提示\n\n> 自动生成自回顾分析\n> 创建 spec 时，额外注意以下方面：\n\n"

    new_hint = f"- **{field_hint}**: (请在此填写)\n"

    if new_hint in content:
        print(f"   ⚠️  提示已存在: {field_hint}")
        return None

    if dry_run:
        print(f"   → 将添加到: {hints_file}")
        print(f"   → 提示: {new_hint.strip()}")
        return {"type": "template", "target": hints_file, "hint": field_hint, "applied": False}

    atomic_write(hints_file, content + new_hint)

    print(f"   ✅ 已添加 spec 提示: {field_hint}")
    return {"type": "template", "target": hints_file, "hint": field_hint, "applied": True}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Apply project-level improvements from retro analysis")
    p.add_argument("project_root", nargs="?", default=None,
                   help="Project root directory (default: auto-detect)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Preview changes without applying (default)")
    p.add_argument("--apply", action="store_true",
                   help="Actually apply changes")
    p.add_argument("--auto", action="store_true",
                   help="Skip confirmation for medium+ priority")
    p.add_argument("--prune", action="store_true",
                   help="Also run self_prune after upgrade")
    args = p.parse_args()

    # Resolve project root
    if args.project_root:
        project_root = os.path.abspath(args.project_root)
    else:
        project_root = os.getcwd()
        # Walk up to find .agents/
        d = project_root
        while True:
            if os.path.exists(os.path.join(d, ".agents")):
                project_root = d
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent

    dry_run = not args.apply
    applied = upgrade(project_root, dry_run=dry_run, auto=args.auto)

    if args.prune and not dry_run:
        print()
        print("=" * 50)
        print("🧹 运行瘦身...")
        import self_prune
        self_prune.prune(project_root, dry_run=False)

    if applied:
        applied_count = sum(1 for a in applied if a.get("applied"))
        print(f"\n📊 总计: {len(applied)} 条建议, {applied_count} 条已应用（均在项目内）")
        print(f"📍 所有变更仅影响当前项目，不会污染 Skill 全局文件。")
        if dry_run:
            print(f"💡 使用 --apply 实际执行变更。")
