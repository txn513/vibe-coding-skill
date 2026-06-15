"""Scaffold a project for Vibe Coding."""

import os
from datetime import datetime, timezone

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def init_project(path: str, project_type: str = "web") -> None:
    """Initialize a project with AGENTS.md and .agents/ structure."""
    project_name = os.path.basename(os.path.abspath(path))
    os.makedirs(path, exist_ok=True)

    # Create directories
    agents_dir = os.path.join(path, ".agents")
    rules_dir = os.path.join(agents_dir, "rules")
    specs_dir = os.path.join(agents_dir, "specs")
    plans_dir = os.path.join(agents_dir, "plans")
    reviews_dir = os.path.join(agents_dir, "reviews")

    for d in [agents_dir, rules_dir, specs_dir, plans_dir, reviews_dir]:
        os.makedirs(d, exist_ok=True)

    # Generate AGENTS.md
    agents_template = _read_template("agents.md")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    defaults = _project_defaults(project_type, project_name)
    content = _render_template(agents_template, {
        "PROJECT_NAME": project_name,
        "PROJECT_DESCRIPTION": defaults["description"],
        "LANGUAGE_RUNTIME": defaults["language"],
        "FRAMEWORK": defaults["framework"],
        "DATABASE": defaults["database"],
        "DEPLOYMENT": defaults["deployment"],
        "PROJECT_STRUCTURE": defaults["structure"],
        "NAMING_CONVENTION": "小写蛇形 (snake_case)",
        "FORMATTER": "prettier + eslint (前端), ruff (Python)",
        "TEST_FRAMEWORK": defaults["test_framework"],
        "GIT_STRATEGY": "trunk-based, feature branches",
        "ARCHITECTURE_CONSTRAINT_1": "前后端分离，API 优先",
        "ARCHITECTURE_CONSTRAINT_2": "无状态服务，状态外存",
        "ARCHITECTURE_CONSTRAINT_3": "异步任务走消息队列",
        "SECURITY_REQUIREMENT_1": "所有外部输入需校验和消毒",
        "SECURITY_REQUIREMENT_2": "API 需认证，敏感操作需二次确认",
        "DO_NOT_DO_1": "不要改构建配置",
        "DO_NOT_DO_2": "不要引入新的第三方依赖（除非明确要求）",
        "DO_NOT_DO_3": "不要重构已有代码（除非明确要求）",
        "CURRENT_PHASE": "项目初始化",
        "LAST_UPDATED": now,
    })

    agents_path = os.path.join(path, "AGENTS.md")
    with open(agents_path, "w") as f:
        f.write(content)

    # Copy rule templates
    rule_files = ["api.md", "db.md", "error.md", "security.md", "frontend.md"]
    for rf in rule_files:
        src = os.path.join(TEMPLATE_DIR, "rules", rf)
        dst = os.path.join(rules_dir, rf)
        if os.path.exists(src):
            with open(src) as f:
                rule_content = f.read()
            with open(dst, "w") as f:
                f.write(rule_content)

    # Create .gitkeep in empty dirs
    for d in [specs_dir, plans_dir, reviews_dir]:
        with open(os.path.join(d, ".gitkeep"), "w") as f:
            f.write("")

    print(f"✅ Vibe Coding 项目初始化完成: {path}")
    print(f"    AGENTS.md → {agents_path}")
    print(f"    规则目录 → {rules_dir}")
    print(f"    规格目录 → {specs_dir}")
    print(f"    计划目录 → {plans_dir}")
    print(f"    审查目录 → {reviews_dir}")
    print()
    print("📋 下一步:")
    print(f"   1. 编辑 AGENTS.md 填入项目具体信息")
    print(f"   2. 编辑 .agents/rules/ 下的规则文件")
    print(f"   3. vibe spec <功能名> — 创建第一个功能规格")


def _read_template(name: str) -> str:
    path = os.path.join(TEMPLATE_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def _render_template(template: str, vars: dict) -> str:
    """Simple {{VAR}} template renderer."""
    result = template
    for key, value in vars.items():
        result = result.replace("{{" + key + "}}", value or "")
    # Clean up any remaining unreplaced placeholders
    import re
    result = re.sub(r"\{\{.*?\}\}", "(待填写)", result)
    return result


def _project_defaults(project_type: str, name: str) -> dict:
    """Return sensible defaults per project type."""
    defaults = {
        "web": {
            "description": f"{name} — 一个 Web 应用。",
            "language": "TypeScript",
            "framework": "React / Next.js",
            "database": "PostgreSQL",
            "deployment": "Vercel / Docker",
            "structure": "src/ (前端), server/ (后端)",
            "test_framework": "Vitest + Playwright",
        },
        "api": {
            "description": f"{name} — 一个 API 服务。",
            "language": "Python 或 TypeScript",
            "framework": "FastAPI 或 Express",
            "database": "PostgreSQL",
            "deployment": "Docker + K8s",
            "structure": "src/ (源码), tests/ (测试)",
            "test_framework": "pytest 或 Vitest",
        },
        "cli": {
            "description": f"{name} — 一个命令行工具。",
            "language": "Python 或 Go",
            "framework": "Click 或 Cobra",
            "database": "SQLite (本地)",
            "deployment": "PyPI 或 Homebrew",
            "structure": "src/ (源码), tests/ (测试)",
            "test_framework": "pytest 或 Go testing",
        },
    }
    return defaults.get(project_type, defaults["web"])
