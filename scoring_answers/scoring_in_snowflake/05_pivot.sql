-- ============================================================================
-- Pivot SCORE_AUDIT into the 8 _BOT columns on RESPONSES_ENRICHED.
-- ----------------------------------------------------------------------------
-- Run after 05_score_anthropic.py (pilot OR full) finishes. Pure SQL, no
-- Cortex calls and no Anthropic spend. Works on whatever subset of rows are
-- currently in SCORE_AUDIT - rows without a SCORE_AUDIT entry keep NULL
-- _BOT values.
--
-- Lifted from the original 05b_run_scoring.sql Stage 2 verbatim - this is
-- the same pivot, just isolated so it can run on its own.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    MODELDNA_DB.SCORING;


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


-- Quick post-pivot summary.
SELECT
    COUNT(*)                                          AS total_audit_rows,
    COUNT_IF(score IS NULL)                           AS null_scores,
    COUNT_IF(score BETWEEN 1 AND 10)                  AS in_range_scores,
    MIN(score)                                        AS min_score,
    MAX(score)                                        AS max_score
FROM SCORE_AUDIT;

SELECT
    COUNT(*) AS responses,
    COUNT_IF(freedman_bot IS NULL
          OR kim_bot      IS NULL
          OR macron_bot   IS NULL
          OR mamdani_bot  IS NULL
          OR milei_bot    IS NULL
          OR aoc_bot      IS NULL
          OR putin_bot    IS NULL
          OR trump_bot    IS NULL) AS responses_with_a_null_score
FROM RESPONSES_ENRICHED;
