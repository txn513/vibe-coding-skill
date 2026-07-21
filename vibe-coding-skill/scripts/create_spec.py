#!/usr/bin/env python3
from __future__ import annotations
"""Create a feature/bug/refactor spec from template.

Usage:
    python3 create_spec.py <project_root> <name> [--type feature|bug|refactor]
"""

import argparse
import os
import pathlib
from datetime import datetime, timezone

from common import adopted_project_rule_paths, atomic_write, validate_artifact_name
import validate_spec

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
    _print_project_guidance_summary(project_root)
    _print_initial_validation(spec_file)
    if spec_type == "bug":
        print(f"🐛 专注：复现步骤、根因分析、修复方案、回归测试")
        if regression_from:
            print(f"   回归来源: {regression_from}")
    elif spec_type == "refactor":
        print(f"🔧 专注：重构目标、不动行为、测试保护")
    return spec_file


def _print_project_guidance_summary(project_root: str) -> None:
    """Surface AGENTS.md + adopted rules so the Agent can cite them in the spec.

    Implements Skill治理升级候选 3: 让 Agent 在 spec 创建那一瞬就能看到项目规则
    摘要(不只是状态),避免 '5 份 retro 点名 AGENTS.md 缺失作为做错了什么' 的循环。
    """
    import re
    agents_path = os.path.join(project_root, "AGENTS.md")
    rules = adopted_project_rule_paths(project_root)
    agents_status = "found" if os.path.exists(agents_path) else "missing"
    print(f"📚 项目规则上下文: AGENTS.md {agents_status}; adopted rules: {len(rules)}")
    if agents_status == "found":
        # 抓 AGENTS.md 的 H2 段标题,告诉 Agent 哪些约束可引用
        try:
            content = pathlib.Path(agents_path).read_text(encoding="utf-8")
            h2_sections = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
            if h2_sections:
                preview = ", ".join(h2_sections[:6])
                suffix = " ..." if len(h2_sections) > 6 else ""
                print(f"   AGENTS.md 章节: {preview}{suffix}")
        except OSError:
            pass
    if rules:
        for rule_path in rules[:5]:
            rel = os.path.relpath(rule_path, project_root)
            try:
                content = pathlib.Path(rule_path).read_text(encoding="utf-8")
                # 抓规则文件第一行非 frontmatter 的标题作为摘要
                lines = content.splitlines()
                title = next((ln.lstrip("# ").strip() for ln in lines if ln.strip() and not ln.startswith("---") and not ln.startswith(">")), "(无标题)")
                print(f"   {rel}: {title}")
            except OSError:
                print(f"   {rel}: (读取失败)")
        suffix = " ..." if len(rules) > 5 else ""
        if suffix:
            print(f"   (+{len(rules) - 5} more){suffix}")
    print("   生成执行 prompt 时会绑定 AGENTS.md 与 adopted 项目规则。")


def _print_initial_validation(spec_file: str) -> None:
    print("🔍 初始规格校验:")
    validate_spec.print_result(validate_spec.validate_spec(spec_file))


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

    # Rule 59 — non-bug specs that touch existing constructors / dependency
    # wiring must list every call site. We pre-fill the section with a
    # reminder so the user fills it in IF applicable; if not applicable
    # (truly additive change), the user deletes the section and
    # validate_spec does NOT warn (it checks presence only after a
    # heuristic trigger).
    non_bug_call_sites_section = (
        "## 调用点 (Call Sites)\n\n"
        "> Rule 59: 如果本 spec 修改某个已有 class 的 `__init__` 行为、"
        "改动关键参数的默认值，或切换第三方 client 的 transport / auth，"
        "必须用 `grep` 全项目列出该符号的所有调用点 (file:line)，并标注每个调用点的适配状态。\n"
        "> 不适用本 spec 时，删除本段即可。\n\n"
        "### 完整调用点清单 (grep `<SymbolName>(` 全项目)\n\n"
        "- `path/to/file.py:LINE` — adapted / needs-adaptation / n/a (原因)\n"
        "- `path/to/file.py:LINE` — adapted / needs-adaptation / n/a (原因)\n\n"
        "### reviewer 独立验证\n\n"
        "- [ ] reviewer 已独立跑过同样的 grep 并展示原始输出\n"
    )

    base = {
        "SPEC_NAME": name, "SPEC_TYPE": spec_type, "STATUS": "draft",
        "RISK_LEVEL": risk, "RISK_CONFIRMATION": "confirmed",
        "OWNER": owner or "待确认",
        "DEPENDENCIES": dependencies or "无",
        "RELEASE_GROUP": release_group or "待确认",
        "REGRESSION_FROM": regression_from,
        "REGRESSION_FROM_LINE": f"> 回归来源: {regression_from}" if regression_from else "",
        "PROMPT_VERSION": "1",
        "CREATED_AT": now, "UPDATED_AT": now,
        "SUCCESS_CRITERION_1": "", "SUCCESS_CRITERION_2": "", "SUCCESS_CRITERION_3": "",
        "TECH_CONSTRAINT_1": "", "TECH_CONSTRAINT_2": "",
        "BUSINESS_CONSTRAINT_1": "", "BUSINESS_CONSTRAINT_2": "",
        "OUT_OF_SCOPE_1": "(请使用 [included]、[follow-up: spec-id] 或 [abandoned] 标注不做事项)",
        "OUT_OF_SCOPE_2": "",
        "HAPPY_PATH_1": "", "HAPPY_PATH_2": "", "HAPPY_PATH_3": "",
        "EDGE_CASE_1": "", "EDGE_CASE_2": "",
        "ERROR_HANDLING_1": "", "ERROR_HANDLING_2": "",
        "NEW_FILES": "", "MODIFIED_FILES": "", "DO_NOT_TOUCH": "",
        "FIX_SCOPE_SECTION": "",
        "CALL_SITES_SECTION": "",
        "PERFORMANCE_REQUIREMENT_1": "(请定义适用于本项目的性能要求与验证方式)",
        "PERFORMANCE_REQUIREMENT_2": "",
        "SECURITY_NFR_1": "(请定义适用于本项目的安全要求与验证方式)",
        "SECURITY_NFR_2": "",
        "ACCESSIBILITY_REQUIREMENT_1": "(请定义适用于本项目的可访问性或兼容性要求)",
        "ACCESSIBILITY_REQUIREMENT_2": "",
        "CALL_SITES_SECTION": non_bug_call_sites_section,
    }

    if spec_type == "bug":
        return {
            **base,
            # Bug specs have their own Fix Scope section that already lists
            # every touched file; Rule 59's Call Sites section is for
            # non-bug specs that modify existing constructors / wiring.
            "CALL_SITES_SECTION": "",
            "INTENT": f"修复 {name} 的 Bug\n\n**复现步骤**: (描述如何复现)\n**实际行为**: (Bug 表现)\n**期望行为**: (修复后应该怎样)\n**影响范围**: (哪些用户/场景受影响)",
            "SUCCESS_CRITERION_1": "(请定义问题不再发生的可验证条件)",
            "SUCCESS_CRITERION_2": "(请定义需要保持不变的行为及验证方式)",
            "ERROR_HANDLING_1": "(请定义相关失败场景的预期行为)",
            "FIX_SCOPE_SECTION": (
                "## 修复范围 (Fix Scope)\n\n"
                "> Rule 51: 任何 type=bug spec 必须显式声明修复范围。"
                "这强制 agent 列举**已修复位置**和**故意不改的相邻位置**，"
                "并写明判断依据。漏列相邻位置导致的回归会进 retro → self_analyze → 升级项目级 rule。\n\n"
                "### 已修复位置\n\n"
                "- `path/to/file.py:LINE` — (修了什么)\n"
                "- `path/to/file.py:LINE` — (修了什么)\n\n"
                "### 故意不改的相邻位置\n\n"
                "- `path/to/adjacent.py:LINE` — (为什么这个位置看起来像同一个 bug 但实际不是,或不属于本 spec)\n"
                "- ...\n\n"
                "### 判断依据\n\n"
                "(用什么标准判断哪些位置属于\"同一个 bug\"？例如:共享 root cause / 同一 API 调用 / 同一分支逻辑 / 同一鉴权上下文。)\n"
            ),
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
