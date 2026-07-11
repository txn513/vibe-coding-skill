#!/usr/bin/env python3
"""Scan project-level upgrade-candidate files (cross-source signals).

Aggregates "Skill upgrade candidate" / "Project-level adoption" proposals
that agents write into `.agents/skill-upgrade-candidates*.md` files
across the project. These are usually written manually when an agent
recognizes a recurring pattern that should generalize to the Skill.

Architecture: this module is interface-isolated from `self_analyze` —
it has no import-time dependency on it. It accepts an OPTIONAL
`self_analyze_findings` keyword argument (pattern A from the
2026-07-11 architecture review) so a future iteration can enrich
proposals with self_analyze cross-references without changing the
public interface.

Standalone mode (this iteration): scan files only, return raw signals.
Enriched mode (future TODO): take self_analyze_findings and boost
priority / dedupe proposals that self_analyze also surfaces.

Usage as a CLI:
    python3 upgrade_signals.py <project_root> [--output report.md]
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter

from common import atomic_write

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def analyze(project_root: str, *, self_analyze_findings: dict | None = None) -> dict:
    """Scan upgrade-candidate files and return findings.

    Returns:
        dict with keys:
            - signals: list of {key, level, title, source_file, status}
            - source_files: list of paths scanned
            - self_analyze_used: bool (whether self_analyze_findings was consumed)
            - enriched: empty list for now (placeholder for future enrichment)

    Note: if `self_analyze_findings` is provided, this iteration logs
    the receipt but does NOT yet consume it (enrichment is TODO).
    The aggregator layer relies on the dict shape being stable; future
    enrichment will add keys without removing any.
    """
    project_root = os.path.abspath(project_root)
    agents_dir = os.path.join(project_root, ".agents")

    if not os.path.exists(agents_dir):
        return {
            "project_root": project_root,
            "signals": [],
            "source_files": [],
            "self_analyze_used": self_analyze_findings is not None,
            "enriched": [],
            "error": "no .agents/ directory",
        }

    candidate_files = _list_candidate_files(agents_dir)
    signals: list[dict] = []
    for path in candidate_files:
        signals.extend(_parse_candidate_file(path))

    # Future enrichment hook — for now just record receipt.
    enriched: list[dict] = []
    if self_analyze_findings is not None:
        # TODO(2026-Q3): cross-reference signals with self_analyze
        # governance_candidates and boost priority when both sources
        # point at the same failure_mode. Keep the public dict shape
        # stable so aggregator changes are independent.
        pass

    return {
        "project_root": project_root,
        "signals": signals,
        "source_files": candidate_files,
        "self_analyze_used": self_analyze_findings is not None,
        "enriched": enriched,
    }


def save_report(findings: dict, path: str) -> str:
    """Render findings to a markdown report file."""
    lines = [
        "# Upgrade Signals Report",
        "",
        f"项目: {findings.get('project_root', '?')}",
        f"扫描源文件: {len(findings.get('source_files', []))} 个",
        f"信号总数: {len(findings.get('signals', []))} 条",
        f"self_analyze 已消费: {findings.get('self_analyze_used', False)}",
        "",
    ]
    for sig in findings.get("signals", []):
        lines.append(
            f"- [{sig['level']}] {sig['title']}  "
            f"(来源: {os.path.basename(sig['source_file'])}, 状态: {sig['status']})"
        )
    atomic_write(path, "\n".join(lines) + "\n")
    return path


def _list_candidate_files(agents_dir: str) -> list[str]:
    """Find all upgrade-candidate files in .agents/.

    Accepts both naming conventions seen across projects:
      - `.agents/skill-upgrade-candidates*.md` (flat files)
      - `.agents/skill-upgrade-candidates/*.md` (directory of files)
      - `.agents/skill-upgrade-proposals/*.md` (directory variant)
    Returns absolute paths in stable sorted order so dedup is
    deterministic across runs.
    """
    found: list[str] = []

    # Flat file pattern
    for entry in sorted(os.listdir(agents_dir)):
        full = os.path.join(agents_dir, entry)
        if (
            entry.startswith("skill-upgrade-candidates")
            and entry.endswith(".md")
            and os.path.isfile(full)
        ):
            found.append(full)

    # Directory patterns
    for dirname in ("skill-upgrade-candidates", "skill-upgrade-proposals"):
        sub = os.path.join(agents_dir, dirname)
        if os.path.isdir(sub):
            for entry in sorted(os.listdir(sub)):
                if entry.endswith(".md") and entry != ".gitkeep":
                    found.append(os.path.join(sub, entry))

    return found


def _parse_candidate_file(path: str) -> list[dict]:
    """Parse a single candidate file into signal entries.

    Conservative parser: extract the title (first H1) and infer level
    (skill / project) from the body. Heuristic, not authoritative —
    agents may have written anything, so we surface what we find and
    let humans categorize downstream.
    """
    try:
        with open(path, encoding="utf-8") as fp:
            content = fp.read()
    except OSError:
        return []

    title = _extract_title(content) or os.path.basename(path)
    level = _infer_level(content)
    status = _extract_status(content) or "unknown"
    # Stable key: derived from title (semantic identity), so the aggregator
    # can dedup against self_analyze's failure_mode-based keys. Falls back
    # to filename if title extraction fails. Both fall back paths remain
    # deterministic per file.
    key_source = title if title else os.path.basename(path)
    key = re.sub(r"[^a-z0-9一-鿿]+", "-", key_source.lower()).strip("-")

    return [{
        "key": key,
        "level": level,
        "title": title,
        "source_file": path,
        "status": status,
    }]


def _extract_title(content: str) -> str:
    m = re.search(r"^#\s+(.+?)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def _infer_level(content: str) -> str:
    """Best-effort level inference. Falls back to 'mixed'.

    Heuristic weights (2026-07-11):
      - explicit prefixes ("Skill upgrade:" / "Project-level:" / "项目级")
        are strong signals and count for 3 points each
      - mid-content keywords ("skill ", "skill 升级", "rule ", "项目沉淀")
        are weaker signals and count for 1 point each
      - tie or no signal → 'mixed'

    Threshold: any positive score on a side resolves to that level.
    Mixed means: aggregator will probe both pools using substring dedup.
    """
    text = content.lower()
    strong_skill = sum(text.count(k) for k in ("skill upgrade:", "skill 升级:", "skill-level:"))
    strong_project = sum(text.count(k) for k in ("project-level:", "project 沉淀:", "项目级"))
    weak_skill = sum(text.count(k) for k in ("skill ", "skill 升级", "skill-level", "skill candidate", "rule "))
    weak_project = sum(text.count(k) for k in ("项目级", "project-level", "project 沉淀", "项目沉淀"))
    skill_score = strong_skill * 3 + weak_skill
    project_score = strong_project * 3 + weak_project
    if skill_score > project_score and skill_score > 0:
        return "skill"
    if project_score > skill_score and project_score > 0:
        return "project"
    return "mixed"


def _extract_status(content: str) -> str:
    m = re.search(r"\*\*状态\*\*:\s*(.+?)(?:\n|$)", content)
    if m:
        return m.group(1).strip()
    return ""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scan upgrade-candidate files in a project")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--output", default="", help="Save report to file")
    args = p.parse_args()

    findings = analyze(os.path.abspath(args.project_root))
    print(f"📂 upgrade_signals: {len(findings['signals'])} 条信号")
    for sig in findings["signals"]:
        print(f"   - [{sig['level']}] {sig['title']} ({sig['status']})")
    if args.output:
        path = save_report(findings, args.output)
        print(f"\n📄 报告已保存: {path}")
