#!/usr/bin/env python3
"""Record typed verification, release, or observation evidence for a spec."""

import argparse
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone

from common import (
    atomic_write,
    backup_file,
    command_digest,
    git_snapshot,
    project_context_digest,
    spec_digest,
    validate_artifact_name,
)
from set_status import _acceptance_criteria_ids, _missing_acceptance_criteria_references
from workflow_state import configured_commands, ensure_workflow, spec_metadata

PHASES = {"verify", "release", "observe"}
RESULTS = {"passed", "failed", "not-applicable"}
PURPOSES = {"standard", "reproduction", "fix-regression"}
VIBE_OPTIONS_AFTER_COMMAND = {"--configured", "--purpose"}


def record_evidence(
    project_root: str,
    spec_name: str,
    phase: str,
    result: str,
    evidence: str,
    actor: str = "",
    role: str = "",
    command: list[str] | None = None,
    configured: bool = False,
    purpose: str = "standard",
) -> str | None:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    if phase not in PHASES:
        raise ValueError(f"无效阶段: {phase}")
    if result not in RESULTS and not command and not configured:
        raise ValueError(f"无效结果: {result}")
    if purpose not in PURPOSES:
        raise ValueError(f"无效证据用途: {purpose}")
    if phase != "verify" and purpose != "standard":
        raise ValueError("只有 verify 阶段支持证据用途")
    misplaced = misplaced_vibe_options(command or [])
    if misplaced:
        raise ValueError(
            "Vibe evidence options must appear before --command: "
            + ", ".join(misplaced)
        )
    evidence = " ".join(evidence.split())
    if not evidence and not command and not configured:
        raise ValueError("证据说明不能为空")

    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_file):
        print(f"❌ 规格不存在: {spec_name}")
        return None
    with open(spec_file, encoding="utf-8") as handle:
        spec_content = handle.read()
    spec_fields = spec_metadata(spec_content)

    status_match = re.search(r">\s*状态:\s*(\S+)", spec_content)
    status = status_match.group(1) if status_match else "draft"
    workflow, _ = ensure_workflow(project_root)
    commands = configured_commands(workflow, phase) if configured else []
    if configured and not commands:
        raise ValueError(f"项目未配置 {phase} 命令")
    if command:
        commands = [command]

    command_output = ""
    exit_codes: list[str] = []
    command_digests: list[str] = []
    if commands:
        outputs = []
        passed = True
        for argv in commands:
            command_digests.append(command_digest(argv))
            try:
                completed = subprocess.run(
                    argv,
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                exit_codes.append(str(completed.returncode))
                passed = passed and completed.returncode == 0
                output = _redact_output(
                    (completed.stdout + completed.stderr).strip()
                )[:20000]
            except subprocess.TimeoutExpired as error:
                exit_codes.append("timeout")
                passed = False
                output = f"command timed out after {error.timeout} seconds"
            outputs.append(f"$ {_redact_output(shlex.join(argv))}\n{output}")
        result = "passed" if passed else "failed"
        command_output = "\n\n".join(outputs)
        evidence = evidence or f"执行 {len(commands)} 个项目命令"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    digest = spec_digest(spec_content)
    context_digest = project_context_digest(project_root)
    git = git_snapshot(project_root)
    evidence_name = phase if purpose == "standard" else f"{phase}-{purpose}"
    evidence_file = os.path.join(
        project_root, ".agents", "evidence", spec_name, f"{evidence_name}.md"
    )
    backup_file(
        evidence_file,
        os.path.join(
            project_root, ".agents", "archive", spec_name, "evidence", evidence_name
        ),
    )
    content = f"""# {spec_name} — {phase}

> 规格: {spec_name} | 规格摘要: {digest} | 上下文摘要: {context_digest} | 阶段: {phase} | 结果: {result}
> 用途: {purpose}
> Commit: {git['commit']} | Snapshot: {git.get('snapshot', 'N/A')} | 工作区: {git['worktree']} | Actor: {actor or '未记录'} | Role: {role or '未记录'}
> 记录: {now} | 规格状态: {status} | Exit: {','.join(exit_codes) or 'N/A'}
> Command-Digests: {','.join(command_digests) or 'N/A'}

## 证据

{evidence}
"""
    if commands:
        content += f"""

## 执行

```text
{command_output}
```
"""
    atomic_write(evidence_file, content)
    if phase == "verify" and purpose == "standard" and spec_fields.get("risk") != "low":
        missing_ac = _missing_acceptance_criteria_references(
            spec_content, content, spec_fields.get("risk", "medium")
        )
        if missing_ac:
            expected = ", ".join(f"AC{index}" for index in _acceptance_criteria_ids(spec_content))
            print(f"⚠️  verify 证据缺少验收标准引用: {', '.join(missing_ac)}")
            if expected:
                print(f"   建议在证据中标注覆盖: {expected}")
    print(f"✅ 已记录 {phase} 证据: {evidence_file}")
    return evidence_file


def _redact_output(output: str) -> str:
    """Redact common credential-shaped values before evidence is persisted."""
    output = re.sub(
        r"(?i)\b(password|passwd|token|secret|api[_-]?key)"
        r"(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        output,
    )
    return re.sub(
        r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]+",
        r"\1 [REDACTED]",
        output,
    )


def misplaced_vibe_options(command: list[str] | None) -> list[str]:
    """Return Vibe-owned options accidentally captured by --command."""
    if not command:
        return []
    return [token for token in command if token in VIBE_OPTIONS_AFTER_COMMAND]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record verification or release evidence")
    parser.add_argument("project_root", help="Project root directory")
    parser.add_argument("spec_name", help="Spec name")
    parser.add_argument("phase", choices=sorted(PHASES), help="Evidence phase")
    parser.add_argument("result", choices=sorted(RESULTS), help="Evidence result")
    parser.add_argument("evidence", nargs="?", default="", help="Concrete evidence or reason")
    parser.add_argument("--actor", default="", help="Person or agent identity")
    parser.add_argument("--role", default="", help="Workflow role")
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="Run and capture a real command")
    parser.add_argument("--configured", action="store_true", help="Run all configured commands for the phase")
    parser.add_argument("--purpose", choices=sorted(PURPOSES), default="standard")
    args = parser.parse_args()
    misplaced = misplaced_vibe_options(args.command)
    if misplaced:
        parser.error(
            "Vibe evidence options must appear before --command: "
            + ", ".join(misplaced)
        )
    record_evidence(
        os.path.abspath(args.project_root),
        args.spec_name,
        args.phase,
        args.result,
        args.evidence,
        args.actor,
        args.role,
        args.command,
        args.configured,
        args.purpose,
    )
