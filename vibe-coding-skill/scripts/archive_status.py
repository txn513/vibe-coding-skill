#!/usr/bin/env python3
"""Identify and archive stale artifacts under .agents/.

Scans `.agents/specs`, `.agents/evidence`, and `.agents/rules` (or whatever
the project configures) and reports files that are unlikely to still be
needed. Default thresholds:

- evidence: verify/observe/release evidence for released/done specs whose
  mtime is older than `archive.thresholds_days.evidence` (default 90).
- rule_unreferenced: rule files older than `archive.thresholds_days.rule_unreferenced`
  (default 180) whose filename stem is not referenced by any spec, plan,
  retro, or design document under `.agents/`.
- spec_untouched: spec files for cancelled or superseded specs whose
  frontmatter `更新:` field is older than `archive.thresholds_days.spec_untouched`
  (default 365).

The script is deliberately read-mostly. The default mode is dry-run: it
prints what would be archived and where. `--apply` actually moves the
files into `.agents/archive/<utc-timestamp>/<original-relative-path>`.

The script never recurses into `.agents/archive/` itself. It also honours
`archive.exclude_paths` from `workflow.json` so projects can opt out of
specific directories without touching the script.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timezone

from common import atomic_write_json
from workflow_state import ensure_workflow, spec_last_touched, spec_metadata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_compact() -> str:
    return _now_utc().strftime("%Y%m%dT%H%M%SZ")


def _file_age_days(path: str, now: datetime) -> int:
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return max(0, (now - mtime).days)


def _archive_root(project_root: str, now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(project_root, ".agents", "archive", stamp)


def _is_excluded(rel_path: str, exclude_paths: list[str]) -> bool:
    for excluded in exclude_paths:
        excluded = excluded.strip().rstrip("/")
        if not excluded:
            continue
        if rel_path == excluded or rel_path.startswith(excluded + "/"):
            return True
    return False


def _scan_targets(project_root: str, scan_paths: list[str], exclude_paths: list[str]) -> list[str]:
    """Return absolute paths of files inside scan_paths, minus exclude_paths."""
    targets: list[str] = []
    for scan in scan_paths:
        scan = scan.strip().rstrip("/")
        if not scan:
            continue
        base = os.path.join(project_root, scan)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, project_root)
            if _is_excluded(rel_dir, exclude_paths):
                dirnames[:] = []
                continue
            for filename in filenames:
                rel_file = os.path.join(rel_dir, filename)
                if _is_excluded(rel_file, exclude_paths):
                    continue
                targets.append(os.path.join(project_root, rel_file))
    return targets


def _rule_stem_referenced(project_root: str, rule_stem: str) -> bool:
    """A rule is 'referenced' if its stem appears in any spec / plan / retro / design body."""
    patterns = [
        os.path.join(project_root, ".agents", "specs", "*.md"),
        os.path.join(project_root, ".agents", "plans", "*.md"),
        os.path.join(project_root, ".agents", "retros", "*.md"),
        os.path.join(project_root, ".agents", "designs", "*.md"),
        os.path.join(project_root, ".agents", "intents", "*.md"),
    ]
    needle = re.escape(rule_stem)
    for pattern in patterns:
        import glob as _glob
        for path in _glob.glob(pattern):
            try:
                with open(path, encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            if re.search(needle, content):
                return True
    return False


def _spec_status_done_or_superseded(spec_path: str) -> tuple[str, datetime | None]:
    """Return (status, last_touched) for a spec file; ('unknown', None) if unparseable."""
    try:
        with open(spec_path, encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return ("unknown", None)
    meta = spec_metadata(content)
    touched = spec_last_touched(content)
    status_match = re.search(r"^>\s*状态:\s*(\S+)", content, re.MULTILINE)
    status = status_match.group(1).strip() if status_match else "draft"
    # spec_metadata doesn't expose status; just return what we found
    return (status, touched)


def _stale_evidence(project_root: str, thresholds: dict, now: datetime) -> list[dict]:
    threshold = int(thresholds.get("evidence", 90))
    findings: list[dict] = []
    evidence_root = os.path.join(project_root, ".agents", "evidence")
    if not os.path.isdir(evidence_root):
        return findings
    for spec_dir in os.listdir(evidence_root):
        spec_path = os.path.join(project_root, ".agents", "specs", f"{spec_dir}.md")
        status, _ = _spec_status_done_or_superseded(spec_path) if os.path.exists(spec_path) else ("unknown", None)
        if status not in {"released", "done", "superseded", "cancelled"}:
            continue
        for dirpath, _, filenames in os.walk(os.path.join(evidence_root, spec_dir)):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                age = _file_age_days(full, now)
                if age >= threshold:
                    findings.append({
                        "kind": "evidence",
                        "path": os.path.relpath(full, project_root),
                        "age_days": age,
                        "threshold_days": threshold,
                        "spec": spec_dir,
                        "reason": f"evidence for {status} spec, untouched {age} days",
                    })
    return findings


def _stale_rules(project_root: str, thresholds: dict, now: datetime) -> list[dict]:
    threshold = int(thresholds.get("rule_unreferenced", 180))
    findings: list[dict] = []
    rules_root = os.path.join(project_root, ".agents", "rules")
    if not os.path.isdir(rules_root):
        return findings
    for filename in os.listdir(rules_root):
        if not filename.endswith(".md"):
            continue
        full = os.path.join(rules_root, filename)
        if not os.path.isfile(full):
            continue
        age = _file_age_days(full, now)
        if age < threshold:
            continue
        stem = filename[:-3]
        if _rule_stem_referenced(project_root, stem):
            continue
        findings.append({
            "kind": "rule_unreferenced",
            "path": os.path.relpath(full, project_root),
            "age_days": age,
            "threshold_days": threshold,
            "reason": f"rule '{stem}' untouched {age} days and not referenced",
        })
    return findings


def _stale_specs(project_root: str, thresholds: dict, now: datetime) -> list[dict]:
    threshold = int(thresholds.get("spec_untouched", 365))
    findings: list[dict] = []
    specs_root = os.path.join(project_root, ".agents", "specs")
    if not os.path.isdir(specs_root):
        return findings
    for filename in os.listdir(specs_root):
        if not filename.endswith(".md"):
            continue
        full = os.path.join(specs_root, filename)
        if not os.path.isfile(full):
            continue
        status, touched = _spec_status_done_or_superseded(full)
        if status not in {"cancelled", "superseded"}:
            continue
        # Prefer frontmatter `更新:` field; fall back to mtime.
        if touched is not None:
            age = max(0, (now - touched).days)
        else:
            age = _file_age_days(full, now)
        if age >= threshold:
            findings.append({
                "kind": "spec_untouched",
                "path": os.path.relpath(full, project_root),
                "age_days": age,
                "threshold_days": threshold,
                "reason": f"{status} spec untouched {age} days",
            })
    return findings


def find_stale(project_root: str) -> list[dict]:
    """Return the list of stale artifacts for a project."""
    workflow, _ = ensure_workflow(project_root)
    archive_cfg = workflow.get("archive") or {}
    thresholds = archive_cfg.get("thresholds_days") or {}
    scan_paths = archive_cfg.get("scan_paths") or [".agents/specs", ".agents/evidence", ".agents/rules"]
    exclude_paths = archive_cfg.get("exclude_paths") or [".agents/archive"]
    now = _now_utc()

    # Touch scan_paths / exclude_paths validation (do not silently drop typos)
    _ = _scan_targets(project_root, scan_paths, exclude_paths)

    findings: list[dict] = []
    findings.extend(_stale_evidence(project_root, thresholds, now))
    findings.extend(_stale_rules(project_root, thresholds, now))
    findings.extend(_stale_specs(project_root, thresholds, now))
    return findings


def archive(project_root: str, findings: list[dict], now: datetime | None = None) -> list[str]:
    """Move each finding.path into `.agents/archive/<stamp>/<rel>` and write a manifest."""
    now = now or _now_utc()
    archive_dir = _archive_root(project_root, now)
    os.makedirs(archive_dir, exist_ok=True)
    manifest: list[dict] = []
    moved: list[str] = []
    for finding in findings:
        rel = finding["path"]
        source = os.path.join(project_root, rel)
        if not os.path.exists(source):
            continue
        dest = os.path.join(archive_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(source, dest)
        moved.append(rel)
        manifest.append({**finding, "archived_to": os.path.relpath(dest, project_root)})
    if manifest:
        atomic_write_json(
            os.path.join(archive_dir, "manifest.json"),
            {"archived_at": now.isoformat(), "items": manifest},
        )
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description="Find and archive stale .agents/ artifacts")
    parser.add_argument("project_root")
    parser.add_argument("--apply", action="store_true", help="Actually move files; default is dry-run")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    findings = find_stale(args.project_root)

    if args.json:
        import json as _json
        print(_json.dumps({"stale": findings, "applied": False}, ensure_ascii=False, indent=2))
        if not args.apply:
            return 0
    if not findings:
        print("✅ 没有发现陈旧文件 (.agents/archive 不会被扫描)")
        return 0

    print(f"📦 发现 {len(findings)} 个陈旧文件:")
    for finding in findings:
        print(f"   - [{finding['kind']}] {finding['path']}  ({finding['age_days']}d / 阈值 {finding['threshold_days']}d)")
        print(f"       {finding['reason']}")

    if not args.apply:
        print("\nℹ️  这是 dry-run。要执行归档，运行: vibe archive-stale <project_root> --apply")
        return 0

    moved = archive(args.project_root, findings)
    print(f"\n✅ 已归档 {len(moved)} 个文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
