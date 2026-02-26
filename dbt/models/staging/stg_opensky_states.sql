with source as (

    select * from {{ source('raw', 'opensky_states') }}

),

cleaned as (

    select
        -- ── Identifiers ────────────────────────────────────────────────────
        cast(ingestion_ts as timestamptz)                              as ingestion_ts,
        cast(data_ts      as bigint)                                   as data_ts,
        bbox_name,

        -- icao24 is always lowercase hex from the OpenSky API, but enforce it
        lower(icao24)                                                  as icao24,

        -- Normalise callsign: blank / whitespace-only → NULL
        case
            when trim(callsign) = '' or callsign is null then null
            else trim(callsign)
        end                                                            as callsign,

        cast(origin_country as varchar)                                as origin_country,

        -- ── Timing ─────────────────────────────────────────────────────────
        cast(time_position as bigint)                                  as time_position,
        cast(last_contact  as bigint)                                  as last_contact,

        -- ── Position ───────────────────────────────────────────────────────
        cast(longitude     as double)                                  as longitude,
        cast(latitude      as double)                                  as latitude,
        cast(baro_altitude as double)                                  as baro_altitude,
        cast(geo_altitude  as double)                                  as geo_altitude,
        cast(on_ground     as boolean)                                 as on_ground,

        -- ── Kinematics ─────────────────────────────────────────────────────
        cast(velocity      as double)                                  as velocity,
        cast(true_track    as double)                                  as true_track,
        cast(vertical_rate as double)                                  as vertical_rate,

        -- ── Transponder metadata ───────────────────────────────────────────
        cast(position_source as integer)                               as position_source,
        cast(squawk          as varchar)                               as squawk,
        cast(spi             as boolean)                               as spi,
        cast(sensors         as varchar)                               as sensors,

        -- ── Derived columns ────────────────────────────────────────────────
        cast(ingestion_ts as date)                                     as ingestion_date,
        (longitude is not null and latitude is not null)               as has_position

    from source

)

select * from cleaned
