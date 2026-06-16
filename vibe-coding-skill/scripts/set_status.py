#!/usr/bin/env python3
"""Update a spec's status without manually editing markdown.

Usage:
    python3 set_status.py <project_root> <spec_name> <status>
    python3 set_status.py <project_root> <spec_name>          # shows current status

Valid statuses: draft, spec-ready, in-progress, review, done, blocked
"""

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from common import (
    atomic_write,
    command_digest,
    git_snapshot,
    project_context_digest,
    spec_digest,
    text_digest,
    validate_artifact_name,
)
from policy_sources import unresolved_conflicts
import generate_changelog
from workflow_state import (
    configured_commands,
    dependency_cycles,
    ensure_workflow,
    risk_profile,
    spec_metadata,
)

VALID_STATUSES = [
    "draft", "spec-ready", "in-progress", "review", "released", "done", "blocked",
    "cancelled", "superseded",
]
ALLOWED_TRANSITIONS = {
    "draft": {"spec-ready", "blocked", "cancelled", "superseded"},
    "spec-ready": {"draft", "in-progress", "blocked", "cancelled", "superseded"},
    "in-progress": {"spec-ready", "review", "blocked", "cancelled", "superseded"},
    "review": {"in-progress", "released", "done", "blocked", "cancelled", "superseded"},
    "released": {"done", "blocked", "cancelled", "superseded"},
    "blocked": {"draft", "spec-ready", "in-progress", "review", "released", "cancelled", "superseded"},
    "done": set(),
    "cancelled": set(),
    "superseded": set(),
}


def set_status(
    project_root: str,
    spec_name: str,
    new_status: str | None = None,
    force: bool = False,
    force_reason: str | None = None,
    actor: str = "",
    role: str = "",
    auto_changelog: bool = True,
    changelog_version: str = "",
) -> str | None:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_file):
        print(f"❌ 规格不存在: {spec_file}")
        return None

    with open(spec_file) as f:
        content = f.read()
    workflow, _ = ensure_workflow(project_root)
    profile = risk_profile(project_root, content)
    metadata_fields = spec_metadata(content)

    # Extract current status
    current = re.search(r">\s*状态:\s*(\S+)", content)
    current_status = current.group(1) if current else "draft"

    if new_status is None:
        # Just show current status
        status_icons = {
            "draft": "📝", "spec-ready": "✅", "in-progress": "🔨",
            "review": "👀", "done": "🎉", "blocked": "🚫"
        }
        icon = status_icons.get(current_status, "❓")
        print(f"{icon} {spec_name}: {current_status}")
        return current_status

    if new_status not in VALID_STATUSES:
        print(f"❌ 无效状态: {new_status}")
        print(f"   有效状态: {', '.join(VALID_STATUSES)}")
        return None

    if new_status == current_status:
        print(f"⚠️  状态未变: {spec_name} 已经是 {current_status}")
        return current_status

    if force and not (force_reason or "").strip():
        print("❌ 使用 --force 时必须通过 --reason 记录绕过原因")
        return None
    if force and (not actor.strip() or role != "override_approver"):
        print("❌ 使用 --force 时必须记录 actor 且 role 必须为 override_approver")
        return None
    if force and not _identity_matches(
        workflow, "override_approver", actor, role
    ):
        print("❌ 当前 actor 无权批准流程绕过")
        return None
    if new_status in {"cancelled", "superseded"} and not (force_reason or "").strip():
        print("❌ cancelled/superseded 必须通过 --reason 记录原因")
        return None

    if new_status == "spec-ready" and not force:
        conflicts = unresolved_conflicts(
            Path(project_root), spec_name=spec_name, severity="high"
        )
        if conflicts:
            print("❌ 存在影响当前规格的未解决高风险规范冲突")
            for conflict in conflicts:
                print(f"   - {conflict.get('id')}: {conflict.get('topic')}")
            print("   先明确适用规则并记录 resolution")
            return None
        if metadata_fields.get("risk_confirmation") != "confirmed":
            print("❌ 需求变更后必须重新确认风险等级")
            print("   使用 confirm_risk.py 记录风险等级和理由")
            return None
        import validate_spec

        validation = validate_spec.validate_spec(spec_file)
        if validation["errors"] or validation["warnings"]:
            print("❌ 规格尚未达到 spec-ready")
            validate_spec.print_result(validation)
            return None

    if new_status == "in-progress" and not force:
        if any(spec_name in cycle for cycle in dependency_cycles(project_root)):
            print("❌ 规格依赖存在循环，必须先修复依赖图")
            return None
        if not _dependencies_done(project_root, metadata_fields["dependencies"]):
            print("❌ 规格依赖尚未全部完成")
            return None
        if profile["require_plan"]:
            plan_file = os.path.join(project_root, ".agents", "plans", f"{spec_name}.md")
            if not os.path.exists(plan_file):
                print("❌ 开始实施前必须先生成并确认实施计划")
                return None
            with open(plan_file, encoding="utf-8") as handle:
                plan_content = handle.read()
            digest_match = re.search(r"规格摘要:\s*([0-9a-f]{16})", plan_content)
            context_match = re.search(r"上下文摘要:\s*([0-9a-f]{16})", plan_content)
            if not digest_match or digest_match.group(1) != spec_digest(content):
                print("❌ 实施计划对应的规格版本已过期，请重新生成计划")
                return None
            if not context_match or context_match.group(1) != project_context_digest(project_root):
                print("❌ 项目规则或上下文已变化，请重新生成计划")
                return None
        if not _identity_matches(workflow, "builder", actor, role):
            print("❌ 当前 actor 与项目配置的 builder 不一致")
            return None

    if new_status == "review" and not force:
        if profile["require_verify"]:
            if metadata_fields.get("spec_type") == "bug":
                if not _has_bug_evidence(
                    project_root, spec_name, content, profile, workflow
                ):
                    print("❌ Bug 进入审查前需要 reproduction 与 fix-regression 双向证据")
                    return None
            elif not _has_current_evidence(
                project_root, spec_name, content, "verify", profile, workflow
            ):
                print("❌ 进入审查前需要当前规格版本的 verify 证据")
                print("   使用 record_evidence.py 记录 passed 或 not-applicable")
                return None

    if new_status in {"released", "done"} and not force:
        if profile["require_review"] and not _has_approved_review(
            project_root, spec_name, content, profile, workflow
        ):
            print("❌ 标记 done 前需要一份结论为 approved 的关联审查记录")
            print("   先运行 generate_review.py，并由独立审查者填写结论")
            return None
        if new_status == "released" and profile["require_release"] and not _has_current_evidence(
            project_root, spec_name, content, "release", profile, workflow
        ):
            print("❌ 标记 released 前需要当前规格版本的 release 证据")
            print("   使用 record_evidence.py 记录 passed 或 not-applicable")
            return None
        if new_status == "done":
            if profile["require_release"] and current_status != "released":
                print("❌ 此风险等级要求先进入 released 状态")
                return None
            if profile.get("require_observe", False) and not _has_current_evidence(
                project_root, spec_name, content, "observe", profile, workflow
            ):
                print("❌ 标记 done 前需要当前版本的上线观察证据")
                return None

    if not force and new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS.get(current_status, set()))) or "无"
        print(f"❌ 不允许的状态流转: {current_status} → {new_status}")
        print(f"   当前可流转到: {allowed}")
        print("   确实需要跳过流程时使用 --force")
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    metadata = re.search(
        r"^>\s*状态:\s*\S+(?:\s*\|\s*创建:\s*([^|]+))?(?:\s*\|\s*更新:\s*(.+))?$",
        content,
        re.MULTILINE,
    )
    created_at = metadata.group(1).strip() if metadata and metadata.group(1) else now
    replacement = f"> 状态: {new_status} | 创建: {created_at} | 更新: {now}"
    if metadata:
        content = content[:metadata.start()] + replacement + content[metadata.end():]
    else:
        content = replacement + "\n\n" + content

    atomic_write(spec_file, content)
    _record_activity(project_root, spec_name, current_status, new_status, actor, role, now)
    if force:
        _record_override(
            project_root,
            spec_name,
            current_status,
            new_status,
            force_reason or "",
            now,
        )
    elif new_status in {"cancelled", "superseded"}:
        _record_override(
            project_root,
            spec_name,
            current_status,
            new_status,
            force_reason or "",
            now,
        )

    transition = f"{current_status} → {new_status}"
    print(f"✅ {spec_name}: {transition}")

    # Auto-generate changelog on a successful released transition.
    # Skipped on --force (user opted out of the workflow) and when
    # auto_changelog is explicitly disabled.
    if new_status == "released" and not force and auto_changelog:
        version = changelog_version.strip() or (
            "unreleased-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        )
        try:
            generate_changelog.generate_changelog(
                project_root, version, force=False, release_group="",
            )
        except Exception as exc:  # noqa: BLE001 — never block the status write
            print(f"⚠️  自动 changelog 失败（状态已推进）: {exc}", file=__import__("sys").stderr)

    return new_status


def _has_approved_review(
    project_root: str,
    spec_name: str,
    spec_content: str,
    profile: dict,
    workflow: dict,
) -> bool:
    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    if not os.path.exists(reviews_dir):
        return False
    expected_digest = spec_digest(spec_content)
    expected_context = project_context_digest(project_root)
    git = git_snapshot(project_root)
    for filename in os.listdir(reviews_dir):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(reviews_dir, filename), encoding="utf-8") as handle:
            review = handle.read()
            has_basis = re.search(r"^-\s*结论依据:\s*\S.+$", review, re.MULTILINE)
            has_evidence = re.search(
                r"^-\s*已核对的验证证据:\s*\S.+$", review, re.MULTILINE
            )
            context_ok = f"上下文摘要: {expected_context}" in review
            snapshot_ok = f"Snapshot: {git.get('snapshot', 'N/A')}" in review
            reviewer_match = re.search(r"Reviewer:\s*([^|\n]+)", review)
            reviewer = reviewer_match.group(1).strip() if reviewer_match else ""
            role_match = re.search(r"Role:\s*([^|\n]+)", review)
            reviewer_role = role_match.group(1).strip() if role_match else ""
            reviewer_ok = _identity_matches(
                workflow, "reviewer", reviewer, reviewer_role
            )
            decision_ok = _review_decision_valid(review)
            separated = True
            if profile["require_role_separation"]:
                builder = _last_actor(project_root, spec_name, "in-progress")
                separated = bool(reviewer and builder and reviewer != builder)
            clean_ok = not profile["require_clean_worktree"] or git["worktree"] == "clean"
            if (
                f"规格: {spec_name}" in review
                and f"规格摘要: {expected_digest}" in review
                and re.search(r"\|\s*结论:\s*approved(?:\s*\||\s*$)", review)
                and has_basis
                and has_evidence
                and context_ok
                and snapshot_ok
                and reviewer_ok
                and decision_ok
                and separated
                and clean_ok
            ):
                return True
    return False


def _record_override(
    project_root: str,
    spec_name: str,
    current_status: str,
    new_status: str,
    reason: str,
    now: str,
) -> None:
    audit_file = os.path.join(project_root, ".agents", "audit.md")
    if os.path.exists(audit_file):
        with open(audit_file, encoding="utf-8") as handle:
            content = handle.read().rstrip()
    else:
        content = "# Workflow Overrides"
    entry = (
        f"\n\n- **{now}** `{spec_name}`: "
        f"`{current_status}` → `{new_status}` — {reason.strip()}\n"
    )
    atomic_write(audit_file, content + entry)


def _has_current_evidence(
    project_root: str,
    spec_name: str,
    spec_content: str,
    phase: str,
    profile: dict,
    workflow: dict,
    purpose: str = "standard",
    require_current_snapshot: bool = True,
    require_configured_commands: bool = True,
) -> bool:
    evidence_name = phase if purpose == "standard" else f"{phase}-{purpose}"
    evidence_file = os.path.join(
        project_root, ".agents", "evidence", spec_name, f"{evidence_name}.md"
    )
    if not os.path.exists(evidence_file):
        return False
    with open(evidence_file, encoding="utf-8") as handle:
        evidence = handle.read()
    expected_digest = spec_digest(spec_content)
    expected_context = project_context_digest(project_root)
    git = git_snapshot(project_root)
    context_ok = f"上下文摘要: {expected_context}" in evidence
    snapshot_ok = (
        not require_current_snapshot
        or f"Snapshot: {git.get('snapshot', 'N/A')}" in evidence
    )
    clean_ok = not profile["require_clean_worktree"] or git["worktree"] == "clean"
    actor_match = re.search(r"Actor:\s*([^|\n]+)", evidence)
    evidence_actor = actor_match.group(1).strip() if actor_match else ""
    if evidence_actor == "未记录":
        evidence_actor = ""
    role_match = re.search(r"Role:\s*([^|\n]+)", evidence)
    evidence_role = role_match.group(1).strip() if role_match else ""
    if evidence_role == "未记录":
        evidence_role = ""
    expected_role = {
        "verify": "builder",
        "release": "releaser",
        "observe": "observer",
    }[phase]
    actor_ok = _identity_matches(
        workflow, expected_role, evidence_actor, evidence_role
    )
    configured = configured_commands(workflow, phase) if require_configured_commands else []
    expected_commands = {command_digest(command) for command in configured}
    digest_match = re.search(r"^>\s*Command-Digests:\s*(.+)$", evidence, re.MULTILINE)
    actual_commands = set()
    if digest_match and digest_match.group(1).strip() != "N/A":
        actual_commands = {
            item.strip() for item in digest_match.group(1).split(",") if item.strip()
        }
    commands_ok = not expected_commands or expected_commands.issubset(actual_commands)
    clauses_ok = True
    if phase == "verify" and purpose == "standard":
        clauses_ok = _verify_evidence_references_acceptance_criteria(
            spec_content, evidence, spec_metadata(spec_content).get("risk", "medium")
        )
    return bool(
        f"规格: {spec_name}" in evidence
        and f"规格摘要: {expected_digest}" in evidence
        and f"阶段: {phase}" in evidence
        and f"用途: {purpose}" in evidence
        and re.search(r"\|\s*结果:\s*(?:passed|not-applicable)\s*$", evidence, re.MULTILINE)
        and context_ok
        and snapshot_ok
        and clean_ok
        and actor_ok
        and commands_ok
        and clauses_ok
    )


def _verify_evidence_references_acceptance_criteria(
    spec_content: str,
    evidence: str,
    risk: str,
) -> bool:
    if risk == "low":
        return True
    criteria = _acceptance_criteria_ids(spec_content)
    if not criteria:
        return True
    evidence_tokens = set(re.findall(r"\bAC\s*-?\s*(\d+)\b", evidence, re.IGNORECASE))
    return all(str(index) in evidence_tokens for index in criteria)


def _acceptance_criteria_ids(spec_content: str) -> list[int]:
    section = _markdown_section(spec_content, "验收标准")
    if not section:
        section = _markdown_section(spec_content, "Acceptance Criteria")
    if not section:
        return []
    count = 0
    for line in section.splitlines():
        stripped = line.strip()
        if re.match(r"^(?:[-*]\s+|\d+[.)]\s+)", stripped):
            if not re.match(r"^[-*]\s*\[[ xX]\]\s+", stripped):
                count += 1
    return list(range(1, count + 1))


def _markdown_section(content: str, title: str) -> str:
    pattern = re.compile(
        rf"^##\s+.*{re.escape(title)}.*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(content)
    return match.group(1) if match else ""


def _has_bug_evidence(
    project_root: str,
    spec_name: str,
    spec_content: str,
    profile: dict,
    workflow: dict,
) -> bool:
    evidence_dir = os.path.join(project_root, ".agents", "evidence", spec_name)
    reproduction_path = os.path.join(evidence_dir, "verify-reproduction.md")
    fixed_path = os.path.join(evidence_dir, "verify-fix-regression.md")
    reproduction = _has_current_evidence(
        project_root,
        spec_name,
        spec_content,
        "verify",
        profile,
        workflow,
        purpose="reproduction",
        require_current_snapshot=False,
        require_configured_commands=False,
    )
    fixed = _has_current_evidence(
        project_root,
        spec_name,
        spec_content,
        "verify",
        profile,
        workflow,
        purpose="fix-regression",
    )
    ordered = (
        os.path.exists(reproduction_path)
        and os.path.exists(fixed_path)
        and os.path.getmtime(reproduction_path) <= os.path.getmtime(fixed_path)
    )
    return reproduction and fixed and ordered


def _dependencies_done(project_root: str, dependencies: list[str]) -> bool:
    for dependency in dependencies:
        path = os.path.join(project_root, ".agents", "specs", f"{dependency}.md")
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as handle:
            match = re.search(r">\s*状态:\s*(\S+)", handle.read())
        if not match or match.group(1) != "done":
            return False
    return True


def _identity_matches(workflow: dict, expected_role: str, actor: str, role: str) -> bool:
    configured = workflow.get("roles", {}).get(expected_role, "").strip()
    if configured:
        return configured == actor and role == expected_role
    if actor or role:
        return role == expected_role
    return True


def _review_decision_valid(review: str) -> bool:
    marker = re.search(r"^>\s*Decision-Record:\s*([0-9a-f]{16})$", review, re.MULTILINE)
    conclusion = re.search(
        r"\|\s*结论:\s*(approved|changes-requested)(?:\s*\||\s*$)", review
    )
    basis = re.search(r"^-\s*结论依据:\s*(\S.+)$", review, re.MULTILINE)
    evidence = re.search(r"^-\s*已核对的验证证据:\s*(\S.+)$", review, re.MULTILINE)
    reviewer = re.search(r"Reviewer:\s*([^|\n]+)", review)
    if not all((marker, conclusion, basis, evidence, reviewer)):
        return False
    payload = "\n".join(
        [
            conclusion.group(1).strip(),
            basis.group(1).strip(),
            evidence.group(1).strip(),
            reviewer.group(1).strip(),
        ]
    )
    return marker.group(1) == text_digest(payload)


def _record_activity(
    project_root: str,
    spec_name: str,
    current_status: str,
    new_status: str,
    actor: str,
    role: str,
    now: str,
) -> None:
    path = os.path.join(project_root, ".agents", "activity.md")
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            existing = handle.read().rstrip()
    else:
        existing = "# Workflow Activity"
    entry = (
        f"\n\n- **{now}** `{spec_name}`: `{current_status}` → `{new_status}`"
        f" | Actor: {actor or '未记录'} | Role: {role or '未记录'}\n"
    )
    atomic_write(path, existing + entry)


def _last_actor(project_root: str, spec_name: str, status: str) -> str:
    path = os.path.join(project_root, ".agents", "activity.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    matches = re.findall(
        rf"`{re.escape(spec_name)}`: `[^`]+` → `{re.escape(status)}`"
        rf"\s*\|\s*Actor:\s*([^|\n]+)",
        content,
    )
    return matches[-1].strip() if matches else ""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Update spec status")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name")
    p.add_argument("status", nargs="?", default=None,
                   help=f"New status: {', '.join(VALID_STATUSES)}")
    p.add_argument("--force", action="store_true", help="Allow non-standard status transition")
    p.add_argument("--reason", default="", help="Required reason when using --force")
    p.add_argument("--actor", default="", help="Person or agent identity")
    p.add_argument("--role", default="", help="Workflow role")
    args = p.parse_args()

    set_status(
        os.path.abspath(args.project_root),
        args.spec_name,
        args.status,
        args.force,
        args.reason,
        args.actor,
        args.role,
    )
