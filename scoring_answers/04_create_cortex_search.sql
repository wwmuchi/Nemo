-- ============================================================================
-- Cortex Search Service over CORPUS_CHUNKS
-- ----------------------------------------------------------------------------
-- Hybrid (vector + keyword) retrieval. The figure_slug attribute is what
-- lets the scoring UDF restrict each retrieval to a single ideologue's
-- corpus while keeping all eight bots on identical retrieval mechanics.
--
-- Run this AFTER 02_load_corpus.py has populated CORPUS_CHUNKS.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- 0. Availability check.
--    Cortex Search requires Snowflake Standard edition or higher and is
--    limited to specific regions (AWS us-east-1, us-west-2, eu-central-1,
--    eu-west-1, ap-southeast-2; Azure East US 2, West Europe; GCP us-central1).
-- ----------------------------------------------------------------------------

SELECT CURRENT_REGION()  AS region,
       CURRENT_ACCOUNT() AS account,
       CURRENT_VERSION() AS version;

-- Ping the Complete API with a known-good model. If this errors, the
-- region does not have Cortex Complete enabled.
SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-sonnet', 'ping') AS ping_3_5_sonnet;

-- Optional: probe Claude 4. If this succeeds, edit 05a_scoring_udf.sql to
-- use 'claude-sonnet-4'. If it errors with "model not found", leave the
-- UDF on the 3.5 default.
-- SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4', 'ping') AS ping_sonnet_4;


-- ----------------------------------------------------------------------------
-- 1. Cortex Search Service.
--    ATTRIBUTES is the critical bit: it lets us filter by figure_slug at
--    retrieval time so each ideologue's scoring call only sees their own
--    corpus.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE CORTEX SEARCH SERVICE IDEOLOGUE_CORPUS_SEARCH
    ON chunk_text
    ATTRIBUTES figure_slug, doc_title, doc_date, source_type, source_url, chunk_id
    WAREHOUSE = MODELDNA_WH
    TARGET_LAG = '365 days'           -- corpus is static; refresh manually
    EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
    AS (
        SELECT chunk_id,
               chunk_text,
               figure_slug,
               doc_title,
               doc_date,
               source_type,
               source_url
        FROM   MODELDNA_DB.SCORING.CORPUS_CHUNKS
    );


-- ----------------------------------------------------------------------------
-- 2. Verify the service was created and is ready.
-- ----------------------------------------------------------------------------

SHOW CORTEX SEARCH SERVICES IN SCHEMA MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- 3. Smoke-test retrieval: pull 3 Friedman chunks relevant to "free markets".
--    If this returns 3 plausible passages, retrieval is wired up correctly.
-- ----------------------------------------------------------------------------

SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'MODELDNA_DB.SCORING.IDEOLOGUE_CORPUS_SEARCH',
        OBJECT_CONSTRUCT(
            'query',   'free markets and individual liberty',
            'columns', ARRAY_CONSTRUCT('chunk_id','doc_title','doc_date','chunk_text'),
            'filter',  OBJECT_CONSTRUCT('@eq', OBJECT_CONSTRUCT('figure_slug', 'friedman_milton')),
            'limit',   3
        )::VARCHAR
    )
):results AS friedman_smoke_test;
