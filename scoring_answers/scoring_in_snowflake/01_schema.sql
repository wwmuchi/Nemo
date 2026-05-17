-- ============================================================================
-- Schema for ideologue agreement scoring
-- ----------------------------------------------------------------------------
-- Reuses the existing MODELDNA_WH warehouse and MODELDNA_DB database created
-- by modeldna/schema.sql, but lives in a new SCORING schema so it stays
-- isolated from the existing CORE.* tables.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
CREATE SCHEMA IF NOT EXISTS MODELDNA_DB.SCORING;
USE SCHEMA    MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- IDEOLOGUES: fixed 8-row dim table. Single source of truth for the
-- (figure_slug -> bot column name) mapping. Note FREEDMAN_BOT preserves the
-- typo present in the source CSV; the slug uses the correct spelling.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE IDEOLOGUES (
    figure_slug   STRING PRIMARY KEY,
    figure_name   STRING,
    bot_column    STRING,
    tier          STRING                -- 'T1' | 'T2' | 'T3'
);

INSERT INTO IDEOLOGUES VALUES
 ('friedman_milton',          'Milton Friedman',         'FREEDMAN_BOT', 'T1'),
 ('kim_jong_un',              'Kim Jong Un',             'KIM_BOT',      'T3'),
 ('macron_emmanuel',          'Emmanuel Macron',         'MACRON_BOT',   'T2'),
 ('mamdani_zohran',           'Zohran Mamdani',          'MAMDANI_BOT',  'T1'),
 ('milei_javier',             'Javier Milei',            'MILEI_BOT',    'T2'),
 ('ocasio_cortez_alexandria', 'Alexandria Ocasio-Cortez','AOC_BOT',      'T1'),
 ('putin_vladimir',           'Vladimir Putin',          'PUTIN_BOT',    'T3'),
 ('trump_donald',             'Donald Trump',            'TRUMP_BOT',    'T1');


-- ----------------------------------------------------------------------------
-- CORPUS_CHUNKS: one row per ~500-token chunk of an ideologue's source
-- document. Populated by 02_load_corpus.py.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE CORPUS_CHUNKS (
    chunk_id        STRING,
    figure_slug     STRING,
    doc_title       STRING,
    doc_date        STRING,            -- ISO YYYY-MM-DD (YYYY-00-00 sentinel allowed)
    source_type     STRING,
    source_url      STRING,
    language_text   STRING,
    chunk_idx       INT,
    chunk_text      STRING,
    char_len        INT,
    loaded_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);


-- ----------------------------------------------------------------------------
-- RESPONSES_ENRICHED: mirror of responses_export_enriched.csv. Eight _BOT
-- columns are nullable integer scores filled by the scoring pipeline.
-- Column names match the CSV header exactly (including the FREEDMAN typo).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE RESPONSES_ENRICHED (
    row_id                  INT AUTOINCREMENT PRIMARY KEY,
    original_question       STRING,
    question_source         STRING,
    category                STRING,
    prompt_given_to_model   STRING,
    model                   STRING,
    model_response          STRING,
    freedman_bot            NUMBER(2,0),
    kim_bot                 NUMBER(2,0),
    macron_bot              NUMBER(2,0),
    mamdani_bot             NUMBER(2,0),
    milei_bot               NUMBER(2,0),
    aoc_bot                 NUMBER(2,0),
    putin_bot               NUMBER(2,0),
    trump_bot               NUMBER(2,0)
);


-- ----------------------------------------------------------------------------
-- SCORE_AUDIT: one row per (response x ideologue) with the full structured
-- output from Cortex Complete. Survives across pivots so we can re-derive
-- the _BOT columns without re-paying for Cortex calls.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE SCORE_AUDIT (
    row_id              INT,
    figure_slug         STRING,
    score               NUMBER(2,0),
    evidence_quote      STRING,
    reasoning           STRING,
    raw_completion      STRING,
    retrieved_chunk_ids ARRAY,
    model_used          STRING,
    scored_at           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (row_id, figure_slug)
);


-- Quick sanity check after running this file.
SELECT 'IDEOLOGUES'         AS tbl, COUNT(*) AS n FROM IDEOLOGUES
UNION ALL SELECT 'CORPUS_CHUNKS',     COUNT(*) FROM CORPUS_CHUNKS
UNION ALL SELECT 'RESPONSES_ENRICHED',COUNT(*) FROM RESPONSES_ENRICHED
UNION ALL SELECT 'SCORE_AUDIT',       COUNT(*) FROM SCORE_AUDIT;
