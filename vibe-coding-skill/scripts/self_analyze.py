#!/usr/bin/env python3
from __future__ import annotations
"""Analyze project retros to identify project-local workflow improvements.

Scans all retrospectives in a project, finds recurring issues, and generates
concrete suggestions for improving that project's guidance.

Usage:
    python3 self_analyze.py <project_root> [--output report.md]
"""

import argparse
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from common import atomic_write
import spec_scorer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def analyze(project_root: str) -> dict:
    """Analyze all retros and return findings."""
    project_root = os.path.abspath(project_root)
    retros_dir = os.path.join(project_root, ".agents", "retros")

    if not os.path.exists(retros_dir):
        return {"error": "暂无回顾数据。至少完成一个功能的回顾后才有分析素材。"}

    retro_files = sorted([
        f for f in os.listdir(retros_dir)
        if f.endswith(".md") and f != ".gitkeep"
    ])

    if len(retro_files) < 2:
        return {"error": f"只有 {len(retro_files)} 份回顾，需要至少 2 份才能发现模式。"}

    findings = {
        "project_root": project_root,
        "retros_analyzed": len(retro_files),
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "failure_modes": Counter(),
        "builder_weaknesses": Counter(),
        "missing_rules": Counter(),
        "missing_constraints": Counter(),
        "reviewer_missed": Counter(),
        "context_issues": Counter(),
        "action_items": [],
        "suggestions": [],
        "governance_candidates": [],
        "top_specs": [],
    }

    for rf in retro_files:
        path = os.path.join(retros_dir, rf)
        with open(path) as f:
            content = f.read()

        spec_name = rf.replace(".md", "")

        if _is_unfilled_retro(content):
            continue

        # Extract fields
        primary_failure_mode = _extract_field(content, "主失败模式")
        weaknesses = _extract_list(content, "反复出错")
        missing_rules = _extract_list(content, "需要补充的规则")
        missing_constraints = _extract_list(content, "哪些约束漏了")
        reviewer_missed = _extract_list(content, "漏掉的问题")
        agents_accuracy = _extract_field(content, "AGENTS.md 是否准确")
        context_understanding = _extract_field(content, "Agent 是否理解了项目结构")
        ac_coverage = _extract_field(content, "验收标准是否覆盖了所有线上情况")

        if primary_failure_mode and not _is_placeholder(primary_failure_mode):
            findings["failure_modes"][primary_failure_mode] += 1
        for w in weaknesses:
            findings["builder_weaknesses"][w] += 1
        for r in missing_rules:
            findings["missing_rules"][r] += 1
        for c in missing_constraints:
            findings["missing_constraints"][c] += 1
        for m in reviewer_missed:
            findings["reviewer_missed"][m] += 1
        if agents_accuracy and re.search(r"(?:^|[^是])否(?:[\uff0c,。.\s]|$)", agents_accuracy):
            findings["context_issues"]["AGENTS.md 不准确"] += 1
        if context_understanding and re.search(r"(?:^|[^是])否(?:[\uff0c,。.\s]|$)", context_understanding):
            findings["context_issues"]["Agent 未正确理解项目结构"] += 1

    # Generate suggestions
    _generate_suggestions(findings)
    _emit_recovery_hints(project_root, findings)

    # Rank done specs by relevance for potential deeper retrospective
    ranked = spec_scorer.rank_specs(project_root, status_filter={"done"}, limit=5)
    retro_set = set(
        f.replace(".md", "") for f in os.listdir(retros_dir)
        if f.endswith(".md") and f != ".gitkeep"
    )
    findings["top_specs"] = [
        s for s in ranked if s["name"] in retro_set
    ]

    return findings


def _generate_suggestions(findings: dict) -> None:
    """Generate concrete skill improvement suggestions from findings."""
    suggestions = findings["suggestions"]
    governance_candidates = findings["governance_candidates"]

    recurring_failure_modes = [
        (mode, count) for mode, count in findings["failure_modes"].items()
        if count >= 2 and len(mode) > 3
    ]
    for mode, count in recurring_failure_modes[:3]:
        governance_candidates.append({
            "type": "governance-candidate",
            "failure_mode": mode,
            "issue": f"{count}/{findings['retros_analyzed']} 个回顾出现相同失败模式: {mode}",
            "action": f"评估是否需要强化 Skill 对该失败模式的默认治理或复盘框架",
            "priority": "high" if count >= 3 else "medium",
        })

    # 1. Recurring builder weaknesses → add to implementation checklist
    recurring_weaknesses = [
        (w, c) for w, c in findings["builder_weaknesses"].items()
        if c >= 2 and len(w) > 3
    ]
    if recurring_weaknesses:
        for weakness, count in recurring_weaknesses[:3]:
            suggestions.append({
                "type": "checklist",
                "target": ".agents/checklists/custom.md (Implementation)",
                "issue": f"Agent 在 {count}/{findings['retros_analyzed']} 个功能中反复出错: {weakness}",
                "action": f"在 Implementation Checklist 中增加一项: '{weakness}'",
                "priority": "high" if count >= 3 else "medium",
            })

    # 2. Recurring missing rules → update rule templates
    recurring_rules = [
        (r, c) for r, c in findings["missing_rules"].items()
        if c >= 2 and len(r) > 3
    ]
    if recurring_rules:
        for rule, count in recurring_rules[:3]:
            suggestions.append({
                "type": "rule",
                "target": ".agents/rules/",
                "issue": f"{count}/{findings['retros_analyzed']} 个回顾发现缺少规则: {rule}",
                "action": f"在项目规则中新增或更新规则文件，覆盖: {rule}",
                "priority": "high" if count >= 3 else "medium",
            })

    # 3. Recurring missing constraints → update spec template
    recurring_constraints = [
        (c, n) for c, n in findings["missing_constraints"].items()
        if n >= 2 and len(c) > 3
    ]
    if recurring_constraints:
        for constraint, count in recurring_constraints[:3]:
            suggestions.append({
                "type": "template",
                "target": ".agents/checklists/spec-hints.md",
                "issue": f"{count}/{findings['retros_analyzed']} 个回顾发现缺少约束: {constraint}",
                "action": f"在项目 spec 提示中增加一项，提醒填写: {constraint}",
                "priority": "medium",
            })

    # 4. Context issues → update init/onboard/refresh
    if findings["context_issues"]:
        total = sum(findings["context_issues"].values())
        if total >= 2:
            suggestions.append({
                "type": "script",
                "target": "refresh_context.py",
                "issue": f"上下文准确性在 {total} 次回顾中被提及",
                "action": "增强 refresh_context.py 的检测能力，或增加刷新频率提醒",
                "priority": "medium",
            })

    # 5. Reviewer missed → update review checklist
    recurring_missed = [
        (m, c) for m, c in findings["reviewer_missed"].items()
        if c >= 2 and len(m) > 3
    ]
    if recurring_missed:
        for missed, count in recurring_missed[:3]:
            suggestions.append({
                "type": "checklist",
                "target": ".agents/checklists/custom.md (Review)",
                "issue": f"Review Agent 在 {count}/{findings['retros_analyzed']} 次审查中漏掉: {missed}",
                "action": f"在 Review Checklist 中增加一项: '{missed}'",
                "priority": "high" if count >= 3 else "medium",
            })


# Mapping of shared-failure-mode labels (from Rule 25 taxonomy) to
# optional project-local rule stems that, when adopted, hint at recovery.
# This is NOT the Skill inventing recovery playbooks from labels: the
# hint only appears when the project has explicitly adopted one of the
# rule stems below (Rule 18). New mappings are added only when a real
# cross-project pattern is established, never from a single project
# incident (Rule 20). The mapping is intentionally short and generic.
_FAILURE_MODE_HINT_RULES = {
    "single-point verified, composed path missing": ("testing-composed-paths",),
    "steady-state verified, time-state missing": ("testing-time-sensitive",),
    "happy-path verified, degradation-path missing": ("testing-degradation",),
    "component capability exists, routing or selection wrong": ("routing",),
    "rule exists, but is not bound to a gate or command": ("rule-binding",),
    "evidence exists, but does not prove the claimed behavior": ("evidence-discipline",),
}


def _list_adopted_rule_stems(project_root: str) -> set[str]:
    """Return the set of rule stems the project has explicitly adopted.

    Honors Rule 18: only rules with `状态: adopted` (or the English
    equivalent) count. `proposed` rules are not yet binding (Rule 9).
    """
    rules_dir = os.path.join(project_root, ".agents", "rules")
    if not os.path.isdir(rules_dir):
        return set()
    stems: set[str] = set()
    for entry in os.listdir(rules_dir):
        if not entry.endswith(".md"):
            continue
        try:
            with open(os.path.join(rules_dir, entry), encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            continue
        status_match = re.search(r">\s*状态:\s*(\S+)", content)
        if status_match and status_match.group(1) == "adopted":
            stems.add(entry[:-3])
    return stems


def _emit_recovery_hints(project_root: str, findings: dict) -> None:
    """Surface recovery hints for recurring failure modes (Rule 25.1).

    For each failure-mode label that appears in 2+ retros, check whether
    the project has adopted a rule stem that maps to it. If yes, the
    hint is added to suggestions. If no, surface an advisory that points
    the user to the project rules directory so they can decide whether
    to adopt one. The Skill never invents the rule itself.
    """
    adopted = _list_adopted_rule_stems(project_root)
    recurring = [
        (mode, count) for mode, count in findings["failure_modes"].items()
        if count >= 2 and len(mode) > 3
    ]
    for mode, count in recurring:
        hint_stems = _FAILURE_MODE_HINT_RULES.get(mode)
        if not hint_stems:
            findings["suggestions"].append({
                "type": "advisory",
                "target": "rule taxonomy",
                "issue": f"{count}/{findings['retros_analyzed']} 个回顾使用未映射的失败模式标签: {mode}",
                "action": "该标签未映射到项目级 hint rule（Rule 25.1）。如确需，可自行在 .agents/rules/ 创建并 adopted；Skill 不会自动生成。",
                "priority": "low",
            })
            continue
        adopted_stem = next((s for s in hint_stems if s in adopted), None)
        if adopted_stem:
            findings["suggestions"].append({
                "type": "recovery-hint",
                "target": f".agents/rules/{adopted_stem}.md",
                "issue": f"{count}/{findings['retros_analyzed']} 个回顾出现: {mode}",
                "action": f"项目已 adopted {adopted_stem} rule。建议在下次类似 spec 推进前 review 这条 rule。",
                "priority": "medium",
            })
        else:
            findings["suggestions"].append({
                "type": "recovery-hint-missing",
                "target": ".agents/rules/",
                "issue": f"{count}/{findings['retros_analyzed']} 个回顾出现: {mode}",
                "action": f"未在 .agents/rules/ 找到 adopted 的 {hint_stems[0]} rule（Rule 25.1 hint）。Skill 不会自动创建，由项目决定。",
                "priority": "low",
            })


def print_report(findings: dict) -> None:
    """Print a human-readable analysis report."""
    if "error" in findings:
        print(f"📭 {findings['error']}")
        return

    print(f"🔍 项目工作流改进分析")
    print(f"═" * 50)
    print(f"   项目: {findings['project_root']}")
    print(f"   分析回顾数: {findings['retros_analyzed']}")
    print(f"   分析时间: {findings['analyzed_at']}")
    print()

    # Builder weaknesses
    if findings["builder_weaknesses"]:
        print("🤖 Agent 反复出错 (≥2 次):")
        for w, c in findings["builder_weaknesses"].most_common(5):
            if c >= 2:
                print(f"   [{c}次] {w}")
        print()

    # Missing rules
    if findings["missing_rules"]:
        print("📋 缺少的规则 (≥2 次):")
        for r, c in findings["missing_rules"].most_common(5):
            if c >= 2:
                print(f"   [{c}次] {r}")
        print()

    # Missing constraints
    if findings["missing_constraints"]:
        print("🔒 遗漏的约束 (≥2 次):")
        for con, c in findings["missing_constraints"].most_common(5):
            if c >= 2:
                print(f"   [{c}次] {con}")
        print()

    # Reviewer missed
    if findings["reviewer_missed"]:
        print("👀 Review 漏掉的问题 (≥2 次):")
        for m, c in findings["reviewer_missed"].most_common(5):
            if c >= 2:
                print(f"   [{c}次] {m}")
        print()

    # Context issues
    if findings["context_issues"]:
        print("🗂️ 上下文问题:")
        for issue, count in findings["context_issues"].most_common():
            print(f"   [{count}次] {issue}")
        print()

    if findings["governance_candidates"]:
        print("🧩 Skill 治理升级候选:")
        for candidate in findings["governance_candidates"]:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                candidate["priority"], "⚪"
            )
            print(f"   {icon} {candidate['failure_mode']}")
            print(f"      {candidate['issue']}")
        print()
        print(
            f"💬 发现 {len(findings['governance_candidates'])} 条可能的 Skill 治理升级候选，是否应用？"
        )
        print()

    # Top specs worth deeper retrospective
    top_specs = findings.get("top_specs", [])
    if top_specs:
        print("🏆 已复盘 spec 中最值得深入的 (按加权评分):")
        for s in top_specs[:3]:
            signals = ", ".join(s["signals"]) if s["signals"] else "baseline only"
            print(f"   {s['name']}  score={s['score']:.0f}  [{signals}]")
        print()

    # Suggestions
    if findings["suggestions"]:
        print(f"💡 改进建议 ({len(findings['suggestions'])} 条):")
        print("─" * 50)
        for i, s in enumerate(findings["suggestions"], 1):
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["priority"], "⚪")
            print(f"  {icon} #{i} [{s['type']}] {s['target']}")
            print(f"     问题: {s['issue']}")
            print(f"     建议: {s['action']}")
            print()
    else:
        print("✅ 未发现需要新增项目规则的重复模式。")

    print(f"💡 运行 self_upgrade.py 来执行这些改进建议。")


def save_report(findings: dict, output_path: str) -> str:
    """Save the report as a markdown file."""
    if "error" in findings:
        atomic_write(output_path, f"# Self Analysis Report\n\n{findings['error']}\n")
        return output_path

    lines = [
        f"# 项目工作流改进分析",
        f"",
        f"- **项目**: {findings['project_root']}",
        f"- **回顾数**: {findings['retros_analyzed']}",
        f"- **时间**: {findings['analyzed_at']}",
        f"",
        f"## 发现",
        f"",
    ]

    sections = [
        ("重复失败模式", findings["failure_modes"]),
        ("Agent 反复出错", findings["builder_weaknesses"]),
        ("缺少的规则", findings["missing_rules"]),
        ("遗漏的约束", findings["missing_constraints"]),
        ("Review 漏掉的问题", findings["reviewer_missed"]),
    ]

    for title, counter in sections:
        items = [(k, v) for k, v in counter.most_common() if v >= 2]
        if items:
            lines.append(f"### {title}")
            for item, count in items:
                lines.append(f"- [{count}次] {item}")
            lines.append("")

    if findings["suggestions"]:
        lines.append("## 改进建议")
        lines.append("")
        for i, s in enumerate(findings["suggestions"], 1):
            lines.append(f"### #{i} [{s['priority'].upper()}] {s['type']}")
            lines.append(f"- **目标**: {s['target']}")
            lines.append(f"- **问题**: {s['issue']}")
            lines.append(f"- **操作**: {s['action']}")
            lines.append("")

    if findings["governance_candidates"]:
        lines.append("## Skill 治理升级候选")
        lines.append("")
        for i, candidate in enumerate(findings["governance_candidates"], 1):
            lines.append(f"### #{i} [{candidate['priority'].upper()}] {candidate['failure_mode']}")
            lines.append(f"- **问题**: {candidate['issue']}")
            lines.append(f"- **操作**: {candidate['action']}")
            lines.append("")

    # Top specs section
    top_specs = findings.get("top_specs", [])
    if top_specs:
        lines.append("## 最值得深入的已复盘 Spec")
        lines.append("")
        for s in top_specs[:5]:
            signals = ", ".join(s["signals"]) if s["signals"] else "baseline only"
            lines.append(f"- **{s['name']}** (score={s['score']:.0f}): {signals}")
        lines.append("")

    atomic_write(output_path, "\n".join(lines))

    return output_path


def _extract_list(content: str, field: str) -> list[str]:
    """Extract list items from a field — handles inline format: '- **Field**: value'."""
    items = []
    inline_pattern = rf"(?:^|\n)\s*-?\s*\*\*{re.escape(field)}\*\*:?\s*(.+?)(?:\n|$)"
    for m in re.finditer(inline_pattern, content, re.MULTILINE):
        item = m.group(1).strip()
        if item and not _is_placeholder(item) and len(item) > 3:
            items.append(item)
    return items


def _is_placeholder(s: str) -> bool:
    """Check if a string is a template placeholder."""
    text = s.strip()
    if not text:
        return True
    if text in {"-", "无", "N/A"}:
        return False
    markers = (
        "(什么", "(Agent", "(哪些", "(如何", "(描述", "(计划", "(请", "（请",
        "(从 spec 复制", "(实际交付了什么)", "(参与回顾的人)", "(上线日期)",
        "(做得好的地方)", "(做得不好的地方)", "(应该补充什么规则",
        "(Review Agent 漏掉了什么)", "(更新 AGENTS.md", "(更新哪些规则文件)",
        "(是否需要调整 spec 模板)", "(是否需要调整 review checklist)", "(其他行动项)",
    )
    return any(marker in text for marker in markers)


def _is_unfilled_retro(content: str) -> bool:
    """Heuristically detect retros that are still mostly template placeholders."""
    fields = [
        _extract_field(content, "最初意图"),
        _extract_field(content, "实际交付"),
        _extract_field(content, "差异分析"),
        _extract_field(content, "擅长"),
        _extract_field(content, "反复出错"),
        _extract_field(content, "需要补充的规则"),
        _extract_field(content, "发现的真实问题"),
        _extract_field(content, "漏掉的问题"),
        _extract_field(content, "AGENTS.md 是否准确"),
        _extract_field(content, "Agent 是否理解了项目结构"),
    ]
    meaningful = [field for field in fields if field and not _is_placeholder(field)]
    return len(meaningful) < 2


def _extract_field(content: str, field: str) -> str:
    """Extract a single field value."""
    pattern = rf"\*\*{field}\*\*:\s*(.+)"
    m = re.search(pattern, content)
    if m:
        return m.group(1).strip()
    return ""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Analyze retros for skill improvement opportunities")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--output", default="", help="Save report to file")
    args = p.parse_args()

    findings = analyze(os.path.abspath(args.project_root))
    print_report(findings)

    if args.output:
        path = save_report(findings, args.output)
        print(f"\n📄 报告已保存: {path}")
