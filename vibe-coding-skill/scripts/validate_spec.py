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
# Each entry: (canonical Chinese key, list of accepted heading aliases).
# A heading like "## 意图 (Intent)" or "## Intent" both match the first entry.
# The Skill prefers the canonical Chinese key, but accepts English aliases
# to keep older specs (pre-bilingual-template) valid without forcing a rewrite.
#
# 2026-07-10 (09f candidate 1): expanded 3 → 7 to match templates/spec.md
# actual h2 headings. Previously validate_spec only enforced 意图/验收/涉及
# — leaving 成功标准/约束/NFR/验证方式 silently optional — so a stub spec
# could pass validate and only fail at advance time. The four new entries
# are unconditional error severity: missing them means the spec template
# was not actually filled in, which is exactly what Rule 9 (project-local
# learning) and Rule 18 (no project-specific knowledge in Skill) expect to
# catch before code lands.
#
# Note: NFR 段允许 "(无)" / "(不适用)" / "(N/A)" 占位（某些轻量 spec
# e.g. typo 修复确实没 NFR）. validate 在 section 缺失时直接 error;
# section 存在但 body 是 placeholder 则由 placeholder scan 抓。
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

    # 4. Check scope is defined. Supports multi-line file lists — capture
    # from `- **<sf>**:` to the next `- **...**:` line OR `## ` heading
    # boundary. The capture is greedy across newlines so an agent that
    # wrote:
    #   - **新增文件**:
    #     - src/foo.ts
    #     - src/bar.ts
    # is recognised as defined (same condition: non-empty body, no
    # placeholder fragments). 2026-07-10 candidate 2.
    scope_fields = ["新增文件", "修改文件", "不动文件"]
    scope_defined = False
    for sf in scope_fields:
        start_m = re.search(rf"^- \*\*{sf}\*\*:\s*", content, re.MULTILINE)
        if not start_m:
            continue
        body_start = start_m.end()
        rest = content[body_start:]
        boundary_m = re.search(r"^(?:- \*\*[^\*]+\*\*:|##\s)", rest, re.MULTILINE)
        body = rest[: boundary_m.start()] if boundary_m else rest
        if body.strip() and not any(p in body for p in ["(计划", "(描述", "(绝对"]):
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

    # 5b. Section-name uniqueness (Rule 18 follow-up). Two h2 headings
    #     with the same canonical text means the agent either:
    #     (a) accidentally pasted a section twice (retro 反思 5 实证), or
    #     (b) duplicated a template reminder block.
    #     Either way it is a defect: the spec body is ambiguous, and
    #     downstream readers (reviewer, future agents) cannot tell which
    #     copy is authoritative. h3 sub-sections (e.g. 正常路径 under
    #     验收标准) are intentionally allowed to repeat — they live
    #     under different AC scenarios, not at the section-of-record level.
    h2_matches = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    # Normalise by stripping optional parenthetical subtitles so
    # "## 验收标准 (Acceptance Criteria)" and "## 验收标准" dedupe.
    def _normalise_h2(raw: str) -> str:
        return re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    seen_h2: dict[str, int] = {}
    duplicates: list[str] = []
    for raw in h2_matches:
        norm = _normalise_h2(raw)
        seen_h2[norm] = seen_h2.get(norm, 0) + 1
    for norm, count in seen_h2.items():
        if count > 1:
            duplicates.append(f"{norm} (x{count})")
    if duplicates:
        issues.append({
            "severity": "error",
            "msg": f"发现 {len(duplicates)} 个重复 h2 段名: {', '.join(duplicates)}",
            "detail": ["合并或删除重复段后再 advance — 重复段让 spec body 失去唯一权威"],
        })
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

    # Rule 59 — non-bug specs include a "调用点 (Call Sites)" reminder section
    # when they touch existing constructors / dependency wiring. The Agent
    # must either fill in the call-site list (with grep'd file:line) OR
    # explicitly delete the reminder block. A spec that leaves the reminder
    # block but does not list any call sites (or does not mark N/A) is
    # signalling that Rule 59 was triggered but not addressed.
    call_sites_section = re.search(
        r"^##\s+调用点.*?(?=^##\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if call_sites_section:
        body = call_sites_section.group(0)
        # The section is "addressed" if the user either:
        # (a) listed at least one concrete file:line call site (file.py:NN),
        #     OR
        # (b) explicitly disabled it. A disable must be a USER action — a
        #     line that starts the section body with an explicit "N/A" or
        #     "不适用" sentinel, NOT the boilerplate reminder sentence
        #     that the template itself emits.
        has_call_site_line = bool(
            re.search(r"^-\s+`[^`]+:\d+", body, re.MULTILINE)
        )
        # Disable sentinel: a list item line that contains N/A / 不适用
        # / <no call sites affected> as an EXPLICIT user annotation. We
        # accept "- ... N/A: ..." style or a line whose first non-whitespace
        # token is "N/A" / "不适用".
        has_disabled_sentinel = bool(
            re.search(
                r"^\s*[-*]\s+(?:N/A\b|n/a\b|不适用\b|<no call sites affected>)",
                body,
                re.MULTILINE,
            )
        )
        if not has_call_site_line and not has_disabled_sentinel:
            issues.append({
                "severity": "warning",
                "msg": "Rule 59: spec 含 '调用点 (Call Sites)' 段但未列出任何调用点（grep 结果）或显式标注「不适用/N/A」。"
                       "reviewer 必须独立 grep 验证调用点清单完整性。",
            })

    # R6_8: spec should have a matching intent file (20260714o)
    spec_dir = os.path.dirname(spec_path)
    intents_dir = os.path.join(os.path.dirname(spec_dir), "intents")
    if os.path.exists(intents_dir):
        intent_path = os.path.join(intents_dir, name + ".md")
        has_intent_ref = bool(re.search(r">\s*(?:关联 intent|Related Intent):", content))
        if not os.path.exists(intent_path) and not has_intent_ref:
            issues.append({
                "severity": "warning",
                "msg": f"Intent file missing: intents/{name}.md (R6_8)",
            })

    # R51e: type=bug spec must have Fix Scope section (20260714o)
    spec_type_match = re.search(r">\s*(?:类型|Type):\s*(\S+)", content)
    if spec_type_match and spec_type_match.group(1) == "bug":
        if "## 修复范围" not in content and "## Fix Scope" not in content:
            issues.append({
                "severity": "error",
                "msg": "type=bug spec missing Fix Scope section (R51e) - declare fixed locations + intentionally unchanged adjacent locations",
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
