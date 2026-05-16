#!/usr/bin/env python3
"""
Categorize the fetched quiz questions and produce a markdown review file.

Reads ./fetched-questions/deduped.json, assigns each question to a topic
category via keyword matching (the question text is NEVER modified — only
routed to a section), and writes ./questions-to-review.md with a `[ ]`
checkbox per question.

Workflow:
    1. python3 categorize_questions.py
    2. Open questions-to-review.md, tick `[x]` on the questions you want.
    3. Run extract_selected.py (separate script) to copy ticked questions
       into FINAL QUESTIONS.md.

Usage:
    python3 categorize_questions.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
IN_FILE = HERE / "fetched-questions" / "deduped.json"
OUT_FILE = HERE / "questions-to-review.md"

# Order matters: a question is placed in the FIRST category whose keywords match.
# Keywords are matched as whole-word, case-insensitive substrings of the text.
CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Religion & Morality",
        [
            "god", "religion", "religious", "church", "atheis", "faith",
            "spiritual", "prayer", "blasphem", "secular", "islam", "christian",
            "jewish", "hindu", "buddhis", "afterlife", "heaven", "hell",
            "soul", "divine", "sin", "moral",
        ],
    ),
    (
        "Family, Gender & Sexuality",
        [
            "abortion", "gay", "lesbian", "lgbt", "lgbtq", "homosex",
            "transgender", "trans ", "gender", "marriage", "marri",
            "adopt", "sex ", "sexual", "pornograph", "surrogac",
            "family", "child", "polyamor", "feminis", "patriarchy",
        ],
    ),
    (
        "Environment & Climate",
        [
            "climate", "environment", "pollut", "carbon", "fossil",
            "green ", "nuclear", "renewable", "animal", "vegan",
            "vegetarian", "biodivers", "ecolog", "nature",
        ],
    ),
    (
        "Immigration & National Identity",
        [
            "immigra", "migra", "refugee", "border", "asylum",
            "nation", "patrioti", "citizen", "ethnic", "race ",
            "racial", "multicultur", "assimilat",
        ],
    ),
    (
        "Foreign Policy & International Relations",
        [
            "foreign", "international", "world", "global", "globaliz",
            "diploma", "war ", "military", "army", "intervention",
            "united nations", " un ", "nato", "european union", " eu ",
            "imperial", "coloni", "ally", "alliance", "sanction",
            "treaty", "trade ", "tariff",
        ],
    ),
    (
        "Justice, Crime & Law Enforcement",
        [
            "police", "prison", "crime", "criminal", "death penalty",
            "execution", "justice ", "court", "punish", "drug",
            "marijuana", "cannabis", "law enforce", "surveillanc",
            "weapon", "gun ", "firearm",
        ],
    ),
    (
        "Education",
        [
            "school", "education", "univers", "college", "student",
            "teach", "curriculum", "tuition",
        ],
    ),
    (
        "Healthcare",
        [
            "health", "medic", "hospital", "doctor", "vaccin",
            "pharmac", "insuranc", "euthanasi", "mental ",
        ],
    ),
    (
        "Technology, Media & Privacy",
        [
            "internet", "online", "tech", "social media", "media ",
            "press", "censor", "encrypt", "data ", "privacy",
            "artificial intelligence", " ai ", "algorithm",
        ],
    ),
    (
        "Labor & Workers",
        [
            "worker", "labor", "labour", "union", "strike", "wage",
            "salary", "employ", "unemploy", "minimum wage",
        ],
    ),
    (
        "Economy & Markets",
        [
            "econom", "market", "capital", "corporat", "industr",
            "trade ", "monopol", "compan", "business", "private property",
            "nationali", "privati", "wealth", "billionaire",
            "inequal", "poverty", "rich", "poor ",
        ],
    ),
    (
        "Taxation & Welfare",
        [
            "tax", "welfare", "benefit", "pension", "social security",
            "redistribut", "subsid", "universal basic income", "ubi ",
        ],
    ),
    (
        "Government, Authority & State Power",
        [
            "government", "state ", "authorit", "regulat", "bureaucr",
            "constitut", "monarch", "dictat", "leader", "central",
            "decentral", "federal", "local government",
        ],
    ),
    (
        "Democracy & Political System",
        [
            "democra", "elect", "vote ", "voter", "voting", "referend",
            "parliament", "congress", "politic", "party",
            "campaign", "lobby",
        ],
    ),
    (
        "Civil Liberties & Individual Rights",
        [
            "freedom", "liberty", "speech", "express", "right ", "rights ",
            "civil", "individual", "protest", "assembl",
        ],
    ),
    (
        "Society & Culture",
        [
            "society", "social", "cultur", "tradition", "values",
            "community", "diversity", "minorit", "history",
        ],
    ),
]


def categorize(text: str) -> str:
    t = " " + text.lower() + " "
    for category, keywords in CATEGORIES:
        for kw in keywords:
            if kw in t:
                return category
    return "Uncategorized"


def main() -> int:
    if not IN_FILE.exists():
        print(f"! {IN_FILE} not found. Run fetch_questions.py first.")
        return 1

    items = json.loads(IN_FILE.read_text(encoding="utf-8"))
    buckets: dict[str, list[dict]] = {}
    for entry in items:
        cat = categorize(entry["text"])
        buckets.setdefault(cat, []).append(entry)

    # Ensure deterministic category order: defined order, then Uncategorized last.
    order = [name for name, _ in CATEGORIES] + ["Uncategorized"]

    lines: list[str] = []
    lines.append("# Questions to Review")
    lines.append("")
    lines.append(
        "Tick `[x]` on the questions you want to keep. Then run "
        "`extract_selected.py` to copy them into `FINAL QUESTIONS.md`."
    )
    lines.append("")
    lines.append(f"Total: **{len(items)} unique questions** across "
                 f"**{len([c for c in order if c in buckets])} categories**.")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_check = 0
    for cat in order:
        if cat not in buckets:
            continue
        qs = buckets[cat]
        lines.append(f"## {cat} ({len(qs)})")
        lines.append("")
        for i, q in enumerate(qs, 1):
            text = q["text"].replace("\n", " ").strip()
            source = q.get("first_seen_in", "?")
            lines.append(f"- [ ] **{i}.** {text}  _(from: {source})_")
            total_check += 1
        lines.append("")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_FILE.relative_to(HERE.parent)}")
    print(f"  {total_check} checkboxes across {len([c for c in order if c in buckets])} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
