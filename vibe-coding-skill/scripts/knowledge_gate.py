#!/usr/bin/env python3
"""Classify knowledge ownership and audit the Skill boundary."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

KINDS = {"governance", "project", "external"}

PROJECT_TARGETS = (
    ".agents/",
    "AGENTS.md",
)

GOVERNANCE_MARKERS = (
    "gate",
    "workflow",
    "risk",
    "evidence",
    "review",
    "status",
    "audit",
    "门禁",
    "流程",
    "风险",
    "证据",
    "审查",
    "状态",
    "治理",
)

EXTERNAL_MARKERS = (
    "external tool",
    "integration",
    "github",
    "gitlab",
    "ci/cd",
    "monitoring platform",
    "scanner",
    "外部工具",
    "外部系统",
    "集成",
    "监控平台",
    "扫描器",
)

PROJECT_MARKERS = (
    "project rule",
    "project-specific",
    "business rule",
    "architecture decision",
    "项目规则",
    "项目特有",
    "业务规则",
    "架构决策",
    "接口",
    "数据表",
)


def classify_knowledge(text: str, target: str = "") -> dict:
    """Classify a candidate as governance, project knowledge, or external capability."""
    value = f"{text}\n{target}".lower()
    normalized_target = target.replace("\\", "/").lstrip("./")

    if any(normalized_target.startswith(item.lstrip("./")) for item in PROJECT_TARGETS):
        return {
            "kind": "project",
            "confidence": "high",
            "reason": f"目标位于项目本地治理目录: {target}",
        }
    if any(marker in value for marker in EXTERNAL_MARKERS):
        return {
            "kind": "external",
            "confidence": "medium",
            "reason": "内容描述外部平台、工具或集成能力",
        }
    if any(marker in value for marker in PROJECT_MARKERS):
        return {
            "kind": "project",
            "confidence": "medium",
            "reason": "内容包含项目事实、业务规则或具体技术决策",
        }
    if any(marker in value for marker in GOVERNANCE_MARKERS):
        return {
            "kind": "governance",
            "confidence": "medium",
            "reason": "内容描述跨项目适用的流程、门禁或证据机制",
        }
    return {
        "kind": "project",
        "confidence": "low",
        "reason": "无法证明其跨项目通用，按项目知识保守处理",
    }


def require_project_destination(destination: str | Path, project_root: str | Path) -> Path:
    """Reject self-upgrade writes outside the project's .agents directory."""
    target = Path(destination).resolve()
    allowed = (Path(project_root).resolve() / ".agents").resolve()
    try:
        target.relative_to(allowed)
    except ValueError as error:
        raise ValueError(f"自升级只能写入项目 .agents/: {target}") from error
    return target


def _skill_files(skill_root: Path) -> list[Path]:
    paths = [skill_root / "SKILL.md"]
    for pattern in (
        "agents/*.yaml",
        "references/*.md",
        "scripts/*.py",
        "templates/*.md",
        "templates/rules/*.md",
    ):
        paths.extend(sorted(skill_root.glob(pattern)))
    return [path for path in paths if path.is_file()]


def _project_identifiers(project_root: Path | None) -> set[str]:
    if project_root is None:
        return set()
    identifiers = {project_root.name}
    agents = project_root / "AGENTS.md"
    if agents.exists():
        first_heading = re.search(
            r"^#\s+(.+?)\s*$", agents.read_text(encoding="utf-8"), re.MULTILINE
        )
        if first_heading:
            identifiers.add(first_heading.group(1).strip())
    return {item for item in identifiers if len(item) >= 8}


def audit_skill(skill_root: str | Path, project_root: str | Path | None = None) -> dict:
    """Audit deterministic contamination signals without guessing business meaning."""
    root = Path(skill_root).resolve()
    project = Path(project_root).resolve() if project_root else None
    issues = []
    warnings = []
    identifiers = _project_identifiers(project)
    unix_home_pattern = "/" + r"(?:Users|home)/[^\s`'\"]+"
    windows_home_pattern = r"[A-Za-z]:\\" + r"Users\\[^\s'\"]+"

    for path in _skill_files(root):
        content = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(root))
        for line_number, line in enumerate(content.splitlines(), start=1):
            if re.search(unix_home_pattern, line):
                issues.append(f"{relative}:{line_number}: contains an absolute user path")
            if re.search(windows_home_pattern, line):
                issues.append(f"{relative}:{line_number}: contains an absolute user path")
            for identifier in identifiers:
                if identifier in line and identifier not in {root.name, "vibe-coding"}:
                    issues.append(
                        f"{relative}:{line_number}: contains project identifier {identifier!r}"
                    )
            if re.search(r"https?://(?!example\.(?:com|org|net)\b)[^\s)>]+", line):
                warnings.append(f"{relative}:{line_number}: review concrete external URL")
            if re.search(
                r"^\s*(?:SELECT\b.+\bFROM\b|INSERT\s+INTO\b|"
                r"UPDATE\s+[A-Za-z0-9_.]+\s+SET\b|DELETE\s+FROM\b)",
                line,
                re.I,
            ):
                warnings.append(f"{relative}:{line_number}: review embedded SQL detail")
            if re.search(r"(?:/api/|/v[0-9]+/)[A-Za-z0-9_./{}:-]+", line):
                warnings.append(f"{relative}:{line_number}: review concrete endpoint detail")

    return {
        "skill_root": str(root),
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
    }


def print_audit(result: dict) -> None:
    print(f"Skill boundary audit: {result['skill_root']}")
    if result["issues"]:
        for issue in result["issues"]:
            print(f"ERROR: {issue}")
    else:
        print("No deterministic boundary violations found.")
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify and audit Skill knowledge ownership")
    sub = parser.add_subparsers(dest="operation", required=True)

    classify = sub.add_parser("classify")
    classify.add_argument("text")
    classify.add_argument("--target", default="")

    audit = sub.add_parser("audit")
    audit.add_argument("skill_root")
    audit.add_argument("--project-root")

    args = parser.parse_args()
    if args.operation == "classify":
        result = classify_knowledge(args.text, args.target)
        print(f"归属: {result['kind']}")
        print(f"置信度: {result['confidence']}")
        print(f"理由: {result['reason']}")
        return

    result = audit_skill(args.skill_root, args.project_root)
    print_audit(result)
    raise SystemExit(1 if result["issues"] else 0)


if __name__ == "__main__":
    main()
