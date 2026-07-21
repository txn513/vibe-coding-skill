#!/usr/bin/env python3
from __future__ import annotations
"""Prune stale rules and checklist items to prevent skill bloat.

Analyzes retro data to identify:
- Stale rules: never cited as useful in any retro
- Redundant items: overlapping checklist entries
- Low-value additions: auto-added items that never caught an issue
- Orphaned rules: rule files not linked to any real problem

Usage:
    python3 self_prune.py <project_root> --dry-run     # preview
    python3 self_prune.py <project_root> --apply        # execute
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from common import atomic_write, backup_file

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")
RULES_DIR = os.path.join(TEMPLATE_DIR, "rules")


def prune(project_root: str, dry_run: bool = True) -> list[dict]:
    """Analyze and suggest pruning actions."""
    project_root = os.path.abspath(project_root)
    results = []

    # 1. Gather retro data - what issues actually occurred?
    retros_data = _gather_retro_data(project_root)
    if not retros_data:
        print("📭 暂无回顾数据可供分析。")
        return []

    print(f"📊 分析 {len(retros_data)} 份回顾数据...\n")

    # 2. Extract current checklist items from SKILL.md
    checklist_items = _extract_all_checklist_items(project_root)

    # 3. Extract current rules
    rule_files = _list_rule_files(project_root)

    # 4. Build relevance map from retros
    relevance = _build_relevance_map(retros_data)

    # 5. Score each checklist item
    checklist_results = _score_checklist_items(checklist_items, relevance, retros_data)
    results.extend(checklist_results)

    # 6. Score each rule file
    rule_results = _score_rule_files(rule_files, relevance, retros_data)
    results.extend(rule_results)

    # 7. Detect redundancy
    redundancy_results = _detect_redundancy(checklist_items)
    results.extend(redundancy_results)

    # 8. Print and optionally apply
    _print_results(results)

    if not dry_run:
        applied = _apply_pruning(results, project_root)
        print(f"\n✅ 已执行 {len(applied)} 项瘦身操作。")
    else:
        print(f"\n💡 使用 --apply 执行瘦身。")

    return results


def _gather_retro_data(project_root: str) -> list[dict]:
    """Gather all retro content for analysis."""
    retros_dir = os.path.join(project_root, ".agents", "retros")
    if not os.path.exists(retros_dir):
        return []

    data = []
    # Sort by modification time: oldest first (lower weight in recency calc)
    retro_files = []
    for rf in os.listdir(retros_dir):
        if rf.endswith(".md") and rf != ".gitkeep":
            path = os.path.join(retros_dir, rf)
            retro_files.append((os.path.getmtime(path), rf))
    retro_files.sort(key=lambda x: x[0])  # oldest first

    for _, rf in retro_files:
        with open(os.path.join(retros_dir, rf)) as f:
            content = f.read()
            data.append({
                "name": rf.replace(".md", ""),
                "content": content,
                "went_well": _extract_items(content, "做对了什么"),
                "went_wrong": _extract_items(content, "做错了什么"),
                "builder_weaknesses": _extract_items(content, "反复出错"),
                "missing_rules": _extract_items(content, "需要补充的规则"),
                "missing_constraints": _extract_items(content, "哪些约束漏了"),
                "reviewer_missed": _extract_items(content, "漏掉的问题"),
            })
    return data


def _extract_all_checklist_items(project_root: str = None) -> list[dict]:
    """Extract all checklist items from both SKILL.md (global) and project-level custom.md.
    Tags items as 'builtin' (original), 'global' (from SKILL.md), or 'project' (from custom.md).
    Only 'project' items (auto-added) are candidates for pruning."""
    builtin_set = _get_builtin_items()
    items = []

    # 1. Global items from SKILL.md (always builtin or kept)
    if os.path.exists(SKILL_MD):
        with open(SKILL_MD) as f:
            content = f.read()

        pattern = r'### (.+?Checklist)\n```\n(.*?)```'
        for m in re.finditer(pattern, content, re.DOTALL):
            section_name = m.group(1).strip()
            body = m.group(2)
            if '□' not in body:
                continue
            for line in body.strip().split('\n'):
                line = line.strip()
                if line.startswith('□ '):
                    item_text = line[2:].strip()
                    items.append({
                        "text": item_text,
                        "section": section_name,
                        "original": line,
                        "builtin": item_text in builtin_set,
                        "source": "global",
                    })

    # 2. Project-level items from .agents/checklists/custom.md
    if project_root:
        custom_file = os.path.join(project_root, ".agents", "checklists", "custom.md")
        if os.path.exists(custom_file):
            with open(custom_file) as f:
                custom_content = f.read()
            # Parse sections: ## SectionName\n- [ ] item
            current_section = "Custom"
            for line in custom_content.split('\n'):
                line = line.strip()
                if line.startswith('## '):
                    current_section = line[3:].strip()
                elif line.startswith('- [ ] ') or line.startswith('- [x] '):
                    item_text = line[5:].strip()
                    if item_text:
                        items.append({
                            "text": item_text,
                            "section": current_section,
                            "original": line,
                            "builtin": False,
                            "source": "project",
                        })

    return items


def _get_builtin_items() -> set:
    """Global SKILL.md items are protected by their source tag, not a duplicated list."""
    return set()


BUILTIN_RULES = {"api.md", "db.md", "error.md", "security.md", "frontend.md"}


def _list_rule_files(project_root: str) -> list[dict]:
    """List project rules; only project-generated rules may be pruned."""
    project_rules = os.path.join(project_root, ".agents", "rules")
    if not os.path.exists(project_rules):
        return []

    rules = []
    for rf in sorted(os.listdir(project_rules)):
        if rf.endswith(".md"):
            path = os.path.join(project_rules, rf)
            with open(path) as f:
                content = f.read()
            is_auto = "自动生成自回顾分析" in content
            rules.append({
                "filename": rf,
                "path": path,
                "auto_generated": is_auto,
                "builtin": rf in BUILTIN_RULES,
                "content": content,
            })
    return rules


def _build_relevance_map(retros: list[dict]) -> dict:
    """Build a map of which topics are relevant, with recency weighting.
    Recent retros (newer) have higher weight than older ones."""
    all_weaknesses = []
    all_missing = []
    all_wrong = []

    total = len(retros)
    for idx, r in enumerate(retros):
        # Recency weight: newest = 1.0, oldest = 0.3 + (0.7 * idx/total)
        weight = 0.3 + (0.7 * (idx + 1) / total) if total > 1 else 1.0
        for w in r["builder_weaknesses"]:
            all_weaknesses.append((w, weight))
        for m in r["missing_rules"]:
            all_missing.append((m, weight))
        for w in r["went_wrong"]:
            all_wrong.append((w, weight))

    # Create weighted keyword relevance scores
    keywords = Counter()
    for w, weight in all_weaknesses + all_wrong:
        for kw in _extract_keywords(w):
            keywords[kw] += weight
    for m, weight in all_missing:
        for kw in _extract_keywords(m):
            keywords[kw] += weight * 2

    return {
        "weakness_keywords": keywords,
        "weakness_count": Counter(w for w, _ in all_weaknesses),
        "missing_count": Counter(m for m, _ in all_missing),
        "total_retros": total,
    }


def _score_checklist_items(items: list[dict], relevance: dict, retros: list[dict]) -> list[dict]:
    """Score each checklist item by directly matching its text against retro data.
    Uses recency-weighted counting: recent issues matter more than old ones."""
    results = []
    total = relevance["total_retros"]

    # Build direct match index from all retro items, with recency weighting
    retro_item_weights = {}
    for idx, r in enumerate(retros):
        weight = 0.3 + (0.7 * (idx + 1) / total) if total > 1 else 1.0
        all_items = (r.get("builder_weaknesses", []) +
                     r.get("missing_rules", []) +
                     r.get("missing_constraints", []) +
                     r.get("reviewer_missed", []) +
                     r.get("went_wrong", []))
        for ri in all_items:
            retro_item_weights[ri] = retro_item_weights.get(ri, 0) + weight

    for item in items:
        text = item["text"]
        score = retro_item_weights.get(text, 0)
        # Fuzzy: check if any retro item contains this text or vice versa
        if score == 0:
            for ri, w in retro_item_weights.items():
                if text[:15] in ri or ri in text:
                    score += w * 0.5
        normalized = score / max(total, 1)

        status = "keep"
        if item.get("builtin", False):
            status = "builtin"
        elif item.get("source") == "global":
            status = "builtin"
        elif item.get("source") == "project" and normalized == 0 and total >= 3:
            status = "stale"
        elif item.get("source") == "project" and normalized < 0.3 and total >= 3:
            status = "low_value"

        results.append({
            "type": "checklist",
            "section": item["section"],
            "text": text,
            "relevance_score": round(normalized, 3),
            "related_retros": round(score, 3),
            "status": status,
            "original": item["original"],
            "source": item.get("source", "unknown"),
        })

    return results

def _score_rule_files(rules: list[dict], relevance: dict, retros: list[dict]) -> list[dict]:
    """Score each rule file. Auto-generated rules with 0 relevance are candidates."""
    results = []
    total = relevance["total_retros"]

    for rule in rules:
        name = rule["filename"].replace(".md", "")
        keywords = _extract_keywords(name + " " + rule["content"][:200])

        score = 0
        for kw in keywords:
            score += relevance["weakness_keywords"].get(kw, 0)
            score += relevance["missing_count"].get(kw, 0) * 2  # Missing rules weight higher

        normalized = score / max(total, 1)

        status = "keep"
        # Builtin rules are never pruned
        if rule.get("builtin", False):
            status = "builtin"
        elif rule["auto_generated"] and normalized == 0 and total >= 2:
            status = "orphaned"
        elif normalized == 0 and total >= 4:
            status = "stale"

        results.append({
            "type": "rule",
            "filename": rule["filename"],
            "auto_generated": rule["auto_generated"],
            "relevance_score": normalized,
            "related_retros": score,
            "status": status,
        })

    return results


def _detect_redundancy(items: list[dict]) -> list[dict]:
    """Detect checklist items that are nearly identical."""
    results = []
    checked = set()

    for i, item1 in enumerate(items):
        if i in checked:
            continue
        # Skip the "check custom.md" reference line - it's intentionally duplicated
        if "custom.md" in item1["text"]:
            continue
        for j, item2 in enumerate(items):
            if j <= i or j in checked:
                continue
            if "custom.md" in item2["text"]:
                continue
            similarity = _text_similarity(item1["text"], item2["text"])
            if similarity > 0.7:
                results.append({
                    "type": "redundancy",
                    "item1": item1["text"],
                    "item2": item2["text"],
                    "section1": item1["section"],
                    "section2": item2["section"],
                    "similarity": similarity,
                    "status": "redundant",
                    "suggestion": f"合并: '{item1['text'][:40]}...' + '{item2['text'][:40]}...' → 保留更通用的那一条",
                })
                checked.add(j)

    return results


def _print_results(results: list[dict]) -> None:
    """Print pruning analysis."""
    if not results:
        print("✅ 未发现需要瘦身的项目本地规则。")
        return

    by_status = defaultdict(list)
    for r in results:
        by_status[r["status"]].append(r)

    print("🔍 项目本地规则瘦身分析")
    print("═" * 50)

    if "stale" in by_status:
        print(f"\n🟤 过期项 ({len(by_status['stale'])}): 从未在回顾中被提及")
        for r in by_status["stale"]:
            if r["type"] == "checklist":
                print(f"   [{r['section']}] □ {r['text']}")
            elif r["type"] == "rule":
                print(f"   规则文件: {r['filename']}")

    if "orphaned" in by_status:
        print(f"\n👻 孤立项 ({len(by_status['orphaned'])}): 自动生成但无实际关联")
        for r in by_status["orphaned"]:
            print(f"   规则文件: {r['filename']} (自动生成)")

    if "low_value" in by_status:
        print(f"\n🟡 低价值项 ({len(by_status['low_value'])}): 相关性 < 0.3")
        for r in by_status["low_value"]:
            if r["type"] == "checklist":
                print(f"   [{r['section']}] □ {r['text']} (分数: {r['relevance_score']:.1f})")

    if "redundant" in by_status:
        print(f"\n🟠 重复项 ({len(by_status['redundant'])}): 相似度 > 70%")
        for r in by_status["redundant"]:
            print(f"   '{r['item1'][:50]}...'")
            print(f"   '{r['item2'][:50]}...'")
            print(f"   → {r['suggestion']}")
            print()

    # Summary
    removable = [r for r in results if r["status"] in ("stale", "orphaned")]
    reviewable = [r for r in results if r["status"] in ("low_value", "redundant")]

    print(f"\n📊 建议:")
    print(f"   可安全删除: {len(removable)} 项")
    print(f"   需人工判断: {len(reviewable)} 项")
    if removable:
        print(f"   预计节省: ~{len(removable) * 50} tokens / 会话")


def _apply_pruning(results: list[dict], project_root: str = None) -> list[dict]:
    """Apply pruning to project-local files while preserving recoverable archives."""
    applied = []
    archive_dir = (
        os.path.join(project_root, ".agents", "archive", "prune")
        if project_root
        else ""
    )

    # Prune project-level custom checklist
    if project_root:
        custom_file = os.path.join(project_root, ".agents", "checklists", "custom.md")
        custom_modified = False
        custom_content = ""
        if os.path.exists(custom_file):
            with open(custom_file) as f:
                custom_content = f.read()

        for r in results:
            if r["status"] in ("stale",) and r["type"] == "checklist" and r.get("source") == "project":
                original = r.get("original", f"- [ ] {r['text']}")
                if original in custom_content:
                    custom_content = custom_content.replace(f"{original}\n", "")
                    custom_content = custom_content.replace(f"\n{original}", "")
                    custom_content = custom_content.replace(original, "")
                    print(f"   🗑️  删除: [{r['section']}] {r['text']}")
                    applied.append(r)
                    custom_modified = True

        if custom_modified:
            backup_file(custom_file, os.path.join(archive_dir, "checklists"))
            atomic_write(custom_file, custom_content)

    # Prune project-level auto-generated rule files
    for r in results:
        if r["status"] in ("stale", "orphaned") and r["type"] == "rule":
            if project_root:
                path = os.path.join(project_root, ".agents", "rules", r["filename"])
                if os.path.exists(path):
                    # Only delete auto-generated project rules, not builtin ones
                    with open(path) as f:
                        if "自动生成自回顾分析" in f.read():
                            destination = backup_file(
                                path, os.path.join(archive_dir, "rules")
                            )
                            if destination:
                                os.unlink(path)
                            print(f"   📦 归档项目规则: {r['filename']}")
                            applied.append(r)

    return applied


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    # Remove common stop words and extract 2-3 char+ keywords
    stop = {"的", "了", "在", "是", "有", "和", "也", "都", "要", "就", "会",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "不", "未", "已", "对", "被", "把", "从", "到", "与", "或"}

    # Extract Chinese and English words
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text.lower())
    return [w for w in words if w not in stop]


def _text_similarity(a: str, b: str) -> float:
    """Simple Jaccard-like similarity between two short texts."""
    set_a = set(_extract_keywords(a))
    set_b = set(_extract_keywords(b))
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _extract_items(content: str, field: str) -> list[str]:
    """Extract list items from a field in retro content."""
    items = []
    inline_pattern = rf"(?:^|\n)\s*-?\s*\*\*{re.escape(field)}\*\*:?\s*(.+?)(?:\n|$)"
    for m in re.finditer(inline_pattern, content, re.MULTILINE):
        item = m.group(1).strip()
        if item and len(item) > 3 and not any(x in item for x in ("(什么", "(Agent", "(哪些")):
            items.append(item)
    return items


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Prune stale rules and checklist items")
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--apply", action="store_true", help="Apply pruning (default: dry-run)")
    args = p.parse_args()
    prune(os.path.abspath(args.project_root), dry_run=not args.apply)
