#!/usr/bin/env python3
from __future__ import annotations
"""Check ENFORCE comment consistency between SKILL.md and CLI scripts.

Pi Extension parses SKILL.md ENFORCE comments at runtime.
CLI scripts have hard-coded gate logic in commit.py, record_evidence.py, etc.

This module checks: for each ENFORCE rule, is there a corresponding
CLI implementation? Mismatches are warnings (not errors) — they help
catch "added ENFORCE but forgot CLI" or vice versa.
"""

import os
import re
from pathlib import Path


def _find_skill_md() -> Path:
    """Locate SKILL.md relative to this script."""
    script_dir = Path(__file__).parent.resolve()
    skill_md = script_dir.parent / "SKILL.md"
    return skill_md


def parse_enforce_rules(skill_md: Path) -> list[dict]:
    """Parse all <!-- ENFORCE: ... --> comments from SKILL.md."""
    if not skill_md.exists():
        return []
    content = skill_md.read_text(encoding="utf-8")
    rules = []
    # Match <!-- ENFORCE: key=val, key2=val2, ... -->
    pattern = re.compile(r"<!--\s*ENFORCE:\s*([^>]+)\s*-->")
    for m in pattern.finditer(content):
        raw = m[1].strip()
        pairs = [p.strip() for p in raw.split(",") if "=" in p]
        rule = {}
        for p in pairs:
            eq = p.index("=")
            rule[p[:eq].strip()] = p[eq + 1 :].strip()
        if rule.get("id") and rule.get("hook"):
            rules.append(rule)
    return rules


# ENFORCE rules that are Pi Extension only (no CLI equivalent by design).
# If a rule is NOT in this list, we expect some CLI gate implementation.
_PURE_EXTENSION_RULES = {
    # R1: agent_end gate check — purely Agent lifecycle, no CLI equivalent
    "R1",
    # R4, R5, R10, R22, R25, R30, R47, R62, R66: tool_call / before_agent_start
    # interceptors — Pi Extension hooks into Agent tool calls / startup
    "R4",
    "R5",
    "R10",
    "R22",
    "R25",
    "R30",
    "R47",
    "R60",
    "R62",
    "R66",
}

# Known CLI gate functions / markers mapped by ENFORCE id.
# Maps id → list of (script_name, expected_symbol_substring)
_KNOWN_CLI_IMPLS: dict[str, list[tuple[str, str]]] = {
    "R53": [
        ("commit.py", "review_summary"),
    ],
}


def check_cli_implementations(skill_md: Path, project_root: str | None = None) -> list[str]:
    """Return list of warnings about ENFORCE/CLI mismatches."""
    warnings: list[str] = []
    rules = parse_enforce_rules(skill_md)
    if not rules:
        return warnings

    scripts_dir = skill_md.parent / "scripts"

    for rule in rules:
        rid = rule["id"]
        if rid in _PURE_EXTENSION_RULES:
            continue

        expected = _KNOWN_CLI_IMPLS.get(rid)
        if expected is None:
            warnings.append(
                f"ENFORCE {rid} not in _PURE_EXTENSION_RULES or _KNOWN_CLI_IMPLS — "
                "add it to one of those lists in enforce_consistency_check.py"
            )
            continue

        found = False
        for script_name, symbol in expected:
            script_path = scripts_dir / script_name
            if not script_path.exists():
                warnings.append(f"ENFORCE {rid}: expected script {script_name} missing")
                continue
            content = script_path.read_text(encoding="utf-8")
            if symbol in content:
                found = True
                break

        if not found:
            warnings.append(
                f"ENFORCE {rid}: no CLI implementation found "
                f"(expected in {expected}). Did you add ENFORCE but forget CLI gate?"
            )

    return warnings


if __name__ == "__main__":
    skill_md = _find_skill_md()
    results = check_cli_implementations(skill_md)
    if results:
        print(f"ENFORCE consistency: {len(results)} warning(s)")
        for w in results:
            print(f"  ⚠️  {w}")
    else:
        print("ENFORCE consistency: OK")
