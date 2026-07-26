#!/usr/bin/env python3
from __future__ import annotations
"""Initialize docs/ directory skeleton for a project (R-D-87).

Scans .agents/specs/, .agents/changelogs/, .agents/retros/, AGENTS.md,
and the repo's manifest files (pyproject.toml / package.json) to
auto-generate docs/README.md + per-document skeleton stubs. Each
generated file gets frontmatter (last_updated, verified_at, status)
so stale-doc detection works.

Idempotent: re-running only creates missing files. Existing files
are NOT overwritten.

Usage:
    python3 docs_init.py <project_root> --dry-run     # preview
    python3 docs_init.py <project_root>               # execute
"""

import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def _frontmatter(status: str = "NEEDS_UPDATE") -> str:
    return (
        "---\n"
        f"last_updated: {_today()}\n"
        f"verified_at: {_today()}\n"
        f"status: {status}\n"
        "---\n\n"
    )


def _detect_modules(project_root: str) -> list[str]:
    specs_dir = os.path.join(project_root, ".agents", "specs")
    modules: set[str] = set()
    if not os.path.isdir(specs_dir):
        return []
    for spec_file in sorted(glob.glob(os.path.join(specs_dir, "*.md"))):
        try:
            with open(spec_file, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        for match in re.finditer(r"^[\s-]+([\w./-]+\.\w+)", content, re.MULTILINE):
            filepath = match.group(1)
            parts = filepath.split("/")
            if len(parts) >= 2:
                candidate = parts[1] if parts[0] in {"backend", "frontend", "src", "lib"} else parts[0]
                if candidate not in {"tests", "docs", "__pycache__", ".git", "node_modules"}:
                    modules.add(candidate)
    return sorted(modules)


def _extract_tech_stack(project_root: str) -> str:
    lines: list[str] = []
    pyproject = os.path.join(project_root, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, encoding="utf-8") as f:
                content = f.read()
            deps_match = re.search(r"\[project\][\s\S]*?dependencies\s*=\s*\[([\s\S]*?)\]", content)
            if deps_match:
                for dep in re.findall(r'"([^"]+)"', deps_match.group(1)):
                    lines.append(f"- {dep}")
        except OSError:
            pass
    package_json = os.path.join(project_root, "package.json")
    if os.path.exists(package_json):
        try:
            with open(package_json, encoding="utf-8") as f:
                pkg = json.load(f)
            for dep in (pkg.get("dependencies") or {}).keys():
                lines.append(f"- {dep}")
            for dep in (pkg.get("devDependencies") or {}).keys():
                lines.append(f"- (dev) {dep}")
        except (OSError, json.JSONDecodeError):
            pass
    if not lines:
        agents_md = os.path.join(project_root, "AGENTS.md")
        if os.path.exists(agents_md):
            try:
                with open(agents_md, encoding="utf-8") as f:
                    content = f.read()
                m = re.search(r"##\s*技术栈\s*\n([\s\S]*?)(?=\n##|\Z)", content)
                if m:
                    lines.append(m.group(1).strip())
            except OSError:
                pass
    return "\n".join(lines) if lines else "<!-- NEEDS_REVIEW: auto-extract failed, fill manually -->"


def _extract_glossary(project_root: str) -> list[tuple[str, int]]:
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.isdir(retros_dir):
        return []
    counter: Counter[str] = Counter()
    for retro_file in sorted(glob.glob(os.path.join(retros_dir, "*.md"))):
        try:
            with open(retro_file, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        for term in re.findall(r"[\u4e00-\u9fff]{2,5}", content):
            counter[term] += 1
        for term in re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", content):
            counter[term] += 1
    return [(t, c) for t, c in counter.most_common(20) if c >= 2]


def _extract_changelog_summary(project_root: str) -> str:
    changelog_dir = os.path.join(project_root, ".agents", "changelogs")
    if not os.path.isdir(changelog_dir):
        return "<!-- NEEDS_AUTHOR: no changelog, fill manually -->"
    files = sorted(glob.glob(os.path.join(changelog_dir, "*.md")), reverse=True)
    summaries = []
    for f in files[:3]:
        try:
            with open(f, encoding="utf-8") as fp:
                content = fp.read()
            m = re.search(r"^#+\s+(.+)", content, re.MULTILINE)
            if m:
                summaries.append(f"- {m.group(1).strip()}")
        except OSError:
            continue
    return "\n".join(summaries) if summaries else "<!-- NEEDS_AUTHOR: changelog content empty -->"


def _doc_index(modules: list[str]) -> str:
    body = "# 项目文档索引\n\n"
    body += "> auto-generated " + _today() + ". Re-run `vibe docs-init` to refresh, `vibe tidy --apply` to clean up.\n\n"
    body += "## 项目全景\n\n"
    body += "- [项目简介](overview.md)\n"
    body += "- [技术栈](tech-stack.md)\n"
    body += "- [架构](architecture.md)\n"
    body += "- [术语表](glossary.md)\n\n"
    if modules:
        body += "## 模块文档\n\n"
        for m in modules:
            body += f"- [modules/{m}.md](modules/{m}.md)\n"
        body += "\n"
    body += "## 决策记录 (ADR)\n\n"
    body += "- [adr/](adr/) — 关键选型与决策\n\n"
    body += "## 维护约定\n\n"
    body += "- 每个文件 frontmatter 含 `last_updated` / `status`\n"
    body += "- `status: CURRENT` 表示近期 (≤30 天) 校验过\n"
    body += "- `status: NEEDS_UPDATE` 内容可能过时, 需复查\n"
    body += "- `status: NEEDS_AUTHOR` 占位, 需作者填充\n"
    return _frontmatter("CURRENT") + body


def _doc_overview(changelog_summary: str) -> str:
    body = "# 项目简介\n\n"
    body += "> 1-page summary. `status: NEEDS_AUTHOR` means auto-generated draft, refine manually.\n\n"
    body += "## 最近变更摘要\n\n"
    body += changelog_summary + "\n\n"
    body += "## 项目定位\n\n"
    body += "<!-- NEEDS_AUTHOR: describe what problem this project solves, for whom -->\n\n"
    body += "## 主要功能\n\n"
    body += "<!-- NEEDS_AUTHOR: list core feature modules -->\n"
    return _frontmatter("NEEDS_AUTHOR") + body


def _doc_tech_stack(tech_stack: str) -> str:
    body = "# 技术栈\n\n"
    body += "> auto-extracted from pyproject.toml / package.json / AGENTS.md. Refine with rationale.\n\n"
    body += "## 依赖\n\n"
    body += tech_stack + "\n\n"
    body += "## 选型理由\n\n"
    body += "<!-- NEEDS_AUTHOR: why X over Y for key dependencies -->\n"
    return _frontmatter("NEEDS_REVIEW") + body


def _doc_architecture() -> str:
    body = "# 架构\n\n"
    body += "> C4 Level 1-2: system boundary + containers + components. Placeholder by `vibe docs-init`.\n\n"
    body += "## 系统边界 (Level 1)\n\n"
    body += "```\n[Client] -> [API] -> [DB]\n```\n\n"
    body += "<!-- NEEDS_AUTHOR: draw with C4 tool or mermaid -->\n\n"
    body += "## 容器 (Level 2)\n\n"
    body += "<!-- NEEDS_AUTHOR: list main services/processes and responsibilities -->\n\n"
    body += "## 主要组件 (Level 3)\n\n"
    body += "<!-- NEEDS_AUTHOR: key module internal structure -->\n"
    return _frontmatter("NEEDS_AUTHOR") + body


def _doc_module(module: str) -> str:
    body = f"# 模块: {module}\n\n"
    body += "> auto-generated draft from related specs. Refine manually.\n\n"
    body += "## 职责\n\n"
    body += f"<!-- NEEDS_AUTHOR: what does {module} module do -->\n\n"
    body += "## 公共 API / 接口\n\n"
    body += "<!-- NEEDS_AUTHOR: list public functions/classes/routes -->\n\n"
    body += "## 关键文件\n\n"
    body += f"<!-- NEEDS_AUTHOR: core files in {module} + line ranges -->\n\n"
    body += "## 已知坑点 / 决策\n\n"
    body += "<!-- NEEDS_AUTHOR: common bugs / history decisions / ADR links -->\n\n"
    body += "## 关联 Spec\n\n"
    body += "<!-- specs that touch this module will be auto-listed on next `vibe docs-init` -->\n"
    return _frontmatter("NEEDS_UPDATE") + body


def _doc_glossary(terms: list[tuple[str, int]]) -> str:
    body = "# 术语表\n\n"
    body += "> auto-extracted from retros (freq >= 2). Manually filter to business terms.\n\n"
    if terms:
        body += "## 候选术语 (by frequency)\n\n"
        body += "| 术语 | 次数 |\n|------|----------|\n"
        for term, count in terms:
            body += f"| {term} | {count} |\n"
        body += "\n<!-- NEEDS_AUTHOR: remove irrelevant, add definitions -->\n"
    else:
        body += "<!-- NEEDS_AUTHOR: no candidates (retros too few), add manually -->\n"
    return _frontmatter("NEEDS_AUTHOR") + body


def _find_docs_actions(project_root: str) -> list[dict]:
    actions = []
    modules = _detect_modules(project_root)
    tech_stack = _extract_tech_stack(project_root)
    changelog_summary = _extract_changelog_summary(project_root)
    glossary_terms = _extract_glossary(project_root)

    docs_dir = os.path.join(project_root, "docs")
    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "README.md"),
        "content": _doc_index(modules),
        "reason": "docs/ index (machine-readable TOC)",
    })
    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "overview.md"),
        "content": _doc_overview(changelog_summary),
        "reason": "project summary (from changelog)",
    })
    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "tech-stack.md"),
        "content": _doc_tech_stack(tech_stack),
        "reason": "tech stack (from pyproject.toml/package.json)",
    })
    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "architecture.md"),
        "content": _doc_architecture(),
        "reason": "architecture (placeholder, draw with C4)",
    })
    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "glossary.md"),
        "content": _doc_glossary(glossary_terms),
        "reason": "glossary (from retros)",
    })

    modules_dir = os.path.join(docs_dir, "modules")
    for m in modules:
        actions.append({
            "action": "create_if_missing",
            "path": os.path.join(modules_dir, f"{m}.md"),
            "content": _doc_module(m),
            "reason": f"module {m} doc",
        })

    actions.append({
        "action": "create_if_missing",
        "path": os.path.join(docs_dir, "adr", "README.md"),
        "content": _frontmatter("CURRENT") + "# 决策记录 (ADR)\n\n"
        + "> 关键选型与决策. 命名: NNNN-<slug>.md, N 从 0001 开始.\n\n"
        + "## 模板\n\n"
        + "每个 ADR 必含:\n"
        + "- **背景**: 为什么需要决策\n"
        + "- **选项**: 考虑了哪些方案\n"
        + "- **决策**: 最终选了哪个, 为什么\n"
        + "- **后果**: 接受此决策后的 trade-offs\n",
        "reason": "ADR directory readme",
    })

    return actions


def docs_init(project_root: str, dry_run: bool = True) -> list[dict]:
    actions = _find_docs_actions(project_root)
    todo = [a for a in actions if not os.path.exists(a["path"])]

    if not todo:
        print(f"✅ docs/ already initialized ({len(actions)} files exist). Re-run skips all.")
        return []

    print(f"📚 计划创建 {len(todo)} 个 docs/ 文件 (跳过 {len(actions) - len(todo)} 个已存在):\n")
    for i, act in enumerate(todo, 1):
        rel = os.path.relpath(act["path"], project_root)
        print(f"  {i}. {rel}")
        print(f"     原因: {act['reason']}")
        print()

    if dry_run:
        print("ℹ️  dry-run. Execute: vibe docs-init <project_root> --apply")
        return []

    created = 0
    for act in todo:
        os.makedirs(os.path.dirname(act["path"]), exist_ok=True)
        with open(act["path"], "w", encoding="utf-8") as f:
            f.write(act["content"])
        created += 1
    print(f"✅ created {created} docs/ files.")
    print()
    print("Next:")
    print("  1. Edit overview.md / architecture.md (NEEDS_AUTHOR sections)")
    print("  2. Run `vibe tidy --apply` to verify docs structure")
    print("  3. On spec done: update docs/modules/<m>.md (R-D-87)")
    return todo


def main() -> None:
    p = argparse.ArgumentParser(
        prog="vibe.py docs-init",
        description="Initialize docs/ directory skeleton (R-D-87)",
    )
    p.add_argument("project_root")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--apply", action="store_true", help="Actually create files")
    args = p.parse_args()
    result = docs_init(args.project_root, dry_run=not args.apply)
    sys.exit(0)


if __name__ == "__main__":
    main()
