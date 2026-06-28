#!/usr/bin/env python3
"""vibe commit — Rule 53 pre-commit verification gate.

Wraps `git commit` with three discipline steps that the agent is
otherwise likely to skip:

  1. Review — show `git diff --stat` so the author sees the blast
     radius of the commit (Rule 12 spirit: composed path still
     intact).
  2. Verify — run every command listed in workflow.json's
     commands.verify phase. If any fails, the commit is aborted
     before a single byte is added to the project history.
  3. Commit — only if both steps pass, hand off to `git commit`
     with the user's argv appended unchanged.

This module is the executable half of Rule 53. The advisory text
in SKILL.md is the policy half. The wrapper is opt-in: agents
that call raw `git commit` are not blocked at the file level,
but the user can wire a pre-commit hook (one-line install) to
enforce `vibe commit` for everyone.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from workflow_state import (
    SCHEMA_VERSION,
    configured_commands,
    ensure_workflow,
)


def _run(argv: list[str], cwd: str) -> tuple[int, str, str]:
    """Run argv in cwd; return (exit_code, stdout, stderr)."""
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _git_diff_stat(project_root: str) -> str:
    """Return `git diff --stat` against HEAD plus untracked file list.

    Empty diff is a hard failure: there is nothing to commit.
    """
    rc, out, err = _run(
        ["git", "diff", "--stat", "HEAD"], project_root
    )
    if rc != 0:
        # No commits yet — diff against the empty tree
        rc, out, err = _run(["git", "diff", "--stat"], project_root)
    if rc != 0:
        return f"(git diff failed: {err.strip()})"
    return out.rstrip() or "(no tracked changes)"


def _has_staged_or_unstaged_changes(project_root: str) -> bool:
    """True when there is something to commit (staged, unstaged, or new)."""
    rc, out, _ = _run(["git", "status", "--porcelain"], project_root)
    if rc != 0:
        return False
    return bool(out.strip())


def _list_untracked(project_root: str) -> list[str]:
    rc, out, _ = _run(
        ["git", "ls-files", "--others", "--exclude-standard"], project_root
    )
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def _is_git_repo(project_root: str) -> bool:
    rc, _, _ = _run(["git", "rev-parse", "--git-dir"], project_root)
    return rc == 0


def commit(project_root: str, commit_argv: list[str]) -> int:
    """Run Rule 53 gate, then hand off to `git commit` if all clear.

    Returns the exit code of `git commit` on success, or a non-zero
    code on any gate failure (1 for missing git, 2 for no changes,
    3 for verify failure, 4 for no verify command configured).
    """
    project_root = os.path.abspath(project_root)

    if not _is_git_repo(project_root):
        print("❌ 当前项目不是 git 仓库（Rule 34 要求先初始化 git）")
        print("   运行 `git init` 初始化后再使用 `vibe commit`。")
        return 1

    if not _has_staged_or_unstaged_changes(project_root):
        print("❌ 没有可提交的改动（git status 干净）")
        return 2

    # Auto-stage everything so the diff shown is what is about to be
    # committed and so `git commit` has a non-empty index. The review
    # step below makes the blast radius visible before anything is
    # persisted to history.
    _run(["git", "add", "-A"], project_root)

    # 1. Review — show diff
    print("📋 提交前 Review (git diff --stat):")
    print(_git_diff_stat(project_root))
    untracked = _list_untracked(project_root)
    if untracked:
        print()
        print(f"   + {len(untracked)} 个未跟踪文件 (需 `git add` 后再 commit):")
        for path in untracked[:10]:
            print(f"     - {path}")
        if len(untracked) > 10:
            print(f"     ... 还有 {len(untracked) - 10} 个")
    print()

    # 2. Verify — run configured verify commands
    workflow, _ = ensure_workflow(project_root)
    verify_commands = configured_commands(workflow, "verify")
    if not verify_commands:
        print(
            "❌ 项目未配置 verify 命令（Rule 53 要求 commit 前必须跑 verify）。\n"
            "   在 .agents/workflow.json 的 commands.verify 中至少添加一条命令。\n"
            "   例子: {\"commands\": {\"verify\": [[\"pytest\", \"-x\"]]}}\n"
            "   临时绕过: `vibe commit --no-verify` (Rule 53 建议只在调试时使用)。"
        )
        return 4

    print(f"🔍 跑 {len(verify_commands)} 条 verify 命令 (Rule 53):")
    all_passed = True
    for idx, argv in enumerate(verify_commands, 1):
        print(f"   [{idx}/{len(verify_commands)}] {' '.join(argv)}")
        rc, out, err = _run(argv, project_root)
        if rc != 0:
            all_passed = False
            print(f"   ❌ 失败 (exit {rc})")
            if out.strip():
                print("   --- stdout ---")
                print(out.rstrip())
            if err.strip():
                print("   --- stderr ---")
                print(err.rstrip())
            break
        print(f"   ✅ 通过")
    print()

    if not all_passed:
        print("❌ Verify 失败 — 取消 commit (Rule 53)。")
        print("   修复失败后重跑 `vibe commit`；或临时绕过：`vibe commit --no-verify`")
        return 3

    # 3. Commit — hand off to git
    print("✅ Verify 全通过，转交 git commit")
    completed = subprocess.run(["git", "commit", *commit_argv], cwd=project_root)
    return completed.returncode


def run(argv: list[str]) -> int:
    """Entry point used by both the CLI and the vibe.py dispatcher.

    Manual argv parsing: argparse.REMAINDER swallows --no-verify into
    git_args, so we cannot rely on argparse for the flag.
    """
    no_verify = False
    if "--no-verify" in argv:
        no_verify = True
        argv = [a for a in argv if a != "--no-verify"]
    if not argv:
        print("Usage: vibe commit <project_root> [--no-verify] [git commit args...]")
        return 2
    project_root = argv[0]
    git_args = argv[1:]

    if no_verify:
        # Direct hand-off, no gate. Documented escape hatch.
        project_root = os.path.abspath(project_root)
        if not _is_git_repo(project_root):
            print("❌ 当前项目不是 git 仓库")
            return 1
        completed = subprocess.run(
            ["git", "commit", *git_args], cwd=project_root
        )
        return completed.returncode

    return commit(project_root, git_args)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
