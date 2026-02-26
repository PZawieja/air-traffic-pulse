-- Air Traffic Pulse — raw DuckDB schema
-- Idempotent: safe to run multiple times.

CREATE SCHEMA IF NOT EXISTS raw;

-- ---------------------------------------------------------------------------
-- Ingestion run audit trail
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
    run_id          VARCHAR     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR     NOT NULL,   -- running, success, or failed
    records_loaded  INTEGER     NOT NULL DEFAULT 0,
    error_msg       VARCHAR
);

-- ---------------------------------------------------------------------------
-- Raw aircraft state vectors from the OpenSky Network /states/all endpoint
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.opensky_states (
    ingestion_ts    TIMESTAMPTZ NOT NULL,
    data_ts         BIGINT,           -- OpenSky server-side Unix epoch (payload["time"])
    bbox_name       VARCHAR     NOT NULL,
    icao24          VARCHAR,
    callsign        VARCHAR,
    origin_country  VARCHAR,
    time_position   BIGINT,           -- unix epoch (NULL if no position report)
    last_contact    BIGINT,           -- unix epoch of last ATC/radio contact
    longitude       DOUBLE,
    latitude        DOUBLE,
    baro_altitude   DOUBLE,           -- metres (NULL when on_ground is true)
    on_ground       BOOLEAN,
    velocity        DOUBLE,           -- ground speed in m/s
    true_track      DOUBLE,           -- clockwise from north, degrees
    vertical_rate   DOUBLE,           -- m/s, positive = climbing
    sensors         VARCHAR,          -- JSON array of sensor IDs, or NULL
    geo_altitude    DOUBLE,           -- WGS-84 geometric altitude, metres
    squawk          VARCHAR,
    spi             BOOLEAN,
    position_source INTEGER           -- 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM
);
