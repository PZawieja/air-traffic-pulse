/*
  mart_traffic_anomalies_5min
  ────────────────────────────
  Z-score and anomaly flags for every 5-minute traffic bucket.

  Method: 28-day rolling population z-score
    z = (observed − baseline_mean) / baseline_std

  Anomaly rule:
    is_anomaly = |z_aircraft| ≥ 3  OR  |z_positioned| ≥ 3

  z-scores are NULL when baseline_std = 0, which happens when:
  - There is only one bucket in the baseline window (early data)
  - Every bucket in the window had identical counts (pathological)
  In both cases is_anomaly defaults to FALSE via the CASE expression.

  One row per (bbox_name, bucket_ts) — same grain as mart_traffic_timeseries_5min.
*/

with joined as (

    select
        t.bbox_name,
        t.bucket_ts,
        t.aircraft_count,
        t.positioned_aircraft_count,

        b.baseline_mean_aircraft,
        b.baseline_std_aircraft,
        b.baseline_mean_positioned,
        b.baseline_std_positioned

    from {{ ref('mart_traffic_timeseries_5min') }}  as t
    left join {{ ref('mart_traffic_baseline_28d') }} as b
        on t.bbox_name = b.bbox_name

),

scored as (

    select
        *,

        -- nullif prevents division-by-zero when std = 0.
        round(
            (aircraft_count - baseline_mean_aircraft)
            / nullif(baseline_std_aircraft, 0),
        3) as z_aircraft,

        round(
            (positioned_aircraft_count - baseline_mean_positioned)
            / nullif(baseline_std_positioned, 0),
        3) as z_positioned

    from joined

)

select
    bbox_name,
    bucket_ts,
    aircraft_count,
    positioned_aircraft_count,

    baseline_mean_aircraft,
    baseline_std_aircraft,
    z_aircraft,

    baseline_mean_positioned,
    baseline_std_positioned,
    z_positioned,

    -- Anomaly flag: significant deviation in either series.
    case
        when abs(z_aircraft)    >= 3 then true
        when abs(z_positioned)  >= 3 then true
        else false
    end as is_anomaly,

    -- Direction only set when the primary series breaches the threshold.
    case
        when z_aircraft >=  3 then 'spike'
        when z_aircraft <= -3 then 'drop'
        else null
    end as anomaly_direction

from scored
order by bbox_name, bucket_ts
