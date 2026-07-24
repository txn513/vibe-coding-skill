#!/usr/bin/env python3
from __future__ import annotations
"""Record a structured decision on the latest pending review for a spec."""

import argparse
import os
import re

from common import atomic_write, text_digest, validate_artifact_name
from generate_review import generate_review

CONCLUSIONS = {"approved", "changes-requested"}


def record_review(
    project_root: str,
    spec_name: str,
    conclusion: str,
    basis: str,
    evidence: str,
    reviewer: str,
    role: str = "",
    reason: str = "",
) -> str | None:
    """role/reason 是 2026-07-10 #4 review-decision-identity 配套参数.

    默认空字符串 (= role 视为 'reviewer'), reviewer == builder 时 WARN.
    role='override_approver' 必须 reason 非空, 否则 raise.
    """
    spec_name = validate_artifact_name(spec_name, "规格名称")
    if conclusion not in CONCLUSIONS:
        raise ValueError(f"无效审查结论: {conclusion}")
    basis = " ".join(basis.split())
    evidence = " ".join(evidence.split())
    reviewer = " ".join(reviewer.split())
    if not basis or not evidence or not reviewer:
        raise ValueError("审查者、结论依据和已核对证据都不能为空")
    # Rule 55: review must inspect content, not just confirm existence.
    # A review basis that is too vague ("looks good", "LGTM", "没问题")
    # without referencing specific diff hunks, spec clauses, or AC
    # numbers is not a valid review — it is the same failure mode as
    # showing stat but not reviewing content (original Rule 53 bug).
    vague_basis = {"looks good", "lgtm", "没问题", "看起来没问题", "ok", "fine", "approved"}
    if basis.strip().lower() in vague_basis:
        raise ValueError(
            "Rule 55: 审查依据太笼统，必须引用具体的 diff 观察、spec 条款或验收标准编号。"
            f"  当前依据: '{basis}'"
        )
    # 2026-07-08g: substantive basis signal gate.
    # Lance retro: even when basis passes the vague-block list (eg
    # "BUG-261 \u884c\u53f7\u98d9\u79fb \u771f\u5b9e\u4f4d\u7f6e _resolve_short_url
    # finally api.py:343"), it can still be post-hoc reasoning without
    # anchoring back to the actual review-context file. The
    # "reviewer of my own work default-accepts" failure mode is the
    # same shape as R53 review-summary form-pass. We require the
    # basis to contain at least one concrete signal: a path to a
    # review-context file, a line reference, an AC number, a path
    # to a code file, or a code-fragment backtick. Cost ~10 lines,
    # value: closes "I am reviewer of my own work" failure mode
    # without forcing a full LLM analysis.
    substantive_signals = [
        re.search(r"\b(?:L|l)\s*\d+\b", basis),
        re.search(r"\bline\s+\d+\b", basis, re.IGNORECASE),
        re.search(r":\d{1,4}\b", basis),
        re.search(r"\bAC\d+\b", basis, re.IGNORECASE),
        re.search(r"\.agents?/\S+", basis),
        re.search(
            r"\b[a-zA-Z_][\w./-]*\.(?:py|js|ts|jsx|tsx|go|rs|java|"
            r"rb|swift|kt|c|cpp|h|hpp|cs|md|sql|sh|bash|zsh|yaml|yml|"
            r"toml|json|env)\b",
            basis,
        ),
        re.search(r"`[^`\s]+`", basis),
    ]
    if not any(substantive_signals):
        raise ValueError(
            "Rule 55 + 2026-07-08g: \u7ed3\u8bba\u4f9d\u636e\u5f62\u5f0f\u5408\u89c4\u4f46\u7f3a\u5177\u4f53\u4fe1\u53f7\u3002\n"
            "\u5fc5\u987b\u81f3\u5c11\u5305\u542b\u4ee5\u4e0b\u4e4b\u4e00\uff1a\n"
            "  \u00b7 \u8def\u5f84\u5f15\u7528\uff08.agents/reviews/<file>.md / backend/api.py\uff09\n"
            "  \u00b7 \u884c\u53f7\uff08L25 / line 25 / api.py:343\uff09\n"
            "  \u00b7 AC \u7f16\u53f7\uff08AC1 / AC2.3\uff09\n"
            "  \u00b7 \u4ee3\u7801\u7247\u6bb5\uff08\u53cd\u5f15\u53f7\u5305\u4f4f identifier\uff09\n"
            f"  \u5f53\u524d\u4f9d\u636e: '{basis}'"
        )

    # 2026-07-10 #4 review-decision-identity: review-decision 检查
    # reviewer vs builder, 与 advance released --role override_approver 机制对齐。
    # 默认 WARN, 不阻塞; 仅当 role == override_approver 时合法 (要求非空 reason)。
    identity_warn = _check_reviewer_identity(
        project_root, spec_name, reviewer,
        id_role=role, id_reason=reason,
    )
    if identity_warn:
        print(identity_warn)
        print("<!-- vibe:review_identity_advisory: surfaced -->")

    # R-D-76: If reviewer claims independent, verify enforcer-log has evidence
    if reviewer and "independent" in reviewer.lower():
        _enforce_independent_session(project_root, reviewer)

    review_file = _latest_pending_review(project_root, spec_name)
    if not review_file:
        generated = generate_review(project_root, spec_name, reviewer)
        if not generated:
            return None
        review_file = generated

    with open(review_file, encoding="utf-8") as handle:
        content = handle.read()
    content = re.sub(
        r"(\|\s*结论:\s*)pending(\s*\|)",
        rf"\g<1>{conclusion}\g<2>",
        content,
        count=1,
    )
    content = re.sub(
        r"Reviewer:\s*[^|\n]+",
        lambda _: f"Reviewer: {reviewer} ",
        content,
        count=1,
    )
    content = re.sub(
        r"^-\s*结论依据[^:]*:.*$",
        lambda _: f"- 结论依据: {basis}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^-\s*已核对的验证证据[^:]*:.*$",
        lambda _: f"- 已核对的验证证据: {evidence}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    payload = "\n".join([conclusion, basis, evidence, reviewer])
    content = re.sub(
        r"^>\s*Decision-Record:\s*.*$",
        lambda _: f"> Decision-Record: {text_digest(payload)}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    atomic_write(review_file, content)
    print(f"✅ 已记录审查结论: {review_file}")

    # Rule 53d: clear pending review marker if one exists.
    # A review decision means the bypassed review has been addressed.
    _clear_pending_review_marker(project_root)

    return review_file




def _clear_pending_review_marker(project_root: str) -> None:
    """Rule 53d: remove entries from .vibe-pending-reviews.json after review.

    If all entries are cleared, delete the file entirely.
    """
    import json as _json
    marker_path = os.path.join(project_root, ".agents", ".vibe-pending-reviews.json")
    if not os.path.exists(marker_path):
        return
    try:
        with open(marker_path, "r", encoding="utf-8") as handle:
            entries = _json.load(handle)
    except (OSError, _json.JSONDecodeError):
        return
    if not entries:
        # Empty — just delete the file
        os.remove(marker_path)
        return
    # Keep entries that are less than 1 day old (give some grace period)
    # or remove all if only 1-2 remain
    import time as _time
    now = _time.time()
    remaining = []
    for entry in entries:
        ts = entry.get("timestamp", "")
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_hours = (now - dt.timestamp()) / 3600
        except (ValueError, OSError):
            age_hours = 999
        # Remove entries older than 1 hour (review has been done)
        if age_hours < 1:
            continue  # too recent, keep
        remaining.append(entry)
    if not remaining:
        os.remove(marker_path)
        print("📋 Rule 53d: pending review marker 已清除（全部审查完成）")
    elif len(remaining) < len(entries):
        with open(marker_path, "w", encoding="utf-8") as handle:
            handle.write(_json.dumps(remaining, ensure_ascii=False, indent=2))
        cleared = len(entries) - len(remaining)
        print(f"📋 Rule 53d: 已清除 {cleared} 条 pending review 记录，剩余 {len(remaining)} 条")

def _latest_pending_review(project_root: str, spec_name: str) -> str | None:
    reviews_dir = os.path.join(project_root, ".agents", "reviews")
    if not os.path.exists(reviews_dir):
        return None
    matches = []
    for filename in os.listdir(reviews_dir):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(reviews_dir, filename)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        if (
            f"规格: {spec_name}" in content
            and re.search(r"\|\s*结论:\s*pending(?:\s*\||\s*$)", content)
        ):
            matches.append(path)
    return sorted(matches)[-1] if matches else None



def _check_reviewer_identity(
    project_root: str,
    spec_name: str,
    reviewer: str,
    id_role: str,
    id_reason: str,
) -> str:
    """2026-07-10 advisory #4: review-decision 检查 reviewer != builder.

    motive: Rule 5 约束 reviewer != builder, 但 review-decision 命令
    没有 enforce。advance released 已经有 --role override_approver 机制,
    review-decision 应该对齐 — 默认让 agent 走普通 reviewer 路径,
    reviewer == builder 时 WARN。如果 agent 显式 role=override_approver
    且 reason 非空, 视为合法, 不发 WARN。

    Returns: warning string (caller prints) or empty string.
    """
    role_norm = (id_role or "").strip().lower() or "reviewer"
    if role_norm == "override_approver":
        if not id_reason.strip():
            raise ValueError(
                "Rule 5: role=override_approver 必须 --reason 非空 (audit trail). "
                "参考 advance released --role override_approver 机制。"
            )
        return ""
    # 普通 reviewer 路径: 抓 spec 的 builder
    spec_file = os.path.join(
        project_root, ".agents", "specs", f"{spec_name}.md"
    )
    builder = ""
    if os.path.isfile(spec_file):
        try:
            with open(spec_file, encoding="utf-8") as handle:
                spec_content = handle.read()
            m = re.search(r"^>\s*(?:\u5efa\u9020\u8005|Builder):\s*(.+?)\s*$", spec_content, re.MULTILINE)
            if m:
                builder = m.group(1).strip()
        except OSError:
            builder = ""
    reviewer_norm = reviewer.strip().lower()
    if builder and reviewer_norm and reviewer_norm == builder.lower():
        return (
            f"\u26a0\ufe0f  reviewer 与 builder 同身份 ({builder}), 可能违反 Rule 5 "
            "(reviewer != builder)。如确实单人项目 / 演示, 改用:\n"
            "  vibe review-decision . <spec> ... --reviewer <name> \\\n"
            "    --role override_approver --reason '<why>'\n"
            "参考 advance released 的等价机制。"
        )
    return ""


def _enforce_independent_session(project_root: str, reviewer: str) -> None:
    """R-D-76: Verify that enforcer-log contains evidence of an independent
    review session before allowing a claim of independent review.

    Without this check, an agent can call record_review.py directly
    with --reviewer "independent" and bypass all R-D-59 / R5b / R5d
    ENFORCE gates that only match vibe CLI commands.
    """
    log_path = os.path.join(project_root, ".agents", "enforcer-log.md")
    if not os.path.exists(log_path):
        raise ValueError(
            f"R-D-76: claimed independent review by {reviewer!r} but "
            f"enforcer-log.md does not exist. Run an independent review "
            f"session first (pi --print --no-session or codex exec)."
        )
    try:
        with open(log_path, encoding="utf-8") as f:
            log_content = f.read()
    except OSError:
        log_content = ""

    # Check for evidence of independent session in enforcer-log
    has_session = bool(
        re.search(r"pi\s+(agent|run)\s+--(print|no-session)", log_content)
        or re.search(r"codex\s+exec", log_content)
        or re.search(r"spawn_reviewer", log_content)
    )
    if not has_session:
        raise ValueError(
            f"R-D-76: claimed independent review by {reviewer!r} but "
            f"enforcer-log has no independent session record. "
            f"Run `pi --print --no-session -ne '<prompt>'` or "
            f"`codex exec --allowedTools Read,Bash,Grep` to start one."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record a structured review decision")
    parser.add_argument("project_root")
    parser.add_argument("spec_name")
    parser.add_argument("conclusion", choices=sorted(CONCLUSIONS))
    parser.add_argument("basis")
    parser.add_argument("evidence")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--role", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    record_review(
        os.path.abspath(args.project_root),
        args.spec_name,
        args.conclusion,
        args.basis,
        args.evidence,
        args.reviewer,
        role=args.role,
        reason=args.reason,
    )
