-- Incident 02 NULL + NOT IN
-- Introduce NULL 
INSERT INTO staging_events (
    event_id,
    provider_id,
    event_type,
    status,
    event_timestamp
)
VALUES (
    11,
    NULL,
    'AUTHORIZATION',
    'APPROVED',
    CURRENT_TIMESTAMP()
);


-- Buggy query
SELECT provider_id
FROM dim_provider_lookup
WHERE provider_id NOT IN (
    SELECT provider_id
    FROM staging_events
);


-- Diagnostic check
SELECT COUNT(*) AS null_provider_ids
FROM staging_events
WHERE provider_id IS NULL;


-- Correct solution
SELECT p.provider_id
FROM dim_provider_lookup p
WHERE NOT EXISTS (
    SELECT 1
    FROM staging_events e
    WHERE e.provider_id = p.provider_id
);

SELECT e.provider_id
FROM staging_events e
WHERE NOT EXISTS (
    SELECT 1
    FROM dim_provider_lookup p
    WHERE p.provider_id = e.provider_id
);