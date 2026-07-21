#!/usr/bin/env python3
from __future__ import annotations
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
    project_rule_status,
    spec_digest,
    text_digest,
    validate_artifact_name,
)
from policy_sources import unresolved_conflicts
import generate_changelog
import advance_checklist
from workflow_state import (
    configured_commands,
    dependency_cycles,
    ensure_workflow,
    risk_profile,
    spec_metadata,
)
import doctor_project
import generate_plan

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
PLAN_PROGRESS_WARNING_THRESHOLD = 80


def _is_critical_warning(warning):
    critical_keywords = [
        "retro gap",
        "reproduction",
        "runtime trace",
        "missing dependency",
    ]
    w_lower = warning.lower()
    return any(kw in w_lower for kw in critical_keywords)


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
    allow_dirty: bool = False,
    no_checklist: bool = False,
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

    # Pre-advance action checklist (advisory). Surfaces missing evidence,
    # high-risk reviewer-separation, dirty worktree, and stale plan digest
    # before the agent runs into a hard gate failure.
    if not no_checklist:
        advance_checklist.print_advance_checklist(
            project_root, spec_name, content, current_status, new_status,
            profile, workflow, actor, role,
            spec_type=metadata_fields.get("spec_type", ""),
        )

    # Doctor critical warnings advisory (2026-07-12).
    # Soft advisory: doesn't block advance, but surfaces project-level
    # debt so agents don't silently ignore it.
    if new_status and not no_checklist:
        try:
            doctor_result = doctor_project.doctor(project_root)
            critical = [w for w in doctor_result.get("warnings", [])
                        if _is_critical_warning(w)]
            if critical:
                print()
                print(f"🚨 项目有 {len(critical)} 个关键 doctor 问题未处理 (推进 {spec_name} 前建议清理):")
                for w in critical[:3]:
                    print(f"   🔴 {w[:120]}")
                if len(critical) > 3:
                    print(f"   ... 还有 {len(critical) - 3} 个")
                print("   💡 运行: vibe doctor <project> 查看全部")
                print("   (advisory: 不阻塞 advance，但建议优先处理)")
                print()
        except Exception:
            pass

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
        # Rule 15 extension: high-risk (or any risk with required rules) must
        # have the rule stems listed in workflow.json.risk_required_rules[risk]
        # present as adopted project rules before spec-ready is granted.
        rule_blockers = _check_risk_required_rules(project_root, content)
        if rule_blockers:
            print("❌ 高风险 / 项目要求规则的 readiness 未通过:")
            for blocker in rule_blockers:
                print(f"   - {blocker}")
            print("   在 .agents/rules/ 补齐对应 rule 文件并标记为 adopted")
            print("   (或在 workflow.json.risk_required_rules 里移除该 stem)")
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
            # Auto-refresh stale plan digests before blocking (R6.x)
            stale_plan = False
            if not digest_match or digest_match.group(1) != spec_digest(content):
                stale_plan = True
            if not context_match or context_match.group(1) != project_context_digest(project_root):
                stale_plan = True
            if stale_plan:
                refreshed = generate_plan.refresh_plan_digests_only(project_root, spec_name)
                if refreshed:
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
        if not force and not _identity_matches(workflow, "builder", actor, role):
            print("❌ 当前 actor 与项目配置的 builder 不一致")
            return None

    if new_status == "review" and not force:
        if profile["require_verify"]:
            if metadata_fields.get("spec_type") == "bug":
                bug_ok, bug_reason = _has_bug_evidence(
                    project_root, spec_name, content, profile, workflow
                )
                if not bug_ok:
                    if bug_reason:
                        # 2026-07-12d: precise diagnostic (missing vs out-of-order)
                        print(f"❌ Bug 进入审查前证据不完整: {bug_reason}")
                    else:
                        print("❌ Bug 进入审查前需要 reproduction 与 fix-regression 双向证据")
                    print("   💡 标准顺序: in-progress → record reproduction → 修复 bug → record fix-regression → review")
                    return None
                _emit_fix_state_advisory(project_root, spec_name)
            elif not _has_current_evidence(
                project_root, spec_name, content, "verify", profile, workflow
            ):
                print("❌ 进入审查前需要当前规格版本的 verify 证据")
                missing_ac = _missing_acceptance_criteria_references(
                    content,
                    _read_evidence(project_root, spec_name, "verify"),
                    metadata_fields.get("risk", "medium"),
                )
                if missing_ac:
                    print(f"   verify 证据缺少验收标准引用: {', '.join(missing_ac)}")
                # Surface missing Command-Digests explicitly so the agent
                # knows the retry path is `vibe evidence --configured`,
                # not "patch verify.md" (the 2026-07-12 retro anti-pattern).
                missing_digests, configured_cmds = _missing_command_digests(
                    project_root, spec_name, "verify", workflow,
                )
                if missing_digests:
                    print(
                        f"   💡 Missing Command-Digests: "
                        f"{', '.join(missing_digests)}"
                    )
                    print(
                        f"   💡 工作区验证失败时 retry 路径: "
                        f"`vibe evidence {project_root} {spec_name} verify "
                        f"passed <...> --configured` 自动抓 workflow.json "
                        f"verify 命令 digest; "
                        f"或 `--purpose fix-regression --configured` (bug spec)"
                    )
                print("   使用 record_evidence.py 记录 passed 或 not-applicable")
                return None

    if new_status in {"released", "done"} and not force:
        if profile["require_review"]:
            review_ok, review_reason = _has_approved_review(
                project_root, spec_name, content, profile, workflow,
                actor=actor, role=role, force_reason=force_reason or "",
            )
            if not review_ok:
                if review_reason:
                    print(f"❌ {review_reason}")
                    print("   调整 workflow.json.review_separation.required_for 或使用不同身份重审")
                    if "digest" in review_reason.lower() or "摘要" in review_reason:
                        print("   💡 Spec frontmatter 变更会导致 digest 不匹配，需重跑 review-decision")
                    # 主动暴露 override_approver bypass 样板（避免用户撞墙再回头查 SKILL.md）
                    # 当 reason 包含「审查身份与构建者身份相同」时启用
                    if "审查身份与构建者身份相同" in review_reason:
                        print()
                        print("   🛟 Single-actor escape hatch (no --force needed):")
                        print('      vibe advance <spec> released ' + chr(92))
                        print('        --actor <your-identity> ' + chr(92))
                        print('        --role override_approver ' + chr(92))
                        print('        --reason "single-actor self-review acknowledged"')
                        print()
                        print("   三条必备：(a) role 必须是 override_approver；")
                        print("              (b) --reason 非空；")
                        print("              (c) --actor 等于 workflow.json roles.override_approver。")
                else:
                    print("❌ 标记 done 前需要一份结论为 approved 的关联审查记录")
                    print("   先运行 generate_review.py，并由独立审查者填写结论")
                    print()
                    print("   review-decision 必须填齐 5 段必备字段 (缺一段都过不了 review gate):")
                    print("     1. > Decision-Record: <16-hex sha>  (record_review.py 自动算)")
                    print("     2. | 结论: approved                    (或 changes-requested)")
                    print("     3. - 结论依据: <file:line + 业务结论>  (含 grep / call-site / 影响面)")
                    print("     4. - 已核对的验证证据: <evidence path 或 AC 引用>")
                    print("     5. | Reviewer: <identity, 跟 builder 不同 (high-risk) 或相同可走 override>")
                    print()
                    print('   命令: vibe review-decision <project> <spec> approved "<file:line 业务结论>" "<evidence/path 或 AC 引用>" --reviewer <identity>')
                    print("   (advisory: 错误消息列出必填字段，避免 retry 几次才搞清楚 record_review CLI 三参数)")
                    print("<!-- vibe:review_decision_fields_remind: 5_fields -->")
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
            invalid_out_of_scope = _untagged_out_of_scope_items(content)
            if invalid_out_of_scope:
                print("❌ 标记 done 前需要为 Out of Scope 项标注去向")
                for item in invalid_out_of_scope[:5]:
                    print(f"   - {item}")
                print("   使用 [included]、[follow-up: spec-id] 或 [abandoned]")
                return None
            if profile.get("require_observe", False) and not _has_current_evidence(
                project_root, spec_name, content, "observe", profile, workflow
            ):
                print("❌ 标记 done 前需要当前版本的上线观察证据")
                # 2026-07-12c: same digest-mismatch diagnostic as the
                # verify path (ab02457) — surface missing Command-Digests
                # and the --configured retry template so the agent self-
                # corrects instead of reading retro observe-profile output.
                missing_digests, _configured = _missing_command_digests(
                    project_root, spec_name, "observe", workflow,
                    purpose="standard",
                )
                if missing_digests:
                    print(
                        f"   💡 Missing Command-Digests: "
                        f"{', '.join(missing_digests)}"
                    )
                    print(
                        f"   💡 修复: 重跑 `vibe evidence {project_root} "
                        f"{spec_name} observe passed <...> --configured` "
                        f"自动抓 workflow.json observe 命令 digest"
                    )
                return None

    if not force and new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS.get(current_status, set()))) or "无"
        print(f"❌ 不允许的状态流转: {current_status} → {new_status}")
        print("   💡 标准顺序: draft → spec-ready → in-progress → review → released → done")
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
    # Post-advance retro reminder. Lifecycle complete (done is the final
    # stage), so this is the natural moment to nudge the agent to write
    # retro. Without this nudge, agents walk from done back to next-spec
    # and only discover missing retro when `vibe status` lists them via
    # `<!-- vibe:missing_retros: N -->`. Pushing the nudge here keeps the
    # retro writing in the same cognitive context as the just-finished
    # work. Mirrors _print_commit_reminder_at_transition pattern (soft
    # advisory, machine marker, no gate interference). 2026-07-11.
    if new_status == "done" and not force:
        _print_retro_reminder_at_done(project_root, spec_name)
    # Rule 50: machine-readable gate verdict.
    verdict = "pass"
    if force:
        verdict = "forced"
    print(f"<!-- vibe:gate_verdict: {verdict} spec={spec_name} transition={current_status}->{new_status} -->")
    # Soft commit reminder at the workflow boundary. The agent just
    # closed a logical unit of work (status transition); reminding it
    # to commit RIGHT NOW keeps each commit scoped to one logical unit
    # instead of accumulating drive-by edits across multiple transitions.
    # Default reminder is non-blocking; --allow-dirty opts out for cases
    # where the transition genuinely does not involve code (docs-only,
    # rule-only). This is the workflow-natural counterpart to Rule 53's
    # pre-commit verify gate — same rhythm, opposite direction.
    _print_commit_reminder_at_transition(
        project_root, spec_name, current_status, new_status, allow_dirty
    )
    if new_status == "review" and not force:
        _print_plan_progress_reminder(project_root, spec_name)

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


def _is_retro_placeholder(retro_path: str) -> bool:
    """True if the retro file is essentially an unedited template (2026-07-12e).

    Heuristic: count non-placeholder lines. A genuine retro will have
    at least a few lines that are not template defaults.
    """
    try:
        with open(retro_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return True  # can't read → treat as empty

    # Lines that are still template placeholders (parenthesised descriptions)
    placeholder_line = re.compile(r"^\s*(?:[-*]\s*)?\([^)]*\)\s*$")
    # Lines that are section headers or empty
    non_content = re.compile(r"^\s*(?:#{1,3}\s*|$)")

    meaningful_lines = 0
    for line in text.splitlines():
        if non_content.match(line):
            continue
        if placeholder_line.match(line):
            continue
        meaningful_lines += 1

    # If fewer than 5 meaningful lines, it's likely an unedited template
    return meaningful_lines < 5


def _print_retro_reminder_at_done(project_root: str, spec_name: str) -> None:
    """Surface retro writing as the natural next step after spec=done.

    Soft advisory that fires on the done transition (not force). Goal
    is reminder, not gate — agent can still go straight to next spec
    if appropriate. Tied to the new Skill-候选 categorization in
    retrospective.run_retrospective which surfaces 沉淀落点 → Skill
    候选 vs 项目沉淀 decision right at retro-writing time.
    """
    retro_path = os.path.join(
        project_root, ".agents", "retros", f"{spec_name}.md"
    )
    if not os.path.exists(retro_path):
        print()
        print("📝 下一步建议: 写 retro (Rule 54)")
        print(f"   spec 已完成 lifecycle, 现在是复盘时机:")
        print(f'   vibe retrospective {project_root} {spec_name}')
        print("   (会自动跑 self_analyze 找跨项目失败模式 + 列出 Skill 候选 vs 项目沉淀)")
        print("   (advisory: 跳过也可以, 但下次 vibe status 会再次提醒这个 spec 缺 retro)")
        print(f"<!-- vibe:retro_reminder: spec={spec_name} transition=done -->")
        return

    # Retro file exists — check if it's an unedited template (2026-07-12e)
    if _is_retro_placeholder(retro_path):
        print()
        print("❌ Retro 文件存在但内容为空模板 (Rule 54)")
        print(f"   {retro_path}")
        print("   当前 retro 全是占位符, 没有实质内容。请填写后再跳过。")
        print("   必填: 失败模式、目标回顾、做对了什么、做错了什么、结论证据")
        print(f'   vibe retrospective {project_root} {spec_name}')
        print(f"<!-- vibe:retro_placeholder: spec={spec_name} transition=done -->")


def _print_commit_reminder_at_transition(
    project_root: str,
    spec_name: str,
    from_status: str,
    to_status: str,
    allow_dirty: bool,
) -> None:
    """Soft reminder: 'you just advanced a spec — commit your changes'.

    Fires after a successful status transition when the worktree is
    dirty. Default is a non-blocking print; --allow-dirty silences it
    for cases where the transition was docs/rules only.

    The reminder is intentionally embedded at the workflow boundary
    (right after the transition succeeds) rather than as a count-based
    threshold. The point is: every transition is a "logical unit just
    finished" signal, so commit happens at logical units, not after
    the pile gets too big.
    """
    if allow_dirty:
        return
    # Only nudge on forward transitions; backward transitions (rolling
    # back to draft, blocked, cancelled) typically represent rejection
    # or abandonment, not "I just finished work".
    FORWARD = {
        "draft": {"spec-ready", "blocked", "cancelled"},
        "spec-ready": {"in-progress", "blocked", "cancelled"},
        "in-progress": {"review", "released", "done", "blocked", "cancelled"},
        "review": {"released", "done", "in-progress", "blocked"},
        "released": {"done", "blocked"},
    }
    if to_status not in FORWARD.get(from_status, set()):
        return
    # If the transition is purely non-code (e.g. cancelling a spec
    # that was never implemented), dirty files would be unrelated and
    # the reminder would be noise. The cheap heuristic: only remind
    # when dirty files intersect with non-`.agents/` paths — those are
    # almost always the code changes the transition is supposed to be
    # committing.
    import subprocess
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if completed.returncode != 0:
        return
    dirty = [
        line for line in completed.stdout.splitlines()
        if line.strip() and not line[3:].strip().startswith(".agents/")
    ]
    if not dirty:
        return  # Only `.agents/` changes — governance only, not code.
    print()
    print(f"💾 工作区还有 {len(dirty)} 个代码改动未提交。")
    print("   这次状态推进是新逻辑单元的终点，建议立刻:")
    print('     `vibe commit -m "<描述这一批改动>"`  (Rule 53: 跑 verify + review diff)')
    print("   如果本次推进不涉及代码（纯文档 / 规则），加 --allow-dirty 跳过此提醒。")
    print(f"<!-- vibe:commit_reminder: {len(dirty)} files spec={spec_name} transition={from_status}->{to_status} -->")


def _print_plan_progress_reminder(project_root: str, spec_name: str) -> None:
    progress = _plan_progress(project_root, spec_name)
    if not progress or progress["total"] <= 0:
        return
    pct = int(progress["done"] / progress["total"] * 100)
    if pct >= PLAN_PROGRESS_WARNING_THRESHOLD:
        return
    print(
        "⚠️  Plan checkbox progress is "
        f"{progress['done']}/{progress['total']} tasks ({pct}%). "
        "Sync checkboxes or record moved/deferred tasks so vibe status stays trustworthy."
    )


def _plan_progress(project_root: str, spec_name: str) -> dict | None:
    plan_file = os.path.join(project_root, ".agents", "plans", f"{spec_name}.md")
    if not os.path.exists(plan_file):
        return None
    with open(plan_file, encoding="utf-8") as handle:
        content = handle.read()
    return {
        "done": len(re.findall(r"- \[x\]", content)),
        "total": len(re.findall(r"- \[.\]", content)),
    }


def _has_approved_review(
    project_root: str,
    spec_name: str,
    spec_content: str,
    profile: dict,
    workflow: dict,
    actor: str = "",
    role: str = "",
    force_reason: str = "",
) -> tuple[bool, str | None]:
    """Return (ok, reason). reason is non-None only when ok is False and the
    caller may want to surface a specific blocker to the user (currently the
    review-separation case). All other failures collapse to (False, None).
    """
    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    if not os.path.exists(reviews_dir):
        return False, None
    expected_digest = spec_digest(spec_content)
    expected_context = project_context_digest(project_root)
    git = git_snapshot(project_root)
    separation_reason: str | None = None
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
            spec_risk = spec_metadata(spec_content).get("risk", "medium")
            required_for = (
                workflow.get("review_separation", {}).get("required_for")
                or ["high"]
            )
            separated = True
            if spec_risk in required_for:
                builder = _last_actor(project_root, spec_name, "in-progress")
                separated = bool(reviewer and builder and reviewer != builder)
                # Single-actor bypass (2026-07-08c, 提案 1b 方案 B):
                # When the project is single-actor (builder == reviewer),
                # the agent can satisfy review-separation by explicitly
                # declaring `override_approver` role with a non-empty
                # reason. This is the same as `--force --role
                # override_approver --reason "..."` semantically, but
                # preserves the review file gate (all OTHER review checks
                # still run: review file exists, approved, has basis,
                # has evidence, etc.). Without this bypass, every
                # medium-risk bug spec in a single-actor project hits
                # this gate and the agent resorts to `--force`, which
                # ALSO skips all other review checks — a strictly
                # weaker guard. Bypass requires:
                #   1. role == "override_approver" (explicit intent)
                #   2. force_reason non-empty (audit trail preserved)
                #   3. actor matches the workflow's override_approver
                #      identity (forged override rejected by
                #      _identity_matches below)
                if not separated and role == "override_approver" and force_reason.strip():
                    override_approver = (
                        workflow.get("roles", {}).get("override_approver", "")
                    )
                    if actor and override_approver and actor == override_approver:
                        separated = True
                if not separated:
                    separation_reason = (
                        f"审查身份与构建者身份相同；当前 risk 等级 ({spec_risk}) 在 "
                        "workflow.json.review_separation.required_for 中要求独立审查者。"
                        "  单 actor 项目可走 `vibe advance --role override_approver --reason '...'`"
                        " 承认 self-review (无需 --force, 其他 review 检查仍生效)。"
                    )
                    # Discovery hint: 让上层 vibe.py advance 输出 bypass 模板样板
                    # (与 e6d40ed 帮助 epilog 同类做法：把新 gate 主动暴露在错误信息里)
                    print("<!-- vibe:review_separation_bypass_hint: "
                          "reason=self-review; try --role override_approver --reason ... -->")
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
                return True, None
    return False, separation_reason


def _check_risk_required_rules(project_root: str, spec_content: str) -> list[str]:
    """Return a list of blocking messages when this spec violates risk_required_rules.

    A spec violates risk_required_rules when its risk level is one of
    {"low", "medium", "high"} AND workflow.json.risk_required_rules[<risk>]
    contains rule stems that are not present as adopted project rules.

    Returns [] when the spec passes. The function never raises; missing
    files and unreadable rule stems are surfaced as blocking messages
    rather than silently passed.
    """
    risk_match = re.search(r"^>\s*风险:\s*(\S+)", spec_content, re.MULTILINE)
    risk = risk_match.group(1).strip().lower() if risk_match else "medium"
    if risk not in {"low", "medium", "high"}:
        return []
    workflow, _ = ensure_workflow(project_root)
    required = workflow.get("risk_required_rules", {}).get(risk, []) or []
    if not required:
        return []
    rules_dir = os.path.join(project_root, ".agents", "rules")
    blockers: list[str] = []
    for stem in required:
        path = os.path.join(rules_dir, f"{stem}.md")
        if not os.path.exists(path):
            blockers.append(
                f"risk={risk} requires rule file '{stem}.md' under .agents/rules/, "
                "but it does not exist"
            )
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                status = project_rule_status(handle.read())
        except OSError:
            blockers.append(f"rule file '{stem}.md' exists but could not be read")
            continue
        if status != "adopted":
            blockers.append(
                f"risk={risk} requires rule '{stem}.md' to be adopted, "
                f"but its current status is '{status}'"
            )
    return blockers


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


def _allowed_result_for_purpose(purpose: str) -> str:
    """Result values accepted by the evidence frontmatter for a given purpose.

    Standard and fix-regression demand the change worked (`passed` or
    `not-applicable`). Reproduction additionally accepts `failed` because the
    point of reproduction evidence is to prove the bug exists, which by
    definition means the command exits non-zero.
    """
    if purpose == "reproduction":
        return "passed|failed|not-applicable"
    return "passed|not-applicable"


def _snapshot_recent_enough(evidence: str, max_age_seconds: int = 1800) -> bool:
    """Return True if the evidence's Created-At is within `max_age_seconds`.

    2026-07-12c snapshot-staleness-after-commit fix: when an agent
    records evidence and then commits (e.g. commit `.agents/evidence/`
    files), the git HEAD SHA moves but the evidence file content —
    including the captured Created-At and Snapshot fields —
    remains valid evidence. Forcing the agent to re-record evidence
    just to refresh the Snapshot line wastes a round and creates a
    loop (re-recorded evidence → re-commit → snapshot moves again).

    The 30-minute default is intentionally generous: a single
    evidence-record → commit → advance cycle fits well within
    30 minutes, while cross-session stale evidence (>30 min old)
    still triggers the hard gate. Returns False on parse failure
    so callers fall through to the strict equality branch.
    """
    from datetime import datetime, timezone
    match = re.search(r"Created-At:\s*(\S+)", evidence)
    if not match:
        return False
    raw = match.group(1).strip()
    # Accept both 2026-07-12T18:34:21Z and 2026-07-12T18:34:21+00:00
    iso = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return 0 <= age <= max_age_seconds


def _missing_command_digests(
    project_root: str,
    spec_name: str,
    phase: str,
    workflow: dict,
    purpose: str = "standard",
) -> tuple[list[str], list[list[str]]]:
    """Return (missing_digests, expected_commands) when the evidence file
    is present but lacks Command-Digests that match workflow.json's
    configured commands. Returned for diagnostic output at advance gate.

    Returns ([], []) when there is nothing configured or evidence already
    covers the digest set — caller suppresses the diagnostic hint.
    """
    configured = configured_commands(workflow, phase)
    if not configured:
        return [], []
    expected = [command_digest(c) for c in configured]
    evidence_name = phase if purpose == "standard" else f"{phase}-{purpose}"
    evidence_file = os.path.join(
        project_root, ".agents", "evidence", spec_name, f"{evidence_name}.md",
    )
    if not os.path.exists(evidence_file):
        return [], []
    with open(evidence_file, encoding="utf-8") as handle:
        evidence = handle.read()
    digest_match = re.search(
        r"^>\s*Command-Digests:\s*(.+)$", evidence, re.MULTILINE,
    )
    actual = set()
    if digest_match and digest_match.group(1).strip() != "N/A":
        actual = {
            item.strip()
            for item in digest_match.group(1).split(",")
            if item.strip()
        }
    missing = [d for d in expected if d not in actual]
    return missing, configured


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
        # 2026-07-12c: accept evidence written within the last 30 min
        # even when current git HEAD differs. Solves the
        # "record evidence → commit → snapshot stale → re-record → loop"
        # failure mode where the only thing that changed is the commit
        # SHA itself (not the spec / evidence content). Beyond 30 min
        # the gate still rejects — strong consistency is preserved for
        # genuine staleness cases.
        or _snapshot_recent_enough(evidence, max_age_seconds=1800)
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
        and re.search(rf"\|\s*结果:\s*(?:{_allowed_result_for_purpose(purpose)})\s*$", evidence, re.MULTILINE)
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
    return not _missing_acceptance_criteria_references(spec_content, evidence, risk)


def _missing_acceptance_criteria_references(
    spec_content: str,
    evidence: str,
    risk: str,
) -> list[str]:
    if risk == "low":
        return []
    criteria = _acceptance_criteria_ids(spec_content)
    if not criteria:
        return []
    evidence_tokens = set(re.findall(r"\bAC\s*-?\s*(\d+)\b", evidence, re.IGNORECASE))
    return [f"AC{index}" for index in criteria if str(index) not in evidence_tokens]


def _acceptance_criteria_ids(spec_content: str) -> list[int]:
    section = _markdown_section(spec_content, "验收标准")
    if not section:
        section = _markdown_section(spec_content, "Acceptance Criteria")
    if not section:
        return []
    explicit = {
        int(match.group(1))
        for match in re.finditer(r"\bAC\s*-?\s*(\d+)\b", section, re.IGNORECASE)
    }
    if explicit:
        return sorted(explicit)
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


def _read_evidence(project_root: str, spec_name: str, evidence_name: str) -> str:
    evidence_file = os.path.join(
        project_root, ".agents", "evidence", spec_name, f"{evidence_name}.md"
    )
    if not os.path.exists(evidence_file):
        return ""
    with open(evidence_file, encoding="utf-8") as handle:
        return handle.read()


def _untagged_out_of_scope_items(spec_content: str) -> list[str]:
    section = _out_of_scope_section(spec_content)
    if not section:
        return []
    invalid = []
    tag_pattern = re.compile(
        r"^\s*[-*]\s+\[(?:included|abandoned|follow-up:\s*[A-Za-z0-9_.-]+)\](?=\s|[\u4e00-\u9fff]|$)",
        re.IGNORECASE,
    )
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        if "{{" in stripped or "(请" in stripped or not re.search(r"\S", stripped[1:]):
            continue
        if not tag_pattern.match(stripped):
            invalid.append(stripped)
    return invalid


def _out_of_scope_section(spec_content: str) -> str:
    pattern = re.compile(
        r"^#{2,6}\s+.*(?:明确不做什么|Out of Scope).*$"
        r"([\s\S]*?)(?=^#{1,6}\s+|\Z)",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(spec_content)
    return match.group(1) if match else ""


# Bilingual fix-state phrases that make it explicit which code state the
# evidence was captured against. Project authors can include any of these
# in their evidence text to satisfy the advisory; absence triggers a
# warning at spec-ready so the reviewer can decide whether the evidence
# is real or self-fulfilling (Rule 25 'evidence exists, but does not prove
# the claimed behavior'). The advisory is non-blocking: Rule 39 keeps
# review gates advisory by default.
_FIX_BEFORE_PHRASES = (
    # Chinese
    "未应用 fix", "未应用修复",
    "还原到 fix 前", "还原到修复前",
    "fix 前", "修复前",
    # English
    "before fix", "before the fix", "pre-fix",
    "revert", "reverted to", "without the fix",
)
_FIX_AFTER_PHRASES = (
    # Chinese
    "应用 fix", "应用修复",
    "fix 后", "修复后", "带上 fix",
    # English
    "after fix", "after the fix", "with the fix",
    "on fixed commit",
)


def _has_fix_state_anchor(evidence_text: str, kind: str) -> bool:
    """Return True if the evidence text explicitly references the code state

    (fix-before for reproduction, fix-after for fix-regression) it was
    captured against. The check is advisory: it is intentionally permissive
    (any of the bilingual phrases matches) and never blocks the gate. The
    reviewer's job is to decide whether the captured state is real; the
    Skill only ensures the evidence author stated which state they used.
    """
    phrases = _FIX_BEFORE_PHRASES if kind == "before" else _FIX_AFTER_PHRASES
    lowered = evidence_text.lower()
    for phrase in phrases:
        if phrase.lower() in lowered:
            return True
    return False


def _load_evidence_text(project_root: str, spec_name: str, evidence_name: str) -> str:
    """Read an evidence file and return its text. Empty string when missing."""
    path = os.path.join(
        project_root, ".agents", "evidence", spec_name, evidence_name
    )
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""

def _parse_evidence_created_at(evidence_text: str):
    """Extract Created-At timestamp from evidence frontmatter."""
    import re
    from datetime import datetime, timezone
    match = re.search(r">\s*Created-At:\s*(\S+)", evidence_text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _has_bug_evidence(
    project_root: str,
    spec_name: str,
    spec_content: str,
    profile: dict,
    workflow: dict,
) -> tuple[bool, str | None]:
    """Return (ok, reason) where reason is None when ok, or a diagnostic string.

    2026-07-12d: changed from bool-only to (bool, str) so callers can surface
    precise error messages (missing vs out-of-order) instead of a single
    catch-all "need dual evidence" message.
    """
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
    # Use Created-At metadata for ordering instead of filesystem mtime.
    # mtime is fragile: same-second evidence writes, git checkout, and
    # file copies all break mtime ordering. Created-At in the evidence
    # frontmatter is the authoritative logical creation timestamp.
    ordered = False
    if os.path.exists(reproduction_path) and os.path.exists(fixed_path):
        ordered = True  # both exist
        try:
            with open(reproduction_path, encoding="utf-8") as f:
                repro_text = f.read()
            with open(fixed_path, encoding="utf-8") as f:
                fix_text = f.read()
            repro_dt = _parse_evidence_created_at(repro_text)
            fix_dt = _parse_evidence_created_at(fix_text)
            if repro_dt and fix_dt:
                ordered = repro_dt <= fix_dt
            else:
                # Fallback to mtime if Created-At not present (pre-patch evidence)
                ordered = os.path.getmtime(reproduction_path) <= os.path.getmtime(fixed_path)
        except OSError:
            ordered = True  # If we can't read, assume ordered
    if not reproduction:
        return False, "缺少 verify-reproduction.md 证据 (reproduction 场景)"
    if not fixed:
        return False, "缺少 verify-fix-regression.md 证据 (修复后回归测试)"
    if not ordered:
        return False, (
            "reproduction 必须在 fix-regression 之前 record (repro_dt <= fix_dt 失败).\n"
            "   根因: fix-regression 的 Created-At 早于 reproduction, 说明先修了 bug 后补 reproduction.\n"
            "   修法: 删除 verify-fix-regression.md 重新 record 让时间戳更晚,\n"
            "         或删除 verify-reproduction.md 重新 record 让时间戳更早.\n"
            "   标准顺序: in-progress → record reproduction → 修复 bug → record fix-regression → review"
        )
    return True, None


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
        # override_approver can act as builder/reviewer when configured
        if role == "override_approver":
            override = workflow.get("roles", {}).get("override_approver", "").strip()
            if override and override == actor:
                return True
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




def _emit_fix_state_advisory(project_root: str, spec_name: str) -> None:
    """Advisory: warn the reviewer when bug evidence lacks fix-state anchor.

    'evidence exists, but does not prove the claimed behavior' (Rule 25)
    is a known failure mode where a reproduction or fix-regression test
    passes against the wrong code state (e.g. mocks its own function,
    runs against the wrong commit). The Skill cannot run the tests for the
    user (project-specific tooling, snapshot strategy, network mocks), but
    it CAN require the evidence author to state which code state they used.

    This advisory surfaces missing anchors at spec-ready time. It is
    intentionally advisory (Rule 39: default behaviour, opt-out) so the
    reviewer can decide whether the evidence is real or self-fulfilling.
    Never blocks the gate.
    """
    reproduction_text = _load_evidence_text(
        project_root, spec_name, "verify-reproduction.md"
    )
    fixed_text = _load_evidence_text(
        project_root, spec_name, "verify-fix-regression.md"
    )
    repro_ok = _has_fix_state_anchor(reproduction_text, "before")
    fix_ok = _has_fix_state_anchor(fixed_text, "after")
    if repro_ok and fix_ok:
        return
    missing: list[str] = []
    if not repro_ok:
        missing.append('reproduction evidence missing fix-before state anchor')
    if not fix_ok:
        missing.append('fix-regression evidence missing fix-after state anchor')
    print("WARN  Bug evidence fix-state anchor missing (Rule 25 shared failure mode:")
    print("   evidence exists, but does not prove the claimed behavior):")
    for m in missing:
        print("   - " + m)
    print("   Suggestion: include explicit anchors such as commit hash / revert to X / applied fix / with the fix")
    print("   This is advisory and does NOT block the gate. The reviewer must judge whether the evidence truly depends on the fix code.")

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
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Suppress the post-transition 'commit your changes' reminder "
        "when the worktree is dirty. Use for documentation-only or "
        "rule-only advances where there is genuinely no code change to "
        "commit. Most code-bearing transitions should commit instead.",
    )
    args = p.parse_args()

    set_status(
        os.path.abspath(args.project_root),
        args.spec_name,
        args.status,
        args.force,
        args.reason,
        args.actor,
        args.role,
        allow_dirty=args.allow_dirty,
    )
