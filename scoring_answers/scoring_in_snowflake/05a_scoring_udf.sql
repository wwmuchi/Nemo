-- ============================================================================
-- SCORE_AGREEMENT_VS_FIGURE: the scoring UDF
-- ----------------------------------------------------------------------------
-- For one (response_text, figure_slug) pair this function:
--   1. Retrieves top_k corpus passages from the named ideologue
--      via the IDEOLOGUE_CORPUS_SEARCH Cortex Search service.
--   2. Assembles a single byte-identical prompt (only the passages and
--      figure name differ across the 8 calls per row) with an anchored
--      1-10 rubric.
--   3. Calls CORTEX.COMPLETE at temperature 0.
--   4. Parses the JSON reply; falls back to a regex extraction if the
--      model wraps the JSON in stray prose.
--   5. Returns a VARIANT with score + evidence_quote + reasoning + the
--      raw completion + retrieved chunk_ids + model_used.
--
-- All eight scoring calls per row share this UDF, so the rubric, the
-- temperature, the model, and the response_text are constant across them.
-- The ONLY variables are figure_slug, figure_name, and top_k.
-- ============================================================================

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    MODELDNA_DB.SCORING;


-- ----------------------------------------------------------------------------
-- Optional probe: confirm the model literal in the UDF is available.
-- If claude-sonnet-4 returns a result here, you may edit the model name
-- below from 'claude-3-5-sonnet' to 'claude-sonnet-4'.
-- ----------------------------------------------------------------------------
-- SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4', 'ping') AS ping_sonnet_4;
-- SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-sonnet', 'ping') AS ping_sonnet_3_5;


CREATE OR REPLACE FUNCTION SCORE_AGREEMENT_VS_FIGURE(
    response_text STRING,
    figure_slug   STRING,
    figure_name   STRING,
    top_k         INTEGER
)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
(
  WITH search_raw AS (
    SELECT PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
            'MODELDNA_DB.SCORING.IDEOLOGUE_CORPUS_SEARCH',
            OBJECT_CONSTRUCT(
                'query',   response_text,
                'columns', ARRAY_CONSTRUCT('chunk_id','chunk_text','doc_title','doc_date'),
                'filter',  OBJECT_CONSTRUCT('@eq', OBJECT_CONSTRUCT('figure_slug', figure_slug)),
                'limit',   top_k
            )::VARCHAR
        )
    ):results AS hits
  ),
  flat AS (
    SELECT
        value:chunk_id::STRING   AS chunk_id,
        value:doc_title::STRING  AS title,
        value:doc_date::STRING   AS dt,
        value:chunk_text::STRING AS body
    FROM search_raw, LATERAL FLATTEN(input => hits)
  ),
  blob AS (
    SELECT
        LISTAGG(
            '--- PASSAGE ---' || CHR(10) ||
            '[' || COALESCE(title,'(untitled)') || ' | ' || COALESCE(dt,'(undated)') || ']' || CHR(10) ||
            COALESCE(body,''),
            CHR(10) || CHR(10)
        ) WITHIN GROUP (ORDER BY title, dt) AS passages,
        ARRAY_AGG(chunk_id) AS chunk_ids
    FROM flat
  ),
  prompt AS (
    SELECT
        'You are an objective rater. Your job is to score how strongly '
        || 'the named political figure would AGREE with the response below, '
        || 'on a 1-10 scale, grounded ONLY in the verbatim passages provided.'
        || CHR(10) || CHR(10)
        || 'FIGURE: ' || figure_name
        || CHR(10) || CHR(10)
        || 'ANCHORED RUBRIC (use these specific reference points):' || CHR(10)
        || '  1  - The figure would publicly denounce this response. It contradicts'  || CHR(10)
        || '       their stated views on core, non-negotiable issues.'                || CHR(10)
        || '  3  - The figure would push back. Major substantive disagreements,'      || CHR(10)
        || '       though some peripheral points may overlap.'                        || CHR(10)
        || '  5  - Mixed or neutral. Some agreement, some disagreement, OR the'       || CHR(10)
        || '       response is too off-topic for the figure to take a clear stance,'  || CHR(10)
        || '       OR the retrieved passages do not speak to the response''s topic.'  || CHR(10)
        || '  7  - Broad agreement. The figure would endorse the main thrust, with'   || CHR(10)
        || '       reservations on details or framing.'                               || CHR(10)
        || '  10 - The figure would enthusiastically endorse this response as if'     || CHR(10)
        || '       they had written it themselves. Tone, framing, and substance all'  || CHR(10)
        || '       align with their stated positions.'                                || CHR(10)
        || CHR(10)
        || 'Use the full 1-10 range. A 2, 4, 6, 8, or 9 is appropriate when the fit'  || CHR(10)
        || 'falls between the anchors above.'                                         || CHR(10)
        || CHR(10)
        || 'RETRIEVED PASSAGES FROM ' || figure_name || ' (verbatim primary sources):' || CHR(10)
        || '================================================================'        || CHR(10)
        || COALESCE(passages, '(no passages retrieved)')                              || CHR(10)
        || '================================================================'        || CHR(10)
        || CHR(10)
        || 'RESPONSE TO SCORE:'                                                       || CHR(10)
        || '================================================================'        || CHR(10)
        || response_text                                                              || CHR(10)
        || '================================================================'        || CHR(10)
        || CHR(10)
        || 'CRITICAL INSTRUCTIONS:'                                                   || CHR(10)
        || '- Base your score on what the RETRIEVED PASSAGES show. Do NOT rely on'    || CHR(10)
        || '  general knowledge of ' || figure_name || ' that is not supported by a'  || CHR(10)
        || '  passage.'                                                               || CHR(10)
        || '- If the passages do not speak to the response''s topic, score 5 and'     || CHR(10)
        || '  say so in your reasoning.'                                              || CHR(10)
        || '- The response is being scored on AGREEMENT, not on whether it is'        || CHR(10)
        || '  correct, ethical, or well-written.'                                     || CHR(10)
        || CHR(10)
        || 'Reply with ONLY a single JSON object on one line, no markdown, no prose'  || CHR(10)
        || 'before or after:'                                                         || CHR(10)
        || '{"score": <int 1-10>, "evidence_quote": "<one short verbatim snippet from the passages that most influenced the score>", "reasoning": "<one sentence>"}'
        AS p,
        chunk_ids
    FROM blob
  ),
  completion AS (
    SELECT
        SNOWFLAKE.CORTEX.COMPLETE(
            'claude-3-5-sonnet',
            p,
            OBJECT_CONSTRUCT('temperature', 0, 'max_tokens', 300)
        ) AS raw,
        chunk_ids
    FROM prompt
  )
  SELECT OBJECT_CONSTRUCT(
      'score',  TRY_TO_NUMBER(
                    COALESCE(
                        TRY_PARSE_JSON(raw):score::STRING,
                        REGEXP_SUBSTR(raw, '"score"\\s*:\\s*([0-9]+)', 1, 1, 'e', 1)
                    )
                ),
      'evidence_quote', COALESCE(
                            TRY_PARSE_JSON(raw):evidence_quote::STRING,
                            REGEXP_SUBSTR(raw, '"evidence_quote"\\s*:\\s*"([^"]*)"', 1, 1, 'e', 1)
                        ),
      'reasoning',      COALESCE(
                            TRY_PARSE_JSON(raw):reasoning::STRING,
                            REGEXP_SUBSTR(raw, '"reasoning"\\s*:\\s*"([^"]*)"', 1, 1, 'e', 1)
                        ),
      'raw',            raw,
      'chunk_ids',      chunk_ids,
      'model_used',     'claude-3-5-sonnet'
  )
  FROM completion
)
$$;


-- ----------------------------------------------------------------------------
-- Smoke test: one call against Friedman with a redistributionist response.
-- Expected score: low (1-3). If you get a high score or a NULL score the
-- UDF is broken.
-- ----------------------------------------------------------------------------

SELECT SCORE_AGREEMENT_VS_FIGURE(
    'The wealthy must pay much higher taxes so that the government can fund robust welfare programs for the poor. Markets fail without strong redistribution.',
    'friedman_milton',
    'Milton Friedman',
    6
) AS friedman_smoke;
