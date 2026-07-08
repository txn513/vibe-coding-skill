#!/usr/bin/env python3
"""Generate an implementation plan from a feature spec."""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

from common import (
    atomic_write,
    backup_file,
    project_context_digest,
    spec_digest,
    validate_artifact_name,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def generate_plan(project_root: str, spec_name: str, force: bool = False) -> str | None:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    if not os.path.exists(spec_file):
        print(f"❌ 规格不存在: {spec_file}")
        return None

    with open(spec_file) as f:
        spec_content = f.read()

    import validate_spec

    validation = validate_spec.validate_spec(spec_file)
    if not validation["valid"]:
        print("❌ 规格未通过校验，无法生成实施计划")
        validate_spec.print_result(validation)
        return None
    if validation["status"] not in {"spec-ready", "in-progress"}:
        print(f"❌ 当前规格状态为 {validation['status']}，请先标记为 spec-ready")
        return None

    plans_dir = os.path.join(project_root, ".agents", "plans")
    os.makedirs(plans_dir, exist_ok=True)
    plan_file = os.path.join(plans_dir, f"{spec_name}.md")
    if os.path.exists(plan_file) and not force:
        print(f"⚠️  实施计划已存在，未覆盖: {plan_file}")
        return plan_file
    if force:
        backup_file(
            plan_file,
            os.path.join(project_root, ".agents", "archive", spec_name, "plans"),
        )

    tmpl_path = os.path.join(TEMPLATE_DIR, "plan.md")
    if not os.path.exists(tmpl_path):
        print(f"❌ 模板不存在: {tmpl_path}")
        return None

    with open(tmpl_path) as f:
        template = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ac_section = re.search(r"###\s*正常路径\n+(.+?)(?:\n###|\Z)", spec_content, re.DOTALL)
    ac_count = len(re.findall(r"^\d+\.\s+\S", ac_section.group(1), re.MULTILINE)) if ac_section else 0
    scope_new = _extract(spec_content, "新增文件")
    scope_mod = _extract(spec_content, "修改文件")

    content = template
    for k, v in {
        "SPEC_NAME": spec_name,
        "SPEC_FILE": f".agents/specs/{spec_name}.md",
        "SPEC_DIGEST": spec_digest(spec_content),
        "CONTEXT_DIGEST": project_context_digest(project_root),
        "CREATED_AT": now,
        "PHASE_1_NAME": "核心实现",
        "TASK_1_1": f"实现核心逻辑（涉及 {scope_new or '待定'}）",
        "TASK_1_2": "编写单元测试",
        "PHASE_2_NAME": "集成与边界",
        "TASK_2_1": f"修改现有代码集成（涉及 {scope_mod or '待定'}）",
        "TASK_2_2": f"编写集成测试（覆盖 {ac_count or '所有'} 条验收标准）",
        "PHASE_3_NAME": "验证与收尾",
        "TASK_3_1": "手动验收测试",
        "TASK_3_2": "Code Review（独立 Agent 审查）",
        "RISK_1": "（从规格中识别风险）",
        "RISK_2": "（从规格中识别风险）",
    }.items():
        content = content.replace("{{" + k + "}}", v)
    content = re.sub(r"\{\{.*?\}\}", "（请根据实际情况填写）", content)

    atomic_write(plan_file, content)

    print(f"✅ 实施计划已生成: {plan_file}")
    return plan_file


def _extract(spec: str, field: str) -> str:
    m = re.search(rf"- \*\*{field}\*\*: (.+)", spec)
    if m:
        v = m.group(1).strip()
        if v and "(计划" not in v and "(描述" not in v:
            return v
    return ""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate implementation plan")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name (without .md)")
    p.add_argument("--force", action="store_true", help="Overwrite an existing plan")
    p.add_argument(
        "--refresh-context",
        action="store_true",
        help=(
            "Refresh an existing plan's context digest and spec digest "
            "after adopted rules or other project guidance change; keeps the "
            "same plan file and archives the previous version."
        ),
    )
    p.add_argument(
        "--refresh-digest-only",
        action="store_true",
        help=(
            "Patch only the spec and context digest header lines on an "
            "existing plan; preserves the Agent-entered plan body. Works "
            "regardless of spec status (unlike --refresh-context which "
            "requires spec-ready or in-progress because it re-renders the "
            "full plan from template). Use after a small spec edit only "
            "changed the digest, not the scope."
        ),
    )
    args = p.parse_args()
    result = generate_plan(os.path.abspath(args.project_root), args.spec_name, args.force)
    if getattr(args, "refresh_digest_only", False):
        result = refresh_plan_digests_only(
            os.path.abspath(args.project_root), args.spec_name
        )
    elif getattr(args, "refresh_context", False):
        result = refresh_plan_context(
            os.path.abspath(args.project_root), args.spec_name
        )
    sys.exit(0 if result else 1)


def refresh_plan_context(project_root: str, spec_name: str) -> str | None:
    """Re-render an existing plan with fresh spec and project-context digests.

    The plan file must already exist; the previous version is archived. Use this
    after editing adopted rules, AGENTS.md, or other project guidance that the
    plan binds to. Doctor will surface a stale-context warning if you skip this.
    """
    spec_name = validate_artifact_name(spec_name, "规格名称")
    plan_file = os.path.join(project_root, ".agents", "plans", f"{spec_name}.md")
    if not os.path.exists(plan_file):
        print(f"❌ 实施计划不存在，请先运行 plan 生成: {plan_file}")
        return None
    return generate_plan(project_root, spec_name, force=True)


def refresh_plan_digests_only(project_root: str, spec_name: str) -> str | None:
    """Patch ONLY the digest header lines of an existing plan file.

    2026-07-09 (Lance retro on social-bookmarking-tool):
    refresh_plan_context refuses to operate when spec.status is done, because
    generate_plan() intentionally guards re-rendering on spec-ready/in-progress
    only — re-running the template would overwrite Agent-entered phase/task
    body with placeholder text. But what the Agent actually needs at done
    state is the cheap operation: re-compute the 16-char spec digest and the
    16-char project-context digest, then patch the two header lines in the
    existing plan file. Body is untouched.

    This new path bypasses the status check on purpose because digest headers
    are derived from spec content (re-computed every time) and project
    guidance (re-computed every time), so they are valid to refresh
    regardless of the spec lifecycle phase.
    """
    spec_name = validate_artifact_name(spec_name, "规格名称")
    plan_file = os.path.join(project_root, ".agents", "plans", f"{spec_name}.md")
    if not os.path.exists(plan_file):
        print(f"❌ 实施计划不存在，请先运行 plan 生成: {plan_file}")
        return None
    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    with open(spec_file, encoding="utf-8") as handle:
        spec_content = handle.read()
    new_spec_digest = spec_digest(spec_content)
    new_context_digest = project_context_digest(project_root)
    with open(plan_file, encoding="utf-8") as handle:
        plan_content = handle.read()
    backup_file(
        plan_file,
        os.path.join(project_root, ".agents", "archive", spec_name, "plans"),
    )
    # 2026-07-09: the template packs both digests on a single header
    # line ("> 基于规格: X | 规格摘要: HEX | 上下文摘要: HEX | ..."),
    # so the regex anchors on "规格摘要:" / "上下文摘要:" within a line
    # that begins with ">" rather than requiring the line to start with
    # the digest label.
    plan_content_new = re.sub(
        r"(^>.*?)规格摘要:\s*[0-9a-f]{16}",
        rf"\1规格摘要: {new_spec_digest}",
        plan_content,
        count=1,
        flags=re.MULTILINE,
    )
    plan_content_new = re.sub(
        r"(^>.*?)上下文摘要:\s*[0-9a-f]{16}",
        rf"\1上下文摘要: {new_context_digest}",
        plan_content_new,
        count=1,
        flags=re.MULTILINE,
    )
    if plan_content_new == plan_content:
        print("⚠️  plan header 不含可识别的 digest 行 (老格式 plan); 未修改")
        return plan_file
    atomic_write(plan_file, plan_content_new)
    print(f"✅ plan header digest 已刷新: 规格={new_spec_digest} 上下文={new_context_digest}")
    print(f"   {plan_file}")
    print("   body 未动 (仅修改 规格摘要 / 上下文摘要 两行 header)")
    return plan_file
