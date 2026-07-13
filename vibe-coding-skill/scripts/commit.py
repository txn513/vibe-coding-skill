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
import re
import subprocess
import sys
import code_pattern_gate

from workflow_state import (
    SCHEMA_VERSION,
    configured_commands,
    ensure_workflow,
)

# Shared review-summary template. Surfaced via:
#   - `vibe commit --help` (argparse epilog, see scripts/vibe.py commit
#     subparser)
#   - line-ref hard-gate failure message in this module
# Centralised so the dispatcher and the gate stay in sync.
REVIEW_SUMMARY_TEMPLATE = """--review-summary 模板 (per-file + 行号 + 业务结论三件套):
  app.py: L25-L30 fast-path 加 closed 检查, 无锁开销; 业务逻辑等价
  utils.py: 新增 `process_helper` 包装, 调用点 grep 已确认
  test_x.py: L100-L120 新增 fixture, 不影响旧测试

接受的行号信号: L25 / line 25 / :25 / `code_fragment`
无行号 → exit 9 (硬门禁, --quick 或 --no-verify 可绕过)

例外: .agents/evidence/ / .agents/plans/ / .agents/reviews/ /
      .agents/changelogs/ / .agents/activity.md 等 vibe 自动生成
      文件不需要行号引用 (Rule 55 排除自动生成文件, 2026-07-10)。

Archive 子目录 (line range 易漏, 2026-07-10 retro):
  .agents/archive/<spec>/<timestamp>/evidence/<file>    ← 需 line range
  .agents/archive/<spec>/<timestamp>/reviews/<file>     ← 需 line range
  .agents/archive/<spec>/<timestamp>/verify/<file>      ← 需 line range

  ❌ "归档版本" 不带 line range → R53 missing_line_refs 拦下
  ✅ archive/<spec>/20260710-133016/evidence/verify.md: line 1-33 旧 verify 快照
  ✅ basename 也可: verify.md: L1-L33 旧 verify 快照 (path entry 包含 basename)

  根因: archive 路径深 + 时间戳命名, agent mental check 易跳过行号;
  gate 不会因为路径深就豁免 line-ref 要求 (auto-generated 白名单不含 archive)。

Multi-file 写法 (推荐换行分隔, 2026-07-11):
  splittersplit 用 [\\n;]+ 切分; 优先换行, 描述里出现 ; 不影响 splitter 边界.

  ✅ 多文件换行 (推荐, 抗 ; 干扰):
    --review-summary 'app.py: L25-L30 检查加 closed
    utils.py: L42-L55 加 helper 包装
    test_x.py: L100-L120 新增 fixture'

  ✅ 单行 ; 分隔 (仍兼容):
    --review-summary 'app.py: L25-L30 检查; utils.py: 加 helper; test_x.py: 加 fixture'

  ❌ 描述内嵌 ; 跟分隔符冲突 (retro 撞过, 2026-07-08):
    --review-summary 'app.py: L789 area; L1130 area; utils.py: 加 helper'
                            ^^^^^^^^ splitter 切开, 后续 part 缺 : 触发 missing_line_refs

  默认行为: 换行最稳, 描述里出现 ; 时也用换行更安全."""



# Path prefixes / exact paths for files that vibe generates automatically
# and that do NOT require line-ref citations in review-summary. The line-ref
# gate exists to prevent agents from rubber-stamping their own code without
# reading the diff; auto-generated files are written by scripts and have no
# human-readable "lines" worth citing. Forcing line refs on them is
# form-pass overhead that does not improve review quality.
#
# Whitelist is intentionally explicit (not glob) so an agent cannot bypass
# the gate by renaming an auto-generated file with an off-list prefix.
AUTO_GENERATED_PATH_PREFIXES = (
    ".agents/evidence/",
    ".agents/plans/",
    ".agents/reviews/",
    ".agents/changelogs/",
)
AUTO_GENERATED_PATH_EXACT = {
    ".agents/activity.md",
}


def _is_auto_generated_path(filepath: str) -> bool:
    """True if filepath is a vibe-managed artifact that does not need
    a line-ref citation in review-summary."""
    if filepath in AUTO_GENERATED_PATH_EXACT:
        return True
    return any(filepath.startswith(p) for p in AUTO_GENERATED_PATH_PREFIXES)

# Governance file extensions that do not need per-file line refs.
# Used by commit gate to skip line-ref requirement for pure-docs commits.
GOVERNANCE_FILE_EXTS = frozenset([
    ".md", ".txt", ".json", ".yml", ".yaml", ".toml",
    ".gitignore", ".gitattributes",
])


def _is_governance_file(filepath: str) -> bool:
    """True if filepath is a governance/docs/config file without logic.

    When ALL changed files in a commit are governance files, the commit
    gate skips per-file line-ref requirement (missing_line_refs gate).
    This eliminates the need for --quick on pure governance commits
    (e.g., retro write, rule update, AGENTS.md housekeeping).

    The missing_file_review gate (exit 8) still requires every file
    to be mentioned in review-summary; only line-ref gate (exit 9)
    is relaxed for governance-only commits.
    """
    # Exact filenames that are always governance
    if filepath in {".agents/activity.md", "AGENTS.md", "README.md", "VERSION"}:
        return True
    # Extension-based check
    ext = os.path.splitext(filepath)[1].lower()
    if ext in GOVERNANCE_FILE_EXTS:
        return True
    # Directory-based: anything under .agents/rules/, .agents/retros/, docs/
    if filepath.startswith((".agents/rules/", ".agents/retros/", ".agents/notes/", "docs/")):
        return True
    return False



# 2026-07-12b: step 2 (vibe commit --reviewed) accepts a marker that
# was written within this many seconds. After the window, the agent
# must re-run step 1 — protects against crashes / Ctrl-C / mid-flow
# distraction leaving a stale marker.
REVIEW_MARKER_TTL_SECONDS = 600


def _review_marker_path(project_root: str) -> str:
    """Path to the marker file that records "step 1 (diff shown) was run".

    Forces the two-step commit pattern by requiring --reviewed to come
    after a prior vibe commit that showed the diff. The marker is removed
    after a successful --reviewed commit, so the next commit must repeat
    step 1.
    """
    return os.path.join(project_root, ".agents", ".vibe-review-pending")


def _write_review_marker(project_root: str) -> None:
    """Write the marker after step 1 (vibe commit shows diff).

    Also ensures `.gitignore` (at the project root) ignores the marker,
    so `git add -A` during commit does not pick it up. Idempotent.

    2026-07-12b: marker now carries `created_at` (timestamp) and
    `project_root` (abs path) — step 2 enforces a TTL window so
    agents that step 1 → fail → fix → step 2 within 10 minutes don't
    trip the "step 1 skipped" gate. `project_root` survives cross-project
    marker confusion (agent switches mid-flow).
    """
    import json as _json
    import time as _time
    path = _review_marker_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "step1": "diff shown, ready for step2 (vibe commit --reviewed)",
        "created_at": _time.time(),
        "project_root": os.path.realpath(project_root),
    }
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_json.dumps(payload, ensure_ascii=False))
    # Ensure .gitignore covers the marker so `git add -A` doesn't include it.
    gitignore = os.path.join(project_root, ".gitignore")
    marker_relpath = ".agents/.vibe-review-pending"
    existing = ""
    if os.path.exists(gitignore):
        with open(gitignore, "r", encoding="utf-8") as gi:
            existing = gi.read()
    if marker_relpath not in existing.splitlines():
        with open(gitignore, "a", encoding="utf-8") as gi:
            if existing and not existing.endswith("\n"):
                gi.write("\n")
            gi.write(f"{marker_relpath}\n")


def _read_and_clear_review_marker(project_root: str) -> str | None:
    """Read and remove the marker. Returns its content or None.

    2026-07-12b (TTL window + cross-project guard): marker payload is
    JSON with created_at + project_root. Step 2 considers the marker
    valid only when:
      - created_at within REVIEW_MARKER_TTL_SECONDS (default 600s = 10min)
      - project_root matches abs path of current project (prevents
        cross-project marker confusion when agent switches mid-flow)
      - JSON parseable (older plain-text markers fall through to
        stale-rebuild path; do NOT crash)
    Returns the JSON string (for the `<!-- ... -->` marker in step 2
    output) when accepted, None otherwise.
    """
    import json as _json
    import time as _time
    path = _review_marker_path(project_root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
        payload = _json.loads(raw)
    except (ValueError, OSError):
        # Old-format marker (plain text written before the TTL upgrade)
        # — accept it as immediate-use. Path is project-local
        # (`.agents/.vibe-review-pending`) so cross-project confusion
        # is impossible: project A's marker never appears under B's root.
        # Returning the raw bytes is enough for the gate to proceed.
        os.remove(path)
        return raw
    # Cross-project guard (only when JSON carries a project_root)
    marker_proj = payload.get("project_root", "")
    if marker_proj and marker_proj != os.path.realpath(project_root):
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    # TTL check
    created_at = payload.get("created_at", 0)
    age = _time.time() - float(created_at)
    if age > REVIEW_MARKER_TTL_SECONDS:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    os.remove(path)
    return content


def _print_evidence_grep(project_root: str, diff_text: str) -> None:
    """Highlight sensitive patterns in the diff for Agent attention.

    Grep for patterns that commonly hide data-semantic bugs:
    emit/write/INSERT/DELETE/UPDATE that change data shapes.
    This is advisory (not blocking), just highlights risk areas.
    """
    if not diff_text or diff_text == "(no tracked changes)":
        return
    import re
    # Patterns that change data shape — these are the most common
    # hiding spots for "test passes but data semantics are wrong" bugs
    patterns = {
        "emit/emit": "事件发射（字段名/值是否跟 schema 一致？）",
        "write": "写入调用（写入的数据结构是否跟下游期望一致？）",
        "INSERT": "SQL INSERT（列名/值是否跟表定义一致？）",
        "UPDATE": "SQL UPDATE（更新字段是否正确？是否遗漏了关联字段？）",
        "DELETE": "SQL DELETE / 删除操作（是否有级联影响？）",
        "fetch": "POST 请求（请求体字段是否跟 API 接口一致？）",
        "json.dumps": "JSON 序列化（键名是否跟消费端期望一致？）",
    }
    hits = {}
    for pattern, hint in patterns.items():
        matches = re.findall(re.escape(pattern), diff_text, re.IGNORECASE)
        if matches:
            hits[pattern] = (len(matches), hint)
    if hits:
        print("🔍 数据语义高亮 (Rule 53): diff 中发现以下敏感模式：")
        for pattern, (count, hint) in hits.items():
            print(f"   - {pattern}: {count} 处 → {hint}")
        print()


def _run(argv: list[str], cwd: str) -> tuple[int, str, str]:
    """Run argv in cwd; return (exit_code, stdout, stderr)."""
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _extract_changed_files_from_stat(stat: str) -> list[str]:
    """Extract file paths from git diff --stat output.

    Git truncates long paths in --stat output (default terminal-width,
    typically 80 columns), inserting a leading `...` or `.../`. The
    truncated form breaks basename matching in the Rule 53 review gate
    because `os.path.basename('...path/to/file.md')` returns the literal
    string with `...` still attached — the review-summary entry won't
    match and the gate reports false-missing files.

    2026-07-12b retro: 27 untracked reports (paths >60 chars) tripped
    this gate and forced the agent to use --no-verify.

    Detection: any line whose first column starts with `...` is a
    truncation marker. In that case the function returns the raw
    `git diff --numstat` form (which never truncates) so the gate can
    match real full paths against the review-summary entries.

    Short-path commits keep the existing basename-friendly behaviour.
    """
    files = []
    truncated = False
    for line in stat.splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.rsplit('|', 1)
        if len(parts) == 2:
            filepath = parts[0].strip()
            if filepath:
                files.append(filepath)
                # Truncated paths: leading `...` or `.../` after stripping.
                # os.path.basename on e.g. "...reports/foo.md" still
                # returns "...reports/foo.md" because git inlines parent
                # directories into the basename.
                first_token = filepath.split(" ", 1)[0]
                if first_token.startswith("..."):
                    truncated = True
    if truncated:
        return []  # signal to caller: re-run via _numstat path
    return files


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
        # No commits yet — root-commit case. Fall back to diff of
        # the index so staged content is visible to review (Rule 53)
        # and to the Rule 64 async-session gate.
        rc, out, err = _run(["git", "diff", "--cached"], project_root)
    if rc != 0:
        # Last resort: working tree diff (will miss staged content).
        rc, out, err = _run(["git", "diff"], project_root)
    if rc != 0:
        return f"(git diff failed: {err.strip()})"
    return out.rstrip() or "(no tracked changes)"


def _git_diff_stat(project_root: str, staged_only: bool = False) -> str:
    """Return `git diff --stat` summary for quick overview.

    staged_only=True returns `git diff --stat --cached` — the
    commit-scoped view, what would actually land in the next
    commit. Used by the R53 missing_file_review gate so the
    review-summary only has to mention files in THIS commit, not
    every dirty file in the working tree (otherwise
    "vibe commit --paths" / "--staged" granularity flow breaks:
    the gate would force the agent to list untracked dirty
    files that are NOT part of this commit).

    staged_only=False returns `git diff --stat HEAD` — the
    working-tree-wide view, useful as a "what's dirty" overview
    before the commit lands.
    """
    if staged_only:
        rc, out, err = _run(
            ["git", "diff", "--stat", "--cached"], project_root
        )
        if rc != 0:
            rc, out, err = _run(["git", "diff", "--stat"], project_root)
    else:
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


def _all_changed_are_governance(project_root: str, changed_files: list[str]) -> bool:
    """True when every changed file is a governance file.

    Used by commit gate to decide whether to skip the per-file
    line-ref requirement (missing_line_refs gate). Production code
    commits (.py/.sh/.js etc.) still get full gate treatment.
    """
    if not changed_files:
        return False
    return all(_is_governance_file(f) for f in changed_files)



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


def _print_expected_file_list(project_root: str) -> None:
    """Pre-print the file list that the next commit will include.

    Acts as a prevention signal for R53 missing_file_review gate: the
    existing gate catches omission AFTER commit (exit 8 retry). Printing
    the list before review-summary writing lets the agent cover all files
    in one shot. Only emits when there ARE untracked files about to be
    auto-staged; otherwise stays silent (no noise for the common case).
    2026-07-11 candidate 1 (commit expected-file-list pre-print).
    """
    untracked = _list_untracked(project_root)
    if not untracked:
        return
    staged = _staged_files(project_root)
    print()
    print("📋 本次 commit 预期文件清单 (Step 1 锚点 — 写 review-summary 时覆盖):")
    if staged:
        print(f"   已 stage ({len(staged)}):")
        for path in staged[:15]:
            print(f"     - {path}")
        if len(staged) > 15:
            print(f"     ... 还有 {len(staged) - 15} 个")
    print(f"   待自动 stage (untracked, {len(untracked)}):")
    for path in untracked[:15]:
        print(f"     - {path}")
    if len(untracked) > 15:
        print(f"     ... 还有 {len(untracked) - 15} 个")
    print("   (Review 时确认无意外文件; 用 `vibe commit --paths <csv>` 可精细拆分)")
    print("<!-- vibe:commit_expected_files: staged="
          f"{len(staged)} untracked={len(untracked)} -->")


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
    no_verify: bool = False,
    quick: bool = False,
    review_summary: str = "",
    no_async_gate: bool = False,
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

    # Rule 66: Session-state check at mutating command entry.
    # Advisory only — does not block commit, but ensures the agent
    # sees the hint even when it skips `vibe next`.
    from project_status import _check_session_state
    _check_session_state(project_root, threshold_minutes=5)

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
    # Rule 53 review declaration gate + evidence grep.
    # After showing the full diff, grep for sensitive patterns
    # that commonly hide "data semantic mismatch" bugs:
    # emit/write/INSERT/DELETE/fetch POST that change data shapes.
    # This is the lowest-cost, highest-value enhancement — it
    # doesn't block the commit, just highlights risk areas.
    _print_evidence_grep(project_root, full_diff)
    # Pre-print expected file list (Rule 53 prevention layer):
    # when this commit will auto-include untracked files, surface
    # them BEFORE the review gate so the agent's review-summary
    # covers all of them in one shot. Without this, the existing
    # "missing_file_review" gate (exit 8) only catches the omission
    # AFTER commit lands, costing the agent a full retry.
    # 2026-07-11 candidate 1.
    if not paths and not staged_only:
        _print_expected_file_list(project_root)
    # Rule 64 advisory runs at diff_shown so the agent sees the
    # anti-pattern alongside the diff. Position rationale: if the
    # advisory only fires after the review gate, the agent is already
    # writing --review-summary and has nothing concrete to cite.
    # Surfacing it here lets the agent either (a) write the
    # anti-pattern into the review-summary as an observation, or
    # (b) fix the code and re-stage before --reviewed.
    if not no_async_gate:
        hints = code_pattern_gate.scan_changed_python_files(
            project_root, diff_text=full_diff,
        )
        code_pattern_gate.print_code_pattern_hints(hints, suppress=no_async_gate)
    print("<!-- vibe:commit_review: diff_shown -->")
    # Step 2 enforcement: --reviewed must come after a prior step 1
    # (vibe commit without --reviewed) that wrote the marker.
    if reviewed and not quick and not no_verify:
        marker_content = _read_and_clear_review_marker(project_root)
        if marker_content is None:
            print("🔒 Review 门禁升级 — 检测到跳过第 1 步 (Rule 53):")
            print("   `--reviewed` 需要在一次 `vibe commit`（不传 --reviewed）之后执行。")
            print("   上一次 `vibe commit` 在哪个项目跑的？是否跟当前项目不一致？")
            print("   如果确实要先看 diff: 先跑 `vibe commit`（不带 --reviewed），再跑 `vibe commit --reviewed`。")
            print("   如果要跳过 review gate: 用 `--quick`（docs-only）或 `--no-verify`（需说明理由）。")
            print("<!-- vibe:commit_review_gate: skipped_step1 -->")
            return 6
        else:
            print("<!-- vibe:commit_review_gate: step1_verified -->")
    # Step 2 enhancement: require an actual review summary, not just
    # the bare `--reviewed` flag. Without this, the Agent could mark
    # step 1 as reviewed without ever reading the diff. An empty
    # summary is rejected (exit 7) so the gate cannot be rubber-stamped.
    if reviewed and not quick and not no_verify:
        summary = review_summary.strip()
        if not summary:
            print("🔒 Review 门禁升级 — 缺 review summary (Rule 53):")
            print("   `--reviewed` 必须配 `--review-summary '<text>'`，描述你读 diff 时实际发现了什么。")
            print("   例: --review-summary '确认只改了 commit.py + tests；无意外文件'")
            print("   如果只是文档/chore 改动: 用 `--quick` 跳过 review gate 但保留 verify。")
            print("   如果必须跳过 review + verify: 用 `--no-verify`（会同时跳过 verify，需在 retro 中说明理由）。")
            print("<!-- vibe:commit_review_gate: missing_summary -->")
            return 7
        snippet = summary[:60] + ("..." if len(summary) > 60 else "")
        print(f"<!-- vibe:commit_review_summary: {snippet} -->")

        # Per-file review-summary validation (Rule 53 hard gate):
        # The review-summary must reference every changed file from the
        # diff. Without this, the Agent can write a generic summary
        # like "confirmed no issues" without actually reading each
        # file diff. This is the most common failure mode observed
        # across multiple projects.
        stat_text = _git_diff_stat(project_root, staged_only=True)
        if stat_text and stat_text != "(no tracked changes)":
            changed_files = _extract_changed_files_from_stat(stat_text)
            if changed_files == []:
                # 2026-07-12b: --stat truncated at least one path, fall
                # back to --numstat which never truncates. We re-derive
                # numstat and parse it ad-hoc (3-column format: add	del	path).
                numstat_rc, numstat_out, _ = _run(
                    ["git", "diff", "--numstat", "--cached"], project_root
                )
                if numstat_rc == 0:
                    changed_files = []
                    for nl in numstat_out.splitlines():
                        cols = nl.split("\t")
                        if len(cols) >= 3 and cols[2].strip():
                            changed_files.append(cols[2].strip())
            missing_files = []
            for filepath in changed_files:
                basename = os.path.basename(filepath)
                if filepath not in summary and basename not in summary:
                    missing_files.append(filepath)
            if missing_files:
                print()
                print("\U0001f512 Review \u95e8\u7981\u5347\u7ea7 \u2014 review-summary \u7f3a\u5c11\u6587\u4ef6\u5ba1\u67e5\u7ed3\u8bba (Rule 53):")
                print(f"   \u4ee5\u4e0b {len(missing_files)} \u4e2a\u6587\u4ef6 diff \u4e2d\u4f46\u672a review-summary \u4e2d\u63d0\u53ca:")
                for mf in missing_files[:10]:
                    print(f"     - {mf}")
                if len(missing_files) > 10:
                    print(f"     ... \u8fd8\u6709 {len(missing_files) - 10} \u4e2a")
                print()
                print("   review-summary \u5fc5\u987b\u5305\u542b\u5bf9\u6bcf\u4e2a\u53d8\u66f4\u6587\u4ef6\u7684\u5ba1\u67e5\u7ed3\u8bba\u3002")
                print("   \u683c\u5f0f: <\u6587\u4ef6\u540d>: <\u5ba1\u67e5\u7ed3\u8bba>; <\u6587\u4ef6\u540d>: <\u5ba1\u67e5\u7ed3\u8bba>")
                # Example with backtick for readability
                print("   \u4f8b: app.py: \u52203\u884c+\u52a02\u884c, \u8bed\u4e49\u7b49\u4ef7; utils.py: \u65b0\u589ehelper, \u65e0\u526f\u4f5c\u7528")
                print("<!-- vibe:commit_review_gate: missing_file_review -->")
                # R53 active inspection reminder (2026-07-13)
                print()
                print("💡 拦截提醒 — 你被拦了，但门禁只检查格式")
                print("   请确认你真的重读了 diff 内容，不是只补文件名引用。")
                print("   review-summary 必须包含对 diff 的实际观察（如行号、代码片段），")
                print("   不能只是列出文件名。")
                print("<!-- vibe:commit_review_gate: active_inspection_advisory -->")
                return 8

        # Per-file-summary 行号引用 hard gate (Rule 53 + Rule 55)
        # 提案: 2026-07-08-review-summary-must-cite-diff (方案 B, 强制)
        # 上面的 hard gate 只检查"每个变更文件被提及"。但 Agent 可以
        # 在 review-summary 里写"+12 行 — 加了 helper"这类写代码时的
        # 记忆性描述, 而不是真正读 diff 后的观察。本 hard gate 检测
        # 每条文件结论是否含至少一个行号或代码片段信号, 防止"看起来
        # 审查了, 实际只是凭记忆写"。Bypass: --quick (整段跳过 review)
        # 或 --no-verify (整段跳过), 与现有 per-file gate 一致。
        line_ref_pattern = re.compile(
            r"(?:L[0-9]+|line\s+[0-9]+|:[0-9]+|`[^`]+`)", re.IGNORECASE
        )
        # 2026-07-08: accept either newline OR ";" as file-entry separator.
        # The original ";" separator collided with descriptions that contain
        # ";" (eg "L789 area; L1130 area"), causing false missing-line-ref
        # hits when the post-split tail lacked a colon. Newline is preferred
        # because review-summary templates now routinely emit multi-line
        # forms, but ";" remains as a compatibility fallback so existing
        # agent output still parses.
        file_parts = [
            part.strip()
            for part in re.split(r"[\n;]+", summary)
            if part.strip()
        ]
        # 2026-07-08g: substantive-review soft advisory.
        # Lance retro: passing line-ref gate with content like
        # "app.py: L25 重命名变量，语义等价"
        # still means "I typed L25 but did not actually verify each call-site
        # keeps compiling". Pure placeholder language satisfies the form
        # gate but evades the substance. As an advisory (NOT a block), we
        # flag conclusions that lean on these soft claims so the agent
        # gets a second-look signal before commit lands. The commit
        # proceeds regardless to avoid the gate becoming a ritual
        # checkbox (同样的 R53 形式合规倒转问题).
        soft_claim_pattern = re.compile(
            r"(语义等价|无副作用|无回归|类似"
            r"|no\s+side\s+effects?|no\s+regression|equivalent|no-op"
            r"|safe|trivial|minor|cleanup|polish|refactor\s+only|\bnothing\s+changed\b"
            r"|难看出区别|差不多|几乎一样)",
            re.IGNORECASE,
        )
        soft_claim_parts = [
            part for part in file_parts
            if ":" in part and soft_claim_pattern.search(
                part.partition(":")[2]
            )
        ]
        if soft_claim_parts:
            print()
            print("⚠️  Substantive-review advisory (不阻塞, Rule 53 补强):")
            print(f"   以下 {len(soft_claim_parts)} 个 review-summary 出现柔性结论词（如")
            print("   “语义等价”/“无副作用”/“无回归”/“equivalent”/...")
            print("   。这些词正常使用场景也可能是 placeholder —")
            print("   建议重新看一遍 diff 后补上 call-site 验证、表面探索")
            print("   检查等具体证据。")
            for p in soft_claim_parts[:5]:
                print(f"     - {p[:80]}{'...' if len(p) > 80 else ''}")
            if len(soft_claim_parts) > 5:
                print(f"     ... 还有 {len(soft_claim_parts) - 5} 个")
            print()
            print("   补强例: app.py: L25 重命名 handle 变量，你可以述")
            print("                “call-site grep 验证无未引用老 handle”")
            print("   Bypass: 指定 --quick 跳过整个 review gate (保留 verify)")
            print("<!-- vibe:commit_review_gate: soft_claims -->")
        no_line_ref_parts = []
        for part in file_parts:
            # 跳过纯文件名前缀 (eg "app.py:" 无结论部分) — 这些在 missing
            # file gate 已经处理过了; 这里只关心有结论描述的部分。
            if ":" not in part:
                continue
            # 提取 filepath 和 ":" 后面的结论文字
            filepath, _, conclusion = part.partition(":")
            filepath = filepath.strip()
            # Rule 55 exclusion (2026-07-10): vibe 自动生成文件
            # (evidence/plans/reviews/changelogs/activity.md) 没有"行号"
            # 概念, 跳过 line-ref 检查。这些文件由 vibe scripts 写入,
            # agent 不需要"审查行号", 写结论就行 (eg "重新生成 plan,
            # digest 已更新")。missing_file gate 仍然要求每个文件被提到。
            if _is_auto_generated_path(filepath):
                continue
            if not line_ref_pattern.search(conclusion):
                no_line_ref_parts.append(part)
        # Governance-only commit: skip per-file line-ref requirement
        # (2026-07-13: candidate 2, R-Lighter-Governance-Gate).
        # When all changed files are governance/docs/config, require only
        # that every file is mentioned in review-summary (missing_file
        # gate above), not per-file line refs. This eliminates --quick
        # friction for retro write, rule update, AGENTS.md housekeeping.
        # Production code commits (.py/.sh etc.) still get full gate.
        if _all_changed_are_governance(project_root, changed_files):
            print()
            print("ℹ️  Governance-only commit: 跳过 per-file 行号引用要求 (Rule 53)")
            print("   所有变更文件均为治理类文档 (.md/.txt/.json/.yml等),")
            print("   review-summary 已覆盖全部文件即可, 不要求行号引用。")
            print("<!-- vibe:commit_review_gate: governance_lighter_path -->")
        elif no_line_ref_parts:
            print()
            print("🔒 Review 门禁升级 — review-summary 缺行号引用 (Rule 53 + Rule 55):")
            print(f"   以下 {len(no_line_ref_parts)} 个文件结论缺少行号/L标识/代码片段引用:")
            for p in no_line_ref_parts[:5]:
                print(f"     - {p[:80]}{'...' if len(p) > 80 else ''}")
            if len(no_line_ref_parts) > 5:
                print(f"     ... 还有 {len(no_line_ref_parts) - 5} 个")
            print()
            print("   行号引用格式: L<行号> / line <行号> / :<行号>")
            print("   代码片段格式: ` (反引号) 包住任意 identifier 或代码片段")
            print("   例: app.py: L25 fast-path 增加 closed 检查, 无锁开销")
            print("        utils.py: 新增 `process_helper` 包装, 调用点 grep 已确认")
            print()
            print("   Bypass: --quick (跳过整个 review gate, 保留 verify) 或")
            print("           --no-verify (跳过 review + verify)")
            print("<!-- vibe:commit_review_gate: missing_line_refs -->")
            # R53 active inspection reminder (2026-07-13)
            print()
            print("💡 拦截提醒 — 你被拦了，但门禁只检查行号引用格式")
            print("   请确认你真的重读了 diff 内容，不是只补行号/反引号。")
            print("   review-summary 必须包含基于 diff 观察的业务结论，")
            print("   不能只是形式合规（如 'L25 重命名，语义等价' 但没有真的看每个调用点）")
            print("<!-- vibe:commit_review_gate: active_inspection_advisory -->")
            return 9

    print("🔒 Review 声明门禁 (Rule 53):")
    print("   Agent 必须确认已逐文件审查 diff 内容。")
    print("   加 --reviewed 标志声明审查完成，否则 commit 被阻止。")
    print("   审查要点: 意外修改 / 范围蔓延 / 回归 / 空文件 / 配置泄露 / 数据语义错位")
    print("<!-- vibe:commit_review_gate: pending -->")
    if not reviewed and not quick and not no_verify:
        print()
        print("🔒 Review 门禁 — diff 已展示，请审查后重新提交 (Rule 53)。")
        print("   这是强制两步操作：")
        print("     第 1 步: vibe commit（你现在在这步 — 看完 diff 后退出）")
        print("     第 2 步: vibe commit --reviewed（确认审查完成，跑 verify + 提交）")
        print("   审查要点: 意外修改 / 范围蔓延 / 回归 / 空文件 / 配置泄露")
        print("   如果发现问题: 先修复，再从第 1 步重新开始。")
        # Write the step-1 marker so a subsequent --reviewed can verify step 1 happened.
        _write_review_marker(project_root)
        print("<!-- vibe:commit_review: marker_written -->")
        print("<!-- vibe:commit_review: blocked_pending_review -->")
        return 5
    print()

    # 2. Verify — select verify tier based on flags and config.
    # Note: Rule 64 advisory already ran above at diff_shown, so the
    # agent has had a chance to fix or acknowledge the anti-pattern
    # before this point. We do not re-run the scan here.
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
    # Wrap verify in try/except to catch unexpected exceptions
    # (e.g. regex bugs in verify commands) and fail-open with warning.
    verify_exception = None
    try:
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
    except re.error as e:
        # Regex bug in verify — fail-open with warning
        print(f"⚠️  verify 阶段 regex 解析失败，自动 fail-open (Rule 53):")
        print(f"   {type(e).__name__}: {e}")
        print(f"   请检查 verify 命令中的正则表达式。")
        print()
        all_passed = True
        verify_exception = e
    except Exception as e:
        # Unknown exception — fail-open with warning
        print(f"⚠️  verify 阶段异常，自动 fail-open (Rule 53):")
        print(f"   {type(e).__name__}: {e}")
        print(f"   请检查 verify 命令配置。")
        print()
        all_passed = True
        verify_exception = e

    if not all_passed:
        print("❌ Verify 失败 — 取消本次 commit (Rule 53)。")
        print("   本次 commit 的代码没有被写入 git history，可以安全修复后重跑。")
        print("   之前已经成功的 commit 不会被回滚——它们已经落地在 git log 里。")
        print("   修复失败后重跑 `vibe commit`；或临时绕过：`vibe commit --no-verify`")
        return 3

    # 2.5 Optional call-site check (Rule 62)
    # If the project has configured `commands.call_site_check` in
    # workflow.json, run it after verify but before commit. This lets
    # projects enforce "all call sites of modified symbols have been
    # adapted" as a gate — without forcing every project to configure it.
    call_site_commands = configured_commands(workflow, "call_site_check")
    if call_site_commands and not no_verify:
        print(f"🔍 跑 {len(call_site_commands)} 条 call_site_check 命令 (Rule 62, 调用点覆盖检查):")
        cs_passed = True
        for idx, argv in enumerate(call_site_commands, 1):
            print(f"   [{idx}/{len(call_site_commands)}] {' '.join(argv)}")
            rc, out, err = _run(argv, project_root)
            if rc != 0:
                cs_passed = False
                print(f"   ❌ 调用点检查失败 (exit {rc})")
                if out.strip():
                    print("   --- stdout ---")
                    print(out.rstrip())
                if err.strip():
                    print("   --- stderr ---")
                    print(err.rstrip())
                break
            print(f"   ✅ 调用点覆盖通过")
        if not cs_passed:
            print("❌ Call-site check 失败 — 取消本次 commit (Rule 62)。")
            print("   说明: verify 测试通过，但有调用点未被覆盖。")
            print("   修复: grep 受影响符号的全项目调用点，确保每个都已适配。")
            print("   临时绕过: `vibe commit --no-verify`")
            return 8
        print()

    # 3. Commit — hand off to git, with Rule 53 trailer
    # Adding a git trailer so doctor can detect commits that bypassed
    # vibe commit (raw `git commit` won't have this trailer).
    print("✅ Verify 全通过" + (" + 调用点覆盖通过" if call_site_commands else "") + "，转交 git commit")
    trailer_key = "quick" if quick else "yes"
    trailer_argv = ["git", "commit", *commit_argv, "--trailer", f"Vibe-Commit={trailer_key}"]
    if verify_exception:
        trailer_argv.extend(["--trailer", f"Verify-Crash={type(verify_exception).__name__}"])
    if reviewed and not quick and not no_verify and review_summary.strip():
        trailer_argv.extend(["--trailer", f"Review-Summary={review_summary.strip()}"])
    completed = subprocess.run(trailer_argv, cwd=project_root)
    return completed.returncode



def _audit_paths_logical_unit(paths):
    """2026-07-10 advisory #5: commit --paths 含多个独立逻辑单元文件时 WARN.

    motive: Rule 53 要求"每批改动应该是一个逻辑单元", 但 --paths
    接受任意路径列表, agent 容易把 spec fix + 无关 candidate 文档
    混在同一 commit。

    识别规则: 路径含 ≥2 个 `.agents/specs/<spec>.md` 或 ≥2 个
    `.agents/skill-upgrade-candidate*.md` 文件 → WARN。混合 spec +
    candidate 也 WARN。
    """
    import re as _re
    spec_re = _re.compile(r"\.agents/specs/[^/]+\.md$")
    cand_re = _re.compile(r"\.agents/skill-upgrade-candidate[^/]*\.md$")
    specs = [p for p in paths if spec_re.search(p)]
    cands = [p for p in paths if cand_re.search(p)]
    warnings = []
    if len(specs) >= 2:
        warnings.append(
            f"--paths 含 {len(specs)} 个 spec 文件: 这是 {len(specs)} 个独立逻辑单元, "
            "建议按 spec 拆分 commit (vibe commit --paths <spec 相关路径>): "
            + ", ".join(specs)
        )
    if len(cands) >= 2:
        warnings.append(
            f"--paths 含 {len(cands)} 个 skill 升级候选文档: 这是 {len(cands)} 个独立逻辑单元, "
            "建议按候选文档拆分 commit: " + ", ".join(cands)
        )
    elif specs and cands:
        warnings.append(
            f"--paths 含 spec 改动与 candidate 文档 ({len(cands)}), 可能是两个逻辑单元: "
            "spec 相关: " + ", ".join(specs) +
            "; candidate: " + ", ".join(cands)
        )
    return warnings


def _extract_commit_message(commit_argv: list[str]) -> str:
    """Extract commit message from git commit argv.

    Handles `-m "msg"`, `-m"msg"`, `--message=msg`, `--message msg`.
    Returns empty string if no message flag found (agent will be prompted
    by git itself for an editor-based message — drift advisory silently
    skips in that case).
    """
    msg_parts: list[str] = []
    i = 0
    while i < len(commit_argv):
        arg = commit_argv[i]
        if arg in ("-m", "--message") and i + 1 < len(commit_argv):
            msg_parts.append(commit_argv[i + 1])
            i += 2
        elif arg.startswith("-m") and len(arg) > 2:
            # -m"msg" or -mmsg
            msg_parts.append(arg[2:])
            i += 1
        elif arg.startswith("--message="):
            msg_parts.append(arg[len("--message="):])
            i += 1
        else:
            i += 1
    return " ".join(msg_parts)


def _check_inbox_drift_advisory(commit_argv: list[str], project_root: str) -> list[str]:
    """Detect commit message references fix-<name> but inbox row still [ ].

    Returns list of fix names that have unclosed inbox rows. Empty list
    means no drift (or feature disabled, or no inbox file).

    Rule 65 opt-in: only fires when workflow.json.bugs.inbox = True.
    """
    workflow_path = os.path.join(project_root, ".agents", "workflow.json")
    if not os.path.exists(workflow_path):
        return []
    try:
        import json as _json
        with open(workflow_path, encoding="utf-8") as f:
            workflow = _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return []
    bugs = (workflow or {}).get("bugs", {})
    if not bugs.get("inbox", False):
        return []

    message = _extract_commit_message(commit_argv)
    if not message:
        return []
    # Find fix-<name> tokens in the commit message.
    # Three forms recognised (all map to inbox rows that say "fix-<name>"):
    #   - explicit: fix-clipboard-catch / fix_clipboard_catch
    #   - conventional commits: fix(clipboard-catch) / fix[clipboard-catch]
    #   - conventional commits underscore: fix(clipboard_catch)
    # The conventional-commits form is reconstructed as "fix-<name>" so it
    # matches the inbox row format.
    fix_names: list[str] = []
    for raw_match in re.finditer(
        r"fix[-_]([A-Za-z][\w-]+)|fix\(([A-Za-z][\w-]+)\)",
        message,
        re.IGNORECASE,
    ):
        # Two capture groups: alt-1 captures fix-X / fix_X, alt-2 captures fix(X).
        captured = raw_match.group(1) or raw_match.group(2)
        if captured:
            # Reconstruct canonical fix-<name> form (dash separator).
            fix_names.append("fix-" + captured.replace("_", "-"))
        else:
            # Already in fix-<name> form (alt-2 path that consumed only one char).
            fix_names.append(raw_match.group(0).replace("_", "-"))
    if not fix_names:
        return []

    inbox_path = os.path.join(project_root, ".agents", "bug-inbox.md")
    if not os.path.exists(inbox_path):
        return []

    try:
        with open(inbox_path, encoding="utf-8") as f:
            inbox_content = f.read()
    except OSError:
        return []

    unclosed: list[str] = []
    for fix_name in fix_names:
        # Normalize: fix_clipboard_catch → fix-clipboard-catch (matches inbox rows).
        # Keep both forms to handle agent that mixes separators.
        candidates = {fix_name, fix_name.replace("_", "-"), fix_name.replace("-", "_")}
        for cand in candidates:
            # Find a - [ ] (open) row mentioning this fix name.
            pattern = r"^-\s*\[\s*\]\s*[^\n]*?" + re.escape(cand) + r"[^\n]*$"
            if re.search(pattern, inbox_content, re.MULTILINE | re.IGNORECASE):
                unclosed.append(fix_name)
                break
    return unclosed


def _print_paths_logical_unit_warnings(paths):
    warnings = _audit_paths_logical_unit(paths)
    if not warnings:
        return
    print()
    print("⚠️  --paths 逻辑单元 advisory (Rule 53 + 2026-07-10 #5 commit-logical-unit):")
    for w in warnings:
        print(f"   - {w}")
    print("<!-- vibe:commit_logical_unit_advisory: surfaced -->")


def _parse_manual_argv(argv: list[str]) -> tuple[list[str], dict]:
    """Pull vibe-specific flags out of the argv list.

    Manual argv parsing: argparse.REMAINDER swallows --no-verify into
    git_args, so we cannot rely on argparse for the flag. Same applies
    to --staged and --paths.

    Returns (cleaned_argv, state_dict). Tests exercise this directly.
    """
    no_verify = False
    no_verify_reason = ""
    no_async_gate = False
    staged_only = False
    full_verify = False
    reviewed = False
    quick = False
    paths: list[str] = []
    review_summary = ""
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-verify":
            no_verify = True
            i += 1
            # 2026-07-12b: optional inline reason for audit trail. Bare
            # `--no-verify` (no reason) remains valid for backward compat
            # but emits an advisory hint pointing to the audit-friendly
            # `--no-verify "<reason>"` form below. Consume the next
            # token only if it doesn't look like a flag.
            if i < len(argv) and not argv[i].startswith("-"):
                no_verify_reason = argv[i]
                i += 1
            continue
        if a == "--no-async-gate":
            no_async_gate = True
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
        if a == "--quick":
            quick = True
            i += 1
            continue
        if a == "--full-verify":
            full_verify = True
            i += 1
            continue
        if a == "--review-summary":
            # The next token is the literal summary text (do NOT split
            # on spaces — the summary may contain spaces). Empty string
            # is allowed here so the enforcement block can reject it
            # with a clear error.
            i += 1
            if i < len(argv):
                review_summary = argv[i]
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
    state = {
        "no_verify": no_verify,
        "no_verify_reason": no_verify_reason,
        "no_async_gate": no_async_gate,
        "staged_only": staged_only,
        "full_verify": full_verify,
        "reviewed": reviewed,
        "quick": quick,
        "paths": paths,
        "review_summary": review_summary,
    }
    return cleaned, state


def run(argv: list[str]) -> int:
    """Entry point used by both the CLI and the vibe.py dispatcher.

    Thin wrapper: extract flag state via _parse_manual_argv() and hand
    off to commit(). Keeping parser isolated lets tests exercise argv
    handling without spinning up a full commit flow.
    """
    argv, state = _parse_manual_argv(argv)
    no_verify = state["no_verify"]
    no_verify_reason = state["no_verify_reason"]
    no_async_gate = state["no_async_gate"]
    staged_only = state["staged_only"]
    full_verify = state["full_verify"]
    reviewed = state["reviewed"]
    quick = state["quick"]
    paths = state["paths"]
    review_summary = state["review_summary"]


    if not argv:
        print("Usage: vibe commit <project_root> [--staged | --paths p1,p2] "
              "[--no-verify] [--no-async-gate] [--full-verify] "
              "[--reviewed --review-summary '<text>'] [--quick] [git commit args...]")
        print()
        print("提示: review-summary 模板见 `vibe commit --help` (epilog 段)")
        return 2
    if paths:
        _print_paths_logical_unit_warnings(paths)
    project_root = argv[0]
    git_args = argv[1:]

    if no_verify:
        # Direct hand-off, no gate. Documented escape hatch. Stage
        # selection is also skipped: the user opted out of the full
        # vibe commit flow.
        #
        # Even when bypassing verify, we still inject a Review-Summary
        # trailer if --reviewed + --review-summary were passed — without
        # this the audit trail is broken (Agent "reviewed" but the claim
        # is invisible in git history). Vibe-Commit=no-verify distinguishes
        # this from a normal commit so doctor can detect the bypass.
        #
        # 2026-07-12b: --no-verify "<reason>" carries the reason into
        # the trailer so `git log | grep Vibe-Commit` exposes why each
        # bypass was used (audit completeness). Bare `--no-verify` is
        # still allowed (backward compat) but the gate below emits an
        # advisory hint to nudge toward the reason form.
        project_root = os.path.abspath(project_root)
        if not _is_git_repo(project_root):
            print("❌ 当前项目不是 git 仓库")
            return 1
        if paths:
            _run(["git", "reset", "HEAD"], project_root)
            _run(["git", "add", "--"] + paths, project_root)
        if no_verify_reason:
            trailer_value = f"Vibe-Commit=no-verify: {no_verify_reason}"
        else:
            trailer_value = "Vibe-Commit=no-verify"
            print(
                "⚠️  --no-verify used without reason: `git log | grep Vibe-Commit` "
                "won't show why this commit skipped review. Pass reason: "
                "`vibe commit --no-verify 'R53 bug short-name' ...` (advisory, "
                "不阻塞 commit)."
            )
        augmented_argv = [*git_args, "--trailer", trailer_value]
        if reviewed and review_summary.strip():
            augmented_argv.extend([
                "--trailer", f"Review-Summary={review_summary.strip()}",
            ])
        completed = subprocess.run(
            ["git", "commit", *augmented_argv], cwd=project_root
        )
        return completed.returncode

    return commit(
        project_root,
        git_args,
        staged_only=staged_only,
        paths=paths,
        full_verify=full_verify,
        reviewed=reviewed,
        no_verify=no_verify,
        quick=quick,
        review_summary=review_summary,
        no_async_gate=no_async_gate,
    )


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
