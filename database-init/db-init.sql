-- Créer l'extension TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table pour stocker les positions des avions
CREATE TABLE IF NOT EXISTS aircraft_positions (
    time TIMESTAMPTZ NOT NULL,
    icao24 TEXT NOT NULL,
    callsign TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    velocity DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    vertical_rate DOUBLE PRECISION,
    on_ground BOOLEAN,
    aircraft_type TEXT,
    aircraft_desc TEXT,
    aircraft_category TEXT
);

-- Convertir en hypertable pour optimisation temporelle
SELECT create_hypertable('aircraft_positions', 'time', if_not_exists => TRUE);

-- Table pour stocker les niveaux de bruit calculés par zone
CREATE TABLE IF NOT EXISTS aircraft_noise_levels (
    time TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    noise_db DOUBLE PRECISION NOT NULL,
    aircraft_count INTEGER,
    grid_id TEXT
);

-- Convertir en hypertable
SELECT create_hypertable('aircraft_noise_levels', 'time', if_not_exists => TRUE);

-- Index pour optimiser les requêtes géographiques
CREATE INDEX IF NOT EXISTS idx_aircraft_positions_coords
    ON aircraft_positions (latitude, longitude, time DESC);

CREATE INDEX IF NOT EXISTS idx_aircraft_noise_levels_coords
    ON aircraft_noise_levels (latitude, longitude, time DESC);

CREATE INDEX IF NOT EXISTS idx_aircraft_noise_levels_grid
    ON aircraft_noise_levels (grid_id, time DESC);

-- Politique de rétention : garder 7 jours de données
SELECT add_retention_policy('aircraft_positions', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('aircraft_noise_levels', INTERVAL '7 days', if_not_exists => TRUE);

-- Référentiel statique des segments routiers (rempli au démarrage du road-producer)
CREATE TABLE IF NOT EXISTS road_segments_ref (
    code_pme       TEXT PRIMARY KEY,
    axe            VARCHAR(20),
    source         VARCHAR(10),
    lat_deb        DOUBLE PRECISION,
    lon_deb        DOUBLE PRECISION,
    lat_fin        DOUBLE PRECISION,
    lon_fin        DOUBLE PRECISION,
    longueur       INTEGER,
    nb_voies       INTEGER,
    sens_cardinal  VARCHAR(20),
    geom_osm       JSONB,
    maxspeed       INTEGER,
    surface        VARCHAR(30),
    bridge         BOOLEAN DEFAULT FALSE,
    tunnel         BOOLEAN DEFAULT FALSE,
    highway_type   VARCHAR(50),
    average_speed  DOUBLE PRECISION,
    free_flow_speed DOUBLE PRECISION,
    traffic_flow   INTEGER,
    fetched_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Migration pour les DB existantes
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS maxspeed INTEGER;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS surface VARCHAR(30);
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS bridge BOOLEAN DEFAULT FALSE;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS tunnel BOOLEAN DEFAULT FALSE;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS highway_type VARCHAR(50);
ALTER TABLE road_segments_ref ALTER COLUMN highway_type TYPE VARCHAR(50);
ALTER TABLE road_segments_ref ALTER COLUMN axe TYPE TEXT;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS average_speed DOUBLE PRECISION;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS free_flow_speed DOUBLE PRECISION;
ALTER TABLE road_segments_ref ADD COLUMN IF NOT EXISTS traffic_flow INTEGER;

-- Niveaux de bruit routier par segment (hypertable TimescaleDB)
CREATE TABLE IF NOT EXISTS road_noise_levels (
    time          TIMESTAMPTZ NOT NULL,
    code_pme      TEXT NOT NULL,
    noise_db      DOUBLE PRECISION NOT NULL,
    traffic_flow  INTEGER,
    average_speed DOUBLE PRECISION
);
SELECT create_hypertable('road_noise_levels', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_road_noise_code_pme ON road_noise_levels (code_pme, time DESC);
SELECT add_retention_policy('road_noise_levels', INTERVAL '7 days', if_not_exists => TRUE);

-- ─── Pipeline ferroviaire (trains SNCF) ────────────────────────────────────

-- Positions des trains (hypertable, pattern aircraft_positions)
CREATE TABLE IF NOT EXISTS railway_positions (
    time TIMESTAMPTZ NOT NULL,
    trip_id TEXT NOT NULL,
    train_number TEXT,
    route_id TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    speed_kmh DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    delay_seconds INTEGER,
    next_stop_name TEXT,
    prev_stop_name TEXT
);
SELECT create_hypertable('railway_positions', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_railway_positions_coords
    ON railway_positions (latitude, longitude, time DESC);
SELECT add_retention_policy('railway_positions', INTERVAL '7 days', if_not_exists => TRUE);
ALTER TABLE railway_positions ADD COLUMN IF NOT EXISTS prev_stop_name TEXT;

-- Niveaux de bruit ferroviaire (hypertable, pattern noise_levels)
CREATE TABLE IF NOT EXISTS railway_noise_levels (
    time TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    noise_db DOUBLE PRECISION NOT NULL,
    train_count INTEGER,
    grid_id TEXT
);
SELECT create_hypertable('railway_noise_levels', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_railway_noise_coords
    ON railway_noise_levels (latitude, longitude, time DESC);
CREATE INDEX IF NOT EXISTS idx_railway_noise_grid
    ON railway_noise_levels (grid_id, time DESC);
SELECT add_retention_policy('railway_noise_levels', INTERVAL '7 days', if_not_exists => TRUE);

-- ─── Tables GTFS SNCF ────────────────────────────────────────────────────────
-- Statiques (backup) : rail_stops, rail_routes, rail_route_shapes
-- Temporelles (refetchées depuis SNCF à chaque mise à jour) : rail_trips, rail_stop_times

CREATE TABLE IF NOT EXISTS rail_stops (
    stop_id          TEXT PRIMARY KEY,
    stop_name        TEXT NOT NULL,
    stop_lat         DOUBLE PRECISION NOT NULL,
    stop_lon         DOUBLE PRECISION NOT NULL,
    parent_station   TEXT,
    location_type    SMALLINT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rail_stops_name ON rail_stops (stop_name);

CREATE TABLE IF NOT EXISTS rail_routes (
    route_id         TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name  TEXT,
    route_type       SMALLINT,
    route_color      VARCHAR(6),
    agency_id        TEXT
);

-- Trips SNCF — temporels, rechargés depuis SNCF à chaque mise à jour GTFS
CREATE TABLE IF NOT EXISTS rail_trips (
    trip_id          TEXT PRIMARY KEY,
    route_id         TEXT NOT NULL,
    service_id       TEXT NOT NULL,
    shape_id         TEXT,
    trip_short_name  TEXT,
    trip_headsign    TEXT,
    direction_id     SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_rail_trips_route ON rail_trips (route_id);
CREATE INDEX IF NOT EXISTS idx_rail_trips_shape ON rail_trips (shape_id);

-- Mapping statique (route_id, first_stop, last_stop) → shape_id
-- Calculé une fois par assign_shapes.py après l'import pfaedle, sauvegardé dans db-backup.
-- Appliqué automatiquement par import-gtfs.py après chaque rechargement des trips.
CREATE TABLE IF NOT EXISTS rail_route_shapes (
    route_id     TEXT NOT NULL,
    first_stop   TEXT NOT NULL,
    last_stop    TEXT NOT NULL,
    shape_id     TEXT NOT NULL,
    match_score  DOUBLE PRECISION,
    PRIMARY KEY (route_id, first_stop, last_stop)
);
CREATE INDEX IF NOT EXISTS idx_rail_route_shapes_route ON rail_route_shapes (route_id);

CREATE TABLE IF NOT EXISTS rail_shapes (
    shape_id             TEXT NOT NULL,
    shape_pt_lat         DOUBLE PRECISION NOT NULL,
    shape_pt_lon         DOUBLE PRECISION NOT NULL,
    shape_pt_sequence    INTEGER NOT NULL,
    shape_dist_traveled  DOUBLE PRECISION,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);
CREATE INDEX IF NOT EXISTS idx_rail_shapes_id ON rail_shapes (shape_id);

-- Tables temporelles — TRUNCATE + reload à chaque changement de service SNCF
CREATE TABLE IF NOT EXISTS rail_stop_times (
    trip_id              TEXT NOT NULL,
    stop_id              TEXT NOT NULL,
    stop_sequence        INTEGER NOT NULL,
    arrival_time         TEXT,   -- HH:MM:SS, peut dépasser 24h (SNCF nuit)
    departure_time       TEXT,
    shape_dist_traveled  DOUBLE PRECISION,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_rail_stop_times_trip ON rail_stop_times (trip_id);
CREATE INDEX IF NOT EXISTS idx_rail_stop_times_stop ON rail_stop_times (stop_id);

CREATE TABLE IF NOT EXISTS rail_calendar (
    service_id      TEXT NOT NULL,
    date            DATE NOT NULL,
    exception_type  SMALLINT NOT NULL,  -- 1=ajouté, 2=supprimé
    PRIMARY KEY (service_id, date)
);
CREATE INDEX IF NOT EXISTS idx_rail_calendar_date ON rail_calendar (date);

