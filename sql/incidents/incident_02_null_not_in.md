# Incident 02 — NULL in NOT IN Silent Failure

## Overview

A simulated production query intended to identify providers with no recent
events unexpectedly returned zero rows.

The SQL completed successfully and did not produce an error, making this a
silent data-quality issue rather than a technical pipeline failure.

This scenario demonstrates how NULL values can affect exclusion logic when
`NOT IN` is used.

## Symptom

A query was expected to return providers that did not exist in staging_events.

The query completed successfully but returned no records.

Buggy query:

```sql
SELECT provider_id
FROM dim_provider_lookup
WHERE provider_id NOT IN (
    SELECT provider_id
    FROM staging_events
);
```

Based on the source data, at least one provider should have been returned.

However, the result was:

```text
0 rows returned
```

No Snowflake error was generated.

## Diagnostic Process

### 1. Validate the lookup table

First, confirm that the provider lookup contains valid providers.

```sql
SELECT *
FROM dim_provider_lookup
ORDER BY provider_id;
```

Example result:

```text
101
102
103
104
105
```

This confirms that the source population exists.

### 2. Review provider IDs present in the staging table

```sql
SELECT DISTINCT provider_id
FROM staging_events
ORDER BY provider_id;
```

The expectation is that some providers from `dim_provider_lookup` are not
present in this result.

That means the exclusion query should return records.

### 3. Check whether the subquery contains NULL values

```sql
SELECT COUNT(*) AS null_provider_count
FROM staging_events
WHERE provider_id IS NULL;
```

Example result:

```text
1
```

This identifies the critical condition affecting the `NOT IN` query.

### 4. Inspect the exact subquery result

```sql
SELECT DISTINCT provider_id
FROM staging_events;
```

Example:

```text
101
102
103
104
NULL
```

The presence of `NULL` means the outer `NOT IN` comparison can no longer
evaluate cleanly.

### 5. Compare NOT IN with NOT EXISTS

Run the original query:

```sql
SELECT provider_id
FROM dim_provider_lookup
WHERE provider_id NOT IN (
    SELECT provider_id
    FROM staging_events
);
```

Result:

```text
0 rows
```

Now run:

```sql
SELECT p.provider_id
FROM dim_provider_lookup p
WHERE NOT EXISTS (
    SELECT 1
    FROM staging_events e
    WHERE e.provider_id = p.provider_id
);
```

Expected result:

```text
105
```

This confirms that the exclusion logic, not the source data, caused the issue.


## Root Cause

The root cause was a `NULL` value inside the subquery used by `NOT IN`.

SQL uses three-valued logic:

```text
TRUE
FALSE
UNKNOWN
```

When Snowflake evaluates a condition such as:

```sql
105 NOT IN (101, 102, 103, 104, NULL)
```

it cannot prove that `105` is different from the unknown `NULL` value.

The result becomes `UNKNOWN`, not `TRUE`.

Because the `WHERE` clause only returns rows where the condition evaluates to
`TRUE`, the provider is excluded from the result.

This caused the query to silently return zero rows.


## Fix

Replace `NOT IN` with `NOT EXISTS`.

```sql
SELECT p.provider_id
FROM dim_provider_lookup p
WHERE NOT EXISTS (
    SELECT 1
    FROM staging_events e
    WHERE e.provider_id = p.provider_id
);
```

This comparison is correlated directly on the provider ID and does not suffer
from the same NULL behavior.


## Alternative Fix

If `NOT IN` must be used, explicitly remove NULL values from the subquery.

```sql
SELECT provider_id
FROM dim_provider_lookup
WHERE provider_id NOT IN (
    SELECT provider_id
    FROM staging_events
    WHERE provider_id IS NOT NULL
);
```

However, `NOT EXISTS` is generally safer for exclusion logic.


## Validation

Validate the corrected query:

```sql
SELECT p.provider_id
FROM dim_provider_lookup p
WHERE NOT EXISTS (
    SELECT 1
    FROM staging_events e
    WHERE e.provider_id = p.provider_id
);
```

Expected result:

```text
105
```

Also confirm that NULL data still exists:

```sql
SELECT *
FROM staging_events
WHERE provider_id IS NULL;
```

The corrected query should continue to work even when NULL values are present.


## Prevention

Recommended preventive controls:

- Prefer `NOT EXISTS` for exclusion logic.
- Add NULL checks during staging validation.
- Apply `NOT NULL` constraints where business rules allow.
- Add dbt or SQL data-quality tests for key columns.
- Review exclusion queries during code review.
- Avoid assuming a successfully executed query is logically correct.

Example monitoring check:

```sql
SELECT COUNT(*) AS null_provider_ids
FROM staging_events
WHERE provider_id IS NULL;
```

If `provider_id` should never be NULL, this check can be incorporated into a
pipeline validation step.


## Engineering Lesson

A query can execute successfully and still produce completely incorrect
results.

When exclusion logic unexpectedly returns zero rows, validate the contents of
the subquery before changing the broader business logic.

In particular, always consider NULL behavior when using:

```sql
NOT IN
```

For production pipelines, `NOT EXISTS` is usually the safer exclusion pattern.