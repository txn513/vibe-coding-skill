#!/usr/bin/env python3
"""Create a feature retrospective template."""

import argparse
import os
import re
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
        with open(retro_file, encoding="utf-8") as handle:
            _print_claim_evidence_warnings(handle.read())
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
        "CLAIM_EVIDENCE": "(evidence 路径、日志、测试输出、截图或记录交互；没有则写 none)",
        "UNVERIFIED_CLAIMS": "(未经复验的历史观察；没有则写 none)",
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


def claim_evidence_warnings(content: str) -> list[str]:
    wrongs = _real_bullets_in_section(content, "做错了什么")
    if not wrongs:
        return []
    evidence = _section(content, "结论证据")
    if not evidence:
        return ["做错了什么包含真实结论，但缺少结论证据段"]
    if _has_real_claim_evidence(evidence):
        return []
    return ["做错了什么包含真实结论，但结论证据仍未填写"]


def _print_claim_evidence_warnings(content: str) -> None:
    for warning in claim_evidence_warnings(content):
        print(f"⚠️  {warning}")
        # 候选 2 落地: 列出全部 evidence 类型,Agent 一眼能选
        print("   请补以下任一 evidence 引用,或显式标注 '未复验历史观察':")
        print("   - 复现命令 / logcat / dumpsys / 单元测试 / 截图 / 调用栈 / diff")
        print("   - 或显式 'unverified historical note' 标注")


def _section(content: str, title: str) -> str:
    pattern = re.compile(
        rf"^##\s+.*{re.escape(title)}.*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(content)
    return match.group(1) if match else ""


def _real_bullets_in_section(content: str, title: str) -> list[str]:
    section = _section(content, title)
    result = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        text = stripped[1:].strip()
        if _is_placeholder(text):
            continue
        result.append(text)
    return result


# 候选 2 retro 列出 + eink-app-dev 卫生修复观察补充的 evidence 关键字
# 大小写不敏感; 中文关键字直接匹配原文
EVIDENCE_KEYWORDS_EN = (
    "evidence", "log", "test", "screenshot", "unverified",
    "logcat", "dumpsys", "repro", "reproduce", "trace", "stack", "diff",
)
EVIDENCE_KEYWORDS_CN = (
    "证据", "日志", "测试", "截图", "未复验", "记录",
    "复现命令", "复现步骤", "验证", "堆栈", "调用栈",
)


def _has_real_claim_evidence(section: str) -> bool:
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        if _is_placeholder(stripped):
            continue
        lower = stripped.lower()
        if "none" in lower and "未复验" not in stripped and "unverified" not in lower:
            continue
        if any(marker in lower for marker in EVIDENCE_KEYWORDS_EN):
            return True
        if any(marker in stripped for marker in EVIDENCE_KEYWORDS_CN):
            return True
    return False


def _is_placeholder(text: str) -> bool:
    stripped = text.strip()
    return (
        not stripped
        or "{{" in stripped
        or stripped in {"-", "*"}
        or stripped.startswith("(")
        or stripped.startswith("（")
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a feature retrospective")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", help="Spec name to retro on")
    args = p.parse_args()
    create_retro(os.path.abspath(args.project_root), args.spec_name)
