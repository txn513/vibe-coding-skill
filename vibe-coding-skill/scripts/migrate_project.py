#!/usr/bin/env python3
"""Migrate an existing project's workflow metadata without changing project rules."""

import argparse
import os
import re

from common import atomic_write, backup_file
from workflow_state import SCHEMA_VERSION, ensure_workflow


def migrate_project(project_root: str, apply: bool = False) -> dict:
    specs_dir = os.path.join(project_root, ".agents", "specs")
    changes = []
    if os.path.exists(specs_dir):
        for filename in sorted(os.listdir(specs_dir)):
            if not filename.endswith(".md") or filename.endswith("-amendments.md"):
                continue
            path = os.path.join(specs_dir, filename)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            additions = []
            for label, default in (
                ("类型", "feature"),
                ("风险", "medium"),
                ("风险确认", "confirmed"),
                ("负责人", "待确认"),
                ("依赖", "无"),
                ("发布组", "待确认"),
            ):
                if not re.search(rf"^>\s*{label}:", content, re.MULTILINE):
                    additions.append(f"> {label}: {default}")
            if additions:
                changes.append({"file": path, "additions": additions})
                if apply:
                    backup_file(
                        path,
                        os.path.join(project_root, ".agents", "archive", "migration"),
                    )
                    metadata = re.search(r"^>\s*状态:.*$", content, re.MULTILINE)
                    insert_at = metadata.end() if metadata else 0
                    content = (
                        content[:insert_at]
                        + "\n"
                        + "\n".join(additions)
                        + content[insert_at:]
                    )
                    atomic_write(path, content)

    workflow_path = os.path.join(project_root, ".agents", "workflow.json")
    workflow_exists = os.path.exists(workflow_path)
    if apply:
        _, workflow_changed = ensure_workflow(project_root)
    else:
        workflow_changed = not workflow_exists

    print(f"Workflow schema target: {SCHEMA_VERSION}")
    print(f"Spec files requiring metadata: {len(changes)}")
    print(f"Workflow manifest change: {'yes' if workflow_changed else 'no'}")
    if not apply:
        print("Dry run only; use --apply to migrate.")
    return {"specs": changes, "workflow_changed": workflow_changed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate project workflow metadata")
    parser.add_argument("project_root")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate_project(os.path.abspath(args.project_root), args.apply)
