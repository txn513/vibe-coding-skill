#!/usr/bin/env python3
from __future__ import annotations
"""vibe verify — standalone verification runner.

Runs the configured verify commands from workflow.json without committing.
Useful when the agent wants to check "does the full suite pass?" before
deciding to commit, or to validate after a series of --no-verify commits.

Three tiers (same as vibe commit):
  verify_scope  — fast, scoped verification
  verify        — default full suite
  verify_full   — explicit full suite (includes integration/e2e)

Usage:
  vibe verify <project_root>           # runs verify (default)
  vibe verify <project_root> --scope   # runs verify_scope
  vibe verify <project_root> --full    # runs verify_full
"""


import os
import subprocess
import sys

from workflow_state import configured_commands, ensure_workflow


def _run(argv: list[str], cwd: str) -> tuple[int, str, str]:
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def verify(project_root: str, tier: str = "verify") -> int:
    """Run configured verify commands for the given tier.

    Returns 0 if all pass, 1 if any fail, 2 if no commands configured.
    """
    project_root = os.path.abspath(project_root)

    agents_dir = os.path.join(project_root, ".agents")
    if not os.path.exists(agents_dir):
        print("📭 项目尚未初始化 Vibe Coding。运行 init_project.py 或 onboard_project.py。")
        return 2

    workflow, _ = ensure_workflow(project_root)
    commands = configured_commands(workflow, tier)

    # Fallback chain: verify_full → verify → verify_scope
    if not commands:
        fallback_map = {
            "verify_full": "verify",
            "verify_scope": "verify",
            "verify": None,
        }
        fallback = fallback_map.get(tier)
        if fallback:
            commands = configured_commands(workflow, fallback)
            if commands:
                print(f"⚠️  {tier} 未配置，回退到 {fallback}")
        if not commands:
            print(
                f"❌ 项目未配置 {tier} 命令。\n"
                f"   在 .agents/workflow.json 的 commands.{tier} 中添加验证命令。\n"
                f"   例子: {{\"commands\": {{\"{tier}\": [[\"pytest\", \"-x\"]]}}}}"
            )
            return 2

    tier_label = {
        "verify_scope": "scoped 快速验证",
        "verify": "全量验证",
        "verify_full": "全量验证 (verify_full)",
    }.get(tier, tier)

    print(f"🔍 跑 {len(commands)} 条 {tier} 命令 ({tier_label}):")

    all_passed = True
    for idx, argv in enumerate(commands, 1):
        print(f"   [{idx}/{len(commands)}] {' '.join(argv)}")
        rc, out, err = _run(argv, project_root)
        if rc != 0:
            all_passed = False
            print(f"   ❌ 失败 (exit {rc})")
            if out.strip():
                print("   --- stdout ---")
                # Show last 30 lines of stdout to keep output manageable
                lines = out.rstrip().splitlines()
                if len(lines) > 30:
                    print(f"   ... (省略前 {len(lines) - 30} 行)")
                    print("\n".join(lines[-30:]))
                else:
                    print(out.rstrip())
            if err.strip():
                print("   --- stderr ---")
                lines = err.rstrip().splitlines()
                if len(lines) > 30:
                    print(f"   ... (省略前 {len(lines) - 30} 行)")
                    print("\n".join(lines[-30:]))
                else:
                    print(err.rstrip())
            break
        print(f"   ✅ 通过")

    print()
    if all_passed:
        print(f"✅ {tier} 全通过")
        print("<!-- vibe:verify_result: passed -->")
        return 0
    else:
        print(f"❌ {tier} 有失败")
        print("<!-- vibe:verify_result: failed -->")
        return 1


def run(argv: list[str]) -> int:
    """Entry point for vibe.py dispatcher."""
    tier = "verify"
    project_root = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--scope":
            tier = "verify_scope"
            i += 1
            continue
        if a == "--full":
            tier = "verify_full"
            i += 1
            continue
        if not project_root:
            project_root = a
        i += 1

    if not project_root:
        print("Usage: vibe verify <project_root> [--scope | --full]")
        return 2

    return verify(project_root, tier)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
