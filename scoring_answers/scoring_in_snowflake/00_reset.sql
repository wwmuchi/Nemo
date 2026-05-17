-- ============================================================================
-- Fresh-start reset for the ideologue scoring pipeline
-- ----------------------------------------------------------------------------
-- DESTRUCTIVE. Drops MODELDNA_DB entirely (all schemas, all tables, all data),
-- then recreates the warehouse (if missing) and an empty database. Intended
-- to be run once before 01_schema.sql when you want to wipe the slate.
--
-- Run with run_sql.py from scoring_answers/scoring_in_snowflake/.
-- ============================================================================

DROP DATABASE IF EXISTS MODELDNA_DB;

CREATE WAREHOUSE IF NOT EXISTS MODELDNA_WH
    WITH WAREHOUSE_SIZE = 'X-SMALL'
         AUTO_SUSPEND   = 60
         AUTO_RESUME    = TRUE;

CREATE DATABASE MODELDNA_DB;

USE WAREHOUSE MODELDNA_WH;
USE DATABASE  MODELDNA_DB;

SELECT CURRENT_WAREHOUSE() AS warehouse,
       CURRENT_DATABASE()  AS database,
       CURRENT_REGION()    AS region,
       CURRENT_VERSION()   AS version;
