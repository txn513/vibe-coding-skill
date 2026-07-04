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





# --- Action item state machine (Rule 60) ---
# A retro "行动项" list item uses one of four states:
#   `- [ ] text`                 open (default; subject to stagnation audit)
#   `- [active: <rule-id>] text` promoted into a rule
#   `- [deferred: <reason>] text` parked with explicit rationale
#   `- [superseded: <id>] text`   replaced by later work
# Items persisting as `[ ]` across multiple retro cycles signal forgotten
# work. The state prefix is the only signal — the surrounding text is freeform.

_ACTION_ITEM_RE = re.compile(
    r"^\s*[-*]\s+"
    r"\[(?P<state>\s|active:|deferred:|superseded:)"
    r"(?P<rest>[^\]]*)\]"
    r"(?P<text>.*)$"
)
_OPEN_STATE = " "  # the literal space inside `[ ]`


@dataclass
class ActionItem:
    """A single retro action item with state and provenance."""

    retro_path: str
    retro_name: str
    state: str  # "open" | "active:<id>" | "deferred:<reason>" | "superseded:<id>"
    state_payload: str  # the part after the colon (or "" for open)
    text: str  # the freeform text after the bracket
    raw_line: str


def _iter_action_items(content: str) -> list[tuple[str, str]]:
    """Yield (state, text) for every action item line found in `content`.

    Scans the whole document for list items matching the action-item
    regex — does not require a specific heading. This mirrors how
    project retros currently structure action items under a 行动项
    section, but tolerates minor heading variations.
    """
    items: list[tuple[str, str]] = []
    for line in content.splitlines():
        m = _ACTION_ITEM_RE.match(line)
        if not m:
            continue
        state_token = m.group("state")
        payload = m.group("rest").strip()
        text = m.group("text").strip()
        if state_token == _OPEN_STATE:
            state = "open"
        elif state_token == "active:":
            state = "active"
        elif state_token == "deferred:":
            state = "deferred"
        elif state_token == "superseded:":
            state = "superseded"
        else:
            continue
        items.append((state, text))
    return items


def scan_stale_action_items(
    project_root: str,
    max_cycles: int = 2,
) -> list[ActionItem]:
    """Return retro action items still in `open` state that have not
    been updated since the most recent `max_cycles` retro files.

    "Not updated" is measured by ordering retro files by their on-disk
    mtime (newest first) and checking whether the retro file containing
    the open item is older than the `max_cycles`th newest retro file.
    This intentionally uses relative project cadence, not wall-clock
    deadlines — projects shipping 5 specs/day and 1 spec/week both
    get an accurate "this is forgotten" signal.
    """
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return []

    # Order retros by mtime, newest first
    retro_paths: list[tuple[float, str]] = []
    for entry in os.listdir(retros_dir):
        if not entry.endswith(".md"):
            continue
        path = os.path.join(retros_dir, entry)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        retro_paths.append((mtime, path))
    retro_paths.sort(reverse=True)

    if not retro_paths:
        return []

    # Threshold: any retro older than the `max_cycles`th newest is "stale".
    if len(retro_paths) <= max_cycles:
        # Not enough retros to establish a "stale" cutoff. Treat all
        # open items as advisory only — return them with state="open"
        # but the caller should decide what to do with so little data.
        threshold = float("inf")
    else:
        threshold = retro_paths[max_cycles][0]

    stale: list[ActionItem] = []
    for mtime, path in retro_paths:
        if mtime > threshold:
            # Recent retro — items here are too new to call stale
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        retro_name = os.path.basename(path)[:-3]
        for state, text in _iter_action_items(content):
            if state == "open" and text:
                # Parse the original line for richer reporting
                raw_line = next(
                    (ln for ln in content.splitlines()
                     if _ACTION_ITEM_RE.match(ln)
                     and _ACTION_ITEM_RE.match(ln).group("text").strip() == text),
                    "",
                )
                m = _ACTION_ITEM_RE.match(raw_line) if raw_line else None
                payload = m.group("rest").strip() if m else ""
                stale.append(
                    ActionItem(
                        retro_path=path,
                        retro_name=retro_name,
                        state="open",
                        state_payload=payload,
                        text=text,
                        raw_line=raw_line,
                    )
                )
    return stale


def format_stale_items(items: list[ActionItem]) -> str:
    """Human-readable summary for stdout printing."""
    if not items:
        return "✅ No stale retro action items.\n"
    lines = [f"⚠️  发现 {len(items)} 个停留在 `[ ]` 状态的 retro 行动项:"]
    for idx, item in enumerate(items, start=1):
        lines.append(f"   [{idx}] {item.retro_name}: {item.text}")
        lines.append(
            "       → 升级为 [active: <rule-id>] / [deferred: <reason>] / [superseded: <id>]"
        )
    lines.append("")
    lines.append("Rule 60 要求: 行动项必须达到 terminal state，不可停留在 `[ ]`。")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Scan retros for gap candidates / stale action items (Rule 60)"
    )
    parser.add_argument("project_root")
    parser.add_argument("--evidence-spec", default="")
    parser.add_argument("--evidence-description", default="")
    parser.add_argument(
        "--audit-stale", action="store_true",
        help="List retro action items still in `[ ]` state past their project\'s "
             "natural review cadence (Rule 60).",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=2,
        help="Number of recent retro cycles used as the staleness threshold "
             "(default 2). Items in retros older than the Nth most recent "
             "retro are considered stale.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.audit_stale:
        items = scan_stale_action_items(args.project_root, max_cycles=args.max_cycles)
        if args.json:
            print(json.dumps([i.__dict__ for i in items], ensure_ascii=False, indent=2))
        else:
            print(format_stale_items(items))
    else:
        candidates = scan_retro_gaps(
            args.project_root,
            args.evidence_spec,
            args.evidence_description,
        )
        if args.json:
            print(json.dumps([c.__dict__ for c in candidates], ensure_ascii=False, indent=2))
        else:
            print(format_candidates(candidates))
