#!/usr/bin/env python3
"""Shared filesystem and validation helpers for workflow scripts."""

from __future__ import annotations

import os
import hashlib
import json
import shutil
import subprocess
import tempfile
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

RULE_STATUSES = {"proposed", "adopted", "deprecated"}
CONTEXT_STALE_AFTER = timedelta(days=7)


def validate_artifact_name(name: str, label: str = "名称") -> str:
    """Reject path traversal and names unsafe for generated filenames."""
    value = name.strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    if value in {".", ".."} or Path(value).name != value:
        raise ValueError(f"{label}不能包含路径")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label}不能包含控制字符")
    if len(value) > 100:
        raise ValueError(f"{label}不能超过 100 个字符")
    return value


def read_text(path: str | Path) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


def text_digest(content: str) -> str:
    """Return a short stable digest for artifact freshness checks."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def spec_digest(content: str) -> str:
    """Digest requirement content while ignoring mutable workflow timestamps/status."""
    normalized = re.sub(
        r"^>\s*状态:\s*\S+(?:\s*\|\s*创建:\s*[^|]+)?(?:\s*\|\s*更新:\s*.+)?$",
        "> 状态: <workflow-managed>",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return text_digest(normalized)


def command_digest(command: list[str]) -> str:
    """Return a stable digest for an argv-style command."""
    return text_digest(json.dumps(command, ensure_ascii=False, separators=(",", ":")))


def project_rule_status(content: str) -> str:
    """Return a project rule lifecycle state; legacy rules are adopted."""
    match = re.search(r"^>.*\b状态:\s*(\S+)", content, re.MULTILINE)
    return match.group(1).strip() if match else "adopted"


def adopted_project_rule_paths(project_root: str | Path) -> list[Path]:
    """List project rules that are active for execution and context freshness."""
    directory = Path(project_root) / ".agents" / "rules"
    if not directory.exists():
        return []
    adopted = []
    for path in sorted(directory.glob("*.md")):
        if project_rule_status(path.read_text(encoding="utf-8")) == "adopted":
            adopted.append(path)
    return adopted


def project_context_digest(project_root: str | Path) -> str:
    """Digest durable project guidance without importing business knowledge."""
    root = Path(project_root)
    paths = [root / "AGENTS.md", *adopted_project_rule_paths(root)]
    checklist_dir = root / ".agents" / "checklists"
    if checklist_dir.exists():
        paths.extend(sorted(checklist_dir.glob("*.md")))
    chunks = []
    for path in paths:
        if path.exists() and path.is_file():
            chunks.append(f"{path.relative_to(root)}\n{path.read_text(encoding='utf-8')}")
    workflow_path = root / ".agents" / "workflow.json"
    if workflow_path.exists():
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        durable_policy = {
            "schema_version": workflow.get("schema_version"),
            "risk_profiles": workflow.get("risk_profiles", {}),
            "commands": workflow.get("commands", {}),
        }
        chunks.append(
            ".agents/workflow.json#durable-policy\n"
            + json.dumps(durable_policy, ensure_ascii=False, sort_keys=True)
        )
    return text_digest("\n\n".join(chunks))


def assess_context_freshness(
    project_root: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Inspect AGENTS.md freshness and pending manual confirmation signals."""
    root = Path(project_root)
    agents_path = root / "AGENTS.md"
    context_refresh_path = root / ".agents" / "context-refresh.md"
    result: dict[str, object] = {
        "missing_agents": not agents_path.exists(),
        "missing_timestamp": False,
        "invalid_timestamp": False,
        "stale": False,
        "stale_days": None,
        "pending_manual_review": context_refresh_path.exists(),
        "warnings": [],
    }
    if not agents_path.exists():
        result["warnings"] = ["AGENTS.md 缺失，无法判断项目上下文是否新鲜"]
        return result

    content = agents_path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^-\s*(?:\*\*)?最后更新(?:\*\*)?:\s*(.+)$", content)
    if not match:
        result["missing_timestamp"] = True
        result["warnings"] = ["AGENTS.md 缺少 `最后更新` 字段，建议先刷新项目上下文"]
        return result

    raw_value = match.group(1).strip()
    try:
        updated_at = datetime.strptime(raw_value, "%Y-%m-%d %H:%M UTC").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        result["invalid_timestamp"] = True
        result["warnings"] = [
            f"AGENTS.md 的 `最后更新` 格式无法解析: {raw_value}"
        ]
        return result

    current_time = now or datetime.now(timezone.utc)
    age = current_time - updated_at
    if age > CONTEXT_STALE_AFTER:
        stale_days = max(1, int(age.total_seconds() // 86400))
        result["stale"] = True
        result["stale_days"] = stale_days
        result["warnings"] = [
            f"AGENTS.md 已有 {stale_days} 天未刷新，建议先更新项目上下文"
        ]
    return result


def git_snapshot(project_root: str | Path) -> dict:
    """Return the current Git commit and worktree state."""
    root = str(project_root)
    inside = subprocess.run(
        ["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if inside.returncode != 0:
        return {"commit": "not-a-git-repo", "worktree": "unknown"}
    commit = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "-C", root, "status", "--porcelain", "--", ".", ":(exclude).agents/**"],
        capture_output=True,
        text=True,
    )
    diff = subprocess.run(
        ["git", "-C", root, "diff", "--binary", "HEAD", "--", ".", ":(exclude).agents/**"],
        capture_output=True,
        text=True,
    ) if commit.returncode == 0 else subprocess.run(
        ["git", "-C", root, "diff", "--binary", "--cached", "--", ".", ":(exclude).agents/**"],
        capture_output=True,
        text=True,
    )
    untracked_names = subprocess.run(
        ["git", "-C", root, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).agents/**"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked_chunks = []
    for name in sorted(untracked_names):
        path = Path(root) / name
        if path.is_file() and path.stat().st_size <= 1_000_000:
            try:
                untracked_chunks.append(name + "\n" + path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                untracked_chunks.append(name + "\n<binary>")
    snapshot_source = "\n".join(
        [commit.stdout.strip(), status.stdout, diff.stdout, *untracked_chunks]
    )
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else "unborn",
        "worktree": "dirty" if status.stdout.strip() else "clean",
        "snapshot": text_digest(snapshot_source),
    }


def atomic_write_json(path: str | Path, value: object) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def backup_file(path: str | Path, backup_dir: str | Path) -> Path | None:
    """Copy an existing file to a timestamped backup directory."""
    source = Path(path)
    if not source.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    destination_dir = Path(backup_dir) / timestamp
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def atomic_write(path: str | Path, content: str) -> None:
    """Write text atomically so interrupted commands do not truncate files."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, file_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
