-- Clear target so the script can be rerun safely during testing.
TRUNCATE TABLE curated_daily_events;

-- Aggregate staging events into the curated layer.

INSERT INTO curated_daily_events (
    event_date,
    event_type,
    status,
    event_count
)
SELECT
    DATE(event_timestamp) AS event_date,
    event_type,
    status,
    COUNT(*) AS event_count
FROM staging_events
GROUP BY
    DATE(event_timestamp),
    event_type,
    status;

-- Validation
SELECT *
FROM curated_daily_events
ORDER BY
    event_date,
    event_type,
    status;