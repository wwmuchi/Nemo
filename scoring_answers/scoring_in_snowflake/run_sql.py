"""Run a Snowflake SQL file via the Python connector.

Handles multi-statement files (including the $$...$$ UDF body in
05a_scoring_udf.sql) by using execute_string, which parses Snowflake SQL
properly rather than naively splitting on ';'.

Usage:
    python run_sql.py <path-to-sql-file>

Streams the rows from each statement that returns a result set to stdout.
Reads SNOWFLAKE_ACCOUNT / USER / PASSWORD (and optional WAREHOUSE / DATABASE
/ SCHEMA) from the .env at the repo root.
"""
import os
import sys
import pathlib
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


def connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SCORING"),
    )


def print_results(cur, max_rows=50, max_col_chars=200):
    """Print a single statement's result set if it has one."""
    if cur.description is None:
        return
    col_names = [c.name for c in cur.description]
    rows = cur.fetchmany(max_rows)
    if not rows:
        print(f"    ({', '.join(col_names)}) -> 0 rows")
        return
    print(f"    columns: {', '.join(col_names)}")
    for row in rows:
        clipped = tuple(
            (str(v)[:max_col_chars] + '...') if v is not None and len(str(v)) > max_col_chars
            else v
            for v in row
        )
        print(f"      {clipped}")
    extra = cur.fetchall()
    if extra:
        print(f"      ... ({len(extra)} more rows not shown)")


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python run_sql.py <path-to-sql-file>")

    sql_path = pathlib.Path(sys.argv[1]).resolve()
    if not sql_path.exists():
        sys.exit(f"SQL file not found: {sql_path}")

    sql_text = sql_path.read_text(encoding="utf-8")
    print(f"== Running {sql_path} ==")

    conn = connect()
    try:
        # execute_string returns a list of cursors, one per statement.
        cursors = conn.execute_string(sql_text, remove_comments=False)
        for i, cur in enumerate(cursors, start=1):
            print(f"\n[stmt {i}] {cur.query.strip().splitlines()[0][:120]}")
            print_results(cur)
        conn.commit()
    finally:
        conn.close()

    print(f"\n== Done {sql_path.name} ==")


if __name__ == "__main__":
    main()
