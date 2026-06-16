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
        r"^-\s*结论依据:.*$",
        lambda _: f"- 结论依据: {basis}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^-\s*已核对的验证证据:.*$",
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
