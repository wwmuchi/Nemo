# Scoring answers against 8 ideologue corpora

Pipeline that scores each row of
`political_questions/main_bot_answering_questions/responses_export_enriched.csv`
against eight ideologue corpora in `ideologue_corpus/`. For every row the
`MODEL_RESPONSE` is scored 1-10 on **how strongly each ideologue would
agree with it**, grounded in retrieved verbatim passages from that
ideologue's primary sources.

Eight calls per row, 200 rows = 1,600 Cortex Complete calls per run.

## Prerequisites

- Snowflake account with Cortex Search + Cortex Complete enabled in the
  region. Verify with the queries at the top of `04_create_cortex_search.sql`.
- Existing `MODELDNA_WH` warehouse and `MODELDNA_DB` database from
  `modeldna/schema.sql`.
- Local Python env with `snowflake-connector-python` and `python-dotenv`.
- `.env` containing `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`,
  `SNOWFLAKE_PASSWORD` (same vars as `modeldna/load_snowflake.py`).

## Run order

1. **`01_schema.sql`** — create `MODELDNA_DB.SCORING.*` tables and seed
   the 8-row `IDEOLOGUES` dim table.
2. **`02_load_corpus.py`** — chunk and load corpus markdown into
   `CORPUS_CHUNKS`. ~650 chunks expected.
3. **`03_load_responses.py`** — load the enriched CSV into
   `RESPONSES_ENRICHED`. ~200 rows.
4. **`04_create_cortex_search.sql`** — create the `IDEOLOGUE_CORPUS_SEARCH`
   service and smoke-test retrieval.
5. **`05a_scoring_udf.sql`** — install the
   `SCORE_AGREEMENT_VS_FIGURE` UDF and smoke-test one call.
6. **`05b_run_scoring.sql`** — the main run: Stage 1 inserts into
   `SCORE_AUDIT`, Stage 1.5 retries unparsed rows, Stage 2 pivots into
   the 8 `_BOT` columns. **~25-45 min on X-SMALL.**
7. **`06_calibration.sql`** — sanity-check the result (per-bot means,
   distribution, cross-correlation, manual spot checks).
8. **`07_export_scored.py`** — write
   `responses_export_enriched_scored.csv` next to the original CSV.

## Key design notes

- **Comparability across the 8 calls** comes from a byte-identical prompt
  template + anchored 1-10 rubric in `05a_scoring_udf.sql`. The only
  per-call differences are the figure name and the retrieved corpus
  passages.
- **Retrieval** uses Cortex Search filtered by `figure_slug`, top-K=6
  (bumped to 8 for sparser T3 figures Kim and Putin).
- **Model**: `claude-3-5-sonnet` by default. If `claude-sonnet-4` is
  available in your region (probe in `04_create_cortex_search.sql`),
  edit the model literal inside the UDF in `05a_scoring_udf.sql`.
- **Audit trail**: `SCORE_AUDIT` holds the full structured output
  (score + evidence quote + reasoning + raw + retrieved chunk IDs) so
  re-pivoting into the `_BOT` columns is free — no re-paying for Cortex
  if you find a bug downstream.
- **Sparse-corpus fallback**: the rubric instructs the model to return
  5 when the retrieved passages do not speak to the response's topic,
  so the failure mode is a detectable score-5 spike (query 6d) rather
  than silent NULLs.
- **`FREEDMAN_BOT` typo** is preserved in the CSV/RESPONSES_ENRICHED
  column name; the corpus side uses the correct slug `friedman_milton`.
  The pivot in `05b_run_scoring.sql` and the seed in `01_schema.sql`
  are the only places this mapping is encoded.
