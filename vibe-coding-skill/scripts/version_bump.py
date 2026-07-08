#!/usr/bin/env python3
"""vibe version-bump — Skill self-maintenance, automate the chore commit.

The Skill's `VERSION` file follows the convention `<7-char-head-hash>-<slug>`
(Rule 52.1). Historically maintainers hand-typed this string in a
`chore(skill): bump VERSION to ...` commit, repeatedly writing the
**previous** feat commit's hash instead of the **new** chore commit's
hash, causing `vibe doctor` / `vibe upgrade` to report false "up to
date" until the next bump.

This command closes that loop:

  1. Read the current git HEAD short hash (pre-commit; will become
     the post-commit hash once we land the chore commit).
  2. Read the previous **non-chore** commit's subject (skip the most
     recent commit if it's already a `chore(skill): bump VERSION`,
     otherwise use the current HEAD). The slug is sourced from the
     feat commit, not the bump commit, so VERSION is human-readable.
  3. Compute the VERSION path relative to the git root so the dev
     checkout (`vibe-coding-skill/` is a sub-directory) works the
     same as an installed Skill with VERSION at the repo root.
  4. Write `VERSION = <head-hash>-<slug>`.
  5. `git add <relpath>` and `git commit -m "chore(skill): bump VERSION"`.

Why no hash in the subject: writing a placeholder hash and then
amending the subject with the real post-commit hash would change the
SHA twice in one logical change and break Rule 53 trailer invariants.
Leaving the hash out of the subject is self-consistent (subject ↔ SHA
is a chicken-and-egg problem that humans shouldn't solve by hand).

Why VERSION content lags HEAD by one commit: the convention is
`<7-char-hash>-<slug>` and the hash is captured **before** the commit
that introduces it. After the commit lands, HEAD's 7-char prefix no
longer matches what's in VERSION. This is an inherent property of the
convention, not a bug. `_check_skill_version_drift()` (Rule 52.1)
treats "the last commit that touched VERSION == HEAD" as no-drift,
which holds immediately after `vibe version-bump` lands. The drift
warning only fires when a **feat** commit lands without a follow-up
`vibe version-bump`, which is the failure mode this command prevents.

Run this command from inside the Skill repo (no project_root argument
is needed — the Skill is its own repo). Exit code 0 on success, 1 on
git failure, 2 on missing VERSION file.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys


_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILENAME = "VERSION"
SLUG_MAX_LEN = 48
BUMP_SUBJECT_PREFIX = "chore(skill): bump VERSION"


def _run_git(*args: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _git_root(start: str) -> str | None:
    """Walk up to find the git root, mirroring doctor/upgrade."""
    cur = start
    while cur != "/":
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        cur = os.path.dirname(cur)
    return None


def _slugify_subject(subject: str, max_len: int = SLUG_MAX_LEN) -> str:
    """Lowercase, replace non-alphanum with '-', collapse dashes, trim."""
    s = subject.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if not s:
        return "unnamed"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s


def _feat_subject(git_root: str) -> tuple[str, str]:
    """Return (pre_hash, feat_slug).

    If HEAD's subject is already a bump commit, skip it and use the
    prior commit's subject (the actual feat commit). Otherwise use
    HEAD's subject directly.

    Returns ("", "unnamed") if no prior commit exists (initial repo).
    """
    head_proc = _run_git("rev-parse", "--short", "HEAD", cwd=git_root)
    if head_proc.returncode != 0:
        return "", "unnamed"
    pre_hash = head_proc.stdout.strip()

    subject_proc = _run_git("log", "-1", "--format=%s", cwd=git_root)
    if subject_proc.returncode != 0:
        return pre_hash, "unnamed"
    head_subject = subject_proc.stdout.strip()

    if head_subject.startswith(BUMP_SUBJECT_PREFIX):
        # Walk back through any number of consecutive bump commits
        # until we hit a non-bump subject. Use `git log -n` with
        # increasing --skip values; bail on first non-bump hit or on
        # any error.
        for skip in range(1, 10):
            skip_proc = _run_git(
                "log", f"--skip={skip}", "-1", "--format=%s",
                cwd=git_root,
            )
            if skip_proc.returncode != 0 or not skip_proc.stdout.strip():
                return pre_hash, "unnamed"
            candidate = skip_proc.stdout.strip()
            if not candidate.startswith(BUMP_SUBJECT_PREFIX):
                return pre_hash, _slugify_subject(candidate)
        # More than 10 consecutive bumps with no feat subject seen.
        return pre_hash, "unnamed"

    return pre_hash, _slugify_subject(head_subject)


def bump() -> int:
    """Execute the version-bump workflow. Returns shell exit code."""
    skill_dir = _SKILL_DIR
    version_path = os.path.join(skill_dir, VERSION_FILENAME)
    if not os.path.exists(version_path):
        print(f"❌ {version_path} not found; not inside a Skill checkout?",
              file=sys.stderr)
        return 2

    git_root = _git_root(skill_dir)
    if not git_root:
        print("❌ no git repo found walking up from the Skill dir",
              file=sys.stderr)
        return 1

    pre_hash, slug = _feat_subject(git_root)
    if not pre_hash:
        print("❌ no git commits yet; nothing to bump", file=sys.stderr)
        return 1

    new_version = f"{pre_hash}-{slug}"

    version_relpath = os.path.relpath(version_path, git_root)

    try:
        with open(version_path, encoding="utf-8") as fp:
            current = fp.read().strip()
    except OSError as exc:
        print(f"❌ cannot read VERSION: {exc}", file=sys.stderr)
        return 1

    if current == new_version:
        print(f"✅ VERSION already up to date ({new_version}); no commit needed.")
        return 0

    # Idempotency check 2: if HEAD is already a bump commit and the
    # working tree is clean, there is nothing to bump. This is the
    # "ran bump twice in a row" case — bump itself produces a commit,
    # so HEAD advances and the next bump call would normally rewrite
    # VERSION with the new pre_hash; but there is nothing semantically
    # new to record. Skip the second commit to avoid pointless churn.
    head_subject_proc = _run_git("log", "-1", "--format=%s", cwd=git_root)
    if (head_subject_proc.returncode == 0 and
            head_subject_proc.stdout.strip().startswith(BUMP_SUBJECT_PREFIX)):
        status_proc = _run_git("status", "--porcelain", cwd=git_root)
        if status_proc.returncode == 0 and not status_proc.stdout.strip():
            print(f"✅ HEAD is already a bump commit and tree is clean; "
                  f"nothing to do.")
            return 0

    try:
        with open(version_path, "w", encoding="utf-8") as fp:
            fp.write(new_version + "\n")
    except OSError as exc:
        print(f"❌ cannot write VERSION: {exc}", file=sys.stderr)
        return 1

    add_proc = _run_git("add", "--", version_relpath, cwd=git_root)
    if add_proc.returncode != 0:
        print(f"❌ git add {version_relpath} failed: {add_proc.stderr.strip()}",
              file=sys.stderr)
        return 1

    commit_msg = BUMP_SUBJECT_PREFIX
    commit_proc = _run_git(
        "commit", "-m", commit_msg,
        "--no-verify",
        cwd=git_root,
    )
    if commit_proc.returncode != 0:
        print(f"❌ git commit failed: {commit_proc.stderr.strip()}",
              file=sys.stderr)
        return 1

    print(f"✅ VERSION bumped to {new_version}")
    print("   new HEAD last-touched VERSION (drift check satisfied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(bump())
