#!/usr/bin/env python3
from __future__ import annotations
"""Scan an existing codebase and generate AGENTS.md from detected context.

Usage:
    python3 onboard_project.py <project_root> [--type web|api|cli]
"""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write, backup_file
from policy_sources import scan_policy_sources
from workflow_state import ensure_workflow

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def onboard_project(root: str, project_type: str = "generic", force: bool = False) -> None:
    root = os.path.abspath(root)
    project_name = _detect_project_name(root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Detection
    tech = _detect_tech_deep(root)
    structure = _detect_structure(root)
    test_fw = _detect_test_frameworks(root)
    linter = _detect_linter(root)
    pkg_manager = _detect_package_manager(root)
    git_branch = _git_branch(root)
    git_remote = _git_remote(root)

    # Create .agents structure
    agents_dir = os.path.join(root, ".agents")
    for sub in ["rules", "specs", "plans", "reviews", "designs", "retros"]:
        os.makedirs(os.path.join(agents_dir, sub), exist_ok=True)

    # Generate AGENTS.md
    tmpl_path = os.path.join(TEMPLATE_DIR, "agents-phase-gates.md")
    if os.path.exists(tmpl_path):
        with open(tmpl_path) as f:
            template = f.read()
    else:
        print("❌ 模板文件缺失")
        return

    # Build description
    if git_remote:
        desc = f"{project_name} — {_guess_description(root, tech)}"
    else:
        desc = f"{project_name}"

    language = tech.get("language") or "待确认"
    framework = tech.get("framework") or "待确认"
    database = tech.get("database") or "待确认"
    deployment = tech.get("deployment") or "待确认"
    test_str = test_fw or "待确认"

    # Detect existing conventions
    naming = _detect_naming_convention(root, language)

    content = template
    replacements = {
        "PROJECT_NAME": project_name,
        "PROJECT_DESCRIPTION": desc,
        "LANGUAGE_RUNTIME": language,
        "FRAMEWORK": framework,
        "DATABASE": database,
        "DEPLOYMENT": deployment,
        "PROJECT_STRUCTURE": structure,
        "NAMING_CONVENTION": naming,
        "FORMATTER": linter or "待确认",
        "PACKAGE_MANAGER": pkg_manager or "待确认",
        "TEST_FRAMEWORK": test_str,
        "GIT_STRATEGY": f"当前分支: {git_branch}" if git_branch else "待确认",
        "ARCHITECTURE_CONSTRAINT_1": "（请根据实际架构补充）",
        "ARCHITECTURE_CONSTRAINT_2": "（请根据实际架构补充）",
        "ARCHITECTURE_CONSTRAINT_3": "（请根据实际架构补充）",
        "SECURITY_REQUIREMENT_1": "（请根据项目风险与现有规则补充）",
        "SECURITY_REQUIREMENT_2": "（请根据项目风险与现有规则补充）",
        "DO_NOT_DO_1": "（请明确禁止修改的系统边界）",
        "DO_NOT_DO_2": "（请明确依赖引入策略）",
        "DO_NOT_DO_3": "（请明确兼容性与重构限制）",
        "CURRENT_PHASE": f"已接手，分支: {git_branch}" if git_branch else "已接手",
        "LAST_UPDATED": now,
    }
    for k, v in replacements.items():
        content = content.replace("{{" + k + "}}", v)
    content = re.sub(r"\{\{.*?\}\}", "（请手动补充）", content)

    agents_path = os.path.join(root, "AGENTS.md")
    if os.path.exists(agents_path) and not force:
        raise FileExistsError("AGENTS.md 已存在；使用 refresh_context.py 更新，或用 --force 覆盖")
    if force:
        backup_file(agents_path, os.path.join(agents_dir, "backups", "onboard"))
    atomic_write(agents_path, content)
    ensure_workflow(root)

    # Copy rule templates (don't overwrite existing)
    for rf in ["api.md", "db.md", "error.md", "security.md", "frontend.md", "testing.md"]:
        src = os.path.join(TEMPLATE_DIR, "rules", rf)
        dst = os.path.join(agents_dir, "rules", rf)
        if os.path.exists(src) and not os.path.exists(dst):
            with open(src) as f:
                atomic_write(dst, f.read())
    policy_manifest = scan_policy_sources(Path(root), apply=True)

    # Summary
    print(f"✅ 项目已接手: {root}")
    print(f"   AGENTS.md 已生成（基于自动检测，含阶段强制规范）")
    print()
    print(f"📋 检测结果:")
    print(f"   语言: {language}")
    print(f"   框架: {framework}")
    print(f"   数据库: {database}")
    print(f"   部署: {deployment}")
    print(f"   测试: {test_str}")
    print(f"   包管理: {pkg_manager}")
    print(f"   格式化: {linter or '未检测到'}")
    print(f"   命名规范: {naming}")
    print(f"   规范来源: {len(policy_manifest['sources'])} 个")
    print(f"   待确认差异: {len(policy_manifest.get('review_items', []))} 项")
    print(f"   差异清单: .agents/policy-differences.md")
    print()
    print(f"⚠️  请手动检查并补充:")
    print(f"   1. 项目描述（PROJECT_DESCRIPTION）")
    print(f"   2. 架构约束（ARCHITECTURE_CONSTRAINT_*）")
    print(f"   3. 安全要求（SECURITY_REQUIREMENT_*）")
    print(f"   4. 不让 Agent 做的事（DO_NOT_DO_*）")


def _detect_project_name(root: str) -> str:
    # Try package.json first
    pkg_path = os.path.join(root, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path) as f:
                pkg = json.load(f)
                if pkg.get("name"):
                    return pkg["name"]
        except (json.JSONDecodeError, KeyError):
            pass
    # Try pyproject.toml
    pyro_path = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyro_path):
        with open(pyro_path) as f:
            m = re.search(r'name\s*=\s*"([^"]+)"', f.read())
            if m:
                return m.group(1)
    # Fallback to directory name
    return os.path.basename(root)


def _detect_tech_deep(root: str) -> dict:
    """Deep tech stack detection."""
    result = {"language": "", "framework": "", "database": "", "deployment": ""}
    files = os.listdir(root)

    # --- Node.js / TypeScript ---
    if "package.json" in files:
        with open(os.path.join(root, "package.json")) as f:
            try:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "typescript" in deps:
                    result["language"] = "TypeScript"
                else:
                    result["language"] = "JavaScript"

                # Framework detection (order matters: more specific first)
                if "next" in deps:
                    result["framework"] = "Next.js"
                elif "remix" in deps or "@remix-run" in str(deps):
                    result["framework"] = "Remix"
                elif "nuxt" in deps:
                    result["framework"] = "Nuxt"
                elif "@angular/core" in deps:
                    result["framework"] = "Angular"
                elif "react" in deps:
                    if "express" in deps:
                        result["framework"] = "React + Express"
                    elif "fastify" in deps:
                        result["framework"] = "React + Fastify"
                    else:
                        result["framework"] = "React"
                elif "vue" in deps:
                    result["framework"] = "Vue"
                elif "svelte" in deps:
                    result["framework"] = "Svelte"
                elif "express" in deps:
                    result["framework"] = "Express"
                elif "fastify" in deps:
                    result["framework"] = "Fastify"
                elif "nest" in deps or "@nestjs" in str(deps):
                    result["framework"] = "NestJS"

                # Database detection
                dbs = []
                if "prisma" in deps or "@prisma/client" in deps:
                    dbs.append("PostgreSQL/MySQL (Prisma)")
                if "drizzle-orm" in deps:
                    dbs.append("Drizzle ORM")
                if "knex" in deps:
                    dbs.append("Knex.js")
                if "mongoose" in deps:
                    dbs.append("MongoDB (Mongoose)")
                if "typeorm" in deps:
                    dbs.append("TypeORM")
                if "pg" in deps:
                    dbs.append("PostgreSQL")
                if "mysql2" in deps:
                    dbs.append("MySQL")
                if "better-sqlite3" in deps or "sqlite3" in deps:
                    dbs.append("SQLite")
                if "redis" in deps or "ioredis" in deps:
                    dbs.append("Redis")
                result["database"] = " + ".join(dbs) if dbs else ""

                # Deployment hints
                deploys = []
                if "vercel" in str(pkg).lower():
                    deploys.append("Vercel")
                if "aws-sdk" in deps or "@aws-sdk" in str(deps):
                    deploys.append("AWS")
                if "firebase" in deps:
                    deploys.append("Firebase")
                result["deployment"] = " + ".join(deploys) if deploys else ""

            except (json.JSONDecodeError, KeyError):
                pass

    # --- Python ---
    if not result["language"]:
        if "pyproject.toml" in files:
            result["language"] = "Python"
            with open(os.path.join(root, "pyproject.toml")) as f:
                content = f.read()
                if "django" in content.lower():
                    result["framework"] = "Django"
                elif "fastapi" in content.lower():
                    result["framework"] = "FastAPI"
                elif "flask" in content.lower():
                    result["framework"] = "Flask"
                if "sqlalchemy" in content.lower():
                    result["database"] = "SQLAlchemy"
                elif "django" in content.lower():
                    result["database"] = "PostgreSQL (Django ORM)"
        elif "requirements.txt" in files:
            result["language"] = "Python"
            with open(os.path.join(root, "requirements.txt")) as f:
                reqs = f.read().lower()
                if "django" in reqs:
                    result["framework"] = "Django"
                elif "fastapi" in reqs:
                    result["framework"] = "FastAPI"
                elif "flask" in reqs:
                    result["framework"] = "Flask"

    # --- Go ---
    if not result["language"] and "go.mod" in files:
        result["language"] = "Go"
        with open(os.path.join(root, "go.mod")) as f:
            content = f.read()
            if "gin-gonic" in content:
                result["framework"] = "Gin"
            elif "echo" in content.lower():
                result["framework"] = "Echo"
            elif "fiber" in content.lower():
                result["framework"] = "Fiber"
            elif "chi" in content.lower():
                result["framework"] = "Chi"

    # --- Rust ---
    if not result["language"] and "Cargo.toml" in files:
        result["language"] = "Rust"
        with open(os.path.join(root, "Cargo.toml")) as f:
            content = f.read()
            if "actix" in content.lower():
                result["framework"] = "Actix Web"
            elif "axum" in content.lower():
                result["framework"] = "Axum"
            elif "rocket" in content.lower():
                result["framework"] = "Rocket"

    # --- Deployment from files ---
    if not result["deployment"]:
        if "Dockerfile" in files:
            result["deployment"] = "Docker"
        if "fly.toml" in files:
            result["deployment"] = "Fly.io"
        if "vercel.json" in files:
            result["deployment"] = "Vercel"
        if os.path.exists(os.path.join(root, ".github/workflows")):
            result["deployment"] = (result["deployment"] + " + CI/CD").strip(" +")

    return result


def _detect_structure(root: str) -> str:
    """Walk project and return a tree-like representation."""
    ignore = {".git", "node_modules", "__pycache__", ".venv", "venv",
              ".next", "dist", "build", ".agents", ".codex", "target",
              ".DS_Store", "coverage", ".turbo", ".cache"}
    lines = []

    def walk(d: str, prefix: str, depth: int):
        if depth > 2:
            return
        try:
            entries = sorted(os.listdir(d))
        except PermissionError:
            return
        dirs = [e for e in entries if os.path.isdir(os.path.join(d, e)) and e not in ignore and not e.startswith(".")]
        files = [e for e in entries if os.path.isfile(os.path.join(d, e)) and e not in ignore and not e.startswith(".")]

        for i, name in enumerate(dirs):
            is_last = (i == len(dirs) - 1) and (len(files) == 0)
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{name}/")
            walk(os.path.join(d, name), prefix + ("    " if is_last else "│   "), depth + 1)

        key_files = [f for f in files if f in (
            "package.json", "tsconfig.json", "pyproject.toml", "go.mod",
            "Cargo.toml", "Dockerfile", "Makefile", "README.md",
            "next.config.js", "vite.config.ts", "tailwind.config.ts"
        )]
        for i, name in enumerate(key_files):
            is_last = i == len(key_files) - 1
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{name}")

    lines.append(f"{os.path.basename(root)}/")
    walk(root, "", 0)
    return "\n".join(lines)


def _detect_test_frameworks(root: str) -> str:
    fws = []
    if os.path.exists(os.path.join(root, "package.json")):
        with open(os.path.join(root, "package.json")) as f:
            try:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for fw in ["vitest", "jest", "mocha", "playwright", "cypress", "testing-library"]:
                    if fw in str(deps).lower():
                        fws.append(fw.capitalize() if fw != "testing-library" else "Testing Library")
            except (json.JSONDecodeError, KeyError):
                pass
    if os.path.exists(os.path.join(root, "pyproject.toml")):
        with open(os.path.join(root, "pyproject.toml")) as f:
            content = f.read()
            if "pytest" in content:
                fws.append("pytest")
    if os.path.exists(os.path.join(root, "go.mod")):
        fws.append("Go testing")
    return " + ".join(fws) if fws else ""


def _detect_linter(root: str) -> str:
    tools = []
    if os.path.exists(os.path.join(root, ".eslintrc.js")) or \
       os.path.exists(os.path.join(root, ".eslintrc.cjs")) or \
       os.path.exists(os.path.join(root, ".eslintrc.json")) or \
       os.path.exists(os.path.join(root, "eslint.config.js")) or \
       os.path.exists(os.path.join(root, "eslint.config.mjs")):
        tools.append("ESLint")
    if os.path.exists(os.path.join(root, ".prettierrc")) or \
       os.path.exists(os.path.join(root, ".prettierrc.json")) or \
       os.path.exists(os.path.join(root, "prettier.config.js")):
        tools.append("Prettier")
    if os.path.exists(os.path.join(root, "biome.json")):
        tools.append("Biome")
    if os.path.exists(os.path.join(root, "pyproject.toml")):
        with open(os.path.join(root, "pyproject.toml")) as f:
            if "ruff" in f.read():
                tools.append("Ruff")
    return " + ".join(tools) if tools else ""


def _detect_package_manager(root: str) -> str:
    if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
        return "pnpm"
    if os.path.exists(os.path.join(root, "yarn.lock")):
        return "yarn"
    if os.path.exists(os.path.join(root, "bun.lockb")):
        return "bun"
    if os.path.exists(os.path.join(root, "package-lock.json")):
        return "npm"
    return ""


def _detect_naming_convention(root: str, language: str) -> str:
    """Guess naming convention from the language."""
    if language in ("TypeScript", "JavaScript"):
        # Check if there are any snake_case files
        return "camelCase (TS/JS 默认)"
    elif language == "Python":
        return "snake_case (Python 默认)"
    elif language == "Go":
        return "camelCase / PascalCase (Go 默认)"
    elif language == "Rust":
        return "snake_case (Rust 默认)"
    return "待确认"


def _guess_description(root: str, tech: dict) -> str:
    """Try to guess what the project does from README or package.json."""
    readme = os.path.join(root, "README.md")
    if os.path.exists(readme):
        with open(readme) as f:
            first_lines = "".join(f.readline() for _ in range(5))
            # Strip markdown headers
            first_lines = re.sub(r'^#+\s*', '', first_lines).strip()
            if first_lines:
                return first_lines.split("\n")[0][:100]

    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            with open(pkg) as f:
                p = json.load(f)
                if p.get("description"):
                    return p["description"][:100]
        except (json.JSONDecodeError, KeyError):
            pass

    return f"一个 {tech.get('framework', '')} 项目".strip()


def _git_branch(root: str) -> str:
    try:
        r = subprocess.run(["git", "-C", root, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or ""
    except Exception:
        return ""


def _git_remote(root: str) -> str:
    try:
        r = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or ""
    except Exception:
        return ""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Onboard an existing project")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument(
        "--type",
        choices=["generic", "web", "api", "cli"],
        default="generic",
        help="Project type",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing AGENTS.md")
    args = p.parse_args()
    try:
        onboard_project(os.path.abspath(args.project_root), args.type, args.force)
    except FileExistsError as error:
        print(f"❌ {error}")
        raise SystemExit(1)
