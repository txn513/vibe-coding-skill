#!/usr/bin/env python3
"""Create a feature retrospective template."""

import argparse
import os
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def create_retro(project_root: str, spec_name: str) -> str:
    spec_name = validate_artifact_name(spec_name, "规格名称")
    # Try to read the spec for context
    spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
    spec_intent = ""
    if os.path.exists(spec_file):
        with open(spec_file) as f:
            content = f.read()
            import re
            status = re.search(r">\s*状态:\s*(\S+)", content)
            if not status or status.group(1) != "done":
                print("❌ 只有状态为 done 的规格才能创建回顾")
                return ""
            m = re.search(r"\*\*要解决什么问题.*?\*\*\s*\n+(.+)", content)
            if m:
                spec_intent = m.group(1).strip()
    else:
        print(f"❌ 规格不存在: {spec_name}")
        return ""

    retros_dir = os.path.join(project_root, ".agents", "retros")
    os.makedirs(retros_dir, exist_ok=True)

    retro_file = os.path.join(retros_dir, f"{spec_name}.md")
    if os.path.exists(retro_file):
        print(f"⚠️  回顾文件已存在: {retro_file}")
        return retro_file

    tmpl_path = os.path.join(TEMPLATE_DIR, "retro.md")
    if not os.path.exists(tmpl_path):
        print(f"❌ 模板不存在: {tmpl_path}")
        return ""

    with open(tmpl_path) as f:
        template = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = {
        "SPEC_NAME": spec_name,
        "SHIP_DATE": "(上线日期)", "RETRO_DATE": now, "PARTICIPANTS": "(参与回顾的人)",
        "PRIMARY_FAILURE_MODE": "(从共享失败模式中选择，或明确写 none)",
        "SECONDARY_FAILURE_MODE": "(可选；没有则写 none)",
        "FAILURE_MODE_RATIONALE": "(为什么这次问题属于上述失败模式)",
        "ORIGINAL_INTENT": spec_intent or "(从 spec 复制原始意图)",
        "ACTUAL_DELIVERY": "(实际交付了什么)",
        "GAP_ANALYSIS": "(最初意图和实际交付之间的差异及原因)",
        "WENT_WELL_1": "(做得好的地方)", "WENT_WELL_2": "", "WENT_WELL_3": "",
        "WENT_WRONG_1": "(做得不好的地方)", "WENT_WRONG_2": "", "WENT_WRONG_3": "",
        "BUILDER_STRENGTHS": "(Agent 擅长什么)", "BUILDER_WEAKNESSES": "(Agent 反复在什么地方出错)",
        "BUILDER_MISSING_RULES": "(应该补充什么规则来避免这些错误)",
        "REVIEWER_FOUND": "(Review Agent 发现了哪些真实问题)",
        "REVIEWER_MISSED": "(Review Agent 漏掉了什么)",
        "SPEC_CONSTRAINTS_GOOD": "(哪些约束有效)", "SPEC_CONSTRAINTS_MISSING": "(哪些约束应该加但没有加)",
        "AC_COVERAGE": "(验收标准是否覆盖了线上所有情况)",
        "AGENTS_ACCURACY": "(AGENTS.md 是否准确反映了项目)", "RULES_ISSUES": "(规则文件是否有误导)",
        "CONTEXT_UNDERSTANDING": "(Agent 是否正确理解了项目结构)",
        "PROJECT_UPDATES": "(本次复盘后应直接更新的项目规则、文档、testing 或 retro)",
        "SKILL_CANDIDATE": "(yes/no；只有抽象后的治理问题才写 yes)",
        "SKILL_CANDIDATE_SUMMARY": "(如果是 yes，写一句通用治理候选摘要；否则写 none)",
        "ACTION_AGENTS": "(更新 AGENTS.md 的具体内容)",
        "ACTION_RULES": "(更新哪些规则文件)", "ACTION_SPEC_TEMPLATE": "(是否需要调整 spec 模板)",
        "ACTION_REVIEW_CL": "(是否需要调整 review checklist)", "ACTION_OTHER": "(其他行动项)",
    }

    content = template
    for k, v in fields.items():
        content = content.replace("{{" + k + "}}", v)

    atomic_write(retro_file, content)

    print(f"✅ 回顾文件已创建: {retro_file}")
    print(f"📝 诚实填写每个部分。回顾的价值取决于你有多诚实。")
    print(f"💡 填写完后，务必执行行动项——更新规则和 AGENTS.md。")
    return retro_file


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a feature retrospective")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name to retro on")
    args = p.parse_args()
    create_retro(os.path.abspath(args.project_root), args.spec_name)
