#!/usr/bin/env python3
"""vibe commit — Rule 53 pre-commit verification gate.

Wraps `git commit` with three discipline steps that the agent is
otherwise likely to skip:

  1. Review — show the full diff so the Agent can inspect actual
     changes, not just file names and line counts. The Agent must
     review the diff content for unintended modifications, scope
     creep, or regressions before proceeding (Rule 53). If issues
     are found, the Agent must fix them before committing.
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


def _git_diff_full(project_root: str) -> str:
    """Return full `git diff` against HEAD so the Agent can review
    actual code changes, not just file names and line counts.

    Rule 53 requires the Agent to inspect diff content for
    unintended modifications, scope creep, or regressions.
    Showing only --stat defeats this purpose.
    """
    rc, out, err = _run(
        ["git", "diff", "HEAD"], project_root
    )
    if rc != 0:
        # No commits yet — diff against the empty tree
        rc, out, err = _run(["git", "diff"], project_root)
    if rc != 0:
        return f"(git diff failed: {err.strip()})"
    return out.rstrip() or "(no tracked changes)"


def _git_diff_stat(project_root: str) -> str:
    """Return `git diff --stat` summary for quick overview.

    Shown alongside the full diff so the Agent gets both the
    summary and the details.
    """
    rc, out, err = _run(
        ["git", "diff", "--stat", "HEAD"], project_root
    )
    if rc != 0:
        rc, out, err = _run(["git", "diff", "--stat"], project_root)
    if rc != 0:
        return f"(git diff failed: {err.strip()})"
    return out.rstrip() or "(no tracked changes)"


def _has_staged_changes(project_root: str) -> bool:
    """True when there is at least one staged change in the index.

    Used by commit() to decide whether to skip `git add -A` so the
    agent's explicit `git add <paths>` choices are respected (the
    one-commit-per-logical-unit workflow). When something is staged,
    `vibe commit` only commits what is staged; otherwise it falls back
    to the legacy `git add -A` behaviour.
    """
    rc, out, _ = _run(["git", "diff", "--cached", "--name-only"], project_root)
    if rc != 0:
        return False
    return bool(out.strip())


def _staged_files(project_root: str) -> list[str]:
    """Return list of file paths that are currently staged in the index.

    Used by commit() to auto-detect which files are about to be
    committed so the verify command can be scoped to only those
    files (the commit-scoped verify pattern) instead of running
    the full test suite.
    """
    rc, out, _ = _run(["git", "diff", "--cached", "--name-only"], project_root)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


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


def commit(
    project_root: str,
    commit_argv: list[str],
    staged_only: bool = False,
    paths: list[str] | None = None,
    full_verify: bool = False,
    reviewed: bool = False,
) -> int:
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

    # Stage selection logic (priority order):
    # 1. --paths <csv>: stage only those paths, then commit. Most
    #    explicit; useful when the agent knows exactly which files
    #    belong to this logical unit.
    # 2. --staged: do not auto-stage anything; commit only what is
    #    already staged. The agent pre-stages via `git add <paths>`.
    # 3. Auto: if anything is already staged, respect it (the agent
    #    is signalling granularity intent); otherwise `git add -A`
    #    as the legacy default for the simple single-commit case.
    if paths:
        # Reset any prior staging so the explicit paths list is the
        # sole thing in the index. Without this, prior `git add -A`
        # from a previous vibe commit would bleed into this one.
        _run(["git", "reset", "HEAD"], project_root)
        _run(["git", "add", "--"] + paths, project_root)
        print(f"ℹ️  --paths: 只 stage 了 {len(paths)} 个路径。")
    elif staged_only:
        # Honour whatever the agent already staged; do NOT auto-add.
        print("ℹ️  --staged: 只 commit 已 staged 改动，不自动 add。")
    else:
        staged = _has_staged_changes(project_root)
        if not staged:
            _run(["git", "add", "-A"], project_root)
        else:
            print("ℹ️  worktree 已有 staged 改动；只 commit 已 staged 内容（精细拆分模式）。")
            print("   如要 commit 全部 dirty 改动，先 `git reset HEAD` 撤回 staged，再用 `vibe commit`。")

    # 1. Review — show full diff + stat summary
    # Rule 53: Agent must inspect diff content for unintended
    # modifications, scope creep, or regressions. Showing only
    # --stat is insufficient — the Agent needs to see actual
    # code changes to catch problems.
    print("📋 提交前 Review — 检查 diff 内容 (Rule 53):")
    print("   ⚠️  审查以下改动：发现意外修改、范围蔓延、或回归问题必须修复后再 commit。")
    print()
    stat = _git_diff_stat(project_root)
    if stat and stat != "(no tracked changes)":
        print("📊 改动概览:")
        print(stat)
        # Commit granularity advisory: if too many files changed in
        # one commit, suggest splitting into logical units. This is
        # the most common failure mode when "vibe upgrade" or bulk
        # edits dump everything into a single commit — 112 files in
        # one "chore: vibe upgrade" commit makes rollback impossible.
        file_count = len([line for line in stat.splitlines() if line.strip() and "|" in line])
        if file_count > 20:
            print()
            print(f"⚠️  {file_count} 个文件变更 — 建议拆分为多个逻辑 commit (Rule 53):")
            print("   拆分方式: `git add <本逻辑单元涉及的文件> && vibe commit --staged -m '...'`")
            print("   或: `vibe commit --paths a.py,b.py -m '...'`")
            print("   好处: 回滚精确、review 清晰、每个 commit 对应一个意图")
            print("<!-- vibe:commit_granularity: large_diff -->")
        print()
    full_diff = _git_diff_full(project_root)
    if full_diff and full_diff != "(no tracked changes)":
        print("📝 完整 diff:")
        print(full_diff)
        print()
    # Rule 53 review declaration gate: Agent must confirm it
    # inspected the diff content. This is a structural forcing
    # function — the Agent must output a review summary before
    # the commit can proceed. Without this, the Agent sees the
    # diff but skips reading it (observed failure mode: 112 files
    # committed without review because "diff was shown but not
    # inspected").
    #
    # The --reviewed flag is the Agent's explicit declaration:
    # "I read the diff, here is what I found." Without it, the
    # commit is blocked at the review gate.
    print("<!-- vibe:commit_review: diff_shown -->")
    print("🔒 Review 声明门禁 (Rule 53):")
    print("   Agent 必须确认已逐文件审查 diff 内容。")
    print("   加 --reviewed 标志声明审查完成，否则 commit 被阻止。")
    print("   审查要点: 意外修改 / 范围蔓延 / 回归 / 空文件 / 配置泄露")
    print("<!-- vibe:commit_review_gate: pending -->")
    if not reviewed and not no_verify:
        print()
        print("🔒 Review 门禁 — diff 已展示，请审查后重新提交 (Rule 53)。")
        print("   这是强制两步操作：")
        print("     第 1 步: vibe commit（你现在在这步 — 看完 diff 后退出）")
        print("     第 2 步: vibe commit --reviewed（确认审查完成，跑 verify + 提交）")
        print("   审查要点: 意外修改 / 范围蔓延 / 回归 / 空文件 / 配置泄露")
        print("   如果发现问题: 先修复，再从第 1 步重新开始。")
        print("<!-- vibe:commit_review: blocked_pending_review -->")
        return 5
    untracked = _list_untracked(project_root)
    if untracked:
        print()
        print(f"   + {len(untracked)} 个未跟踪文件 (需 `git add` 后再 commit):")
        for path in untracked[:10]:
            print(f"     - {path}")
        if len(untracked) > 10:
            print(f"     ... 还有 {len(untracked) - 10} 个")
    print()

    # 2. Verify — select verify tier based on flags and config.
    #
    # Three tiers (fastest → slowest):
    #   verify_scope  — fast, scoped to changed files. Ideal for
    #     intermediate commits in a batch (8 commits × 30s = 4min
    #     instead of 8 × 5min = 40min).
    #   verify        — default full suite. Used when no scope
    #     commands are configured (backward-compatible).
    #   verify_full   — explicit full suite via --full-verify.
    #     Used for the final commit in a batch to confirm the
    #     complete integration. Falls back to verify if verify_full
    #     is not configured separately.
    #
    # Selection logic:
    #   --full-verify → verify_full (fallback verify)
    #   default       → verify_scope (fallback verify)
    workflow, _ = ensure_workflow(project_root)
    if full_verify:
        full_commands = configured_commands(workflow, "verify_full")
        fallback_commands = configured_commands(workflow, "verify")
        if full_commands:
            print(f"🔍 跑 {len(full_commands)} 条 verify_full 命令 (Rule 53, 全量验证):")
            commands_to_run = full_commands
        elif fallback_commands:
            print(f"🔍 跑 {len(fallback_commands)} 条 verify 命令 (Rule 53, 全量验证, 无独立 verify_full):")
            commands_to_run = fallback_commands
        else:
            print(
                "❌ 项目未配置 verify / verify_full 命令（Rule 53）。\n"
                "   在 .agents/workflow.json 的 commands.verify 中添加验证命令。\n"
                "   临时绕过: `vibe commit --no-verify`"
            )
            return 4
    else:
        scope_commands = configured_commands(workflow, "verify_scope")
        verify_commands = configured_commands(workflow, "verify")
        if scope_commands:
            print(f"🔍 跑 {len(scope_commands)} 条 verify_scope 命令 (Rule 53, scoped):")
            commands_to_run = scope_commands
        elif verify_commands:
            print(f"🔍 跑 {len(verify_commands)} 条 verify 命令 (Rule 53, full suite):")
            commands_to_run = verify_commands
        else:
            print(
                "❌ 项目未配置 verify 或 verify_scope 命令（Rule 53）。\n"
                "   在 .agents/workflow.json 的 commands.verify_scope 中添加快速验证命令，\n"
                "   或在 commands.verify 中添加完整验证命令。\n"
                "   例子: {\"commands\": {\"verify_scope\": [[\"pytest\", \"-x\", \"-k\", \"scope\"]]}}\n"
                "   临时绕过: `vibe commit --no-verify`"
            )
            return 4
    all_passed = True
    for idx, argv in enumerate(commands_to_run, 1):
        print(f"   [{idx}/{len(commands_to_run)}] {' '.join(argv)}")
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
        print("❌ Verify 失败 — 取消本次 commit (Rule 53)。")
        print("   本次 commit 的代码没有被写入 git history，可以安全修复后重跑。")
        print("   之前已经成功的 commit 不会被回滚——它们已经落地在 git log 里。")
        print("   修复失败后重跑 `vibe commit`；或临时绕过：`vibe commit --no-verify`")
        return 3

    # 3. Commit — hand off to git
    print("✅ Verify 全通过，转交 git commit")
    completed = subprocess.run(["git", "commit", *commit_argv], cwd=project_root)
    return completed.returncode


def run(argv: list[str]) -> int:
    """Entry point used by both the CLI and the vibe.py dispatcher.

    Manual argv parsing: argparse.REMAINDER swallows --no-verify into
    git_args, so we cannot rely on argparse for the flag. Same applies
    to --staged and --paths.
    """
    no_verify = False
    staged_only = False
    full_verify = False
    reviewed = False
    paths: list[str] = []
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-verify":
            no_verify = True
            i += 1
            continue
        if a == "--staged":
            staged_only = True
            i += 1
            continue
        if a == "--reviewed":
            reviewed = True
            i += 1
            continue
        if a == "--full-verify":
            full_verify = True
            i += 1
            continue
        if a == "--paths":
            # Collect subsequent comma-separated tokens until the next
            # flag (anything starting with "-" — both long "--staged"
            # and short "-m"). Path lists can be passed as one CSV
            # string or as repeated tokens; both work.
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                paths.extend(p for p in argv[i].split(",") if p)
                i += 1
            continue
        cleaned.append(a)
        i += 1
    argv = cleaned
    if not argv:
        print("Usage: vibe commit <project_root> [--staged | --paths p1,p2] "
              "[--no-verify] [--full-verify] [--reviewed] [git commit args...]")
        return 2
    project_root = argv[0]
    git_args = argv[1:]

    if no_verify:
        # Direct hand-off, no gate. Documented escape hatch. Stage
        # selection is also skipped: the user opted out of the full
        # vibe commit flow.
        project_root = os.path.abspath(project_root)
        if not _is_git_repo(project_root):
            print("❌ 当前项目不是 git 仓库")
            return 1
        if paths:
            _run(["git", "reset", "HEAD"], project_root)
            _run(["git", "add", "--"] + paths, project_root)
        completed = subprocess.run(
            ["git", "commit", *git_args], cwd=project_root
        )
        return completed.returncode

    return commit(project_root, git_args, staged_only=staged_only, paths=paths, full_verify=full_verify, reviewed=reviewed)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
