"""ModelDNA - fetch real model responses and load them into AUDIT_MATRIX.

For every question in questions.json, this asks each available model
(ChatGPT, Claude, Gemini, Grok) the question once, then writes the answers
into the Snowflake table - one row per question x model.

It produces TWO things, so it works whether or not your Snowflake account
allows a script to connect:

  1. ALWAYS writes  rebuild_audit_matrix.sql  - paste it into a Snowflake
     worksheet and Run All. This is the reliable path.
  2. IF your .env Snowflake credentials connect, it ALSO loads the table
     directly - no pasting needed.

REQUIREMENTS - put these in .env (see .env.example):
  ANTHROPIC_API_KEY   -> Claude     (console.anthropic.com)
  OPENAI_API_KEY      -> ChatGPT    (platform.openai.com)
  GEMINI_API_KEY      -> Gemini     (aistudio.google.com)
  XAI_API_KEY         -> Grok       (console.x.ai)  - optional
A missing Grok key just means the run uses 3 models instead of 4.

Run:  python fetch_responses.py
"""
import os
import json

from dotenv import load_dotenv

# Reuse the tested model-calling code from inference.py.
import inference

load_dotenv()

QUESTIONS_FILE = "questions.json"
SQL_OUT = "rebuild_audit_matrix.sql"

# Long-format table: one row per question x model.
TABLE_DDL = """CREATE OR REPLACE TABLE AUDIT_MATRIX (
    question  STRING,   -- the political question (repeats across its 4 model rows)
    model     STRING,   -- which model answered: claude | chatgpt | gemini | grok
    response  STRING,   -- the real answer from that model
    bot1 FLOAT, bot2 FLOAT, bot3 FLOAT, bot4 FLOAT,
    bot5 FLOAT, bot6 FLOAT, bot7 FLOAT   -- scores - filled by the scoring step
)"""


def fetch_all():
    """Ask every model every question once. Returns [(question, model, response), ...]."""
    inference._build_clients()
    models = inference.active_models()
    if not models:
        raise SystemExit(
            "No model API keys found in .env. Add at least ANTHROPIC_API_KEY, "
            "OPENAI_API_KEY and GEMINI_API_KEY, then run again."
        )
    print(f"Models this run: {', '.join(models)}")

    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)["questions"]

    rows = []
    total = len(questions) * len(models)
    done = 0
    for q in questions:
        for model_key, cfg in models.items():
            # Prompt sent AS-IS - no injection. A refusal is a valid response.
            text, err = inference.with_retries(
                lambda c=cfg: inference.dispatch(c["provider"], c["model"], q["text"]),
                f"{q['id']}/{model_key}",
            )
            if err is not None:
                print(f"  FAILED {q['id']} / {model_key}: {err}")
                text = "[NO RESPONSE - API error]"
            rows.append((q["text"], model_key, text))
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{total} responses fetched")
    print(f"Fetched {len(rows)} responses.")
    return rows


def _sql_literal(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def write_sql(rows):
    """Write a paste-and-run SQL file that rebuilds AUDIT_MATRIX with real responses."""
    lines = [
        "-- ModelDNA - AUDIT_MATRIX with REAL model responses.",
        "-- Paste this whole file into a Snowflake worksheet and Run All.",
        "",
        "CREATE DATABASE IF NOT EXISTS MODELDNA_DB;",
        "CREATE SCHEMA   IF NOT EXISTS MODELDNA_DB.CORE;",
        "USE DATABASE MODELDNA_DB;",
        "USE SCHEMA   CORE;",
        "",
        TABLE_DDL + ";",
        "",
        "INSERT INTO AUDIT_MATRIX (question, model, response) VALUES",
    ]
    values = [
        "  (" + ", ".join(_sql_literal(v) for v in (q, m, r)) + ")"
        for q, m, r in rows
    ]
    lines.append(",\n".join(values) + ";")
    lines += [
        "",
        "SELECT COUNT(*) AS rows_loaded FROM AUDIT_MATRIX;",
        "SELECT * FROM AUDIT_MATRIX ORDER BY question, model LIMIT 12;",
    ]
    with open(SQL_OUT, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {SQL_OUT} ({len(rows)} rows).")


def try_snowflake_load(rows):
    """Optionally load straight into Snowflake. Skips cleanly if it cannot connect."""
    if not os.getenv("SNOWFLAKE_ACCOUNT"):
        print("No SNOWFLAKE_ACCOUNT in .env - skipping direct load.")
        print(f"-> Paste {SQL_OUT} into a Snowflake worksheet instead.")
        return
    try:
        import snowflake.connector

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

        conn = snowflake.connector.connect(**params)
        cur = conn.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS MODELDNA_DB")
        cur.execute("CREATE SCHEMA IF NOT EXISTS MODELDNA_DB.CORE")
        cur.execute("USE SCHEMA MODELDNA_DB.CORE")
        cur.execute(TABLE_DDL)
        cur.executemany(
            "INSERT INTO AUDIT_MATRIX (question, model, response) VALUES (%s, %s, %s)",
            rows,
        )
        conn.commit()
        conn.close()
        print(f"Loaded {len(rows)} rows directly into MODELDNA_DB.CORE.AUDIT_MATRIX.")
    except Exception as e:
        print(f"Direct Snowflake load skipped ({e.__class__.__name__}: {e}).")
        print(f"-> Paste {SQL_OUT} into a Snowflake worksheet instead.")


if __name__ == "__main__":
    fetched = fetch_all()
    write_sql(fetched)
    try_snowflake_load(fetched)
