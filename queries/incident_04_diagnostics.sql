
-- Type-Mismatch Join

CREATE OR REPLACE TEMP TABLE provider_string_source (
    provider_id STRING,
    provider_name STRING
);

INSERT INTO provider_string_source
VALUES
    ('101', 'Provider A'),
    ('102', 'Provider B'),
    ('ABC', 'Invalid Provider');

-- Inspect types
DESCRIBE TABLE staging_events;

DESCRIBE TABLE provider_string_source;

-- Validate source values
SELECT * FROM provider_string_source;

-- Identify non-numeric IDs
SELECT * FROM provider_string_source WHERE TRY_TO_NUMBER(provider_id) IS NULL;

-- Safe join
SELECT
    e.event_id,
    e.provider_id,
    p.provider_name
FROM staging_events e
LEFT JOIN provider_string_source p
    ON e.provider_id = TRY_TO_NUMBER(p.provider_id);