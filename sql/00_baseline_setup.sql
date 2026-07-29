-- Staging table
-- Simulates raw/event data landed from AWS S3 and loaded by Matillion.

CREATE OR REPLACE TABLE staging_events (
    event_id INTEGER,
    provider_id INTEGER,
    event_type STRING,
    status STRING,
    event_timestamp TIMESTAMP,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Provider lookup table
-- Used for JOIN and NULL-handling diagnostic scenarios.

CREATE OR REPLACE TABLE dim_provider_lookup (
    provider_id INTEGER,
    provider_name STRING,
    specialty STRING
);

-- Curated target table
-- Simulates the downstream table populated by the transformation pipeline.

CREATE OR REPLACE TABLE curated_daily_events (
    event_date DATE,
    event_type STRING,
    status STRING,
    event_count INTEGER
);