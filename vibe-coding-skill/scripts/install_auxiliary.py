#!/usr/bin/env python3
"""Install a Vibe Coding auxiliary Skill by symlinking it into ~/.codex/skills/.

The core Skill uses this to pull sibling auxiliaries (e.g. vibe-coding-reviewer)
on demand. The user never names an auxiliary explicitly; the core surfaces a
suggestion and runs this command internally.

Convention: auxiliaries live next to the core in the same monorepo, named
``vibe-coding-<role>``. The source path is resolved by walking up from this
script to find a sibling directory matching that pattern, or by accepting an
explicit ``--suite-root``.

Symlink is preferred over copy: edits to the monorepo stay in sync, and the
source of truth remains one place.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

AUX_PREFIX = "vibe-coding-"
CORE_NAMES = {"vibe-coding", "vibe-coding-skill"}


def _suite_root_from_here() -> str | None:
    """Guess the suite (monorepo) root from this script's location.

    Layout assumed: <suite>/vibe-coding-skill/scripts/install_auxiliary.py
    Returns the suite directory or None if it cannot be inferred.
    """
    here = Path(__file__).resolve()
    # scripts/ -> vibe-coding-skill/ -> suite/
    candidate = here.parent.parent.parent
    if (candidate / "vibe-coding-skill" / "SKILL.md").exists():
        return str(candidate)
    return None


def _find_auxiliary_dir(name: str, suite_root: str) -> Path:
    """Resolve the on-disk path to the auxiliary Skill directory.

    The auxiliary directory must be named ``<name>`` and live directly under
    the suite root. We also accept the legacy ``vibe-coding-skill`` placement
    by special-casing the core name.
    """
    if suite_root == "<inferred>":
        resolved = _suite_root_from_here()
        if not resolved:
            raise FileNotFoundError(
                "无法推断 suite 根目录；请通过 --suite-root 显式传入。"
            )
        suite_root = resolved
    aux_dir = Path(suite_root) / name
    if not aux_dir.is_dir():
        raise FileNotFoundError(f"未找到辅助 Skill 目录: {aux_dir}")
    if not (aux_dir / "SKILL.md").exists():
        raise FileNotFoundError(f"目录缺少 SKILL.md，不是合法 Skill: {aux_dir}")
    return aux_dir


def _iter_siblings(suite_root: str) -> list[Path]:
    root = Path(suite_root)
    siblings: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not child.name.startswith(AUX_PREFIX):
            continue
        if child.name in CORE_NAMES:
            continue
        if (child / "SKILL.md").exists():
            siblings.append(child)
    return siblings


def _target_path(name: str, codex_home: str) -> Path:
    return Path(codex_home) / "skills" / name


def _already_installed(target: Path) -> str | None:
    if not target.exists() and not target.is_symlink():
        return None
    if target.is_symlink():
        resolved = target.resolve()
        return f"已是符号链接 → {resolved}"
    return f"目录已存在（不是符号链接），请先手动检查: {target}"


def _install_one(
    name: str,
    suite_root: str,
    codex_home: str,
    force: bool,
) -> tuple[bool, str]:
    """Install a single auxiliary. Returns (changed, message)."""
    aux_dir = _find_auxiliary_dir(name, suite_root)
    target = _target_path(name, codex_home)
    target.parent.mkdir(parents=True, exist_ok=True)

    state = _already_installed(target)
    if state:
        if target.is_symlink() and target.resolve() == aux_dir.resolve():
            return False, f"✓ {name} 已正确链接到 {aux_dir}"
        if not force:
            return False, f"⚠ {name}: {state}（用 --force 覆盖）"
        # Force: remove existing entry. Symlinks use unlink; real dirs need rmtree.
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            import shutil
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    os.symlink(str(aux_dir), str(target))
    return True, f"🔗 {name} → {target} → {aux_dir}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install Vibe Coding auxiliary Skills into ~/.codex/skills/"
    )
    parser.add_argument(
        "name",
        nargs="?",
        default="",
        help="辅助 Skill 名（如 vibe-coding-reviewer）；省略时配合 --all 扫描同级",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="扫描 suite 根目录，安装所有 vibe-coding-* 辅助",
    )
    parser.add_argument(
        "--suite-root",
        default="<inferred>",
        help="套件根目录（包含 vibe-coding-skill/ 与各辅助的 monorepo 根）",
    )
    parser.add_argument(
        "--codex-home",
        default=os.path.expanduser("~/.codex"),
        help="Codex 配置目录（默认 ~/.codex）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="已存在链接/目录时强制覆盖",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅列出可安装的辅助，不实际安装",
    )
    args = parser.parse_args()

    suite_root = (
        args.suite_root
        if args.suite_root != "<inferred>"
        else (_suite_root_from_here() or "<inferred>")
    )

    if args.list:
        if suite_root == "<inferred>":
            print("❌ 无法推断 suite 根目录，请使用 --suite-root")
            sys.exit(1)
        for sibling in _iter_siblings(suite_root):
            print(f"  • {sibling.name}")
        return

    if not args.all and not args.name:
        parser.error("需要提供 name 或 --all")
        if suite_root == "<inferred>":
            print("❌ 无法推断 suite 根目录，请使用 --suite-root")
            sys.exit(1)
        for sibling in _iter_siblings(suite_root):
            print(f"  • {sibling.name}")
        return

    names = (
        [s.name for s in _iter_siblings(suite_root)]
        if args.all
        else [args.name]
    )
    if not names:
        print("⚠ 没有发现可安装的辅助 Skill。")
        return

    changed = 0
    for name in names:
        ok, msg = _install_one(name, suite_root, args.codex_home, args.force)
        print(msg)
        if ok:
            changed += 1
    print(f"\n完成: {changed}/{len(names)} 个变更。")


if __name__ == "__main__":
    main()
