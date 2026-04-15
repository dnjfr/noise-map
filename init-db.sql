-- Créer l'extension TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Table pour stocker les positions des avions
CREATE TABLE IF NOT EXISTS aircraft_positions (
    time TIMESTAMPTZ NOT NULL,
    icao24 VARCHAR(10) NOT NULL,
    callsign VARCHAR(10),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    velocity DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    vertical_rate DOUBLE PRECISION,
    on_ground BOOLEAN,
    aircraft_type VARCHAR(10),
    aircraft_desc VARCHAR(100),
    aircraft_category VARCHAR(5)
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
    grid_id VARCHAR(20)
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

-- Table de correspondance codes ICAO → fabricant/modèle (FAA JO 7360.1H)
CREATE TABLE IF NOT EXISTS icao_type_mapping (
    id             SERIAL PRIMARY KEY,
    icao_code      VARCHAR(10)  NOT NULL,
    manufacturer   VARCHAR(200),
    model          VARCHAR(300) NOT NULL,
    aircraft_class VARCHAR(50),
    wtc            VARCHAR(10),
    UNIQUE(icao_code, manufacturer, model)
);
CREATE INDEX IF NOT EXISTS idx_icao_type_code ON icao_type_mapping(icao_code);

-- Table de correspondance ICAO → patterns madb_noise_ref (pour jointures)
CREATE TABLE IF NOT EXISTS icao_to_madb_pattern (
    id                        SERIAL PRIMARY KEY,
    icao_code                 VARCHAR(10)  NOT NULL,
    madb_model_pattern        VARCHAR(200) NOT NULL,
    madb_manufacturer_pattern VARCHAR(200),
    notes                     VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS idx_icao_to_madb_code ON icao_to_madb_pattern(icao_code);

-- Table de référence des niveaux de bruit certifiés MAdB (EASA/ICAO)
CREATE TABLE IF NOT EXISTS madb_noise_ref (
    id SERIAL PRIMARY KEY,
    source VARCHAR(20) NOT NULL,
    record_number VARCHAR(20),
    manufacturer VARCHAR(100),
    aircraft_model VARCHAR(200),
    mtom_kg INTEGER,
    lateral_epndb FLOAT,
    flyover_epndb FLOAT,
    approach_epndb FLOAT,
    overflight_dba FLOAT,
    takeoff_dba FLOAT,
    noise_unit VARCHAR(10) NOT NULL,
    UNIQUE(source, record_number)
);

-- Index GIN trigram pour accélérer les regex ~ sur aircraft_model
CREATE INDEX IF NOT EXISTS idx_madb_aircraft_model_trgm
    ON madb_noise_ref USING GIN (aircraft_model gin_trgm_ops);

-- Vue matérialisée pré-calculant la jointure icao_to_madb_pattern × madb_noise_ref
-- Réduit load_madb_lookup de 2-3 min à < 1s
-- Rafraîchir après make import-all : make refresh-madb-view
CREATE MATERIALIZED VIEW IF NOT EXISTS icao_to_madb_resolved AS
SELECT
    p.icao_code,
    m.flyover_epndb,
    m.approach_epndb,
    m.overflight_dba,
    m.takeoff_dba,
    m.noise_unit
FROM icao_to_madb_pattern p
JOIN madb_noise_ref m
    ON (p.madb_manufacturer_pattern IS NULL
        OR m.manufacturer ILIKE p.madb_manufacturer_pattern)
   AND m.aircraft_model ~ p.madb_model_pattern
WITH NO DATA;

CREATE INDEX IF NOT EXISTS idx_icao_resolved_code
    ON icao_to_madb_resolved (icao_code);

-- Référentiel statique des segments routiers (rempli au démarrage du road-producer)
CREATE TABLE IF NOT EXISTS road_segments_ref (
    code_pme       VARCHAR(20) PRIMARY KEY,
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
    code_pme      VARCHAR(20) NOT NULL,
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

-- Référentiel statique des routes ferroviaires (shapes GTFS)
CREATE TABLE IF NOT EXISTS railway_routes_ref (
    route_id TEXT PRIMARY KEY,
    route_name TEXT,
    shape_coords JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Tables GTFS SNCF ────────────────────────────────────────────────────────
-- Remplies par : python3 archives/railway/import_gtfs.py
-- Tables statiques (import unique, stables) : rail_stops, rail_routes, rail_shapes
-- Tables temporelles (2x/an, changements de service) : rail_trips, rail_stop_times, rail_calendar

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
CREATE TABLE IF NOT EXISTS rail_trips (
    trip_id              TEXT PRIMARY KEY,
    route_id             TEXT NOT NULL,
    service_id           TEXT NOT NULL,
    shape_id             TEXT,
    trip_short_name      TEXT,
    trip_headsign        TEXT,
    direction_id         SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_rail_trips_route  ON rail_trips (route_id);
CREATE INDEX IF NOT EXISTS idx_rail_trips_shape  ON rail_trips (shape_id);
CREATE INDEX IF NOT EXISTS idx_rail_trips_service ON rail_trips (service_id);

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

