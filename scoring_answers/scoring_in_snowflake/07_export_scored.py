"""Export RESPONSES_ENRICHED back to a CSV with the 8 bot scores filled in.

Writes to political_questions/main_bot_answering_questions/
responses_export_enriched_scored.csv, leaving the original CSV untouched.
Column ordering matches the input header exactly.

Run:  python 07_export_scored.py
"""
import csv
import os
import pathlib
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

OUT_CSV = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "political_questions"
    / "main_bot_answering_questions"
    / "responses_export_enriched_scored.csv"
)

HEADER = [
    "ORIGINAL_QUESTION", "QUESTION_SOURCE", "CATEGORY", "PROMPT_GIVEN_TO_MODEL",
    "MODEL", "MODEL_RESPONSE",
    "FREEDMAN_BOT", "KIM_BOT", "MACRON_BOT", "MAMDANI_BOT",
    "MILEI_BOT", "AOC_BOT", "PUTIN_BOT", "TRUMP_BOT",
]


def connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SCORING"),
    )


def main():
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT original_question, question_source, category,
                   prompt_given_to_model, model, model_response,
                   freedman_bot, kim_bot, macron_bot, mamdani_bot,
                   milei_bot, aoc_bot, putin_bot, trump_bot
            FROM   MODELDNA_DB.SCORING.RESPONSES_ENRICHED
            ORDER  BY row_id
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(HEADER)
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
