#!/usr/bin/env python3
from __future__ import annotations
"""Security pattern scanner — detect common credential leakage patterns.

Governance upgrade candidate 2026-07-12: OAuth credential in URL query.
RFC 6749 §2.3.1 requires confidential client credentials (client_secret,
refresh_token, authorization_code) to be sent in HTTP POST body, NOT URL query.

Usage:
    python3 security_scan.py <project_root> [--fix]

Exit codes:
    0 — no violations
    1 — violations found (CI blocking)
"""

import argparse
import ast
import os
import re
from pathlib import Path


# RFC 6749 §2.3.1 sensitive fields that MUST NOT be in URL query
SENSITIVE_KEYS = {
    "client_secret", "refresh_token", "code", "access_token",
    "id_token", "password",
}
# Pattern for suffix-matching: anything ending with _secret, _token, _password
SENSITIVE_SUFFIXES = ("_secret", "_token", "_password")
# Whitelist: fields allowed in URL query per RFC 6749
ALLOWED_IN_URL = {"client_id"}


def _is_sensitive_key(key: str) -> bool:
    """Check if a dict key contains sensitive OAuth credential material."""
    if key in ALLOWED_IN_URL:
        return False
    if key in SENSITIVE_KEYS:
        return True
    return key.endswith(SENSITIVE_SUFFIXES)


class OAuthUrlQueryVisitor(ast.NodeVisitor):
    """AST visitor: detect `requests.post(url, params={"client_secret": ...})`."""

    def __init__(self, source: str, filepath: str):
        self.source = source
        self.filepath = filepath
        self.findings: list[dict] = []

    def _line(self, node: ast.AST) -> int:
        return getattr(node, "lineno", 0)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Match: func.post(url, params={...})
        if not isinstance(node.func, ast.Attribute):
            return
        if node.func.attr not in ("post", "get", "put", "patch", "delete"):
            return

        # Look for params= keyword with a Dict value
        for kw in node.keywords:
            if kw.arg != "params":
                continue
            if not isinstance(kw.value, ast.Dict):
                continue
            # Check keys in the dict
            sensitive_found = []
            for k in kw.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if _is_sensitive_key(k.value):
                        sensitive_found.append(k.value)
                elif isinstance(k, ast.Str):  # Python < 3.8 compat
                    if _is_sensitive_key(k.s):
                        sensitive_found.append(k.s)

            if sensitive_found:
                self.findings.append({
                    "line": self._line(node),
                    "method": node.func.attr,
                    "sensitive_keys": sensitive_found,
                    "snippet": self.source.splitlines()[self._line(node) - 1].strip()[:120],
                })


def scan_file(filepath: str) -> list[dict]:
    """Scan a single Python file for OAuth credential-in-URL violations."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = OAuthUrlQueryVisitor(source, filepath)
    visitor.visit(tree)
    return visitor.findings


def scan_project(project_root: str) -> list[dict]:
    """Scan project for OAuth credential-in-URL violations."""
    findings = []
    for root, _dirs, files in os.walk(project_root):
        # Skip common non-source directories
        if any(skip in root for skip in ("/.git/", "/__pycache__/", "/venv/", "/node_modules/")):
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            file_findings = scan_file(filepath)
            if file_findings:
                findings.append({
                    "filepath": filepath,
                    "matches": file_findings,
                })
    return findings


def main(project_root: str, fix: bool = False) -> int:
    """Run security scan. Returns exit code."""
    findings = scan_project(project_root)

    if not findings:
        print("✅ 安全扫描通过: 未检测到 OAuth credential 在 URL query 中的风险")
        return 0

    print(f"🚨 检测到 {len(findings)} 个文件存在 OAuth credential 泄露风险:")
    print()
    for item in findings:
        print(f"   📁 {item['filepath']}")
        for match in item["matches"]:
            print(f"      L{match['line']}: {match['snippet']}")
            print(f"      敏感字段: {', '.join(match['sensitive_keys'])}")
            print(f"      风险: RFC 6749 §2.3.1 — confidential client 凭证不应在 URL query 中")
            print(f"      修复: 改用 data= 代替 params=，将凭证放入 POST body")
            print()

    print("<!-- vibe:security_scan: oauth_credential_in_url_query=" + str(len(findings)) + " -->")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Security pattern scanner")
    parser.add_argument("project_root", help="Project root to scan")
    parser.add_argument("--fix", action="store_true", help="Auto-fix (not yet implemented)")
    args = parser.parse_args()
    raise SystemExit(main(args.project_root, fix=args.fix))
