"""Load responses_export_enriched.csv into MODELDNA_DB.SCORING.RESPONSES_ENRICHED.

Inserts the 6 text columns; the 8 _BOT columns are left NULL — they get
populated by the Cortex scoring pipeline. Truncate-then-insert so reloads
are idempotent.

Run:  python 03_load_responses.py
"""
import csv
import os
import pathlib
import sys
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()
csv.field_size_limit(sys.maxsize)

CSV_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "political_questions"
    / "main_bot_answering_questions"
    / "responses_export_enriched.csv"
)
BATCH = 100


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
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                r["ORIGINAL_QUESTION"],
                r["QUESTION_SOURCE"],
                r["CATEGORY"],
                r["PROMPT_GIVEN_TO_MODEL"],
                r["MODEL"],
                r["MODEL_RESPONSE"],
            )
            for r in reader
        ]
    print(f"prepared {len(rows)} rows from {CSV_PATH.name}")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("USE SCHEMA MODELDNA_DB.SCORING")
        cur.execute("TRUNCATE TABLE IF EXISTS RESPONSES_ENRICHED")
        sql = (
            "INSERT INTO RESPONSES_ENRICHED "
            "(original_question, question_source, category, "
            " prompt_given_to_model, model, model_response) "
            "VALUES (%s,%s,%s,%s,%s,%s)"
        )
        for i in range(0, len(rows), BATCH):
            cur.executemany(sql, rows[i:i + BATCH])
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM RESPONSES_ENRICHED")
        print(f"  loaded {cur.fetchone()[0]} rows into RESPONSES_ENRICHED")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
