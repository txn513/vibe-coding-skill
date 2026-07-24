#!/usr/bin/env python3
from __future__ import annotations
"""vibe upgrade — bring an existing project up to the current Skill.

For a project that was initialised by an older version of the Skill,
this command:

  0. Git pulls the Skill repo (--ff-only) so local code matches GitHub.
     This ensures symlink-based installs always have the latest code.

  1. Records the current Skill VERSION in .agents/.skill-version so
     Rule 52 (version drift detection) can start working on the next
     `vibe doctor` run. Pre-Rule-52 projects (no .skill-version)
     are picked up here without touching anything else.

  2. Diagnoses Rule 53 readiness: is the project configured with a
     `commands.verify`? If not, prints the exact workflow.json snippet
     to add. `vibe commit` refuses to run on a project without a
     verify command (Rule 53 hard-fail).

The command is idempotent: re-running it is safe. Step 0 is a
fast-forward-only pull; if it fails (diverged branches, no git repo),
the command continues with the local code. The verify-command step is
advisory-only (the user must choose the right command for their
project's stack).

Usage:
    vibe upgrade <project_root>
"""


import argparse
import os
import sys

import workflow_state
from common import atomic_write, check_skill_version_drift


def _read_current_version() -> str:
    """Read the Skill's currently installed VERSION, or 'unknown'."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    version_path = os.path.join(skill_dir, "VERSION")
    if not os.path.exists(version_path):
        return "unknown"
    try:
        with open(version_path, encoding="utf-8") as fp:
            value = fp.read().strip()
        return value or "unknown"
    except OSError:
        return "unknown"





def upgrade(project_root: str) -> int:
    project_root = os.path.abspath(project_root)
    agents_dir = os.path.join(project_root, ".agents")
    if not os.path.isdir(agents_dir):
        print(f"❌ 项目未初始化 Vibe Coding：{agents_dir} 不存在")
        print("   先运行 `vibe init` 或 `python3 scripts/init_project.py`")
        return 1

    # Pre-step 0: git pull the skill repo to get latest code from GitHub
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("🔄 拉取 Skill 最新代码...")
    try:
        import subprocess as _sp
        pull_result = _sp.run(
            ["git", "pull", "--ff-only"],
            cwd=skill_dir, capture_output=True, text=True, timeout=30,
        )
        if pull_result.returncode == 0:
            if "Already up to date" in pull_result.stdout:
                print("   ✅ Skill 仓库已是最新")
            else:
                print("   ✅ Skill 仓库已更新")
                for line in pull_result.stdout.strip().split("\n")[:5]:
                    print(f"   {line}")
        else:
            print(f"   ⚠️  git pull 失败 (exit {pull_result.returncode})")
            if pull_result.stderr.strip():
                print(f"   {pull_result.stderr.strip()[:200]}")
            print("   本地代码可能不是最新，建议手动 git pull")
    except Exception as exc:
        print(f"   ⚠️  无法 git pull: {exc}")
        print("   如果 skill 不是 git 仓库（如 pip install），可以忽略此提示")
    print()

    # Pre-step 1: detect VERSION drift before any version comparison
    drift_warning = check_skill_version_drift(skill_dir)
    if drift_warning:
        print(f"⚠️  {drift_warning}")
        print()

    # Step 1: record current Skill version
    current = _read_current_version()
    version_file = os.path.join(agents_dir, ".skill-version")
    previous = "unknown"
    if os.path.exists(version_file):
        try:
            with open(version_file, encoding="utf-8") as fp:
                previous = fp.read().strip() or "unknown"
        except OSError:
            previous = "unknown"

    if previous == current:
        print(f"✅ Skill 版本已是最新：{current}")
    else:
        atomic_write(version_file, current + "\n")
        print(f"📝 Skill 版本记录更新：{previous} → {current}")
        print(f"   写入 {version_file}")

    # Step 2: diagnose Rule 53 readiness
    print()
    print("🔍 Rule 53 (pre-commit gate) 状态:")
    try:
        workflow, _ = workflow_state.ensure_workflow(project_root)
    except Exception as exc:  # noqa: BLE001
        print(f"   ⚠️  无法读取 workflow.json: {exc}")
        return 0

    verify_commands = workflow_state.configured_commands(workflow, "verify")
    if verify_commands:
        print(f"   ✅ 已配置 verify 命令 ({len(verify_commands)} 条):")
        for argv in verify_commands:
            print(f"      - {' '.join(argv)}")
        print()
        print("   现在可以用 `vibe commit` 替代裸 `git commit` 了。")
    else:
        print("   ⚠️  未配置 verify 命令 — `vibe commit` 将拒绝运行。")
        print()
        print("   在 .agents/workflow.json 中添加 commands.verify，例如：")
        print()
        print('   Python 项目:    "verify": [["pytest", "-x"]]')
        print('   Node 项目:      "verify": [["pnpm", "test"]]')
        print('   Go 项目:        "verify": [["go", "test", "./..."]]')
        print('   自定义脚本:    "verify": [["./scripts/verify.sh"]]')
        print()
        print("   配置完成后，`vibe commit` 才会真正生效。")

    # Step 3: auto-upgrade AGENTS.md with AGENT-MANDATORY retrofit (2026-07-14)
    print("\n🔍 AGENTS.md 升级检测:")
    try:
        import upgrade_agents
        upgrade_agents.upgrade_agents(project_root)
    except Exception:
        pass  # advisory only, do not block upgrade

    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="vibe.py upgrade",
        description="Bring an existing project up to the current Skill version",
    )
    p.add_argument("project_root", help="Project root to upgrade")
    args = p.parse_args()
    sys.exit(upgrade(args.project_root))


if __name__ == "__main__":
    main()
