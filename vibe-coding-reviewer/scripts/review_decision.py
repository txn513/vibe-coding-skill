#!/usr/bin/env python3
"""Record an independent review decision for a Vibe Coding spec.

This is a thin wrapper around the core Skill's vibe.py review-decision.
It exists so a Reviewer agent in a fresh Codex session can record a
decision without needing to know the core Skill's CLI structure.
"""

import os
import subprocess
import sys


def find_core_skill() -> str:
    """Locate the core Skill's scripts directory.

    Resolution order:
    1. ``$VIBE_SKILL_ROOT/scripts/vibe.py`` (explicit override, matches vibe-cli)
    2. Sibling of this Skill in the same monorepo (``../vibe-coding-skill``
       or ``../vibe-coding``).
    3. ``~/.codex/skills/vibe-coding-skill/scripts/vibe.py`` and the
       installed copy under ``vibe-coding``.
    """
    env_root = os.environ.get("VIBE_SKILL_ROOT", "").strip()
    candidates: list[str] = []
    if env_root:
        candidates.append(os.path.join(env_root, "scripts", "vibe.py"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates += [
        os.path.join(os.path.dirname(here), "vibe-coding-skill", "scripts", "vibe.py"),
        os.path.join(os.path.dirname(here), "vibe-coding", "scripts", "vibe.py"),
        os.path.expanduser("~/.codex/skills/vibe-coding-skill/scripts/vibe.py"),
        os.path.expanduser("~/.codex/skills/vibe-coding/scripts/vibe.py"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def main() -> None:
    core = find_core_skill()
    if not core:
        print(
            "❌ Core Vibe Coding Skill not found.\n"
            "   Install it via: codex install-skill <path-to-vibe-coding-skill>\n"
            "   or clone the suite to ~/vibe-coding-suite/.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Forward all args to the core's review-decision subcommand
    args = [sys.executable, core, "review-decision", *sys.argv[1:]]
    sys.exit(subprocess.call(args))


if __name__ == "__main__":
    main()
