"""ModelDNA v2 - load JSON outputs into Snowflake.

Loads questions.json, responses.json, and scores.json into the QUESTIONS,
RESPONSES, and SCORES tables. Run schema.sql first.

Run:  python load_snowflake.py
"""
import os
import json
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

BATCH = 200  # rows per executemany chunk


def connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "CORE"),
    )


def _chunks(rows, n=BATCH):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def _insert(cur, sql, rows, label):
    for chunk in _chunks(rows):
        cur.executemany(sql, chunk)
    print(f"  loaded {len(rows)} rows into {label}")


def load_all():
    questions = json.load(open("questions.json"))["questions"]
    responses = json.load(open("responses.json"))["responses"]
    scores = json.load(open("scores.json"))["scores"]

    conn = connect()
    cur = conn.cursor()
    try:
        # Truncate so reloads are idempotent.
        for t in ("QUESTIONS", "RESPONSES", "SCORES"):
            cur.execute(f"TRUNCATE TABLE IF EXISTS {t}")

        _insert(cur,
            "INSERT INTO QUESTIONS "
            "(question_id, category, pair_id, lean, coding_rationale, text) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            [(q["id"], q["category"], q["pair_id"], q["lean"],
              q["coding_rationale"], q["text"]) for q in questions],
            "QUESTIONS")

        _insert(cur,
            "INSERT INTO RESPONSES "
            "(response_id, question_id, model, repeat, response) "
            "VALUES (%s,%s,%s,%s,%s)",
            [(r["response_id"], r["question_id"], r["model"], r["repeat"],
              r["response"]) for r in responses],
            "RESPONSES")

        _insert(cur,
            "INSERT INTO SCORES "
            "(response_id, question_id, category, pair_id, lean, model, repeat, "
            "engagement_class, engagement_score, judge_agreement, judge_strict, "
            "judge_lenient, judge_neutral, personal_expression) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(s["response_id"], s["question_id"], s["category"], s["pair_id"],
              s["lean"], s["model"], s["repeat"], s["engagement_class"],
              s["engagement_score"], s["judge_agreement"], s["judge_strict"],
              s["judge_lenient"], s["judge_neutral"], s["personal_expression"])
             for s in scores],
            "SCORES")

        conn.commit()
        print(f"Done. {len(questions)} questions, {len(responses)} responses, "
              f"{len(scores)} scores.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    load_all()
