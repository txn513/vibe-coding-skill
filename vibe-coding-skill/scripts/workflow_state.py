#!/usr/bin/env python3
"""Project-local workflow schema and migration helpers."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from common import atomic_write_json

SCHEMA_VERSION = 10


def default_workflow(project_name: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_name,
        "roles": {
            "owner": "",
            "builder": "",
            "reviewer": "",
            "releaser": "",
            "observer": "",
            "override_approver": "",
        },
        "risk_profiles": {
            "low": {
                "require_plan": False,
                "require_verify": True,
                "require_review": True,
                "require_release": False,
                "require_observe": False,
                "require_role_separation": False,
                "require_clean_worktree": False,
            },
            "medium": {
                "require_plan": True,
                "require_verify": True,
                "require_review": True,
                "require_release": True,
                "require_observe": False,
                "require_role_separation": False,
                "require_clean_worktree": False,
            },
            "high": {
                "require_plan": True,
                "require_verify": True,
                "require_review": True,
                "require_release": True,
                "require_observe": True,
                "require_role_separation": True,
                "require_clean_worktree": True,
            },
        },
        "commands": {"verify": [], "verify_scope": [], "verify_full": [], "release": [], "observe": []},
        "model_tiers": {},
        "repositories": [],
        "archive": {
            "thresholds_days": {
                "evidence": 90,
                "rule_unreferenced": 180,
                "spec_untouched": 365,
            },
            "scan_paths": [
                ".agents/specs",
                ".agents/evidence",
                ".agents/rules",
            ],
            "exclude_paths": [
                ".agents/archive",
            ],
        },
        "stage_stall_sla": {
            "low_hours": 72,
            "medium_hours": 24,
            "high_hours": 8,
        },
        "risk_required_rules": {
            "high": [],
            "medium": [],
            "low": [],
        },
        "review_separation": {
            "required_for": ["high"],
        },
    }


def ensure_workflow(project_root: str) -> tuple[dict, bool]:
    root = Path(project_root)
    path = root / ".agents" / "workflow.json"
    if not path.exists():
        value = default_workflow(root.name)
        atomic_write_json(path, value)
        return value, True
    value = json.loads(path.read_text(encoding="utf-8"))
    changed = migrate(value, root.name)
    if changed:
        atomic_write_json(path, value)
    return value, changed


def migrate(value: dict, project_name: str) -> bool:
    changed = False
    defaults = default_workflow(project_name)
    for key in (
        "project_id", "roles", "risk_profiles", "commands", "model_tiers",
        "repositories", "archive", "stage_stall_sla", "risk_required_rules",
        "review_separation",
    ):
        if key not in value:
            value[key] = defaults[key]
            changed = True
    for role, default in defaults["roles"].items():
        if role not in value["roles"]:
            value["roles"][role] = default
            changed = True
    for phase, default in defaults["commands"].items():
        if phase not in value["commands"]:
            value["commands"][phase] = default
            changed = True
    for risk, profile in defaults["risk_profiles"].items():
        if risk not in value["risk_profiles"]:
            value["risk_profiles"][risk] = profile
            changed = True
        else:
            for key, default in profile.items():
                if key not in value["risk_profiles"][risk]:
                    value["risk_profiles"][risk][key] = default
                    changed = True
    if value.get("schema_version") != SCHEMA_VERSION:
        value["schema_version"] = SCHEMA_VERSION
        changed = True
    return changed


def configured_commands(workflow: dict, phase: str) -> list[list[str]]:
    """Normalize project commands to argv lists without invoking a shell."""
    commands = workflow.get("commands", {}).get(phase, [])
    normalized = []
    for command in commands if isinstance(commands, list) else []:
        if isinstance(command, str):
            argv = shlex.split(command)
        elif isinstance(command, list) and all(isinstance(part, str) for part in command):
            argv = command
        elif isinstance(command, dict) and isinstance(command.get("command"), list) and all(isinstance(part, str) for part in command["command"]):
            argv = command["command"]
        else:
            continue
        if argv:
            normalized.append(argv)
    return normalized


def dependency_cycles(project_root: str) -> list[list[str]]:
    """Return dependency cycles found among project specs."""
    specs_dir = Path(project_root) / ".agents" / "specs"
    graph: dict[str, list[str]] = {}
    if specs_dir.exists():
        for path in specs_dir.glob("*.md"):
            if path.name.endswith("-amendments.md"):
                continue
            graph[path.stem] = spec_metadata(path.read_text(encoding="utf-8"))["dependencies"]

    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited or node not in graph:
            return
        visiting.append(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.pop()
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def spec_metadata(content: str) -> dict:
    import re

    def field(name: str, default: str = "") -> str:
        # Take first token only, filtering out parenthetical annotations
        # e.g. "> 风险: low（CSS 修复）" → "low", not "low（CSS 修复）"
        match = re.search(rf"^>\s*{re.escape(name)}:\s*(\S+)", content, re.MULTILINE)
        return match.group(1).strip().rstrip("*").rstrip(":") if match else default

    dependencies = []
    for item in field("依赖", "无").replace("，", ",").split(","):
        item = item.strip()
        if not item or item == "无":
            continue
        # Trim parenthetical status annotations: "foo (done)" → "foo"
        m = re.match(r"^(\S+?)\s*[（(].*$", item)
        if m:
            item = m.group(1)
        dependencies.append(item)
    return {
        "risk": field("风险", "medium"),
        "risk_confirmation": field("风险确认", "confirmed"),
        "owner": field("负责人", ""),
        "dependencies": dependencies,
        "release": field("发布组", ""),
        "spec_type": field("类型", "feature"),
        "regression_from": field("回归来源", ""),
    }


def spec_last_touched(content):
    import re
    from datetime import datetime, timezone
    m = re.search(r"^>\s*状态:\s*\S+(?:\s*\|\s*创建:\s*[^|]+)?\s*\|\s*更新:\s*(.+?)\s*$", content, re.MULTILINE)
    if not m: return None
    try: return datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError: return None

def risk_profile(project_root: str, spec_content: str) -> dict:
    workflow, _ = ensure_workflow(project_root)
    risk = spec_metadata(spec_content)["risk"]
    return workflow["risk_profiles"].get(risk, workflow["risk_profiles"]["medium"])
