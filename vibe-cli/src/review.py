"""Generate independent review context."""

import importlib
import os
import subprocess
from datetime import datetime, timezone


def generate_review(project_root: str, spec_name: str | None = None) -> str | None:
    """Generate a review context file for independent Agent review."""
    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    os.makedirs(reviews_dir, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    review_file = os.path.join(reviews_dir, f"review-{now}.md")

    diff = _get_git_diff(project_root)
    branch = _get_git_branch(project_root)
    agents_md = _read_file(os.path.join(project_root, "AGENTS.md"))
    spec_content = ""
    if spec_name:
        spec_mod = importlib.import_module("spec")
        spec_content = spec_mod.read_spec(project_root, spec_name) or ""

    content = f"""# Code Review — {now}

> 分支: {branch} | 规格: {spec_name or 'N/A'}

## 项目上下文

{agents_md if agents_md else '(AGENTS.md 未找到 — 请先运行 vibe init)'}

## 功能规格

{spec_content if spec_content else '(未指定规格文件)'}

## 变更内容 (git diff)

```diff
{diff if diff else '(无变更)'}
```

## 审查要点

请独立审查以下方面（不要受实现 Agent 的上下文影响）:

### 🔴 安全
- 是否有注入风险（SQL、XSS、命令注入）？
- 是否有越权访问？
- 是否有敏感信息泄露？

### 🟡 逻辑
- 边界情况是否处理？
- 并发场景是否安全？
- 错误处理是否完整？

### 🟢 质量
- 命名是否清晰、符合项目规范？
- 是否有不必要的复杂度？
- 是否有遗漏的测试覆盖？

### 🔵 影响
- 对现有功能是否有破坏性变更？
- 性能是否有明显退化？
- 依赖是否合理？
"""
    with open(review_file, "w") as f:
        f.write(content)

    print(f"✅ 审查上下文已生成: {review_file}")
    print(f"📤 将该文件内容发送给独立的 Review Agent 进行审查。")
    print(f"💡 提示: 确保审查 Agent 是全新会话，不受实现上下文污染。")
    return review_file


def _get_git_diff(project_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "diff", "--stat"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            full = subprocess.run(
                ["git", "-C", project_root, "diff", "--", ":(exclude)package-lock.json",
                 ":(exclude)yarn.lock", ":(exclude)pnpm-lock.yaml",
                 ":(exclude)go.sum", ":(exclude)Cargo.lock"],
                capture_output=True, text=True, timeout=10
            )
            output = full.stdout.strip()
            if len(output) > 15000:
                output = output[:15000] + "\n... (truncated)"
            return output
        return "(无未提交的变更)"
    except Exception as e:
        return f"(git diff 失败: {e})"


def _get_git_branch(project_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "branch", "--show-current"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _read_file(path: str) -> str | None:
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None
