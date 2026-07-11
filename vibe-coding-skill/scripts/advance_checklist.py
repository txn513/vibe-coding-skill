"""Pre-advance action checklist for `vibe advance`.

Before `vibe advance` runs the hard gate (per-spec risk profile + spec
metadata + evidence freshness), it asks this module for a list of soft
reminders — things the agent should confirm but the gate does not
enforce. Examples:

  - "verify evidence exists but release evidence is missing"
  - "advance to review requires an independent reviewer (current
    --actor matches builder, expected different)"
  - "worktree is dirty; commit before advancing"
  - "advance to released but release evidence not yet recorded"

Output is advisory only. The advance gate itself remains the source of
truth for hard blocking. To suppress, pass `--no-checklist` to
`vibe advance` (escape hatch for emergencies, mirrors the existing
`--no-verify` / `--quick` family).
"""

from __future__ import annotations

import os
import re
from pathlib import Path


# Phase → expected role for the evidence file that should exist.
# Mirrors the table in record_evidence and set_status (line 644). Kept
# in sync by tests in test_workflow.py.
_PHASE_TO_ROLE = {
    "verify": "builder",
    "release": "releaser",
    "observe": "observer",
}


def _evidence_file(project_root: str, spec_name: str, phase: str) -> str:
    return os.path.join(
        project_root, ".agents", "evidence", spec_name, f"{phase}.md"
    )


def _has_evidence_file(project_root: str, spec_name: str, phase: str) -> bool:
    return os.path.exists(_evidence_file(project_root, spec_name, phase))


def _worktree_state(project_root: str) -> str:
    """Return 'clean', 'dirty', or 'not-a-git-repo'."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return "not-a-git-repo"
        return "dirty" if result.stdout.strip() else "clean"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "not-a-git-repo"


def _plan_digest_matches(project_root: str, spec_name: str, spec_content: str) -> bool:
    """True if .agents/plans/<spec>.md exists and its 规格摘要 matches the spec."""
    from common import spec_digest
    plan_file = os.path.join(project_root, ".agents", "plans", f"{spec_name}.md")
    if not os.path.exists(plan_file):
        return False
    with open(plan_file, encoding="utf-8") as handle:
        plan_content = handle.read()
    match = re.search(r"规格摘要:\s*([0-9a-f]{16})", plan_content)
    if not match:
        return False
    return match.group(1) == spec_digest(spec_content)


# Phases the agent must have already recorded for the CURRENT transition.
# Mapping: target status → set of evidence phases that should already exist.
# Verify evidence is required before reaching `review`; release before `done`; observe before `released`.
_TARGET_REQUIRES_EVIDENCE = {
    "spec-ready": set(),
    "in-progress": set(),
    "review": {"verify"},
    "released": {"verify", "release"},
    "done": {"verify", "release"},
    "blocked": set(),
    "cancelled": set(),
    "superseded": set(),
    "draft": set(),
}


def _check_evidence_phase(
    project_root: str, spec_name: str, phase: str, profile: dict,
    target: str, spec_type: str = "",
) -> str | None:
    """Return a checklist hint if `phase` is required for the target status
    but no evidence file exists for it. Returns None otherwise.

    `spec_type="bug"` switches the verify hint to require the dual
    reproduction + fix-regression evidence files (mirrors set_status
    `_has_bug_evidence` logic). Other spec types keep the standard
    single verify.md hint.
    """
    if phase not in _TARGET_REQUIRES_EVIDENCE.get(target, set()):
        return None
    # Phases have a 1:1 mapping to risk-profile require_* flags.
    phase_to_flag = {
        "verify": "require_verify",
        "release": "require_release",
        "observe": "require_observe",
    }
    flag = phase_to_flag.get(phase)
    if not flag or not profile.get(flag, False):
        return None

    # Bug spec needs dual evidence at verify gate: reproduction + fix-regression.
    # Mirrors set_status._has_bug_evidence — single verify.md is not enough.
    if phase == "verify" and spec_type == "bug":
        reproduction_path = os.path.join(
            project_root, ".agents", "evidence", spec_name,
            "verify-reproduction.md",
        )
        fixed_path = os.path.join(
            project_root, ".agents", "evidence", spec_name,
            "verify-fix-regression.md",
        )
        missing = []
        if not os.path.exists(reproduction_path):
            missing.append("reproduction")
        if not os.path.exists(fixed_path):
            missing.append("fix-regression")
        if not missing:
            return None
        missing_list = " + ".join(missing)
        return (
            f"advance 前确认: bug spec verify 双向证据缺失 ({missing_list}); "
            f"需要 `verify-reproduction.md` + `verify-fix-regression.md` 双文件 — "
            f"记录命令: `vibe evidence {project_root} {spec_name} verify passed "
            f"--purpose reproduction --configured` + "
            f"`vibe evidence {project_root} {spec_name} verify passed "
            f"--purpose fix-regression --configured`"
        )

    if _has_evidence_file(project_root, spec_name, phase):
        return None
    role = _PHASE_TO_ROLE[phase]
    return (
        f"advance 前确认: {phase} 证据缺失 — 期望 role=`{role}` 记录 "
        f"`vibe evidence {project_root} {spec_name} {phase} passed <...>`"
    )


def _check_reviewer_separation(
    project_root: str, spec_name: str, spec_content: str,
    actor: str, role: str, profile: dict, workflow: dict,
) -> str | None:
    """High-risk: reviewer must not be the same identity as the builder.

    Only fires when:
    - profile is high-risk
    - transition target is "review" or "done" (i.e. review gate applies)
    - workflow.review_separation.required_for includes "high"
    - actor/role match the configured builder (would mean self-review)
    """
    if profile.get("require_role_separation") is False:
        return None
    review_sep = workflow.get("review_separation", {})
    if "high" not in review_sep.get("required_for", []):
        return None
    if not actor or role != "builder":
        return None
    builder = (workflow.get("roles") or {}).get("builder", "")
    if not builder or builder != actor:
        # Either no builder configured (let real gate fail) OR actor is
        # already independent of the builder (no self-review risk).
        return None
    return (
        "advance 前确认: 高风险 + review gate 要求独立 reviewer；"
        f"当前 --actor=`{actor}` 与 builder=`{builder}` 相同，"
        "请换 session 或 `--role override_approver --reason ...`"
    )


def _check_worktree_state(project_root: str) -> str | None:
    state = _worktree_state(project_root)
    if state == "dirty":
        return (
            "advance 前确认: 工作区有未 commit 改动（`vibe commit` 走 Rule 53 gate）"
        )
    return None


def _check_plan_digest(
    project_root: str, spec_name: str, spec_content: str,
    current_status: str,
) -> str | None:
    """Plan digest mismatch — only relevant when spec is in-progress or later."""
    in_progress_states = {"in-progress", "review", "done"}
    if current_status not in in_progress_states:
        return None
    if _plan_digest_matches(project_root, spec_name, spec_content):
        return None
    return (
        f"advance 前确认: 实施计划 (.agents/plans/{spec_name}.md) 摘要已过期，"
        f"重新生成后再 advance（`vibe plan <project_root> {spec_name}`）"
    )


def _check_release_evidence_pre_done(
    project_root: str, spec_name: str, profile: dict, target: str,
) -> str | None:
    """If user is advancing to done but release evidence not recorded."""
    if target != "done":
        return None
    if not profile.get("require_release", False):
        return None
    if _has_evidence_file(project_root, spec_name, "release"):
        return None
    return (
        "advance 前确认: 目标=done 但 release 证据未 record —— "
        f"先 `vibe evidence {project_root} {spec_name} release passed <...>`"
    )


# Frontend / browser-affecting spec detection (advisory, R55 form-pass-safe).
# Real bug retro: fix-membership-tier-stale-cache 是 localStorage + DOM bug,
# verify 阶段只跑 pytest 1674 pass, 没浏览器实测 → 误判已覆盖。
#
# Heuristic keywords are universal web-dev terms (no project-specific names).
# Trigger only when verify evidence file exists but lacks any browser smoke
# trace — if no verify evidence at all, the upstream evidence-phase check
# already flags that, no need to duplicate.
_FRONTEND_KEYWORDS = re.compile(
    r"frontend/|浏览器|localStorage|DOM|UI 渲染|浏览器实测|browser smoke"
    r"|browser\s*test|chrome|safari|firefox|devtools",
    re.IGNORECASE,
)
_BROWSER_SMOKE_KEYWORDS = re.compile(
    r"browser|chrome|safari|firefox|手动|实测|smoke|devtools"
    r"|playwright|puppeteer|selenium",
    re.IGNORECASE,
)


def _check_frontend_browser_test(
    project_root: str, spec_name: str, spec_content: str, target: str,
) -> str | None:
    """Frontend / browser-affecting spec — verify evidence 应含浏览器实测痕迹。

    Advisory only: 不阻塞 advance, 仅在 spec 命中前端关键词且 verify evidence
    找不到任何 browser smoke 痕迹时, 给 agent 一个提醒。
    """
    if target not in {"review", "released", "done"}:
        return None
    if not _FRONTEND_KEYWORDS.search(spec_content):
        return None
    # Only fire when verify evidence exists (otherwise evidence-phase check
    # upstream already handles "missing verify" — don't duplicate).
    if not _has_evidence_file(project_root, spec_name, "verify"):
        return None
    verify_path = _evidence_file(project_root, spec_name, "verify")
    try:
        with open(verify_path, encoding="utf-8") as handle:
            verify_text = handle.read()
    except OSError:
        return None
    if _BROWSER_SMOKE_KEYWORDS.search(verify_text):
        return None
    return (
        "spec 涉及前端 / 浏览器 (localStorage / DOM / UI), "
        "verify 证据未发现浏览器实测痕迹 (browser / chrome / playwright 等), "
        "建议补充 PC + 移动端浏览器 smoke (advisory, 不阻塞)"
    )


def build_advance_checklist(
    project_root: str,
    spec_name: str,
    spec_content: str,
    current_status: str,
    target_status: str,
    profile: dict,
    workflow: dict,
    actor: str = "",
    role: str = "",
    spec_type: str = "",
) -> list[str]:
    """Return a list of soft reminder strings, in priority order.

    Empty list means "nothing to flag" — advance gate can run as usual.
    """
    hints: list[str] = []

    # 1. Phase-evidence hints (verify / release / observe).
    #    Done for all transitions where the phase is required, because the
    #    agent may have forgotten to record evidence for a phase that was
    #    already enforced by the previous gate.
    for phase in ("verify", "release", "observe"):
        hint = _check_evidence_phase(
            project_root, spec_name, phase, profile, target_status,
            spec_type=spec_type,
        )
        if hint:
            hints.append(hint)

    # 2. Release-evidence-before-done (explicit reminder even if release
    #    evidence is not required by profile — it's a common case).
    hint = _check_release_evidence_pre_done(
        project_root, spec_name, profile, target_status,
    )
    if hint:
        hints.append(hint)

    # 3. Reviewer separation (high-risk only).
    hint = _check_reviewer_separation(
        project_root, spec_name, spec_content, actor, role, profile, workflow,
    )
    if hint:
        hints.append(hint)

    # 4. Worktree cleanliness — only when profile requires it.
    if profile.get("require_clean_worktree", False):
        hint = _check_worktree_state(project_root)
        if hint:
            hints.append(hint)

    # 5. Plan digest freshness — for in-progress or later.
    hint = _check_plan_digest(project_root, spec_name, spec_content, current_status)
    if hint:
        hints.append(hint)

    # 6. Frontend / browser smoke coverage (advisory, 2026-07-10 retro).
    hint = _check_frontend_browser_test(
        project_root, spec_name, spec_content, target_status,
    )
    if hint:
        hints.append(hint)

    return hints


def print_advance_checklist(
    project_root: str,
    spec_name: str,
    spec_content: str,
    current_status: str,
    target_status: str,
    profile: dict,
    workflow: dict,
    actor: str = "",
    role: str = "",
    spec_type: str = "",
) -> int:
    """Print the checklist; return the hint count (0 means no checklist)."""
    hints = build_advance_checklist(
        project_root, spec_name, spec_content, current_status, target_status,
        profile, workflow, actor, role, spec_type=spec_type,
    )
    if not hints:
        return 0
    print()
    print(f"📋 Advance 前 action checklist — {spec_name} ({current_status} → {target_status}):")
    for index, hint in enumerate(hints, 1):
        print(f"   [{index}/{len(hints)}] {hint}")
    print("   (advisory only, 不阻塞 advance; 如确认全部完成可继续)")
    print("   (跳过: `vibe advance --no-checklist`)")
    print(f"<!-- vibe:advance_checklist: count={len(hints)} spec={spec_name} transition={current_status}->{target_status} -->")
    return len(hints)
