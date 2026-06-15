#!/usr/bin/env python3
"""Create a feature/bug/refactor spec from template.

Usage:
    python3 create_spec.py <project_root> <name> [--type feature|bug|refactor]
"""

import argparse
import os
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def create_spec(
    project_root: str,
    name: str,
    spec_type: str = "feature",
    risk: str = "medium",
    owner: str = "",
    dependencies: str = "无",
    release_group: str = "",
    regression_from: str = "",
) -> str:
    name = validate_artifact_name(name, "规格名称")
    specs_dir = os.path.join(project_root, ".agents", "specs")
    os.makedirs(specs_dir, exist_ok=True)

    spec_file = os.path.join(specs_dir, f"{name}.md")
    if os.path.exists(spec_file):
        print(f"⚠️  规格已存在: {spec_file}")
        return spec_file

    tmpl_path = os.path.join(TEMPLATE_DIR, "spec.md")
    if not os.path.exists(tmpl_path):
        print(f"❌ 模板不存在: {tmpl_path}")
        return ""

    with open(tmpl_path) as f:
        template = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Type-specific defaults
    type_defaults = _get_type_defaults(
        spec_type, name, risk, owner, dependencies, release_group, regression_from
    )

    content = template
    for k, v in type_defaults.items():
        content = content.replace("{{" + k + "}}", v)

    atomic_write(spec_file, content)

    type_label = {"feature": "功能", "bug": "Bug 修复", "refactor": "重构"}.get(spec_type, "功能")
    print(f"✅ {type_label}规格已创建: {spec_file}")
    if spec_type == "bug":
        print(f"🐛 专注：复现步骤、根因分析、修复方案、回归测试")
        if regression_from:
            print(f"   回归来源: {regression_from}")
    elif spec_type == "refactor":
        print(f"🔧 专注：重构目标、不动行为、测试保护")
    return spec_file


def _get_type_defaults(
    spec_type: str,
    name: str,
    risk: str = "medium",
    owner: str = "",
    dependencies: str = "无",
    release_group: str = "",
    regression_from: str = "",
) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    base = {
        "SPEC_NAME": name, "SPEC_TYPE": spec_type, "STATUS": "draft",
        "RISK_LEVEL": risk, "RISK_CONFIRMATION": "confirmed",
        "OWNER": owner or "待确认",
        "DEPENDENCIES": dependencies or "无",
        "RELEASE_GROUP": release_group or "待确认",
        "REGRESSION_FROM": regression_from,
        "REGRESSION_FROM_LINE": f"> 回归来源: {regression_from}" if regression_from else "",
        "CREATED_AT": now, "UPDATED_AT": now,
        "SUCCESS_CRITERION_1": "", "SUCCESS_CRITERION_2": "", "SUCCESS_CRITERION_3": "",
        "TECH_CONSTRAINT_1": "", "TECH_CONSTRAINT_2": "",
        "BUSINESS_CONSTRAINT_1": "", "BUSINESS_CONSTRAINT_2": "",
        "OUT_OF_SCOPE_1": "", "OUT_OF_SCOPE_2": "",
        "HAPPY_PATH_1": "", "HAPPY_PATH_2": "", "HAPPY_PATH_3": "",
        "EDGE_CASE_1": "", "EDGE_CASE_2": "",
        "ERROR_HANDLING_1": "", "ERROR_HANDLING_2": "",
        "NEW_FILES": "", "MODIFIED_FILES": "", "DO_NOT_TOUCH": "",
        "PERFORMANCE_REQUIREMENT_1": "(请定义适用于本项目的性能要求与验证方式)",
        "PERFORMANCE_REQUIREMENT_2": "",
        "SECURITY_NFR_1": "(请定义适用于本项目的安全要求与验证方式)",
        "SECURITY_NFR_2": "",
        "ACCESSIBILITY_REQUIREMENT_1": "(请定义适用于本项目的可访问性或兼容性要求)",
        "ACCESSIBILITY_REQUIREMENT_2": "",
    }

    if spec_type == "bug":
        return {
            **base,
            "INTENT": f"修复 {name} 的 Bug\n\n**复现步骤**: (描述如何复现)\n**实际行为**: (Bug 表现)\n**期望行为**: (修复后应该怎样)\n**影响范围**: (哪些用户/场景受影响)",
            "SUCCESS_CRITERION_1": "(请定义问题不再发生的可验证条件)",
            "SUCCESS_CRITERION_2": "(请定义需要保持不变的行为及验证方式)",
            "ERROR_HANDLING_1": "(请定义相关失败场景的预期行为)",
        }

    if spec_type == "refactor":
        return {
            **base,
            "INTENT": f"重构 {name}\n\n**重构目标**: (请描述希望改善的质量属性)\n**当前问题**: (请描述为什么需要重构)\n**预期改善**: (请定义可验证的改善结果)",
            "SUCCESS_CRITERION_1": "(请定义必须保持不变的行为及验证方式)",
            "SUCCESS_CRITERION_2": "(请定义重构目标达成的可验证条件)",
            "TECH_CONSTRAINT_1": "(请定义不得改变的外部契约)",
            "TECH_CONSTRAINT_2": "(请定义必须保持的项目约束)",
            "DO_NOT_TOUCH": "(请列出本次重构不得修改的范围)",
        }

    # Default: feature
    return {
        **base,
        "INTENT": "(描述要解决什么问题，为谁解决)",
        "SUCCESS_CRITERION_1": "(如何判断成功？量化指标)",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a spec (feature, bug, or refactor)")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("name", help="Feature/bug/refactor name (used as filename)")
    p.add_argument("--type", choices=["feature", "bug", "refactor"], default="feature",
                   help="Spec type (default: feature)")
    p.add_argument("--risk", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--owner", default="", help="Accountable owner")
    p.add_argument("--depends-on", default="无", help="Comma-separated spec dependencies")
    p.add_argument("--release-group", default="", help="Optional release grouping")
    p.add_argument("--regression-from", default="", help="For bug specs: spec that introduced the regression")
    args = p.parse_args()
    create_spec(
        os.path.abspath(args.project_root),
        args.name,
        args.type,
        args.risk,
        args.owner,
        args.depends_on,
        args.release_group,
        args.regression_from,
    )
