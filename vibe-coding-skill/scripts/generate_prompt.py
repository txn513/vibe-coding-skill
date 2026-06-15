#!/usr/bin/env python3
"""Generate a ready-to-use Agent prompt from AGENTS.md + spec + project rules.

Usage:
    python3 generate_prompt.py <project_root> <spec_name> [--with-design]
"""

import argparse
import os
import re
import sys

from common import (
    adopted_project_rule_paths,
    atomic_write,
    git_snapshot,
    project_context_digest,
    spec_digest,
    validate_artifact_name,
)
from workflow_state import risk_profile


def generate_prompt(project_root: str, spec_name: str, with_design: bool = False,
                    rules_mode: str = "auto") -> str:
    project_root = os.path.abspath(project_root)
    spec_name = validate_artifact_name(spec_name, "规格名称")

    agents_content = _read(os.path.join(project_root, "AGENTS.md"))

    spec_content = _read(os.path.join(project_root, ".agents", "specs", f"{spec_name}.md"))
    if not spec_content:
        print(f"❌ 规格不存在: {spec_name}")
        sys.exit(1)

    # Validate spec before generating prompt
    import importlib
    try:
        validator = importlib.import_module("validate_spec")
        spec_path = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
        result = validator.validate_spec(spec_path)
        if not result["valid"]:
            print(f"❌ 规格未通过校验，无法生成 prompt。请先修复以下问题：")
            print()
            validator.print_result(result)
            sys.exit(1)
        if result["status"] not in {"spec-ready", "in-progress"}:
            print(f"❌ 当前规格状态为 {result['status']}，请先标记为 spec-ready")
            sys.exit(1)
        if not result["ready"]:
            print(f"⚠️  规格有 {result['warnings']} 个提醒，将继续生成 prompt。")
            print()
    except ImportError:
        pass  # validate_spec not available, skip

    # Project rules are authoritative. Do not guess which ones are irrelevant.
    rules_content = _filter_rules(project_root, spec_content, rules_mode)

    design_content = ""
    if with_design:
        design_file = os.path.join(project_root, ".agents", "designs", f"{spec_name}.md")
        if os.path.exists(design_file):
            design_content = _read(design_file) or ""
        else:
            print(f"⚠️  设计文档不存在: {spec_name}，跳过。")

    plan_content = _read(os.path.join(project_root, ".agents", "plans", f"{spec_name}.md"))
    profile = risk_profile(project_root, spec_content)
    if profile["require_plan"] and not plan_content:
        print("❌ 此风险等级要求先生成实施计划")
        sys.exit(1)
    if plan_content:
        if f"规格摘要: {spec_digest(spec_content)}" not in plan_content:
            print("❌ 实施计划对应的规格版本已过期，请重新生成")
            sys.exit(1)
        if f"上下文摘要: {project_context_digest(project_root)}" not in plan_content:
            print("❌ 实施计划使用了过期的项目规则，请重新生成")
            sys.exit(1)

    # Include project-level custom checklist
    custom_checklist = _read(os.path.join(project_root, ".agents", "checklists", "custom.md"))
    git = git_snapshot(project_root)

    prompt = f"""# Execution Context

> 规格摘要: {spec_digest(spec_content)} | 上下文摘要: {project_context_digest(project_root)}
> Commit: {git['commit']} | Snapshot: {git.get('snapshot', 'N/A')} | 工作区: {git['worktree']}

## 项目上下文

{agents_content if agents_content else '(先运行 init_project.py 或 onboard_project.py)'}

---

## 编码规范

{rules_content}

---

## 项目特有检查项

{custom_checklist if custom_checklist else '(暂无项目特有检查项)'}

---

## 架构设计

{design_content if design_content else '(未提供设计文档。如果是复杂功能，请先用 create_design.py 创建)'}

---

## 任务：实现功能规格

以下是你要实现的功能规格。请严格遵循规格中的约束，特别注意"不动文件"和"明确不做什么"。

{spec_content}

---

## 实施计划

{plan_content if plan_content else '(先运行 generate_plan.py)'}

---

## 实现要求

1. 只实施规格和计划明确授权的范围；遇到冲突或信息缺失时先停止并说明。
2. 以 AGENTS.md、项目规则和规格为准，不自行补充项目未确认的技术或业务决策。
3. 按计划逐项实施并保留项目要求的验证证据。
4. 完成后报告实际变更、验证结果、偏差和仍未解决的问题。
"""
    return prompt


def _filter_rules(project_root: str, spec_content: str, mode: str) -> str:
    """Load all project rules without inferring relevance from filenames."""
    rules_dir = os.path.join(project_root, ".agents", "rules")
    if not os.path.exists(rules_dir):
        return "(无自定义规则)"

    rule_files = [path.name for path in adopted_project_rule_paths(project_root)]
    return _concat_rules(rules_dir, rule_files)


def _concat_rules(rules_dir: str, rule_files: list[str]) -> str:
    """Concatenate rule files into a single string."""
    result = ""
    for rf in rule_files:
        content = _read(os.path.join(rules_dir, rf))
        if content:
            result += f"\n### {rf.replace('.md', '').upper()}\n\n{content}\n"
    return result if result else "(无自定义规则)"


def _extract_field(spec: str, field: str) -> str:
    m = re.search(rf"- \*\*{field}\*\*: (.+)", spec)
    return m.group(1).strip() if m else ""


def generate_and_save(project_root: str, spec_name: str, with_design: bool = False,
                      rules_mode: str = "auto") -> str:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    prompt = generate_prompt(project_root, spec_name, with_design, rules_mode)
    prompts_dir = os.path.join(project_root, ".agents", "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    prompt_file = os.path.join(prompts_dir, f"{spec_name}.md")
    atomic_write(prompt_file, prompt)

    print(f"✅ Agent 提示词已生成: {prompt_file}")
    print(f"   (同时输出到 stdout，可直接复制)")
    print()
    return prompt_file


def _read(path: str) -> str | None:
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate an Agent prompt from spec and context")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name")
    p.add_argument("--with-design", action="store_true", help="Include design document")
    p.add_argument("--rules", choices=["auto", "all"], default="auto",
                   help="Compatibility option; all project rules are always included")
    p.add_argument("--print-only", action="store_true", help="Print to stdout only, don't save")
    args = p.parse_args()

    if args.print_only:
        prompt = generate_prompt(os.path.abspath(args.project_root), args.spec_name,
                                 args.with_design, args.rules)
        print(prompt)
    else:
        generate_and_save(os.path.abspath(args.project_root), args.spec_name,
                          args.with_design, args.rules)
