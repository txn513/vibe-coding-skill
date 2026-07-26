#!/usr/bin/env python3
from __future__ import annotations
"""Tidy .agents/ and docs/ directory structure per Directory Contract.

Detects and fixes overlapping/deprecated/unknown directories that
accumulate over time. Based on the same audit logic as doctor's
_audit_directory_structure, but with actual cleanup capability.

Usage:
    python3 tidy.py <project_root> --dry-run     # preview
    python3 tidy.py <project_root>               # execute
"""

import argparse
import datetime as _dt
import os
import re
import shutil
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_tidy_actions(project_root: str) -> list[dict]:
    """Scan .agents/ and docs/ for tidy actions per Directory Contract."""
    actions = []
    agents_dir = os.path.join(project_root, ".agents")
    has_agents = os.path.isdir(agents_dir)

    if has_agents:
        archive_dir = os.path.join(agents_dir, "archive")

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

        proposals_dir = os.path.join(agents_dir, "skill-upgrade-proposals")
        if os.path.isdir(proposals_dir):
            count = len([f for f in os.listdir(proposals_dir) if f.endswith(".md")])
            if count > 0:
                actions.append({
                    "action": "move",
                    "src": ".agents/skill-upgrade-proposals",
                    "dst": ".agents/skill-upgrade-candidates/archive/proposals-migrated",
                    "reason": f"skill-upgrade-proposals/ is deprecated ({count} files), per Directory Contract",
                })

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

    # === docs/ tidy actions (R-D-87) ===
    docs_dir = os.path.join(project_root, "docs")
    if not os.path.isdir(docs_dir):
        actions.append({
            "action": "advise",
            "src": "docs/",
            "reason": "docs/ directory missing - run `vibe docs-init <project_root> --apply` (R-D-87)",
        })
    else:
        if not os.path.exists(os.path.join(docs_dir, "README.md")):
            actions.append({
                "action": "advise",
                "src": "docs/README.md",
                "reason": "docs/README.md missing - re-run `vibe docs-init` (idempotent, fills missing only)",
            })

        now_date = _dt.datetime.now()
        for root, _dirs, files in os.walk(docs_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8") as fp:
                        head = fp.read(2000)
                except OSError:
                    continue
                lu = re.search(r"^last_updated:\s*(\d{4}-\d{2}-\d{2})", head, re.MULTILINE)
                if not lu:
                    continue
                try:
                    lu_date = _dt.datetime.strptime(lu.group(1), "%Y-%m-%d")
                except ValueError:
                    continue
                age_days = (now_date - lu_date).days
                if age_days > 30:
                    rel = os.path.relpath(fpath, project_root)
                    actions.append({
                        "action": "advise",
                        "src": rel,
                        "reason": f"docs/ file last_updated {age_days} days ago (may be stale)",
                    })

        readme_path = os.path.join(docs_dir, "README.md")
        if os.path.exists(readme_path):
            try:
                with open(readme_path, encoding="utf-8") as fp:
                    readme_content = fp.read()
                linked = set(re.findall(r"\[([^\]]+\.md)\]", readme_content))
                for root, _dirs, files in os.walk(docs_dir):
                    for fname in files:
                        if not fname.endswith(".md"):
                            continue
                        rel = os.path.relpath(os.path.join(root, fname), docs_dir)
                        if rel == "README.md":
                            continue
                        if rel not in linked and fname not in linked:
                            actions.append({
                                "action": "advise",
                                "src": f"docs/{rel}",
                                "reason": "orphan doc - not linked from docs/README.md index",
                            })
            except OSError:
                pass

    reserved_root_md = {"README.md", "LICENSE.md", "LICENSE", "AGENTS.md", "CHANGELOG.md"}
    for entry in sorted(os.listdir(project_root)):
        if not entry.endswith(".md"):
            continue
        if entry in reserved_root_md:
            continue
        if os.path.isfile(os.path.join(project_root, entry)):
            actions.append({
                "action": "advise",
                "src": entry,
                "reason": f"root-level .md ({entry}) - consider moving to docs/ or .agents/",
            })

    return actions


def tidy(project_root: str, dry_run: bool = True) -> list[dict]:
    actions = _find_tidy_actions(project_root)
    if not actions:
        print("OK .agents/ and docs/ structure clean.")
        return actions

    print(f"Found {len(actions)} tidy actions:")
    print()

    for i, act in enumerate(actions, 1):
        if act["action"] == "move":
            print(f"  {i}. [move] {act['src']} -> {act['dst']}")
            print(f"     reason: {act['reason']}")
        elif act["action"] == "move_files":
            print(f"  {i}. [move_files] {act['src']}/ ({len(act['files'])} files) -> {act['dst']}/")
            print(f"     reason: {act['reason']}")
        elif act["action"] == "advise":
            print(f"  {i}. [advise] {act['src']}")
            print(f"     reason: {act['reason']}")
        print()

    if dry_run:
        print("dry-run. Execute: vibe tidy <project_root>")
        return actions

    executed = 0
    for act in actions:
        if act["action"] == "advise":
            continue

        src_abs = os.path.join(project_root, act["src"])
        dst_abs = os.path.join(project_root, act["dst"])

        if not os.path.exists(src_abs):
            continue

        if act["action"] == "move":
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            if os.path.exists(dst_abs):
                for item in os.listdir(src_abs):
                    src_item = os.path.join(src_abs, item)
                    dst_item = os.path.join(dst_abs, item)
                    if os.path.exists(dst_item):
                        continue
                    shutil.move(src_item, dst_item)
                if not os.listdir(src_abs):
                    os.rmdir(src_abs)
            else:
                shutil.move(src_abs, dst_abs)
            executed += 1

        elif act["action"] == "move_files":
            os.makedirs(dst_abs, exist_ok=True)
            files = act.get("files", [])
            for f in files:
                src_item = os.path.join(src_abs, f)
                dst_item = os.path.join(dst_abs, f)
                if os.path.exists(src_item) and not os.path.exists(dst_item):
                    shutil.move(src_item, dst_item)
            executed += 1

    print(f"Executed {executed} actions.")
    print("Note: 'advise' items need human judgment, not executed.")
    return actions


def main() -> None:
    p = argparse.ArgumentParser(description="Tidy .agents/ and docs/ directory structure")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="preview only (default)")
    p.add_argument("--apply", action="store_true", help="execute")
    args = p.parse_args()
    tidy(args.project_root, dry_run=not args.apply)


if __name__ == "__main__":
    main()
