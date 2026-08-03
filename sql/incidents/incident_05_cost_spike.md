# Incident 05 — Snowflake Runaway Cost Spike

## Overview
A simulated production incident caused an unexpected increase in Snowflake
compute consumption overnight.

No functional pipeline failure was initially reported.

The pipeline completed successfully, but consumed significantly more compute
than normal.

The investigation identified a job that had rerun without its normal
incremental filter, causing a much larger volume of data to be scanned and
processed.

This scenario demonstrates that pipeline health includes cost and resource
behavior, not only successful completion.


## Symptom
The team observed an unexpected increase in Snowflake usage.

Typical indicators could include:

```text
Higher daily credit consumption
Longer warehouse runtime
Queries scanning significantly more data than normal
Unexpected warehouse auto-scaling
Cost-monitor alerts
```

The affected pipeline itself showed:

```text
SUCCESS
```

so the first indication of the problem came from usage/cost monitoring rather
than a failed job.


## Diagnostic Process

### 1. Identify warehouses consuming the most credits
```sql
SELECT
    warehouse_name,
    SUM(credits_used) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
)
GROUP BY warehouse_name
ORDER BY total_credits DESC;
```

This identifies which warehouse experienced abnormal usage.


### 2. Compare warehouse usage with previous periods
```sql
SELECT
    DATE(start_time) AS usage_date,
    warehouse_name,
    SUM(credits_used) AS credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -7,
    CURRENT_TIMESTAMP()
)
GROUP BY
    DATE(start_time),
    warehouse_name
ORDER BY
    usage_date DESC,
    credits_used DESC;
```

This establishes whether the increase is truly abnormal relative to previous
days.


### 3. Identify expensive or long-running queries
```sql
SELECT
    query_id,
    user_name,
    warehouse_name,
    query_text,
    start_time,
    end_time,
    total_elapsed_time,
    bytes_scanned,
    rows_produced
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
)
ORDER BY bytes_scanned DESC
LIMIT 20;
```

This helps isolate queries that processed unusually large volumes of data.


### 4. Look specifically for repeated pipeline SQL
Search for repeated or duplicate executions.

```sql
SELECT
    query_text,
    COUNT(*) AS execution_count,
    SUM(bytes_scanned) AS total_bytes_scanned
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
)
  AND warehouse_name = 'PRACTICE_WH'
GROUP BY query_text
HAVING COUNT(*) > 1
ORDER BY total_bytes_scanned DESC;
```

This can expose accidental reruns.


### 5. Review the suspected transformation
Expected incremental logic:

```sql
SELECT *
FROM source_events
WHERE event_timestamp >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
);
```

Problematic execution:

```sql
SELECT *
FROM source_events;
```

The missing filter causes a full historical scan/reprocessing.


### 6. Confirm processing volume
Compare normal and incident volumes.

```sql
SELECT
    DATE(start_time) AS run_date,
    COUNT(*) AS query_count,
    SUM(bytes_scanned) AS bytes_scanned
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = 'PRACTICE_WH'
  AND start_time >= DATEADD(
      'day',
      -7,
      CURRENT_TIMESTAMP()
  )
GROUP BY DATE(start_time)
ORDER BY run_date DESC;
```

A major increase on the incident date confirms abnormal processing volume.


### 7. Check orchestration history
In Matillion, review:

```text
Task History
Job Run History
Job parameters
Retry/restart history
Environment variables
Incremental date parameters
```

Questions to answer:

```text
Was the job manually restarted?
Did a parameter resolve incorrectly?
Was an incremental date missing?
Did retry logic execute the full job?
Was the historical-run flag accidentally enabled?
```

This links the Snowflake resource symptom back to the pipeline behavior.


## Root Cause
The pipeline reran without its normal incremental filter.

Instead of processing only the latest data, it performed a full-table
scan/reload of a substantially larger dataset.

Conceptually:

Expected:

```sql
WHERE event_date >= :last_successful_run_date
```

Incident execution:

```sql
-- filter missing
```

As a result:

```text
More rows scanned
More compute time
Longer warehouse runtime
Higher Snowflake credit consumption
```

The pipeline still completed successfully, which is why functional monitoring
alone did not detect the incident.


## Immediate Fix
Restore the incremental filter and stop unnecessary workloads.

Example:

```sql
SELECT *
FROM source_events
WHERE event_timestamp > (
    SELECT MAX(event_timestamp)
    FROM target_events
);
```

The actual production implementation should use the appropriate watermark or
load-control mechanism.


## Resource Protection
Add a Snowflake resource monitor.

Example:

```sql
CREATE OR REPLACE RESOURCE MONITOR production_monitor
WITH
    CREDIT_QUOTA = 100
    FREQUENCY = MONTHLY
    START_TIMESTAMP = IMMEDIATELY
    TRIGGERS
        ON 75 PERCENT DO NOTIFY
        ON 90 PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND;
```

Attach it to a warehouse:

```sql
ALTER WAREHOUSE practice_wh
SET RESOURCE_MONITOR = production_monitor;
```

The actual quota should be based on production workload expectations.


## Validation

### Validate current query behavior

Review recent execution:

```sql
SELECT
    query_id,
    query_text,
    bytes_scanned,
    total_elapsed_time,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = 'PRACTICE_WH'
ORDER BY start_time DESC
LIMIT 20;
```

The corrected job should process substantially less data.


### Validate warehouse usage

```sql
SELECT
    warehouse_name,
    SUM(credits_used) AS credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time >= DATEADD(
    'hour',
    -24,
    CURRENT_TIMESTAMP()
)
GROUP BY warehouse_name;
```

Usage should return to the expected range after the fix.


### Validate incremental processing

```sql
SELECT
    MIN(event_timestamp) AS minimum_processed_timestamp,
    MAX(event_timestamp) AS maximum_processed_timestamp,
    COUNT(*) AS rows_processed
FROM target_events
WHERE loaded_at >= DATEADD(
    'hour',
    -1,
    CURRENT_TIMESTAMP()
);
```

This confirms that the job processed only the intended window.


## Prevention
Recommended controls:

- Resource monitors on all production warehouses
- Credit-usage alerts
- Query-volume monitoring
- Incremental watermark tables
- Load-control tables
- Idempotent job design
- Historical-run flags separated from normal runs
- Parameter validation before execution
- Warehouse auto-suspend
- Workload-specific warehouses
- Maximum runtime monitoring
- Daily usage comparison
- Alerting on unusual bytes scanned

A pipeline should be considered unhealthy when resource consumption suddenly
deviates from normal behavior, even if the job technically completes.


## Example Load-Control Pattern
Instead of relying on manually supplied dates:

```sql
CREATE TABLE IF NOT EXISTS pipeline_control (
    pipeline_name STRING,
    last_successful_timestamp TIMESTAMP
);
```

Read the watermark:

```sql
SELECT last_successful_timestamp
FROM pipeline_control
WHERE pipeline_name = 'EVENT_PIPELINE';
```

Use it during extraction:

```sql
SELECT *
FROM source_events
WHERE event_timestamp > :last_successful_timestamp;
```

Update it only after successful completion.

This reduces the risk of accidentally processing the full historical dataset.


## Engineering Lesson

Production pipeline monitoring should answer more than:

> Did the job succeed?

It should also answer:

```text
Did it process the expected amount of data?
Did it run for the expected duration?
Did it scan the expected volume?
Did it consume the expected amount of compute?
```

A pipeline can be functionally successful while being operationally unhealthy.

Cost anomalies are therefore an important production-support signal, not only
a finance concern.