"""Load ideologue corpus markdown into MODELDNA_DB.SCORING.CORPUS_CHUNKS.

Walks scoring_answers/ideologue_corpus/<slug>/*.md, parses YAML frontmatter,
splits the body into ~500-token chunks with ~100-token overlap, and bulk-loads
the result. Skips files prefixed with `_` (e.g. _sources.md).

Run:  python 02_load_corpus.py
"""
import os
import re
import sys
import pathlib
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

CORPUS_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ideologue_corpus"
BATCH = 200
TARGET_TOKENS = 500
OVERLAP_TOKENS = 100
CHARS_PER_TOKEN = 4    # rough heuristic; corpus is small so we don't need tiktoken


def connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SCORING"),
    )


def parse_frontmatter(text):
    """Return (frontmatter_dict, body). Minimal YAML parser — handles the
    flat key: value layout used in _schema.md without pulling in PyYAML."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in head.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


def chunk_text(body, target_tokens=TARGET_TOKENS, overlap_tokens=OVERLAP_TOKENS):
    """Split into chunks of ~target_tokens with overlap_tokens of overlap.

    Strategy: split on paragraph (blank-line) boundaries; pack paragraphs
    into chunks until the rolling char budget is reached; then start a new
    chunk that re-includes the last overlap_tokens worth of characters from
    the previous chunk so quotes that straddle a boundary stay intact.
    Long paragraphs that exceed the target are split on sentence boundaries.
    """
    target_chars = target_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces = []
    for p in paragraphs:
        if len(p) <= target_chars:
            pieces.append(p)
        else:
            sentences = re.split(r"(?<=[.!?])\s+", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) + 1 > target_chars and buf:
                    pieces.append(buf.strip())
                    buf = s
                else:
                    buf = (buf + " " + s).strip() if buf else s
            if buf:
                pieces.append(buf.strip())

    chunks = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
            continue
        if len(current) + 2 + len(piece) <= target_chars:
            current = current + "\n\n" + piece
        else:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars and len(current) > overlap_chars else ""
            current = (tail + "\n\n" + piece).strip() if tail else piece
    if current:
        chunks.append(current)
    return chunks


def collect_rows():
    rows = []
    if not CORPUS_ROOT.exists():
        sys.exit(f"Corpus root not found: {CORPUS_ROOT}")
    for slug_dir in sorted(CORPUS_ROOT.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name.startswith("_"):
            continue
        slug = slug_dir.name
        for md_path in sorted(slug_dir.glob("*.md")):
            if md_path.name.startswith("_"):
                continue
            text = md_path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            title = meta.get("title", md_path.stem)
            date = meta.get("date", "0000-00-00")
            source_type = meta.get("source_type", "")
            source_url = meta.get("source_url", "")
            language_text = meta.get("language_text", "en")
            for idx, chunk in enumerate(chunk_text(body)):
                chunk_id = f"{slug}::{md_path.stem}::{idx:03d}"
                rows.append((
                    chunk_id, slug, title, date, source_type, source_url,
                    language_text, idx, chunk, len(chunk),
                ))
    return rows


def _chunks(seq, n=BATCH):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    rows = collect_rows()
    print(f"prepared {len(rows)} chunks from {CORPUS_ROOT}")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("USE SCHEMA MODELDNA_DB.SCORING")
        cur.execute("TRUNCATE TABLE IF EXISTS CORPUS_CHUNKS")
        sql = (
            "INSERT INTO CORPUS_CHUNKS "
            "(chunk_id, figure_slug, doc_title, doc_date, source_type, "
            " source_url, language_text, chunk_idx, chunk_text, char_len) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        for batch in _chunks(rows):
            cur.executemany(sql, batch)
        conn.commit()

        cur.execute("SELECT figure_slug, COUNT(*) FROM CORPUS_CHUNKS GROUP BY figure_slug ORDER BY 1")
        for slug, n in cur.fetchall():
            print(f"  {slug}: {n} chunks")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
