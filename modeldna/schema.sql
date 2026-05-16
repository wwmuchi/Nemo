-- ModelDNA v2 - Snowflake schema
-- Run once in a Snowflake worksheet (region must support Cortex, e.g. AWS US West 2).

CREATE WAREHOUSE IF NOT EXISTS MODELDNA_WH
    WITH WAREHOUSE_SIZE = 'X-SMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;

CREATE DATABASE IF NOT EXISTS MODELDNA_DB;
CREATE SCHEMA   IF NOT EXISTS MODELDNA_DB.CORE;

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;
USE SCHEMA    CORE;

-- The political question set (one row per question).
CREATE OR REPLACE TABLE QUESTIONS (
    question_id      STRING,
    category         STRING,
    pair_id          STRING,   -- shared by a left/right pair; NULL for controls
    lean             STRING,   -- 'left' | 'right' | 'neutral'
    coding_rationale STRING,   -- documented party-platform sourcing
    text             STRING
);

-- Raw model output: one row per question x model x repeat.
CREATE OR REPLACE TABLE RESPONSES (
    response_id  STRING,
    question_id  STRING,
    model        STRING,
    repeat       INT,
    response     STRING
);

-- Behavioral scores: one row per response, from the 3-judge classification.
CREATE OR REPLACE TABLE SCORES (
    response_id         STRING,
    question_id         STRING,
    category            STRING,
    pair_id             STRING,
    lean                STRING,
    model               STRING,
    repeat              INT,
    engagement_class    STRING,   -- majority verdict of the 3 judges
    engagement_score    FLOAT,    -- 1.0 full / 0.5 partial / 0.0 refusal
    judge_agreement     FLOAT,    -- fraction of judges agreeing (inter-rater)
    judge_strict        STRING,
    judge_lenient       STRING,
    judge_neutral       STRING,
    personal_expression BOOLEAN
);

-- Cortex availability check (optional - confirms the region supports Cortex).
-- SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b', 'hi');
