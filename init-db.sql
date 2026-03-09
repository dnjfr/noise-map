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
CREATE TABLE IF NOT EXISTS noise_levels (
    time TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    noise_db DOUBLE PRECISION NOT NULL,
    aircraft_count INTEGER,
    grid_id VARCHAR(20)
);

-- Convertir en hypertable
SELECT create_hypertable('noise_levels', 'time', if_not_exists => TRUE);

-- Index pour optimiser les requêtes géographiques
CREATE INDEX IF NOT EXISTS idx_aircraft_positions_coords 
    ON aircraft_positions (latitude, longitude, time DESC);

CREATE INDEX IF NOT EXISTS idx_noise_levels_coords 
    ON noise_levels (latitude, longitude, time DESC);

CREATE INDEX IF NOT EXISTS idx_noise_levels_grid 
    ON noise_levels (grid_id, time DESC);

-- Politique de rétention : garder 7 jours de données
SELECT add_retention_policy('aircraft_positions', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('noise_levels', INTERVAL '7 days', if_not_exists => TRUE);

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