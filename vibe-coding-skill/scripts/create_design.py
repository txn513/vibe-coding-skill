#!/usr/bin/env python3
"""Create an architecture/design document template."""

import argparse
import os
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def create_design(project_root: str, name: str) -> str:
    name = validate_artifact_name(name, "设计名称")
    designs_dir = os.path.join(project_root, ".agents", "designs")
    os.makedirs(designs_dir, exist_ok=True)

    design_file = os.path.join(designs_dir, f"{name}.md")
    if os.path.exists(design_file):
        print(f"⚠️  设计文档已存在: {design_file}")
        return design_file

    tmpl_path = os.path.join(TEMPLATE_DIR, "design.md")
    if not os.path.exists(tmpl_path):
        print(f"❌ 模板不存在: {tmpl_path}")
        return ""

    with open(tmpl_path) as f:
        template = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = {
        "DESIGN_NAME": name, "STATUS": "draft",
        "CREATED_AT": now, "LINKED_SPEC": "(关联的 spec 名称)",
        "PROBLEM_STATEMENT": "(用一段话描述要解决什么问题)",
        "CURRENT_CONTEXT": "(描述与本次设计有关的现状)",
        "IN_SCOPE_BOUNDARY": "(描述本次方案负责什么)",
        "OUT_OF_SCOPE_BOUNDARY": "(描述本次方案不负责什么)",
        "SOLUTION_OVERVIEW": "(用一段话描述方案及其工作方式)",
        "PART_1": "(组成部分)", "PART_1_RESPONSIBILITY": "(职责)",
        "PART_1_INPUT": "(输入)", "PART_1_OUTPUT": "(输出)",
        "PART_2": "(组成部分)", "PART_2_RESPONSIBILITY": "(职责)",
        "PART_2_INPUT": "(输入)", "PART_2_OUTPUT": "(输出)",
        "INTERACTION_FLOW": "(描述组成部分之间的交互或状态流转)",
        "STABLE_CONTRACTS": "(列出不得改变的契约)",
        "CHANGED_CONTRACTS": "(列出新增或改变的契约)",
        "COMPATIBILITY_REQUIREMENTS": "(说明兼容与迁移要求)",
        "DECISION_1_TITLE": "(决策标题)", "DECISION_1_OPTIONS": "(选项 A / 选项 B)",
        "DECISION_1_CHOICE": "(选择的方案)", "DECISION_1_RATIONALE": "(选择理由)",
        "DECISION_2_TITLE": "(决策标题)", "DECISION_2_OPTIONS": "(选项 A / 选项 B)",
        "DECISION_2_CHOICE": "(选择的方案)", "DECISION_2_RATIONALE": "(选择理由)",
        "VALIDATION_STRATEGY": "(描述如何验证设计目标)",
        "REQUIRED_EVIDENCE": "(描述完成时需要保留什么证据)",
        "RISK_1": "(风险描述)", "RISK_1_IMPACT": "(影响程度)", "RISK_1_MITIGATION": "(缓解措施)",
        "RISK_2": "(风险描述)", "RISK_2_IMPACT": "(影响程度)", "RISK_2_MITIGATION": "(缓解措施)",
        "OPEN_QUESTION_1": "(待澄清的问题)",
        "OPEN_QUESTION_2": "(待澄清的问题)",
    }

    content = template
    for k, v in fields.items():
        content = content.replace("{{" + k + "}}", v)

    atomic_write(design_file, content)

    print(f"✅ 设计文档已创建: {design_file}")
    print(f"📐 填写边界、职责、契约、关键决策和验证策略后再创建 spec。")
    return design_file


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create an architecture design document")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("name", help="Design document name")
    args = p.parse_args()
    create_design(os.path.abspath(args.project_root), args.name)
