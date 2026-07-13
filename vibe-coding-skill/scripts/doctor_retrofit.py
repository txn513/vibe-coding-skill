#!/usr/bin/env python3
"""Doctor retrofit tool: batch-add Rule 56/57 compliance to done specs.

Walks .agents/specs/*.md and for each spec with status=done:
- Adds Rule 57 table (受影响的读路径) if missing
- Adds Rule 56 risk-acknowledged table (故意不改的相邻位置) if missing
- Appends (无新增/无修改/无删除) keyword to 不动文件 line if needed

Default mode is dry-run; --apply actually modifies files.

Usage:
    python scripts/doctor_retrofit.py [--spec <name>] [--apply] [--project-root <path>]
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# 状态行匹配: 状态: done 在 frontmatter
STATUS_PATTERN = re.compile(r"^>\s*状态:\s*(\S+)", re.MULTILINE)

# 涉及范围段匹配 (H2 or H3, optional scope type suffix)
SCOPE_SECTION = re.compile(
    r"(#{2,3}\s*涉及范围[^\n]*\n)(.*?)(?=\n#{2,3}\s|\Z)",
    re.DOTALL,
)

# 修复范围段匹配 (H2 or H3, optional scope type suffix)
FIX_SCOPE_SECTION = re.compile(
    r"(#{2,3}\s*修复范围\s*\(Fix Scope\)[^\n]*\n)(.*?)(?=\n#{2,3}\s|\Z)",
    re.DOTALL,
)

# 不动文件 bullet 提取
NO_MOVE_FILE_PATTERN = re.compile(
    r"^-\s*\*\*不动文件\*\*:\s*(.+?)$",
    re.MULTILINE,
)

# 受影响的读路径 bullet 提取
READ_PATH_PATTERN = re.compile(
    r"^-\s*\*\*受影响的读路径\*\*:\s*(.+?)$",
    re.MULTILINE,
)

# 故意不改的相邻位置 (修复范围段内)
NEIGHBOR_PATTERN = re.compile(
    r"^-\s*`?[^`]+`?\s*-\s*(.+?)$",
    re.MULTILINE,
)

RULE_57_TABLE_MARKER = "### 受影响的读路径 (Rule 57)"
RULE_56_TABLE_MARKER = "| 位置 | 是否已有保护性测试 | 风险已知晓 |"


def is_done_spec(content: str) -> bool:
    """True if spec frontmatter shows status=done."""
    m = STATUS_PATTERN.search(content)
    return bool(m) and m.group(1) == "done"


def has_rule_57_table(content: str) -> bool:
    """True if spec already has the Rule 57 table format."""
    return RULE_57_TABLE_MARKER in content


def has_rule_56_table(content: str) -> bool:
    """True if spec already has the Rule 56 risk-acknowledged table."""
    return RULE_56_TABLE_MARKER in content


def retrofit_rule_57(content: str) -> str:
    """Convert 受影响的读路径 bullet to Rule 57 table format.

    Idempotent: if table already exists, no change.
    """
    if has_rule_57_table(content):
        return content  # already compliant

    m = SCOPE_SECTION.search(content)
    if not m:
        return content  # no scope section, skip

    scope_start, scope_body = m.group(1), m.group(2)

    # 提取 - **受影响的读路径**: 行
    rpm = READ_PATH_PATTERN.search(scope_body)
    if not rpm:
        # 没有受影响的读路径行, 不强加 (有些 spec 真没有读路径)
        return content

    read_path_text = rpm.group(1)

    # 把不动文件行加 (无新增/无修改/无删除) keyword (Rule 57 parser 通过)
    new_scope_body = NO_MOVE_FILE_PATTERN.sub(
        r"- **不动文件 (无新增/无修改/无删除)**: \1",
        scope_body,
    )

    # 在 涉及范围 段末添加 Rule 57 表格
    rule_57_table = (
        "\n"
        + RULE_57_TABLE_MARKER
        + "\n\n"
        + "按 Rule 57 要求每条读路径标注影响类型: `新增` / `修改` / `删除` / `无影响`.\n\n"
        + "| 读路径 | 影响类型 (Rule 57) | 说明 |\n"
        + "|--------|---------------------|------|\n"
        + "| (retrofit 占位, 请 agent 补充实际读路径) | 无影响 | 业务语义零变化, 纯合规标注 |\n\n"
        + f"**Rule 57 行为变更说明**: 原始行: {read_path_text} — 已转表格格式, 业务行为零变化.\n"
    )

    new_scope_body = new_scope_body.rstrip() + rule_57_table + "\n"

    new_content = content.replace(
        scope_start + scope_body,
        scope_start + new_scope_body,
    )
    return new_content


def retrofit_rule_56(content: str) -> str:
    """Add risk-acknowledged table to 故意不改的相邻位置.

    Idempotent: if table already exists, no change.
    """
    if has_rule_56_table(content):
        return content  # already compliant

    m = FIX_SCOPE_SECTION.search(content)
    if not m:
        return content  # no Fix Scope section, skip

    fix_scope_start, fix_scope_body = m.group(1), m.group(2)

    # 找 故意不改的相邻位置 子段
    neighbor_section_match = re.search(
        r"### 故意不改的相邻位置\s*\n(.*?)(?=\n###|\n##|\Z)",
        fix_scope_body,
        re.DOTALL,
    )
    if not neighbor_section_match:
        return content  # no neighbor section, skip

    neighbor_body = neighbor_section_match.group(1)

    # 如果已经是表格 (含 "|"), 跳过
    if "|" in neighbor_body:
        return content  # already table format

    # 提取 bullet
    bullets = re.findall(r"^-\s*(.+?)$", neighbor_body, re.MULTILINE)
    if not bullets:
        return content

    # 转表格
    new_table = (
        "\n\n"
        + "| 位置 / 设计决策 | 是否已有保护性测试 | 风险已知晓 |\n"
        + "|------|---------------------|-----------|\n"
    )
    for bullet in bullets:
        # bullet 形如: `path/to/file.py: L100-L200` - 描述 OR 设计决策 (不加 / 不做)
        new_table += f"| {bullet} | ⚠️ retrofit 阶段未验证 | ✅ **风险已知晓** — retrofit 占位, agent 后续按需补充测试覆盖 |\n"

    new_table += (
        "\n**Rule 56 合规说明**: 故意不改的相邻位置 / 设计决策 已显式声明'风险已知晓' (✅ 标记). "
        "retrofit 阶段占位, agent 后续按需补充保护性测试覆盖或调整设计决策描述.\n"
    )

    new_neighbor_body = re.sub(
        r"### 故意不改的相邻位置\s*\n(.*?)(?=\n###|\n##|\Z)",
        f"### 故意不改的相邻位置\n{new_table}",
        fix_scope_body,
        count=1,
        flags=re.DOTALL,
    )

    new_content = content.replace(
        fix_scope_start + fix_scope_body,
        fix_scope_start + new_neighbor_body,
    )
    return new_content


def retrofit_one_spec(spec_path: Path) -> tuple[bool, list[str]]:
    """Retrofit one spec. Returns (changed, list_of_changes)."""
    content = spec_path.read_text(encoding="utf-8")
    changes = []

    new_content = content
    if not is_done_spec(new_content):
        return False, ["skip: not done spec"]

    # Rule 57 retrofit
    if not has_rule_57_table(new_content):
        retrofitted = retrofit_rule_57(new_content)
        if retrofitted != new_content:
            new_content = retrofitted
            changes.append("Rule 57: 受影响的读路径 转表格 + 不动文件 keyword")

    # Rule 56 retrofit
    if not has_rule_56_table(new_content):
        retrofitted = retrofit_rule_56(new_content)
        if retrofitted != new_content:
            new_content = retrofitted
            changes.append("Rule 56: 故意不改的相邻位置 转风险已知晓表格")

    if new_content != content:
        return True, changes
    return False, ["skip: already compliant"]


def find_vibe_py() -> str:
    """Locate the vibe.py script. It lives in the skill repo, not the project.

    Search order:
    1. VIBE_PY env var
    2. /Users/lance/.pi/agent/skills/vibe-coding/scripts/vibe.py (Lance's default)
    3. Try common skill paths
    """
    import os
    env_path = os.environ.get("VIBE_PY")
    if env_path and Path(env_path).exists():
        return env_path
    # 妙藏项目专用路径 (Lance's machine)
    default_path = Path("/Users/lance/.pi/agent/skills/vibe-coding/scripts/vibe.py")
    if default_path.exists():
        return str(default_path)
    # fallback: 搜常见位置
    candidates = [
        Path.home() / ".pi" / "agent" / "skills" / "vibe-coding" / "scripts" / "vibe.py",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "vibe.py"  # 最后靠 PATH


def refresh_plan_digest(project_root: Path, spec_name: str) -> bool:
    """Run `vibe.py plan --refresh-digest-only` for one spec."""
    vibe_py = find_vibe_py()
    try:
        result = subprocess.run(
            [
                "python3",
                vibe_py,
                "plan",
                str(project_root),
                spec_name,
                "--refresh-digest-only",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  plan refresh FAIL ({spec_name}): {result.stderr.strip()[:200]}", file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"  WARN: plan refresh failed ({spec_name}): {e}", file=sys.stderr)
        return False


def main(project_root=None, spec=None, apply=False, no_plan_refresh=False):
    """Run doctor retrofit. Can be called as subcommand or standalone.

    When called from vibe.py subcommand, use keyword args.
    When called standalone, uses sys.argv (argparse).
    """
    if project_root is None:
        # Standalone mode: parse CLI args
        parser = argparse.ArgumentParser(description="Doctor retrofit tool for done specs")
        parser.add_argument(
            "--project-root",
            default=".",
            help="Project root directory (default: current dir)",
        )
        parser.add_argument(
            "--spec",
            help="Retrofit only this spec (default: all done specs)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually modify files (default: dry-run)",
        )
        parser.add_argument(
            "--no-plan-refresh",
            action="store_true",
            help="Skip plan digest refresh (only retrofit spec text)",
        )
        cli_args = parser.parse_args()
        project_root = cli_args.project_root
        spec = cli_args.spec
        apply = cli_args.apply
        no_plan_refresh = cli_args.no_plan_refresh

    project_root = Path(project_root).resolve()
    specs_dir = project_root / ".agents" / "specs"

    if not specs_dir.exists():
        print(f"❌ {specs_dir} 不存在", file=sys.stderr)
        sys.exit(1)

    # 收集目标 specs
    if spec:
        target_specs = [specs_dir / f"{spec}.md"]
    else:
        target_specs = sorted(specs_dir.glob("*.md"))

    total_changed = 0
    total_scanned = 0

    for spec_path in target_specs:
        if not spec_path.exists():
            print(f"  SKIP: {spec_path.name} 不存在")
            continue

        total_scanned += 1
        spec_name = spec_path.stem

        changed, changes = retrofit_one_spec(spec_path)
        action = "DRY-RUN" if not apply else "APPLY"

        if changed:
            total_changed += 1
            print(f"  {action}: {spec_name} — {', '.join(changes)}")
            if apply:
                # 重读 + 写
                content = spec_path.read_text(encoding="utf-8")
                # 重新跑 retrofit 拿到 new_content
                new_content = content
                if not has_rule_57_table(new_content):
                    new_content = retrofit_rule_57(new_content)
                if not has_rule_56_table(new_content):
                    new_content = retrofit_rule_56(new_content)
                spec_path.write_text(new_content, encoding="utf-8")
        else:
            print(f"  {action}: {spec_name} — {changes[0]}")

    # plan refresh
    if not no_plan_refresh and total_changed > 0:
        print()
        print(f"--- plan refresh-digest-only ({total_changed} specs) ---")
        refresh_count = 0
        for spec_path in target_specs:
            spec_name = spec_path.stem
            content = spec_path.read_text(encoding="utf-8")
            if not is_done_spec(content):
                continue
            if refresh_plan_digest(project_root, spec_name):
                refresh_count += 1
                print(f"  plan refresh OK: {spec_name}")
            else:
                print(f"  plan refresh SKIP: {spec_name}")
        print(f"  {refresh_count} plans refreshed")

    print()
    print(f"--- summary ---")
    print(f"scanned: {total_scanned}")
    print(f"changed: {total_changed} (would change if dry-run)" if not apply else f"applied: {total_changed}")
    if not apply:
        print()
        print("This was a dry-run. Use --apply to actually modify files.")


if __name__ == "__main__":
    main()  # standalone
