with source as (

    select * from {{ source('raw', 'ingestion_runs') }}

),

cleaned as (

    select
        cast(run_id       as varchar)     as run_id,
        cast(started_at   as timestamptz) as started_at,
        cast(finished_at  as timestamptz) as finished_at,
        cast(status       as varchar)     as status,
        cast(records_loaded as integer)   as records_loaded,
        cast(error_msg    as varchar)     as error_msg,

        -- ── Derived columns ────────────────────────────────────────────────
        case
            when finished_at is not null
                then datediff('second', started_at, finished_at)
        end                               as run_duration_seconds,

        (status = 'success')              as is_success

    from source

)

select * from cleaned
