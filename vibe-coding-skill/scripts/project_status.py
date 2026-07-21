#!/usr/bin/env python3
from __future__ import annotations
"""Show a holistic project status overview.

Usage:
    python3 project_status.py <project_root>
"""

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import set_status
import validate_spec
from common import assess_context_freshness, project_context_digest, spec_digest
from policy_sources import pending_review_items, unresolved_conflicts
import doctor_project
from workflow_state import (
    dependency_cycles, ensure_workflow, risk_profile, spec_last_touched, spec_metadata,
)

import archive_status

STATUS_ORDER = [
    "draft", "spec-ready", "in-progress", "review", "released", "blocked",
    "done", "cancelled", "superseded",
]
STATUS_ICONS = {
    "draft": "📝", "spec-ready": "✅", "in-progress": "🔨",
    "review": "👀", "done": "🎉", "blocked": "🚫",
    "cancelled": "⏹", "superseded": "↪",
    "released": "🚀",
}
PLAN_PROGRESS_STALE_STATUSES = {"review", "released", "done"}
PLAN_PROGRESS_WARNING_THRESHOLD = 80


from retro_gap_scan import scan_stale_action_items

def project_status(project_root: str) -> None:
    project_root = os.path.abspath(project_root)
    agents_dir = os.path.join(project_root, ".agents")

    if not os.path.exists(agents_dir):
        print("📭 项目尚未初始化 Vibe Coding。运行 init_project.py 或 onboard_project.py。")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    project_name = os.path.basename(project_root)

    # Read AGENTS.md for project info
    agents_md = os.path.join(project_root, "AGENTS.md")
    phase = "未知"
    if os.path.exists(agents_md):
        with open(agents_md) as f:
            content = f.read()
            m = re.search(r"(?:-\s*)?(?:\*\*)?当前阶段(?:\*\*)?:\s*(.+)", content)
            if m:
                phase = m.group(1).strip()

    print(f"📊 {project_name}")
    print(f"   项目: {project_root}")
    print(f"   阶段: {phase}")
    print(f"   时间: {now}")
    print()

    # Specs
    specs_dir = os.path.join(agents_dir, "specs")
    specs = _list_specs(specs_dir)
    if specs:
        by_status = {}
        for s in specs:
            by_status.setdefault(s["status"], []).append(s)

        agents_dir = os.path.dirname(specs_dir)
        print(f"📋 功能规格 ({len(specs)}):")
        for status in STATUS_ORDER:
            if status in by_status:
                icon = STATUS_ICONS.get(status, "❓")
                names = ", ".join(s["name"] for s in by_status[status])
                print(f"   {icon} {status}: {names}")
        # Per-spec artifact indicator for non-done specs so the agent can
        # see at a glance which specs are missing plan / evidence / review
        # / retro without having to ls each .agents/ subdirectory.
        active_specs = [s for s in specs if s["status"] not in {"done", "cancelled", "superseded"}]
        if active_specs:
            print("   产物完整度:")
            for s in active_specs:
                artifacts = _spec_artifacts(agents_dir, s["name"])
                print(f"     {s['name']:24s} {_spec_artifact_indicator(artifacts)}")
        print()

        # Active / blocked
        active = [s for s in specs if s["status"] in ("in-progress", "review", "released")]
        blocked = [s for s in specs if s["status"] == "blocked"]
        ready = [s for s in specs if s["status"] == "spec-ready"]

        if blocked:
            print(f"🚫 阻塞: {', '.join(s['name'] for s in blocked)}")
        if active:
            print(f"🔨 进行中: {', '.join(s['name'] for s in active)}")
        if ready:
            print(f"✅ 待开发: {', '.join(s['name'] for s in ready)}")
        if not active and not blocked and not ready:
            print(f"💤 无活跃任务")
        print()
    else:
        print("📋 暂无功能规格。")
        print(f"   → create_spec.py <project_root> <名称> 创建第一个")
        print()

    # Plans
    plans_dir = os.path.join(agents_dir, "plans")
    plans = _list_plans(plans_dir)
    if plans:
        total_tasks = sum(p["total"] for p in plans)
        done_tasks = sum(p["done"] for p in plans)
        pct = int(done_tasks / total_tasks * 100) if total_tasks > 0 else 0
        print(f"📐 整体进度: {done_tasks}/{total_tasks} tasks ({pct}%)")
        for p in plans:
            if p["total"] > 0:
                bar = "█" * int(p["done"] / p["total"] * 10)
                print(f"   {bar:10s} {p['name']}: {p['done']}/{p['total']}")
        for warning in _plan_progress_warnings(plans, specs):
            print(f"   ⚠️  {warning}")
        # Workflow-natural commit reminder: every plan-task `- [x]` is a
        # "logical unit just finished" signal. If the worktree is dirty
        # while the agent is mid-plan, the natural rhythm is: tick task,
        # commit, then continue. Surface this only when there is some
        # plan progress AND the worktree has uncommitted code, so it
        # doesn't fire on freshly-initialised projects with empty plans.
        _print_plan_progress_commit_hint(project_root, plans, specs)
        print()

    # Retros
    retros_dir = os.path.join(agents_dir, "retros")
    retro_count = _count_files(retros_dir)
    if retro_count > 0:
        print(f"📝 已完成回顾: {retro_count} 个")
        if retro_count >= 2:
            print(f"   → 可以运行 self_analyze 检查改进机会")
        print()

    # P1+ (2026-07-11): surface unaddressed aggregator candidate counts
    # in `vibe status`. Without this hint, agent has to remember to run
    # `vibe next` / `vibe self-analyze` to see what upgrades are pending.
    # Lightweight one-liner — full details still in vibe next.
    _print_aggregator_count_hint(project_root)

    # Reviews pending
    reviews_dir = os.path.join(agents_dir, "reviews")
    review_count = _count_pending_reviews(reviews_dir)
    if review_count > 0:
        print(f"👀 待审查: {review_count} 个 review 上下文已生成")

    # Changelogs
    changelogs_dir = os.path.join(agents_dir, "changelogs")
    cl_count = _count_files(changelogs_dir)
    if cl_count > 0:
        print(f"📦 已生成 {cl_count} 个 changelog")

    print()
    recommendation = recommend_next(project_root, specs)
    recommendation = _apply_commit_prereq(project_root, recommendation)
    _apply_model_mapping(project_root, recommendation)
    _print_recommendation(recommendation)
    _print_stale_archive_hint(project_root)
    _print_untagged_precipitation_hint(project_root)
    _print_stage_stall_warnings(project_root, specs)
    _print_version_drift_hint(project_root)
    _print_proposed_rules_hint(project_root)
    _print_missing_retro_hint(project_root)
    _print_missing_changelog_hint(project_root)
    _print_uncommitted_work_hint(project_root)
    _print_skill_upgrade_advisory(project_root)
    _print_pending_reviews_hint(project_root)
    _print_all_clean_signal(project_root, specs)
    _print_pending_reviews_hint(project_root)
    _print_all_clean_signal(project_root, specs)
    # Rule 50: machine-readable status summary.
    spec_count = len(specs)
    summary = f"specs={spec_count} recommendation={recommendation.get('action', '')}"
    print(f"<!-- vibe:status_summary: {summary} -->")


# Doctor cache: avoid re-running within 60 seconds
doctor_cache: dict[str, tuple[dict, float]] = {}


def _run_doctor_if_needed(project_root: str, max_age_seconds: int = 60) -> dict:
    import os
    if os.environ.get("VIBE_QUIET_AUTO_DOCTOR"):
        return {"issues": [], "warnings": []}
    """Auto-fire doctor on `vibe next` (方案 A, 2026-07-12).

    Runs doctor and surfaces violations BEFORE recommendation.
    Caches results to avoid re-running on rapid successive calls.
    Returns the doctor result dict for downstream inspection.
    """
    import time
    now = time.time()
    cache_key = str(project_root)
    if cache_key in doctor_cache:
        cached, timestamp = doctor_cache[cache_key]
        if now - timestamp < max_age_seconds:
            return cached

    try:
        result = doctor_project.doctor(project_root)
    except Exception:  # noqa: BLE001
        return {"issues": [], "warnings": []}

    issues = result.get("issues", [])
    warnings = result.get("warnings", [])

    # Categorize warnings by type for better visibility
    categorized = {"critical": [], "warning": [], "info": []}
    for warning in warnings:
        if "retro gap" in warning or "reproduction" in warning:
            categorized["critical"].append(warning)
        elif "stale project guidance" in warning or "HEAD 已过期" in warning:
            categorized["warning"].append(warning)
        else:
            categorized["info"].append(warning)

    if issues:
        print()
        print(f"🚨 发现 {len(issues)} 个问题 (vibe doctor auto-fire):")
        for issue in issues[:5]:
            print(f"   ❌ {issue}")
        if len(issues) > 5:
            print(f"   ... 还有 {len(issues) - 5} 个")
        print()

    # Show critical warnings first
    if categorized["critical"]:
        print()
        print(f"🚨 关键债务 {len(categorized['critical'])} 个 (影响 spec 推进):")
        for warning in categorized["critical"][:3]:
            print(f"   🔴 {warning[:120]}")
        if len(categorized["critical"]) > 3:
            print(f"   ... 还有 {len(categorized['critical']) - 3} 个")
        print("   💡 建议优先处理后再推进新 spec")
        print()

    if categorized["warning"]:
        print()
        print(f"⚠️  警告 {len(categorized['warning'])} 个 (建议清理):")
        for warning in categorized["warning"][:3]:
            print(f"   🟡 {warning[:120]}")
        if len(categorized["warning"]) > 3:
            print(f"   ... 还有 {len(categorized['warning']) - 3} 个")
        print()

    if categorized["info"]:
        print()
        print(f"ℹ️  提示 {len(categorized['info'])} 个:")
        for warning in categorized["info"][:3]:
            print(f"   💡 {warning[:120]}")
        if len(categorized["info"]) > 3:
            print(f"   ... 还有 {len(categorized['info']) - 3} 个")
        print()

    doctor_cache[cache_key] = (result, now)
    return result


# Skill upgrade candidates cache: avoid re-scanning within 60 seconds
_skill_upgrade_cache: dict[str, tuple[list[str], float]] = {}




def _check_retro_upgrade_candidates(project_root: str) -> list[dict]:
    """Scan retros for '沉淀落点' sections that declare Skill/项目 candidates
    but have no matching file in .agents/skill-upgrade-candidates/ or archive/.

    This closes the gap where retro authors write '是否形成 Skill 治理候选: yes'
    but never create the formal candidate file, so vibe next never sees it.
    """
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return []

    # Collect existing candidate names (both active and archived)
    existing_candidates = set()
    for subdir in [".agents/skill-upgrade-candidates", ".agents/archive/skill-upgrade-candidates"]:
        cdir = os.path.join(project_root, subdir)
        if os.path.isdir(cdir):
            for f in os.listdir(cdir):
                if f.endswith(".md"):
                    existing_candidates.add(f.lower())

    candidates = []
    for fname in sorted(os.listdir(retros_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(retros_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue

        # Check for 沉淀落点 section with Skill or project candidate declaration
        has_skill_candidate = bool(
            re.search(r"是否形成 Skill (?:治理)?候选(?:\*\*)?:\s*yes", text, re.IGNORECASE)
        )
        has_project_update = "项目内应更新什么" in text

        if not has_skill_candidate and not has_project_update:
            continue

        # Extract the candidate summary (Skill level)
        summary = "(无摘要)"
        if has_skill_candidate:
            summary_match = re.search(
                r"候选摘要是什么(?:\*\*)?(?:\?|：|:)\s*(.+?)$",
                text,
                re.MULTILINE,
            )
            summary = summary_match.group(1).strip() if summary_match else "(无摘要)"

        # Extract project-level update items
        project_items = []
        if has_project_update:
            project_items = re.findall(
                r"项目内应更新什么(?:\*\*)?(?:\?|：|:).*?\n((?:\s+-.*?\n)+)",
                text,
                re.MULTILINE,
            )
            if project_items:
                # Count the bullet items
                bullets = re.findall(r"\s+-\s+(.+)", project_items[0])
                if bullets and not summary:
                    summary = f"{len(bullets)} 条项目级规则待更新"

        # Determine level
        level = "skill" if has_skill_candidate else "project"

        # Check if a candidate file already exists for this retro
        retro_base = fname.replace(".md", "").lower()
        has_file = any(retro_base in ec for ec in existing_candidates)

        if not has_file:
            candidates.append({
                "retro": fname,
                "summary": summary[:120],
                "level": level,
            })

    return candidates

def _check_pending_skill_upgrades(project_root: str, max_age_seconds: int = 60) -> list[dict]:
    """Check for pending skill upgrade candidates not yet archived.
    
    Returns list of dicts with keys: fname, age_days, status.
    Candidates with 状态: accepted/rejected/已实施 in their header are excluded.
    """
    import time
    cache_key = str(project_root)
    now = time.time()
    if cache_key in _skill_upgrade_cache:
        cached, timestamp = _skill_upgrade_cache[cache_key]
        if now - timestamp < max_age_seconds:
            return cached

    candidates_dir = os.path.join(project_root, ".agents", "skill-upgrade-candidates")
    if not os.path.isdir(candidates_dir):
        return []

    candidates = []
    for fname in sorted(os.listdir(candidates_dir)):
        if not fname.endswith(".md") or not fname.startswith("skill-upgrade-candidate-"):
            continue
        # Skip if already in archive
        archive_dir = os.path.join(project_root, ".agents", "archive", "skill-upgrade-candidates")
        if os.path.exists(os.path.join(archive_dir, fname)):
            continue
        fpath = os.path.join(candidates_dir, fname)
        # Check candidate status header (lifecycle state machine)
        status = "proposed"
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("## ") or line.startswith("# "):
                        break  # past header area
                    m = re.search(r">\s*状态:\s*(\S+)", line)
                    if m:
                        status = m.group(1).lower()
                        break
        except OSError:
            pass
        # Skip candidates that are already decided
        if status in ("accepted", "rejected", "已实施", "已拒绝"):
            continue
        # Calculate age
        try:
            mtime = os.path.getmtime(fpath)
            age_days = (now - mtime) / 86400
        except OSError:
            age_days = 0
        candidates.append({"fname": fname, "age_days": age_days, "status": status})

    _skill_upgrade_cache[cache_key] = (candidates, now)
    return candidates


def _print_skill_upgrade_advisory(project_root: str) -> None:
    """Print advisory about pending skill upgrade candidates with SLA warnings."""
    candidates = _check_pending_skill_upgrades(project_root)
    if not candidates:
        return
    print()
    stale_count = sum(1 for c in candidates if c["age_days"] > 7)
    sla_warning = f" ({stale_count} 个超过 7 天未评审)" if stale_count else ""
    print(f"💡 项目有 {len(candidates)} 个待评审的 Skill 升级候选提案{sla_warning}:")
    for c in candidates:
        age_tag = f" ({int(c['age_days'])}d)" if c["age_days"] > 3 else ""
        status_tag = f" [{c['status']}]" if c["status"] != "proposed" else ""
        print(f"   - .agents/skill-upgrade-candidates/{c['fname']}{age_tag}{status_tag}")
    print("   管理员评审后: 改 状态 为 accepted/rejected, 或移至 archive/")
    fnames = [c["fname"] for c in candidates]
    print("<!-- vibe:pending_skill_upgrades: " + ",".join(fnames) + " -->")


def project_next(project_root: str, args=None) -> dict:
    """Print only the highest-priority governed next action.

    Auto-fires self_analyze (P1+, 2026-07-11). Pass `args` with a
    truthy `--skip-self-analyze` to bypass the analyzer side-channel
    for tests / emergency speed.
    """
    project_root = os.path.abspath(project_root)
    print(f"📍 项目: {project_root}")
    if not os.path.exists(os.path.join(project_root, ".agents")):
        recommendation = _recommendation(
            "接入已有项目或初始化新项目",
            "当前项目还没有 Vibe Coding 工作流状态。",
            checks=["尚未检测到 .agents/ 工作流目录"],
            why_not="现在不能直接给出实施建议，因为项目还没有治理上下文。",
            action_command=_init_command(),
            alternative={
                "action": "先澄清这是新项目还是已有项目",
                "reason": "接入方式会决定初始化还是扫描现有规范。",
            },
        )
    else:
        specs = _list_specs(os.path.join(project_root, ".agents", "specs"))
        recommendation = recommend_next(project_root, specs)
    recommendation = _apply_commit_prereq(project_root, recommendation)
    _apply_model_mapping(project_root, recommendation)
    # P1+ (2026-07-11): auto-fire self_analyze on every `vibe next`.
    # Before this hook, self_analyze only ran inside `vibe retrospective`,
    # so any session that skipped retro silently lost governance signals.
    # Now per-call: read retros, surface governance candidates, persist
    # full report. Cheap (~50ms for typical projects), bypassable via
    # `--skip-self-analyze`. Same audit pattern as the doctor hooks
    # (Rule 50 machine marker on every auto-fired audit).
    #
    # 2026-07-12: auto-fire doctor on every `vibe next` (方案 A).
    # This prevents agents from silently ignoring violations.
    # Doctor runs BEFORE recommendation so violations are surfaced first.
    _run_doctor_if_needed(project_root)
    skip_flag = bool(args and getattr(args, "skip_self_analyze", False))
    skip_us_flag = bool(args and getattr(args, "skip_upgrade_signals", False))
    if not skip_flag:
        recommendation = _maybe_inject_governance_candidates(
            project_root, recommendation, specs,
            skip_self_analyze=skip_flag,
            skip_upgrade_signals=skip_us_flag,
        )
    _print_recommendation(recommendation)
    _print_self_analyze_summary(project_root, skip=skip_flag)
    _print_stale_archive_hint(project_root)
    _print_stale_action_items_hint(project_root)
    _print_version_drift_hint(project_root)
    _print_proposed_rules_hint(project_root)
    _print_missing_retro_hint(project_root)
    _print_missing_changelog_hint(project_root)
    _print_uncommitted_work_hint(project_root)
    _print_skill_upgrade_advisory(project_root)
    _print_pending_reviews_hint(project_root)
    _print_all_clean_signal(project_root, specs)
    _print_pending_reviews_hint(project_root)
    _print_all_clean_signal(project_root, specs)
    return recommendation




def _print_stale_action_items_hint(project_root: str) -> None:
    """Advisory hint (Rule 60): retro action items still in `[ ]` past
    the project's natural review cadence. Same pattern as
    _print_stale_archive_hint — silent when clean, advisory + machine-
    readable marker (Rule 50) when stale items exist.
    """
    if not os.path.exists(os.path.join(project_root, ".agents", "retros")):
        return
    try:
        stale = scan_stale_action_items(project_root, max_cycles=2)
    except Exception:  # noqa: BLE001
        # Hint is advisory; never let a scan error block next.
        return
    if not stale:
        return
    print()
    print(f"📋 Rule 60: 发现 {len(stale)} 个 retro 行动项仍停在 [ ] 状态 (跨过项目最近的 2 个 retro cycle)")
    print("   命令: python scripts/retro_gap_scan.py <project> --audit-stale")
    print("   处置: 把 [ ] 升级为 [active: <rule-id>] / [deferred: <reason>] / [superseded: <id>]")
    print("   (Rule 60: 行动项必须达到 terminal state，不可停留在 [ ])")
    print(f"<!-- vibe:stale_action_items: count={len(stale)} -->")


def _print_untagged_precipitation_hint(project_root: str) -> None:
    """Advisory (Rule 60 extension): retro precipitation entries without R6.1 tag.

    Scans the most recent retro for untagged precipitation entries
    (those lacking [active:]/[deferred:]/[superseded:]/[永不:] tags).
    """
    import glob

    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return

    retro_files = sorted(
        glob.glob(os.path.join(retros_dir, "*.md")),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    if not retro_files:
        return

    try:
        with open(retro_files[0], encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    if "## 沉淀清单" not in content:
        return

    section_match = re.search(r"## 沉淀清单.*?(?=\n## |\Z)", content, re.DOTALL)
    if not section_match:
        return

    tag_pattern = re.compile(r"\[(?:active|deferred|superseded|永不):\s*[^\]]+\]")
    level_pattern = re.compile(r"\(\s*(?:项目级|skill 级|skill-level|project-level)\s*\)")
    active_pattern = re.compile(r"\[active:\s*[^\]]+\]")
    bullets = re.findall(r"^-\s+(.+)$", section_match.group(0), re.MULTILINE)
    untagged = [b for b in bullets if not tag_pattern.search(b)]
    unlevelled = [b for b in bullets if tag_pattern.search(b) and not level_pattern.search(b)]

    # Check for [active: ...] entries in old retros (> 7 days)
    old_active = []
    for path in retro_files[1:]:
        if os.path.getmtime(path) > time.time() - 7 * 86400:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                old_content = f.read()
            if "## 沉淀清单" not in old_content:
                continue
            old_section = re.search(r"## 沉淀清单.*?(?=\\n## |\\Z)", old_content, re.DOTALL)
            if not old_section:
                continue
            old_bullets = re.findall(r"^-\s+(.+)$", old_section.group(0), re.MULTILINE)
            for b in old_bullets:
                if active_pattern.search(b):
                    old_active.append(f"{os.path.basename(path)}: {b[:60]}")
        except OSError:
            continue

    if not untagged and not unlevelled and not old_active:
        return

    print()
    if untagged:
        print(f"📋 发现 {len(untagged)} 条 retro 沉淀条目未带 R6.1 tag:")
        for entry in untagged[:5]:
            print(f"   - {entry[:80]}{'...' if len(entry) > 80 else ''}")
        print("   请补 tag: [active: <id>] / [deferred: <条件>] / [superseded: <id>] / [永不: <理由>]")
    if unlevelled:
        print(f"📋 发现 {len(unlevelled)} 条 retro 沉淀条目未标层级:")
        for entry in unlevelled[:5]:
            print(f"   - {entry[:80]}{'...' if len(entry) > 80 else ''}")
        print("   请补层级: (项目级) 或 (skill 级)")
    if old_active:
        print(f"📋 发现 {len(old_active)} 条 [active: ...] 沉淀在旧 retro (>7 天) 中未推进:")
        for entry in old_active[:5]:
            print(f"   - {entry}")
        print("   请推进: advance spec / 改为 [deferred:] / [superseded:] / [永不:]")
    print("<!-- vibe:untagged_precipitation: count={} -->")


def _print_stale_archive_hint(project_root: str) -> None:
    """Low-priority advisory: stale .agents/ files eligible for archive."""
    if not os.path.exists(os.path.join(project_root, ".agents")):
        return
    try:
        stale = archive_status.find_stale(project_root)
    except Exception:  # noqa: BLE001
        # Hint is advisory; never let a stale-scan error block next.
        return
    if not stale:
        return
    print()
    print(f"🧹 发现 {len(stale)} 个陈旧 .agents/ 文件，应归档 (Rule 54: warning 必须处理，不能忽略)")
    print("   命令: vibe archive-stale <project_root> --apply")
    print("   (Rule 45: 归档是显式动作,Skill 不会自动搬文件)")


def _print_version_drift_hint(project_root: str) -> None:
    """Low-priority advisory: project's recorded Skill version is behind the
    installed version (Rule 52). Same pattern as _print_stale_archive_hint:
    silent when there is no drift, advisory + machine-readable marker
    (Rule 50) when there is.
    """
    if not os.path.exists(os.path.join(project_root, ".agents")):
        return
    project_version = "unknown"
    project_path = os.path.join(project_root, ".agents", ".skill-version")
    if os.path.exists(project_path):
        try:
            with open(project_path, encoding="utf-8") as fp:
                project_version = fp.read().strip() or "unknown"
        except OSError:
            return
    if project_version == "unknown":
        return  # Pre-Rule-52 project; do not back-warn.
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill_version_path = os.path.join(skill_dir, "VERSION")
    skill_version = "unknown"
    if os.path.exists(skill_version_path):
        try:
            with open(skill_version_path, encoding="utf-8") as fp:
                skill_version = fp.read().strip() or "unknown"
        except OSError:
            return
    if skill_version == "unknown" or project_version == skill_version:
        return  # Match or dev install
    print()
    # The drift means the installed Skill has moved past the version this
    # project last recorded. Two consequences:
    #   1. The project agent in this session is still operating against the
    #      OLD rules (because the session loaded the Skill before the
    #      new commit landed). Reloading the session / reloading the Skill
    #      picks up the new rules.
    #   2. The project's `.agents/.skill-version` is now stale; running
    #      `vibe upgrade <project>` rewrites it so the next session's
    #      drift check starts from the right baseline.
    # The hint surfaces both so the agent doesn't just reload and forget.
    print(
        f"⚠️  Skill version drift (Rule 54: 必须处理): project records '{project_version}', "
        f"installed Skill is '{skill_version}' (Rule 52)."
    )
    print(
        "   1) Reload the Skill in the active session (or open a new one) "
        "to pick up the new rules."
    )
    print(
        f"   2) Run `vibe upgrade <project_root>` to rewrite "
        f".agents/.skill-version so future drift checks start from "
        f"'{skill_version}'."
    )
    # Rule 50: machine-readable marker
    print(f"<!-- vibe:skill_version: {skill_version} (project: {project_version}) -->")
    # Also emit a dedicated marker so parsers can distinguish "drift
    # present, project records are stale" from a generic version print.
    print("<!-- vibe:skill_drift: action_required -->")


def _print_aggregator_count_hint(project_root: str) -> None:
    """One-line aggregator candidate count summary for vibe status.

    P1+ (2026-07-11): closes the gap where `vibe status` showed
    retro count but not candidate count. Agents running status to
    check project health should see "X Skill + Y 项目级 待评审"
    as a single line — no need to remember to run `vibe next` /
    `vibe self-analyze` to discover pending upgrades.

    Silent when aggregator pool is empty.
    """
    try:
        aggregated = _aggregate_signals(project_root)
    except Exception:  # noqa: BLE001 — never break vibe status
        return
    skill = len(aggregated.get("skill_candidates", []))
    project_n = len(aggregated.get("project_signals", []))
    if skill == 0 and project_n == 0:
        return
    print(
        f"📚 升级候选: {skill} 条 Skill + {project_n} 条项目级 (待评审)"
    )
    print(
        f"   → 查看详情: vibe next | ack: vibe signal ack <key> | "
        f"列表: vibe signal list"
    )
    print(
        f"<!-- vibe:aggregator_count: skill={skill} project={project_n} -->"
    )


def _print_proposed_rules_hint(project_root: str) -> None:
    """Low-priority advisory: project has rule files in 'proposed' state.

    Rule 18 says generated rules are 'proposed' until explicitly adopted.
    retro -> self_analyze can generate new proposed rules; if they sit
    there un-reviewed, the Skill self-improvement loop stalls. This
    hint surfaces the backlog so the agent can review / adopt / discard
    them rather than letting them accumulate.
    """
    rules_dir = os.path.join(project_root, ".agents", "rules")
    if not os.path.isdir(rules_dir):
        return
    proposed = []
    for entry in sorted(os.listdir(rules_dir)):
        if not entry.endswith(".md"):
            continue
        path = os.path.join(rules_dir, entry)
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            continue
        m = re.search(r">\s*状态:\s*(\S+)", content)
        if m and m.group(1) == "proposed":
            proposed.append(entry[:-3])
    if not proposed:
        return
    print()
    print(
        f"📋 你有 {len(proposed)} 条 proposed 规则待评审 (Rule 18 + Rule 54: 必须决策，不能忽略):"
    )
    for stem in proposed[:10]:
        print(f"   - {stem}")
    if len(proposed) > 10:
        print(f"   ... 还有 {len(proposed) - 10} 条")
    print("   决策: `vibe rule-status <project> <stem> adopted` 或 `abandoned`")
    print(f"<!-- vibe:proposed_rules: {len(proposed)} -->")


def _aggregate_signals(project_root: str, *, skip_self_analyze: bool = False, skip_upgrade_signals: bool = False) -> dict:
    """P1+ architecture (2026-07-11): multi-source signal aggregator.

    Calls each signal-producing module in turn (self_analyze for
    retros, upgrade_signals for cross-source proposal files), then
    dedupes by stable key so the same upgrade candidate never appears
    twice in `vibe next` output even when multiple sources point at it.

    Architecture pattern (2026-07-11 review):
      - each module is interface-isolated (no import-time deps)
      - modules may optionally consume each other via keyword args
        (Pattern A: upgrade_signals accepts self_analyze_findings=None)
      - aggregator is the only place dedup happens
      - new modules can be added without touching existing ones
    """
    raw: dict = {}
    sa_findings: dict = {}
    us_findings: dict = {}

    if not skip_self_analyze:
        try:
            import self_analyze
            sa_findings = self_analyze.analyze(project_root)
            raw["self_analyze"] = sa_findings
        except Exception:
            pass

    if not skip_upgrade_signals:
        try:
            import upgrade_signals as _us
            us_findings = _us.analyze(project_root, self_analyze_findings=sa_findings or None)
            raw["upgrade_signals"] = us_findings
        except Exception:
            pass

    skill_pool: dict = {}
    project_pool: dict = {}

    for cand in sa_findings.get("governance_candidates", []):
        mode = cand.get("failure_mode", "?")
        key = _normalize_key(mode)
        if key not in skill_pool:
            skill_pool[key] = {"key": key, "title": mode, "issue": cand.get("issue", ""), "action": cand.get("action", ""), "priority": cand.get("priority", "medium"), "sources": ["self_analyze"], "level": "skill"}
        elif "self_analyze" not in skill_pool[key]["sources"]:
            skill_pool[key]["sources"].append("self_analyze")

    for sug in sa_findings.get("suggestions", []):
        target = sug.get("target", "?")
        key = _normalize_key(target)
        if key not in project_pool:
            project_pool[key] = {"key": key, "title": f"{sug.get('type', '?')}: {target}", "issue": sug.get("issue", ""), "action": sug.get("action", ""), "priority": sug.get("priority", "medium"), "sources": ["self_analyze"], "level": "project"}
        elif "self_analyze" not in project_pool[key]["sources"]:
            project_pool[key]["sources"].append("self_analyze")

    for sig in us_findings.get("signals", []):
        level = sig.get("level", "mixed")
        key = sig.get("key", "?")
        title = sig.get("title", "?")
        resolved_level = level if level in ("skill", "project") else "project"
        entry = {
            "key": key,
            "title": title,
            "issue": "",
            "action": "",
            "priority": "medium",
            "sources": ["upgrade_signals"],
            "level": resolved_level,
            "source_file": sig.get("source_file", ""),
            "status": sig.get("status", "unknown"),
        }
        # For mixed-level signals probe both pools but default-pool first
        # matches resolved_level (heuristic's best guess), so brand-new
        # keys land in the pool the heuristic intended. For explicit
        # levels only probe the matching pool. Substring dedup against
        # self_analyze failure_modes is allowed in both directions.
        if level == "mixed":
            default_pool = skill_pool if resolved_level == "skill" else project_pool
            other_pool = project_pool if default_pool is skill_pool else skill_pool
            probe_pools = [default_pool, other_pool]
        else:
            probe_pools = [skill_pool if resolved_level == "skill" else project_pool]
        merged = False
        for pool in probe_pools:
            if key in pool:
                if "upgrade_signals" not in pool[key]["sources"]:
                    pool[key]["sources"].append("upgrade_signals")
                merged = True
                break
            for existing_key in list(pool.keys()):
                if len(existing_key) < 6 or len(key) < 6:
                    continue
                if key in existing_key or existing_key in key:
                    if "upgrade_signals" not in pool[existing_key]["sources"]:
                        pool[existing_key]["sources"].append("upgrade_signals")
                    merged = True
                    break
            if merged:
                break
        if not merged:
            probe_pools[0][key] = entry

    # Filter out candidates the agent has acknowledged/dismissed.
    # Real failure mode (2026-07-11): without this filter, candidates
    # accumulate and re-surface on every `vibe next`, leading to
    # fatigue and eventual ignoring — which defeats the whole
    # auto-surface story.
    #
    # Format: `.agents/.acknowledged-candidates.txt` — one key per line.
    # To acknowledge a candidate, the agent writes its key (normalized
    # via _normalize_key) to this file. Comments (# ...) and blank
    # lines are ignored.
    #
    # Auto-mark logic: if a candidate is in BOTH skill_pool and
    # project_pool AND the spec was implemented (no current spec
    # mentions it), it's likely addressed — but this is conservative
    # and not currently auto-triggered; manual ack is the contract.
    ack_keys = _load_acknowledged_candidates(project_root)
    if ack_keys:
        for pool in (skill_pool, project_pool):
            for key in list(pool.keys()):
                if key in ack_keys:
                    pool[key]["acknowledged"] = True
        # Move acknowledged entries to a separate list (still
        # accessible for audit but not surfaced as action candidates)
        acknowledged: list[dict] = []
        for pool in (skill_pool, project_pool):
            for key, cand in list(pool.items()):
                if cand.get("acknowledged"):
                    acknowledged.append(cand)
                    del pool[key]

    for pool in (skill_pool, project_pool):
        for cand in pool.values():
            if len(cand["sources"]) >= 2:
                cand["priority"] = "high" if cand["priority"] != "high" else "high"

    return {
        "skill_candidates": sorted(skill_pool.values(), key=lambda c: (-_priority_rank(c["priority"]), c["title"])),
        "project_signals": sorted(project_pool.values(), key=lambda c: (-_priority_rank(c["priority"]), c["title"])),
        "acknowledged": acknowledged if ack_keys else [],
        "raw": raw,
    }


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]+", "-", text.lower()).strip("-")


def _priority_rank(priority: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(priority, 0)


def _load_acknowledged_candidates(project_root: str) -> set[str]:
    """Load acknowledged candidate keys from .agents/.acknowledged-candidates.txt.

    Returns a set of normalized keys. File format:
        # Comments OK
        evidence-not-reviewed
        rule-taxonomy
        some-other-key-2026-07-11

    If the file doesn't exist or is empty, returns empty set
    (no filtering). Used by _aggregate_signals to suppress
    candidates the agent has already addressed.
    """
    path = os.path.join(project_root, ".agents", ".acknowledged-candidates.txt")
    if not os.path.exists(path):
        return set()
    keys: set[str] = set()
    try:
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Normalize to match aggregator's key format
                keys.add(_normalize_key(line))
    except OSError:
        return set()
    return keys


def _maybe_inject_governance_candidates(
    project_root: str,
    recommendation: dict,
    specs: list[dict] | None = None,
    *,
    skip_self_analyze: bool = False,
    skip_upgrade_signals: bool = False,
) -> dict:
    """P1+ (2026-07-11): weave aggregated signals into next action.

    Calls _aggregate_signals (which fans out to self_analyze +
    upgrade_signals, then dedupes by stable key). When unaddressed
    signals exist AND the current recommendation is not already
    governance-related (drift / freshness / proposed rules / stalled
    specs), promote the top signal into recommendation.alternative so
    the agent has to actively choose to skip it rather than never
    see it.

    Without this hook, self_analyze findings only surface inside
    `vibe retrospective`, which most agents skip. upgrade_signals
    findings live in `.agents/skill-upgrade-candidates*.md` files
    which are never read by any lifecycle command. Both are now
    guaranteed visibility at the canonical decision point.
    """
    aggregated = _aggregate_signals(project_root, skip_self_analyze=skip_self_analyze, skip_upgrade_signals=skip_upgrade_signals)
    skill_candidates = aggregated["skill_candidates"]
    project_signals = aggregated["project_signals"]
    if not skill_candidates and not project_signals:
        return recommendation

    # Persist the aggregated report (cheap write).
    try:
        os.makedirs(
            os.path.join(project_root, ".agents", "reports"),
            exist_ok=True,
        )
        # self_analyze full report (kept under same path for back-compat)
        if aggregated["raw"].get("self_analyze"):
            try:
                import self_analyze as _sa
                _sa.save_report(
                    aggregated["raw"]["self_analyze"],
                    os.path.join(project_root, ".agents", "reports", "self-analyze.md"),
                )
            except Exception:  # noqa: BLE001
                pass
        # upgrade_signals full report
        if aggregated["raw"].get("upgrade_signals"):
            try:
                import upgrade_signals as _us
                _us.save_report(
                    aggregated["raw"]["upgrade_signals"],
                    os.path.join(project_root, ".agents", "reports", "upgrade-signals.md"),
                )
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    current_action = recommendation.get("action", "")
    already_governance = any(
        kw in current_action
        for kw in (
            "Skill 候选", "规则", "proposed", "Skill 版本", "Skill drift",
            "复盘", "反模式",
        )
    )
    if already_governance:
        return recommendation

    top = skill_candidates[0] if skill_candidates else None
    parts: list[str] = []
    if skill_candidates:
        parts.append(f"N={len(skill_candidates)} 条 Skill 候选")
    if project_signals:
        parts.append(f"M={len(project_signals)} 条项目级信号")
    summary = " + ".join(parts) if parts else "0 条候选"

    if top:
        recommendation["alternative"] = {
            "action": f"先评审 {summary}",
            "reason": (
                f"现成候选 (top-1: {top['title']}): {top.get('issue', '')}"
            ),
        }
    else:
        recommendation["alternative"] = {
            "action": f"先评审 {summary}",
            "reason": "项目级沉淀信号待评估",
        }
    if recommendation.get("why_not"):
        recommendation["why_not"] += f"; 同时 {summary} 待评审"
    else:
        recommendation["why_not"] = f"另: {summary} 待评审"
    recommendation["governance_candidates_count"] = (
        len(skill_candidates) + len(project_signals)
    )
    return recommendation


def _print_self_analyze_summary(project_root: str, skip: bool = False) -> None:
    """P1+ (2026-07-11): surface aggregated signals inline.

    Called from project_next() as a FALLBACK for the post-retro
    surfacing (which fires when vibe retrospective writes a retro).
    Even if the agent skipped writing a retro for the just-finished
    spec, vibe next still surfaces whatever is currently in the
    aggregator pool — from prior retros AND from upgrade-candidate
    files. So the "agent completed a feature, but no retro, ran
    vibe next for the next thing instead" path still surfaces
    accumulated signals.

    Shows:
      - Skill-level candidates (top 5 with priority + sources)
      - Project-level signals (top 5 with sources)
      - Both buckets only printed if non-empty
      - Silent when aggregator pool is empty (no spam)

    Pass `skip=True` to bypass for batch/test use.
    """
    if skip:
        return
    try:
        aggregated = _aggregate_signals(project_root)
    except Exception:  # noqa: BLE001 — aggregator failure must not break vibe next
        return
    skill_candidates = aggregated.get("skill_candidates", [])
    project_signals = aggregated.get("project_signals", [])
    if not skill_candidates and not project_signals:
        return
    print()
    if skill_candidates:
        print(
            f"📚 Skill 候选 (P1+, 待管理员评审): {len(skill_candidates)} 条"
        )
        for cand in skill_candidates[:5]:
            mode = cand.get("title", "?")
            issue = cand.get("issue", "")
            sources_str = ",".join(cand.get("sources", []))
            priority_marker = "🔴" if cand.get("priority") == "high" else "🟡"
            print(
                f"   {priority_marker} {mode}: {issue[:100]}{'...' if len(issue) > 100 else ''} "
                f"(来源: {sources_str})"
            )
        if len(skill_candidates) > 5:
            print(f"   ... 还有 {len(skill_candidates) - 5} 条")
    if project_signals:
        print(
            f"📂 项目级信号 (P1+, 待沉淀): {len(project_signals)} 条"
        )
        for sig in project_signals[:5]:
            title = sig.get("title", "?")
            sources_str = ",".join(sig.get("sources", []))
            print(
                f"   - {title} (来源: {sources_str})"
            )
        if len(project_signals) > 5:
            print(f"   ... 还有 {len(project_signals) - 5} 条")
    print(
        f"   命令: vibe self-analyze {project_root} | "
        f"报告: .agents/reports/self-analyze.md"
    )
    print(
        f"<!-- vibe:self_analyze_summary: skill={len(skill_candidates)} "
        f"project={len(project_signals)} -->"
    )


def _missing_retros_for_done_specs(project_root: str) -> list[tuple[str, str]]:
    """Return list of (spec_name, status) for done/released specs without retro.

    Shared logic with _print_missing_retro_hint (DRY).
    """
    specs_dir = os.path.join(project_root, ".agents", "specs")
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(specs_dir) or not os.path.isdir(retros_dir):
        return []
    existing_retros = {
        entry[:-3] for entry in os.listdir(retros_dir)
        if entry.endswith(".md") and entry != ".gitkeep"
    }
    missing = []
    for entry in sorted(os.listdir(specs_dir)):
        if not entry.endswith(".md") or entry.endswith("-amendments.md"):
            continue
        path = os.path.join(specs_dir, entry)
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            continue
        m = re.search(r">\s*状态:\s*(\S+)", content)
        if m and m.group(1) in {"done", "released"}:
            name = entry[:-3]
            if name not in existing_retros:
                missing.append((name, m.group(1)))
    return missing


def _print_missing_retro_hint(project_root: str) -> None:
    """Low-priority advisory: spec is done but has no retro file.

    self_analyze scans .agents/retros/ to find recurring failure modes
    and propose Skill upgrades. If a spec ships without a retro, its
    failure mode is invisible to the Skill and the same mistake will
    happen again. This hint surfaces specs that completed without
    retros so the agent can write them.
    """
    specs_dir = os.path.join(project_root, ".agents", "specs")
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(specs_dir) or not os.path.isdir(retros_dir):
        return
    existing_retros = {
        entry[:-3] for entry in os.listdir(retros_dir)
        if entry.endswith(".md") and entry != ".gitkeep"
    }
    missing = []
    for entry in sorted(os.listdir(specs_dir)):
        if not entry.endswith(".md") or entry.endswith("-amendments.md"):
            continue
        path = os.path.join(specs_dir, entry)
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            continue
        m = re.search(r">\s*状态:\s*(\S+)", content)
        if m and m.group(1) in {"done", "released"}:
            name = entry[:-3]
            if name not in existing_retros:
                missing.append((name, m.group(1)))
    if not missing:
        return
    print()
    print(
        f"📝 {len(missing)} 个已 done/released 的 spec 缺 retro (Rule 54: 必须补写，不能忽略):"
    )
    for name, status in missing[:10]:
        print(f"   - {name} ({status})")
    if len(missing) > 10:
        print(f"   ... 还有 {len(missing) - 10} 个")
    print("   命令: `vibe retrospective <project> <spec-name>` 写 retro")
    print(f"<!-- vibe:missing_retros: {len(missing)} -->")


def _print_missing_changelog_hint(project_root: str) -> None:
    """Soft advisory: spec is released/done but no CHANGELOG row yet.

    Release hygiene: a spec that ships without a CHANGELOG row leaves
    no trace for users / release notes. The hint surfaces such specs.

    2026-07-08 (妙藏 Gemkeep retro): the previous wording read
    "Rule 54: 应补齐", which framed CHANGELOG as a hard
    blocker the moment a spec reached done/released. Agents and
    humans interpreted this as "must fix this 下一步",
    pushing them to backfill CHANGELOGs for the same release window
    they had not yet finalised. CHANGELOGs are user-facing release
    notes that only make sense after the release window is decided;
    surfacing a soft prompt every time a spec done-stamps is noise,
    not actionable. Retro prompts (in _print_missing_retro_hint) stay
    hard because missing retros block self_analyze's failure-mode
    signal; CHANGELOGs do not. The 7-day staleness threshold the
    project uses is correctly kept in the project's own rules, not
    baked into the Skill core.

    The hint remains visible so vibe doctor (diagnostic mode) still
    reports the gap; the wording simply no longer pretends it is a
    priority action.
    """
    specs_dir = os.path.join(project_root, ".agents", "specs")
    changelogs_dir = os.path.join(project_root, ".agents", "changelogs")
    if not os.path.isdir(specs_dir) or not os.path.isdir(changelogs_dir):
        return
    existing = {
        entry[:-3] for entry in os.listdir(changelogs_dir)
        if entry.endswith(".md") and entry != ".gitkeep"
    }
    import time as _time
    _now = _time.time()
    _window = 30 * 86400  # 30 days
    recent_missing = []
    old_missing = 0
    for entry in sorted(os.listdir(specs_dir)):
        if not entry.endswith(".md") or entry.endswith("-amendments.md"):
            continue
        path = os.path.join(specs_dir, entry)
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
            spec_mtime = os.path.getmtime(path)
        except OSError:
            continue
        m = re.search(r">\s*状态:\s*(\S+)", content)
        if m and m.group(1) in {"done", "released"}:
            name = entry[:-3]
            if name not in existing:
                if _now - spec_mtime > _window:
                    old_missing += 1
                else:
                    recent_missing.append((name, m.group(1)))
    total_missing = len(recent_missing) + old_missing
    if total_missing == 0:
        return
    print()
    # 2026-07-08: 软提示语气 ("[可选]" / "某些项目可能定义了一个悬空门槛
    # 如 7 天)。快看不再看起来像"必须上东"。
    # 2026-07-21: 30-day window — recent shown individually, old summarized.
    print(
        f"📝 [可选] {total_missing} 个已 done/released 的 spec 尚未补 CHANGELOG 行。"
        "未补 CHANGELOG 不阻塞 workflow；"
        "仅作为发布门面的软提示，你可能在决定 release 节奏后一并补。"
    )
    for name, status in recent_missing[:10]:
        print(f"   - {name} ({status})")
    if old_missing > 0:
        print(f"   ... 还有 {old_missing} 个超过 30 天的历史欠账（不逐一列出）")
    print("   如需现在补: `vibe changelog <project> <spec-name>`")
    print("   如需调整项目自定缺失门槛: 项目级 rules 表达（如 7 天）。")
    print(f"<!-- vibe:missing_changelogs: {total_missing} -->")


def _uncommitted_count(project_root: str) -> int:
    """Return the current `git status --porcelain` line count, or 0 if not a repo.

    Used by recommend_next to decide whether to weave a commit step into
    the recommendation. The agent is reminded to commit when about to
    advance a spec, not based on a hard count threshold but because the
    next action is an irreversible workflow transition (status advance,
    evidence recording) that should be tied to a clean commit so the
    commit hash in the evidence matches what's on disk.
    """
    if not os.path.isdir(os.path.join(project_root, ".agents")):
        return 0
    import subprocess
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if completed.returncode != 0:
        return 0
    return len([line for line in completed.stdout.splitlines() if line.strip()])


def _classify_uncommitted_files(project_root: str) -> dict:
    """Classify uncommitted files into draft-spec / ready-spec / code.

    Returns a dict with three lists (each entry is the file path string).
    Used by Rule 54 advisory + next action recommendation to avoid the
    misleading "先 commit 当前改动" suggestion when the only dirty file
    is a draft-spec. A draft spec (Status: draft in frontmatter) has not
    passed validate_spec yet — committing it forces an amend cycle the
    next time the spec is updated, which is wasted churn.

    Ready-spec files (Status: spec-ready or later) can be committed as
    normal — the spec is finalised and the commit captures the design
    decision at a stable point.

    Code files (.py / .ts / .js / etc., anything outside .agents/specs/)
    trigger the standard "commit before next irreversible step" advice.

    NOTE: plan documents (.agents/plans/*.md) are NOT split out —
    they are always generated as a complete artifact (no draft state).
    They are tagged as code so the commit advice still fires. Stale
    plans (spec digest changed since plan generation) are detected
    separately by `_classify_stale_plans()` and surfaced via the
    uncommitted-work hint without affecting the commit prereq logic.
    """
    if not os.path.isdir(os.path.join(project_root, ".agents")):
        return {"draft_spec": [], "ready_spec": [], "code": []}
    import re
    import subprocess
    try:
        # --untracked-files=all so we recurse into untracked directories
        # like .agents/specs/ and see individual file paths. Default
        # porcelain collapses untracked dirs to a single line, which
        # breaks spec-file classification.
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"draft_spec": [], "ready_spec": [], "code": []}
    if completed.returncode != 0:
        return {"draft_spec": [], "ready_spec": [], "code": []}

    draft_spec: list[str] = []
    ready_spec: list[str] = []
    code: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        # git status --porcelain: first 2 chars are status, then space, then path.
        # For renames/copies the format is longer ("R  old -> new"), strip the
        # arrow half to get the canonical path.
        path = line[3:].strip() if len(line) > 3 else line
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()

        # Spec files: classify by reading frontmatter Status.
        spec_match = re.match(
            r"^\.agents/specs/(?P<name>[^/]+)\.md$", path
        )
        if spec_match:
            full = os.path.join(project_root, path)
            if not os.path.isfile(full):
                # Path looks like a spec but file is missing (deleted in
                # working tree). Treat as code so the agent gets told to
                # commit the deletion.
                code.append(path)
                continue
            try:
                with open(full, encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                code.append(path)
                continue
            status_m = re.search(r">\s*状态:\s*(\S+)", content)
            current_status = status_m.group(1) if status_m else "draft"
            # Draft = any state before spec-ready. spec-ready+ counts as ready.
            if current_status in {"draft"}:
                draft_spec.append(path)
            else:
                ready_spec.append(path)
            continue

        # Everything else is "code" for Rule 54's purposes (config,
        # source, scripts, docs, plan files, etc.). The next action
        # recommendation still says "commit before irreversible step".
        code.append(path)

    return {"draft_spec": draft_spec, "ready_spec": ready_spec, "code": code}

    return {"draft_spec": draft_spec, "ready_spec": ready_spec, "code": code}


def _classify_stale_plans(project_root: str) -> list[str]:
    """Return a list of `.agents/plans/*.md` paths whose recorded spec
    digest no longer matches the current spec file.

    A stale plan is NOT a draft (plans are always generated as complete
    artifacts), but committing a stale plan alongside other code can
    mislead reviewers who rely on the plan's task list. The hint prints
    a `建议: 先 vibe plan <spec> --force 重新生成` line so the agent
    sees the staleness before committing. This is advisory only —
    `_apply_commit_prereq` does NOT block on stale plans because the
    plan is a reference document, not the source of truth.
    """
    import re
    import subprocess
    plans_dir = os.path.join(project_root, ".agents", "plans")
    if not os.path.isdir(plans_dir):
        return []
    # Import lazily to avoid top-level circular imports.
    try:
        from common import spec_digest, project_context_digest
    except ImportError:
        return []
    stale: list[str] = []
    for entry in sorted(os.listdir(plans_dir)):
        if not entry.endswith(".md"):
            continue
        plan_path = os.path.join(plans_dir, entry)
        try:
            with open(plan_path, encoding="utf-8") as f:
                plan_content = f.read()
        except OSError:
            continue
        # Plan header records `规格摘要: <digest>` — compare against
        # the spec's current digest.
        m = re.search(r"规格摘要:\s*([a-f0-9]+)", plan_content)
        if not m:
            continue
        plan_digest = m.group(1)
        # spec file path is encoded in plan header as
        # `基于规格: .agents/specs/<name>.md`. Extract it; if not
        # present, skip the check (older plan format).
        spec_path_m = re.search(
            r"基于规格:\s*(\.agents/specs/[^|]+?)(?:\s*\||\s*$)",
            plan_content,
        )
        if not spec_path_m:
            continue
        spec_rel = spec_path_m.group(1).strip()
        spec_full = os.path.join(project_root, spec_rel)
        if not os.path.isfile(spec_full):
            continue
        try:
            with open(spec_full, encoding="utf-8") as f:
                spec_content = f.read()
        except OSError:
            continue
        if spec_digest(spec_content) != plan_digest:
            stale.append(f".agents/plans/{entry}")
    return stale


def _apply_commit_prereq(
    project_root: str, recommendation: dict
) -> dict:
    """If worktree is dirty and the next action is an 'advance' transition,
    prefix a commit step into the recommendation.

    The agent should not push a Spec from in-progress to review, or to
    done, while holding a pile of uncommitted edits — the evidence it
    records will not match the commit hash on disk, and any reviewer
    reading the diff will see a mixture of the spec's work plus
    drive-by edits. Weaving the commit step into the recommendation
    makes the natural rhythm: edit -> commit -> advance.

    The integration is intentionally surgical:
    - only applied when the recommendation has an action_command that
      targets a state-changing operation (advance, evidence, amend);
    - the commit step is appended to the action_command via '&&' so the
      agent runs them in order;
    - the action string itself gets a '先 commit 当前改动，再 X' prefix
      so the human-readable line is also honest.

    For low-risk edits (docs, rules) where the user explicitly did not
    want a forced commit, the call sites can pass through `apply=False`.

    Exception: draft-spec-only dirt (rule54-spec-vs-code 候选, 2026-07-10).
    When the only dirty file is a draft spec (Status: draft), the
    "先 commit 当前改动" advice is misleading — committing a not-yet-
    validated spec forces an amend cycle on the next spec update. In
    that case we surface an "先 amend 补全 spec" advice instead. The
    weave step is suppressed (returns recommendation unchanged) so the
    user is not pushed to commit an unstable spec.
    """
    classified = _classify_uncommitted_files(project_root)
    if not any(classified.values()):
        return recommendation
    # If the only dirt is draft spec files, skip the commit weave and
    # surface the "amend first" advice via _print_uncommitted_work_hint
    # rather than prefixing the next-action command. The next action
    # itself still applies (e.g. "vibe amend" or whatever vibe next
    # recommended) — we just don't tell the user to commit first.
    only_draft_spec = (
        classified["draft_spec"]
        and not classified["ready_spec"]
        and not classified["code"]
    )
    cmd = recommendation.get("action_command", "")
    if only_draft_spec or not cmd:
        return recommendation
    # Only weave into state-changing ops, not read-only or workflow-setup
    # commands. The action_command strings we use are predictable.
    WEAVEABLE_PREFIXES = (
        "vibe advance ", "vibe evidence ", "vibe amend ",
    )
    if not any(cmd.startswith(prefix) for prefix in WEAVEABLE_PREFIXES):
        return recommendation
    # Rewrite the recommendation: prefix the action text and chain the
    # commit command so a copy-paste runs both steps in order.
    original_action = recommendation["action"]
    if "commit" not in original_action.lower():
        recommendation = dict(recommendation)
        recommendation["action"] = f"先 commit 当前改动，再 {original_action}"
    recommendation["action_command"] = 'vibe commit --reviewed -m "<describe this batch>" && ' + cmd
    return recommendation


def _print_raw_commit_warning(project_root: str) -> None:
    """Lightweight Rule 53 check: recent commits missing Vibe-Commit trailer."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "--no-merges", "-5", "--format=%h%n%B---END---"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return
        entries = result.stdout.split("---END---")
        raw_shas = []
        for entry in entries:
            entry_lines = entry.strip().splitlines()
            if not entry_lines:
                continue
            sha = entry_lines[0]
            body = "\n".join(entry_lines[1:])
            if "Vibe-Commit:" not in body:
                raw_shas.append(sha)
        if raw_shas:
            print()
            print(
                f"⚠️  最近 {len(raw_shas)} 个 commit 缺 Vibe-Commit trailer "
                f"(可能绕过 vibe commit, Rule 53): {', '.join(raw_shas)}"
            )
            print("   修复: `git reset --soft HEAD~N` + 重做 `vibe commit` (step 1) + "
                  "`vibe commit --reviewed --review-summary '...'` (step 2)")
            print("   严禁 `git commit --amend` 改 message 补 trailer — SHA 会变, trailer 校验失效")
    except (OSError, subprocess.TimeoutExpired):
        return


def _print_uncommitted_work_hint(project_root: str) -> None:
    """Low-priority advisory: worktree has uncommitted changes + raw commit check."""
    if not os.path.isdir(os.path.join(project_root, ".agents")):
        return
    import subprocess
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if completed.returncode != 0:
        return  # Not a git repo, or git unavailable
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return  # Clean worktree
    classified = _classify_uncommitted_files(project_root)
    draft_specs = classified["draft_spec"]
    ready_specs = classified["ready_spec"]
    code_files = classified["code"]
    count = len(lines)
    print()
    # Split output by file class so the agent sees a tailored suggestion
    # for each bucket rather than one generic "先 commit" line that
    # misleads on draft specs (rule54-spec-vs-code 候选, 2026-07-10).
    if draft_specs:
        print(
            f"📝 检测到 {len(draft_specs)} 个 draft spec 未提交 "
            f"(Status: draft, 尚未通过 validate_spec):"
        )
        for path in draft_specs[:10]:
            print(f"   - {path}")
        if len(draft_specs) > 10:
            print(f"   ... 还有 {len(draft_specs) - 10} 个")
        print(
            "   建议: 先 `vibe amend <spec-name>` 补全 spec → spec-ready,"
            " 再和代码改动一起 commit。"
        )
        print(
            "   若确需单独提交 draft spec 文档(罕见): "
            "`vibe commit --no-verify -m 'spec: <name>'`"
        )
        print("<!-- vibe:uncommitted_draft_spec: {} files -->".format(len(draft_specs)))
    if ready_specs or code_files:
        remaining = ready_specs + code_files
        print(
            f"💾 检测到 {len(remaining)} 个未提交改动 "
            f"(Rule 54: 应提交，不能忽略):"
        )
        for path in remaining[:10]:
            print(f"   - {path}")
        if len(remaining) > 10:
            print(f"   ... 还有 {len(remaining) - 10} 个")
        print(
            "   命令: `vibe commit --reviewed -m '...'` "
            "(Rule 53: 审查 diff + 跑 verify)"
        )
        print(
            "   批量提交: 中间 commit 用 `vibe commit --no-verify -m '...'`,"
            " 最终 commit 用 `vibe commit --full-verify -m '...'`"
        )
        print("<!-- vibe:uncommitted_work: {} files -->".format(len(remaining)))
    # Rule 50: machine-readable marker (overall count for compatibility)
    print(f"<!-- vibe:uncommitted_work: total={count} files -->")
    # Also check recent commits for raw git commit bypass (Rule 53 trailer)
    _print_raw_commit_warning(project_root)
    # Stale-plan advisory: spec digest changed since plan was generated.
    # Advisory only — plan is a reference document, not source of truth.
    # The agent sees the warning before committing and can choose to
    # regenerate via `vibe plan <spec>` (no --force needed when status
    # is not done) or commit anyway if the divergence is intentional.
    stale_plans = _classify_stale_plans(project_root)
    if stale_plans:
        print()
        print(
            f"⚠️  检测到 {len(stale_plans)} 个 plan 文件与 spec digest "
            f"不一致 (rule54-spec-vs-code 候选扩展):"
        )
        for path in stale_plans[:10]:
            print(f"   - {path}")
        if len(stale_plans) > 10:
            print(f"   ... 还有 {len(stale_plans) - 10} 个")
        print(
            "   建议: 先 `vibe plan <spec>` 重新生成，再 commit。"
            " 若确需保留旧 plan(罕见): 直接 commit 即可"
        )
        print("<!-- vibe:stale_plans: {} files -->".format(len(stale_plans)))


def _print_stage_stall_warnings(project_root: str, specs: list[dict] | None = None) -> None:
    """Print stage-stall advisories as low-priority hints after primary status / next output."""
    try:
        warnings = stage_stall_warnings(project_root, specs)
    except Exception:  # noqa: BLE001
        # Hint is advisory; never let a stall-scan error block status/next.
        return
    if not warnings:
        return
    print()
    print("⏰ Stage-stall 提醒:")
    for warning in warnings:
        print(f"   - {warning}")
    print("   阈值可在 .agents/workflow.json 的 stage_stall_sla 调整。")




def _last_activity_timestamp(project_root: str) -> datetime | None:
    """Parse the most recent timestamp from .agents/activity.md.

    Returns None if the file is missing or has no parseable timestamps.
    """
    import re
    from datetime import datetime

    path = os.path.join(project_root, ".agents", "activity.md")
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # activity.md timestamps look like: "- **2026-07-13T10:00:00Z** ..."
    timestamps = re.findall(r"-\s*\*\*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC)\*\*", content)
    if not timestamps:
        return None

    try:
        return datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00").replace(" UTC", "+00:00"))
    except ValueError:
        return None



def _check_session_state(project_root: str, threshold_minutes: int = 5) -> None:
    """Print session-state advisory if last activity is stale.

    Called from commit, amend, and other mutating commands so the
    agent sees the advisory even when it skips `vibe next`.
    Rule 66 enforcement: advisory at every entry point.
    """
    from datetime import datetime, timezone

    last = _last_activity_timestamp(project_root)
    if last is None:
        print("🧠 Session 状态提示: 未找到 activity 记录。如果这是新 session, 请先运行 `vibe status` 恢复状态 (Rule 66)。")
        print("<!-- vibe:session_state: no_activity -->")
        return

    minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60
    if minutes > threshold_minutes:
        print(f"🧠 Session 状态提示: 距离上次 activity 已 {int(minutes)} 分钟。")
        print("   如果这是新 session, 请先运行 `vibe status` 恢复状态 (Rule 66)。")
        print("<!-- vibe:session_state: stale_activity -->")


def recommend_next(project_root: str, specs: list[dict] | None = None) -> dict:
    """Return one prioritized next action based on current gates."""
    specs = specs if specs is not None else _list_specs(
        os.path.join(project_root, ".agents", "specs")
    )

    # Rule 66: Session recovery advisory (2026-07-14).
    # When activity.md is empty or the last entry is stale (e.g., >30min),
    # surface a session-state hint at the top of vibe next so the agent
    # knows to re-read project state before proceeding.
    last_activity = _last_activity_timestamp(project_root)
    if last_activity is not None:
        minutes_since = (datetime.now(timezone.utc) - last_activity).total_seconds() / 60
        if minutes_since > 30:
            print(f"🧠 Session 状态提示：距离上次 activity 已 {int(minutes_since)} 分钟。")
            print("   如果这是新 session，请先运行 `vibe status` 恢复状态 (Rule 66)。")
            print("<!-- vibe:session_state: stale_activity -->")
            print()

    # 2026-07-12: missing retro for done specs is the highest-priority
    # next action. A retro is required for every done spec (Rule 54),
    # and skipping it means the failure modes are invisible to
    # self_analyze and the same mistakes will repeat across specs.
    missing_retros = _missing_retros_for_done_specs(project_root)
    if missing_retros:
        return _recommendation(
            "补写 retro (Rule 54: done 后不能跳过)",
            f"{len(missing_retros)} 个已 done 的 spec 缺 retro。"
            "retro 是复盘失败模式、沉淀治理候选的关键输出，不能跳过。",
            checks=[f"{name} ({status})" for name, status in missing_retros],
            why_not="现在不能推进新 spec，因为已有 done spec 的 retro 缺失，"
                   "failure mode 不可见，self_analyze 无法生成治理候选。",
            action_command=f"vibe retrospective {project_root} {missing_retros[0][0]}",
            alternative={
                "action": "先写最老的 missing retro",
                "reason": "越早的 spec 失败模式越可能被遗忘，优先补。",
            },
        )

    # Rule 52: skill version drift is highest-priority because the agent
    # is operating against stale rules until it runs `vibe upgrade` and
    # reloads the Skill. Surfacing it as the top recommendation guarantees
    # the agent sees it even when there is active spec work in flight.
    drift = _skill_drift(project_root)
    if drift:
        return _recommendation(
            "同步 Skill 版本 (Rule 52)",
            f"项目记录的是 '{drift['project_version']}'，但已安装的 Skill 是 "
            f"'{drift['skill_version']}'；当前会话仍按旧规则执行。",
            checks=[
                "项目 .agents/.skill-version 与已安装 Skill VERSION 不一致",
                "已安装 Skill 已推进至少一个 commit",
            ],
            why_not="现在不优先推进 Spec，因为会话加载的是旧规则，可能漏掉新引入的门禁或建议。",
            action_command=f"vibe upgrade {project_root}",
            alternative={
                "action": "先在新版本里重读 SKILL.md 后再继续",
                "reason": "如果会话里已经手动 reload 过 Skill，可以直接 ack 这次 drift。",
            },
        )
    freshness = assess_context_freshness(project_root)
    if (
        freshness.get("missing_timestamp")
        or freshness.get("invalid_timestamp")
        or freshness.get("stale")
    ):
        checks = list(freshness.get("warnings", []))
        return _recommendation(
            "先刷新并确认项目上下文",
            "当前治理上下文可能已过期，继续推进会降低下一步建议的可靠性。",
            checks=checks,
            why_not="现在不优先推进具体 Spec，因为后续门禁和建议都依赖当前项目上下文是可信的。",
            action_command=_context_refresh_command(),
            alternative={
                "action": "先运行 context-refresh 并核对 AGENTS.md",
                "reason": "至少先把技术栈、当前阶段和待人工确认项同步到最新。",
            },
        )
    # Rule 54: doctor warnings must be acted on, not just displayed.
    # If there are high-priority warnings (proposed rules, stage stall),
    # surface them as the next action so the agent cannot silently skip.
    proposed_rules = _count_proposed_rules(project_root)
    if proposed_rules > 0:
        return _recommendation(
            f"评审并决策 {proposed_rules} 条 proposed 规则 (Rule 54)",
            f"retro 沉淀的规则尚未被采纳或废弃，self_analyze 看不到这些失败模式。",
            checks=[f"{proposed_rules} 条规则处于 proposed 状态"],
            why_not="现在不优先推进 Spec，因为未评审的规则意味着治理闭环未完成。",
            action_command=f"vibe rule-status <project_root> <stem> adopted|abandoned",
            alternative={
                "action": "先批量浏览 proposed 规则内容",
                "reason": "如果不确定是否采纳，先读一遍再决定。",
            },
        )
    # Retro中声明但未提取的升级候选（Skill级 + 项目级）
    retro_candidates = _check_retro_upgrade_candidates(project_root)
    if retro_candidates:
        rc = retro_candidates[0]
        level_label = "Skill" if rc["level"] == "skill" else "项目级"
        target_dir = ".agents/skill-upgrade-candidates" if rc["level"] == "skill" else ".agents/project-upgrade-candidates"
        skill_count = sum(1 for c in retro_candidates if c["level"] == "skill")
        proj_count = sum(1 for c in retro_candidates if c["level"] == "project")
        counts = []
        if skill_count:
            counts.append(f"{skill_count} 个 Skill 级")
        if proj_count:
            counts.append(f"{proj_count} 个项目级")
        counts_str = ", ".join(counts)
        return _recommendation(
            f"提取 retro 中的{level_label}升级候选 (来源: {rc['retro']})",
            f"retro 沉淀了 {counts_str} 升级候选但未创建正式文件。"
            f"摘要: {rc['summary']}",
            checks=[f"{len(retro_candidates)} 个 retro 声明候选但未提取"],
            why_not="未提取的候选不会出现在 vibe next 中，同样的失败模式会在后续 spec 中重复出现。",
            action_command=f"mkdir -p {target_dir} && cp .agents/retros/{rc['retro']} {target_dir}/",
            alternative={
                "action": "先读 retro 沉淀落点再决定是否提取",
                "reason": "如果候选已过时或 over-engineering，在 retro 中标记 'no' 即可。",
            },
        )

    # Pending skill/project upgrade candidates from retros
    pending_upgrades = _check_pending_skill_upgrades(project_root)
    if pending_upgrades:
        return _recommendation(
            f"评审 {len(pending_upgrades)} 个待处理的升级候选提案",
            f"retro 沉淀的升级候选尚未被评审或归档。这些提案来自实战反思，"
            "不处理意味着同样的失败模式会在后续 spec 中重复出现。",
            checks=[f"{len(pending_upgrades)} 个候选在 .agents/skill-upgrade-candidates/"],
            why_not="现在不优先推进 Spec，因为未评审的升级候选意味着治理闭环未完成。",
            action_command=f"ls .agents/skill-upgrade-candidates/",
            alternative={
                "action": "先读最新候选内容再决定是否升级",
                "reason": "如果候选是 over-engineering，归档即可；如果是合理改进，升级到 Skill。",
            },
        )

    stall_warnings = stage_stall_warnings(project_root, specs)
    if stall_warnings:
        return _recommendation(
            "处理停滞的 Spec (Rule 54)",
            f"有 spec 在当前阶段停留超过 risk SLA，可能需要推进、阻塞或取消。",
            checks=stall_warnings[:3],
            why_not="停滞的 spec 占用注意力但不产出价值，应该先决策它的去向。",
            action_command=_status_command(),
            alternative={
                "action": "先确认停滞原因",
                "reason": "如果是等外部依赖，可以标记 blocked；如果是需求变了，可以取消。",
            },
        )

    conflicts = unresolved_conflicts(Path(project_root), severity="high")
    if conflicts:
        conflict = conflicts[0]
        return _recommendation(
            "解决高风险规范冲突",
            "现有项目规则与新增治理要求尚未明确谁优先，继续推进可能造成错误变更。",
            blocker=f"{conflict.get('id')}: {conflict.get('topic')}",
            checks=["已检测到影响当前流程的 high 级 open conflict"],
            why_not="现在不能进入规格推进或实施，因为适用规则还不明确。",
            action_command=_policy_resolve_command(conflict.get("id", "<conflict-id>")),
            alternative={
                "action": "先补充冲突 resolution 记录",
                "reason": "至少要先明确谁优先，后续门禁才有依据。",
            },
        )
    review_items = pending_review_items(Path(project_root))
    if review_items:
        item = review_items[0]
        return _recommendation(
            item.get("action", "确认既有项目规范差异"),
            f"接管已有项目后，{item.get('title')} 还没有完成治理确认。",
            blocker=f"{item.get('title')}: {item.get('path')} -> {item.get('target', '待判断')}",
            checks=[
                f"待确认来源 {len(review_items)} 项",
                "现有项目规范优先级高于 Skill 默认规则",
                item.get("reason", ""),
                "确认草稿已生成: .agents/policy-confirmations.md",
            ],
            why_not="现在不优先推进实施，因为还没有确认这些既有规范是否会改变后续门禁或命令入口。",
            action_command="vibe policy-scan <project_root>  # 先列出所有冲突，再编辑 .agents/policy-confirmations.md",
            alternative={
                "action": "先填写 policy-confirmations 草稿中的该来源决策",
                "reason": "如果主路径暂时做不完，至少先把 authority、落点和冲突判断写清楚。",
            },
        )
    cycles = dependency_cycles(project_root)
    if cycles:
        return _recommendation(
            "修复规格依赖环",
            "循环依赖会让所有相关任务都无法安全开始。",
            spec=cycles[0][0],
            blocker=" -> ".join(cycles[0]),
            checks=["依赖图存在 cycle，当前工作流不可推进"],
            why_not="现在不能启动任何相关 Spec，因为依赖顺序本身不成立。",
            action_command=_amend_command(cycles[0][0]),
            alternative={
                "action": "临时降级一个依赖为独立 Spec",
                "reason": "先拆开耦合点，再恢复正常推进顺序。",
            },
        )
    if not specs:
        # Check bug-inbox first (Rule 65 opt-in): if there are open bugs,
        # recommend handling them before creating new specs.
        bug_inbox_path = os.path.join(project_root, ".agents", "bug-inbox.md")
        if os.path.exists(bug_inbox_path):
            with open(bug_inbox_path, encoding="utf-8") as f:
                inbox_content = f.read()
            open_bugs = re.findall(r"^- \[ \] (P[1-4]): (.+)$", inbox_content, re.MULTILINE)
            if open_bugs:
                priority_map = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
                open_bugs.sort(key=lambda x: priority_map.get(x[0], 99))
                p, desc = open_bugs[0]
                return _recommendation(
                    f"处理 bug-inbox 中的 {p} 级 bug",
                    f"当前有 {len(open_bugs)} 个未关闭的 bug，优先级最高的是 {p}。建议先处理 bug 再创建新 spec，避免新功能建立在有缺陷的基础上。",
                    checks=[f"{len(open_bugs)} 个 open bug 在 inbox 中", f"最高优先级: {p}"],
                    why_not="项目没有可推进的 Spec，但 bug-inbox 中有未处理的 bug。" +
                             "先修 bug 再推进新功能，避免技术债务累积。",
                    action_command=f"grep -E '^- \\\\[ \\\\[\\\\] P' {bug_inbox_path}",
                    alternative={
                        "action": "为这个 bug 创建 vibe spec 走完整修复流程",
                        "reason": "高风险 bug (P1/P2) 必须走 reproduction + fix-regression 流程 (R10)。",
                    },
                )
        intents_dir = os.path.join(project_root, ".agents", "intents")
        has_intent = _count_files(intents_dir) > 0
        return _recommendation(
            "把已澄清的意图整理为第一个 Spec" if has_intent else "先澄清意图并创建第一个 Spec",
            "项目还没有可执行的工作项。",
            checks=["当前没有可推进的 Spec"],
            why_not="现在不能给出实施步骤，因为还没有明确的工作项边界。",
            action_command=_create_spec_command(),
            alternative={
                "action": "先记录 discovery / intent",
                "reason": "如果目标仍然模糊，先把问题和范围写清楚更稳。",
            },
        )

    priority = {
        "released": 0,
        "review": 1,
        "in-progress": 2,
        "blocked": 3,
        "spec-ready": 4,
        "draft": 5,
        "done": 6,
        "cancelled": 7,
        "superseded": 8,
    }
    active = sorted(
        specs,
        key=lambda item: (
            priority.get(item["status"], 99),
            {"high": 0, "medium": 1, "low": 2}.get(item.get("risk", "medium"), 1),
            item["name"],
        ),
    )
    item = active[0]
    name = item["name"]
    content = item["content"]
    status = item["status"]
    workflow, _ = ensure_workflow(project_root)
    profile = risk_profile(project_root, content)

    if status == "draft":
        if spec_metadata(content).get("risk_confirmation") != "confirmed":
            return _recommendation(
                "重新确认需求变更后的风险等级",
                "需求已经变更，原风险判断不能自动沿用。",
                spec=name,
                checks=["检测到需求变更后风险确认仍为 pending"],
                action_command=_advance_command(name),
                why_not="现在不能回到 spec-ready，因为门禁要求先确认风险判断。",
                alternative={
                    "action": "先补齐变更影响范围",
                    "reason": "如果风险还拿不准，先明确受影响范围会更容易判断。",
                    "spec": name,
                },
            )
        validation = validate_spec.validate_spec(item["path"])
        if validation["errors"] or validation["warnings"]:
            return _recommendation(
                "补全并校验 Spec",
                f"规格仍有 {validation['errors']} 个错误和 {validation['warnings']} 个提醒。",
                spec=name,
                checks=["当前 Spec 还未通过完整性校验"],
                action_command=_amend_command(name),
                why_not="现在不能进入实施准备，因为规格还不够完整。",
                alternative={
                    "action": "先补范围和验收标准",
                    "reason": "这两块通常最先决定后续计划和验证方式。",
                    "spec": name,
                },
            )
        return _recommendation(
            "将 Spec 标记为 spec-ready",
            "规格内容已满足进入实施准备的条件。",
            spec=name,
            checks=["风险确认已完成", "Spec 校验通过"],
            action_command=_advance_command(name),
            why_not="现在不直接开始实施，因为状态还没有正式进入可执行阶段。",
            alternative={
                "action": "先生成或刷新 Agent Prompt",
                "reason": "如果准备交给实现 Agent，可以先固定当前上下文快照。",
                "spec": name,
            },
        )

    if status == "spec-ready":
        dependencies = spec_metadata(content)["dependencies"]
        if not set_status._dependencies_done(project_root, dependencies):
            return _recommendation(
                "先完成或修正前置依赖",
                "当前 Spec 的依赖尚未全部完成。",
                spec=name,
                blocker=", ".join(dependencies),
                checks=["Spec 已 ready", "依赖尚未全部 done"],
                why_not="现在不能直接实施，因为前置工作还没有闭环。",
                action_command=_status_command(),
                alternative={
                    "action": "检查依赖定义是否仍然准确",
                    "reason": "如果依赖其实已失效，可以先收缩依赖关系。",
                    "spec": name,
                },
            )
        if profile["require_plan"] and not _current_plan(project_root, name, content):
            staleness = _plan_staleness(project_root, name, content) or "missing"
            if staleness == "spec":
                return _recommendation(
                    "刷新实施计划 (规格摘要已过期)",
                    "Spec frontmatter 或正文已改动，计划里烧的 `规格摘要` 不再匹配。",
                    spec=name,
                    checks=[
                        "Spec 已 ready",
                        "依赖已完成",
                        "Plan 内的 `规格摘要` 与当前 spec digest 不一致",
                    ],
                    why_not="现在不能直接实施，因为执行步骤绑定的是旧版 spec。",
                    action_command=_regen_plan_command(name),
                    alternative={
                        "action": "先确认本次 spec 改动是有意的",
                        "reason": "如果改动是误操作，先回滚 spec 再生成计划更稳。",
                        "spec": name,
                    },
                )
            if staleness == "context":
                return _recommendation(
                    "刷新实施计划 (上下文摘要已过期)",
                    "adopted rules、AGENTS.md 或其他项目规则已改动，计划里烧的 `上下文摘要` 不再匹配。",
                    spec=name,
                    checks=[
                        "Spec 已 ready",
                        "依赖已完成",
                        "Plan 内的 `上下文摘要` 与当前 project context digest 不一致",
                    ],
                    why_not="现在不能直接实施，因为计划还没有绑定到当前项目治理上下文。",
                    action_command=_refresh_plan_command(name),
                    alternative={
                        "action": "先确认 rules 改动是有意的",
                        "reason": "如果只是临时实验，可以先回滚 rules 再刷新 plan。",
                        "spec": name,
                    },
                )
            return _recommendation(
                "生成或刷新实施计划",
                "当前风险等级要求计划，但还没有可用的 plan；使用 `vibe plan ... --force` 生成。",
                spec=name,
                checks=["Spec 已 ready", "依赖已完成", "Plan 缺失"],
                why_not="现在不能直接实施，因为执行步骤还没有绑定到当前规格快照。",
                action_command=_regen_plan_command(name),
                alternative={
                    "action": "先重新确认当前范围没有继续变化",
                    "reason": "避免刚生成计划就因需求波动过期。",
                    "spec": name,
                },
            )
        return _recommendation(
            "进入实施并按计划执行",
            "规格、依赖和所需计划均已就绪。",
            spec=name,
            checks=["Spec 已 ready", "依赖已完成", "计划有效"],
            why_not="现在不优先推进 review，因为还没有当前版本的实现和验证证据。",
            action_command=_advance_command(name),
            alternative={
                "action": "先生成或刷新 Agent Prompt",
                "reason": "如果要交给实现 Agent，先把当前规格和计划冻结成单一上下文。",
                "spec": name,
            },
        )

    if status == "in-progress":
        metadata = spec_metadata(content)
        evidence_ready = (
            set_status._has_bug_evidence(
                project_root, name, content, profile, workflow
            )[0]  # 2026-07-12d: _has_bug_evidence returns (bool, str)
            if metadata.get("spec_type") == "bug"
            else set_status._has_current_evidence(
                project_root, name, content, "verify", profile, workflow
            )
        )
        if profile["require_verify"] and not evidence_ready:
            configured = bool(workflow.get("commands", {}).get("verify"))
            return _recommendation(
                (
                    "补齐 Bug 的复现与修复回归证据"
                    if metadata.get("spec_type") == "bug"
                    else "执行项目配置的验证并记录证据"
                    if configured
                    else "完成验证并记录证据"
                ),
                (
                    "Bug 进入审查前必须同时证明修复前可复现、修复后已消失且既有行为保持。"
                    if metadata.get("spec_type") == "bug"
                    else "进入审查前还缺少当前版本的有效验证证据。"
                ),
                spec=name,
                checks=["实现阶段已开始", "当前 verify 证据不足"],
                action_command=_evidence_command(name, "verify"),
                why_not="现在不能进入 review，因为缺少与当前版本绑定的验证结果。",
                alternative={
                    "action": "先确认是否需要补回归测试",
                    "reason": "对会影响既有行为的修改，测试通常比口头说明更可靠。",
                    "spec": name,
                },
            )
        return _recommendation(
            "将工作项推进到 review",
            "当前版本的验证门禁已经满足。",
            spec=name,
            checks=["verify 证据齐全", "当前版本可进入审查"],
            action_command=_advance_command(name),
            why_not="现在不直接标记完成，因为还缺少独立审查或后续发布门禁。",
            alternative={
                "action": "先生成审查上下文",
                "reason": "把当前实现、证据和差异整理好，后续 review 会更顺。",
                "spec": name,
            },
        )

    if status == "review":
        if profile["require_review"]:
            _r_ok, _r_reason = set_status._has_approved_review(
                project_root, name, content, profile, workflow
            )
            if not _r_ok:
                if _r_reason:
                    # 2026-07-08d: 53b2afc 已在 vibe advance --help epilog 与
                    # runtime error block 暴露 override_approver escape hatch。
                    # status 推荐必须 surface 一致, 否则推荐与
                    # "实际入口"反向, 多 actor 项目也会被旧文案误导去改 workflow.json。
                    if "审查身份与构建者身份相同" in _r_reason:
                        alt_action = (
                            "运行 vibe advance {spec} released "
                            "--role override_approver --reason \"...\""
                        )
                        alt_reason = (
                            "单 actor 项目可走 escape hatch(无需改 workflow.json)；"
                            "三件套见 vibe advance --help epilog。"
                        )
                    else:
                        alt_action = "调整 workflow.json.review_separation.required_for"
                        alt_reason = (
                            "如确需同身份自审，把当前 risk 等级从该列表中移除。"
                        )
                    return _recommendation(
                        "使用不同身份生成审查并重新提交",
                        _r_reason,
                        spec=name,
                        checks=["verify 门禁已满足", "approved review 仍缺失"],
                        why_not="当前 risk 等级要求独立审查者；review 与 build 身份必须不同。",
                        action_command=_review_decision_command(name),
                        alternative={
                            "action": alt_action,
                            "reason": alt_reason,
                            "spec": name,
                        },
                    )
                return _recommendation(
                    "生成独立审查并提交结构化结论",
                    "尚无当前版本的有效批准记录。",
                    spec=name,
                    checks=["verify 门禁已满足", "approved review 仍缺失"],
                    why_not="现在不能发布或完成，因为还缺少独立审查结论。",
                    action_command=_review_decision_command(name),
                    alternative={
                        "action": "先检查审查上下文是否过期",
                        "reason": "如果代码或证据已变，先刷新 review 上下文更稳。",
                        "spec": name,
                    },
                )
            return _recommendation(
                "生成独立审查并提交结构化结论",
                "尚无当前版本的有效批准记录。",
                spec=name,
                checks=["verify 门禁已满足", "approved review 仍缺失"],
                why_not="现在不能发布或完成，因为还缺少独立审查结论。",
                action_command=_review_decision_command(name),
                alternative={
                    "action": "先检查审查上下文是否过期",
                    "reason": "如果代码或证据已变，先刷新 review 上下文更稳。",
                    "spec": name,
                },
            )
        if profile["require_release"] and not set_status._has_current_evidence(
            project_root, name, content, "release", profile, workflow
        ):
            configured = bool(workflow.get("commands", {}).get("release"))
            return _recommendation(
                "执行项目配置的发布并记录证据" if configured else "完成发布并记录证据",
                "审查已通过，但发布门禁尚未满足。",
                spec=name,
                checks=["approved review 已存在", "release 证据仍缺失"],
                action_command=_evidence_command(name, "release"),
                why_not="现在不能结束工作，因为还没有完成当前版本的发布闭环。",
                alternative={
                    "action": "先确认是否属于无需发布的场景",
                    "reason": "如果确实不适用，应记录 not-applicable 而不是跳过。",
                    "spec": name,
                },
            )
        return _recommendation(
            "推进到 released" if profile["require_release"] else "推进到 done",
            "当前风险配置要求的审查与发布证据已满足。",
            spec=name,
            checks=["approved review 已存在", "release 门禁已满足" if profile["require_release"] else "当前风险无需 release"],
            action_command=_advance_command(name),
            why_not="现在不再停留在 review，因为必需证据已经齐备。",
            alternative={
                "action": "先补 changelog 或发布说明",
                "reason": "如果团队需要对外同步，可以在状态推进前整理变更说明。",
                "spec": name,
            },
        )

    if status == "released":
        if profile.get("require_observe", False) and not set_status._has_current_evidence(
            project_root, name, content, "observe", profile, workflow
        ):
            configured = bool(workflow.get("commands", {}).get("observe"))
            return _recommendation(
                "执行项目配置的上线观察并记录证据" if configured else "完成上线观察并记录证据",
                "高风险工作在结束前必须确认发布后的实际状态。",
                spec=name,
                checks=["Spec 已 released", "observe 证据仍缺失"],
                action_command=_evidence_command(name, "observe"),
                why_not="现在不能标记 done，因为发布后的实际运行状态还没确认。",
                alternative={
                    "action": "先确认观察窗口和指标",
                    "reason": "避免记录一份没有判断依据的 observe 证据。",
                    "spec": name,
                },
            )
        return _recommendation(
            "将工作项标记为 done",
            "发布后观察门禁已经满足。",
            spec=name,
            checks=["Spec 已 released", "observe 门禁已满足"],
            action_command=_advance_command(name),
            why_not="现在不再停留在 released，因为后续观察工作已经完成。",
            alternative={
                "action": "先创建回顾",
                "reason": "如果团队想趁热总结，也可以先沉淀经验再正式收尾。",
                "spec": name,
            },
        )

    if status == "blocked":
        return _recommendation(
            "确认阻塞原因和解除条件，再恢复到原工作阶段",
            "阻塞项优先于启动新的工作，但不能在原因不明时自动推进。",
            spec=name,
            checks=["当前工作项状态为 blocked"],
            why_not="现在不建议切到新工作，因为未关闭的阻塞会持续制造上下文债务。",
            action_command=_status_command(),
            alternative={
                "action": "明确是否应该取消或 supersede 该 Spec",
                "reason": "如果阻塞长期无解，继续挂起不一定是最好选择。",
                "spec": name,
            },
        )

    done = [spec for spec in specs if spec["status"] == "done"]
    without_retro = [
        spec for spec in done
        if not os.path.exists(
            os.path.join(project_root, ".agents", "retros", f"{spec['name']}.md")
        )
    ]
    if without_retro:
        return _recommendation(
            "为最近完成的工作创建回顾",
            "完成项尚未沉淀项目本地经验。",
            spec=without_retro[-1]["name"],
            checks=["存在 done 但尚未回顾的工作项"],
            action_command=_retro_command(without_retro[-1]["name"]),
            why_not="现在不优先开启新任务，因为最近一次交付还没有沉淀经验。",
            alternative={
                "action": "先检查是否有规则需要从回顾中落地",
                "reason": "如果经验已经明确，可以直接准备项目本地规则变更。",
                "spec": without_retro[-1]["name"],
            },
        )
    # Session continuity: if there are non-done specs that were recently touched,
    # surface them as "continue?" suggestions. If everything is done, mention the
    # most recently completed spec.
    continuity = _session_continuity_hint(specs)
    if continuity:
        return continuity

    return _recommendation(
        "创建或选择下一个工作项",
        "当前没有待推进或待回顾的活动项。",
        checks=["当前没有 active spec，也没有待补回顾的 done 项"],
        action_command=_create_spec_command(),
        why_not="现在没有更高优先级的收尾动作，因此可以安全进入新一轮选择。",
        alternative={
            "action": "先运行 self_analyze",
            "reason": "如果回顾积累足够，先看治理改进机会也很划算。",
        },
    )


def _recommendation(
    action: str,
    reason: str,
    spec: str = "",
    blocker: str = "",
    checks: list[str] | None = None,
    why_not: str = "",
    alternative: dict | None = None,
    model: dict | None = None,
    action_command: str = "",
) -> dict:
    model = model or _model_effort_for_action(
        action, reason, checks or [], blocker, spec
    )
    return {
        "action": action,
        "reason": reason,
        "spec": spec,
        "blocker": blocker,
        "checks": checks or [],
        "why_not": why_not,
        "alternative": alternative or {},
        "model": model,
        "action_command": action_command,
    }


def _current_plan(project_root: str, name: str, content: str) -> bool:
    path = os.path.join(project_root, ".agents", "plans", f"{name}.md")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as handle:
        plan = handle.read()
    return (
        f"规格摘要: {spec_digest(content)}" in plan
        and f"上下文摘要: {project_context_digest(project_root)}" in plan
    )


def _plan_staleness(project_root: str, name: str, content: str) -> str | None:
    """Return one of: "missing", "spec", "context", or None when plan is current."""
    path = os.path.join(project_root, ".agents", "plans", f"{name}.md")
    if not os.path.exists(path):
        return "missing"
    with open(path, encoding="utf-8") as handle:
        plan = handle.read()
    if f"规格摘要: {spec_digest(content)}" not in plan:
        return "spec"
    if f"上下文摘要: {project_context_digest(project_root)}" not in plan:
        return "context"
    return None


def _refresh_plan_command(spec_name: str) -> str:
    return f"vibe plan <project_root> {spec_name} --refresh-context"


def _regen_plan_command(spec_name: str) -> str:
    return f"vibe plan <project_root> {spec_name} --force"


def _skill_drift(project_root: str) -> dict | None:
    """Return a drift dict if project's recorded version != installed, else None.

    Used by recommend_next to surface `vibe upgrade` as a top action when
    drift is detected. Returns None when no drift (or pre-Rule-52 project
    with no .skill-version file).
    """
    project_version = "unknown"
    project_path = os.path.join(project_root, ".agents", ".skill-version")
    if os.path.exists(project_path):
        try:
            with open(project_path, encoding="utf-8") as fp:
                project_version = fp.read().strip() or "unknown"
        except OSError:
            return None
    if project_version == "unknown":
        return None  # Pre-Rule-52 project; no drift to warn about.
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill_version_path = os.path.join(skill_dir, "VERSION")
    if not os.path.exists(skill_version_path):
        return None
    try:
        with open(skill_version_path, encoding="utf-8") as fp:
            skill_version = fp.read().strip() or "unknown"
    except OSError:
        return None
    if skill_version == "unknown" or skill_version == project_version:
        return None
    return {"project_version": project_version, "skill_version": skill_version}


def _count_proposed_rules(project_root: str) -> int:
    """Count rule files in 'proposed' state (Rule 54)."""
    rules_dir = os.path.join(project_root, ".agents", "rules")
    if not os.path.isdir(rules_dir):
        return 0
    count = 0
    for entry in sorted(os.listdir(rules_dir)):
        if not entry.endswith(".md"):
            continue
        path = os.path.join(rules_dir, entry)
        try:
            with open(path, encoding="utf-8") as fp:
                rule_content = fp.read()
        except OSError:
            continue
        m = re.search(r">\s*状态:\s*(\S+)", rule_content)
        if m and m.group(1) == "proposed":
            count += 1
    return count


def _evidence_command(spec_name: str, phase: str) -> str:
    """Build the canonical `vibe evidence <root> <spec> <phase> passed` command."""
    return f"vibe evidence <project_root> {spec_name} {phase} passed \"<describe what you observed>\""


def _advance_command(spec_name: str) -> str:
    """Build the canonical `vibe advance <root> <spec>` command."""
    return f"vibe advance <project_root> {spec_name}"


def _amend_command(spec_name: str) -> str:
    """Build the canonical `vibe amend <root> <spec>` command."""
    return f"vibe amend <project_root> {spec_name}"


def _retro_command(spec_name: str) -> str:
    """Build the canonical `vibe retrospective <root> <spec>` command."""
    return f"vibe retrospective <project_root> {spec_name}"


def _create_spec_command() -> str:
    """Build the canonical `vibe create-spec <root> <name>` command."""
    return "vibe create-spec <project_root> <name>"


def _status_command() -> str:
    """Build the canonical `vibe status <root>` command."""
    return "vibe status <project_root>"


def _init_command() -> str:
    """Build the canonical `vibe init <root>` command."""
    return "vibe init <project_root>"


def _context_refresh_command() -> str:
    """Build the canonical `vibe context-refresh <root>` command."""
    return "vibe context-refresh <project_root>"


def _policy_resolve_command(conflict_id: str = "<conflict-id>") -> str:
    """Build the canonical `vibe policy-conflict-resolve <root> <id>` command."""
    return f'vibe policy-conflict-resolve <project_root> {conflict_id} --resolution "<how to resolve>"'


def _review_decision_command(spec_name: str) -> str:
    """Build the canonical `vibe review-decision <root> <spec>` command."""
    return f'vibe review-decision <project_root> {spec_name} --decision approved --actor "<independent-reviewer-identity>"'


def _print_recommendation(recommendation: dict) -> None:
    print("💡 建议下一步:")
    target = f" [{recommendation['spec']}]" if recommendation.get("spec") else ""
    print(f"   {recommendation['action']}{target}")
    print(f"   原因: {recommendation['reason']}")
    command = recommendation.get("action_command")
    if command:
        print(f"   命令: {command}")
    if recommendation.get("blocker"):
        print(f"   阻塞: {recommendation['blocker']}")
    if recommendation.get("checks"):
        print(f"   前置检查: {'；'.join(recommendation['checks'])}")
    if recommendation.get("why_not"):
        print(f"   暂不选择: {recommendation['why_not']}")
    alternative = recommendation.get("alternative") or {}
    if alternative.get("action"):
        alternative_target = f" [{alternative['spec']}]" if alternative.get("spec") else ""
        print(
            f"   备选: {alternative['action']}{alternative_target}；"
            f"{alternative.get('reason', '')}"
        )
    model = recommendation.get("model") or {}
    if model.get("tier"):
        print(f"   模型建议: {model['tier']}")
        if model.get("configured_model"):
            print(f"   具体模型: {model['configured_model']}")
        elif model.get("configured_model") == "":
            print("   具体模型: 未配置（可在 .agents/workflow.json 的 model_tiers 中映射）")
        if model.get("reason"):
            print(f"   模型理由: {model['reason']}")
        if model.get("upgrade_if"):
            print(f"   升级条件: {model['upgrade_if']}")
    # Rule 50: machine-readable next_action marker for downstream parsers.
    print(f"<!-- vibe:next_action: {recommendation.get('action', '')} -->")
    if recommendation.get("spec"):
        print(f"<!-- vibe:next_target: {recommendation['spec']} -->")


def _apply_model_mapping(project_root: str, recommendation: dict) -> None:
    model = recommendation.get("model") or {}
    tier = model.get("tier")
    if not tier or not os.path.exists(os.path.join(project_root, ".agents")):
        return
    workflow, _ = ensure_workflow(project_root)
    configured = workflow.get("model_tiers", {})
    value = configured.get(tier, "")
    if isinstance(value, str) and value.strip():
        model["configured_model"] = value.strip()
    else:
        model["configured_model"] = ""
    recommendation["model"] = model


def _model_effort_for_action(
    action: str,
    reason: str,
    checks: list[str],
    blocker: str,
    spec: str,
) -> dict:
    action_text = action.lower()
    text = " ".join([action, reason, blocker, " ".join(checks)]).lower()
    if any(
        token in text
        for token in (
            "高风险", "high", "冲突", "循环依赖", "依赖环", "回归",
            "regression", "安全", "权限", "迁移", "blocked", "阻塞",
        )
    ):
        return {
            "tier": "strong",
            "reason": "下一步涉及跨边界判断、风险收敛或因果分析，低档模型容易漏条件。",
            "upgrade_if": "如果还需要独立验收或上线判断，改用 review 档。",
        }
    if any(
        token in action_text
        for token in ("审查", "review", "验收", "复盘", "retrospective")
    ):
        return {
            "tier": "review",
            "reason": "下一步是判断型工作，需要独立视角核对规格、证据或结论。",
            "upgrade_if": "如果审查发现架构、安全或回归疑点，切到 strong。",
        }
    if any(
        token in text
        for token in (
            "记录证据", "执行项目配置", "changelog", "context-refresh",
            "状态", "checkbox", "回顾", "retro", "self_analyze", "self-analyze",
        )
    ):
        return {
            "tier": "lite",
            "reason": "下一步主要是运行已有命令、整理状态或记录产物，不需要高强度推理。",
            "upgrade_if": "如果命令失败、证据含义不清或出现回归线索，切到 standard。",
        }
    return {
        "tier": "standard",
        "reason": "下一步是常规规格推进或实现准备，需要理解项目上下文但风险未升高。",
        "upgrade_if": "如果涉及跨模块设计、安全/数据边界或复杂 bug，切到 strong。",
    }


def _list_specs(dir: str) -> list[dict]:
    if not os.path.exists(dir):
        return []
    result = []
    for f in sorted(os.listdir(dir)):
        if f.endswith(".md") and f != ".gitkeep" and "-amendments" not in f:
            path = os.path.join(dir, f)
            with open(path) as fh:
                content = fh.read()
            status_match = re.search(r">\s*状态:\s*(\S+)", content)
            metadata = spec_metadata(content)
            result.append({
                "name": f.replace(".md", ""),
                "status": status_match.group(1) if status_match else "draft",
                "risk": metadata["risk"],
                "content": content,
                "path": path,
            })
    return result


def _print_plan_progress_commit_hint(
    project_root: str, plans: list[dict], specs: list[dict]
) -> None:
    """Surface commit nudge when a spec has ticked plan tasks but is dirty.

    Workflow-natural commit boundary: every `- [x]` in a plan.md marks a
    logical unit just finished. If the worktree is also dirty, the
    natural rhythm is "tick -> commit -> continue" so each commit
    contains one logical unit. Without this nudge, the agent keeps
    ticking tasks without committing until the pile is huge.

    Fires only when:
    - At least one in-progress / review spec has plan progress > 0
    - Worktree is dirty (uncommitted files exist)
    - At least one dirty file is outside `.agents/` (otherwise the
      dirt is governance-only and doesn't need a code commit)

    Silent otherwise.
    """
    if _uncommitted_count(project_root) == 0:
        return
    specs_by_name = {spec["name"]: spec for spec in specs}
    has_progress = False
    for plan in plans:
        spec = specs_by_name.get(plan["name"])
        if not spec or spec.get("status") not in {"in-progress", "review"}:
            continue
        if plan.get("done", 0) > 0:
            has_progress = True
            break
    if not has_progress:
        return
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
    code_dirty = [
        line for line in completed.stdout.splitlines()
        if line.strip() and not line[3:].strip().startswith(".agents/")
    ]
    if not code_dirty:
        return
    # Decide which commit command to suggest based on whether the dirty
    # files look like a single logical unit or several. The split path
    # is the more disciplined default — when in doubt, prefer staged
    # commits over one mega-commit, because rollback precision matters
    # more than commit count for project health.
    total_done = sum(p.get("done", 0) for p in plans)
    dirty_count = len(code_dirty)
    # If only one ticked task OR one dirty file, suggest a single commit.
    # Otherwise suggest the split path so the agent doesn't squash
    # multiple logical units into one commit.
    if total_done <= 1 or dirty_count <= 2:
        suggestion = (
            '   命令: `vibe commit --reviewed -m "<describe this task batch>"`'
            '   (如已配置 verify_scope，自动跑快速验证；否则跑全量 verify)'
        )
    else:
        suggestion = (
            '   命令: `git add <本 task 涉及的文件> && vibe commit --reviewed -m "<describe this task batch>"`\n'
            '   多 task / 多文件已 dirty：用 `git add <paths>` 精细 stage，'
            '再 `vibe commit --staged --reviewed`，让每个 commit 对应一个逻辑单元。'
            '   批量模式下：中间 commit `vibe commit --staged --no-verify -m "task N"`，'
            '最终 commit `vibe commit --full-verify --reviewed -m "batch done"` 跑全量验证。'
        )
    print()
    print(
        f"🪜 plan 任务已推进 {total_done} 个，"
        f"worktree 仍有 {dirty_count} 个代码改动未提交。"
    )
    print(
        "   自然节奏: 勾一个 task → commit 当前 task 的文件 → 继续下一个 task。"
    )
    print(
        "   这样每个 commit 对应一个逻辑单元，回滚时定位也精确。"
    )
    print(suggestion)
    print(f"<!-- vibe:plan_progress_commit_hint: {dirty_count} files -->")


def _extract_task_section(content: str):
    import re
    task_headers = [
        r"^##\s*任务列表",
        r"^##\s*Task List",
        r"^##\s*Tasks",
        r"^##\s*实施步骤",
    ]
    lines = content.splitlines()
    in_task_section = False
    task_lines = []
    for line in lines:
        if in_task_section:
            # Stop at next "## " (same or higher level heading), not "###"
            # Task section is "## 任务列表", so stop at next "## " or end
            if re.match(r"^##\s", line):
                break
            task_lines.append(line)
        else:
            if any(re.match(h, line) for h in task_headers):
                in_task_section = True
                task_lines.append(line)
    if task_lines:
        return "\n".join(task_lines)
    return None


def _list_plans(dir: str) -> list[dict]:
    if not os.path.exists(dir):
        return []
    result = []
    for f in sorted(os.listdir(dir)):
        if f.endswith(".md") and f != ".gitkeep":
            path = os.path.join(dir, f)
            with open(path) as fh:
                content = fh.read()
            # 候选 20260716: 只识别 "## 任务列表" 段下的 checkbox
            task_section = _extract_task_section(content)
            if task_section:
                done = len(re.findall(r"^\s*- \[x\]", task_section, re.MULTILINE))
                total = len(re.findall(r"^\s*- \[.\]", task_section, re.MULTILINE))
            else:
                # fallback: 老格式 plan
                done = len(re.findall(r"^\s*- \[x\]", content, re.MULTILINE))
                total = len(re.findall(r"^\s*- \[.\]", content, re.MULTILINE))
            result.append({
                "name": f.replace(".md", ""),
                "done": done,
                "total": total,
            })
    return result


def _spec_artifacts(agents_dir: str, spec_name: str) -> dict[str, bool]:
    """Per-spec existence flags for the four required artifacts.

    Returns a dict with keys plan, evidence, review, retro — True when at
    least one matching file exists for this spec. Used by the per-spec
    readiness indicator next to active specs.
    """
    def _has(subdir: str) -> bool:
        d = os.path.join(agents_dir, subdir)
        if not os.path.isdir(d):
            return False
        return os.path.exists(os.path.join(d, f"{spec_name}.md"))
    return {
        "plan": _has("plans"),
        "evidence": _has("evidence"),
        "review": _has("reviews"),
        "retro": _has("retros"),
    }


def _spec_artifact_indicator(artifacts: dict[str, bool]) -> str:
    """Compact per-spec readiness strip: 'plan ✓ evidence ✗ review ✓ retro ✗'.

    The checkmark/cross tells the agent at a glance which artifacts are
    already on disk for this spec. Missing artifacts are the obvious next
    step (run vibe plan / vibe record-evidence / etc.).
    """
    order = ("plan", "evidence", "review", "retro")
    parts = []
    for key in order:
        mark = "✓" if artifacts.get(key) else "✗"
        parts.append(f"{key} {mark}")
    return "  ".join(parts)


def _plan_progress_warnings(plans: list[dict], specs: list[dict]) -> list[str]:
    specs_by_name = {spec["name"]: spec for spec in specs}
    warnings = []
    for plan in plans:
        total = plan.get("total", 0)
        if total <= 0:
            continue
        spec = specs_by_name.get(plan["name"])
        if not spec or spec["status"] not in PLAN_PROGRESS_STALE_STATUSES:
            continue
        pct = int(plan["done"] / total * 100)
        if pct < PLAN_PROGRESS_WARNING_THRESHOLD:
            warnings.append(
                f"plan progress may be stale: {plan['name']} is "
                f"{spec['status']} but plan is {plan['done']}/{total} tasks "
                f"({pct}%). Sync checkboxes or record moved/deferred tasks."
            )
    return warnings


def _count_files(dir: str) -> int:
    if not os.path.exists(dir):
        return 0
    return len([f for f in os.listdir(dir) if f.endswith(".md") and f != ".gitkeep"])


def _count_pending_reviews(dir: str) -> int:
    if not os.path.exists(dir):
        return 0
    count = 0
    for filename in os.listdir(dir):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(dir, filename), encoding="utf-8") as handle:
            if re.search(r"\|\s*结论:\s*pending(?:\s*\||\s*$)", handle.read()):
                count += 1
    return count




def _session_continuity_hint(specs):
    """Suggest a recent or stale in-progress spec to continue.

    Returns a _recommendation dict, or None if no continuity signal applies.
    """
    from datetime import datetime, timezone
    terminal_statuses = {"done", "cancelled", "superseded"}
    open_specs = [s for s in specs if s["status"] not in terminal_statuses]
    if not open_specs:
        # All specs terminal: surface the most recently completed one as a reminder
        done_specs = [s for s in specs if s["status"] == "done"]
        annotated_done = []
        for spec in done_specs:
            touched = spec_last_touched(spec.get("content", ""))
            if touched:
                annotated_done.append((spec, touched))
        if not annotated_done:
            return None
        annotated_done.sort(key=lambda item: item[1], reverse=True)
        spec, touched = annotated_done[0]
        days = max(0, int((datetime.now(timezone.utc) - touched).total_seconds() // 86400))
        return _recommendation(
            f"继续或开新工作？上次完成的是 {spec['name']}（{days} 天前）",
            "所有已开始的 Spec 都已结束，最近交付的是这个。",
            spec=spec["name"],
            checks=[f"{spec['name']} 在 {days} 天前 done"],
            why_not="现在不默认开新 Spec，因为你的最近交付还没有被纳入下一步考虑。",
            action_command=_status_command(),
            alternative={
                "action": "基于最近完成的工作决定下一步",
                "reason": "新工作可以从延续上次工作开始，避免上下文丢失。",
            },
        )
    now = datetime.now(timezone.utc)
    STALE_DAYS = 7
    annotated = []
    for spec in open_specs:
        touched = spec_last_touched(spec.get("content", ""))
        if not touched:
            continue
        age = now - touched
        annotated.append((spec, age))
    if not annotated:
        return None
    annotated.sort(key=lambda item: item[1])
    spec, age = annotated[0]
    days = max(0, int(age.total_seconds() // 86400))
    if days < STALE_DAYS:
        return _recommendation(
            f"继续 {spec['name']}（上次活动 {days} 天前）",
            "你最近在推进这个 Spec，离开时还没完成。",
            spec=spec["name"],
            checks=[f"Spec 状态为 {spec['status']}，距离上次活动 {days} 天"],
            why_not="现在不直接切到新工作，因为上次的推进可能还没沉淀完。",
            action_command=_status_command(),
            alternative={
                "action": "先跑 vibe status 看看进度",
                "reason": "确认状态和证据是否仍然对得上。",
                "spec": spec["name"],
            },
        )
    return _recommendation(
        f"{spec['name']} 已经 {days} 天没动",
        "这个 Spec 卡在当前状态很久了，可能阻塞了也可能是被忘了。",
        spec=spec["name"],
        checks=[f"Spec 状态为 {spec['status']}，距离上次活动 {days} 天（>7）"],
        why_not="现在不建议直接创建新工作，因为旧的未关闭工作会持续制造上下文债务。",
        action_command=_status_command(),
        alternative={
            "action": "决定继续还是关闭",
            "reason": "如果阻塞长期无解，更好的选择是标记为 cancelled 或 supersede。",
            "spec": spec["name"],
        },
    )


def post_verify_hint(project_root: str, spec_name: str) -> None:
    """Compact post-verify hint printed by `vibe evidence <spec> verify passed`.

    Reads the spec's risk profile and remaining gates, then prints one of:
      - low-risk:  advance to done (skip released) if all gates pass
      - medium/high:  blocked by review / release / observe gates
      - any-risk:  generic fallback when we cannot determine the spec state

    The hint is deliberately shorter than `vibe next` and explicitly says
    "next action will NOT auto-advance" so the agent does not skip review
    or observe gates. Always read `vibe next <root> <spec>` for the full
    gate list before running `vibe advance`.
    """
    spec_path = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_path):
        return
    try:
        with open(spec_path, encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return
    try:
        meta = spec_metadata(content)
        risk = meta.get("risk", "medium")
    except Exception:  # noqa: BLE001
        risk = "medium"
    workflow, _ = ensure_workflow(project_root)
    profile = workflow.get("risk_profiles", {}).get(risk, workflow["risk_profiles"]["medium"])

    remaining = []
    if profile.get("require_review"):
        remaining.append("独立 review")
    if profile.get("require_release"):
        remaining.append("release 推进")
    if profile.get("require_observe"):
        remaining.append("observe 证据")

    print()
    if risk == "low":
        print(f"✅ verify passed — {spec_name} (low-risk)")
        if remaining:
            print(f"   剩余 gate: {' / '.join(remaining)}")
        else:
            print("   可直接: vibe advance <project_root> " + spec_name + " done")
        print("   完整门禁仍以 `vibe next` 为准;这一步不会自动推进。")
    elif risk in {"medium", "high"}:
        print(f"✅ verify passed — {spec_name} ({risk}-risk)")
        if remaining:
            print(f"   剩余 gate: {' / '.join(remaining)}")
        else:
            print("   已无剩余 gate;可运行 `vibe next` 拿到完整推荐动作。")
        print("   verify 不会自动 advance;review / release / observe 必须显式触发。")
    else:
        print(f"✅ verify passed — {spec_name} (risk={risk})")
        print("   完整门禁仍以 `vibe next` 为准。")
    print(f"   命令: vibe next <project_root> {spec_name}")


def _parse_activity_entered_at(project_root: str, spec_name: str, status: str) -> datetime | None:
    """Return the UTC datetime when `spec_name` most recently entered `status`,
    parsed from `.agents/activity.md` (already auto-written by set_status).

    Returns None when the activity log is missing or has no matching entry.
    """
    activity_path = os.path.join(project_root, ".agents", "activity.md")
    if not os.path.exists(activity_path):
        return None
    try:
        with open(activity_path, encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return None
    # activity entries look like:
    # - **2026-06-13 00:00 UTC** `spec-x`: `in-progress` → `review` | Actor: ...
    pattern = (
        r"\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)\*\*\s+"
        r"`" + re.escape(spec_name) + r"`:\s+`[^`]+`\s+→\s+`"
        + re.escape(status) + r"`"
    )
    matches = re.findall(pattern, content)
    if not matches:
        return None
    try:
        return datetime.strptime(matches[-1], "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def stage_stall_warnings(project_root: str, specs: list[dict] | None = None) -> list[str]:
    """Return one warning per spec whose current stage has exceeded the risk SLA.

    The threshold for each risk is configurable in workflow.json under
    `stage_stall_sla`: low_hours / medium_hours / high_hours. The Skill default
    is conservative (72h / 24h / 8h). The entered-at timestamp is read from
    `.agents/activity.md` (auto-maintained by `set_status`); when no activity
    entry exists for the spec's current status, the spec is skipped (we cannot
    reason about duration without a timestamp).
    """
    specs = specs if specs is not None else _list_specs(
        os.path.join(project_root, ".agents", "specs")
    )
    workflow, _ = ensure_workflow(project_root)
    sla = workflow.get("stage_stall_sla") or {}
    threshold_hours_by_risk = {
        "low": int(sla.get("low_hours", 72)),
        "medium": int(sla.get("medium_hours", 24)),
        "high": int(sla.get("high_hours", 8)),
    }
    now = datetime.now(timezone.utc)
    warnings: list[str] = []
    for spec in specs:
        status = spec.get("status", "draft")
        if status in {"done", "cancelled", "superseded"}:
            continue
        # Read risk from the spec content; default to medium.
        content = spec.get("content", "")
        risk = "medium"
        match = re.search(r"^>\s*风险:\s*(\S+)", content, re.MULTILINE)
        if match:
            risk = match.group(1).strip().lower()
        threshold = threshold_hours_by_risk.get(risk, threshold_hours_by_risk["medium"])
        entered = _parse_activity_entered_at(project_root, spec["name"], status)
        if entered is None:
            continue
        hours = max(0, int((now - entered).total_seconds() // 3600))
        if hours < threshold:
            continue
        warnings.append(
            f"{spec['name']} ({risk}-risk) has been in `{status}` for "
            f"{hours}h (SLA {threshold}h) — surface in `vibe next` or update activity.md"
        )
    return warnings


def ac_coverage(project_root: str, spec_name: str) -> dict:
    """Return per-AC coverage status for the latest verify evidence of `spec_name`.

    Result shape:
      {
        "spec": str,
        "risk": str,
        "criteria": [{"id": "AC1", "covered": bool}, ...],
        "missing": list[str],
        "evidence_path": str | None,
      }

    The function reads `.agents/specs/<spec_name>.md` for the AC list and risk,
    then reads the latest `.agents/evidence/<spec_name>/verify.md` (or
    `verify-reproduction.md` / `verify-fix-regression.md` if those exist).
    An AC is "covered" if its id appears anywhere in the evidence text. For
    low-risk specs every AC is reported as covered without checking, matching
    Rule 30's "low-risk specs get a brief note" exception. When the spec has
    no AC list or no evidence file yet, the function returns an empty
    criteria list and evidence_path=None.
    """
    import set_status as _set_status
    spec_path = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_path):
        return {"spec": spec_name, "risk": "medium", "criteria": [], "missing": [], "evidence_path": None}
    try:
        with open(spec_path, encoding="utf-8") as handle:
            spec_content = handle.read()
    except OSError:
        return {"spec": spec_name, "risk": "medium", "criteria": [], "missing": [], "evidence_path": None}
    risk_match = re.search(r"^>\s*风险:\s*(\S+)", spec_content, re.MULTILINE)
    risk = risk_match.group(1).strip().lower() if risk_match else "medium"

    # Discover the latest evidence file under .agents/evidence/<spec_name>/
    evidence_root = os.path.join(project_root, ".agents", "evidence", spec_name)
    evidence_path: str | None = None
    evidence_text = ""
    if os.path.isdir(evidence_root):
        candidates: list[str] = []
        for phase in ("verify", "release", "observe"):
            for suffix in ("", "-reproduction", "-fix-regression"):
                candidates.append(os.path.join(evidence_root, f"{phase}{suffix}.md"))
        # Pick the most recently modified evidence file across all candidates
        existing = [(p, os.path.getmtime(p)) for p in candidates if os.path.exists(p)]
        if existing:
            existing.sort(key=lambda item: item[1], reverse=True)
            evidence_path = existing[0][0]
            try:
                with open(evidence_path, encoding="utf-8") as handle:
                    evidence_text = handle.read()
            except OSError:
                evidence_text = ""

    criteria_ids = _set_status._acceptance_criteria_ids(spec_content)
    criteria = [{"id": f"AC{index}", "covered": False} for index in criteria_ids]
    if not criteria:
        return {"spec": spec_name, "risk": risk, "criteria": [], "missing": [], "evidence_path": evidence_path}

    if risk == "low":
        # Rule 30 exception: low-risk specs are exempt from per-AC mapping.
        for entry in criteria:
            entry["covered"] = True
        return {"spec": spec_name, "risk": risk, "criteria": criteria, "missing": [], "evidence_path": evidence_path}

    evidence_tokens = set(re.findall(r"\bAC\s*-?\s*(\d+)\b", evidence_text, re.IGNORECASE))
    for entry in criteria:
        index = int(entry["id"][2:])
        entry["covered"] = str(index) in evidence_tokens

    missing = [entry["id"] for entry in criteria if not entry["covered"]]
    return {
        "spec": spec_name,
        "risk": risk,
        "criteria": criteria,
        "missing": missing,
        "evidence_path": evidence_path,
    }


def print_ac_coverage(coverage: dict) -> None:
    """Pretty-print the result of ac_coverage() for the user."""
    if not coverage["criteria"]:
        if coverage["evidence_path"]:
            print(f"ℹ️  {coverage['spec']}: 没有找到 AC 列表（spec 可能不要求 AC）")
        else:
            print(f"ℹ️  {coverage['spec']}: 还没有 verify 证据")
        return
    if coverage["risk"] == "low":
        print(f"✅ {coverage['spec']} (low-risk): AC 覆盖详情不要求逐条引用")
        return
    missing = coverage["missing"]
    if not missing:
        print(f"✅ {coverage['spec']} ({coverage['risk']}-risk): 全部 {len(coverage['criteria'])} 条 AC 已被 verify 证据引用")
    else:
        print(f"⚠️  {coverage['spec']} ({coverage['risk']}-risk): {len(missing)}/{len(coverage['criteria'])} 条 AC 未在 verify 证据中引用")
        print(f"   缺失: {', '.join(missing)}")
    if coverage["evidence_path"]:
        rel = os.path.relpath(coverage["evidence_path"])
        print(f"   证据: {rel}")


def _print_git_context_hint(project_root: str) -> None:
    """Show git branch, unpushed commits, and merge conflict status.

    Agent commonly needs this but doesn't know to ask:
    - Which branch am I on? (avoid editing wrong branch)
    - Are there unpushed commits? (other agents can't see them)
    - Are there merge conflicts? (need resolution before continuing)
    """
    import subprocess
    if not os.path.isdir(os.path.join(project_root, ".agents")):
        return
    parts = []
    try:
        # Current branch
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if branch.returncode == 0 and branch.stdout.strip():
            parts.append(f"分支: {branch.stdout.strip()}")

        # Unpushed commits
        unpushed = subprocess.run(
            ["git", "log", "--oneline", "@{u}..HEAD"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if unpushed.returncode == 0 and unpushed.stdout.strip():
            count = len(unpushed.stdout.strip().splitlines())
            parts.append(f"{count} 个本地 commit 未推送")

        # Merge conflicts
        conflicts = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if conflicts.returncode == 0 and conflicts.stdout.strip():
            conflict_files = [f.strip() for f in conflicts.stdout.strip().splitlines() if f.strip()]
            if conflict_files:
                parts.append(f"⚠️ {len(conflict_files)} 个合并冲突文件")

        # Verify command configured?
        from workflow_state import ensure_workflow, configured_commands
        workflow, _ = ensure_workflow(project_root)
        verify_cmds = configured_commands(workflow, "verify")
        if not verify_cmds:
            parts.append("❌ 未配置 verify 命令 (Rule 53)")

    except (OSError, subprocess.TimeoutExpired):
        return

    if parts:
        print()
        print("🔀 Git 上下文: " + " | ".join(parts))




def _print_pending_reviews_hint(project_root: str) -> None:
    """Rule 53d: remind agent about commits that bypassed review gate.

    Reads .agents/.vibe-pending-reviews.json and surfaces unreviewed
    commits at high priority in vibe next / vibe status output.
    """
    import json as _json
    marker_path = os.path.join(project_root, ".agents", ".vibe-pending-reviews.json")
    if not os.path.exists(marker_path):
        return
    try:
        with open(marker_path, "r", encoding="utf-8") as handle:
            entries = _json.load(handle)
    except (OSError, _json.JSONDecodeError):
        return
    if not entries:
        return
    print()
    n = len(entries)
    print(f"⚠️  Rule 53d: {n} 个 commit 跳过了 review gate，待补独立审查:")
    for entry in entries[:5]:
        commit = entry.get("commit", "?")[:7]
        bypass = entry.get("bypass_type", "?")
        reason = entry.get("reason", "")
        files = entry.get("files", [])
        file_summary = files[0] if files else "unknown"
        if len(files) > 1:
            file_summary += f" +{len(files)-1}"
        reason_str = f" ({reason})" if reason else ""
        print(f"   - {commit} (--{bypass}){reason_str}: {file_summary}")
    if n > 5:
        print(f"   ... 还有 {n-5} 个")
    print("   补跑: vibe review <project_root> <spec_name>")
    print("   清除: 补跑后 marker 自动删除；或手动删除 .agents/.vibe-pending-reviews.json")
    print("<!-- vibe:pending_reviews_hint: count=%d -->" % n)

def _print_all_clean_signal(project_root: str, specs: list) -> None:
    """Positive closing signal: nothing is pending, agent can stop.

    Fires only when:
    - Project has at least one spec (not an empty project)
    - No spec is in active progression (spec-ready / in-progress / review)
    - Version drift is clean (or unknown — both treated as not-a-problem)
    - Worktree is clean (or not a git repo — both treated as not-a-problem)
    - No proposed rules in .agents/rules/
    - All done/released specs have retros and changelogs

    The per-category hints above already surface each kind of pending
    item; this function exists to give the agent a single, unambiguous
    "you are caught up" signal so it knows when to stop looping on
    `vibe next` and wait for the user's next instruction.
    """
    if not specs:
        return  # Empty project — recommendation will say "create a spec".
    # The "all clean" state means every spec is in a terminal state and the
    # agent has nothing to advance. Any non-terminal status (draft, spec-ready,
    # in-progress, review, released) means the project still has pending work.
    PENDING_STATUSES = {"draft", "spec-ready", "in-progress", "review", "released"}
    if any(s.get("status") in PENDING_STATUSES for s in specs):
        return

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill_version_path = os.path.join(skill_dir, "VERSION")
    project_version_path = os.path.join(project_root, ".agents", ".skill-version")
    pv = "unknown"
    sv = "unknown"
    if os.path.exists(project_version_path):
        try:
            with open(project_version_path, encoding="utf-8") as fp:
                pv = fp.read().strip() or "unknown"
        except OSError:
            pass
    if os.path.exists(skill_version_path):
        try:
            with open(skill_version_path, encoding="utf-8") as fp:
                sv = fp.read().strip() or "unknown"
        except OSError:
            pass
    if pv != "unknown" and sv != "unknown" and pv != sv:
        return  # Version drift pending.

    import subprocess
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return  # Uncommitted work pending.
    except (OSError, subprocess.TimeoutExpired):
        pass

    rules_dir = os.path.join(project_root, ".agents", "rules")
    if os.path.isdir(rules_dir):
        for entry in os.listdir(rules_dir):
            if not entry.endswith(".md"):
                continue
            try:
                with open(
                    os.path.join(rules_dir, entry), encoding="utf-8"
                ) as fp:
                    content = fp.read()
            except OSError:
                continue
            if re.search(r">\s*状态:\s*proposed\b", content):
                return  # Proposed rule pending.

    specs_dir = os.path.join(project_root, ".agents", "specs")
    for sub_dir_name in ("retros", "changelogs"):
        sub_dir = os.path.join(project_root, ".agents", sub_dir_name)
        if not (os.path.isdir(specs_dir) and os.path.isdir(sub_dir)):
            continue
        existing = {
            entry[:-3] for entry in os.listdir(sub_dir)
            if entry.endswith(".md") and entry != ".gitkeep"
        }
        for entry in os.listdir(specs_dir):
            if not entry.endswith(".md") or entry.endswith("-amendments.md"):
                continue
            try:
                with open(
                    os.path.join(specs_dir, entry), encoding="utf-8"
                ) as fp:
                    content = fp.read()
            except OSError:
                continue
            m = re.search(r">\s*状态:\s*(\S+)", content)
            if m and m.group(1) in {"done", "released"}:
                if entry[:-3] not in existing:
                    return  # Missing retro or changelog pending.

    print()
    print(
        "✅ 项目干净 — 没有 pending spec / retro / CHANGELOG / 提交 / 规则待评审 / 版本漂移"
    )
    print("   agent 可以停，等用户下一个指令")
    print("<!-- vibe:project_state: clean -->")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Show project status overview")
    p.add_argument("project_root", help="Project root directory")
    args = p.parse_args()
    project_status(os.path.abspath(args.project_root))
