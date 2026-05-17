-- ============================================================================
-- Pilot scoring run: score the first 100 responses only.
-- ----------------------------------------------------------------------------
-- Identical to 05b_run_scoring.sql except for the WHERE r.row_id BETWEEN 1 AND
-- 100 scope on Stages 1 and 1.5. Stage 2 pivot leaves the other ~2,687 rows'
-- _BOT columns NULL, which is fine — the full run will TRUNCATE SCORE_AUDIT
-- and re-score everything from scratch.
--
-- Cost: ~100 x 8 = 800 Cortex Complete calls (~$2-7, ~15-25 min on X-SMALL).
-- Run before 05b_run_scoring.sql to validate the rubric/retrieval end-to-end.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- Stage 1: score the first 100 responses against all 8 ideologues.
-- T3 figures (Kim, Putin) get top_k = 8 because their corpora are sparser.
-- ----------------------------------------------------------------------------

TRUNCATE TABLE SCORE_AUDIT;

INSERT INTO SCORE_AUDIT
    (row_id, figure_slug, score, evidence_quote, reasoning,
     raw_completion, retrieved_chunk_ids, model_used)
SELECT
    r.row_id,
    i.figure_slug,
    v:score::NUMBER(2,0),
    v:evidence_quote::STRING,
    v:reasoning::STRING,
    v:raw::STRING,
    v:chunk_ids,
    v:model_used::STRING
FROM   RESPONSES_ENRICHED r
CROSS JOIN IDEOLOGUES i,
LATERAL (
    SELECT SCORE_AGREEMENT_VS_FIGURE(
        r.model_response,
        i.figure_slug,
        i.figure_name,
        CASE WHEN i.tier = 'T3' THEN 8 ELSE 6 END
    ) AS v
)
WHERE r.row_id BETWEEN 1 AND 100;


-- ----------------------------------------------------------------------------
-- Stage 1.5: retry any rows where the score failed to parse.
-- Wider retrieval (top_k=12) to reduce sparse-corpus regression to 5.
-- Scoped to the same pilot window.
-- ----------------------------------------------------------------------------

MERGE INTO SCORE_AUDIT tgt
USING (
    SELECT a.row_id, a.figure_slug,
           SCORE_AGREEMENT_VS_FIGURE(r.model_response, a.figure_slug, i.figure_name, 12) AS v
    FROM   SCORE_AUDIT a
    JOIN   RESPONSES_ENRICHED r USING (row_id)
    JOIN   IDEOLOGUES i ON i.figure_slug = a.figure_slug
    WHERE  a.score IS NULL
      AND  a.row_id BETWEEN 1 AND 100
) src
ON  tgt.row_id = src.row_id
AND tgt.figure_slug = src.figure_slug
WHEN MATCHED THEN UPDATE SET
    tgt.score          = src.v:score::NUMBER(2,0),
    tgt.evidence_quote = src.v:evidence_quote::STRING,
    tgt.reasoning      = src.v:reasoning::STRING,
    tgt.raw_completion = src.v:raw::STRING,
    tgt.retrieved_chunk_ids = src.v:chunk_ids,
    tgt.scored_at      = CURRENT_TIMESTAMP();


-- ----------------------------------------------------------------------------
-- Stage 2: pivot SCORE_AUDIT into the 8 _BOT columns. Pure SQL, no Cortex.
-- Only the 100 piloted rows will be updated; the rest stay NULL until the
-- full 05b_run_scoring.sql executes.
-- ----------------------------------------------------------------------------

UPDATE RESPONSES_ENRICHED r
SET    freedman_bot = s.freedman_bot,
       kim_bot      = s.kim_bot,
       macron_bot   = s.macron_bot,
       mamdani_bot  = s.mamdani_bot,
       milei_bot    = s.milei_bot,
       aoc_bot      = s.aoc_bot,
       putin_bot    = s.putin_bot,
       trump_bot    = s.trump_bot
FROM (
    SELECT row_id,
        MAX(IFF(figure_slug='friedman_milton',          score, NULL)) AS freedman_bot,
        MAX(IFF(figure_slug='kim_jong_un',              score, NULL)) AS kim_bot,
        MAX(IFF(figure_slug='macron_emmanuel',          score, NULL)) AS macron_bot,
        MAX(IFF(figure_slug='mamdani_zohran',           score, NULL)) AS mamdani_bot,
        MAX(IFF(figure_slug='milei_javier',             score, NULL)) AS milei_bot,
        MAX(IFF(figure_slug='ocasio_cortez_alexandria', score, NULL)) AS aoc_bot,
        MAX(IFF(figure_slug='putin_vladimir',           score, NULL)) AS putin_bot,
        MAX(IFF(figure_slug='trump_donald',             score, NULL)) AS trump_bot
    FROM   SCORE_AUDIT
    GROUP BY row_id
) s
WHERE  r.row_id = s.row_id;


-- ----------------------------------------------------------------------------
-- Quick post-pilot summary. Run 06_calibration.sql for the full sanity suite.
-- ----------------------------------------------------------------------------

SELECT
    COUNT(*)                                          AS total_audit_rows,
    COUNT_IF(score IS NULL)                           AS null_scores,
    COUNT_IF(score BETWEEN 1 AND 10)                  AS in_range_scores,
    MIN(score)                                        AS min_score,
    MAX(score)                                        AS max_score
FROM SCORE_AUDIT;

SELECT
    COUNT(*) AS piloted_responses,
    COUNT_IF(freedman_bot IS NULL
          OR kim_bot      IS NULL
          OR macron_bot   IS NULL
          OR mamdani_bot  IS NULL
          OR milei_bot    IS NULL
          OR aoc_bot      IS NULL
          OR putin_bot    IS NULL
          OR trump_bot    IS NULL) AS piloted_responses_with_a_null_score
FROM RESPONSES_ENRICHED
WHERE row_id BETWEEN 1 AND 100;
