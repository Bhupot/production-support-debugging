-- Stale Pipeline / Pipeline Did Not Run

-- Check data freshness
SELECT
    MAX(loaded_at) AS latest_load
FROM staging_events;

-- Determine age
SELECT
    MAX(loaded_at) AS latest_load,
    DATEDIFF(
        'hour',
        MAX(loaded_at),
        CURRENT_TIMESTAMP()
    ) AS hours_since_last_load\
FROM staging_events;

-- Example monitoring check
SELECT
    CASE
        WHEN MAX(loaded_at) < DATEADD(
            'hour',
            -24,
            CURRENT_TIMESTAMP()
        )
            THEN 'STALE'
        ELSE 'HEALTHY'
    END AS pipeline_health
FROM staging_events;