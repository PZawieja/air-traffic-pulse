/*
  mart_latest_snapshot_by_bbox
  ─────────────────────────────
  For each bounding-box preset, surface the most recent ingestion snapshot
  and compute aircraft summary statistics for that single point in time.

  One row per bbox_name.  Primary consumer: Streamlit Overview table.
*/

with latest_ts as (

    -- Find the newest ingestion_ts per bbox so we can isolate the latest batch.
    select
        bbox_name,
        max(ingestion_ts) as snapshot_ingestion_ts
    from {{ ref('stg_opensky_states') }}
    group by bbox_name

),

latest_rows as (

    select s.*
    from {{ ref('stg_opensky_states') }} as s
    inner join latest_ts as l
        on  s.bbox_name    = l.bbox_name
        and s.ingestion_ts = l.snapshot_ingestion_ts

)

select
    bbox_name,
    ingestion_ts                                                          as snapshot_ingestion_ts,

    -- Unique aircraft observed in this snapshot
    count(distinct icao24)                                                as aircraft_count,

    -- Aircraft with a valid GPS/ADS-B position fix
    count(distinct case when has_position     then icao24 end)            as positioned_aircraft_count,

    -- Aircraft reporting ground contact
    count(case when on_ground then 1 end)                                 as on_ground_count,

    -- Average ground speed (excludes NULLs and parked aircraft at 0 m/s)
    round(avg(case when velocity is not null then velocity end), 2)       as avg_velocity_mps

from latest_rows
group by bbox_name, ingestion_ts
order by bbox_name
