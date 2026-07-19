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
    check_skill_version_drift,
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


def _audit_adjacent_protection(spec_name: str, content: str, warnings: list[str]) -> dict:
    """Rule 56: check that adjacent-location entries have protection or risk ack.

    Returns a stats dict: {total, protected, skipped} for this spec.
    """
    # Check if Rule 56 table already exists (retrofit-generated table)
    has_rule_56_table = bool(re.search(
        r"\|\s*位置.*是否已有保护性测试.*风险已知晓\s*\|",
        content,
    ))

    # Find "故意不改" section content
    adjacent_match = re.search(
        r"(?:故意不改的相邻位置|Deliberately unchanged)[^\n]*\n((?:\s+-.*\n?)+)",
        content,
    )
    if not adjacent_match:
        return {"total": 0, "protected": 0, "skipped": 0}
    section = adjacent_match.group(1)

    # If Rule 56 table exists, skip bullet-level checks (table is authoritative)
    if has_rule_56_table:
        entries = []
    else:
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

    # Check if Rule 57 table already exists (retrofit-generated table)
    has_rule_57_table = bool(re.search(
        r"###\s*受影响的读路径.*Rule 57|\|.*读路径.*\|.*影响类型.*\|",
        content,
    ))

    # Look for read-path lines that mention paths/endpoints but lack impact type
    # Impact types: 新增, 修改, 删除, added, modified, removed
    impact_types = {"新增", "修改", "删除", "added", "modified", "removed", "无影响", "无变化", "no-impact", "no-change"}
    # Find lines that look like read-path entries (paths, endpoints, APIs)
    path_lines = [
        line.strip() for line in section.splitlines()
        if line.strip().startswith("-") and ("/" in line or "API" in line or "端点" in line or "路径" in line or "path" in line.lower())
    ]
    if not path_lines:
        return
    unannotated = []
    for line in path_lines:
        # Skip bullet when Rule 57 table exists and this bullet is about read paths
        if has_rule_57_table and "受影响的读路径" in line:
            continue
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


def _audit_agents_outdated(project_root: str, warnings: list[str]) -> None:
    """Detect if project's AGENTS.md is outdated (missing per-stage constraints).

    2026-07-12: the template now includes a per-stage constraint section.
    Existing projects may still have the old template without these checks.
    Advisory only — the agent decides when to migrate.
    """
    agents_path = os.path.join(project_root, "AGENTS.md")
    if not os.path.exists(agents_path):
        return
    try:
        with open(agents_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    # Heuristic: check for the presence of key new sections
    if "## 阶段级约束" not in content:
        warnings.append(
            "AGENTS.md 模板已过期 (2026-07-12): 缺少 '阶段级约束' 章节。"
            "建议: 运行 `vibe upgrade-agents <project> --dry-run` 预览合并（保留用户内容） "
            "手动更新 AGENTS.md，或重新初始化项目。"
        )
    elif "禁止直接使用 `git commit`" not in content:
        warnings.append(
            "AGENTS.md 模板已过期: 缺少 '禁止直接使用 git commit' 约束。"
            "建议: 手动添加或更新 AGENTS.md。"
        )


def _audit_inbox_drift(project_root: str, warnings: list[str]) -> None:
    """Detect done spec with open inbox bug (Rule 65, opt-in).

    For each spec in `.agents/specs/` with status `done` or `released`,
    check if `.agents/bug-inbox.md` contains a `- [ ]` row mentioning
    that spec name. If yes, append a warning ("spec X done but inbox
    still has open row").

    Only fires when:
      - workflow.json.bugs.inbox = True (opt-in)
      - .agents/bug-inbox.md exists

    Does not filter by fix-<name> prefix — any done spec with an open
    inbox row that names it is drift, regardless of naming convention.
    """
    workflow_path = os.path.join(project_root, ".agents", "workflow.json")
    if not os.path.exists(workflow_path):
        return
    try:
        import json as _json
        with open(workflow_path, encoding="utf-8") as f:
            workflow = _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return
    bugs = (workflow or {}).get("bugs", {})
    if not bugs.get("inbox", False):
        return

    inbox_path = os.path.join(project_root, ".agents", "bug-inbox.md")
    if not os.path.exists(inbox_path):
        return
    try:
        with open(inbox_path, encoding="utf-8") as f:
            inbox_content = f.read()
    except OSError:
        return

    specs_dir = os.path.join(project_root, ".agents", "specs")
    if not os.path.exists(specs_dir):
        return

    # Find open rows mentioning each spec name.
    # Pattern: ^- [ ] <anything> <spec-name> <anything>$
    for filename in sorted(os.listdir(specs_dir)):
        if not filename.endswith(".md") or filename.endswith("-amendments.md"):
            continue
        spec_path = os.path.join(specs_dir, filename)
        try:
            with open(spec_path, encoding="utf-8") as f:
                spec_content = f.read()
        except OSError:
            continue
        # Read status (Chinese field; we accept any prefix per project config).
        status_match = re.search(r">\s*状态:\s*(\S+)", spec_content)
        if not status_match:
            continue
        status = status_match.group(1).strip()
        if status not in ("done", "released"):
            continue
        spec_name = filename[:-3]  # strip ".md"
        # Open inbox row mentioning this spec name.
        pattern = r"^-\s*\[\s*\]\s*[^\n]*?" + re.escape(spec_name) + r"[^\n]*$"
        match = re.search(pattern, inbox_content, re.MULTILINE | re.IGNORECASE)
        if match:
            warnings.append(
                f"inbox drift: {spec_name} ({status}) 有 inbox 行仍 [ ] — "
                "按 inbox ## 同步规则（强制）段第 2 条同步 ([ ] → [x] + 关闭笔记 + commit-sha)"
            )




def _audit_directory_structure(project_root: str, warnings: list[str]) -> None:
    """Check .agents/ for overlapping/deprecated directories per the
    .agents/ Directory Contract in SKILL.md. Advisory only."""
    agents_dir = os.path.join(project_root, ".agents")
    if not os.path.isdir(agents_dir):
        return

    # 1. reports/ overlapping with retros/
    reports_dir = os.path.join(agents_dir, "reports")
    retros_dir = os.path.join(agents_dir, "retros")
    if os.path.isdir(reports_dir) and os.path.isdir(retros_dir):
        report_specs = {f.replace(".md", "") for f in os.listdir(reports_dir) if f.endswith(".md")}
        retro_specs = {f.replace(".md", "") for f in os.listdir(retros_dir) if f.endswith(".md")}
        overlap = report_specs & retro_specs
        if overlap:
            warnings.append(
                f"reports/ has {len(overlap)} specs also in retros/ "
                f"(source of truth is retros/). Archive reports/ to reduce confusion."
            )

    # 2. Deprecated skill-upgrade-proposals/ directory
    proposals_dir = os.path.join(agents_dir, "skill-upgrade-proposals")
    if os.path.isdir(proposals_dir):
        count = len([f for f in os.listdir(proposals_dir) if f.endswith(".md")])
        if count > 0:
            warnings.append(
                f"skill-upgrade-proposals/ is deprecated ({count} files). "
                "Migrate to skill-upgrade-candidates/ per Directory Contract."
            )

    # 3. discovery/ files older than 30 days
    discovery_dir = os.path.join(agents_dir, "discovery")
    if os.path.isdir(discovery_dir):
        import time
        now = time.time()
        old_files = []
        for f in os.listdir(discovery_dir):
            fpath = os.path.join(discovery_dir, f)
            if f.endswith(".md") and os.path.getmtime(fpath) < now - 30 * 86400:
                old_files.append(f)
        if old_files:
            warnings.append(
                f"discovery/ has {len(old_files)} files older than 30 days. "
                "Archive to archive/discovery/ per Directory Contract."
            )

    # 4. Unknown directories not in the Contract
    known_dirs = {
        "specs", "plans", "evidence", "reviews", "retros", "changelogs",
        "intents", "reports", "notes", "archive", "skill-upgrade-candidates",
        "rules", "bugs", "templates", "discovery", "skill-upgrade-proposals",
        # Internal/hidden
        ".vibe-review-pending", ".session-state",
    }
    for entry in os.listdir(agents_dir):
        full = os.path.join(agents_dir, entry)
        if os.path.isdir(full) and entry not in known_dirs and not entry.startswith(".") and entry not in ("project-upgrade-candidates",):
            warnings.append(
                f".agents/{entry}/ is not in the Directory Contract. "
                "Consider migrating to a declared directory or archiving."
            )



def _audit_unbound_rules(project_root: str, warnings: list[str]) -> None:
    """Check .agents/rules/ for TBD/TODO markers and stale proposed rules.

    3/259 retros showed 'rule exists, but is not bound to a gate or command'.
    Rules with TBD/TODO markers sit indefinitely until manually triggered.
    This audit surfaces them so the agent can bind them to a gate or open
    a follow-up spec.
    """
    agents_dir = os.path.join(project_root, ".agents")
    if not os.path.isdir(agents_dir):
        return

    import time
    now = time.time()

    # 1. Scan all .md files in rules/ for TBD/TODO/待定 markers
    rules_dir = os.path.join(agents_dir, "rules")
    tbd_count = 0
    if os.path.isdir(rules_dir):
        tbd_re = re.compile(r"\b(TBD|TODO|待定|follow-up|follow up)\b", re.IGNORECASE)
        for root_dir, _, files in os.walk(rules_dir):
            for f in files:
                if not f.endswith(".md"):
                    continue
                fpath = os.path.join(root_dir, f)
                try:
                    with open(fpath, encoding="utf-8") as handle:
                        text = handle.read()
                except OSError:
                    continue
                matches = tbd_re.findall(text)
                if matches:
                    tbd_count += len(matches)
    if tbd_count > 0:
        warnings.append(
            f".agents/rules/ contains {tbd_count} TBD/TODO/待定 markers. "
            "Consider binding them to a gate or opening a follow-up spec "
            "(rule-binding enforcement, per 2026-07-19 候选 2)."
        )

    # 2. Scan rules/proposed/ for rules older than 30 days
    proposed_dir = os.path.join(rules_dir, "proposed") if os.path.isdir(rules_dir) else None
    if proposed_dir and os.path.isdir(proposed_dir):
        stale_proposed = []
        for f in os.listdir(proposed_dir):
            if not f.endswith(".md"):
                continue
            fpath = os.path.join(proposed_dir, f)
            if os.path.getmtime(fpath) < now - 30 * 86400:
                stale_proposed.append(f)
        if stale_proposed:
            warnings.append(
                f"rules/proposed/ has {len(stale_proposed)} rules older than 30 days "
                "still in proposed status. Consider adopting, rejecting, or binding "
                "them to a gate (rule-binding enforcement, per 2026-07-19 候选 2)."
            )


def _audit_rule_bloat(project_root: str, warnings: list[str]) -> None:
    """Rule lifecycle governance: detect stale or bloated rule files.

    Rules that are never triggered dilute the visibility of important
    rules in the agent's context window. This audit checks:
    1. Total rule file size (lines across all .agents/rules/*.md)
    2. Rules not referenced in the last 5 retros
    Advisory only — does not auto-archive.
    """
    rules_dir = os.path.join(project_root, ".agents", "rules")
    if not os.path.isdir(rules_dir):
        return

    # 1. Total lines across all rule files
    total_lines = 0
    rule_files = []
    for root_dir, _, files in os.walk(rules_dir):
        # Skip archive subdirectory
        if "archive" in root_dir:
            continue
        for f in files:
            if not f.endswith(".md"):
                continue
            fpath = os.path.join(root_dir, f)
            try:
                with open(fpath, encoding="utf-8") as handle:
                    lines = len(handle.readlines())
                total_lines += lines
                rule_files.append((fpath, lines, f))
            except OSError:
                continue

    if total_lines > 2000:
        warnings.append(
            f"Rule bloat: .agents/rules/ has {total_lines} lines across "
            f"{len(rule_files)} files. Agents with limited context windows "
            "may not read all rules. Consider archiving stale rules to "
            ".agents/rules/archive/."
        )

    # 2. Check if rules are referenced in recent retros
    retros_dir = os.path.join(project_root, ".agents", "retros")
    recent_retro_refs = set()
    if os.path.isdir(retros_dir):
        import time
        now = time.time()
        retro_files = []
        for f in os.listdir(retros_dir):
            if not f.endswith(".md"):
                continue
            fpath = os.path.join(retros_dir, f)
            if os.path.getmtime(fpath) > now - 90 * 86400:  # last 90 days
                retro_files.append(fpath)

        rule_id_re = re.compile(r"(R-D-\d+|W-\d+|R-\d+|P-PSQ-\d+)", re.IGNORECASE)
        for rf in retro_files:
            try:
                with open(rf, encoding="utf-8") as handle:
                    text = handle.read()
                for m in rule_id_re.finditer(text):
                    recent_retro_refs.add(m.group(1).upper())
            except OSError:
                continue

    # 3. Find rule IDs defined in rule files not referenced in retros
    if recent_retro_refs and rule_files:
        defined_ids = set()
        rule_id_def_re = re.compile(r"(?:##|###)\s+(R-D-\d+|W-\d+|R-\d+|P-PSQ-\d+)", re.IGNORECASE)
        for fpath, _, _ in rule_files:
            try:
                with open(fpath, encoding="utf-8") as handle:
                    text = handle.read()
                for m in rule_id_def_re.finditer(text):
                    defined_ids.add(m.group(1).upper())
            except OSError:
                continue

        stale_ids = defined_ids - recent_retro_refs
        if len(stale_ids) > 10:
            sample = sorted(stale_ids)[:5]
            warnings.append(
                f"Rule lifecycle: {len(stale_ids)} rule IDs not referenced in "
                f"last 90 days of retros (sample: {', '.join(sample)}). "
                "Consider archiving stale rules to .agents/rules/archive/ "
                "or marking with > 状态: stale."
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
    # Maintainer-side: detect if Skill's own VERSION is behind its git HEAD.
    # Without this check, downstream projects would silently miss new rules.
    skill_drift = check_skill_version_drift(SKILL_DIR)
    if skill_drift:
        warnings.append(skill_drift)

    # 2026-07-12: detect if project's AGENTS.md is outdated (per-stage
    # constraints missing). When the template evolves, existing projects
    # silently miss new constraints until init_project --force is run.
    # Advisory only — agent can decide to migrate manually.
    _audit_agents_outdated(project_root, warnings)

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
    _audit_evidence_commit_freshness(project_root, warnings)
    _audit_reproduction_runtime_present(project_root, warnings)
    _audit_inbox_drift(project_root, warnings)
    _audit_directory_structure(project_root, warnings)
    _audit_unbound_rules(project_root, warnings)
    _audit_rule_bloat(project_root, warnings)
    # Rule 53d: check for pending review markers (bypassed review gates)
    pending_reviews_path = os.path.join(project_root, ".agents", ".vibe-pending-reviews.json")
    if os.path.exists(pending_reviews_path):
        import json as _json
        try:
            with open(pending_reviews_path, "r", encoding="utf-8") as handle:
                entries = _json.load(handle)
            if entries:
                warnings.append(
                    f"Rule 53d: {len(entries)} commit(s) bypassed review gate "
                    "and have not been reviewed. Run `vibe review` to address them, "
                    "or delete .agents/.vibe-pending-reviews.json to dismiss."
                )
        except (OSError, _json.JSONDecodeError):
            pass

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
        # ENFORCE consistency check (Pi Extension vs CLI gate parity)
    from enforce_consistency_check import check_cli_implementations, _find_skill_md
    skill_md = _find_skill_md()
    for w in check_cli_implementations(skill_md):
        warnings.append(f"ENFORCE parity: {w}")

    # ENFORCE consistency check (Pi Extension vs CLI gate parity)
    from enforce_consistency_check import check_cli_implementations, _find_skill_md
    skill_md = _find_skill_md()
    for w in check_cli_implementations(skill_md):
        warnings.append(f"ENFORCE parity: {w}")

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


def _audit_evidence_commit_freshness(project_root: str, warnings: list[str]) -> None:
    """2026-07-10 advisory #1: evidence 记录时的 HEAD 与当前 HEAD 不一致时 WARN.

    motive: Spec record 的 evidence frontmatter 会烧入 `Commit: <hash>`,
    代表 record 这一刻的工作区状态。如果之后又有 commit 推过了该 hash,
    evidence 描述的代码状态可能已经飘移 — 典型场景是用户在 record evidence
    后没立即 commit (dirty + new commit),或者误把 dirty + 旧 commit 当成
    "已验证" 的状态。

    判断与实现边界:
    - 仅 advisory, 不阻塞. 允许"先 record 验证, 再补 commit"的合法工作流.
    - 仅警告 stale: "evidence 的 Commit 仍存在, 但有 ≥1 个 commit 在它前面".
    - 不再警告"Commit 已不存在 / amend 后被丢掉" — 那类场景无法静态判断.
    """
    import re
    import subprocess

    evidence_root = os.path.join(project_root, ".agents", "evidence")
    if not os.path.isdir(evidence_root):
        return
    # 快速判断当前 repo 的 HEAD 与 evidence 是否同根.
    try:
        head = subprocess.run(
            ["git", "-C", project_root, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if head.returncode != 0:
            return
        current_head = head.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return

    stale = []
    commit_re = re.compile(r"^>\s*Commit:\s*([0-9a-f]{7,40})\b", re.MULTILINE)
    for spec_dir in sorted(os.listdir(evidence_root)):
        spec_path = os.path.join(evidence_root, spec_dir)
        if not os.path.isdir(spec_path):
            continue
        for fname in sorted(os.listdir(spec_path)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(spec_path, fname)
            try:
                with open(fpath, encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            m = commit_re.search(content)
            if not m:
                continue
            recorded = m.group(1)
            if recorded == current_head:
                continue
            # recorded 仍然存在?
            try:
                exists = subprocess.run(
                    ["git", "-C", project_root, "cat-file", "-t", recorded],
                    capture_output=True, text=True, timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if exists.returncode != 0:
                continue
            # 落后 N 个 commit?
            try:
                behind = subprocess.run(
                    [
                        "git", "-C", project_root, "rev-list", "--count",
                        f"{recorded}..{current_head}",
                    ],
                    capture_output=True, text=True, timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if behind.returncode == 0 and behind.stdout.strip().isdigit():
                n = int(behind.stdout.strip())
                if n > 0:
                    stale.append((spec_dir, fname, recorded, n))
    if stale:
        sample = ", ".join(f"{s}/{f} (-{n})" for s, f, _, n in stale[:3])
        more = f" (+{len(stale)-3} more)" if len(stale) > 3 else ""
        warnings.append(
            f"evidence 记录时 HEAD 已过期 {len(stale)} 份 (advisory #1 worktree-clean): "
            f"{sample}{more}. evidence 描述的状态可能已不反映当前代码。"
            "重跑 verify 或在 commit message 引用 evidence 文件路径补 commit。"
        )



def _audit_reproduction_runtime_present(project_root: str, warnings: list[str]) -> None:
    """2026-07-10 advisory #2: reproduction evidence should contain
    real runtime traces, not just static inspection output.

    motive: Skill Rule 10/R11 require type=bug specs to record two
    pieces of evidence (reproduction + fix-regression) that PROVE the
    fix changes runtime behaviour. In practice agents record reproduction
    evidence by running `grep` / `ls` / `cat` and pasting the output, which
    passes the "evidence file exists" gate but does not actually prove the
    bug existed in unfixed code. Same shape as Rule 25 ("evidence exists,
    but does not prove the claimed behavior").

    Strategy: scan .agents/evidence/<spec>/verify-reproduction.md. If the
    file does NOT contain any obvious runtime-trace signal — exit code
    keyword (`exit N`, `returncode`), pytest outcome (`PASSED` / `FAILED`
    / `AssertionError`), runtime language keyword (`RuntimeError`,
    `Traceback`, `Error:`), or HTTP status (`HTTP/1.X NNN` /
    `200 OK` / `404`) — surface a WARN.

    Test boundary: this is a heuristic. Agents that hand-author outputs
    without running anything can still satisfy the gate by writing a
    line like `Exit: 1` or `AssertionError`. That is acceptable for an
    advisory — the value is letting the user/agent catch the most
    common failure mode (no runtime trace at all), not blocking it.
    """
    import re
    evidence_root = os.path.join(project_root, ".agents", "evidence")
    if not os.path.isdir(evidence_root):
        return
    # Heuristic patterns that strongly suggest runtime evidence.
    runtime_signals = re.compile(
        r"(?:"
        r"\bexit\s*(?:code)?\s*\d+\b"
        r"|returncode\s*[=:]?\s*\d+"
        r"|\bPASSED\b|\bFAILED\b|\bAssertionError\b"
        r"|\bRuntimeError\b|\bTraceback\b"
        r"|\bError:\s|\bError\s-\s"
        r"|HTTP/[0-9.]+\s+\d{3}"
        r"|\b200\s+OK\b|\b(?:404|500|502|503)\b"
        r")",
        re.IGNORECASE,
    )
    suspect = []
    for spec_dir in sorted(os.listdir(evidence_root)):
        spec_path = os.path.join(evidence_root, spec_dir)
        if not os.path.isdir(spec_path):
            continue
        repro = os.path.join(spec_path, "verify-reproduction.md")
        if not os.path.isfile(repro):
            continue
        try:
            with open(repro, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        if not content.strip():
            suspect.append((spec_dir, "empty file"))
            continue
        if not runtime_signals.search(content):
            suspect.append((spec_dir, "no runtime trace signal"))
    if suspect:
        sample = ", ".join(f"{s} ({reason})" for s, reason in suspect[:3])
        more = f" (+{len(suspect)-3} more)" if len(suspect) > 3 else ""
        warnings.append(
            f"reproduction evidence 缺运行时痕迹 {len(suspect)} 份 (advisory #2 reproduction-runtime-required): "
            f"{sample}{more}. verify-reproduction.md 应含 exit code / 异常 / HTTP 状态等 "
            "运行时输出，不能仅含 grep / ls / cat 静态检查结果。重跑 verify 或补实际命令。"
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
