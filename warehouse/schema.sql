-- Air Traffic Pulse — raw DuckDB schema
-- This file is idempotent; safe to run multiple times.

CREATE TABLE IF NOT EXISTS raw_states (
    ingested_at     TIMESTAMPTZ NOT NULL,
    bbox_name       VARCHAR     NOT NULL,
    icao24          VARCHAR,
    callsign        VARCHAR,
    origin_country  VARCHAR,
    time_position   BIGINT,       -- unix epoch seconds; NULL if no position report
    last_contact    BIGINT,       -- unix epoch seconds
    longitude       DOUBLE,
    latitude        DOUBLE,
    baro_altitude   DOUBLE,       -- metres; NULL if on ground
    on_ground       BOOLEAN,
    velocity        DOUBLE,       -- m/s
    true_track      DOUBLE,       -- clockwise from north, degrees
    vertical_rate   DOUBLE,       -- m/s; positive = climbing
    geo_altitude    DOUBLE,       -- metres; geometric WGS-84 altitude
    squawk          VARCHAR,
    spi             BOOLEAN,
    position_source INTEGER       -- 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM
);
