/*
  metricflow_time_spine
  ──────────────────────
  Required by dbt's MetricFlow semantic layer.
  Provides a continuous sequence of dates that MetricFlow uses to
  fill time-series gaps and align metric windows.

  Covers 2020-01-01 → 10 years from today.
*/

{{
  config(
    materialized = 'table',
  )
}}

with spine as (
  {{
    dbt.date_spine(
      datepart   = "day",
      start_date = "cast('2020-01-01' as date)",
      end_date   = "cast(current_date + interval '10 years' as date)"
    )
  }}
)

select cast(date_day as date) as date_day
from spine
