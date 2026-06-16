#!/usr/bin/env python3
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
from workflow_state import (
    dependency_cycles, ensure_workflow, risk_profile, spec_last_touched, spec_metadata,
)

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

        print(f"📋 功能规格 ({len(specs)}):")
        for status in STATUS_ORDER:
            if status in by_status:
                icon = STATUS_ICONS.get(status, "❓")
                names = ", ".join(s["name"] for s in by_status[status])
                print(f"   {icon} {status}: {names}")
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
        print()

    # Retros
    retros_dir = os.path.join(agents_dir, "retros")
    retro_count = _count_files(retros_dir)
    if retro_count > 0:
        print(f"📝 已完成回顾: {retro_count} 个")
        if retro_count >= 2:
            print(f"   → 可以运行 self_analyze 检查改进机会")
        print()

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
    _print_recommendation(recommend_next(project_root, specs))


def project_next(project_root: str) -> dict:
    """Print only the highest-priority governed next action."""
    project_root = os.path.abspath(project_root)
    if not os.path.exists(os.path.join(project_root, ".agents")):
        recommendation = _recommendation(
            "接入已有项目或初始化新项目",
            "当前项目还没有 Vibe Coding 工作流状态。",
            checks=["尚未检测到 .agents/ 工作流目录"],
            why_not="现在不能直接给出实施建议，因为项目还没有治理上下文。",
            alternative={
                "action": "先澄清这是新项目还是已有项目",
                "reason": "接入方式会决定初始化还是扫描现有规范。",
            },
        )
    else:
        recommendation = recommend_next(
            project_root,
            _list_specs(os.path.join(project_root, ".agents", "specs")),
        )
    _print_recommendation(recommendation)
    return recommendation


def recommend_next(project_root: str, specs: list[dict] | None = None) -> dict:
    """Return one prioritized next action based on current gates."""
    specs = specs if specs is not None else _list_specs(
        os.path.join(project_root, ".agents", "specs")
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
            alternative={
                "action": "先运行 context-refresh 并核对 AGENTS.md",
                "reason": "至少先把技术栈、当前阶段和待人工确认项同步到最新。",
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
            alternative={
                "action": "临时降级一个依赖为独立 Spec",
                "reason": "先拆开耦合点，再恢复正常推进顺序。",
            },
        )
    if not specs:
        intents_dir = os.path.join(project_root, ".agents", "intents")
        has_intent = _count_files(intents_dir) > 0
        return _recommendation(
            "把已澄清的意图整理为第一个 Spec" if has_intent else "先澄清意图并创建第一个 Spec",
            "项目还没有可执行的工作项。",
            checks=["当前没有可推进的 Spec"],
            why_not="现在不能给出实施步骤，因为还没有明确的工作项边界。",
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
                alternative={
                    "action": "检查依赖定义是否仍然准确",
                    "reason": "如果依赖其实已失效，可以先收缩依赖关系。",
                    "spec": name,
                },
            )
        if profile["require_plan"] and not _current_plan(project_root, name, content):
            return _recommendation(
                "生成或刷新实施计划",
                "当前风险等级要求计划，且现有计划缺失或已过期。",
                spec=name,
                checks=["Spec 已 ready", "依赖已完成", "计划缺失或与当前上下文不一致"],
                why_not="现在不能直接实施，因为执行步骤还没有绑定到当前规格快照。",
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
            )
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
            why_not="现在不直接标记完成，因为还缺少独立审查或后续发布门禁。",
            alternative={
                "action": "先生成审查上下文",
                "reason": "把当前实现、证据和差异整理好，后续 review 会更顺。",
                "spec": name,
            },
        )

    if status == "review":
        if profile["require_review"] and not set_status._has_approved_review(
            project_root, name, content, profile, workflow
        ):
            return _recommendation(
                "生成独立审查并提交结构化结论",
                "尚无当前版本的有效批准记录。",
                spec=name,
                checks=["verify 门禁已满足", "approved review 仍缺失"],
                why_not="现在不能发布或完成，因为还缺少独立审查结论。",
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
) -> dict:
    return {
        "action": action,
        "reason": reason,
        "spec": spec,
        "blocker": blocker,
        "checks": checks or [],
        "why_not": why_not,
        "alternative": alternative or {},
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


def _print_recommendation(recommendation: dict) -> None:
    print("💡 建议下一步:")
    target = f" [{recommendation['spec']}]" if recommendation.get("spec") else ""
    print(f"   {recommendation['action']}{target}")
    print(f"   原因: {recommendation['reason']}")
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


def _list_plans(dir: str) -> list[dict]:
    if not os.path.exists(dir):
        return []
    result = []
    for f in sorted(os.listdir(dir)):
        if f.endswith(".md") and f != ".gitkeep":
            path = os.path.join(dir, f)
            with open(path) as fh:
                content = fh.read()
            done = len(re.findall(r"- \[x\]", content))
            total = len(re.findall(r"- \[.\]", content))
            result.append({
                "name": f.replace(".md", ""),
                "done": done,
                "total": total,
            })
    return result


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
        alternative={
            "action": "决定继续还是关闭",
            "reason": "如果阻塞长期无解，更好的选择是标记为 cancelled 或 supersede。",
            "spec": spec["name"],
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Show project status overview")
    p.add_argument("project_root", help="Project root directory")
    args = p.parse_args()
    project_status(os.path.abspath(args.project_root))
