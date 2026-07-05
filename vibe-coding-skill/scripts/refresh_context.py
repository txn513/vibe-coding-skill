#!/usr/bin/env python3
"""Scan project and update AGENTS.md with current state."""

import argparse
import os
import json
import re
from datetime import datetime, timezone

from common import atomic_write

# Lazy import to avoid circular dependency
_update_agents = None

def _get_update_agents():
    global _update_agents
    if _update_agents is None:
        import importlib.util
        import sys
        script_dir = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("update_agents", os.path.join(script_dir, "update_agents.py"))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["update_agents"] = mod
            spec.loader.exec_module(mod)
            _update_agents = mod
    return _update_agents


IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist",
    "build", ".agents", ".codex", "target", ".idea", ".vscode",
}


def refresh_context(project_root: str) -> None:
    agents_path = os.path.join(project_root, "AGENTS.md")
    if not os.path.exists(agents_path):
        print("❌ AGENTS.md 不存在，请先运行 init_project.py")
        return

    with open(agents_path) as f:
        content = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Detect tech stack
    tech = _detect_tech(project_root)

    # Detect project structure
    structure = _detect_structure(project_root)

    # Detect test framework
    test_fw = _detect_test_framework(project_root)

    # Detect git info
    branch = _git_branch(project_root)

    updates = []
    suggestions = []

    # Detect additional tools
    formatters = _detect_formatters(project_root)
    pkg_manager = _detect_package_manager(project_root)
    ci_platform = _detect_ci(project_root)

    detected_fields = [
        ("语言/运行时", tech["language"]),
        ("框架", tech["framework"]),
        ("数据库", tech["database"] if tech["database"] != "待定" else ""),
        ("部署", tech["deployment"] if tech["deployment"] != "待定" else ci_platform),
        ("测试框架", test_fw),
        ("格式化", formatters),
        ("包管理", pkg_manager),
    ]
    for label, detected in detected_fields:
        if not detected:
            continue
        old = _extract_labeled_value(content, label)
        if not old or old == detected:
            continue
        if _is_placeholder(old):
            updated = _replace_labeled_value(content, label, detected)
            if updated != content:
                content = updated
                updates.append(f"{label}: {old} → {detected}")
        else:
            suggestions.append(f"{label}: 已记录 `{old}`，检测到 `{detected}`")

    # Update project structure
    old_struct = _extract_section(content, "## 项目结构", "## 编码约定")
    if old_struct and structure and _is_placeholder(old_struct):
        new_block = f"## 项目结构\n\n```\n{structure}\n```\n"
        content = content.replace(old_struct, new_block)
        updates.append("项目结构已更新")
    elif old_struct and structure and structure not in old_struct:
        suggestions.append("项目结构已变化，请核对 AGENTS.md 的人工描述")

    # Update current phase and timestamp
    content = re.sub(
        r"(?m)^-\s*(?:\*\*)?当前阶段(?:\*\*)?:\s*.+$",
        f"- 当前阶段: 开发中 ({branch})",
        content
    )
    content = re.sub(
        r"(?m)^-\s*(?:\*\*)?最后更新(?:\*\*)?:\s*.+$",
        f"- 最后更新: {now}",
        content
    )

    atomic_write(agents_path, content)
    snapshot = os.path.join(project_root, ".agents", "context-refresh.md")
    if suggestions:
        snapshot_content = (
            f"# Context Refresh Review\n\n> 生成: {now}\n\n"
            + "\n".join(f"- {item}" for item in suggestions)
            + "\n"
        )
        atomic_write(snapshot, snapshot_content)
    elif os.path.exists(snapshot):
        os.remove(snapshot)

    # Check if phase-gates section needs update
    phase_gates_advisory = []
    try:
        update_agents_mod = _get_update_agents()
        if update_agents_mod:
            result = update_agents_mod.update_agents(project_root)
            if result.get("success") and not result.get("updated"):
                # Version matches, no update needed
                pass
            elif result.get("success") and result.get("updated"):
                phase_gates_advisory.append(f"阶段强制规范已更新: {result.get('message')}")
    except Exception:
        pass  # Don't fail context-refresh if phase-gates check fails

    print(f"✅ AGENTS.md 已刷新 ({now})")
    if updates:
        print("   变更:")
        for u in updates:
            print(f"   - {u}")
    else:
        print("   (上下文已是最新，无需变更)")
    if phase_gates_advisory:
        print("   阶段强制规范:")
        for advisory in phase_gates_advisory:
            print(f"   - {advisory}")
    if suggestions:
        print(f"   待人工核对: {len(suggestions)} 项，见 .agents/context-refresh.md")
    print()
    print("💡 提示: 检查更新后的 AGENTS.md，手动补充架构约束和安全要求。")


def _detect_tech(root: str) -> dict:
    """Detect tech stack from config files (root + subdirectories)."""
    result = {"language": "", "framework": "", "database": "待定", "deployment": "待定"}

    # Python (root + subdirectories)
    python_configs = set(_find_files(root, {"pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"}))
    if python_configs:
        result["language"] = "Python"
        for cfg in sorted(python_configs):
            try:
                with open(cfg, encoding="utf-8") as f:
                    cfg_content = f.read().lower()
            except (OSError, UnicodeDecodeError):
                continue
            if not result["framework"]:
                if "fastapi" in cfg_content:
                    result["framework"] = "FastAPI"
                elif "django" in cfg_content:
                    result["framework"] = "Django"
                elif "flask" in cfg_content:
                    result["framework"] = "Flask"
                elif "typer" in cfg_content or "click" in cfg_content:
                    result["framework"] = "Typer/Click (CLI)"

    # Node.js / TypeScript (root + subdirectories)
    package_jsons = _find_files(root, {"package.json"})
    if package_jsons:
        for path in sorted(package_jsons):
            try:
                with open(path, encoding="utf-8") as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "typescript" in deps:
                    result["language"] = "TypeScript"
                else:
                    result["language"] = result["language"] or "JavaScript"
                if not result["framework"]:
                    if "next" in deps:
                        result["framework"] = "Next.js"
                    elif "react" in deps:
                        result["framework"] = "React" + (" + Express" if "express" in deps else "")
                    elif "vue" in deps:
                        result["framework"] = "Vue"
                    elif "express" in deps:
                        result["framework"] = "Express"
            except (json.JSONDecodeError, KeyError, OSError):
                continue

    # Go
    for go_mod in _find_files(root, {"go.mod"}):
        if not result["language"]:
            result["language"] = "Go"
        try:
            with open(go_mod, encoding="utf-8") as f:
                first = f.readline()
                if "gin" in first.lower() and not result["framework"]:
                    result["framework"] = "Gin"
        except (OSError, UnicodeDecodeError):
            pass

    # Rust
    for cargo in _find_files(root, {"Cargo.toml"}):
        if not result["language"]:
            result["language"] = "Rust"
        try:
            with open(cargo, encoding="utf-8") as f:
                cargo_content = f.read()
                if not result["framework"]:
                    if "actix" in cargo_content.lower():
                        result["framework"] = "Actix"
                    elif "axum" in cargo_content.lower():
                        result["framework"] = "Axum"
        except (OSError, UnicodeDecodeError):
            pass

    # Detect database
    root_files = set(os.listdir(root))
    if os.path.exists(os.path.join(root, "prisma")):
        result["database"] = "PostgreSQL (Prisma)"
    elif os.path.exists(os.path.join(root, "migrations")):
        result["database"] = "PostgreSQL / MySQL"
    elif any("sqlite" in f.lower() for f in root_files if os.path.isfile(os.path.join(root, f))):
        result["database"] = "SQLite"

    # Detect deployment
    if "Dockerfile" in root_files:
        result["deployment"] = "Docker"
    if "vercel.json" in root_files:
        result["deployment"] = "Vercel"
    # Merge CI detection into deployment after base checks
    ci_detected = _detect_ci(root)
    if ci_detected:
        result["deployment"] = (result["deployment"] + " / " + ci_detected) if result["deployment"] else ci_detected

    if not result["language"]:
        result["language"] = _detect_language_from_source(root)

    return result


def _detect_structure(root: str, depth: int = 2) -> str:
    """Generate a tree-like structure of the project."""
    lines = []
    ignore = IGNORED_DIRS | {".DS_Store", "*.egg-info"}

    def walk(d: str, prefix: str, current_depth: int):
        if current_depth > depth:
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
            next_prefix = prefix + ("    " if is_last else "│   ")
            walk(os.path.join(d, name), next_prefix, current_depth + 1)

        for i, name in enumerate(files[:10]):  # limit files shown
            is_last = i == len(files) - 1 or i == 9
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{name}")
        if len(files) > 10:
            lines.append(f"{prefix}└── ... ({len(files) - 10} more files)")

    lines.append(f"{os.path.basename(root)}/")
    walk(root, "", 0)
    return "\n".join(lines)


def _detect_ci(root: str) -> str:
    """Detect CI/CD platform from standard config locations."""
    found = []
    if os.path.isdir(os.path.join(root, ".github", "workflows")):
        found.append("GitHub Actions")
    if os.path.exists(os.path.join(root, ".gitlab-ci.yml")):
        found.append("GitLab CI")
    if os.path.exists(os.path.join(root, "circleci")) or        os.path.isdir(os.path.join(root, ".circleci")):
        found.append("CircleCI")
    if os.path.exists(os.path.join(root, "Jenkinsfile")):
        found.append("Jenkins")
    if os.path.exists(os.path.join(root, ".travis.yml")):
        found.append("Travis CI")
    if os.path.exists(os.path.join(root, "bitbucket-pipelines.yml")):
        found.append("Bitbucket Pipelines")
    return " + ".join(_dedupe_keep_order(found))

def _detect_formatters(root: str) -> str:
    """Detect code formatters and linters from config files."""
    found = []
    root_files = set(os.listdir(root))
    # Root-level configs
    if ".ruff.toml" in root_files or "ruff.toml" in root_files or        _repo_contains(root, ".toml", ("[tool.ruff]",)):
        found.append("Ruff")
    if "pyproject.toml" in root_files:
        try:
            with open(os.path.join(root, "pyproject.toml")) as f:
                if "[tool.black]" in f.read():
                    found.append("Black")
        except (OSError, UnicodeDecodeError):
            pass
    for name in (".prettierrc", ".prettierrc.json", ".prettierrc.yaml",
                 ".prettierrc.yml", ".prettierrc.js", "prettier.config.js"):
        if name in root_files:
            found.append("Prettier")
            break
    if ".prettierrc" not in root_files and not any(
            n.startswith(".prettierrc") for n in root_files):
        for path in _find_files(root, {"package.json"}):
            try:
                with open(path, encoding="utf-8") as f:
                    pkg = __import__("json").load(f)
                if "prettier" in pkg.get("devDependencies", {}):
                    found.append("Prettier")
                    break
            except Exception:
                continue
    if ".eslintrc.js" in root_files or ".eslintrc.json" in root_files or        ".eslintrc.yaml" in root_files or ".eslintrc.yml" in root_files or        ".eslintrc" in root_files or "eslint.config.js" in root_files:
        found.append("ESLint")
    # Check for biome, oxfmt, dprint
    if "biome.json" in root_files:
        found.append("Biome")
    if "dprint.json" in root_files:
        found.append("dprint")
    return " + ".join(_dedupe_keep_order(found))


def _detect_package_manager(root: str) -> str:
    """Detect package manager from lockfiles and config."""
    root_files = set(os.listdir(root))
    if "pnpm-lock.yaml" in root_files:
        return "pnpm"
    if "yarn.lock" in root_files:
        return "Yarn"
    if "bun.lockb" in root_files:
        return "Bun"
    if "poetry.lock" in root_files or "pyproject.toml" in root_files:
        if "pyproject.toml" in root_files:
            try:
                with open(os.path.join(root, "pyproject.toml")) as f:
                    if "[tool.poetry]" in f.read():
                        return "Poetry"
            except (OSError, UnicodeDecodeError):
                pass
    if "Pipfile" in root_files or "Pipfile.lock" in root_files:
        return "Pipenv"
    if "requirements.txt" in root_files:
        return "pip"
    if "package.json" in root_files:
        return "npm"
    return ""



def _detect_ci(root: str) -> str:
    """Detect CI/CD platform from standard config locations."""
    found = []
    if os.path.isdir(os.path.join(root, ".github", "workflows")):
        found.append("GitHub Actions")
    if os.path.exists(os.path.join(root, ".gitlab-ci.yml")):
        found.append("GitLab CI")
    if os.path.exists(os.path.join(root, "circleci")) or        os.path.isdir(os.path.join(root, ".circleci")):
        found.append("CircleCI")
    if os.path.exists(os.path.join(root, "Jenkinsfile")):
        found.append("Jenkins")
    if os.path.exists(os.path.join(root, ".travis.yml")):
        found.append("Travis CI")
    if os.path.exists(os.path.join(root, "bitbucket-pipelines.yml")):
        found.append("Bitbucket Pipelines")
    return " + ".join(_dedupe_keep_order(found))

def _detect_formatters(root: str) -> str:
    """Detect code formatters and linters from config files."""
    found = []
    root_files = set(os.listdir(root))
    if ".ruff.toml" in root_files or "ruff.toml" in root_files or        _repo_contains(root, ".toml", ("[tool.ruff]",)):
        found.append("Ruff")
    if "pyproject.toml" in root_files:
        try:
            with open(os.path.join(root, "pyproject.toml")) as f:
                if "[tool.black]" in f.read():
                    found.append("Black")
        except (OSError, UnicodeDecodeError):
            pass
    for name in (".prettierrc", ".prettierrc.json", ".prettierrc.yaml",
                 ".prettierrc.yml", ".prettierrc.js", "prettier.config.js"):
        if name in root_files:
            found.append("Prettier")
            break
    if not any(n in found for n in ("Prettier",)):
        for pkg_path in _find_files(root, {"package.json"}):
            try:
                with open(pkg_path, encoding="utf-8") as f:
                    pkg = json.load(f)
                if "prettier" in pkg.get("devDependencies", {}):
                    found.append("Prettier")
                    break
            except Exception:
                continue
    eslint_configs = {".eslintrc.js", ".eslintrc.json", ".eslintrc.yaml",
                      ".eslintrc.yml", ".eslintrc", "eslint.config.js",
                      "eslint.config.mjs", "eslint.config.cjs"}
    if root_files & eslint_configs:
        found.append("ESLint")
    if "biome.json" in root_files:
        found.append("Biome")
    if "dprint.json" in root_files:
        found.append("dprint")
    return " + ".join(_dedupe_keep_order(found))


def _detect_package_manager(root: str) -> str:
    """Detect package manager from lockfiles and config."""
    root_files = set(os.listdir(root))
    if "pnpm-lock.yaml" in root_files:
        return "pnpm"
    if "yarn.lock" in root_files:
        return "Yarn"
    if "bun.lockb" in root_files:
        return "Bun"
    if "poetry.lock" in root_files:
        return "Poetry"
    if "pyproject.toml" in root_files:
        try:
            with open(os.path.join(root, "pyproject.toml")) as f:
                if "[tool.poetry]" in f.read():
                    return "Poetry"
        except (OSError, UnicodeDecodeError):
            pass
    if "Pipfile" in root_files or "Pipfile.lock" in root_files:
        return "Pipenv"
    if "requirements.txt" in root_files:
        return "pip"
    if "package.json" in root_files:
        return "npm"
    return ""

def _detect_test_framework(root: str) -> str:
    if os.path.exists(os.path.join(root, "package.json")):
        with open(os.path.join(root, "package.json")) as f:
            try:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                fws = []
                if "vitest" in deps: fws.append("Vitest")
                if "jest" in deps: fws.append("Jest")
                if "playwright" in deps: fws.append("Playwright")
                if "cypress" in deps: fws.append("Cypress")
                return " + ".join(fws) if fws else ""
            except (json.JSONDecodeError, KeyError):
                pass
    frameworks = []
    if _repo_contains(root, ".py", ("import unittest", "from unittest")):
        frameworks.append("unittest")
    if _repo_contains(root, ".py", ("import pytest", "from pytest")):
        frameworks.append("pytest")
    if _repo_contains(root, {".ts", ".tsx", ".js", ".jsx"}, ("from '@playwright/test'", "playwright")):
        frameworks.append("Playwright")
    if _repo_contains(root, {".ts", ".tsx", ".js", ".jsx"}, ("vitest", "describe(", "it(")):
        package_matches = list(_find_files(root, {"package.json"}))
        if any(_package_has_dependency(path, "vitest") for path in package_matches):
            frameworks.append("Vitest")
    return " + ".join(_dedupe_keep_order(frameworks))
    return ""


def _git_branch(root: str) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", root, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _extract_field(content: str, pattern: str) -> str | None:
    m = re.search(pattern, content)
    return m.group(1).strip() if m else None


def _extract_labeled_value(content: str, label: str) -> str | None:
    patterns = [
        rf"(?m)^-\s+\*\*{re.escape(label)}\*\*:\s*(.+)$",
        rf"(?m)^-\s+{re.escape(label)}:\s*(.+)$",
    ]
    for pattern in patterns:
        value = _extract_field(content, pattern)
        if value is not None:
            return value
    return None


def _replace_labeled_value(content: str, label: str, value: str) -> str:
    patterns = [
        (
            rf"(?m)^(\s*-\s+\*\*{re.escape(label)}\*\*:\s*)(.+)$",
            rf"\g<1>{value}",
        ),
        (
            rf"(?m)^(\s*-\s+{re.escape(label)}:\s*)(.+)$",
            rf"\g<1>{value}",
        ),
    ]
    for pattern, replacement in patterns:
        updated, count = re.subn(pattern, replacement, content, count=1)
        if count:
            return updated
    return content


def _extract_section(content: str, start_header: str, next_header: str) -> str | None:
    """Extract a section between two headers."""
    pattern = rf"({re.escape(start_header)}.*?)(?={re.escape(next_header)})"
    m = re.search(pattern, content, re.DOTALL)
    return m.group(1) if m else None


def _is_placeholder(value: str) -> bool:
    return any(marker in value for marker in ("待确认", "待定", "请描述", "请根据"))


def _find_files(root: str, names: set[str]) -> list[str]:
    matches = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
        for filename in files:
            if filename in names:
                matches.append(os.path.join(current_root, filename))
    return sorted(matches)


def _detect_language_from_source(root: str) -> str:
    counts = {".py": 0, ".ts": 0, ".tsx": 0, ".js": 0, ".jsx": 0, ".go": 0, ".rs": 0}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
        for filename in files:
            _, ext = os.path.splitext(filename)
            if ext in counts:
                counts[ext] += 1

    if counts[".py"]:
        return "Python"
    if counts[".ts"] or counts[".tsx"]:
        return "TypeScript"
    if counts[".js"] or counts[".jsx"]:
        return "JavaScript"
    if counts[".go"]:
        return "Go"
    if counts[".rs"]:
        return "Rust"
    return ""


def _repo_contains(root: str, extensions: str | set[str], markers: tuple[str, ...]) -> bool:
    if isinstance(extensions, str):
        allowed = {extensions}
    else:
        allowed = set(extensions)
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
        for filename in files:
            _, ext = os.path.splitext(filename)
            if ext not in allowed:
                continue
            path = os.path.join(current_root, filename)
            try:
                with open(path, encoding="utf-8") as handle:
                    sample = handle.read(4000)
            except (OSError, UnicodeDecodeError):
                continue
            if any(marker in sample for marker in markers):
                return True
    return False


def _package_has_dependency(path: str, dependency: str) -> bool:
    try:
        with open(path, encoding="utf-8") as handle:
            pkg = json.load(handle)
    except (OSError, json.JSONDecodeError, KeyError):
        return False
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    return dependency in deps


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Refresh AGENTS.md context")
    p.add_argument("project_root", help="Project root directory")
    args = p.parse_args()
    refresh_context(os.path.abspath(args.project_root))
