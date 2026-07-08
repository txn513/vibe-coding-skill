#!/usr/bin/env python3
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
) -> str | None:
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
    return review_file


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record a structured review decision")
    parser.add_argument("project_root")
    parser.add_argument("spec_name")
    parser.add_argument("conclusion", choices=sorted(CONCLUSIONS))
    parser.add_argument("basis")
    parser.add_argument("evidence")
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    record_review(
        os.path.abspath(args.project_root),
        args.spec_name,
        args.conclusion,
        args.basis,
        args.evidence,
        args.reviewer,
    )
