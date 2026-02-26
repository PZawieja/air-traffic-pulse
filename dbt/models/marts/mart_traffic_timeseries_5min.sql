/*
  mart_traffic_timeseries_5min
  ─────────────────────────────
  Traffic intensity per bounding-box, bucketed into 5-minute intervals.

  Bucketing logic (DuckDB):
    1. date_trunc to the minute
    2. Subtract (minute % 5) minutes to align to the nearest 5-min boundary

  One row per (bbox_name, bucket_ts).
  Primary consumer: Streamlit timeseries line chart.
*/

with bucketed as (

    select
        bbox_name,
        icao24,
        has_position,

        -- Snap ingestion_ts to the start of its 5-minute window.
        date_trunc('minute', ingestion_ts)
            - (extract('minute' from ingestion_ts)::bigint % 5)
            * interval '1 minute'                                   as bucket_ts

    from {{ ref('stg_opensky_states') }}

)

select
    bbox_name,
    bucket_ts,

    count(distinct icao24)                                          as aircraft_count,
    count(distinct case when has_position then icao24 end)          as positioned_aircraft_count

from bucketed
group by bbox_name, bucket_ts
order by bbox_name, bucket_ts
