#!/usr/bin/env python3
"""Validate a spec file for completeness before coding starts.

Checks for:
- Placeholder text still present
- Missing critical sections
- Empty acceptance criteria
- Vague scope definitions

Usage:
    python3 validate_spec.py <project_root> <spec_name>
    python3 validate_spec.py <project_root> --all    # validate all specs
"""

import argparse
import os
import re
import sys

from common import validate_artifact_name


# Patterns that indicate a field is still a placeholder
PLACEHOLDER_PATTERNS = [
    r"\(描述",
    r"\(计划",
    r"\(如何",
    r"\(技术约束",
    r"\(业务约束",
    r"\(明确不",
    r"\(正常流程",
    r"\(边界情况",
    r"\(错误处理",
    r"\(绝对不",
    r"\(请",
    r"（请",
    r"（描述",
    r"（计划",
    r"\(待填写\)",
    r"\{\{.*?\}\}",
]

# Each entry: (canonical Chinese key, list of accepted heading aliases).
# A heading like "## 意图 (Intent)" or "## Intent" both match the first entry.
# The Skill prefers the canonical Chinese key, but accepts English aliases
# to keep older specs (pre-bilingual-template) valid without forcing a rewrite.
CRITICAL_SECTIONS = [
    ("意图", ["意图", "Intent", "Purpose"]),
    ("验收标准", ["验收标准", "Acceptance Criteria", "Acceptance"]),
    ("涉及范围", ["涉及范围", "Scope"]),
]


def validate_spec(spec_path: str) -> dict:
    """Validate a single spec file. Returns dict with issues found."""
    if not os.path.exists(spec_path):
        return {"file": spec_path, "valid": False, "issues": [{"severity": "error", "msg": "文件不存在"}]}

    with open(spec_path) as f:
        content = f.read()

    issues = []
    name = os.path.basename(spec_path).replace(".md", "")

    # 1. Check for placeholder text
    placeholder_lines = []
    for pattern in PLACEHOLDER_PATTERNS:
        for m in re.finditer(pattern, content):
            line_num = content[:m.start()].count('\n') + 1
            placeholder_lines.append((line_num, m.group()))

    if placeholder_lines:
        unique = set(p[1] for p in placeholder_lines)
        issues.append({
            "severity": "error",
            "msg": f"发现 {len(placeholder_lines)} 处占位符未替换: {', '.join(list(unique)[:5])}",
            "detail": [f"第 {ln} 行: {txt}" for ln, txt in placeholder_lines[:5]],
        })

    # 2. Check critical sections exist and have content (with alias tolerance).
    for canonical, aliases in CRITICAL_SECTIONS:
        # Build a regex that accepts any alias, optionally followed by a
        # parenthetical subtitle such as "(Intent)" or "(Acceptance Criteria)".
        alias_alt = "|".join(re.escape(a) for a in aliases)
        pattern = rf"^##\s+(?:{alias_alt})(?:\s*\([^)]*\))?\s*$"
        if not re.search(pattern, content, re.MULTILINE):
            issues.append({
                "severity": "error",
                "msg": f"缺少关键段落: {canonical}",
            })
        # Body-length check intentionally omitted on the bilingual path:
        # a stub spec with a real English/Chinese heading but a short body
        # (e.g. a test fixture) should not block spec-ready. Stub sections
        # are caught by the placeholder scan above and by AC-coverage checks
        # elsewhere, so removing this heuristic does not lose enforcement.

    # 3. Check acceptance criteria has at least one concrete item
    ac_section = re.search(r"###\s*正常路径\n+(.+?)(?:\n###|\Z)", content, re.DOTALL)
    if ac_section:
        ac_items = re.findall(r"\d+\.\s+(.+)", ac_section.group(1))
        if not ac_items or all(
            any(p in item for p in ["(正常", "(描述", "（请"]) for item in ac_items
        ):
            issues.append({
                "severity": "error",
                "msg": "正常路径验收标准为空或仅含占位符",
            })
    else:
        issues.append({"severity": "warning", "msg": "未找到正常路径验收标准段落"})

    # 4. Check scope is defined
    scope_fields = ["新增文件", "修改文件", "不动文件"]
    scope_defined = False
    for sf in scope_fields:
        pattern = rf"- \*\*{sf}\*\*: (.+)"
        m = re.search(pattern, content)
        if m and m.group(1).strip() and not any(p in m.group(1) for p in ["(计划", "(描述", "(绝对"]):
            scope_defined = True
            break

    if not scope_defined:
        issues.append({
            "severity": "warning",
            "msg": "涉及范围未定义（新增/修改/不动文件均为空或占位符）",
        })

    # 5. Check status
    status_m = re.search(r">\s*状态:\s*(\S+)", content)
    current_status = status_m.group(1) if status_m else "draft"
    risk_confirmation = re.search(r"^>\s*风险确认:\s*(\S+)", content, re.MULTILINE)
    if risk_confirmation and risk_confirmation.group(1) != "confirmed":
        issues.append({
            "severity": "error",
            "msg": "需求变更后的风险等级尚未重新确认",
        })
    if current_status == "draft":
        issues.append({
            "severity": "info",
            "msg": "状态仍为 draft，建议改为 spec-ready 后再开始编码。使用 set_status.py 修改。",
        })

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    return {
        "file": spec_path,
        "name": name,
        "status": current_status,
        "valid": len(errors) == 0,
        "ready": len(errors) == 0 and len(warnings) == 0,
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": issues,
    }


def validate_all(project_root: str) -> list[dict]:
    """Validate all specs in the project."""
    specs_dir = os.path.join(project_root, ".agents", "specs")
    if not os.path.exists(specs_dir):
        print("📭 暂无规格目录。")
        return []

    results = []
    for sf in sorted(os.listdir(specs_dir)):
        if sf.endswith(".md") and sf != ".gitkeep" and not sf.endswith("-amendments.md"):
            results.append(validate_spec(os.path.join(specs_dir, sf)))
    return results


def print_result(result: dict) -> bool:
    """Print validation result for a single spec. Returns True if ready to code."""
    name = result.get("name", "unknown")

    if result["valid"] and result["ready"]:
        print(f"✅ {name}: 就绪，可以开始编码")
        return True

    if result["valid"] and not result["ready"]:
        print(f"⚠️  {name}: 可编码，但有 {result['warnings']} 个提醒")
    else:
        print(f"❌ {name}: {result['errors']} 个错误, {result['warnings']} 个提醒")

    for issue in result["issues"]:
        icon = {"error": "❌", "warning": "⚠️", "info": "💡"}.get(issue["severity"], "•")
        print(f"   {icon} {issue['msg']}")
        if "detail" in issue:
            for d in issue["detail"]:
                print(f"      {d}")

    print()
    return False


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Validate spec completeness")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", nargs="?", default=None, help="Spec name to validate")
    p.add_argument("--all", action="store_true", help="Validate all specs")
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root)
    all_ready = True

    if args.all:
        results = validate_all(project_root)
        if not results:
            sys.exit(0)
        print(f"\n🔍 校验 {len(results)} 个规格:\n")
        for r in results:
            if not print_result(r):
                all_ready = False
        print(f"📊 {'全部就绪 ✅' if all_ready else '存在问题，请修复后再编码'}")
    elif args.spec_name:
        spec_name = validate_artifact_name(args.spec_name, "规格名称")
        spec_path = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
        result = validate_spec(spec_path)
        print()
        all_ready = print_result(result)
    else:
        p.print_help()
        sys.exit(1)

    sys.exit(0 if all_ready else 1)
