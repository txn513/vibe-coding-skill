#!/usr/bin/env python3
"""Create a project-local discovery record before design or specification."""

import argparse
import os
from datetime import datetime, timezone

from common import atomic_write, validate_artifact_name

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_intent(project_root: str, name: str) -> str:
    name = validate_artifact_name(name, "发现记录名称")
    path = os.path.join(project_root, ".agents", "intents", f"{name}.md")
    if os.path.exists(path):
        print(f"⚠️  发现记录已存在: {path}")
        return path
    template = os.path.join(SKILL_DIR, "templates", "intent.md")
    with open(template, encoding="utf-8") as handle:
        content = handle.read()
    replacements = {
        "INTENT_NAME": name,
        "CREATED_AT": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "PROBLEM": "(描述观察到的问题，不预设解决方案)",
        "AUDIENCE": "(描述受影响的对象和发生场景)",
        "EVIDENCE": "(记录已有事实、反馈或数据；没有则明确写无)",
        "SUCCESS_SIGNAL": "(定义可观察的改善信号和当前基线)",
        "ALTERNATIVES": "(列出不开发、流程调整或其他可能方案)",
        "TRADEOFFS": "(记录成本、风险和放弃其他工作的代价)",
        "DECISION_BASIS": "(填写决定继续、补证据、暂停或放弃的理由)",
    }
    for key, value in replacements.items():
        content = content.replace("{{" + key + "}}", value)
    atomic_write(path, content)
    print(f"✅ 发现记录已创建: {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a discovery/intent record")
    parser.add_argument("project_root")
    parser.add_argument("name")
    args = parser.parse_args()
    create_intent(os.path.abspath(args.project_root), args.name)
