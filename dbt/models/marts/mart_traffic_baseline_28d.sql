/*
  mart_traffic_baseline_28d
  ──────────────────────────
  Rolling 28-day baseline statistics per bounding-box.
  Used downstream by mart_traffic_anomalies_5min to compute z-scores.

  Design notes:
  - Window is anchored to current_timestamp so it stays "trailing" on every
    dbt build.  With less than 28 days of history (typical at project start)
    all available data is used instead — the filter simply returns everything.
  - stddev_pop returns NULL when there is only one data point.  We coalesce
    to 0, which causes downstream nullif(std, 0) to suppress z-score
    computation rather than divide by zero.

  One row per bbox_name.
*/

with window_data as (

    select
        bbox_name,
        aircraft_count,
        positioned_aircraft_count

    from {{ ref('mart_traffic_timeseries_5min') }}

    where bucket_ts >= current_timestamp - interval '28 days'

),

stats as (

    select
        bbox_name,
        avg(aircraft_count)                    as baseline_mean_aircraft,
        stddev_pop(aircraft_count)             as baseline_std_aircraft_raw,
        avg(positioned_aircraft_count)         as baseline_mean_positioned,
        stddev_pop(positioned_aircraft_count)  as baseline_std_positioned_raw,
        count(*)                               as n_buckets

    from window_data
    group by bbox_name

)

select
    bbox_name,
    round(coalesce(baseline_mean_aircraft,      0), 2) as baseline_mean_aircraft,
    round(coalesce(baseline_std_aircraft_raw,   0), 4) as baseline_std_aircraft,
    round(coalesce(baseline_mean_positioned,    0), 2) as baseline_mean_positioned,
    round(coalesce(baseline_std_positioned_raw, 0), 4) as baseline_std_positioned,
    n_buckets

from stats
