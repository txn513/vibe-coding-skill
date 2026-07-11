#!/usr/bin/env python3
"""Run a project retrospective workflow for a completed spec."""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write
import create_retro
import self_analyze
import spec_scorer


def run_retrospective(project_root: str, spec_name: str = "") -> dict | None:
    """Create or reuse a retro and summarize next retrospective actions."""
    project_root = os.path.abspath(project_root)
    spec_name = spec_name.strip()
    auto_status = "done"
    rationale = ""
    if not spec_name:
        spec_name, auto_status, rationale = _auto_detect_spec(project_root)
        if not spec_name:
            print("❌ 无法自动定位要复盘的 spec。请显式提供 spec_name。")
            return None
        if auto_status not in {"released", "done"}:
            print(f"❌ 自动定位到 {spec_name}，但其状态为 {auto_status}，尚不能创建正式回顾。")
            print("   请先完成该 spec，或显式指定一个已 released 或 done 的 spec。")
            return None

    retro_path = os.path.join(project_root, ".agents", "retros", f"{spec_name}.md")
    created = not os.path.exists(retro_path)
    retro_file = create_retro.create_retro(project_root, spec_name)
    if not retro_file:
        return None

    findings = self_analyze.analyze(project_root)
    governance_candidates = findings.get("governance_candidates", [])
    report_file = _write_retrospective_report(
        project_root, spec_name, retro_file, findings, governance_candidates
    )

    print()
    print("🧭 复盘动作")
    print(f"   目标 spec: {spec_name}")
    if rationale:
        print(f"   定位理由: {rationale}")
    print(f"   回顾文件: {retro_file}")
    print(f"   回顾状态: {'新建' if created else '复用现有回顾'}")
    print(f"   结构化报告: {report_file}")
    print()
    print("   Skill 候选 vs 项目沉淀 — 先做这一步分类（Rule 18 + 项目级 rule 范畴）:")
    print("     (a) 沉淀能否抽象为治理规则？跨项目通用 + 不含项目业务词汇 → Skill 候选")
    print("     (b) 沉淀仅本项目适用 (e.g. ORM / endpoint / fixture) → 项目规则 / docs")
    print("     (c) 沉淀当前不够具体，先放进 retro 开放 gap，等下一轮 spec 复测")
    print()
    # Surface the retro 沉淀落点 / SKILL_CANDIDATE field status explicitly.
    # Real failure mode: agent 走完 1-2-3 后从未回到 retro 末尾填这栏。
    _print_skill_candidate_field_status(project_root, spec_name)
    print()
    print("   下一步:")
    print("   1. 决策并填 retro '沉淀落点' 段 → Skill 候选 vs 项目沉淀")
    print("   2. 项目沉淀 → 写 .agents/rules/ 或更新 AGENTS.md / docs / testing")
    print("   3. Skill 候选 → 在 retro 末尾填摘要, 同步给 Skill 管理员评审")
    if "error" in findings:
        print(f"   4. self_analyze 暂无法聚合分析: {findings['error']}")
    elif governance_candidates:
        print(
            f"   4. self_analyze 发现 {len(governance_candidates)} 条可能的 Skill 治理升级候选，是否应用？"
        )
        for cand in governance_candidates[:3]:
            print(f"      - {cand['failure_mode']}: {cand['issue']}")
    else:
        print("   4. 暂无重复失败模式，不建议升级 Skill 核心")

    return {
        "retro_file": retro_file,
        "report_file": report_file,
        "created": created,
        "rationale": rationale,
        "governance_candidates": governance_candidates,
        "analysis": findings,
    }


def _auto_detect_spec(project_root: str) -> tuple[str, str, str]:
    """Find the most relevant recent spec using weighted scoring.

    Returns (spec_name, status, rationale).
    """
    done = spec_scorer.rank_specs(project_root, status_filter={"released", "done"})
    if done:
        top = done[0]
        rationale = spec_scorer.format_rationale(top, len(done))
        return top["name"], "done", rationale

    active = spec_scorer.rank_specs(
        project_root,
        status_filter={"released", "review", "in-progress", "spec-ready", "draft"},
    )
    if active:
        top = active[0]
        rationale = spec_scorer.format_rationale(top, len(active))
        return top["name"], top["status"], rationale

    return "", "", ""


def _write_retrospective_report(
    project_root: str,
    spec_name: str,
    retro_file: str,
    findings: dict,
    governance_candidates: list[dict],
) -> str:
    """Persist a compact retrospective report for project-local reuse."""
    retro_content = ""
    if os.path.exists(retro_file):
        with open(retro_file, encoding="utf-8") as handle:
            retro_content = handle.read()

    primary_failure_mode = _extract_bullet_value(retro_content, "主失败模式")
    secondary_failure_mode = _extract_bullet_value(retro_content, "次级失败模式")
    rationale = _extract_bullet_value(retro_content, "为什么归到这个类别")
    project_updates = _extract_bullet_value(retro_content, "项目内应更新什么")
    claim_evidence = _extract_bullet_value(retro_content, "证据引用")
    unverified_claims = _extract_bullet_value(retro_content, "未复验结论")
    claim_warnings = create_retro.claim_evidence_warnings(retro_content)
    skill_candidate = _extract_bullet_value(retro_content, "是否形成 Skill 治理候选")
    skill_candidate_summary = _extract_bullet_value(
        retro_content, "如果形成，候选摘要是什么"
    )

    lines = [
        f"# {spec_name} — 结构化复盘报告",
        "",
        f"- **生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **回顾文件**: {retro_file}",
        "",
        "## 失败模式",
        "",
        f"- **主失败模式**: {primary_failure_mode or '(待填写)'}",
        f"- **次级失败模式**: {secondary_failure_mode or '(待填写)'}",
        f"- **分类理由**: {rationale or '(待填写)'}",
        "",
        "## 项目沉淀",
        "",
        f"- **项目内应更新什么**: {project_updates or '(待填写)'}",
        "",
        "## 结论证据",
        "",
        f"- **证据引用**: {claim_evidence or '(待填写)'}",
        f"- **未复验结论**: {unverified_claims or '(待填写)'}",
        f"- **证据状态**: {'需要补充' if claim_warnings else '已填写或暂无失败结论'}",
        "",
        "## Skill 候选",
        "",
        f"- **是否形成 Skill 治理候选**: {skill_candidate or '(待填写)'}",
        f"- **候选摘要**: {skill_candidate_summary or '(待填写)'}",
        "",
        "## 聚合分析",
        "",
    ]

    if "error" in findings:
        lines.append(f"- **当前状态**: {findings['error']}")
    else:
        lines.append(f"- **已分析回顾数**: {findings.get('retros_analyzed', 0)}")
        if governance_candidates:
            lines.append(
                f"- **发现 {len(governance_candidates)} 条可能的 Skill 治理升级候选，是否应用？**"
            )
            for candidate in governance_candidates:
                lines.append(
                    f"  - {candidate['failure_mode']}: {candidate['issue']}"
                )
        else:
            lines.append("- **结论**: 暂无重复失败模式，不建议升级 Skill 核心")

    report_file = os.path.join(
        project_root, ".agents", "reports", f"retrospective-{spec_name}.md"
    )
    atomic_write(report_file, "\n".join(lines) + "\n")
    return report_file


def _extract_bullet_value(content: str, label: str) -> str:
    match = re.search(
        rf"^\s*-\s*\*\*{re.escape(label)}\*\*:\s*(.+)$",
        content,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _print_skill_candidate_field_status(project_root: str, spec_name: str) -> None:
    """Surface whether the retro 沉淀落点 → Skill 候选 fields are filled.

    Real failure mode (2026-07-11 review): agents walk through the
    retrospective 1→2→3→4 list and never reach "Skill 候选" at the
    bottom. The retro file's "是否形成 Skill 治理候选" / "候选摘要"
    fields stay {{SKILL_CANDIDATE}} placeholders or get a one-line
    "no" with no actual categorization. self_analyze then sees no
    governance signal for that retro, and Skill-level patterns the
    agent intended to surface are lost.

    This function reads the just-created retro and surfaces:
      - both fields filled → agent has done the categorization
      - placeholder left or "(待填写)" → missed step reminder
      - explicit "no" / "否" → fine, recorded as not applicable
    """
    retro_path = os.path.join(project_root, ".agents", "retros", f"{spec_name}.md")
    if not os.path.exists(retro_path):
        return
    with open(retro_path, encoding="utf-8") as handle:
        content = handle.read()
    skill_field = _extract_bullet_value(content, "是否形成 Skill 治理候选")
    summary_field = _extract_bullet_value(content, "如果形成，候选摘要是什么")
    unfilled = any(
        not field
        or "{{" in field
        or "(待填写)" in field
        or "(描述" in field
        for field in (skill_field, summary_field)
    )
    if unfilled:
        print("   ⚠️  retro 末尾 '沉淀落点' 段（Skill 候选两栏）尚未填写:")
        print("      > 是否形成 Skill 治理候选: (待填写) ← 这是 agent 最容易漏的步骤")
        print("      > 如果形成, 候选摘要是什么: (待填写)")
        print("      填完后这两条可作为 candidate 输入 self_analyze / 提交给 Skill 管理员")
        print("      <!-- vibe:retro_skill_candidate_unfilled: spec=" + spec_name + " -->")
    elif skill_field.strip().lower() in {"否", "no", "无", "不形成", "n/a"}:
        print("   ℹ️  retro Skill 候选栏已决策: 不形成 (项目级规则已足够)")
    else:
        print(f"   ✅ retro Skill 候选栏已填: {skill_field[:60]}{'...' if len(skill_field) > 60 else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a project retrospective workflow")
    parser.add_argument("project_root")
    parser.add_argument("spec_name", nargs="?", default="")
    args = parser.parse_args()
    result = run_retrospective(args.project_root, args.spec_name)
    raise SystemExit(1 if result is None else 0)
