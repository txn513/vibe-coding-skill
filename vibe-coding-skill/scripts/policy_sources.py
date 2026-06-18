#!/usr/bin/env python3
"""Inventory project policy sources and track explicit governance conflicts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import atomic_write, atomic_write_json


POLICY_SCHEMA_VERSION = 1
MANIFEST_PATH = Path(".agents/policy-sources.json")
DIFFERENCE_REPORT_PATH = Path(".agents/policy-differences.md")
CONFIRMATION_DRAFT_PATH = Path(".agents/policy-confirmations.md")
SEVERITIES = {"low", "medium", "high"}
CONFLICT_STATUSES = {"open", "resolved", "accepted"}

KNOWN_SOURCES = (
    ("agents-md", "AGENTS.md", "project", 300),
    ("contributing", "CONTRIBUTING.md", "project", 300),
    ("readme", "README.md", "project", 250),
    ("claude-md", "CLAUDE.md", "project", 300),
    ("gemini-md", "GEMINI.md", "project", 300),
    ("cursor-rules", ".cursor/rules", "project", 300),
    ("cursor-legacy", ".cursorrules", "project", 300),
    ("copilot-instructions", ".github/copilot-instructions.md", "project", 300),
    ("ci-workflows", ".github/workflows", "project", 300),
    ("makefile", "Makefile", "project", 250),
    ("package-json", "package.json", "project", 250),
    ("pyproject", "pyproject.toml", "project", 250),
)


def manifest_file(project_root: Path) -> Path:
    return project_root.resolve() / MANIFEST_PATH


def difference_report_file(project_root: Path) -> Path:
    return project_root.resolve() / DIFFERENCE_REPORT_PATH


def confirmation_draft_file(project_root: Path) -> Path:
    return project_root.resolve() / CONFIRMATION_DRAFT_PATH


def empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "precedence": [
            "external-mandate",
            "project",
            "project-local",
            "skill-default",
        ],
        "sources": [],
        "conflicts": [],
    }


def _display_name(source_id: str) -> str:
    names = {
        "agents-md": "AGENTS.md",
        "contributing": "CONTRIBUTING.md",
        "readme": "README.md",
        "claude-md": "CLAUDE.md",
        "gemini-md": "GEMINI.md",
        "cursor-rules": ".cursor/rules",
        "cursor-legacy": ".cursorrules",
        "copilot-instructions": ".github/copilot-instructions.md",
        "ci-workflows": ".github/workflows",
        "makefile": "Makefile",
        "package-json": "package.json",
        "pyproject": "pyproject.toml",
        "skill-defaults": "Skill defaults",
    }
    return names.get(source_id, source_id)


def _review_note(source_id: str) -> str:
    notes = {
        "contributing": "确认其中的提交、评审、分支或发布要求是否应视为强制规范。",
        "readme": "确认 README 中的开发和运行方式是否仍代表当前项目事实。",
        "claude-md": "确认这份 AI 协作规则是否仍有效，以及与 AGENTS.md 的优先级关系。",
        "gemini-md": "确认这份 AI 协作规则是否仍有效，以及与 AGENTS.md 的优先级关系。",
        "cursor-rules": "确认 Cursor 规则是否仍有效，以及哪些内容需要进入项目治理。",
        "cursor-legacy": "确认旧版 Cursor 规则是否仍在生效，是否需要迁移或废弃。",
        "copilot-instructions": "确认 Copilot 指令是否仍有效，以及是否包含需要提升优先级的限制。",
        "ci-workflows": "确认哪些 CI job 代表强制门禁，以及失败是否应阻断 verify/release。",
        "makefile": "确认 Makefile 中哪些入口应映射为 verify、release 或 observe 命令。",
        "package-json": "确认 package.json scripts 中哪些入口应映射为 verify、release 或 observe 命令。",
        "pyproject": "确认 pyproject.toml 中哪些测试、构建或工具入口应进入工作流配置。",
    }
    return notes.get(source_id, "确认这份来源中的项目约束是否需要进入治理上下文。")


def _review_guidance(source_id: str) -> dict[str, str]:
    workflow_sources = {"ci-workflows", "makefile", "package-json", "pyproject"}
    project_rule_sources = {
        "contributing",
        "readme",
        "claude-md",
        "gemini-md",
        "cursor-rules",
        "cursor-legacy",
        "copilot-instructions",
    }
    if source_id in workflow_sources:
        return {
            "action": f"确认 {_display_name(source_id)} 并同步到 workflow.json",
            "target": ".agents/workflow.json",
            "reason": "这类来源通常定义验证、发布或观察门禁，应该先落到工作流配置。",
            "fallback_action": "若与现有工作流配置不一致，记录 explicit conflict",
        }
    if source_id in project_rule_sources:
        return {
            "action": f"确认 {_display_name(source_id)} 并沉淀为项目规则",
            "target": ".agents/rules/*.md 或 AGENTS.md",
            "reason": "这类来源通常是协作约束、开发约定或本地事实，应该先落到项目规则层。",
            "fallback_action": "若与现有项目规则冲突，记录 explicit conflict",
        }
    return {
        "action": f"确认 {_display_name(source_id)} 的治理归属",
        "target": "待判断",
        "reason": "先判断它更适合成为工作流配置、项目规则，还是显式冲突。",
        "fallback_action": "先记录治理结论，再决定落点",
    }


def _candidate_snippet(item: dict[str, Any]) -> tuple[str, str]:
    source_id = item["source_id"]
    if item["target"] == ".agents/workflow.json":
        snippet = {
            "commands": {
                "verify": [
                    {
                        "name": f"{source_id}-verify",
                        "command": ["pending-command"],
                    }
                ]
            }
        }
        return "workflow.json patch", json.dumps(snippet, ensure_ascii=False, indent=2)
    if item["target"] == ".agents/rules/*.md 或 AGENTS.md":
        slug = re.sub(r"[^a-z0-9]+", "-", source_id.lower()).strip("-")
        snippet = "\n".join(
            [
                f"# {item['title']}",
                "",
                "> 状态: proposed",
                "",
                "## Rule",
                "",
                f"- Source: {item['path']}",
                "- Pending project-specific instruction goes here.",
                "",
                "## Adoption",
                "",
                "- Why this should become a project rule: pending",
            ]
        )
        return f"rule draft (`.agents/rules/{slug}.md`)", snippet
    conflict_id = re.sub(r"[^a-z0-9]+", "-", source_id.lower()).strip("-") or "policy"
    snippet = "\n".join(
        [
            "python3 scripts/vibe.py policy-conflict-add <project_root> "
            f"{conflict_id}-pending \\",
            f'  --topic "{item["title"]} precedence pending" \\',
            f'  --sources "{source_id},agents-md" \\',
            '  --severity medium \\',
            '  --description "pending contradiction to be confirmed" \\',
            '  --scope "*"',
        ]
    )
    return "explicit conflict template", snippet


def _build_review_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for source in manifest.get("sources", []):
        if source.get("status") != "active":
            continue
        if source.get("kind") != "project":
            continue
        if source.get("id") == "agents-md":
            continue
        if source.get("manifest_override") is True:
            continue
        guidance = _review_guidance(source["id"])
        items.append(
            {
                "source_id": source["id"],
                "title": _display_name(source["id"]),
                "path": source.get("path", ""),
                "priority": "high" if source.get("priority", 0) >= 300 else "medium",
                "note": _review_note(source["id"]),
                "action": guidance["action"],
                "target": guidance["target"],
                "reason": guidance["reason"],
                "fallback_action": guidance["fallback_action"],
            }
        )
        label, snippet = _candidate_snippet(items[-1])
        items[-1]["candidate_label"] = label
        items[-1]["candidate_snippet"] = snippet
    return items


def render_policy_differences(
    project_root: Path,
    manifest: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> str:
    root = project_root.resolve()
    manifest = manifest or load_policy_sources(root)
    review_items = manifest.get("review_items") or _build_review_items(manifest)
    open_conflicts = [
        conflict
        for conflict in manifest.get("conflicts", [])
        if conflict.get("status") == "open"
    ]
    missing_sources = [
        source
        for source in manifest.get("sources", [])
        if source.get("status") == "missing" and not source.get("manifest_override")
    ]
    override_sources = [
        source
        for source in manifest.get("sources", [])
        if source.get("manifest_override") is True
    ]
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Policy Differences",
        "",
        f"> Generated: {generated_at}",
        "",
        "## Summary",
        "",
        f"- Pending confirmations: {len(review_items)}",
        f"- Open explicit conflicts: {len(open_conflicts)}",
        f"- Missing previously-seen sources: {len(missing_sources)}",
        f"- Manifest overrides (explicit): {len(override_sources)}",
        "",
        "## Pending Confirmations",
        "",
    ]
    if review_items:
        for item in review_items:
            lines.append(
                f"- [{item['priority']}] {item['title']} ({item['path']})"
            )
            lines.append(f"  - {item['note']}")
            lines.append(f"  - Suggested landing: {item['target']}")
            lines.append(f"  - Next move: {item['action']}")
    else:
        lines.append("- No higher-precedence project sources need confirmation right now.")

    lines.extend(["", "## Open Conflicts", ""])
    if open_conflicts:
        for conflict in open_conflicts:
            source_names = ", ".join(
                _display_name(source_id) for source_id in conflict.get("sources", [])
            )
            scope = ", ".join(conflict.get("scope") or ["*"])
            lines.append(
                f"- [{conflict.get('severity', 'unknown')}] {conflict.get('id')}: {conflict.get('topic', '')}"
            )
            lines.append(f"  - Sources: {source_names}")
            lines.append(f"  - Scope: {scope}")
            lines.append(f"  - Why: {conflict.get('description', '')}")
    else:
        lines.append("- No open explicit conflicts recorded.")

    lines.extend(["", "## Missing Sources", ""])
    if missing_sources:
        for source in missing_sources:
            lines.append(
                f"- {source.get('id')}: {source.get('path', '')} is no longer present."
            )
    else:
        lines.append("- No previously-seen policy sources are currently missing.")

    lines.extend(["", "## Manifest Overrides", ""])
    if override_sources:
        for source in override_sources:
            reason = source.get("override_reason") or "(no reason recorded)"
            actor = source.get("override_actor") or "(unknown)"
            lines.append(
                f"- {source.get('id')}: status={source.get('status')}, detected={source.get('detected')}"
            )
            lines.append(f"  - Path: {source.get('path', '')}")
            lines.append(f"  - Reason: {reason}")
            lines.append(f"  - Recorded by: {actor}")
    else:
        lines.append("- No policy sources currently use manifest_override.")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This file records governance differences only; it does not copy business rules.",
            "- Resolve real contradictions through explicit conflicts in `.agents/policy-sources.json`.",
            "- Sources with `manifest_override: true` bypass automatic scanner detection; see `vibe.py policy-override-add`.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_policy_confirmations(
    project_root: Path,
    manifest: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> str:
    manifest = manifest or load_policy_sources(project_root.resolve())
    review_items = manifest.get("review_items") or _build_review_items(manifest)
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Policy Confirmations",
        "",
        f"> Generated: {generated_at}",
        "",
        "## How To Use",
        "",
        "- Confirm whether the source is still authoritative.",
        "- Choose one landing: `workflow.json`, project rules / AGENTS, or explicit conflict.",
        "- Replace `pending` markers with the project decision.",
        "",
        "## Pending Items",
        "",
    ]
    if not review_items:
        lines.append("- No pending policy confirmations right now.")
        return "\n".join(lines) + "\n"

    for item in review_items:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- Source ID: `{item['source_id']}`",
                f"- Path: `{item['path']}`",
                f"- Suggested landing: `{item['target']}`",
                f"- Suggested action: {item['action']}",
                f"- Why: {item['reason']}",
                "",
                "Candidate Patch",
                "",
                f"- Type: {item['candidate_label']}",
                "```text",
                item["candidate_snippet"],
                "```",
                "",
                "Decision",
                "",
                "- Authority status: pending",
                "- Chosen landing: pending",
                "- Planned update: pending",
                "- Conflict needed: pending",
                "",
                "Notes",
                "",
                f"- {item['note']}",
                f"- Fallback: {item['fallback_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def load_policy_sources(project_root: Path) -> dict[str, Any]:
    path = manifest_file(project_root)
    if not path.exists():
        return empty_manifest()
    return json.loads(path.read_text(encoding="utf-8"))


def pending_review_items(project_root: Path) -> list[dict[str, Any]]:
    manifest = load_policy_sources(project_root)
    items = manifest.get("review_items") or _build_review_items(manifest)
    return [i for i in items if i.get("status") != "resolved"]


def _source(
    source_id: str,
    path: str,
    kind: str,
    priority: int,
    detected: bool = True,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "path": path,
        "kind": kind,
        "priority": priority,
        "status": "active" if detected else "missing",
        "detected": detected,
    }


def _rule_source_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    return f"agent-rule-{slug}"


def scan_policy_sources(project_root: Path, apply: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    current = load_policy_sources(root)
    existing = {
        item.get("id"): item
        for item in current.get("sources", [])
        if isinstance(item, dict) and item.get("id")
    }

    detected: list[dict[str, Any]] = [
        _source("skill-defaults", "skill://vibe-coding", "skill-default", 100)
    ]
    for source_id, relative_path, kind, priority in KNOWN_SOURCES:
        if (root / relative_path).exists():
            detected.append(_source(source_id, relative_path, kind, priority))

    rules_dir = root / ".agents" / "rules"
    if rules_dir.exists():
        for rule_path in sorted(rules_dir.glob("*.md")):
            relative = rule_path.relative_to(root).as_posix()
            detected.append(
                _source(_rule_source_id(rule_path), relative, "project-local", 200)
            )

    merged: list[dict[str, Any]] = []
    detected_ids = {item["id"] for item in detected}
    # 检测到的 source: 若 previous 显式 manifest_override=true,保留 previous.status 与 override 元数据
    for item in detected:
        previous = existing.get(item["id"], {})
        if previous.get("manifest_override") is True:
            override_meta = {
                k: previous[k]
                for k in ("manifest_override", "override_reason", "override_actor", "override_at")
                if k in previous
            }
            merged.append({
                **item,
                **override_meta,
                "detected": True,
                "status": previous.get("status", item["status"]),
            })
        else:
            merged.append({**item, **previous, "detected": True})

    # 未检测到的 source: 若显式 manifest_override=true,保留 previous.status(不再强制 missing);
    # 否则保持向后兼容行为,标记 missing。
    for source_id, item in existing.items():
        if source_id not in detected_ids:
            if item.get("manifest_override") is True:
                merged.append({**item, "detected": False})
            else:
                merged.append({**item, "detected": False, "status": "missing"})

    result = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "precedence": current.get("precedence", empty_manifest()["precedence"]),
        "sources": sorted(merged, key=lambda item: (-item.get("priority", 0), item["id"])),
        "conflicts": current.get("conflicts", []),
    }
    result["review_items"] = _build_review_items(result)
    if apply:
        atomic_write_json(manifest_file(root), result)
        atomic_write(difference_report_file(root), render_policy_differences(root, result))
        atomic_write(confirmation_draft_file(root), render_policy_confirmations(root, result))
    return result


def add_override(
    project_root: Path,
    source_id: str,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    """Mark a policy source as manifest-overridden.

    The scanner will preserve the source's previous status instead of forcing
    it back to `missing` when the source path cannot be auto-detected. The
    override decision is recorded on the source entry plus audit.md so the
    choice is auditable.
    """
    if not reason.strip():
        raise ValueError("override reason must not be empty")
    if not actor.strip():
        raise ValueError("override actor must not be empty")

    root = project_root.resolve()
    manifest = load_policy_sources(root)
    sources = manifest.get("sources", [])
    target = next((s for s in sources if s.get("id") == source_id), None)
    if target is None:
        raise ValueError(
            f"unknown policy source id: {source_id}. "
            f"Run `vibe.py policy-scan {project_root}` first to register it."
        )

    target["manifest_override"] = True
    target["override_reason"] = reason.strip()
    target["override_actor"] = actor.strip()
    target["override_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    manifest["review_items"] = _build_review_items(manifest)
    atomic_write_json(manifest_file(root), manifest)
    atomic_write(difference_report_file(root), render_policy_differences(root, manifest))
    atomic_write(confirmation_draft_file(root), render_policy_confirmations(root, manifest))
    return target


def add_conflict(
    project_root: Path,
    conflict_id: str,
    topic: str,
    source_ids: list[str],
    severity: str,
    description: str,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise ValueError(f"invalid severity: {severity}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", conflict_id):
        raise ValueError("conflict id must use lowercase letters, numbers, and hyphens")
    if len(source_ids) < 2:
        raise ValueError("a conflict must reference at least two policy sources")

    root = project_root.resolve()
    manifest = scan_policy_sources(root, apply=False)
    known_ids = {item["id"] for item in manifest["sources"]}
    unknown = sorted(set(source_ids) - known_ids)
    if unknown:
        raise ValueError(f"unknown policy source ids: {', '.join(unknown)}")
    if any(item.get("id") == conflict_id for item in manifest["conflicts"]):
        raise ValueError(f"conflict already exists: {conflict_id}")

    conflict = {
        "id": conflict_id,
        "topic": topic.strip(),
        "sources": sorted(set(source_ids)),
        "severity": severity,
        "status": "open",
        "scope": scopes or ["*"],
        "description": description.strip(),
        "resolution": "",
    }
    manifest["conflicts"].append(conflict)
    manifest["review_items"] = _build_review_items(manifest)
    atomic_write_json(manifest_file(root), manifest)
    atomic_write(difference_report_file(root), render_policy_differences(root, manifest))
    atomic_write(confirmation_draft_file(root), render_policy_confirmations(root, manifest))
    return conflict


def resolve_conflict(
    project_root: Path,
    conflict_id: str,
    resolution: str,
    status: str = "resolved",
) -> dict[str, Any]:
    if status not in {"resolved", "accepted"}:
        raise ValueError("resolution status must be resolved or accepted")
    if not resolution.strip():
        raise ValueError("resolution must not be empty")

    root = project_root.resolve()
    manifest = load_policy_sources(root)
    for conflict in manifest.get("conflicts", []):
        if conflict.get("id") == conflict_id:
            conflict["status"] = status
            conflict["resolution"] = resolution.strip()
            manifest["review_items"] = _build_review_items(manifest)
            atomic_write_json(manifest_file(root), manifest)
            atomic_write(difference_report_file(root), render_policy_differences(root, manifest))
            atomic_write(confirmation_draft_file(root), render_policy_confirmations(root, manifest))
            return conflict
    raise ValueError(f"conflict not found: {conflict_id}")


def unresolved_conflicts(
    project_root: Path,
    spec_name: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    path = manifest_file(project_root)
    if not path.exists():
        return []
    manifest = load_policy_sources(project_root)
    matches = []
    for conflict in manifest.get("conflicts", []):
        if conflict.get("status") != "open":
            continue
        if severity and conflict.get("severity") != severity:
            continue
        scopes = conflict.get("scope") or ["*"]
        if spec_name and "*" not in scopes and spec_name not in scopes:
            continue
        matches.append(conflict)
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan")
    scan.add_argument("project_root", type=Path)
    scan.add_argument("--apply", action="store_true")

    add = subparsers.add_parser("add-conflict")
    add.add_argument("project_root", type=Path)
    add.add_argument("conflict_id")
    add.add_argument("--topic", required=True)
    add.add_argument("--sources", required=True)
    add.add_argument("--severity", choices=sorted(SEVERITIES), required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--scope", default="*")

    resolve = subparsers.add_parser("resolve-conflict")
    resolve.add_argument("project_root", type=Path)
    resolve.add_argument("conflict_id")
    resolve.add_argument("--resolution", required=True)
    resolve.add_argument("--accept", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "scan":
            result = scan_policy_sources(args.project_root, apply=args.apply)
        elif args.command == "add-conflict":
            result = add_conflict(
                args.project_root,
                args.conflict_id,
                args.topic,
                [item.strip() for item in args.sources.split(",") if item.strip()],
                args.severity,
                args.description,
                [item.strip() for item in args.scope.split(",") if item.strip()],
            )
        else:
            result = resolve_conflict(
                args.project_root,
                args.conflict_id,
                args.resolution,
                "accepted" if args.accept else "resolved",
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
