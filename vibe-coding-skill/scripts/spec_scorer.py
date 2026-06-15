#!/usr/bin/env python3
"""Weighted relevance scoring for completed specs.

Shared by retrospective and self-analyze to rank which specs are most
worth reviewing or analyzing.

Weights:
  amendments  = 40  (design was corrected — highest signal)
  reviews     = 30  (decision-making activity)
  evidence    = 20  (verification activity)
  spec mtime  = 10  (baseline)
  regression_from metadata = +15 bonus (bug fix with lessons)
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from workflow_state import spec_last_touched, spec_metadata

# --- Weights ---
WEIGHT_AMENDMENTS = 40.0
WEIGHT_REVIEWS = 30.0
WEIGHT_EVIDENCE = 20.0
WEIGHT_BASELINE = 10.0
BONUS_REGRESSION = 15.0


def score_spec(project_root: str, spec_name: str, content: str) -> dict | None:
    """Return a relevance score dict for a single spec, or None if unscorable.

    Returns:
        {
            "name": str,
            "score": float,
            "signals": list[str],
            "latest": datetime,
        }
    """
    base = spec_last_touched(content)
    if not base:
        return None

    signals: list[str] = []
    score = WEIGHT_BASELINE
    latest = base

    # Evidence
    evidence_dir = Path(project_root) / ".agents" / "evidence" / spec_name
    if evidence_dir.exists():
        evidence_files = list(evidence_dir.glob("*.md"))
        if evidence_files:
            newest = max(
                datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                for p in evidence_files
            )
            latest = max(latest, newest)
            score += WEIGHT_EVIDENCE
            signals.append(f"evidence({len(evidence_files)} files)")

    # Reviews
    reviews_dir = Path(project_root) / ".agents" / "reviews"
    if reviews_dir.exists():
        pattern = re.compile(
            rf"^>\s*规格:\s*{re.escape(spec_name)}\s*\|", re.MULTILINE
        )
        count = 0
        newest_review = None
        for path in reviews_dir.glob("*.md"):
            try:
                rc = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if pattern.search(rc):
                count += 1
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                newest_review = max(newest_review, mtime) if newest_review else mtime
        if count > 0:
            latest = max(latest, newest_review)
            score += WEIGHT_REVIEWS
            signals.append(f"review({count} docs)")

    # Amendments
    amendments = Path(project_root) / ".agents" / "specs" / f"{spec_name}-amendments.md"
    if amendments.exists():
        mtime = datetime.fromtimestamp(amendments.stat().st_mtime, tz=timezone.utc)
        latest = max(latest, mtime)
        score += WEIGHT_AMENDMENTS
        signals.append("amended")

    # Regression bonus
    metadata = spec_metadata(content)
    if metadata.get("regression_from"):
        score += BONUS_REGRESSION
        signals.append(f"regression(from={metadata['regression_from']})")

    return {
        "name": spec_name,
        "score": score,
        "signals": signals,
        "latest": latest,
    }


def rank_specs(
    project_root: str,
    status_filter: set[str] | None = None,
    limit: int = 0,
) -> list[dict]:
    """Scan all specs and return them ranked by relevance score.

    Args:
        project_root: path to project root
        status_filter: only include specs with these statuses (None = all)
        limit: max results (0 = all)

    Returns:
        list of score dicts sorted by score descending.
    """
    specs_dir = os.path.join(project_root, ".agents", "specs")
    if not os.path.exists(specs_dir):
        return []

    results: list[dict] = []
    for filename in sorted(os.listdir(specs_dir)):
        if not filename.endswith(".md") or filename.endswith("-amendments.md"):
            continue
        path = os.path.join(specs_dir, filename)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        status_match = re.search(r"^>\s*状态:\s*(\S+)", content, re.MULTILINE)
        if not status_match:
            continue
        status = status_match.group(1)
        if status_filter and status not in status_filter:
            continue
        scored = score_spec(project_root, filename[:-3], content)
        if scored:
            scored["status"] = status
            results.append(scored)

    results.sort(key=lambda item: item["score"], reverse=True)
    if limit > 0:
        results = results[:limit]
    return results


def format_rationale(scored: dict, total_candidates: int = 0) -> str:
    """Format a scored spec into a human-readable rationale string."""
    parts = [f"score={scored['score']:.0f}"]
    parts.append(f"signals=[{', '.join(scored['signals'])}]")
    if total_candidates > 1:
        parts.append(f"(among {total_candidates} candidates)")
    return ", ".join(parts)
