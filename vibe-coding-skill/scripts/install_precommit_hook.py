#!/usr/bin/env python3
"""Install a pre-commit hook that blocks raw `git commit`.

The hook requires every commit to have a `Vibe-Commit:` trailer,
which is only written by `vibe commit` (Rule 53). This makes it
impossible to accidentally bypass the two-step review + verify gate
with `git commit`.

Usage:
    python install_precommit_hook.py <project_root>
"""

import os
import stat

HOOK_CONTENT = '''#!/bin/bash
# Vibe Coding pre-commit hook (Rule 53 enforcement)
# Installed by `vibe install-precommit-hook`
#
# Blocks any commit that lacks the Vibe-Commit trailer.
# The trailer is written by `vibe commit` during step 2 (verify + commit).
# If a commit is made with raw `git commit`, this hook rejects it
# and tells the user how to fix.

COMMIT_MSG_FILE="$1"

if ! grep -q "^Vibe-Commit:" "$COMMIT_MSG_FILE"; then
    echo "❌ 错误：此项目必须使用 \`vibe commit\` 提交代码（Rule 53）"
    echo ""
    echo "   当前提交缺少 Vibe-Commit trailer，说明是用 \`git commit\` 直接提交的。"
    echo "   这绕过了 review + verify gate，会导致失败模式不可见、同样错误重复。"
    echo ""
    echo "   修复步骤（任选其一）："
    echo "   1. 撤销本次提交：git reset --soft HEAD~1"
    echo "   2. 用 vibe commit 重新提交（两步流程：看 diff → verify → commit）"
    echo "   3. 如果实在要跳过（如 docs-only）：vibe commit --quick"
    echo ""
    echo "   禁止用 \`git commit\` 直接提交 —— 这是防错 guard rail，不是可选 overhead。"
    exit 1
fi
'''


def install_hook(project_root: str) -> int:
    """Install the pre-commit hook. Returns exit code."""
    project_root = os.path.abspath(project_root)
    hook_dir = os.path.join(project_root, ".git", "hooks")
    hook_path = os.path.join(hook_dir, "pre-commit")

    if not os.path.isdir(hook_dir):
        print(f"❌ 不是 git 仓库或缺少 .git/hooks: {hook_dir}")
        return 1

    # Check if an existing hook exists (don't clobber user custom hooks)
    if os.path.exists(hook_path):
        with open(hook_path, "r", encoding="utf-8") as f:
            existing = f.read()
        if "Vibe-Commit:" in existing:
            print(f"✅ Vibe Coding pre-commit hook 已存在: {hook_path}")
            return 0
        print(f"⚠️  已有其他 pre-commit hook: {hook_path}")
        print("   请手动合并以下代码到现有 hook 中：")
        print("   ---")
        print(HOOK_CONTENT.strip())
        print("   ---")
        return 1

    # Write the hook
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(HOOK_CONTENT)
    # Make executable
    os.chmod(hook_path, os.stat(hook_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"✅ Vibe Coding pre-commit hook 已安装: {hook_path}")
    print("   现在任何没有 Vibe-Commit trailer 的 git commit 都会被阻止。")
    print("   卸载：rm .git/hooks/pre-commit")
    return 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Install Vibe Coding pre-commit hook")
    p.add_argument("project_root", help="Project root directory")
    args = p.parse_args()
    raise SystemExit(install_hook(args.project_root))
