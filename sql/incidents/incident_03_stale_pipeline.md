# Incident 03 — Silently Stale Pipeline

## Overview
A simulated production pipeline appeared healthy because the curated table
contained valid-looking data and no pipeline error had been reported.

However, downstream users reported that the data had not changed since the
previous day.

The actual issue was not incorrect SQL.

The ingestion/orchestration job had never run.

This represents a common production-support scenario where "no failure" does
not necessarily mean "successful execution."

## Symptom
The curated table returned valid records:

```sql
SELECT *
FROM curated_daily_events
ORDER BY event_date DESC;
```

The records appeared structurally correct.

However, users reported that newly expected source events were missing.

There were:

```text
No SQL errors
No failed transformation
No obvious data corruption
```

The pipeline appeared healthy at first glance.


## Diagnostic Process

### 1. Check the newest business event
```sql
SELECT MAX(event_timestamp) AS latest_event
FROM staging_events;
```

Example result:

```text
2026-07-29 15:10:00
```

If the current date is July 30, this immediately indicates that no recent data
has arrived.


### 2. Check the actual ingestion timestamp
```sql
SELECT MAX(loaded_at) AS latest_load
FROM staging_events;
```

Example:

```text
2026-07-29 15:15:00
```

This shows that the staging layer itself has not received data since the prior
day.


### 3. Calculate pipeline freshness
```sql
SELECT
    MAX(loaded_at) AS latest_load,
    DATEDIFF(
        'hour',
        MAX(loaded_at),
        CURRENT_TIMESTAMP()
    ) AS hours_since_last_load
FROM staging_events;
```

Example:

```text
LATEST_LOAD             HOURS_SINCE_LAST_LOAD
2026-07-29 15:15:00     24
```

This confirms that the issue is data freshness.


### 4. Determine whether the problem is upstream or downstream
Check the curated table:

```sql
SELECT MAX(event_date) AS latest_curated_date
FROM curated_daily_events;
```

Then compare with staging:

```sql
SELECT MAX(DATE(event_timestamp)) AS latest_staging_date
FROM staging_events;
```

If both staging and curated data are stale, the transformation is unlikely to
be the root cause.
The issue is probably upstream.


### 5. Check orchestration history
In a real Matillion environment, inspect:

```text
Matillion Task History
Job History
Scheduled Job History
Component execution status
```

Questions to answer:

```text
Did the job start?
Was the schedule enabled?
Was the job triggered?
Was the environment active?
Did an upstream dependency prevent execution?
```

If using Snowpipe/COPY-based ingestion, Snowflake load history can also be
reviewed.

Example:

```sql
SELECT *
FROM TABLE(
    INFORMATION_SCHEMA.COPY_HISTORY(
        TABLE_NAME => 'STAGING_EVENTS',
        START_TIME => DATEADD('day', -2, CURRENT_TIMESTAMP())
    )
)
ORDER BY LAST_LOAD_TIME DESC;
```

### 6. Confirm the pipeline simply did not run
Once job history confirms there is no recent execution, the incident can be
isolated to the orchestration layer.

This avoids unnecessarily modifying valid transformation SQL.


## Root Cause
The scheduled ingestion/orchestration job did not execute.

Possible realistic reasons include:

```text
Schedule disabled
Job not triggered
Environment unavailable
Upstream dependency not met
Scheduler configuration issue
Deployment missed the schedule configuration
```

Because the job never started, no component technically failed.

Therefore, no failure alert was produced.

The result was a silent freshness failure.


## Fix
Restore and run the missing ingestion job.

In a Matillion environment:

```text
1. Confirm the correct environment.
2. Re-enable or correct the schedule.
3. Execute the ingestion/orchestration job.
4. Confirm files are processed.
5. Run the downstream transformation.
```

After successful processing, verify:

```sql
SELECT MAX(loaded_at)
FROM staging_events;
```

The timestamp should now reflect the current load.


## Validation

### Validate staging freshness

```sql
SELECT
    MAX(loaded_at) AS latest_load,
    DATEDIFF(
        'minute',
        MAX(loaded_at),
        CURRENT_TIMESTAMP()
    ) AS minutes_since_last_load
FROM staging_events;
```


### Validate curated freshness

```sql
SELECT MAX(event_date)
FROM curated_daily_events;
```


### Validate row growth

```sql
SELECT COUNT(*)
FROM staging_events;
```

Compare against the prior known row count.


### Validate pipeline output

```sql
SELECT *
FROM curated_daily_events
ORDER BY event_date DESC;
```

Newly expected records should now appear.


## Prevention

A production system should monitor data freshness independently of pipeline
error status.

Example freshness test:

```sql
SELECT
    CASE
        WHEN MAX(loaded_at) <
             DATEADD('hour', -6, CURRENT_TIMESTAMP())
            THEN 'STALE'
        ELSE 'HEALTHY'
    END AS pipeline_health
FROM staging_events;
```

Recommended controls:

- Table freshness monitoring
- SLA-based alerts
- Matillion schedule monitoring
- Missing-run alerts
- Data arrival checks
- Pipeline heartbeat tables
- Audit/logging tables
- Expected-file monitoring
- Snowflake task/load history monitoring

For example, an alert could trigger if:

```text
MAX(loaded_at) > 6 hours old
```

even when no pipeline component has failed.


## Engineering Lesson

One of the first production-support questions should be:

> Did the pipeline actually run?

A downstream table containing valid data does not prove that the pipeline ran
recently.

Before debugging transformation SQL, validate:

```text
Data arrival
Last load timestamp
Job execution history
Schedule status
```

"No error" and "successfully refreshed" are not the same thing.