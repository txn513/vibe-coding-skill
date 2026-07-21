#!/usr/bin/env python3
from __future__ import annotations
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
import retro_gap_scan

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

    # Auto-default actor/role from workflow.json roles (Single-Actor
    # Convenience). Most projects have a single named operator per role
    # (e.g. roles.builder = "lance"); forcing the agent to type
    # `--actor lance --role builder` on every evidence call is pure noise.
    # For multi-actor projects (roles.<expected_role> == ""), this is a
    # no-op and the existing advisory still fires so the agent must
    # specify identity explicitly. 2026-07-10 candidate 1.
    _phase_to_role_default = {
        "verify": "builder",
        "release": "releaser",
        "observe": "observer",
    }
    _expected_role = _phase_to_role_default.get(phase, "builder")
    if not actor or not role:
        _configured_actor = (
            (workflow.get("roles") or {}).get(_expected_role, "") or ""
        ).strip()
        if _configured_actor:
            if not actor:
                actor = _configured_actor
            if not role:
                role = _expected_role

    # Advisory A: suggest filling actor/role (Record-Side Identity Hint)
    # If user did not pass --actor or --role, suggest filling them.
    # Auto-default above already filled from workflow.json roles when the
    # project has a single named operator; this advisory only fires for
    # multi-actor / fresh projects where the recorded identity must be
    # specified explicitly. The phase_to_role table here is the same
    # fallback used to pick --role hint text.
    if not actor or not role:
        suggested_role = _phase_to_role_default.get(phase)
        missing = []
        if not actor:
            missing.append("--actor")
        if not role and suggested_role:
            missing.append(f"--role {suggested_role}")
        if missing:
            hint = (
                f"\u26a0\ufe0f  证据未记录执行者身份: 建议补充 {' '.join(missing)}"
            )
            if suggested_role:
                hint += (
                    f" (项目级默认可在 .agents/workflow.json 的 "
                    f"roles.{suggested_role} 配置)"
                )
            print(hint)
            print(
                "<!-- vibe:evidence_identity_hint: missing="
                + ",".join(
                    name
                    for name, present in (("actor", actor), ("role", role))
                    if not present
                )
                + " -->"
            )

    # Advisory B: suggest --configured when project has commands but
    # user did not use it (Command-Digests Auto-Capture Hint)
    if not configured and not command:
        all_commands = (
            configured_commands(workflow, phase)
            or configured_commands(workflow, "verify")
            or []
        )
        if all_commands:
            print(
                f"\u26a0\ufe0f  项目已配置 {len(all_commands)} 条 {phase} 命令，"
                f"建议加 --configured 自动捕获 Command-Digests 与执行结果，"
                f"否则 verify gate 可能报 evidence exists but digest mismatch。"
            )
            print(
                f"<!-- vibe:evidence_configured_hint: phase={phase} "
                f"commands={len(all_commands)} -->"
            )

    command_output = ""
    exit_codes: list[str] = []
    command_digests: list[str] = []
    if commands:
        outputs = []
        passed = True
        for raw_argv in commands:
            # Normalize: --command argparse.REMAINDER may pass the
            # command as a single string instead of an argv list.
            # command_digest() expects list[str]; without normalization
            # the digest differs from the one computed during advance
            # gate checks, causing "evidence exists but digest mismatch".
            if isinstance(raw_argv, str):
                argv = shlex.split(raw_argv)
            else:
                argv = list(raw_argv)
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
> Created-At: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

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
    # C2 advisory (2026-07-11): bug spec fix-regression gate requires
    # Command-Digests line to include ALL configured verify digests
    # (subset check). If the agent recorded custom --command instead
    # of --configured, the gate silently fails. Surface the gap right
    # after recording so the agent fixes Command-Digests or re-records
    # with --configured. Skipped when not bug-fix-regression (no gate
    # to misalign with).
    if (
        phase == "verify"
        and purpose == "fix-regression"
        and command
        and not configured
    ):
        _emit_fix_regression_digest_advisory(
            project_root, command_digests, workflow
        )
    if phase == "verify" and purpose == "standard" and spec_fields.get("risk") != "low":
        missing_ac = _missing_acceptance_criteria_references(
            spec_content, content, spec_fields.get("risk", "medium")
        )
        if missing_ac:
            expected = ", ".join(f"AC{index}" for index in _acceptance_criteria_ids(spec_content))
            print(f"⚠️  verify 证据缺少验收标准引用: {', '.join(missing_ac)}")
            if expected:
                print(f"   建议在证据中标注覆盖: {expected}")
    # 2026-07-21: degradation-path advisory — if spec has happy-path ACs
    # but no failure/degradation evidence, remind the agent.
    if phase == "verify" and result == "passed" and spec_fields.get("risk") in {"high", "medium"}:
        _check_degradation_path_coverage(spec_content, evidence, spec_name)
    print(f"✅ 已记录 {phase} 证据: {evidence_file}")
    if _evidence_missing_rerun_command(content, command):
        _emit_rerun_advisory(content)
    _maybe_prompt_retro_gap_closure(project_root, spec_name, evidence, phase)
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


def _emit_fix_regression_digest_advisory(
    project_root: str, actual_digests: list[str], workflow: dict
) -> None:
    """Surface configured digest subset gap before advance gate hits it.

    The bug-spec fix-regression evidence advance gate requires
    `Command-Digests` ⊇ configured verify digests (subset check, see
    set_status.py:_has_current_evidence purpose=fix-regression). When
    agent records evidence with a custom `--command` instead of
    `--configured`, the digests only contain the custom commands and
    the gate silently fails on next `vibe advance review`.

    2026-07-11 candidate 2 advisory — discover the gap at record
    time, not advance time, by listing configured vs actual digests.
    """
    from workflow_state import configured_commands
    from common import command_digest as _cd

    configured = configured_commands(workflow, "verify")
    if not configured:
        return
    expected = {_cd(c) for c in configured}
    actual = set(actual_digests or [])
    missing = expected - actual
    if not missing:
        return
    print()
    print("⚠️  Evidence Command-Digests 子集提示 (Rule 10 + 53b2afc):")
    print("   bug spec fix-regression 推进 review 时 gate 要求")
    print("   Command-Digests ⊇ configured verify digests。")
    print(f"   当前实际 ({len(actual)}):")
    for d in sorted(actual):
        print(f"     - {d}")
    print(f"   configured ({len(expected)}) — missing {len(missing)}:")
    for d in sorted(missing):
        print(f"     - {d}")
    print("   修复方法 A: 用 `--configured` 重新跑 evidence，自动捕获所有 configured 命令 digest")
    print("   修复方法 B: 在 evidence 文本里额外跑一次 configured verify 命令并把 digest 加进 Command-Digests")
    print("   (advisory 不阻塞; advance 时 gate 会 reject, 看到这条提示可预先对齐)")
    print("<!-- vibe:fix_regression_digest_subset: missing="
          f"{','.join(sorted(missing))} -->")


def misplaced_vibe_options(command: list[str] | None) -> list[str]:
    """Return Vibe-owned options accidentally captured by --command."""
    if not command:
        return []
    return [token for token in command if token in VIBE_OPTIONS_AFTER_COMMAND]




_RUN_KEYWORDS = (
    "ran pytest", "ran the test", "ran tests", "running pytest",
    "ran the suite", "ran unit tests",
    "\u8dd1\u4e86 pytest", "\u8dd1\u6d4b\u8bd5", "\u8dd1\u4e86\u6d4b\u8bd5", "\u8dd1\u901a\u4e86\u6d4b\u8bd5",
    "\u6d4b\u8bd5\u901a\u8fc7", "tests pass", "tests passed",
    "executed the test", "\u6267\u884c\u4e86\u6d4b\u8bd5",
)
_CAPTURED_COMMAND_HINT = (
    "## \u6267\u884c", "command:", "cmd:", "$ ", "```bash", "```sh",
    "py.test ", "pytest -", "pytest.", "pnpm test", "pnpm exec", "npm test", "npm run",
    "cargo test", "go test",
    "make ", "just ",)


def _evidence_missing_rerun_command(evidence_text, captured_command):
    """Rule 28.3 advisory.

    Returns True when free-text evidence contains a 'ran X' claim AND
    the agent did NOT pass --command AND the evidence text does not
    contain a recognisable command fragment for the reviewer to re-run.
    """
    if captured_command:
        return False
    lowered = evidence_text.lower()
    for kw in _RUN_KEYWORDS:
        if kw.lower() in lowered:
            for hint in _CAPTURED_COMMAND_HINT:
                if hint.lower() in lowered:
                    return False
            return True
    return False


def _emit_rerun_advisory(evidence_text):
    print("\u26a0\ufe0f  Evidence 包含 'ran X' 描述但未捕获可重跑命令 (Rule 28.3)")
    print("   建议: 用 --command 参数跑实际命令, 或在 evidence 文本里包含完整命令行")
    print("   (advisory, 不阻塞; reviewer 需要可重跑来验证结果)")


def _maybe_prompt_retro_gap_closure(
    project_root, spec_name, evidence_text, phase
):
    if phase != "verify":
        return
    try:
        candidates = retro_gap_scan.scan_retro_gaps(
            project_root, spec_name, evidence_text
        )
    except Exception:
        return
    if not candidates:
        return
    print()
    print(retro_gap_scan.format_candidates(candidates))
    try:
        answer = input("   选择 (Y/n/skip-all): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if answer in {"y", "yes", ""}:
        for c in candidates:
            print()
            print("---" + " 建议追加到 " + c.retro_name + " 的 mini 段（手动粘贴）---")
            print(retro_gap_scan.suggested_mini_paragraph(c, spec_name))
        print("⚠️  Skill 不会自动写入 retro；请你 review 后手动粘贴。")
    elif answer == "skip-all":
        _record_retro_skip_all(project_root)
        print("   本项目 retro gap 提示已永久关闭（写入 workflow.json）。")
    else:
        print("   跳过本次提示。")


def _record_retro_skip_all(project_root):
    import workflow_state
    workflow, _ = workflow_state.ensure_workflow(project_root)
    workflow.setdefault("retro_gap_scan", {})["enabled"] = False
    from common import atomic_write_json
    atomic_write_json(
        os.path.join(project_root, ".agents", "workflow.json"),
        workflow,
    )


def _check_degradation_path_coverage(spec_content: str, evidence_content: str, spec_name: str) -> None:
    """Advisory: if spec has happy-path ACs but no failure/degradation evidence,
    remind the agent to verify the degradation path too.

    This is advisory-only — it does not block advance. The goal is to
    surface the "only happy path verified" anti-pattern (2026-07-21e candidate).
    """
    # Count ACs that are happy-path vs degradation-path
    happy_count = len(re.findall(r"\[happy-path\]", spec_content))
    degrad_count = len(re.findall(r"\[degradation-path\]", spec_content))
    # If spec has no explicit tags, check for implicit happy-path ACs
    # (ACs without degradation-path tag)
    ac_ids = re.findall(r"\*\*AC\d+\*\*", spec_content)
    if not ac_ids:
        return
    # Check if evidence mentions degradation / failure / error handling
    has_degradation_evidence = bool(
        re.search(
            r"(degradation|失败|降级|fallback|error.handle|failure.mode|异常处理|边界条件|错误恢复)",
            evidence_content,
            re.IGNORECASE,
        )
    )
    # Only warn if: spec has ACs, but no degradation-path ACs AND no degradation evidence
    if degrad_count == 0 and not has_degradation_evidence and len(ac_ids) >= 2:
        print()
        print(f"💡 [可选] spec `{spec_name}` 有 {len(ac_ids)} 个验收标准但无 degradation-path 验证。")
        print("   建议补充: 异常/降级路径的 verify 证据（如: 网络超时、依赖不可用、边界输入）。")
        print("   标记方式: 在 spec AC 后加 `[degradation-path]`，或直接在证据中描述异常场景。")
        print("<!-- vibe:degradation_path_advisory -->")

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
