#!/usr/bin/env python3
"""Audit a project's workflow schema and artifact freshness."""

import argparse
import json
import os
import re
from pathlib import Path

from common import (
    RULE_STATUSES,
    assess_context_freshness,
    project_context_digest,
    project_rule_status,
    spec_digest,
)
from policy_sources import (
    confirmation_draft_file,
    CONFLICT_STATUSES,
    POLICY_SCHEMA_VERSION,
    SEVERITIES,
    difference_report_file,
    load_policy_sources,
    manifest_file,
    render_policy_confirmations,
    render_policy_differences,
)
from workflow_state import (
    SCHEMA_VERSION,
    configured_commands,
    dependency_cycles,
    ensure_workflow,
    spec_metadata,
    # NOTE: retro_gap_scan is imported lazily inside _audit_retro_gap_candidates
)

import archive_status

# Auxiliary Skills that ship with this suite. If any of them is missing from
# ~/.codex/skills/ alongside the core, doctor will surface a warning so the
# user does not have to remember to run install-auxiliary themselves.
KNOWN_AUXILIARIES = ("vibe-coding-reviewer", "vibe-coding-debugger")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def _read_project_skill_version(project_root: str) -> str:
    """Return the Skill version recorded in the project's .agents/.

    Returns 'unknown' when the file is missing (pre-Rule-52 project).
    """
    path = os.path.join(project_root, ".agents", ".skill-version")
    if not os.path.exists(path):
        return "unknown"
    try:
        with open(path, encoding="utf-8") as fp:
            value = fp.read().strip()
        return value or "unknown"
    except OSError:
        return "unknown"


def _read_current_skill_version() -> str:
    """Return the Skill's currently installed VERSION, or 'unknown' if missing.

    Missing VERSION usually means a dev install, a symlink to a checkout
    without a VERSION file, or a partial install — none of which should
    cause doctor to false-positive.
    """
    version_path = os.path.join(SKILL_DIR, "VERSION")
    if not os.path.exists(version_path):
        return "unknown"
    try:
        with open(version_path, encoding="utf-8") as fp:
            value = fp.read().strip()
        return value or "unknown"
    except OSError:
        return "unknown"


def _missing_auxiliaries() -> list[str]:
    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    skills_dir = os.path.join(codex_home, "skills")
    missing = []
    for name in KNOWN_AUXILIARIES:
        target = os.path.join(skills_dir, name)
        if not (os.path.isdir(target) or os.path.islink(target)):
            missing.append(name)
    return missing


def _audit_adjacent_protection(spec_name: str, content: str, warnings: list[str]) -> None:
    """Rule 56: check that adjacent-location entries have protection or risk ack."""
    # Find "故意不改" section content
    adjacent_match = re.search(
        r"(?:故意不改的相邻位置|Deliberately unchanged)[^\n]*\n((?:\s+-.*\n?)+)",
        content,
    )
    if not adjacent_match:
        return  # No adjacent locations declared — nothing to check
    section = adjacent_match.group(1)
    entries = [line.strip().lstrip("- ").strip() for line in section.splitlines() if line.strip().startswith("-")]
    if not entries:
        return
    # Check for risk acknowledgment in the section
    has_ack = any(
        "风险已知晓" in entry or "risk acknowledged" in entry.lower() or "无自动化测试保护" in entry
        for entry in entries
    )
    if has_ack:
        return  # Agent explicitly acknowledged the risk
    # No protection tests mentioned, no risk ack — advisory
    warnings.append(
        f"{spec_name}: {len(entries)} 个'故意不改的相邻位置'没有保护性测试或风险确认 (Rule 56) — "
        "添加保护性测试，或显式声明'风险已知晓'"
    )


def _audit_read_path_impact(spec_name: str, content: str, warnings: list[str]) -> None:
    """Rule 57: check that read paths have impact-type annotations."""
    # Find the scope/涉及范围 section
    scope_match = re.search(
        r"(?:## 涉及范围|## Scope)[^\n]*\n((?:.*\n?)*?)(?=## |$)",
        content,
    )
    if not scope_match:
        return  # No scope section — Rule 44 advisory covers this elsewhere
    section = scope_match.group(1)
    # Look for read-path lines that mention paths/endpoints but lack impact type
    # Impact types: 新增, 修改, 删除, added, modified, removed
    impact_types = {"新增", "修改", "删除", "added", "modified", "removed"}
    # Find lines that look like read-path entries (paths, endpoints, APIs)
    path_lines = [
        line.strip() for line in section.splitlines()
        if line.strip().startswith("-") and ("/" in line or "API" in line or "端点" in line or "路径" in line or "path" in line.lower())
    ]
    if not path_lines:
        return
    unannotated = []
    for line in path_lines:
        # Check if any impact type keyword is present
        if not any(it in line for it in impact_types):
            unannotated.append(line.lstrip("- ").strip()[:60])
    if unannotated:
        examples = unannotated[:3]
        warnings.append(
            f"{spec_name}: {len(unannotated)} 条读取路径缺少影响类型标注 (Rule 57) — "
            f"每条路径标注: 新增/修改/删除。示例: {', '.join(examples)}"
        )


def doctor(project_root: str) -> dict:
    workflow, migrated = ensure_workflow(project_root)
    issues = []
    warnings = []
    # Rule 52: surface Skill version drift so the user knows when a project
    # agent is running against a stale Skill. Advisory only — the project
    # itself is fine; only the agent's loaded rules may be out of date.
    project_version = _read_project_skill_version(project_root)
    skill_version = _read_current_skill_version()
    if project_version == "unknown":
        # Pre-Rule-52 project: do not back-warn; init_project / onboard
        # will populate .skill-version on next touch.
        pass
    elif project_version != skill_version and skill_version != "unknown":
        warnings.append(
            f"Skill version drift: project records '{project_version}', "
            f"installed Skill is '{skill_version}' (Rule 52). "
            f"Reload the Skill in the active session or open a new one "
            f"to pick up the new rules."
        )

    if workflow.get("schema_version") != SCHEMA_VERSION:
        issues.append("workflow schema is outdated")
    for phase in ("verify", "release", "observe"):
        raw = workflow.get("commands", {}).get(phase, [])
        if not isinstance(raw, list):
            issues.append(f"workflow commands.{phase} must be a list")
        elif len(configured_commands(workflow, phase)) != len(raw):
            issues.append(f"workflow commands.{phase} contains invalid commands")
    for cycle in dependency_cycles(project_root):
        issues.append(f"dependency cycle: {' -> '.join(cycle)}")
    _audit_policy_sources(Path(project_root), issues, warnings)
    _audit_context_freshness(Path(project_root), warnings)
    _audit_retro_gap_candidates(project_root, warnings)

    specs_dir = os.path.join(project_root, ".agents", "specs")
    if os.path.exists(specs_dir):
        for filename in sorted(os.listdir(specs_dir)):
            if not filename.endswith(".md") or filename.endswith("-amendments.md"):
                continue
            path = os.path.join(specs_dir, filename)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            name = filename[:-3]
            metadata = spec_metadata(content)
            if metadata["risk"] not in workflow["risk_profiles"]:
                issues.append(f"{name}: unknown risk {metadata['risk']}")
            if metadata.get("risk_confirmation") != "confirmed":
                warnings.append(f"{name}: risk requires confirmation")
            # Rule 47: spec frontmatter should carry a Prompt version.
            # Advisory only — pre-47 specs are grandfathered.
            pv_match = re.search(r">\s*Prompt version:\s*(\d+)\s*$", content, re.MULTILINE)
            if not pv_match:
                warnings.append(
                    f"{name}: spec frontmatter missing '> Prompt version: N' (Rule 47) — "
                    "add it so amendments are version-tracked"
                )
            # Rule 51: type=bug specs must declare a Fix Scope section.
            # Advisory only — pre-51 specs are grandfathered.
            spec_type_match = re.search(r">\s*类型:\s*(\S+)", content)
            if spec_type_match and spec_type_match.group(1) == "bug":
                if "## 修复范围" not in content and "## Fix Scope" not in content:
                    warnings.append(
                        f"{name}: type=bug spec missing '## 修复范围 (Fix Scope)' section (Rule 51) — "
                        "declare 已修复位置 + 故意不改的相邻位置 + 判断依据"
                    )
                # Rule 56: adjacent-location protection advisory.
                # If "故意不改" positions exist but no risk acknowledgment,
                # remind the agent to add protection tests or explicit risk ack.
                elif "## 修复范围" in content or "## Fix Scope" in content:
                    _audit_adjacent_protection(name, content, warnings)
            for dependency in metadata["dependencies"]:
                dependency_path = os.path.join(specs_dir, f"{dependency}.md")
                if not os.path.exists(dependency_path):
                    issues.append(f"{name}: missing dependency {dependency}")
            regression = metadata.get("regression_from", "")
            if regression:
                regression_path = os.path.join(specs_dir, f"{regression}.md")
                if not os.path.exists(regression_path):
                    issues.append(f"{name}: regression source spec {regression} not found")
                else:
                    with open(regression_path, encoding="utf-8") as rh:
                        reg_status = re.search(r">\s*状态:\s*(\S+)", rh.read())
                    if reg_status and reg_status.group(1) != "done":
                        warnings.append(f"{name}: regression source {regression} is not marked done")
            # Rule 57: read-path impact type annotation advisory.
            _audit_read_path_impact(name, content, warnings)

            plan = os.path.join(project_root, ".agents", "plans", filename)
            if os.path.exists(plan):
                with open(plan, encoding="utf-8") as handle:
                    plan_content = handle.read()
                spec_digest_value = spec_digest(content)
                context_digest_value = project_context_digest(project_root)
                if f"规格摘要: {spec_digest_value}" not in plan_content:
                    issues.append(
                        f"{name}: stale plan (spec digest mismatch); "
                        "regenerate or run "
                        "`vibe plan <project_root> <spec> --force`"
                    )
                if f"上下文摘要: {context_digest_value}" not in plan_content:
                    warnings.append(
                        f"{name}: plan uses stale project guidance; "
                        "run `vibe plan <project_root> <spec> --refresh-context`"
                    )

    rules_dir = os.path.join(project_root, ".agents", "rules")
    if os.path.exists(rules_dir):
        for filename in sorted(os.listdir(rules_dir)):
            if not filename.endswith(".md"):
                continue
            with open(os.path.join(rules_dir, filename), encoding="utf-8") as handle:
                status = project_rule_status(handle.read())
            if status not in RULE_STATUSES:
                issues.append(f"{filename}: unknown rule status {status}")
            elif status == "proposed":
                warnings.append(f"{filename}: proposed rule is not active")

    archive_dir = os.path.join(project_root, ".agents", "archive")
    archive_files = []
    if os.path.exists(archive_dir):
        archive_files = [
            os.path.join(root, filename)
            for root, _, filenames in os.walk(archive_dir)
            for filename in filenames
        ]
    archive_bytes = sum(
        os.path.getsize(path) for path in archive_files if os.path.isfile(path)
    )
    if len(archive_files) > 100 or archive_bytes > 50 * 1024 * 1024:
        warnings.append(
            "archive retention review recommended: "
            f"{len(archive_files)} files, {archive_bytes // (1024 * 1024)} MiB"
        )

    stale = archive_status.find_stale(project_root)
    if stale:
        warnings.append(
            f"{len(stale)} stale .agents/ file(s) eligible for archive — "
            "run `vibe archive-stale <root> [--apply]` (Rule 45)"
        )

    for name in _missing_auxiliaries():
        warnings.append(
            f"suite auxiliary not installed: {name} — run "
            f"`vibe install-auxiliary --all` to link it into ~/.codex/skills/"
        )

    print(f"Workflow schema: {workflow.get('schema_version')}")
    print(f"Migration applied: {'yes' if migrated else 'no'}")
    if issues:
        for issue in issues:
            print(f"- {issue}")
    else:
        print("No workflow integrity issues found.")
    for warning in warnings:
        print(f"Warning: {warning}")
    # Rule 50: machine-readable doctor health.
    health = "issues" if issues else "clean"
    print(f"<!-- vibe:doctor_health: {health} issues={len(issues)} warnings={len(warnings)} -->")
    return {"workflow": workflow, "issues": issues, "warnings": warnings}


def _audit_context_freshness(project_root: Path, warnings: list[str]) -> None:
    freshness = assess_context_freshness(project_root)
    for item in freshness.get("warnings", []):
        warnings.append(str(item))
    if freshness.get("pending_manual_review"):
        warnings.append(
            "context refresh 仍有待人工确认项: .agents/context-refresh.md"
        )


def _audit_policy_sources(
    project_root: Path, issues: list[str], warnings: list[str]
) -> None:
    path = manifest_file(project_root)
    if not path.exists():
        warnings.append("policy source inventory missing; run policy scan")
        return
    try:
        manifest = load_policy_sources(project_root)
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"policy source inventory is unreadable: {exc}")
        return
    if manifest.get("schema_version") != POLICY_SCHEMA_VERSION:
        issues.append("policy source schema is outdated")
    report_path = difference_report_file(project_root)
    review_items = manifest.get("review_items", [])
    if review_items and not report_path.exists():
        warnings.append("policy difference report missing; run policy scan --apply")
    elif report_path.exists():
        try:
            report_content = report_path.read_text(encoding="utf-8")
            generated_match = re.search(r"^> Generated:\s*(.+)$", report_content, re.MULTILINE)
            expected_report = render_policy_differences(
                project_root,
                manifest,
                generated_at=generated_match.group(1).strip() if generated_match else "",
            )
            if report_content != expected_report:
                warnings.append("policy difference report is stale; run policy scan --apply")
        except OSError as exc:
            warnings.append(f"policy difference report is unreadable: {exc}")
    confirmation_path = confirmation_draft_file(project_root)
    if review_items and not confirmation_path.exists():
        warnings.append("policy confirmation draft missing; run policy scan --apply")
    elif confirmation_path.exists():
        try:
            confirmation_content = confirmation_path.read_text(encoding="utf-8")
            generated_match = re.search(
                r"^> Generated:\s*(.+)$", confirmation_content, re.MULTILINE
            )
            expected_confirmation = render_policy_confirmations(
                project_root,
                manifest,
                generated_at=generated_match.group(1).strip() if generated_match else "",
            )
            if confirmation_content != expected_confirmation:
                warnings.append("policy confirmation draft is stale; run policy scan --apply")
        except OSError as exc:
            warnings.append(f"policy confirmation draft is unreadable: {exc}")

    sources = manifest.get("sources", [])
    if not isinstance(sources, list):
        issues.append("policy sources must be a list")
        return
    source_ids = [item.get("id") for item in sources if isinstance(item, dict)]
    if len(source_ids) != len(set(source_ids)):
        issues.append("policy source ids must be unique")
    known_ids = set(source_ids)
    for source in sources:
        if not isinstance(source, dict):
            issues.append("policy source entries must be objects")
            continue
        if not isinstance(source.get("priority"), int):
            issues.append(f"{source.get('id', '?')}: policy priority must be an integer")
        if source.get("status") == "missing" and not source.get("manifest_override"):
            warnings.append(f"{source.get('id', '?')}: policy source is missing")

    conflicts = manifest.get("conflicts", [])
    if not isinstance(conflicts, list):
        issues.append("policy conflicts must be a list")
        return
    conflict_ids = []
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            issues.append("policy conflict entries must be objects")
            continue
        conflict_id = conflict.get("id", "?")
        conflict_ids.append(conflict_id)
        unknown = sorted(set(conflict.get("sources", [])) - known_ids)
        if unknown:
            issues.append(
                f"{conflict_id}: unknown policy sources {', '.join(unknown)}"
            )
        if conflict.get("severity") not in SEVERITIES:
            issues.append(f"{conflict_id}: invalid conflict severity")
        if conflict.get("status") not in CONFLICT_STATUSES:
            issues.append(f"{conflict_id}: invalid conflict status")
        if conflict.get("status") == "open":
            message = (
                f"{conflict_id}: open {conflict.get('severity')} policy conflict "
                f"({conflict.get('topic', '')})"
            )
            if conflict.get("severity") == "high":
                issues.append(message)
            else:
                warnings.append(message)
    if len(conflict_ids) != len(set(conflict_ids)):
        issues.append("policy conflict ids must be unique")



def _smoke_commands(project_root: str) -> list[dict] | None:
    """Run configured commands and report their results."""
    import subprocess
    import shlex
    workflow, _ = ensure_workflow(project_root)
    results = []
    for phase in ("verify", "release", "observe"):
        commands = configured_commands(workflow, phase)
        if not commands:
            continue
        for argv in commands:
            try:
                completed = subprocess.run(
                    argv,
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                passed = completed.returncode == 0
                results.append({
                    "phase": phase,
                    "argv": shlex.join(argv),
                    "passed": passed,
                    "exit_code": completed.returncode,
                    "output": (completed.stdout + completed.stderr).strip()[:500],
                })
                if passed:
                    print(f"  ✅ {phase}: {shlex.join(argv)}")
                else:
                    print(f"  ❌ {phase}: {shlex.join(argv)} (exit {completed.returncode})")
            except subprocess.TimeoutExpired:
                results.append({
                    "phase": phase,
                    "argv": shlex.join(argv),
                    "passed": False,
                    "error": "timeout after 300s",
                })
                print(f"  ❌ {phase}: {shlex.join(argv)} (timeout)")
            except OSError as exc:
                results.append({
                    "phase": phase,
                    "argv": shlex.join(argv),
                    "passed": False,
                    "error": str(exc),
                })
                print(f"  ❌ {phase}: {shlex.join(argv)} ({exc})")
    if not results:
        print("  ℹ️  没有配置 smoke 命令（在 workflow.json 的 commands 中配置）")
        return None
    passed_count = sum(1 for r in results if r.get("passed"))
    print(f"  Smoke: {passed_count}/{len(results)} 通过")
    return results



def _audit_retro_gap_candidates(project_root, warnings):
    """P2 advisory: surface retro gap candidates as a doctor warning.

    Lists all open gaps from any retro in the project so the user
    can see them during a routine doctor sweep. Never blocks.
    Honours the per-project opt-out flag.
    """
    try:
        workflow, _ = ensure_workflow(project_root)
        if workflow.get("retro_gap_scan", {}).get("enabled") is False:
            return
    except Exception:
        return
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return
    import retro_gap_scan as _rgs
    total = 0
    for entry in sorted(os.listdir(retros_dir)):
        if not entry.endswith(".md"):
            continue
        try:
            content = open(os.path.join(retros_dir, entry), encoding="utf-8").read()
        except OSError:
            continue
        for _title, body, _ in _rgs._iter_gap_sections(content):
            for line in body.splitlines():
                if line.lstrip().startswith(("-", "*")):
                    total += 1
    if total > 0:
        warnings.append(
            f"retro gap 候选 {total} 个未确认（新 verify evidence 写入时会逐条提示）"
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit project workflow integrity")
    parser.add_argument("project_root")
    parser.add_argument("--smoke", action="store_true",
                        help="Run configured verify/release/observe commands and report results")
    args = parser.parse_args()
    result = doctor(os.path.abspath(args.project_root))
    if args.smoke:
        smoke_result = _smoke_commands(os.path.abspath(args.project_root))
        result["smoke"] = smoke_result
        if smoke_result:
            for cmd_result in smoke_result:
                if not cmd_result.get("passed"):
                    result["issues"].append(
                        f"smoke: {cmd_result['phase']} command failed: "
                        f"{cmd_result.get('error', cmd_result.get('argv'))}"
                    )
    raise SystemExit(1 if result["issues"] else 0)
