"""ModelDNA - load the wide AUDIT_MATRIX table into Snowflake.

Pivots responses.json + scores.json into one row per question:

    question | response_claude .. response_grok | <model>_<bot> scores | means

Run order:
    1. schema_audit_matrix.sql   (once, in a Snowflake worksheet - creates the table)
    2. inference.py              (produces responses.json)
    3. score.py                  (produces scores.json)
    4. python load_audit_matrix.py

For a dry run without real API calls, run make_sample_data.py first - it
writes synthetic responses.json / scores.json that this loader will ingest.

Credentials are read from .env (see .env.example).
"""
import os
import json
from collections import defaultdict

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

MODELS = ["claude", "chatgpt", "gemini", "grok"]
BOTS = ["strict", "lenient", "neutral"]          # the 3 judges defined in score.py
CLASS_TO_SCORE = {"full_engagement": 1.0, "partial": 0.5, "full_refusal": 0.0}

# Column order must match the INSERT below and the table in schema_audit_matrix.sql.
COLUMNS = (
    ["question_id", "question_text", "category", "lean", "pair_id", "coding_rationale"]
    + [f"response_{m}" for m in MODELS]
    + [f"{m}_{bot}" for m in MODELS for bot in BOTS]
    + [f"{m}_mean_score" for m in MODELS]
)


def connect():
    # Auth method is set by SNOWFLAKE_AUTHENTICATOR in .env:
    #   externalbrowser -> opens a browser to log in (works with MFA)
    #   unset / snowflake -> plain username + password
    params = dict(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "CORE"),
    )
    if os.getenv("SNOWFLAKE_AUTHENTICATOR", "snowflake") == "externalbrowser":
        params["authenticator"] = "externalbrowser"
    else:
        params["password"] = os.getenv("SNOWFLAKE_PASSWORD")
    return snowflake.connector.connect(**params)


def _mean(values):
    """Mean of the non-null values, rounded; None if there are none."""
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _load_json(path, key):
    if not os.path.exists(path):
        raise SystemExit(
            f"Missing {path}. Run the pipeline first "
            f"(inference.py + score.py), or make_sample_data.py for a dry run."
        )
    with open(path) as f:
        return json.load(f)[key]


def build_rows(questions_file="questions.json",
               responses_file="responses.json",
               scores_file="scores.json"):
    """Collapse the per-repeat response/score records into one wide row per question."""
    questions = _load_json(questions_file, "questions")
    responses = _load_json(responses_file, "responses")
    scores = _load_json(scores_file, "scores")

    # Representative response text per (question, model): the earliest repeat.
    resp_text = {}
    for r in responses:
        key = (r["question_id"], r["model"])
        if key not in resp_text or r["repeat"] < resp_text[key][0]:
            resp_text[key] = (r["repeat"], r["response"])

    # Each bot's numeric scores across all repeats, per (question, model, bot).
    bot_values = defaultdict(list)
    for s in scores:
        for bot in BOTS:
            cls = s.get(f"judge_{bot}")
            if cls in CLASS_TO_SCORE:
                bot_values[(s["question_id"], s["model"], bot)].append(
                    CLASS_TO_SCORE[cls])

    rows = []
    for q in questions:
        qid = q["id"]
        row = {
            "question_id": qid,
            "question_text": q["text"],
            "category": q["category"],
            "lean": q["lean"],
            "pair_id": q["pair_id"],
            "coding_rationale": q["coding_rationale"],
        }
        for model in MODELS:
            row[f"response_{model}"] = resp_text.get((qid, model), (None, None))[1]
            per_bot_means = []
            for bot in BOTS:
                score = _mean(bot_values.get((qid, model, bot), []))
                row[f"{model}_{bot}"] = score
                per_bot_means.append(score)
            row[f"{model}_mean_score"] = _mean(per_bot_means)
        rows.append(row)
    return rows


def load(rows):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE IF EXISTS AUDIT_MATRIX")
        placeholders = ",".join(["%s"] * len(COLUMNS))
        sql = f"INSERT INTO AUDIT_MATRIX ({','.join(COLUMNS)}) VALUES ({placeholders})"
        cur.executemany(sql, [tuple(r.get(c) for c in COLUMNS) for r in rows])
        conn.commit()
        print(f"Loaded {len(rows)} rows into MODELDNA_DB.CORE.AUDIT_MATRIX")
    finally:
        conn.close()


if __name__ == "__main__":
    audit_rows = build_rows()
    load(audit_rows)
