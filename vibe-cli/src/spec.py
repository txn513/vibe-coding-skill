"""Manage feature specifications."""

import os
from datetime import datetime, timezone

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def create_spec(project_root: str, name: str) -> str:
    """Create a new feature spec from template."""
    specs_dir = os.path.join(project_root, ".agents", "specs")
    os.makedirs(specs_dir, exist_ok=True)

    spec_file = os.path.join(specs_dir, f"{name}.md")
    if os.path.exists(spec_file):
        print(f"⚠️  规格已存在: {spec_file}")
        return spec_file

    template = _read_template("spec.md")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    content = template
    replacements = {
        "SPEC_NAME": name,
        "STATUS": "draft",
        "CREATED_AT": now,
        "UPDATED_AT": now,
        "INTENT": "(描述要解决什么问题，为谁解决)",
        "SUCCESS_CRITERION_1": "(如何判断成功？量化指标)",
        "SUCCESS_CRITERION_2": "",
        "SUCCESS_CRITERION_3": "",
        "TECH_CONSTRAINT_1": "(技术约束，如：不动现有路由)",
        "TECH_CONSTRAINT_2": "",
        "BUSINESS_CONSTRAINT_1": "(业务约束，如：仅限已登录用户)",
        "BUSINESS_CONSTRAINT_2": "",
        "OUT_OF_SCOPE_1": "(明确不做的事)",
        "OUT_OF_SCOPE_2": "",
        "HAPPY_PATH_1": "(正常流程步骤)",
        "HAPPY_PATH_2": "",
        "HAPPY_PATH_3": "",
        "EDGE_CASE_1": "(边界情况)",
        "EDGE_CASE_2": "",
        "ERROR_HANDLING_1": "(错误处理)",
        "ERROR_HANDLING_2": "",
        "NEW_FILES": "(计划新增的文件)",
        "MODIFIED_FILES": "(计划修改的文件)",
        "DO_NOT_TOUCH": "(绝对不动的文件/模块)",
    }
    for key, value in replacements.items():
        content = content.replace("{{" + key + "}}", value)

    with open(spec_file, "w") as f:
        f.write(content)

    print(f"✅ 功能规格已创建: {spec_file}")
    print(f"📝 请编辑该文件，填写意图、约束和验收标准后再开始编码。")
    return spec_file


def list_specs(project_root: str) -> list:
    """List all specs in the project."""
    specs_dir = os.path.join(project_root, ".agents", "specs")
    if not os.path.exists(specs_dir):
        return []
    return sorted([
        f for f in os.listdir(specs_dir)
        if f.endswith(".md") and f != ".gitkeep"
    ])


def read_spec(project_root: str, name: str) -> str | None:
    """Read a spec file content."""
    spec_file = os.path.join(project_root, ".agents", "specs", f"{name}.md")
    if not os.path.exists(spec_file):
        return None
    with open(spec_file) as f:
        return f.read()


def _read_template(name: str) -> str:
    path = os.path.join(TEMPLATE_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""
