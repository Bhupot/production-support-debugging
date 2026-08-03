# Incident 04 — Type-Mismatch Join Silently Drops Rows

## Overview
A simulated production transformation returned fewer rows than expected after
joining event data to a provider lookup table.

The query executed successfully and did not generate an error.

The issue was caused by inconsistent provider identifiers between the two
sources.

One source stored `provider_id` as an INTEGER while another stored it as a
STRING and contained invalid/non-numeric values.

This scenario demonstrates the importance of validating schema and data types
before assuming that join logic itself is incorrect.

## Symptom
A provider enrichment query returned fewer matched rows than expected.

Example query:

```sql
SELECT
    e.event_id,
    e.provider_id,
    p.provider_name
FROM staging_events e
JOIN provider_string_source p
    ON e.provider_id = p.provider_id;
```

The query completed successfully.

However:

```text
Some expected providers were missing.
No Snowflake error was produced.
```

## Diagnostic Process

### 1. Establish expected event volume
```sql
SELECT COUNT(*) AS staging_rows
FROM staging_events;
```

Example:

```text
10
```


### 2. Check joined row count
```sql
SELECT COUNT(*) AS joined_rows
FROM staging_events e
JOIN provider_string_source p
    ON e.provider_id = p.provider_id;
```

Example:

```text
6
```

This confirms that rows are being lost during the join.


### 3. Use LEFT JOIN to expose unmatched rows
Instead of immediately changing the join logic, identify which rows failed to
match.

```sql
SELECT
    e.event_id,
    e.provider_id,
    p.provider_id AS lookup_provider_id,
    p.provider_name
FROM staging_events e
LEFT JOIN provider_string_source p
    ON e.provider_id = p.provider_id
WHERE p.provider_id IS NULL;
```

This reveals the specific providers being dropped.


### 4. Inspect data types on both sides
```sql
DESCRIBE TABLE staging_events;
```

Example:

```text
provider_id INTEGER
```

Then:

```sql
DESCRIBE TABLE provider_string_source;
```

Example:

```text
provider_id VARCHAR
```

This confirms schema inconsistency.


### 5. Inspect the actual lookup values
```sql
SELECT *
FROM provider_string_source;
```

Example:

```text
101
102
103
ABC
104 
```

Potential issues include:

```text
Non-numeric values
Leading/trailing spaces
Different formatting
Different data types
```


### 6. Identify invalid numeric identifiers
```sql
SELECT *
FROM provider_string_source
WHERE TRY_TO_NUMBER(TRIM(provider_id)) IS NULL;
```

Example result:

```text
ABC
```

This identifies records that cannot be safely converted to numeric provider
IDs.


### 7. Test normalized values
```sql
SELECT
    provider_id,
    TRY_TO_NUMBER(TRIM(provider_id)) AS normalized_provider_id
FROM provider_string_source;
```

This makes it possible to compare the underlying values directly.


## Root Cause
`provider_id` was not standardized across the two datasets.

The staging table stored the key as:

```text
INTEGER
```

while the provider source stored it as:

```text
VARCHAR
```

Some values also contained formatting problems or invalid identifiers.

This caused expected join matches to be lost.

The transformation itself was syntactically valid, so no runtime SQL error was
generated.


## Fix
Normalize the lookup value before joining.

```sql
SELECT
    e.event_id,
    e.provider_id,
    p.provider_name
FROM staging_events e
LEFT JOIN provider_string_source p
    ON e.provider_id = TRY_TO_NUMBER(TRIM(p.provider_id));
```

Using `TRY_TO_NUMBER` is safer than `TO_NUMBER` because invalid values return
NULL instead of causing the whole query to fail.


## Better Long-Term Fix
The preferred solution is to normalize data types in the staging layer.

For example:

```sql
CREATE OR REPLACE VIEW stg_provider AS
SELECT
    TRY_TO_NUMBER(TRIM(provider_id)) AS provider_id,
    provider_name
FROM provider_string_source;
```

Then downstream models use:

```sql
SELECT
    e.event_id,
    e.provider_id,
    p.provider_name
FROM staging_events e
LEFT JOIN stg_provider p
    ON e.provider_id = p.provider_id;
```

The transformation layer no longer needs repeated type-cleaning logic.


## Validation

### Check unmatched rows

```sql
SELECT
    e.event_id,
    e.provider_id
FROM staging_events e
LEFT JOIN stg_provider p
    ON e.provider_id = p.provider_id
WHERE p.provider_id IS NULL;
```

Only legitimately unknown provider IDs should remain.


### Compare before and after match rates

```sql
SELECT
    COUNT(*) AS total_events,
    COUNT(p.provider_id) AS matched_events,
    COUNT(*) - COUNT(p.provider_id) AS unmatched_events
FROM staging_events e
LEFT JOIN stg_provider p
    ON e.provider_id = p.provider_id;
```

This provides a simple join-quality metric.


### Validate invalid source keys

```sql
SELECT *
FROM provider_string_source
WHERE TRY_TO_NUMBER(TRIM(provider_id)) IS NULL;
```

Invalid values should be reviewed separately.


## Prevention

Recommended controls:

- Standardize business-key types in staging.
- Validate schema before downstream joins.
- Add data-contract expectations for key columns.
- Monitor unmatched join rates.
- Test invalid identifier formats.
- Trim whitespace during staging cleanup.
- Use `TRY_` conversion functions during ingestion validation.
- Add dbt accepted/not-null/relationship tests where appropriate.

Example quality check:

```sql
SELECT
    COUNT(*) AS invalid_provider_ids
FROM provider_string_source
WHERE TRY_TO_NUMBER(TRIM(provider_id)) IS NULL;
```

This can be monitored before downstream transformations run.


## Engineering Lesson
When a join unexpectedly loses rows, do not immediately rewrite the business
logic.

First validate:

```text
Data type
Formatting
NULL values
Whitespace
Duplicate keys
Key coverage
```

A syntactically correct join can still produce incomplete data if join keys are
not standardized.

Schema consistency should be enforced as early as possible, ideally in the
staging layer.