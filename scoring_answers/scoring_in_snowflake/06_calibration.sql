-- ============================================================================
-- Calibration / sanity checks
-- ----------------------------------------------------------------------------
-- Run after 05_pivot.sql. The cross-correlation query (6f) is the
-- single best end-to-end signal that the rubric and retrieval are working.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- 6a. Per-ideologue mean + stddev. Distributions should differ; flat means
--     across all 8 = the rubric is collapsing everything to 5.
-- ----------------------------------------------------------------------------
SELECT 'friedman' AS bot, AVG(freedman_bot) AS mean_score, STDDEV(freedman_bot) AS sd FROM RESPONSES_ENRICHED
UNION ALL SELECT 'kim',      AVG(kim_bot),     STDDEV(kim_bot)     FROM RESPONSES_ENRICHED
UNION ALL SELECT 'macron',   AVG(macron_bot),  STDDEV(macron_bot)  FROM RESPONSES_ENRICHED
UNION ALL SELECT 'mamdani',  AVG(mamdani_bot), STDDEV(mamdani_bot) FROM RESPONSES_ENRICHED
UNION ALL SELECT 'milei',    AVG(milei_bot),   STDDEV(milei_bot)   FROM RESPONSES_ENRICHED
UNION ALL SELECT 'aoc',      AVG(aoc_bot),     STDDEV(aoc_bot)     FROM RESPONSES_ENRICHED
UNION ALL SELECT 'putin',    AVG(putin_bot),   STDDEV(putin_bot)   FROM RESPONSES_ENRICHED
UNION ALL SELECT 'trump',    AVG(trump_bot),   STDDEV(trump_bot)   FROM RESPONSES_ENRICHED
ORDER BY bot;


-- ----------------------------------------------------------------------------
-- 6b. Polarization gap per row. Flat 5/5/5/5/5/5/5/5 = degenerate response;
--     a response that splits the ideologues hard will surface here.
-- ----------------------------------------------------------------------------
SELECT row_id, model, LEFT(original_question, 80) AS q,
       GREATEST(freedman_bot,kim_bot,macron_bot,mamdani_bot,
                milei_bot,aoc_bot,putin_bot,trump_bot)
     - LEAST(freedman_bot,kim_bot,macron_bot,mamdani_bot,
                milei_bot,aoc_bot,putin_bot,trump_bot) AS gap
FROM   RESPONSES_ENRICHED
ORDER  BY gap DESC NULLS LAST
LIMIT  20;


-- ----------------------------------------------------------------------------
-- 6c. Null count after retry. Must be 0; if not, inspect raw_completion.
-- ----------------------------------------------------------------------------
SELECT COUNT_IF(score IS NULL) AS unparsed_scores,
       COUNT(*)                AS total_audit_rows
FROM   SCORE_AUDIT;


-- ----------------------------------------------------------------------------
-- 6d. Score distribution per ideologue. Healthy: spread across the range.
--     A spike at 5 for an ideologue = retrieval often pulls off-topic
--     passages (or the corpus does not cover that domain).
-- ----------------------------------------------------------------------------
SELECT figure_slug, score, COUNT(*) AS n
FROM   SCORE_AUDIT
GROUP BY 1,2
ORDER BY 1,2;


-- ----------------------------------------------------------------------------
-- 6e. Spot-check 5 representative rows: pull the response + all 8 bot
--     reasonings side by side. Read these by eye to confirm the scores
--     are defensible.
-- ----------------------------------------------------------------------------
SELECT r.row_id,
       LEFT(r.original_question, 80) AS question,
       r.model,
       a.figure_slug,
       a.score,
       a.evidence_quote,
       a.reasoning
FROM   RESPONSES_ENRICHED r
JOIN   SCORE_AUDIT a USING (row_id)
WHERE  r.row_id IN (1, 50, 100, 150, 200)
ORDER BY r.row_id, a.figure_slug;


-- ----------------------------------------------------------------------------
-- 6f. Cross-correlation sanity. This is the strongest single signal.
--     Ideologically similar figures should correlate positively;
--     opposites should correlate negatively or near zero.
-- ----------------------------------------------------------------------------
SELECT CORR(freedman_bot, milei_bot)    AS friedman_milei,   -- expect strongly positive
       CORR(aoc_bot,      mamdani_bot)  AS aoc_mamdani,      -- expect strongly positive
       CORR(trump_bot,    aoc_bot)      AS trump_aoc,        -- expect negative
       CORR(macron_bot,   kim_bot)      AS macron_kim,       -- expect negative / near zero
       CORR(freedman_bot, aoc_bot)      AS friedman_aoc,     -- expect negative
       CORR(trump_bot,    putin_bot)    AS trump_putin       -- expect positive
FROM   RESPONSES_ENRICHED;


-- ----------------------------------------------------------------------------
-- 6g. Per-model bias check. If one judged-model (chatgpt vs claude vs ...)
--     consistently scores much higher/lower across all bots, that suggests
--     a systematic verbosity or hedging difference, not an alignment shift.
-- ----------------------------------------------------------------------------
SELECT model,
       AVG((freedman_bot + kim_bot + macron_bot + mamdani_bot
          + milei_bot + aoc_bot + putin_bot + trump_bot) / 8.0) AS mean_score_across_bots,
       COUNT(*) AS n
FROM   RESPONSES_ENRICHED
GROUP  BY model
ORDER  BY model;
