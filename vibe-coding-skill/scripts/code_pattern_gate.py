"""Static scan for asyncio.create_task + shared AsyncSession commit.

Rule 64: `asyncio.create_task` MUST NOT be used to call
`session.commit()` (or `db.commit()` / `<var>.commit()`) on an
AsyncSession that is shared with the parent coroutine. The race is
deterministic: when the parent and the fire-and-forget task both try
to commit, SQLAlchemy raises
`IllegalStateChangeError: Method 'commit()' can't be called here;
method 'commit()' is already in progress`, and the fire-and-forget
task's exception handler silently swallows it. The fix is to either
use a fresh AsyncSession inside the task, use `asyncio.Lock`, or call
the commit from the parent coroutine.

This gate is **advisory only** — the parent gate in `commit.py` never
hard-blocks on this. Suppress with `--no-async-gate` for legitimate
use cases (actor model with independent sessions, one-shot background
writes via a session factory, etc).

Implementation note: uses `ast` rather than regex so docstrings,
comments, and string literals are not falsely matched. The scan walks
each changed `.py` file and looks for `asyncio.create_task(...)` calls
whose first positional argument is a Callable (Lambda / FunctionDef /
AsyncFunctionDef / Name reference) and whose body references a
`session` / `db` / `AsyncSession` / `Session` identifier (or any
identifier that *resolves* to a session-style attribute on a name that
appears as `commit()`'s receiver inside the body).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path


# Identifier names that strongly suggest "this is a DB session object".
# The scan uses these as a heuristic for what counts as a "shared
# AsyncSession" — adding new aliases is fine, but the parent project
# should consider adopting a naming convention instead.
_SESSION_NAMES = frozenset({
    "session", "db", "async_session", "AsyncSession", "Session",
    "_session", "_db", "conn", "connection",
})


def _callable_name(node: ast.AST) -> str | None:
    """Return a human-readable label for a Callable AST node, or None."""
    if isinstance(node, ast.Lambda):
        return "lambda"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        # `factory()` returning a callable — describe as the function
        # being called, e.g. `make_worker`.
        if isinstance(node.func, ast.Name):
            return f"{node.func.id}()"
        if isinstance(node.func, ast.Attribute):
            return f"<expr>.{node.func.attr}()"
    return None


def _collect_callable_body(node: ast.AST) -> list[ast.stmt] | None:
    """Return the body statements of a callable, or None if not a known shape."""
    if isinstance(node, ast.Lambda):
        return [ast.Expr(value=node.body)]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return list(node.body)
    if isinstance(node, ast.Name):
        # We can't see the body of a Name reference at static scan time.
        return None
    if isinstance(node, ast.Call):
        # E.g. `make_worker(session)` — we don't know what `make_worker`
        # does statically. Skip (this is the conservative case: don't
        # warn for indirect factories the user has vetted).
        return None
    return None


def _find_session_commits(body: list[ast.stmt]) -> list[tuple[str, int]]:
    """Walk a list of statements; return [(receiver_name, lineno), ...]
    for any `*.commit(` call where the receiver name looks like a session.

    Only matches the EXACT method name `commit` (not `commit_xxx`), so
    `asyncio.Future` callbacks that happen to call `done.commit` etc.
    don't get caught. We do not match `db.execute()` style, only the
    actual `commit()` call which is the SQLAlchemy AsyncSession method
    that triggers the race.
    """
    findings: list[tuple[str, int]] = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "commit":
                continue
            # Receiver must be a plain Name (not e.g. chained calls).
            if not isinstance(func.value, ast.Name):
                continue
            receiver = func.value.id
            if receiver in _SESSION_NAMES:
                findings.append((receiver, sub.lineno))
    return findings


def scan_python_source(source: str, file_label: str = "<source>") -> list[str]:
    """Return a list of human-readable hint strings for any
    `asyncio.create_task` anti-pattern detected in `source`.

    Empty list means no anti-pattern found (or the file is not Python
    / cannot be parsed). The caller is responsible for printing these
    hints and tagging them with the file path / line number.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Malformed file (mid-edit, generated stub, etc.) — do not block.
        return []

    hints: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `asyncio.create_task(...)` (attr access form).
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "create_task":
            continue
        # Accept both `asyncio.create_task` and `<anything>.create_task`.
        if not (isinstance(func.value, ast.Name) and func.value.id == "asyncio"):
            continue
        if not node.args:
            continue
        target = node.args[0]
        callable_label = _callable_name(target)
        body = _collect_callable_body(target)
        if body is None:
            # Indirect call (Name / Call) — conservative: skip.
            continue
        findings = _find_session_commits(body)
        if not findings:
            continue
        receivers = sorted({name for name, _ in findings})
        first_lineno = min(ln for _, ln in findings)
        callable_str = callable_label or "<callable>"
        hint = (
            f"Rule 64 advisory: {file_label}:L{node.lineno} "
            f"`asyncio.create_task({callable_str})` 内对 "
            f"`{', '.join(receivers)}.commit()` 共享 session 触发 race — "
            f"改用独立 session factory / 加 asyncio.Lock / 同步调用"
        )
        hints.append(hint)
    return hints


def scan_changed_python_files(
    project_root: str,
    diff_text: str | None = None,
) -> list[str]:
    """Scan every `.py` file referenced in `diff_text` (or every `.py`
    file in `project_root` if `diff_text` is None) and return a flat
    list of hints across all files.

    The diff_text form is used during `vibe commit` to limit the scan
    to what is actually being committed; the directory form is used
    by the standalone audit command.
    """
    if diff_text is not None:
        files: list[str] = []
        for line in diff_text.splitlines():
            # Unified diff format: "+++ b/path/to/file"
            if line.startswith("+++ b/"):
                files.append(line[len("+++ b/"):])
            elif line.startswith("+++ "):
                # Unusual: relative or absolute path without `b/`
                path = line[len("+++"):].strip()
                if path and path != "/dev/null":
                    files.append(path.lstrip("/"))
        # De-dupe, preserve order.
        seen: set[str] = set()
        unique = []
        for f in files:
            if f not in seen and f.endswith(".py"):
                seen.add(f)
                unique.append(f)
        files = unique
    else:
        files = []
        for root, _dirs, fnames in os.walk(project_root):
            for fn in fnames:
                if fn.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, fn), project_root)
                    files.append(rel)

    hints: list[str] = []
    for relpath in files:
        full = Path(project_root) / relpath
        if not full.exists() or not full.is_file():
            continue
        try:
            source = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hints.extend(scan_python_source(source, file_label=relpath))
    return hints


def print_code_pattern_hints(hints: list[str], *, suppress: bool = False) -> int:
    """Print the hints in the same advisory style as `advance_checklist`
    / `line_ref_gate`. Returns the number of hints emitted (0 means
    the scan ran but found nothing).

    `suppress=True` is the escape hatch wired to `vibe commit --no-async-gate`.
    """
    if suppress or not hints:
        return 0
    print()
    print("⚠️  Rule 64 advisory — asyncio.create_task 反 pattern 扫描 (advisory, 不阻塞):")
    for idx, hint in enumerate(hints, 1):
        print(f"   [{idx}/{len(hints)}] {hint}")
    print("   修法: 改用独立 session factory / 加 asyncio.Lock / 改同步调用")
    print("   跳过: `vibe commit --no-async-gate`（参照 --no-checklist / --no-verify 模式）")
    print(f"<!-- vibe:code_pattern_gate: count={len(hints)} kind=async_shared_session -->")
    return len(hints)
