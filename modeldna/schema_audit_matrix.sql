-- ModelDNA - wide "audit matrix" database + table
-- ===========================================================================
-- Creates the database and ONE wide table: every political question on its own
-- row, with all 4 models' responses and every judge bot's score side by side.
--
-- HOW TO RUN
--   1. Open a Snowflake worksheet.
--   2. Paste and run this whole file. It is idempotent - safe to re-run.
--   3. Then run  load_audit_matrix.py  to ingest the questions and scores.
--
-- Region should support Cortex if you also use the Cortex checks (AWS US West 2).
-- ===========================================================================

CREATE WAREHOUSE IF NOT EXISTS MODELDNA_WH
    WITH WAREHOUSE_SIZE = 'X-SMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;

CREATE DATABASE IF NOT EXISTS MODELDNA_DB;
CREATE SCHEMA   IF NOT EXISTS MODELDNA_DB.CORE;

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    CORE;

-- ---------------------------------------------------------------------------
-- AUDIT_MATRIX - one row per question.
--
--   question_*           the prompt and its pre-assigned party-platform coding
--   response_<model>     the full text each of the 4 models returned
--   <model>_<bot>        that bot's score (0.0-1.0) of that model's answer
--   <model>_mean_score   that model's mean score across all 3 bots
--
-- The three bots - strict, lenient, neutral - are the judges defined in
-- score.py. Each bot scores each model's answer, so there are 4 models x 3
-- bots = 12 score columns. See the note at the bottom of this file on what
-- the bots score (engagement behavior) vs. what "ideology bots" would score.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE AUDIT_MATRIX (
    -- the question -----------------------------------------------------------
    question_id        STRING,
    question_text      STRING,
    category           STRING,
    lean               STRING,   -- 'left' | 'right' | 'neutral' (party-platform coded)
    pair_id            STRING,    -- shared by a left/right pair; NULL for controls
    coding_rationale   STRING,    -- documented sourcing for the lean

    -- one response per model -------------------------------------------------
    response_claude    STRING,
    response_chatgpt   STRING,
    response_gemini    STRING,
    response_grok      STRING,

    -- bot scores: each bot scores each model's answer, 0.0-1.0 ---------------
    claude_strict      FLOAT,
    claude_lenient     FLOAT,
    claude_neutral     FLOAT,

    chatgpt_strict     FLOAT,
    chatgpt_lenient    FLOAT,
    chatgpt_neutral    FLOAT,

    gemini_strict      FLOAT,
    gemini_lenient     FLOAT,
    gemini_neutral     FLOAT,

    grok_strict        FLOAT,
    grok_lenient       FLOAT,
    grok_neutral       FLOAT,

    -- per-model summary: mean of the 3 bots, averaged over repeats -----------
    claude_mean_score  FLOAT,
    chatgpt_mean_score FLOAT,
    gemini_mean_score  FLOAT,
    grok_mean_score    FLOAT,

    loaded_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ---------------------------------------------------------------------------
-- Example reads (run after load_audit_matrix.py has ingested the data)
-- ---------------------------------------------------------------------------

-- Every model's mean score, one row per question:
-- SELECT question_id, lean, category,
--        claude_mean_score, chatgpt_mean_score, gemini_mean_score, grok_mean_score
-- FROM AUDIT_MATRIX ORDER BY category, lean;

-- A left/right pair side by side (swap in any pair_id):
-- SELECT lean, question_text, claude_mean_score, chatgpt_mean_score,
--        gemini_mean_score, grok_mean_score
-- FROM AUDIT_MATRIX WHERE pair_id = 'econ_minwage' ORDER BY lean;

-- Refusal-leaning answers - questions where a model scored below 0.5:
-- SELECT question_id, lean, claude_mean_score
-- FROM AUDIT_MATRIX WHERE claude_mean_score < 0.5 AND category <> 'control';

-- Directional asymmetry per model (left engagement minus right engagement):
-- SELECT AVG(IFF(lean='left', claude_mean_score, NULL))
--          - AVG(IFF(lean='right', claude_mean_score, NULL)) AS claude_asymmetry,
--        AVG(IFF(lean='left', chatgpt_mean_score, NULL))
--          - AVG(IFF(lean='right', chatgpt_mean_score, NULL)) AS chatgpt_asymmetry
-- FROM AUDIT_MATRIX WHERE lean IN ('left','right');

-- ===========================================================================
-- NOTE ON THE BOTS  (this is Decision Box B from your plan)
-- ---------------------------------------------------------------------------
-- The 3 bots wired into score.py (strict / lenient / neutral) vary by how
-- strict they are, and they score one thing: did the model do the task -
-- engagement behavior, mapped full=1.0 / partial=0.5 / refusal=0.0. They do
-- NOT rate "how left-wing / right-wing the answer is."
--
-- This table's column shape is identical either way (model x bot -> score).
-- If you want the bots to be literal LEFT / RIGHT / CENTER ideology raters
-- that score alignment magnitude, only two things change: the bot names in
-- this file and the loader, and the judge prompts in score.py. Your plan's
-- Decision Box B explains the tradeoff - magnitude scores have no ground
-- truth - so make that call deliberately before switching.
-- ===========================================================================
