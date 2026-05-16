#!/usr/bin/env python3
"""
Fetch quiz questions from open-source political quizzes on GitHub.

Each entry in QUIZZES points at the raw GitHub URL of the JS file that contains
the questions array for that quiz. The script downloads the file, extracts the
questions, and saves them per-quiz under ./fetched/<quiz>.json plus a combined
./fetched/all_questions.json.

All listed quizzes are MIT-licensed open source. For closed-source quizzes
(Political Compass, IDRlabs, Pew, iSideWith, Belief-O-Matic, the Italian VAAs,
etc.) you have to copy the questions from each site manually — there is no
clean automated way to do it.

Usage:
    python3 fetch_questions.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

# (quiz_name, raw_github_url, license, attribution)
QUIZZES: list[tuple[str, str, str, str]] = [
    (
        "8values",
        "https://raw.githubusercontent.com/8values/8values.github.io/master/js/quiz_questions.js",
        "MIT",
        "https://github.com/8values/8values.github.io",
    ),
    (
        "sapplyvalues",
        "https://raw.githubusercontent.com/Sapply/sapplyvalues.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/Sapply/sapplyvalues.github.io",
    ),
    (
        "leftvalues",
        "https://raw.githubusercontent.com/LeftValues/leftvalues.github.io/master/js/quiz_questions.js",
        "MIT",
        "https://github.com/LeftValues/leftvalues.github.io",
    ),
    (
        "9axes",
        "https://raw.githubusercontent.com/9Axes/9Axes.github.io/master/js/quiz_questions.js",
        "MIT",
        "https://github.com/9Axes/9Axes.github.io",
    ),
    (
        "libertarianvalues",
        "https://raw.githubusercontent.com/polittest/libertarianvalues/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/polittest/libertarianvalues",
    ),
    (
        "authvalues",
        "https://raw.githubusercontent.com/politicaltests/auth/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/politicaltests/auth",
    ),
    (
        "liberationvalues",
        "https://raw.githubusercontent.com/liberationvalues/liberationvalues.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/liberationvalues/liberationvalues.github.io",
    ),
    (
        "10groups",
        "https://raw.githubusercontent.com/10groups/10groups.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/10groups/10groups.github.io",
    ),
    (
        "sixtriangles",
        "https://raw.githubusercontent.com/sixtriangles/sixtriangles.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/sixtriangles/sixtriangles.github.io",
    ),
    (
        "3axes",
        "https://raw.githubusercontent.com/3axes/3axes.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/3axes/3axes.github.io",
    ),
    (
        "prismquiz",
        "https://raw.githubusercontent.com/prismquiz/prismquiz.github.io/main/js/quiz_questions.js",
        "MIT",
        "https://github.com/prismquiz/prismquiz.github.io",
    ),
]

OUT_DIR = Path(__file__).parent / "fetched"


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "quiz-fetcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ! failed: {e}", file=sys.stderr)
        return None


_QUESTION_PATTERN = re.compile(
    r'question\s*:\s*"((?:[^"\\]|\\.)*)"',
    flags=re.IGNORECASE,
)


def extract_questions(js_source: str) -> list[str]:
    """Pull every `question: "..."` value out of a quiz JS file."""
    raw = _QUESTION_PATTERN.findall(js_source)
    cleaned: list[str] = []
    seen = set()
    for q in raw:
        unescaped = bytes(q, "utf-8").decode("unicode_escape", errors="replace").strip()
        if unescaped and unescaped not in seen:
            seen.add(unescaped)
            cleaned.append(unescaped)
    return cleaned


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    combined: dict[str, dict] = {}

    for name, url, license_, attribution in QUIZZES:
        print(f"Fetching {name} ...")
        body = fetch(url)
        if body is None:
            continue
        questions = extract_questions(body)
        if not questions:
            print(f"  ! no questions parsed — the URL may have changed; inspect: {url}")
            continue

        record = {
            "quiz": name,
            "source_url": url,
            "license": license_,
            "attribution": attribution,
            "count": len(questions),
            "questions": questions,
        }
        (OUT_DIR / f"{name}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        combined[name] = record
        print(f"  ok — {len(questions)} questions saved to fetched/{name}.json")

    (OUT_DIR / "all_questions.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Build a deduplicated flat list (case-insensitive match on full text).
    seen: set[str] = set()
    deduped: list[dict] = []
    for name, record in combined.items():
        for q in record["questions"]:
            key = q.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"text": q, "first_seen_in": name})
    (OUT_DIR / "deduped.json").write_text(
        json.dumps(deduped, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print(f"Done. {len(deduped)} unique questions across {len(combined)} quizzes.")
    print(f"Output dir: {OUT_DIR}")
    print()
    print("NOTE: Closed-source quizzes (Political Compass, IDRlabs, Pew, iSideWith,")
    print("Belief-O-Matic, and the Italian VAAs) are NOT fetched here — their")
    print("questions are copyrighted and must be copied manually from each site.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
