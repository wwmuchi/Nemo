#!/usr/bin/env python3
"""
Fetch quiz questions from open-source political quizzes on GitHub.

Each entry in QUIZZES points at the raw GitHub URL of the file that contains
the questions for that quiz, plus the parser used to extract them. The script
downloads the file, extracts the questions, and saves them per-quiz under
./fetched/<quiz>.json plus a combined ./fetched/all_questions.json plus a
deduplicated flat ./fetched/deduped.json.

All listed quizzes are MIT-licensed open source. For closed-source quizzes
(Political Compass, IDRlabs, Pew, iSideWith, Belief-O-Matic, the Italian VAAs,
etc.) you have to copy the questions from each site manually.

Usage:
    python3 fetch_questions.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

# Each quiz: (name, url, license, attribution_url, parser_type)
#   parser_type:
#     - "labeled"        — extract `"question": "..."` style entries
#     - "sentence_array" — extract all double-quoted strings that look like
#                          sentences from arrays (used by 9axes)
#     - "json_values"    — fetch JSON, take values of keys starting with "q_"
QUIZZES: list[tuple[str, str, str, str, str]] = [
    (
        "8values",
        "https://raw.githubusercontent.com/8values/8values.github.io/HEAD/questions.js",
        "MIT",
        "https://github.com/8values/8values.github.io",
        "labeled",
    ),
    (
        "sapplyvalues",
        "https://raw.githubusercontent.com/SapplyValues/SapplyValues.github.io/HEAD/questions.js",
        "MIT",
        "https://github.com/SapplyValues/SapplyValues.github.io",
        "labeled",
    ),
    (
        "leftvalues",
        "https://raw.githubusercontent.com/LeftValues/leftvalues.github.io/HEAD/lang/lang_en.json",
        "MIT",
        "https://github.com/LeftValues/leftvalues.github.io",
        "json_values",
    ),
    (
        "9axes",
        "https://raw.githubusercontent.com/9Axes/9axes.github.io/HEAD/questions.js",
        "MIT",
        "https://github.com/9Axes/9axes.github.io",
        "sentence_array",
    ),
    (
        "authvalues",
        "https://raw.githubusercontent.com/Pandemik-svg/AuthValues/HEAD/questions.js",
        "MIT",
        "https://github.com/Pandemik-svg/AuthValues",
        "labeled",
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


_LABELED_PATTERN = re.compile(
    r'["\']?question["\']?\s*:\s*["\']((?:[^"\'\\]|\\.)*)["\']',
    flags=re.IGNORECASE,
)
# Match any double-quoted string that looks like a sentence: contains a space,
# at least one letter, length >= 25, ends with letter/period/?/!.
_SENTENCE_PATTERN = re.compile(
    r'"((?:[^"\\]|\\.){25,})"',
)


def parse_labeled(body: str) -> list[str]:
    return _dedupe([_unescape(m).strip() for m in _LABELED_PATTERN.findall(body)])


def parse_sentence_array(body: str) -> list[str]:
    out: list[str] = []
    for m in _SENTENCE_PATTERN.findall(body):
        s = _unescape(m).strip()
        if " " in s and any(c.isalpha() for c in s):
            out.append(s)
    return _dedupe(out)


def parse_json_values(body: str) -> list[str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"  ! JSON parse error: {e}")
        return []
    out: list[str] = []
    # LeftValues uses keys like q_0, q_1, ... for question text.
    for key, val in data.items():
        if not isinstance(val, str):
            continue
        if re.fullmatch(r"q_?\d+", key, flags=re.IGNORECASE) or key.lower().startswith(
            "question"
        ):
            out.append(val.strip())
    return _dedupe(out)


def _unescape(s: str) -> str:
    try:
        return bytes(s, "utf-8").decode("unicode_escape", errors="replace")
    except Exception:
        return s


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


PARSERS = {
    "labeled": parse_labeled,
    "sentence_array": parse_sentence_array,
    "json_values": parse_json_values,
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    combined: dict[str, dict] = {}

    for name, url, license_, attribution, parser_type in QUIZZES:
        print(f"Fetching {name} ...")
        body = fetch(url)
        if body is None:
            continue
        parser = PARSERS.get(parser_type)
        if parser is None:
            print(f"  ! unknown parser type: {parser_type}")
            continue
        questions = parser(body)
        if not questions:
            print(f"  ! no questions parsed — inspect {url}")
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
