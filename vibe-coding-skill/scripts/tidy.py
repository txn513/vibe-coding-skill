#!/usr/bin/env python3
from __future__ import annotations
"""Tidy .agents/ directory structure per the Directory Contract.

Detects and fixes overlapping/deprecated/unknown directories that
accumulate over time. Based on the same audit logic as doctor's
_audit_directory_structure, but with actual cleanup capability.

Usage:
    python3 tidy.py <project_root> --dry-run     # preview
    python3 tidy.py <project_root>               # execute
"""

import os
import shutil
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_tidy_actions(project_root: str) -> list[dict]:
    """Scan .agents/ for tidy actions per the Directory Contract.

    Returns a list of dicts, each with:
        action: "move" | "remove_dir"
        src: source path (relative to project_root)
        dst: destination path (relative to project_root), for "move"
        reason: human-readable explanation
    """
    agents_dir = os.path.join(project_root, ".agents")
    if not os.path.isdir(agents_dir):
        return []

    actions = []
    archive_dir = os.path.join(agents_dir, "archive")

    # 1. reports/ overlapping with retros/ → archive reports/
    reports_dir = os.path.join(agents_dir, "reports")
    retros_dir = os.path.join(agents_dir, "retros")
    if os.path.isdir(reports_dir) and os.path.isdir(retros_dir):
        report_specs = {f.replace(".md", "") for f in os.listdir(reports_dir) if f.endswith(".md")}
        retro_specs = {f.replace(".md", "") for f in os.listdir(retros_dir) if f.endswith(".md")}
        overlap = report_specs & retro_specs
        if overlap:
            actions.append({
                "action": "move",
                "src": ".agents/reports",
                "dst": ".agents/archive/reports",
                "reason": f"reports/ has {len(overlap)} specs also in retros/ (source of truth is retros/)",
            })

    # 2. Deprecated skill-upgrade-proposals/ → migrate to candidates/archive/
    proposals_dir = os.path.join(agents_dir, "skill-upgrade-proposals")
    candidates_archive = os.path.join(agents_dir, "skill-upgrade-candidates", "archive")
    if os.path.isdir(proposals_dir):
        count = len([f for f in os.listdir(proposals_dir) if f.endswith(".md")])
        if count > 0:
            actions.append({
                "action": "move",
                "src": ".agents/skill-upgrade-proposals",
                "dst": ".agents/skill-upgrade-candidates/archive/proposals-migrated",
                "reason": f"skill-upgrade-proposals/ is deprecated ({count} files), per Directory Contract",
            })

    # 3. discovery/ files older than 30 days → archive/discovery/
    discovery_dir = os.path.join(agents_dir, "discovery")
    if os.path.isdir(discovery_dir):
        now = time.time()
        old_files = []
        for f in os.listdir(discovery_dir):
            fpath = os.path.join(discovery_dir, f)
            if f.endswith(".md") and os.path.getmtime(fpath) < now - 30 * 86400:
                old_files.append(f)
        if old_files:
            actions.append({
                "action": "move_files",
                "src": ".agents/discovery",
                "dst": ".agents/archive/discovery",
                "files": old_files,
                "reason": f"discovery/ has {len(old_files)} files older than 30 days",
            })

    # 4. Unknown directories → archive/<name>/
    known_dirs = {
        "specs", "plans", "evidence", "reviews", "retros", "changelogs",
        "intents", "reports", "notes", "archive", "skill-upgrade-candidates",
        "rules", "bugs", "templates", "discovery", "skill-upgrade-proposals",
        ".vibe-review-pending", ".session-state",
    }
    for entry in sorted(os.listdir(agents_dir)):
        full = os.path.join(agents_dir, entry)
        if (os.path.isdir(full) and entry not in known_dirs
                and not entry.startswith(".")
                and entry not in ("project-upgrade-candidates",)):
            actions.append({
                "action": "move",
                "src": f".agents/{entry}",
                "dst": f".agents/archive/{entry}",
                "reason": f".agents/{entry}/ is not in the Directory Contract",
            })

    # 5. rules/proposed/ rules older than 60 days still "proposed" → flag
    proposed_dir = os.path.join(agents_dir, "rules", "proposed")
    if os.path.isdir(proposed_dir):
        now = time.time()
        stale_rules = []
        for f in os.listdir(proposed_dir):
            fpath = os.path.join(proposed_dir, f)
            if f.endswith(".md") and os.path.getmtime(fpath) < now - 60 * 86400:
                stale_rules.append(f)
        if stale_rules:
            actions.append({
                "action": "advise",
                "src": ".agents/rules/proposed",
                "reason": f"rules/proposed/ has {len(stale_rules)} rules older than 60 days still in proposed status: {', '.join(stale_rules[:5])}",
            })

    return actions


def tidy(project_root: str, dry_run: bool = True) -> list[dict]:
    """Execute or preview tidy actions.

    Returns the list of actions taken/previewed.
    """
    actions = _find_tidy_actions(project_root)
    if not actions:
        print("✅ .agents/ 目录结构整洁，无需清理。")
        return actions

    print(f"📦 发现 {len(actions)} 项清理操作:")
    print()

    for i, act in enumerate(actions, 1):
        if act["action"] == "move":
            print(f"  {i}. [move] {act['src']} → {act['dst']}")
            print(f"     原因: {act['reason']}")
        elif act["action"] == "move_files":
            print(f"  {i}. [move_files] {act['src']}/ ({len(act['files'])} files) → {act['dst']}/")
            print(f"     原因: {act['reason']}")
        elif act["action"] == "advise":
            print(f"  {i}. [advise] {act['src']}")
            print(f"     原因: {act['reason']}")
        print()

    if dry_run:
        print("ℹ️  这是 dry-run。要执行清理，运行: vibe tidy <project_root>")
        return actions

    # Execute
    executed = 0
    for act in actions:
        if act["action"] == "advise":
            # Advisory only — no file operation
            continue

        src_abs = os.path.join(project_root, act["src"])
        dst_abs = os.path.join(project_root, act["dst"])

        if not os.path.exists(src_abs):
            continue

        if act["action"] == "move":
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            if os.path.exists(dst_abs):
                # Merge: move individual files
                for item in os.listdir(src_abs):
                    src_item = os.path.join(src_abs, item)
                    dst_item = os.path.join(dst_abs, item)
                    if os.path.exists(dst_item):
                        # Skip if already exists at destination
                        continue
                    shutil.move(src_item, dst_item)
                # Remove source dir if empty
                if not os.listdir(src_abs):
                    os.rmdir(src_abs)
            else:
                shutil.move(src_abs, dst_abs)
            executed += 1

        elif act["action"] == "move_files":
            os.makedirs(dst_abs, exist_ok=True)
            for f in act["files"]:
                src_file = os.path.join(src_abs, f)
                dst_file = os.path.join(dst_abs, f)
                if os.path.exists(src_file) and not os.path.exists(dst_file):
                    shutil.move(src_file, dst_file)
            executed += 1

    print(f"✅ 已执行 {executed} 项清理操作。")
    return actions


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Tidy .agents/ directory structure per the Directory Contract",
    )
    parser.add_argument("project_root", help="项目根目录")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="预览清理操作，不实际执行 (默认: 执行)")
    args = parser.parse_args()

    root = os.path.abspath(args.project_root)
    tidy(root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
