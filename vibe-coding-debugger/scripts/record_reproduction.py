#!/usr/bin/env python3
"""Record an independent bug reproduction or fix-regression evidence.

This is a thin wrapper around the core Skill's vibe.py evidence command.
It exists so a Debugger agent in a fresh Codex session can record evidence
without needing to know the core Skill's CLI structure.
"""

import os
import subprocess
import sys


def find_core_skill() -> str:
    """Locate the core Skill's scripts directory.

    Resolution order:
    1. ``$VIBE_SKILL_ROOT/scripts/vibe.py`` (explicit override)
    2. Sibling of this Skill in the same monorepo
    3. ``~/.codex/skills/vibe-coding*/scripts/vibe.py`` install
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

    # The script signature is:
    #   record_reproduction.py <project_root> <spec_name> <phase> <description> --command <argv...> --reviewer <id>
    if len(sys.argv) < 5:
        print(
            "Usage: record_reproduction.py <project_root> <spec_name> <phase> "
            "<description> --command <argv...> --reviewer <id>",
            file=sys.stderr,
        )
        sys.exit(2)

    if "--command" not in sys.argv:
        print(
            "❌ --command is required.\n"
            "   The Debugger Skill refuses to record reproduction evidence\n"
            "   without the actual command that was executed.",
            file=sys.stderr,
        )
        sys.exit(2)

    project_root, spec_name, phase, description = sys.argv[1:5]
    if phase not in ("reproduction", "fix-regression"):
        print(
            f"❌ phase must be 'reproduction' or 'fix-regression', got: {phase!r}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Forward to vibe.py evidence with --purpose mapping
    purpose = "reproduction" if phase == "reproduction" else "fix-regression"
    args = [
        sys.executable, core, "evidence",
        project_root, spec_name, "verify", "passed", description,
        "--purpose", purpose,
        *sys.argv[5:],
    ]
    sys.exit(subprocess.call(args))


if __name__ == "__main__":
    main()
