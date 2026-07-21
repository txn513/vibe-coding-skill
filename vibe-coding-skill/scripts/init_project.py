#!/usr/bin/env python3
from __future__ import annotations
"""Initialize a project for Vibe Coding — creates AGENTS.md and .agents/rules/."""

import argparse
import subprocess
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_write, backup_file
from policy_sources import scan_policy_sources
from workflow_state import ensure_workflow

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")


def _read_skill_version() -> str:
    """Read the VERSION file shipped with the Skill, or 'unknown' if missing.

    Rule 52: doctor compares this value against the project's recorded
    version to detect Skill updates the active session has not picked up.
    """
    version_path = os.path.join(SKILL_DIR, "VERSION")
    if not os.path.exists(version_path):
        return "unknown"
    try:
        with open(version_path, encoding="utf-8") as fp:
            value = fp.read().strip()
        return value or "unknown"
    except OSError:
        return "unknown"


def _record_skill_version(agents_dir: str) -> None:
    """Persist the current Skill version into the project's .agents/.

    On first init the file is created; on subsequent re-inits (--force)
    it is overwritten with the current install. Projects that pre-date
    Rule 52 (no .skill-version file) are skipped silently here and
    picked up lazily by doctor.
    """
    from common import atomic_write as _aw
    target = os.path.join(agents_dir, ".skill-version")
    _aw(target, _read_skill_version() + "\n")


def init_project(path: str, project_type: str = "generic", force: bool = False) -> None:
    project_name = os.path.basename(os.path.abspath(path))
    os.makedirs(path, exist_ok=True)

    agents_dir = os.path.join(path, ".agents")
    rules_dir = os.path.join(agents_dir, "rules")
    specs_dir = os.path.join(agents_dir, "specs")
    plans_dir = os.path.join(agents_dir, "plans")
    reviews_dir = os.path.join(agents_dir, "reviews")

    bugs_dir = os.path.join(agents_dir, "bugs")

    for d in [agents_dir, rules_dir, specs_dir, plans_dir, reviews_dir, bugs_dir]:
        os.makedirs(d, exist_ok=True)

    # Generate AGENTS.md
    tmpl = _read("agents-phase-gates.md")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    defaults = _defaults(project_type, project_name)

    content = _render(tmpl, {
        "PROJECT_NAME": project_name,
        "PROJECT_DESCRIPTION": defaults["description"],
        "LANGUAGE_RUNTIME": defaults["language"],
        "FRAMEWORK": defaults["framework"],
        "DATABASE": defaults["database"],
        "DEPLOYMENT": defaults["deployment"],
        "PROJECT_STRUCTURE": defaults["structure"],
        "NAMING_CONVENTION": "待确认",
        "FORMATTER": "待确认",
        "PACKAGE_MANAGER": "待确认",
        "TEST_FRAMEWORK": defaults["test_framework"],
        "GIT_STRATEGY": "待确认",
        "ARCHITECTURE_CONSTRAINT_1": "（请明确模块边界）",
        "ARCHITECTURE_CONSTRAINT_2": "（请明确依赖方向）",
        "ARCHITECTURE_CONSTRAINT_3": "（请明确数据与状态边界）",
        "SECURITY_REQUIREMENT_1": "（请明确认证、授权与数据保护要求）",
        "SECURITY_REQUIREMENT_2": "（请明确输入校验、日志与密钥要求）",
        "DO_NOT_DO_1": "（请明确禁止修改的系统边界）",
        "DO_NOT_DO_2": "（请明确依赖引入策略）",
        "DO_NOT_DO_3": "（请明确兼容性与重构限制）",
        "CURRENT_PHASE": "项目初始化",
        "LAST_UPDATED": now,
    })

    agents_path = os.path.join(path, "AGENTS.md")
    if os.path.exists(agents_path) and not force:
        raise FileExistsError("AGENTS.md 已存在；使用 --force 才能覆盖")
    if force:
        backup_file(agents_path, os.path.join(agents_dir, "backups", "init"))
    atomic_write(agents_path, content)

    # Copy rule templates
    for rf in ["api.md", "db.md", "error.md", "security.md", "frontend.md", "testing.md"]:
        src = os.path.join(TEMPLATE_DIR, "rules", rf)
        dst = os.path.join(rules_dir, rf)
        if os.path.exists(src) and (force or not os.path.exists(dst)):
            if force:
                backup_file(dst, os.path.join(agents_dir, "backups", "init-rules"))
            with open(src) as f:
                atomic_write(dst, f.read())

    for d in [specs_dir, plans_dir, reviews_dir]:
        atomic_write(os.path.join(d, ".gitkeep"), "")

    # Create .gitignore for vibe-generated files (2026-07-12)
    gitignore_path = os.path.join(path, ".gitignore")
    if not os.path.exists(gitignore_path):
        gitignore_content = """# Vibe Coding generated files
.agents/.skill-version
.agents/archive/
.agents/evidence/*/verify-reproduction.md
.agents/evidence/*/verify-fix-regression.md
.agents/enforcer-log.md
"""
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(gitignore_content)
        print(f"   .gitignore — 已创建（忽略 vibe 生成文件）")
    else:
        print(f"   .gitignore — 已存在，跳过")

    # Record the Skill version that initialised this project (Rule 52).
    _record_skill_version(agents_dir)
    workflow, _ = ensure_workflow(path)
    policy_manifest = scan_policy_sources(Path(path), apply=True)

    # Rule 65: bug-inbox opt-in. When workflow.bugs.inbox is true, generate
    # .agents/bug-inbox.md from templates/bug-inbox.md so the project has
    # a fresh append-only bug ledger scaffold. Existing projects that
    # already have a bug-inbox.md are not overwritten (init is idempotent
    # for that file — the agent manually migrated content keeps priority).
    bugs = (workflow or {}).get("bugs", {})
    if bugs.get("inbox", False):
        inbox_src = os.path.join(TEMPLATE_DIR, "bug-inbox.md")
        inbox_dst = os.path.join(agents_dir, "bug-inbox.md")
        if os.path.exists(inbox_src) and not os.path.exists(inbox_dst):
            with open(inbox_src, encoding="utf-8") as f:
                inbox_content = f.read()
            # Stamp the initialisation date into the catalog header so the
            # template doesn't ship with a placeholder.
            inbox_content = inbox_content.replace(
                "YYYY-MM-DD",
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            atomic_write(inbox_dst, inbox_content)
            print(f"   .agents/bug-inbox.md — bug 入口 ledger (Rule 65, bugs.inbox=true)")
        elif os.path.exists(inbox_dst):
            print(f"   .agents/bug-inbox.md — 已存在, 未覆盖 (保留项目级内容)")
        else:
            print(f"   ⚠️  bugs.inbox=true 但 templates/bug-inbox.md 不存在")

    # Auto git init if not a repo (2026-07-12: many agents forget this step)
    git_dir = os.path.join(path, ".git")
    if not os.path.isdir(git_dir):
        try:
            subprocess.run(["git", "init", "-q", path], check=True, capture_output=True)
            print(f"   git init — 已初始化仓库")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"   ⚠️  git init 失败（git 未安装或非 git 项目），跳过")
    else:
        print(f"   git init — 已存在，跳过")

    # Install commit-msg hook if inside a git repo (Rule 53 enforcement)
    git_dir = os.path.join(path, ".git")
    if os.path.isdir(git_dir):
        hook_path = os.path.join(git_dir, "hooks", "pre-commit")
        if not os.path.exists(hook_path):
            try:
                import install_precommit_hook
                install_precommit_hook.install_hook(path)
                print(f"   .git/hooks/commit-msg — 已安装（阻止 raw git commit）")
            except Exception:
                print(f"   ⚠️  commit-msg hook 安装失败，请手动运行: vibe install-precommit-hook {path}")
        else:
            print(f"   .git/hooks/commit-msg — 已存在，跳过")
    else:
        print(f"   ⚠️  未检测到 git 仓库，跳过 commit-msg hook 安装")
        print(f"      如需安装：cd {path} && git init && vibe install-precommit-hook {path}")

    print(f"✅ 项目初始化完成: {path}")
    print()
    print(f"📋 下一步做什么？")
    print(f"   1. 填写 AGENTS.md（技术栈、架构约束、安全要求等）")
    print(f"   2. 运行 `vibe next {path}` 查看当前推荐")
    print(f"   3. 如果有需求，运行 `vibe intent {path} <需求名称>` 开始 Discovery")
    print()
    print(f"📂 已创建：")
    print(f"   AGENTS.md     — Agent 上下文文件（含阶段强制规范）")
    print(f"   .agents/rules/ — 编码规范 (api, db, error, security, frontend)")
    print(f"   .agents/specs/ — 功能规格")
    print(f"   .agents/plans/ — 实施计划")
    print(f"   .agents/reviews/ — 审查记录")
    print(f"   .agents/policy-sources.json — 规范来源与冲突记录")
    print(f"   .agents/policy-differences.md — 待确认规范差异摘要 ({len(policy_manifest.get('review_items', []))} 项)")
    print(f"   .git/hooks/commit-msg — 阻止 raw git commit（Rule 53）")
    print(f"   .gitignore — 忽略 vibe 生成文件")


def _read(name: str) -> str:
    p = os.path.join(TEMPLATE_DIR, name)
    if os.path.exists(p):
        with open(p) as f:
            return f.read()
    return ""


def _render(template: str, vars: dict) -> str:
    result = template
    for k, v in vars.items():
        result = result.replace("{{" + k + "}}", v or "")
    return re.sub(r"\{\{.*?\}\}", "(待填写)", result)


def _defaults(ptype: str, name: str) -> dict:
    return {
        "generic": {
            "description": f"{name} — 项目目标待确认。",
            "language": "待确认", "framework": "待确认",
            "database": "待确认", "deployment": "待确认",
            "structure": "（请描述主要目录及职责）",
            "test_framework": "待确认",
        },
        "web": {
            "description": f"{name} — 一个 Web 应用。",
            "language": "待确认", "framework": "待确认",
            "database": "待确认", "deployment": "待确认",
            "structure": "（请描述主要目录及职责）",
            "test_framework": "待确认",
        },
        "api": {
            "description": f"{name} — 一个 API 服务。",
            "language": "待确认", "framework": "待确认",
            "database": "待确认", "deployment": "待确认",
            "structure": "（请描述主要目录及职责）",
            "test_framework": "待确认",
        },
        "cli": {
            "description": f"{name} — 一个命令行工具。",
            "language": "待确认", "framework": "待确认",
            "database": "待确认", "deployment": "待确认",
            "structure": "（请描述主要目录及职责）",
            "test_framework": "待确认",
        },
    }.get(ptype, {
        "description": f"{name}", "language": "待定", "framework": "待定",
        "database": "待定", "deployment": "待定", "structure": "待定",
        "test_framework": "待定",
    })


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Initialize a Vibe Coding project")
    p.add_argument("path", nargs="?", default=".", help="Project path")
    p.add_argument("--type", choices=["generic", "web", "api", "cli"], default="generic")
    p.add_argument("--force", action="store_true", help="Overwrite existing AGENTS.md and builtin rules")
    args = p.parse_args()
    try:
        init_project(os.path.abspath(args.path), args.type, args.force)
    except FileExistsError as error:
        print(f"❌ {error}")
        raise SystemExit(1)
