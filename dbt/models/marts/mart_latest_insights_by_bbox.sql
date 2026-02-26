/*
  mart_latest_insights_by_bbox
  ─────────────────────────────
  One insight row per bounding-box, combining:
    - The latest observed aircraft counts
    - The 28-day statistical baseline (mean + std)
    - The z-score for the most recent 5-minute bucket
    - A 1-hour momentum indicator (trend_1h_pct)
    - A Traffic Health Score (0–100) and plain-language label

  trend_1h_pct: percentage change between the latest bucket and the
  average of the preceding 12 buckets (1 hour).  Positive = traffic is
  higher than the recent 1-hour trend; negative = lower.

  traffic_health_score: 100 × exp(−0.35 × |z_aircraft|), clamped 0–100.
  Higher scores = closer to normal.  NULL when z-score is unavailable.

  One row per bbox_name.  Primary consumer: Streamlit Insights table.
*/

with latest_buckets as (

    select
        bbox_name,
        max(bucket_ts) as latest_bucket_ts

    from {{ ref('mart_traffic_timeseries_5min') }}
    group by bbox_name

),

latest_anomaly_row as (

    -- Pull the full anomaly-enriched row for each bbox's latest bucket.
    select
        a.bbox_name,
        a.bucket_ts                 as latest_bucket_ts,
        a.aircraft_count            as latest_aircraft_count,
        a.positioned_aircraft_count as latest_positioned_count,
        a.baseline_mean_aircraft,
        a.baseline_std_aircraft,
        a.z_aircraft                as latest_z_aircraft,
        a.is_anomaly                as latest_is_anomaly,
        a.anomaly_direction         as latest_anomaly_direction

    from {{ ref('mart_traffic_anomalies_5min') }} as a
    inner join latest_buckets as lb
        on  a.bbox_name = lb.bbox_name
        and a.bucket_ts = lb.latest_bucket_ts

),

recent_1h as (

    -- Average aircraft count over the 12 buckets that precede the latest one.
    -- Excludes the latest bucket itself to make the comparison meaningful.
    select
        t.bbox_name,
        avg(t.aircraft_count) as avg_1h_aircraft

    from {{ ref('mart_traffic_timeseries_5min') }} as t
    inner join latest_buckets as lb
        on t.bbox_name = lb.bbox_name
    where
        t.bucket_ts >= lb.latest_bucket_ts - interval '1 hour'
        and t.bucket_ts <  lb.latest_bucket_ts

    group by t.bbox_name

),

combined as (

    select
        la.bbox_name,
        la.latest_bucket_ts,
        la.latest_aircraft_count,
        la.latest_positioned_count,
        la.baseline_mean_aircraft,
        la.baseline_std_aircraft,
        la.latest_z_aircraft,
        la.latest_is_anomaly,
        la.latest_anomaly_direction,

        -- Percent change: latest vs the preceding 1-hour average.
        round(
            case
                when coalesce(r.avg_1h_aircraft, 0) > 0
                then (la.latest_aircraft_count - r.avg_1h_aircraft)
                     / r.avg_1h_aircraft * 100.0
                else null
            end,
        1) as trend_1h_pct,

        -- Traffic Health Score: 100 × exp(−0.35 × severity), clamped 0–100.
        -- NULL when z_aircraft is unavailable (insufficient baseline history).
        case
            when la.latest_z_aircraft is null then null
            else cast(
                round(
                    greatest(0, least(100,
                        100.0 * exp(-0.35 * abs(la.latest_z_aircraft))
                    ))
                ) as integer
            )
        end as traffic_health_score

    from latest_anomaly_row as la
    left join recent_1h      as r  on la.bbox_name = r.bbox_name

)

select
    bbox_name,
    latest_bucket_ts,
    latest_aircraft_count,
    latest_positioned_count,
    baseline_mean_aircraft,
    baseline_std_aircraft,
    latest_z_aircraft,
    latest_is_anomaly,
    latest_anomaly_direction,
    trend_1h_pct,
    traffic_health_score,

    -- Plain-language label derived from the health score.
    case
        when traffic_health_score is null    then null
        when traffic_health_score >= 90      then 'Excellent'
        when traffic_health_score >= 70      then 'Good'
        when traffic_health_score >= 40      then 'Watch'
        else                                      'Investigate'
    end as traffic_health_label

from combined
order by bbox_name
