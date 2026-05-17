# Scoring answers against 8 ideologue corpora

Pipeline that scores each row of
`political_questions/main_bot_answering_questions/responses_export_enriched.csv`
against eight ideologue corpora in `ideologue_corpus/`. For every row the
`MODEL_RESPONSE` is scored 1-10 on **how strongly each ideologue would
agree with it**, grounded in retrieved verbatim passages from that
ideologue's primary sources.

Eight calls per row, 2,787 rows = 22,296 Anthropic API calls per full run.

## Architecture

Snowflake holds the data (corpus chunks, responses, scores). Retrieval and
scoring run in local Python:

- **Storage**: Snowflake `MODELDNA_DB.SCORING.*` (4 tables seeded by `01_schema.sql`).
- **Retrieval**: hybrid. Small-corpus figures (AOC, Kim, Mamdani) get their
  full corpus per call - it's <15K tokens and fits in one prompt. Large-corpus
  figures (Friedman, Milei, Trump, Macron, Putin) use local
  `sentence-transformers/all-MiniLM-L6-v2` embeddings + cosine top-K search,
  cached to `.embeddings_cache.pkl` by `04_embed_corpus.py`.
- **Scoring**: direct Anthropic API via `claude-sonnet-4-6`. Prompt caching
  on the rubric (system) and per-figure passages (user) blocks holds the
  full-run cost to ~$150-250.

The original design used Snowflake Cortex Complete + Cortex Search. That
required Snowflake Standard edition or higher, which is paywalled on trial
accounts. Switching to the Anthropic API avoids that gate and cuts cost.

## Prerequisites

- Local Python env with:
    pip install snowflake-connector-python python-dotenv anthropic \
                sentence-transformers torch tqdm numpy
- `.env` at the repo root containing:
    SNOWFLAKE_ACCOUNT=<org-account>
    SNOWFLAKE_USER=<user>
    SNOWFLAKE_PASSWORD=<password>
    ANTHROPIC_API_KEY=<sk-ant-...>
  Optional overrides default to `MODELDNA_WH` / `MODELDNA_DB` / `SCORING`.

## Run order

| Step | File | What it does | Cost |
|---|---|---|---|
| 0 | `00_reset.sql` (via `run_sql.py`) | Drop and recreate `MODELDNA_DB`; create `MODELDNA_WH` if missing | $0 |
| 1 | `01_schema.sql` (via `run_sql.py`) | Create `SCORING` schema + 4 tables; seed 8-row `IDEOLOGUES` | $0 |
| 2 | `02_load_corpus.py` | Chunk corpus markdown into `CORPUS_CHUNKS` (~650 chunks) | $0 |
| 3 | `03_load_responses.py` | Load the enriched CSV into `RESPONSES_ENRICHED` (2,787 rows) | $0 |
| 4 | `04_embed_corpus.py` | Embed large-figure chunks locally (~2 min on CPU) | $0 |
| 5 | `05_score_anthropic.py --limit 100` | Pilot: score 100 responses across all 8 figures (800 API calls) | ~$3 |
| 6 | `05_pivot.sql` (via `run_sql.py`) | Pivot `SCORE_AUDIT` into the 8 `_BOT` columns | $0 |
| 7 | `06_calibration.sql` (via `run_sql.py`) | Validate distributions + cross-correlations on the pilot | $0 |
| 8 | `05_score_anthropic.py` | Full run: 22,296 API calls, ~45 min with 8 workers | ~$150-250 |
| 9 | `05_score_anthropic.py --retry-only` | Re-score any NULL-score rows with top-K=12 | small |
| 10 | `05_pivot.sql` again | Final pivot now that SCORE_AUDIT is complete | $0 |
| 11 | `06_calibration.sql` | Full sanity check | $0 |
| 12 | `07_export_scored.py` | Write `responses_export_enriched_scored.csv` | $0 |

## Key design notes

- **Comparability across the 8 calls** comes from a byte-identical rubric
  + JSON output spec in the `SYSTEM_RUBRIC` constant inside
  `05_score_anthropic.py`. The only per-call differences are the figure
  name and the retrieved passages.
- **Hybrid retrieval threshold**: figures in
  `SMALL_FIGURE_SLUGS = {ocasio_cortez_alexandria, kim_jong_un, mamdani_zohran}`
  always get their full corpus; everyone else gets top-6 chunks (top-12
  on retry).
- **Prompt caching**: the system rubric is cached across all 22K calls;
  for small figures, the entire passages block is cached per figure (one
  cache write per figure, 2,786 reads each). This is the bulk of the cost
  savings vs. uncached.
- **Idempotency**: every script can be re-run safely.
  `02_load_corpus.py` and `03_load_responses.py` truncate-then-insert.
  `04_embed_corpus.py` skips figures already in the cache unless
  `--force`. `05_score_anthropic.py` skips `(row_id, figure_slug)` pairs
  already present with non-NULL `score`.
- **Audit trail**: `SCORE_AUDIT` holds the full structured output
  (score + evidence quote + reasoning + raw + retrieved chunk IDs + model
  used) so re-pivoting into the `_BOT` columns is free, and a bad-prompt
  postmortem doesn't require re-paying for API calls.
- **Sparse-corpus fallback**: the rubric instructs the model to return
  5 when the retrieved passages do not speak to the response's topic,
  so the failure mode is a detectable score-5 spike (query 6d) rather
  than silent NULLs.
- **`FREEDMAN_BOT` typo** is preserved in the CSV/`RESPONSES_ENRICHED`
  column name; the corpus side uses the correct slug `friedman_milton`.
  The pivot in `05_pivot.sql` and the seed in `01_schema.sql` are the
  only places this mapping is encoded.
- **Concurrency**: `--workers` defaults to 8. The Anthropic SDK has
  built-in retry on rate-limit errors. If your account is on a low RPM
  tier, drop to `--workers 4` or 2.

## Original Cortex pipeline

The Cortex-based files (`04_create_cortex_search.sql`, `05a_scoring_udf.sql`,
`05b_run_scoring.sql`, `05b_pilot.sql`) are still in this directory for
reference. They require Snowflake Standard edition or higher and Cortex
Complete + Cortex Search enabled in the region; if you ever upgrade the
Snowflake account you could resume that path.
