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
    print("   下一步:")
    print("   1. 先填写失败模式分类和沉淀落点")
    print("   2. 优先更新当前项目的 rules / docs / testing / retro")
    print("   3. 只把抽象后的治理结论作为 Skill 候选")
    if "error" in findings:
        print(f"   4. 当前还无法聚合分析: {findings['error']}")
    elif governance_candidates:
        print(
            f"   4. 发现 {len(governance_candidates)} 条可能的 Skill 治理升级候选，是否应用？"
        )
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a project retrospective workflow")
    parser.add_argument("project_root")
    parser.add_argument("spec_name", nargs="?", default="")
    args = parser.parse_args()
    result = run_retrospective(args.project_root, args.spec_name)
    raise SystemExit(1 if result is None else 0)
