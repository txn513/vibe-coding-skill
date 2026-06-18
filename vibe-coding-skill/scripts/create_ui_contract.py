#!/usr/bin/env python3
"""Create UI design or redesign contract drafts for a spec."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write, validate_artifact_name

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates"

SOURCE_TYPES = {
    "manual",
    "screenshot",
    "opendesign",
    "penpot",
    "figma",
    "mixed",
    "other",
}
MODEL_CAPABILITIES = {"text-only", "multimodal", "mixed", "unknown"}


def create_ui_contract(
    project_root: str,
    spec_name: str,
    *,
    redesign: bool = False,
    source_type: str = "manual",
    source_artifacts: str = "",
    generated_by: str = "",
    model_capability: str = "unknown",
) -> str:
    """Create a project-local UI contract draft under .agents/specs/<spec>/."""
    spec_name = validate_artifact_name(spec_name, "规格名称")
    source_type = _normalize_choice(source_type, SOURCE_TYPES, "source type")
    model_capability = _normalize_choice(
        model_capability, MODEL_CAPABILITIES, "model capability"
    )

    spec_dir = Path(project_root) / ".agents" / "specs" / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)

    filename = "ui-redesign-contract.md" if redesign else "ui-design-contract.md"
    contract_path = spec_dir / filename
    if contract_path.exists():
        print(f"⚠️  UI 合同已存在: {contract_path}")
        return str(contract_path)

    template_name = "ui-redesign-contract.md" if redesign else "ui-design-contract.md"
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        print(f"❌ 模板不存在: {template_path}")
        return ""

    content = _render_template(
        template_path.read_text(encoding="utf-8"),
        _fields(
            spec_name,
            source_type,
            source_artifacts,
            generated_by,
            model_capability,
        ),
    )
    atomic_write(contract_path, content)

    print(f"✅ UI 合同已创建: {contract_path}")
    print("🎨 将设计工具输出转成 UI-AC、状态、组件映射和证据计划后再实施。")
    return str(contract_path)


def _normalize_choice(value: str, allowed: set[str], label: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        normalized = "unknown" if "unknown" in allowed else "manual"
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{label} 必须是以下之一: {allowed_values}")
    return normalized


def _fields(
    spec_name: str,
    source_type: str,
    source_artifacts: str,
    generated_by: str,
    model_capability: str,
) -> dict[str, str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    common = {
        "SPEC_NAME": spec_name,
        "CREATED_AT": now,
        "SOURCE_TYPE": source_type,
        "SOURCE_ARTIFACTS": source_artifacts or "(记录设计工具输出、截图、链接或本地路径)",
        "GENERATED_BY": generated_by or "(工具、Agent 或人工来源)",
        "MODEL_CAPABILITY": model_capability,
        "FRESHNESS": "(记录设计产物生成时间与是否仍适用)",
        "PROJECT_UI_CONSTRAINTS": "(记录 AGENTS.md、项目规则或用户明确要求中的视觉禁令、组件约束、动效限制、图标策略等；外部设计工具不得覆盖这些约束)",
        "DESIGN_VERSION": "v1",
        "DESIGN_BASELINE": "(首次设计填 none；迭代设计填上一版合同、设计产物或 evidence 路径)",
        "DESIGN_CHANGED": "(相对上一版改变了什么)",
        "DESIGN_PRESERVED": "(明确保留什么视觉、交互、信息架构或行为)",
        "DESIGN_ABANDONED": "(明确放弃什么旧方案或旧承诺)",
        "DESIGN_ROLLBACK_TARGET": "(可回退到的上一版合同、设计源或归档路径；首次设计填 none)",
        "DESIGN_SPEC_IMPACT": "(影响哪些 spec、UI-AC、行为 AC、计划或实现范围；没有则写 none)",
        "DESIGN_EVIDENCE_UPDATE": "(需要新增或更新哪些截图、录屏、visual diff、交互验证或回归证据)",
        "INTENT": "(说明这个 UI 支持的用户任务，以及首屏最应该传达什么)",
        "INFORMATION_ARCHITECTURE": "(页面区域、层级、导航、主要/次要内容)",
        "LAYOUT": "(桌面、平板、移动端布局规则与断点要求)",
        "DESIGN_TOKENS": "(颜色、字体、间距、圆角、阴影、断点、状态 token)",
        "COMPONENT_MAP": "(设计元素到项目组件的映射)",
        "STATES": "(loading、empty、error、disabled、hover、focus、selected、overflow、responsive 等状态)",
        "ACCESSIBILITY": "(键盘导航、焦点可见性、对比度、标签、ARIA、低动效要求)",
        "UI_AC_1": "(视觉/布局验收标准)",
        "UI_AC_2": "(交互/状态验收标准)",
        "UI_AC_3": "(响应式/可访问性验收标准)",
        "EVIDENCE_PLAN": "(截图、录屏、浏览器输出、Storybook capture、visual diff 或等价证据；必须映射 UI-AC)",
        "OUT_OF_SCOPE": "(明确不包含的视觉、交互或设计系统工作)",
    }
    common.update(
        {
            "EXISTING_UI_INVENTORY": "(现有路由、页面、组件、状态、截图、token 与关键用户路径)",
            "CURRENT_BEHAVIOR_TO_PRESERVE": "(必须保留的业务流程、字段、URL、权限、数据语义、键盘行为和交互)",
            "REDESIGN_GOALS": "(视觉系统、密度、导航、响应式、可访问性、一致性等改进目标)",
            "REPLACE": "(允许替换的视觉系统、布局、组件、导航或交互模式)",
            "PRESERVE": "(明确不能改变的行为和 UI affordance)",
            "COMPONENT_MIGRATION_MAP": "(旧组件或模式 -> 新组件或模式)",
            "LAYOUT_MIGRATION": "(桌面、平板、移动端布局变化)",
            "REGRESSION_RISKS": "(易坏断点、工作流、边界情况和旧 UI 路径)",
            "MIGRATION_STEP_1": "(token/theme)",
            "MIGRATION_STEP_2": "(shared components)",
            "MIGRATION_STEP_3": "(pages/app shell and cleanup)",
            "BEHAVIOR_AC_1": "(必须保持不变的行为验收标准)",
            "BEHAVIOR_AC_2": "(回归路径验收标准)",
        }
    )
    return common


def _render_template(template: str, fields: dict[str, str]) -> str:
    content = template
    for key, value in fields.items():
        content = content.replace("{{" + key + "}}", value)
    return content


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a UI contract draft")
    parser.add_argument("project_root", help="Project root directory")
    parser.add_argument("spec_name", help="Spec name")
    parser.add_argument("--redesign", action="store_true", help="Create redesign contract")
    parser.add_argument("--source-type", default="manual", choices=sorted(SOURCE_TYPES))
    parser.add_argument("--source-artifacts", default="")
    parser.add_argument("--generated-by", default="")
    parser.add_argument(
        "--model-capability", default="unknown", choices=sorted(MODEL_CAPABILITIES)
    )
    args = parser.parse_args()
    create_ui_contract(
        os.path.abspath(args.project_root),
        args.spec_name,
        redesign=args.redesign,
        source_type=args.source_type,
        source_artifacts=args.source_artifacts,
        generated_by=args.generated_by,
        model_capability=args.model_capability,
    )
