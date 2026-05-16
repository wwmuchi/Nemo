#!/usr/bin/env python3
"""
Read questions-to-review.md, pick the ticked `[x]` items, and write them
verbatim into FINAL QUESTIONS.md grouped by category.

Question text is never modified — only filtered and reorganized.

Usage:
    python3 extract_selected.py
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).parent
IN_FILE = HERE / "questions-to-review.md"
OUT_FILE = HERE / "FINAL QUESTIONS.md"

CATEGORY_RE = re.compile(r"^##\s+(.+?)(?:\s+\(\d+\))?\s*$")
# A line counts as ticked if EITHER:
#   1. the markdown checkbox is `[x]`        (e.g. "- [x] **1.** ...")
#   2. the line starts with `x` or `X`        (e.g. "x - [ ] **1.** ...")
# Captures the question text without numbering prefix and without the
# trailing "_(from: source)_" tag.
TICKED_RE = re.compile(
    r"^\s*(?:x\s+)?-\s*\[\s*x?\s*\]\s*(?:\*\*\d+\.\*\*\s*)?(.*?)(?:\s+_\(from:\s*[^)]+\)_)?\s*$",
    flags=re.IGNORECASE,
)
STARTS_WITH_X_RE = re.compile(r"^\s*x\s+-\s*\[", flags=re.IGNORECASE)
HAS_BRACKET_X_RE = re.compile(r"^\s*-\s*\[\s*x\s*\]", flags=re.IGNORECASE)


def line_is_ticked(line: str) -> bool:
    return bool(STARTS_WITH_X_RE.match(line) or HAS_BRACKET_X_RE.match(line))


def main() -> int:
    if not IN_FILE.exists():
        print(f"! {IN_FILE} not found. Run categorize_questions.py first.")
        return 1

    current_category = "Uncategorized"
    by_category: dict[str, list[str]] = {}
    category_order: list[str] = []

    for raw_line in IN_FILE.read_text(encoding="utf-8").splitlines():
        cat_match = CATEGORY_RE.match(raw_line)
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue
        if not line_is_ticked(raw_line):
            continue
        tick_match = TICKED_RE.match(raw_line)
        if not tick_match:
            continue
        text = tick_match.group(1).strip()
        if not text:
            continue
        if current_category not in by_category:
            by_category[current_category] = []
            category_order.append(current_category)
        by_category[current_category].append(text)

    total = sum(len(v) for v in by_category.values())

    lines: list[str] = []
    lines.append("# Final Questions")
    lines.append("")
    lines.append(
        f"**{total} questions** selected from `questions-to-review.md` across "
        f"**{len(by_category)} categories**."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for cat in category_order:
        qs = by_category[cat]
        lines.append(f"## {cat} ({len(qs)})")
        lines.append("")
        for i, q in enumerate(qs, 1):
            lines.append(f"{i}. {q}")
        lines.append("")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_FILE.name} with {total} questions across "
          f"{len(by_category)} categories.")
    if total == 0:
        print("  (no `[x]` ticked checkboxes were found — did you save the file?)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
