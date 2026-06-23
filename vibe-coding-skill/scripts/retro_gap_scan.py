#!/usr/bin/env python3
"""Scan project retros for open gaps that may have been closed by new evidence.

This module is deliberately read-only. It identifies candidate gaps from
existing retro files and lets the caller (record_evidence, doctor, status)
present them to the user. It never writes to retro files.

Gap detection follows the project convention (not a Skill-imposed schema):
a "## 开放 gap" / "## 未完成项" / "## Gap" / "## Open gaps" section
contains a list of explicit open items. Candidates are produced when the
new evidence references the same spec name; closure is then decided by
the user (Rule 17: discovery is not authorization).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


# Bilingual section titles. Aligns with the same alias-tolerance pattern
# the heading validator uses for spec sections (Rule 18 / Rule 20 spirit:
# only accept explicit declarations, not natural-language guesses).
GAP_SECTION_TITLES = (
    "开放 gap",
    "未完成项",
    "Gap",
    "Open gaps",
)

# A line that starts a list item under a gap section.
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")

# A spec-name reference. Matches a spec file stem like "auth-refactor" or
# any token that looks like one (lowercase, hyphens, no extension).
_SPEC_NAME_RE = re.compile(r"\b([a-z][a-z0-9]+(?:-[a-z0-9]+)+)\b")


@dataclass
class GapCandidate:
    """A single gap candidate produced by the scan."""

    retro_path: str  # absolute path to the retro file
    retro_name: str  # basename without extension, e.g. "retro-2026-06-15"
    section_title: str  # the section heading that produced the candidate
    line_text: str  # the raw list item text
    matched_spec: str  # the spec name that matched ("" if no name match)
    spec_match: bool  # True if a spec-name match was found in the item text


def _iter_gap_sections(content: str) -> list[tuple[str, str, int]]:
    """Yield (section_title, section_body, start_line) for every recognised
    gap section in the markdown content. Bilingual titles are accepted;
    unknown titles are silently skipped (the section is treated as
    ordinary prose, not a gap declaration).
    """
    lines = content.splitlines()
    sections: list[tuple[str, str, int]] = []
    in_gap = False
    current_title = ""
    body_lines: list[str] = []
    start_line = 0
    for line in lines:
        heading_match = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if heading_match:
            if in_gap and body_lines:
                sections.append((current_title, "\n".join(body_lines), start_line))
            title = heading_match.group(1).strip()
            # Strip a parenthetical subtitle (e.g. "Gap (open items)")
            title = re.sub(r"\s*\(.+?\)\s*$", "", title).strip()
            if title in GAP_SECTION_TITLES:
                in_gap = True
                current_title = title
                body_lines = []
                start_line = lines.index(line) + 1
            else:
                in_gap = False
                current_title = ""
                body_lines = []
        elif in_gap:
            body_lines.append(line)
    if in_gap and body_lines:
        sections.append((current_title, "\n".join(body_lines), start_line))
    return sections


def _extract_spec_names(text: str) -> set[str]:
    """Return the set of spec-name-shaped tokens found in the text."""
    return set(_SPEC_NAME_RE.findall(text))


def scan_retro_gaps(
    project_root: str,
    evidence_spec: str = "",
    evidence_description: str = "",
) -> list[GapCandidate]:
    """Scan all retros under ``<project_root>/.agents/retros/`` and return
    candidate gaps that may have been closed by a new evidence entry.

    A gap is a candidate when its list item text references the same
    spec name as the new evidence (case-sensitive equality on the
    spec-file stem). Gaps that don't reference any spec name are
    NOT candidates — they need human judgement and the Skill refuses
    to claim a closure (Rule 17: discovery is not authorization).

    Returns an empty list when the retros directory does not exist,
    when no retro contains a recognised gap section, or when no gap
    references the evidence spec by name.
    """
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return []

    # Build the set of spec names that could plausibly match. We compare
    # against both the evidence_spec itself and any spec-name-shaped
    # tokens in the evidence description (e.g. an evidence line that
    # references "auth-refactor" inside a longer description).
    candidate_names: set[str] = set()
    if evidence_spec:
        candidate_names.add(evidence_spec)
        # Also strip common suffixes ("-verify", "-review") so an
        # evidence like "auth-refactor-verify" matches the spec
        # "auth-refactor".
        base = re.sub(r"-(?:verify|review|retro|test|fix)$", "", evidence_spec)
        if base and base != evidence_spec:
            candidate_names.add(base)
    candidate_names |= _extract_spec_names(evidence_description or "")

    candidates: list[GapCandidate] = []
    for entry in sorted(os.listdir(retros_dir)):
        if not entry.endswith(".md"):
            continue
        path = os.path.join(retros_dir, entry)
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        retro_name = entry[:-3]
        for section_title, body, _ in _iter_gap_sections(content):
            for raw_line in body.splitlines():
                item_match = _LIST_ITEM_RE.match(raw_line)
                if not item_match:
                    continue
                item_text = item_match.group(1).strip()
                if not item_text:
                    continue
                names_in_item = _extract_spec_names(item_text)
                matched = names_in_item & candidate_names
                # A gap is a candidate only when it references the evidence
                # spec by name. We do NOT match on plain text overlap;
                # closure judgement belongs to the user (Rule 17).
                if matched:
                    candidates.append(
                        GapCandidate(
                            retro_path=path,
                            retro_name=retro_name,
                            section_title=section_title,
                            line_text=item_text,
                            matched_spec=sorted(matched)[0],
                            spec_match=True,
                        )
                    )
    return candidates


def format_candidates(candidates: list[GapCandidate]) -> str:
    """Return a human-readable summary suitable for stdout printing."""
    if not candidates:
        return ""
    lines = [f"💡 检测到 {len(candidates)} 个 retro gap 可能被新 evidence 闭合:"]
    for idx, c in enumerate(candidates, start=1):
        lines.append(
            f"   [{idx}] {c.retro_name} § {c.section_title}: {c.line_text}"
        )
        lines.append(
            f"       → 匹配新 evidence spec: {c.matched_spec}"
        )
    lines.append("   是否补写 mini retro 闭合？(Y/n/skip-all)")
    lines.append("   Y → 我把建议的 mini 段落打印出来，由你粘贴到 retro")
    lines.append("   n → 跳过本次提示（下次新 evidence 仍会提示）")
    lines.append("   skip-all → 本项目不再提示此类候选（写入 workflow.json）")
    return "\n".join(lines)


def suggested_mini_paragraph(
    candidate: GapCandidate,
    evidence_spec: str,
) -> str:
    """Return a suggested mini retro paragraph the user can paste.

    Deliberately does NOT write to the retro file. The user reviews and
    pastes (Rule 17: discovery is not authorization).
    """
    return (
        f"## Mini retro 闭合记录\n\n"
        f"- 闭合来源: 新 evidence ({evidence_spec})\n"
        f"- 闭合目标: {candidate.line_text}\n"
        f"- 原始 retro: {candidate.retro_name} § {candidate.section_title}\n"
        f"- 状态: 由用户复核后粘贴（auto-suggested, not auto-written）\n"
    )


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Scan retros for gap candidates")
    parser.add_argument("project_root")
    parser.add_argument("--evidence-spec", default="")
    parser.add_argument("--evidence-description", default="")
    args = parser.parse_args()

    candidates = scan_retro_gaps(
        args.project_root,
        args.evidence_spec,
        args.evidence_description,
    )
    if "--json" in sys.argv:
        print(json.dumps([c.__dict__ for c in candidates], ensure_ascii=False, indent=2))
    else:
        print(format_candidates(candidates))
