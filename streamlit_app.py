from __future__ import annotations

from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st

# Page configuration

st.set_page_config(
    page_title="Pipeline Diagnostics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Constants

DATABASE = "ANALYTICS"
SCHEMA = "PUBLIC"

STAGING_TABLE = f"{DATABASE}.{SCHEMA}.STAGING_EVENTS"
CURATED_TABLE = f"{DATABASE}.{SCHEMA}.CURATED_DAILY_EVENTS"
PROVIDER_TABLE = f"{DATABASE}.{SCHEMA}.DIM_PROVIDER_LOOKUP"

FRESHNESS_THRESHOLD_HOURS = 24

# Styling

st.markdown(
    """
    <style>
        .main-title {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0;
        }

        .main-subtitle {
            color: #6b7280;
            margin-top: 0.25rem;
            margin-bottom: 1.5rem;
        }

        .healthy-status {
            padding: 0.7rem 1rem;
            border-radius: 0.5rem;
            background-color: #dcfce7;
            color: #166534;
            font-weight: 600;
        }

        .warning-status {
            padding: 0.7rem 1rem;
            border-radius: 0.5rem;
            background-color: #fef3c7;
            color: #92400e;
            font-weight: 600;
        }

        .critical-status {
            padding: 0.7rem 1rem;
            border-radius: 0.5rem;
            background-color: #fee2e2;
            color: #991b1b;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# Snowflake connection

@st.cache_resource
def get_connection():
    """
    Create and cache the Snowflake connection.

    The credentials are loaded from:
    .streamlit/secrets.toml
    """
    return st.connection("snowflake")


def run_query(sql: str, ttl: int = 300) -> pd.DataFrame:
    """
    Run a read-only Snowflake query and return a pandas DataFrame.

    Parameters
    ----------
    sql:
        SQL query to execute.
    ttl:
        Number of seconds that Streamlit should cache the query result.
    """
    connection = get_connection()

    return connection.query(
        sql,
        ttl=ttl,
        show_spinner="Running Snowflake diagnostic query...",
    )


# Data-loading functions

@st.cache_data(ttl=300)
def load_summary_metrics() -> pd.DataFrame:
    sql = f"""
        SELECT
            (SELECT COUNT(*) FROM {STAGING_TABLE}) AS staging_rows,
            (SELECT COUNT(*) FROM {CURATED_TABLE}) AS curated_rows,
            (
                SELECT COUNT(*)
                FROM {STAGING_TABLE}
                WHERE provider_id IS NULL
            ) AS null_provider_ids,
            (
                SELECT COUNT(*)
                FROM (
                    SELECT
                        event_id
                    FROM {STAGING_TABLE}
                    GROUP BY event_id
                    HAVING COUNT(*) > 1
                )
            ) AS duplicate_event_ids,
            (
                SELECT MAX(loaded_at)
                FROM {STAGING_TABLE}
            ) AS latest_load
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_event_trend() -> pd.DataFrame:
    sql = f"""
        SELECT
            event_date,
            SUM(event_count) AS total_events
        FROM {CURATED_TABLE}
        GROUP BY event_date
        ORDER BY event_date
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_status_distribution() -> pd.DataFrame:
    sql = f"""
        SELECT
            status,
            SUM(event_count) AS event_count
        FROM {CURATED_TABLE}
        GROUP BY status
        ORDER BY event_count DESC
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_event_type_distribution() -> pd.DataFrame:
    sql = f"""
        SELECT
            event_type,
            SUM(event_count) AS event_count
        FROM {CURATED_TABLE}
        GROUP BY event_type
        ORDER BY event_count DESC
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_duplicate_details() -> pd.DataFrame:
    sql = f"""
        SELECT
            event_id,
            COUNT(*) AS duplicate_count,
            MIN(loaded_at) AS first_loaded_at,
            MAX(loaded_at) AS last_loaded_at
        FROM {STAGING_TABLE}
        GROUP BY event_id
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC, event_id
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_null_provider_records() -> pd.DataFrame:
    sql = f"""
        SELECT
            event_id,
            provider_id,
            event_type,
            status,
            event_timestamp,
            loaded_at
        FROM {STAGING_TABLE}
        WHERE provider_id IS NULL
        ORDER BY loaded_at DESC
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_unmatched_providers() -> pd.DataFrame:
    sql = f"""
        SELECT
            e.event_id,
            e.provider_id,
            e.event_type,
            e.status,
            e.event_timestamp
        FROM {STAGING_TABLE} AS e
        LEFT JOIN {PROVIDER_TABLE} AS p
            ON e.provider_id = p.provider_id
        WHERE e.provider_id IS NOT NULL
          AND p.provider_id IS NULL
        ORDER BY e.event_timestamp DESC
    """

    return run_query(sql)


@st.cache_data(ttl=300)
def load_recent_events(limit: int = 100) -> pd.DataFrame:
    safe_limit = max(1, min(int(limit), 1000))

    sql = f"""
        SELECT
            event_id,
            provider_id,
            event_type,
            status,
            event_timestamp,
            loaded_at
        FROM {STAGING_TABLE}
        ORDER BY event_timestamp DESC
        LIMIT {safe_limit}
    """

    return run_query(sql)


@st.cache_data(ttl=600)
def load_warehouse_usage() -> pd.DataFrame:
    sql = """
        SELECT
            TO_DATE(start_time) AS usage_date,
            warehouse_name,
            ROUND(SUM(credits_used), 3) AS credits_used
        FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
        WHERE start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        GROUP BY
            TO_DATE(start_time),
            warehouse_name
        ORDER BY
            usage_date,
            warehouse_name
    """

    return run_query(sql, ttl=600)


@st.cache_data(ttl=600)
def load_expensive_queries() -> pd.DataFrame:
    sql = """
        SELECT
            query_id,
            user_name,
            warehouse_name,
            query_type,
            start_time,
            ROUND(total_elapsed_time / 1000, 2) AS elapsed_seconds,
            bytes_scanned,
            rows_produced,
            query_text
        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
        WHERE start_time >= DATEADD('day', -1, CURRENT_TIMESTAMP())
          AND execution_status = 'SUCCESS'
        ORDER BY bytes_scanned DESC
        LIMIT 20
    """

    return run_query(sql, ttl=600)


# Helper functions

def normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Convert Snowflake uppercase result-column names to lowercase.
    """
    renamed = dataframe.copy()
    renamed.columns = [str(column).lower() for column in renamed.columns]
    return renamed


def calculate_freshness_hours(latest_load) -> float | None:
    if pd.isna(latest_load):
        return None

    latest_timestamp = pd.Timestamp(latest_load)

    if latest_timestamp.tzinfo is None:
        latest_timestamp = latest_timestamp.tz_localize("UTC")
    else:
        latest_timestamp = latest_timestamp.tz_convert("UTC")

    current_timestamp = pd.Timestamp(datetime.now(timezone.utc))

    difference = current_timestamp - latest_timestamp

    return round(difference.total_seconds() / 3600, 1)


def display_health_status(
    freshness_hours: float | None,
    duplicate_count: int,
    null_count: int,
) -> None:
    if freshness_hours is None:
        st.markdown(
            '<div class="critical-status">'
            "🔴 Critical: no successful load timestamp was found."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if freshness_hours > FRESHNESS_THRESHOLD_HOURS:
        st.markdown(
            '<div class="critical-status">'
            f"🔴 Critical: pipeline data is {freshness_hours} hours old."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if duplicate_count > 0 or null_count > 0:
        st.markdown(
            '<div class="warning-status">'
            "🟠 Warning: the pipeline is fresh, but data-quality issues exist."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div class="healthy-status">'
        "🟢 Healthy: the pipeline is fresh and no monitored issues were detected."
        "</div>",
        unsafe_allow_html=True,
    )


def format_timestamp(value) -> str:
    if pd.isna(value):
        return "No load found"

    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


# Main app

st.markdown(
    '<p class="main-title">Pipeline Diagnostics Dashboard</p>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <p class="main-subtitle">
        Production-support monitoring for the Snowflake event pipeline.
    </p>
    """,
    unsafe_allow_html=True,
)


# Sidebar

with st.sidebar:
    st.header("Dashboard controls")

    page = st.radio(
        "Select view",
        options=[
            "Pipeline Overview",
            "Incident Diagnostics",
            "Snowflake Cost Monitoring",
            "Raw Data Explorer",
        ],
    )

    st.divider()

    st.caption("Snowflake environment")

    st.code(
        f"""
Database: {DATABASE}
Schema:   {SCHEMA}
Warehouse: configured in secrets.toml
        """.strip()
    )

    st.divider()

    if st.button("Refresh dashboard data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# Load common metrics

try:
    summary = normalize_columns(load_summary_metrics())

except Exception as error:
    st.error("The dashboard could not connect to Snowflake or run its queries.")

    st.exception(error)

    st.stop()


if summary.empty:
    st.warning("The summary query returned no data.")
    st.stop()


summary_row = summary.iloc[0]

staging_rows = int(summary_row.get("staging_rows", 0) or 0)
curated_rows = int(summary_row.get("curated_rows", 0) or 0)
null_provider_ids = int(summary_row.get("null_provider_ids", 0) or 0)
duplicate_event_ids = int(summary_row.get("duplicate_event_ids", 0) or 0)
latest_load = summary_row.get("latest_load")

freshness_hours = calculate_freshness_hours(latest_load)


# Page 1: Pipeline Overview

if page == "Pipeline Overview":
    st.subheader("Current pipeline health")

    display_health_status(
        freshness_hours=freshness_hours,
        duplicate_count=duplicate_event_ids,
        null_count=null_provider_ids,
    )

    st.write("")

    metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)

    metric_1.metric(
        label="Staging rows",
        value=f"{staging_rows:,}",
    )

    metric_2.metric(
        label="Curated rows",
        value=f"{curated_rows:,}",
    )

    metric_3.metric(
        label="Duplicate event IDs",
        value=f"{duplicate_event_ids:,}",
    )

    metric_4.metric(
        label="NULL provider IDs",
        value=f"{null_provider_ids:,}",
    )

    metric_5.metric(
        label="Hours since load",
        value="Unknown" if freshness_hours is None else freshness_hours,
    )

    st.caption(
        f"Latest load timestamp: {format_timestamp(latest_load)}"
    )

    st.divider()

    left_chart, right_chart = st.columns(2)

    with left_chart:
        st.subheader("Event volume by date")

        event_trend = normalize_columns(load_event_trend())

        if event_trend.empty:
            st.info("No curated event trend data is available.")

        else:
            event_trend["event_date"] = pd.to_datetime(
                event_trend["event_date"]
            )

            trend_chart = (
                alt.Chart(event_trend)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "event_date:T",
                        title="Event date",
                    ),
                    y=alt.Y(
                        "total_events:Q",
                        title="Total events",
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "event_date:T",
                            title="Date",
                        ),
                        alt.Tooltip(
                            "total_events:Q",
                            title="Events",
                            format=",",
                        ),
                    ],
                )
                .properties(height=350)
            )

            st.altair_chart(
                trend_chart,
                use_container_width=True,
            )

    with right_chart:
        st.subheader("Events by status")

        status_distribution = normalize_columns(
            load_status_distribution()
        )

        if status_distribution.empty:
            st.info("No event status data is available.")

        else:
            status_chart = (
                alt.Chart(status_distribution)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "event_count:Q",
                        title="Event count",
                    ),
                    y=alt.Y(
                        "status:N",
                        title="Status",
                        sort="-x",
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "status:N",
                            title="Status",
                        ),
                        alt.Tooltip(
                            "event_count:Q",
                            title="Events",
                            format=",",
                        ),
                    ],
                )
                .properties(height=350)
            )

            st.altair_chart(
                status_chart,
                use_container_width=True,
            )

    st.subheader("Events by type")

    event_types = normalize_columns(load_event_type_distribution())

    if event_types.empty:
        st.info("No event-type data is available.")

    else:
        event_type_chart = (
            alt.Chart(event_types)
            .mark_bar()
            .encode(
                x=alt.X(
                    "event_type:N",
                    title="Event type",
                    sort="-y",
                ),
                y=alt.Y(
                    "event_count:Q",
                    title="Event count",
                ),
                tooltip=[
                    alt.Tooltip(
                        "event_type:N",
                        title="Event type",
                    ),
                    alt.Tooltip(
                        "event_count:Q",
                        title="Events",
                        format=",",
                    ),
                ],
            )
            .properties(height=350)
        )

        st.altair_chart(
            event_type_chart,
            use_container_width=True,
        )


# Page 2: Incident Diagnostics

elif page == "Incident Diagnostics":
    st.subheader("Production incident checks")

    incident_tab_1, incident_tab_2, incident_tab_3, incident_tab_4 = st.tabs(
        [
            "Duplicate Loads",
            "NULL Provider IDs",
            "Stale Pipeline",
            "Unmatched Providers",
        ]
    )

    with incident_tab_1:
        st.markdown("### Incident 01 — Duplicate batch load")

        duplicate_data = normalize_columns(load_duplicate_details())

        if duplicate_data.empty:
            st.success("No duplicate event IDs were found.")

        else:
            st.error(
                f"{len(duplicate_data):,} duplicated event IDs were found."
            )

            st.dataframe(
                duplicate_data,
                use_container_width=True,
                hide_index=True,
            )

            duplicate_chart = (
                alt.Chart(duplicate_data)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "event_id:N",
                        title="Event ID",
                        sort="-y",
                    ),
                    y=alt.Y(
                        "duplicate_count:Q",
                        title="Row count",
                    ),
                    tooltip=[
                        "event_id:N",
                        "duplicate_count:Q",
                    ],
                )
                .properties(height=350)
            )

            st.altair_chart(
                duplicate_chart,
                use_container_width=True,
            )

        with st.expander("Diagnostic SQL"):
            st.code(
                f"""
SELECT
    event_id,
    COUNT(*) AS duplicate_count
FROM {STAGING_TABLE}
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
                """.strip(),
                language="sql",
            )

    with incident_tab_2:
        st.markdown("### Incident 02 — NULL provider IDs")

        null_records = normalize_columns(load_null_provider_records())

        if null_records.empty:
            st.success("No NULL provider IDs were found.")

        else:
            st.warning(
                f"{len(null_records):,} records have a NULL provider ID."
            )

            st.dataframe(
                null_records,
                use_container_width=True,
                hide_index=True,
            )

        with st.expander("Diagnostic SQL"):
            st.code(
                f"""
SELECT
    *
FROM {STAGING_TABLE}
WHERE provider_id IS NULL;
                """.strip(),
                language="sql",
            )

        with st.expander("Safe exclusion pattern"):
            st.code(
                f"""
SELECT
    p.provider_id
FROM {PROVIDER_TABLE} AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM {STAGING_TABLE} AS e
    WHERE e.provider_id = p.provider_id
);
                """.strip(),
                language="sql",
            )

    with incident_tab_3:
        st.markdown("### Incident 03 — Pipeline freshness")

        freshness_col_1, freshness_col_2 = st.columns(2)

        freshness_col_1.metric(
            "Latest load",
            format_timestamp(latest_load),
        )

        freshness_col_2.metric(
            "Hours since load",
            "Unknown" if freshness_hours is None else freshness_hours,
        )

        if freshness_hours is None:
            st.error("No load timestamp exists.")

        elif freshness_hours > FRESHNESS_THRESHOLD_HOURS:
            st.error(
                f"The pipeline is stale. The latest data is "
                f"{freshness_hours} hours old."
            )

        else:
            st.success(
                f"The pipeline is within the "
                f"{FRESHNESS_THRESHOLD_HOURS}-hour freshness SLA."
            )

        st.code(
            f"""
SELECT
    MAX(loaded_at) AS latest_load,
    DATEDIFF(
        'hour',
        MAX(loaded_at),
        CURRENT_TIMESTAMP()
    ) AS hours_since_last_load
FROM {STAGING_TABLE};
            """.strip(),
            language="sql",
        )

    with incident_tab_4:
        st.markdown("### Incident 04 — Unmatched provider joins")

        unmatched_records = normalize_columns(load_unmatched_providers())

        if unmatched_records.empty:
            st.success(
                "Every non-NULL staging provider ID matched the provider lookup."
            )

        else:
            st.warning(
                f"{len(unmatched_records):,} events have an unmatched "
                "provider ID."
            )

            st.dataframe(
                unmatched_records,
                use_container_width=True,
                hide_index=True,
            )

        with st.expander("Diagnostic SQL"):
            st.code(
                f"""
SELECT
    e.event_id,
    e.provider_id
FROM {STAGING_TABLE} AS e
LEFT JOIN {PROVIDER_TABLE} AS p
    ON e.provider_id = p.provider_id
WHERE e.provider_id IS NOT NULL
  AND p.provider_id IS NULL;
                """.strip(),
                language="sql",
            )


# Page 3: Snowflake Cost Monitoring

elif page == "Snowflake Cost Monitoring":
    st.subheader("Snowflake warehouse usage")

    st.info(
        "Snowflake ACCOUNT_USAGE views can have reporting latency. "
        "This page is intended for trend and incident analysis."
    )

    try:
        warehouse_usage = normalize_columns(load_warehouse_usage())

        if warehouse_usage.empty:
            st.info("No warehouse usage data is available.")

        else:
            warehouse_usage["usage_date"] = pd.to_datetime(
                warehouse_usage["usage_date"]
            )

            total_credits = warehouse_usage["credits_used"].sum()

            warehouse_count = warehouse_usage[
                "warehouse_name"
            ].nunique()

            usage_metric_1, usage_metric_2 = st.columns(2)

            usage_metric_1.metric(
                "Credits used in last 7 days",
                f"{total_credits:,.3f}",
            )

            usage_metric_2.metric(
                "Warehouses active",
                f"{warehouse_count:,}",
            )

            usage_chart = (
                alt.Chart(warehouse_usage)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "usage_date:T",
                        title="Usage date",
                    ),
                    y=alt.Y(
                        "credits_used:Q",
                        title="Credits used",
                    ),
                    color=alt.Color(
                        "warehouse_name:N",
                        title="Warehouse",
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "usage_date:T",
                            title="Date",
                        ),
                        alt.Tooltip(
                            "warehouse_name:N",
                            title="Warehouse",
                        ),
                        alt.Tooltip(
                            "credits_used:Q",
                            title="Credits",
                            format=".3f",
                        ),
                    ],
                )
                .properties(height=400)
            )

            st.altair_chart(
                usage_chart,
                use_container_width=True,
            )

        st.subheader("Most expensive recent queries")

        expensive_queries = normalize_columns(load_expensive_queries())

        if expensive_queries.empty:
            st.info("No recent query-history records were returned.")

        else:
            display_columns = [
                "query_id",
                "user_name",
                "warehouse_name",
                "query_type",
                "start_time",
                "elapsed_seconds",
                "bytes_scanned",
                "rows_produced",
                "query_text",
            ]

            available_columns = [
                column
                for column in display_columns
                if column in expensive_queries.columns
            ]

            st.dataframe(
                expensive_queries[available_columns],
                use_container_width=True,
                hide_index=True,
            )

    except Exception as cost_error:
        st.warning(
            "Cost-monitoring data could not be loaded. "
            "Your Snowflake role may not have access to ACCOUNT_USAGE."
        )

        with st.expander("Technical details"):
            st.exception(cost_error)


# Page 4: Raw Data Explorer

elif page == "Raw Data Explorer":
    st.subheader("Staging-event explorer")

    row_limit = st.slider(
        "Maximum number of rows",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
    )

    event_data = normalize_columns(
        load_recent_events(limit=row_limit)
    )

    if event_data.empty:
        st.info("No staging records were returned.")

    else:
        filter_col_1, filter_col_2 = st.columns(2)

        event_type_options = sorted(
            event_data["event_type"].dropna().unique().tolist()
        )

        status_options = sorted(
            event_data["status"].dropna().unique().tolist()
        )

        selected_event_types = filter_col_1.multiselect(
            "Event type",
            options=event_type_options,
            default=event_type_options,
        )

        selected_statuses = filter_col_2.multiselect(
            "Status",
            options=status_options,
            default=status_options,
        )

        filtered_events = event_data[
            event_data["event_type"].isin(selected_event_types)
            & event_data["status"].isin(selected_statuses)
        ]

        st.metric(
            "Rows displayed",
            f"{len(filtered_events):,}",
        )

        st.dataframe(
            filtered_events,
            use_container_width=True,
            hide_index=True,
        )

        csv_data = filtered_events.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download filtered data as CSV",
            data=csv_data,
            file_name="pipeline_events.csv",
            mime="text/csv",
        )


# Footer

st.divider()

st.caption(
    "Pipeline Diagnostics Portfolio | Snowflake + Matillion concepts + AWS S3 + Streamlit"
)