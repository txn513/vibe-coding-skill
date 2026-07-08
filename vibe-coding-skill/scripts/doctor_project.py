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


def _check_skill_version_drift() -> str | None:
    """Detect if the installed Skill's VERSION is behind its git HEAD.

    Compares the git commit that last touched `VERSION` against the
    current Skill HEAD. If N commits have landed since the last
    VERSION bump, the maintainer likely forgot to bump VERSION, and
    downstream `vibe doctor` / `vibe upgrade` will falsely report
    "version is up to date".

    The check is amend-safe: `git log VERSION` always points to the
    most recent commit (including amends) that changed the file. So
    as long as the maintainer amends VERSION together with the rule
    change, no false positive fires.
    """

    version_path = os.path.join(SKILL_DIR, "VERSION")
    if not os.path.exists(version_path):
        # Dev install without a VERSION file — stay silent, never false-positive.
        return None
    import subprocess
    # Walk up to find the git root (handles the dev checkout where
    # .git is one level above vibe-coding-skill/).
    git_root = SKILL_DIR
    while git_root != "/":
        if os.path.isdir(os.path.join(git_root, ".git")):
            break
        git_root = os.path.dirname(git_root)
    else:
        return None
    version_relpath = os.path.relpath(
        os.path.join(SKILL_DIR, "VERSION"), git_root,
    )
    try:
        # Last commit that touched VERSION (in git history, not working tree)
        version_commit_result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", version_relpath],
            cwd=git_root, capture_output=True, text=True, timeout=5,
        )
        head_result = subprocess.run(
            ["git", "log", "-1", "--format=%H"],
            cwd=git_root, capture_output=True, text=True, timeout=5,
        )
        if (version_commit_result.returncode != 0 or
                head_result.returncode != 0):
            return None
        version_sha = version_commit_result.stdout.strip()
        head_sha = head_result.stdout.strip()
        if not version_sha or not head_sha:
            return None
        if version_sha == head_sha:
            return None  # VERSION was bumped in HEAD itself
        # Hybrid amend-safe shortcut: if the maintainer already edited the
        # working-tree VERSION to begin with the current HEAD short hash
        # (e.g. "<7char>-fix-xxx"), treat that as a fresh bump even before
        # the next commit lands. Prevents transient false positives while
        # the maintainer is staging the new commit that bumps VERSION.
        try:
            # Accept either 7- or 8-char short hash prefixes to align with
            # common commit-hash shorthand used in VERSION placeholders.
            head_short7 = head_sha[:7]
            head_short8 = head_sha[:8]
            with open(os.path.join(SKILL_DIR, "VERSION"), encoding="utf-8") as fp:
                wt_version = fp.read().strip()
            if (wt_version.startswith(head_short7 + "-") or wt_version == head_short7 or
                    wt_version.startswith(head_short8 + "-") or wt_version == head_short8):
                return None
        except OSError:
            pass
        count_result = subprocess.run(
            ["git", "rev-list", "--count", f"{version_sha}..{head_sha}"],
            cwd=git_root, capture_output=True, text=True, timeout=5,
        )
        commit_count = count_result.stdout.strip() or "?"
        return (
            f"Skill VERSION drift: {commit_count} commit(s) have landed "
            f"since the last VERSION bump (last bump in {version_sha[:8]}, "
            f"HEAD is {head_sha[:8]}). The maintainer likely forgot to "
            f"bump VERSION in the last commit — `vibe upgrade` and "
            f"version drift checks will report false 'up to date' "
            f"until VERSION is bumped."
        )
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None


def _missing_auxiliaries() -> list[str]:
    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    skills_dir = os.path.join(codex_home, "skills")
    missing = []
    for name in KNOWN_AUXILIARIES:
        target = os.path.join(skills_dir, name)
        if not (os.path.isdir(target) or os.path.islink(target)):
            missing.append(name)
    return missing


def _audit_adjacent_protection(spec_name: str, content: str, warnings: list[str]) -> dict:
    """Rule 56: check that adjacent-location entries have protection or risk ack.

    Returns a stats dict: {total, protected, skipped} for this spec.
    """
    # Find "故意不改" section content
    adjacent_match = re.search(
        r"(?:故意不改的相邻位置|Deliberately unchanged)[^\n]*\n((?:\s+-.*\n?)+)",
        content,
    )
    if not adjacent_match:
        return {"total": 0, "protected": 0, "skipped": 0}
    section = adjacent_match.group(1)
    entries = [line.strip().lstrip("- ").strip() for line in section.splitlines() if line.strip().startswith("-")]
    if not entries:
        return {"total": 0, "protected": 0, "skipped": 0}
    # Check for risk acknowledgment or protection test mention
    protected = 0
    skipped = 0
    for entry in entries:
        is_ack = (
            "风险已知晓" in entry
            or "risk acknowledged" in entry.lower()
            or "无自动化测试保护" in entry
        )
        is_test = (
            "测试" in entry or "test" in entry.lower()
        )
        if is_ack or is_test:
            protected += 1
        else:
            skipped += 1
    if skipped > 0:
        warnings.append(
            f"{spec_name}: {skipped} 个'故意不改的相邻位置'没有保护性测试或风险确认 (Rule 56) — "
            "添加保护性测试，或显式声明'风险已知晓'"
        )
    return {"total": len(entries), "protected": protected, "skipped": skipped}


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


def _audit_raw_git_commits(project_root: str, warnings: list[str]) -> None:
    """Rule 53: detect recent commits that bypassed vibe commit.

    vibe commit adds a 'Vibe-Commit: yes' trailer to every commit it
    creates. Commits without this trailer were likely created with
    raw `git commit`, bypassing the review + verify gate.
    """
    try:
        import subprocess
        # Check last 10 commits
        result = subprocess.run(
            ["git", "log", "--no-merges", "-10", "--format=%H%n%B---END---"],
            cwd=project_root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return
        entries = result.stdout.split("---END---")
        raw_commits = []
        for entry in entries:
            lines = entry.strip().splitlines()
            if not lines:
                continue
            sha = lines[0][:12]
            body = "\n".join(lines[1:])
            if "Vibe-Commit:" not in body:
                # Skip the very first commit (init) which predates vibe commit
                raw_commits.append(sha)
        if raw_commits:
            warnings.append(
                f"最近 {len(raw_commits)} 个 commit 缺少 Vibe-Commit trailer (Rule 53): "
                f"这些 commit 可能用 raw `git commit` 提交，绕过了 review + verify gate。"
                f"  SHA: {', '.join(raw_commits[:5])}"
            )
            # Recovery guidance: tell the Agent exactly how to replay the commit
            # so the audit trail is restored. (2026-07-08 候选 2a)
            warnings.append(
                "  修复: 用 `git reset --soft HEAD~N` 回到违规 commit 之前，"
                "然后按顺序跑 `vibe commit` (step 1, 看 diff) + "
                "`vibe commit --reviewed --review-summary '...'` (step 2, "
                "verify + commit with trailer)。严禁用 `git commit --amend` 改 "
                "message 补 trailer — amend 会改变 commit SHA, trailer 校验会失效。"
            )
    except (OSError, subprocess.TimeoutExpired):
        return


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
    # Maintainer-side: detect if Skill's own VERSION is behind its git HEAD.
    # Without this check, downstream projects would silently miss new rules.
    skill_drift = _check_skill_version_drift()
    if skill_drift:
        warnings.append(skill_drift)

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
    _audit_raw_git_commits(project_root, warnings)
    _audit_policy_sources(Path(project_root), issues, warnings)
    _audit_context_freshness(Path(project_root), warnings)
    _audit_retro_gap_candidates(project_root, warnings)
    # Rule 56: accumulate adjacent-location protection stats across specs
    adjacent_stats = {"total": 0, "protected": 0, "skipped": 0}

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
                    stats = _audit_adjacent_protection(name, content, warnings)
                    adjacent_stats["total"] += stats["total"]
                    adjacent_stats["protected"] += stats["protected"]
                    adjacent_stats["skipped"] += stats["skipped"]
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
                    # 2026-07-09 (Lance retro on social-bookmarking-tool):
                    # the old advisory said "--force" which would re-render
                    # the entire plan from template and clobber Agent-entered
                    # phase/task body. The Agent had to manually compute a
                    # 16-char sha256 to patch the header, a real friction
                    # surface. Surface the cheap one-line fix:
                    #   vibe plan ... --refresh-digest-only
                    # which patches only the digest header lines and works
                    # even when spec status is done/released.
                    issues.append(
                        f"{name}: stale plan (spec digest mismatch); "
                        "run `vibe plan <project_root> <spec> --refresh-digest-only` "
                        f"(patch header; spec digest should be {spec_digest_value}, "
                        f"context digest should be {context_digest_value})"
                    )
                if f"上下文摘要: {context_digest_value}" not in plan_content:
                    warnings.append(
                        f"{name}: plan uses stale project guidance; "
                        "run `vibe plan <project_root> <spec> --refresh-context` "
                        "(re-renders plan; requires spec-ready/in-progress) "
                        "or --refresh-digest-only (header-only patch, any status)"
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

    _check_spec_frontmatter_uniqueness(project_root, warnings)
    _check_stale_retro_action_items(project_root, warnings)

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
    # Rule 56: adjacent-location protection summary
    if adjacent_stats["total"] > 0:
        total = adjacent_stats["total"]
        protected = adjacent_stats["protected"]
        skipped = adjacent_stats["skipped"]
        skip_rate = f"{skipped * 100 // total}%" if total > 0 else "0%"
        print(f"📋 Rule 56 相邻位置保护: {total} 个声明, {protected} 个已保护, {skipped} 个跳过 (跳过率 {skip_rate})")
        if skipped > total // 2 and total >= 3:
            print("   ⚠️  跳过率超过 50%，考虑在 workflow.json 加 adjacent_protection.required_for 配置项")
        print(f"<!-- vibe:adjacent_protection: total={total} protected={protected} skipped={skipped} -->")
    print(f"<!-- vibe:doctor_health: {health} issues={len(issues)} warnings={len(warnings)} -->")
    return {"workflow": workflow, "issues": issues, "warnings": warnings}


# Frontmatter fields that MUST be unique in a spec (one line per field).
# `依赖` is intentionally excluded — multiple dependencies are valid
# (`> 依赖: spec-a, spec-b`). All other governance-critical fields
# should appear exactly once; duplicates indicate a write tool bug
# (e.g. an older set_status.py appending without dedup).
_UNIQUE_FRONTMATTER_FIELDS = (
    "状态",
    "风险",
    "风险确认",
    "更新时间",
)


def _check_spec_frontmatter_uniqueness(project_root: Path, warnings: list[str]) -> None:
    """Advisory: flag specs whose governance-critical frontmatter fields
    appear more than once. Likely a tool bug or manual edit error.
    Only advisory — project migration periods may legitimately have
    duplicates while dedup scripts run.
    """
    specs_dir = Path(project_root) / ".agents" / "specs"
    if not specs_dir.exists():
        return
    for spec_path in sorted(specs_dir.glob("*.md")):
        if spec_path.name.endswith("-amendments.md"):
            continue
        try:
            content = spec_path.read_text(encoding="utf-8")
        except OSError:
            continue
        spec_name = spec_path.stem
        for field in _UNIQUE_FRONTMATTER_FIELDS:
            pattern = rf"^>\s*{re.escape(field)}:\s*\S"
            matches = re.findall(pattern, content, re.MULTILINE)
            if len(matches) > 1:
                warnings.append(
                    f"spec '{spec_name}' frontmatter 字段 '{field}' 出现 "
                    f"{len(matches)} 行（应唯一）— 可能是 set_status / "
                    f"confirm_risk 写入 bug，建议清理"
                )


def _check_stale_retro_action_items(project_root: Path, warnings: list[str]) -> None:
    """Advisory: flag retro action items still in `[ ]` past the project's
    natural review cadence. Mirrors the hint that vibe next emits, but
    also surfaces here so `vibe doctor` is self-contained.

    Reuses scan_stale_action_items() from retro_gap_scan (Rule 60).
    """
    from retro_gap_scan import scan_stale_action_items
    retros_dir = Path(project_root) / ".agents" / "retros"
    if not retros_dir.exists():
        return
    try:
        stale = scan_stale_action_items(str(project_root), max_cycles=2)
    except Exception:  # noqa: BLE001
        # Advisory only; never let a retro scan error block doctor.
        return
    if not stale:
        return
    warnings.append(
        f"{len(stale)} retro action item(s) still in `[ ]` past the "
        f"project's 2-cycle review cadence (Rule 60). Run "
        f"`python scripts/retro_gap_scan.py <project> --audit-stale` "
        f"for the full list and upgrade each to "
        f"[active: <id>] / [deferred: <reason>] / [superseded: <id>]."
    )


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
