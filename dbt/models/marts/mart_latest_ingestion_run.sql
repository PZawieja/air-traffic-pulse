/*
  mart_latest_ingestion_run
  ──────────────────────────
  Single-row model exposing the most recent ingestion run.
  Drives the "last run" metric strip in the Streamlit dashboard.
*/

select
    run_id,
    started_at,
    finished_at,
    status,
    records_loaded,
    error_msg,
    run_duration_seconds

from {{ ref('stg_ingestion_runs') }}
order by started_at desc
limit 1
