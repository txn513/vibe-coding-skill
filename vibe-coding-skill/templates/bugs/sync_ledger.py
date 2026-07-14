#!/usr/bin/env python3
"""Bug ledger sync script — template for vibe-coding projects.

Usage:
    python3 .agents/bugs/sync_ledger.py [--apply]

This script keeps BUG_INDEX.md in sync with CHANGELOG.md and RN_MAPPING.md.
Copy this template into your project and customize the parse logic for your
data formats.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def parse_changelog(changelog_path: Path) -> list[dict]:
    """Parse CHANGELOG.md, return list of {bug_id, status, date}."""
    entries = []
    if not changelog_path.exists():
        return entries
    content = changelog_path.read_text(encoding="utf-8")
    # Example: "- BUG-123: FIXED (2026-07-14)"
    for m in re.finditer(r"- (BUG-\d+): (\w+) \(([^)]+)\)", content):
        entries.append({
            "bug_id": m.group(1),
            "status": m.group(2),
            "date": m.group(3),
        })
    return entries


def parse_mapping(mapping_path: Path) -> dict[str, str]:
    """Parse RN_TO_BUGN_MAPPING.md, return {rn: bugn}."""
    mapping = {}
    if not mapping_path.exists():
        return mapping
    content = mapping_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        # Example: "RN-45 → BUG-123"
        m = re.match(r"(\S+)\s*→\s*(BUG-\d+)", line)
        if m:
            mapping[m.group(1)] = m.group(2)
    return mapping


def sync_index(index_path: Path, changelog_entries: list[dict], dry_run: bool = True) -> int:
    """Sync BUG_INDEX.md with changelog entries. Returns count of changes."""
    if not index_path.exists():
        print(f"INDEX not found: {index_path}")
        return 0

    content = index_path.read_text(encoding="utf-8")
    changes = 0

    for entry in changelog_entries:
        bug_id = entry["bug_id"]
        new_status = entry["status"]
        # Replace "| PENDING |" or "| OPEN |" with new status
        pattern = rf"(\\| {re.escape(bug_id)} \\|).*?(\\| OPEN| PENDING \\|)"
        if re.search(pattern, content):
            if not dry_run:
                content = re.sub(pattern, rf"\\1 {new_status} ", content, count=1)
            changes += 1
            print(f"  {'[DRY]' if dry_run else ''} {bug_id}: → {new_status}")

    if changes > 0 and not dry_run:
        index_path.write_text(content, encoding="utf-8")
        print(f"✅ BUG_INDEX.md updated: {changes} entries")
    elif changes == 0:
        print("ℹ️  No sync needed — INDEX already consistent")
    else:
        print(f"[DRY RUN] Would update {changes} entries")

    return changes


def main():
    parser = argparse.ArgumentParser(description="Sync bug ledger")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.parent
    bugs_dir = project_root / ".agents" / "bugs"

    changelog_path = bugs_dir / "CHANGELOG.md"
    mapping_path = bugs_dir / "RN_MAPPING.md"
    index_path = bugs_dir / "INDEX.md"

    changelog_entries = parse_changelog(changelog_path)
    mapping = parse_mapping(mapping_path)

    print(f"🔄 Bug ledger sync (dry={'no' if args.apply else 'yes'})")
    print(f"   CHANGELOG entries: {len(changelog_entries)}")
    print(f"   RN mappings: {len(mapping)}")

    changes = sync_index(index_path, changelog_entries, dry_run=not args.apply)
    return 0 if changes >= 0 else 1


if __name__ == "__main__":
    exit(main())
