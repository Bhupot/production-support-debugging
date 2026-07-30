-- STEP 1 - Introduce the failure.
-- Simulate a Matillion job accidentally rerunning the same batch.
INSERT INTO staging_events
SELECT *
FROM staging_events;

-- STEP 2 - Confirm the anomaly.
SELECT COUNT(*) AS total_rows
FROM staging_events;


-- STEP 3 - Check duplicate business keys.
SELECT
    event_id,
    COUNT(*) AS duplicate_count
FROM staging_events
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY event_id;

-- STEP 4 - Determine how widespread the duplication is.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT event_id) AS unique_events,
    COUNT(*) - COUNT(DISTINCT event_id) AS duplicate_rows
FROM staging_events;


-- STEP 5 - Fix
-- Keep one row for each event.
CREATE OR REPLACE TABLE staging_events AS
SELECT
    event_id,
    provider_id,
    event_type,
    status,
    event_timestamp,
    loaded_at
FROM staging_events
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY event_id
    ORDER BY loaded_at
) = 1;


-- STEP 6 - Validate fix.
SELECT
    event_id,
    COUNT(*)
FROM staging_events
GROUP BY event_id
HAVING COUNT(*) >=1;