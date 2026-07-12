#!/usr/bin/env python3
"""Create a skill upgrade candidate proposal in the project.

Usage:
    python3 propose_skill_upgrade.py <project_root> <title>

Creates a proposal in .agents/skill-upgrade-candidates/ with a date-based
filename following the convention: skill-upgrade-candidate-YYYYMMDD<N>.md
"""

import argparse
import os
import re
from datetime import datetime, timezone


def _find_next_suffix(project_root: str) -> str:
    """Find the next available suffix for today's date.
    
    Convention: skill-upgrade-candidate-YYYYMMDD.md → ...-YYYYMMDDc.md
    If "skill-upgrade-candidate-20260713.md" exists, try "...-20260713b.md", etc.
    """
    candidates_dir = os.path.join(project_root, ".agents", "skill-upgrade-candidates")
    if not os.path.isdir(candidates_dir):
        return ""
    
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    # Check if any file for today exists
    has_today = False
    max_suffix = ""
    for fname in os.listdir(candidates_dir):
        if not fname.startswith(f"skill-upgrade-candidate-{today}"):
            continue
        has_today = True
        # Extract suffix letter (b, c, d, ...)
        match = re.search(rf"skill-upgrade-candidate-{today}([a-z]*)\.md$", fname)
        if match:
            suffix = match.group(1)
            if suffix and suffix > max_suffix:
                max_suffix = suffix
    
    if not has_today:
        return ""  # No files for today, use bare date
    
    # Next suffix: if max is "b", next is "c"; if max is "", next is "b"
    if not max_suffix:
        return "b"
    
    # Increment last character
    next_char = chr(ord(max_suffix[-1]) + 1)
    return max_suffix[:-1] + next_char


def propose_skill_upgrade(project_root: str, title: str) -> str:
    """Create a new skill upgrade candidate proposal. Returns the file path."""
    project_root = os.path.abspath(project_root)
    candidates_dir = os.path.join(project_root, ".agents", "skill-upgrade-candidates")
    os.makedirs(candidates_dir, exist_ok=True)
    
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = _find_next_suffix(project_root)
    
    # Build filename: skill-upgrade-candidate-YYYYMMDD.md or ...-YYYYMMDD<N>.md
    if suffix:
        filename = f"skill-upgrade-candidate-{today}{suffix}.md"
    else:
        filename = f"skill-upgrade-candidate-{today}.md"
    
    filepath = os.path.join(candidates_dir, filename)
    
    if os.path.exists(filepath):
        raise FileExistsError(
            f"Skill upgrade proposal already exists at {filepath}. " +
            "Use a different title or amend the existing proposal."
        )
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    content = f"""# Skill 升级候选 — {today}

来源: （请填写 retro 文件名或本次项目流程反思来源）
日期: {now}
标题: {title}
状态: proposed

---

## 候选 1: （请填写标题）

**分类**: governance / project

**问题**: （请描述问题现象，引用 retro 或实际案例）

**建议方案**: （请描述建议的 Skill 规则变更、新增命令、或流程调整）

**通用性审计**:
- 通用: （是/否，是否跨项目适用）
- 不含项目知识: （是/否）
- 跨项目适用: （是/否）
- 失败模式: （"rule exists but not bound to a gate" / "evidence exists but does not prove..." 等）

**影响范围**: （哪些 agent 行为会受影响）

**实施复杂度**: 低 / 中 / 高

**预期收益**: （简要说明）

---

## 评估

| 候选 | 紧急程度 | 实施复杂度 | 预计收益 |
|------|---------|-----------|---------|
| 候选 1 | 高/中/低 | 低/中/高 | ... |

建议优先级: （排序）

---

## 管理员反馈

（待管理员评审后填写）

### 候选 1 — 状态: （待评审 / 已采纳 / 已拒绝 / 已归档）

- 实施 commit: （如果已采纳）
- 拒绝原因: （如果已拒绝）

---

> 归档说明: 本提案经管理员评审后，如已采纳或拒绝，请移动到
> .agents/archive/skill-upgrade-candidates/ 归档。
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✅ Skill 升级提案已创建: {filepath}")
    print(f"   请填写提案内容，然后提交给管理员评审。")
    print(f"   归档路径: .agents/archive/skill-upgrade-candidates/")
    return filepath


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a skill upgrade candidate proposal")
    parser.add_argument("project_root", help="Project root directory")
    parser.add_argument("title", help="Short title for the proposal")
    args = parser.parse_args()
    propose_skill_upgrade(args.project_root, args.title)
