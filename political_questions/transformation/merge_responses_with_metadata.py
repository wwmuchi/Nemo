"""
Joins chatbot responses with question metadata.

Reads:
  - ../responses_export.csv      (QUESTION, MODEL, RESPONSE, BOT1..BOT7)
  - fifty_best_questions_transformed.json
      (text, first_seen_in, category, scenario)

Writes:
  - ../responses_export_enriched.csv
      (TEXT, FIRST_SEEN_IN, CATEGORY, QUESTION, MODEL, RESPONSE, BOT1..BOT7)

Join key: CSV.QUESTION == JSON.scenario (exact match).
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
JSON_PATH = HERE / "fifty_best_questions_transformed.json"
CSV_IN = HERE.parent / "responses_export.csv"
CSV_OUT = HERE.parent / "responses_export_enriched.csv"

NEW_COLS = ["TEXT", "FIRST_SEEN_IN", "CATEGORY"]
ORIG_COLS = ["QUESTION", "MODEL", "RESPONSE", "BOT1", "BOT2", "BOT3", "BOT4", "BOT5", "BOT6", "BOT7"]
OUT_COLS = NEW_COLS + ORIG_COLS


def main() -> int:
    metadata = {
        q["scenario"]: {
            "TEXT": q["text"],
            "FIRST_SEEN_IN": q["first_seen_in"],
            "CATEGORY": q["category"],
        }
        for q in json.loads(JSON_PATH.read_text())
    }

    with CSV_IN.open(newline="") as f_in, CSV_OUT.open("w", newline="") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=OUT_COLS)
        writer.writeheader()

        count = 0
        for row in reader:
            meta = metadata.get(row["QUESTION"])
            if meta is None:
                raise KeyError(f"No JSON metadata for QUESTION: {row['QUESTION'][:80]!r}")
            writer.writerow({**meta, **{c: row[c] for c in ORIG_COLS}})
            count += 1

    print(f"Wrote {count} rows to {CSV_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
