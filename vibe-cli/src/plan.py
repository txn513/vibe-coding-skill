"""Generate implementation plans from specs."""

import importlib
import os
import re
from datetime import datetime, timezone

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def generate_plan(project_root: str, spec_name: str) -> str | None:
    """Generate a plan file from a spec."""
    spec_mod = importlib.import_module("spec")
    spec_content = spec_mod.read_spec(project_root, spec_name)
    if spec_content is None:
        print(f"❌ 规格不存在: {spec_name}")
        return None

    plans_dir = os.path.join(project_root, ".agents", "plans")
    os.makedirs(plans_dir, exist_ok=True)

    plan_file = os.path.join(plans_dir, f"{spec_name}.md")

    template = _read_template("plan.md")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ac_count = len(re.findall(r"HAPPY_PATH", spec_content))
    scope_new = _extract_field(spec_content, "NEW_FILES")
    scope_mod = _extract_field(spec_content, "MODIFIED_FILES")

    content = template
    replacements = {
        "SPEC_NAME": spec_name,
        "SPEC_FILE": f".agents/specs/{spec_name}.md",
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
    }
    for key, value in replacements.items():
        content = content.replace("{{" + key + "}}", value)
    content = re.sub(r"\{\{.*?\}\}", "（请根据实际情况填写）", content)

    with open(plan_file, "w") as f:
        f.write(content)

    print(f"✅ 实施计划已生成: {plan_file}")
    print(f"📋 包含 3 个 Phase，每个 Phase 有验证门禁。")
    print(f"💡 提示: 每个 Phase 完成后用 vibe check 验证。")
    return plan_file


def _extract_field(spec: str, field: str) -> str:
    """Extract a field value from spec content."""
    pattern = rf"- \*\*{field}\*\*: (.+)"
    match = re.search(pattern, spec)
    if match:
        val = match.group(1).strip()
        if val and "(计划" not in val and "(描述" not in val:
            return val
    return ""


def _read_template(name: str) -> str:
    path = os.path.join(TEMPLATE_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""
