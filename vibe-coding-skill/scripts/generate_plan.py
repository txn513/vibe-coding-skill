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
    args = p.parse_args()
    result = generate_plan(os.path.abspath(args.project_root), args.spec_name, args.force)
    sys.exit(0 if result else 1)
