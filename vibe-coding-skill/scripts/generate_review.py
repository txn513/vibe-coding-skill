#!/usr/bin/env python3
"""Generate an independent code review context file."""

import argparse
import os
import subprocess
from datetime import datetime, timezone

from common import (
    atomic_write,
    git_snapshot,
    project_context_digest,
    spec_digest,
    validate_artifact_name,
)


def generate_review(
    project_root: str,
    spec_name: str | None = None,
    reviewer: str = "",
) -> str | None:
    if spec_name:
        spec_name = validate_artifact_name(spec_name, "规格名称")
    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    os.makedirs(reviews_dir, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    review_file = os.path.join(reviews_dir, f"review-{now}.md")

    diff = _git_diff(project_root)
    branch = _git_branch(project_root)
    agents_md = _read(os.path.join(project_root, "AGENTS.md"))
    spec_content = ""
    if spec_name:
        spec_file = os.path.join(project_root, ".agents", "specs", f"{spec_name}.md")
        spec_content = _read(spec_file) or ""
        if not spec_content:
            print(f"❌ 规格不存在: {spec_name}")
            return None
    spec_version = spec_digest(spec_content) if spec_content else "N/A"
    context_digest = project_context_digest(project_root)
    git = git_snapshot(project_root)

    content = f"""# Code Review — {now}

> 规格: {spec_name or 'N/A'} | 规格摘要: {spec_version} | 上下文摘要: {context_digest} | 结论: pending | 分支: {branch}
> Commit: {git['commit']} | Snapshot: {git.get('snapshot', 'N/A')} | 工作区: {git['worktree']} | Reviewer: {reviewer or '未记录'} | Role: reviewer
> Decision-Record: pending

将 `pending` 改为 `approved` 或 `changes-requested`，并在下方记录依据。

## 项目上下文

{agents_md if agents_md else '(AGENTS.md 未找到 — 请先运行 init_project.py)'}

## 功能规格

{spec_content if spec_content else '(未指定规格文件)'}

## 变更内容 (git diff)

```diff
{diff if diff else '(无变更)'}
```

## 审查要点

请独立审查以下方面（不要受实现 Agent 的上下文影响）:

### 安全
- 是否符合项目定义的安全规则与风险边界？
- 输入、权限、数据与依赖边界是否经过验证？
- 是否引入项目未接受的安全风险？

### 逻辑
- 边界情况是否处理？
- 并发场景是否安全？
- 错误处理是否完整？

### 质量
- 命名是否清晰、符合项目规范？
- 是否有不必要的复杂度？
- 是否有遗漏的测试覆盖？

### 影响
- 对现有功能是否有破坏性变更？
- 性能是否有明显退化？
- 依赖是否合理？

## 审查结论与依据

- 结论依据:
- 必须修复的问题:
- 已核对的验证证据:
"""
    atomic_write(review_file, content)

    print(f"✅ 审查上下文已生成: {review_file}")
    print(f"📤 将该文件路径粘贴到一个新的 Codex 会话中。")
    print(f"   新的会话会加载 \"Vibe Coding Reviewer\" Skill（与本核心 Skill 同一套件），")
    print(f"   独立审查本工作并通过 scripts/review_decision.py 记录结论。")
    print(f"   如尚未安装该辅助 Skill，请运行：")
    print(f"     python3 <vibe-coding-skill>/scripts/vibe.py install-auxiliary --all")
    return review_file


def _git_diff(root: str) -> str:
    try:
        inside = subprocess.run(
            ["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if inside.returncode != 0:
            return "(当前目录不是 Git 工作区)"

        has_head = subprocess.run(
            ["git", "-C", root, "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).returncode == 0
        if has_head:
            tracked = subprocess.run(
                ["git", "-C", root, "diff", "--binary", "HEAD", "--"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
        else:
            staged = subprocess.run(
                ["git", "-C", root, "diff", "--binary", "--cached", "--"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            unstaged = subprocess.run(
                ["git", "-C", root, "diff", "--binary", "--"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            tracked = "\n\n".join(part for part in (staged, unstaged) if part)

        untracked_result = subprocess.run(
            ["git", "-C", root, "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        untracked = [line for line in untracked_result.stdout.splitlines() if line]

        parts = []
        if tracked:
            parts.append(tracked)
        if untracked:
            parts.append(
                "未跟踪文件（内容未自动嵌入，请在审查时逐一检查）:\n"
                + "\n".join(f"- {name}" for name in untracked)
            )
        out = "\n\n".join(parts) or "(无未提交的变更)"
        return out[:15000] + ("\n... (truncated)" if len(out) > 15000 else "")
    except Exception as e:
        return f"(git diff 失败: {e})"


def _git_branch(root: str) -> str:
    try:
        r = subprocess.run(["git", "-C", root, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _read(path: str) -> str | None:
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate review context")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("spec_name", nargs="?", default=None, help="Associated spec name")
    p.add_argument("--reviewer", default="", help="Reviewer identity")
    args = p.parse_args()
    generate_review(os.path.abspath(args.project_root), args.spec_name, args.reviewer)
