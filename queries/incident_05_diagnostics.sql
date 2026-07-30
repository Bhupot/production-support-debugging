-- Unexpected Snowflake Compute Cost

-- /* Review recent expensive queries */
SELECT
    user_name,
    query_text,
    start_time,
    end_time,
    warehouse_name,
    total_elapsed_time,
    bytes_scanned
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
)
ORDER BY bytes_scanned DESC
LIMIT 20;


-- Warehouse activity
SELECT
    warehouse_name,
    SUM(credits_used) AS credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time >= DATEADD(
    'day',
    -1,
    CURRENT_TIMESTAMP()
)
GROUP BY warehouse_name
ORDER BY credits_used DESC;
