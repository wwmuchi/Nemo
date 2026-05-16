"""Generate insert_audit_matrix.sql - plain INSERT statements for AUDIT_MATRIX.

Lets you populate the table by pasting SQL into a Snowflake worksheet, with no
Python connection / authentication needed. Run this once; it writes the .sql file.
"""
import sys
import types

# build_rows lives in load_audit_matrix.py, which imports snowflake at module
# level. We only need build_rows (no DB call), so stub the import.
fake = types.ModuleType("snowflake")
fake.connector = types.ModuleType("connector")
sys.modules["snowflake"] = fake
sys.modules["snowflake.connector"] = fake.connector

from load_audit_matrix import build_rows, COLUMNS  # noqa: E402

OUT = "insert_audit_matrix.sql"


def sql_literal(value):
    """Render a Python value as a Snowflake SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    # string: single-quote and escape embedded quotes
    return "'" + str(value).replace("'", "''") + "'"


def main():
    rows = build_rows()
    lines = [
        "-- ModelDNA - populate AUDIT_MATRIX by pasting this into a Snowflake worksheet.",
        "-- Run schema_audit_matrix.sql first (it creates the table).",
        "",
        "USE DATABASE MODELDNA_DB;",
        "USE SCHEMA CORE;",
        "",
        "TRUNCATE TABLE IF EXISTS AUDIT_MATRIX;",
        "",
        f"INSERT INTO AUDIT_MATRIX ({', '.join(COLUMNS)}) VALUES",
    ]
    value_rows = []
    for r in rows:
        cells = ", ".join(sql_literal(r.get(c)) for c in COLUMNS)
        value_rows.append(f"  ({cells})")
    lines.append(",\n".join(value_rows) + ";")
    lines.append("")
    lines.append("SELECT COUNT(*) AS rows_loaded FROM AUDIT_MATRIX;")

    with open(OUT, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {OUT} - {len(rows)} rows.")


if __name__ == "__main__":
    main()
