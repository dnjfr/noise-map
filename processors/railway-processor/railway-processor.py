import os
import re
import json
import math
import time
import logging
from datetime import datetime
from kafka import KafkaConsumer
from sqlalchemy import create_engine, Column, String, Float, Integer, TIMESTAMP, text
from sqlalchemy.orm import declarative_base, sessionmaker
from collections import defaultdict
from dotenv import load_dotenv
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

GRID_SIZE = 0.1
_SERVICE_TYPE_RE = re.compile(r'_[FR]:([A-Z]+):')

Base = declarative_base()


class RailwayPosition(Base):
    __tablename__ = "railway_positions"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    trip_id = Column(String, primary_key=True)
    train_number = Column(String)
    route_id = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    speed_kmh = Column(Float)
    heading = Column(Float)
    delay_seconds = Column(Integer)
    next_stop_name = Column(String)
    prev_stop_name = Column(String)


class RailwayNoiseLevel(Base):
    __tablename__ = "railway_noise_levels"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    latitude = Column(Float, primary_key=True)
    longitude = Column(Float, primary_key=True)
    noise_db = Column(Float, nullable=False)
    train_count = Column(Integer)
    grid_id = Column(String)


def create_db_engine():
    max_retries = 10
    database_url = (
        f"postgresql+psycopg://{os.getenv('TIMESCALE_USER')}:{quote_plus(os.getenv('TIMESCALE_PASSWORD'))}"
        f"@{os.getenv('TIMESCALE_HOST')}:{os.getenv('TIMESCALE_PORT')}/{os.getenv('TIMESCALE_NAME')}"
    )
    for attempt in range(max_retries):
        try:
            engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                echo=False,
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connexion à TimescaleDB réussie")
            return engine
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur DB: {e}")
            time.sleep(5)
    raise Exception("Impossible de se connecter à la base de données")


def create_kafka_consumer():
    max_retries = 10
    for attempt in range(max_retries):
        try:
            consumer = KafkaConsumer(
                "railway-positions",
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="railway-processor",
            )
            logger.info("Connexion au consumer Kafka réussie")
            return consumer
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur Kafka: {e}")
            time.sleep(5)
    raise Exception("Impossible de se connecter à Kafka")


RAILWAY_NOISE_REF = {
    'TGV':  {'l_ref': 92.0, 'v_ref': 300.0},
    'IC':   {'l_ref': 82.0, 'v_ref': 200.0},
    'TER':  {'l_ref': 80.0, 'v_ref': 140.0},
    'FRET': {'l_ref': 88.0, 'v_ref': 100.0},
}
DEFAULT_REF = {'l_ref': 80.0, 'v_ref': 140.0}


def extract_service_type(trip_id: str) -> str:
    """Extrait TGV/TER/IC/FRET du trip_id SNCF (ex: OCESN..._F:TER:...)"""
    m = _SERVICE_TYPE_RE.search(trip_id)
    return m.group(1) if m else ''


def calculate_railway_noise(speed_kmh, distance_m=25.0, service_type=''):
    """CRN/CNOSSOS formula for railway noise with per-type references.
    Propagation cylindrique : -10*log10(d/25)
    Correction vitesse : 30*log10(v/v_ref)
    """
    ref = RAILWAY_NOISE_REF.get(service_type, DEFAULT_REF)
    l_ref = ref['l_ref']
    v_ref = ref['v_ref']

    if speed_kmh is None or speed_kmh <= 0:
        speed_kmh = v_ref * 0.5

    speed_correction = 30.0 * math.log10(max(speed_kmh, 10) / v_ref)
    distance_attenuation = -10.0 * math.log10(max(distance_m, 1) / 25.0)

    noise = l_ref + speed_correction + distance_attenuation
    return max(30.0, round(noise, 1))


def get_grid_id(lat, lon):
    grid_lat = round(lat / GRID_SIZE) * GRID_SIZE
    grid_lon = round(lon / GRID_SIZE) * GRID_SIZE
    return f"{grid_lat:.2f}_{grid_lon:.2f}"


def store_railway_position(session, data):
    position = RailwayPosition(
        time=datetime.utcnow(),
        trip_id=data["trip_id"],
        train_number=data.get("train_number"),
        route_id=data.get("route_id"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        speed_kmh=data.get("speed_kmh"),
        heading=data.get("heading"),
        delay_seconds=data.get("delay_seconds"),
        next_stop_name=data.get("next_stop_name"),
        prev_stop_name=data.get("prev_stop_name"),
    )
    session.add(position)


def process_batch_and_calculate_noise(session, batch_data):
    grid_noise = defaultdict(lambda: {"total_noise": 0, "count": 0, "coords": None})

    for data in batch_data:
        lat = data["latitude"]
        lon = data["longitude"]
        speed = data.get("speed_kmh", 80)
        service_type = extract_service_type(data.get("trip_id", ""))

        noise = calculate_railway_noise(speed, service_type=service_type)
        if noise < 30:
            continue

        grid_id = get_grid_id(lat, lon)
        grid_noise[grid_id]["total_noise"] += noise
        grid_noise[grid_id]["count"] += 1
        grid_noise[grid_id]["coords"] = (lat, lon)

    for grid_id, data in grid_noise.items():
        if data["count"] == 0:
            continue
        avg_noise = data["total_noise"] / data["count"]
        lat, lon = data["coords"]

        noise_level = RailwayNoiseLevel(
            time=datetime.utcnow(),
            latitude=lat,
            longitude=lon,
            noise_db=avg_noise,
            train_count=data["count"],
            grid_id=grid_id,
        )
        session.add(noise_level)


def main():
    logger.info("Démarrage du railway-processor Kafka -> TimescaleDB")
    time.sleep(15)

    engine = create_db_engine()
    Session = sessionmaker(bind=engine)
    consumer = create_kafka_consumer()

    batch = []
    batch_size = 50
    last_process_time = time.time()
    process_interval = 30

    try:
        for message in consumer:
            data = message.value
            batch.append(data)

            if len(batch) >= batch_size or (time.time() - last_process_time) > process_interval:
                session = Session()
                try:
                    for item in batch:
                        store_railway_position(session, item)
                    process_batch_and_calculate_noise(session, batch)
                    session.commit()
                    logger.info(f"Traité {len(batch)} positions de trains - Bruit calculé")
                except Exception as e:
                    session.rollback()
                    logger.error(f"Erreur lors du traitement: {e}")
                finally:
                    session.close()

                batch = []
                last_process_time = time.time()

    except KeyboardInterrupt:
        logger.info("Arrêt du railway-processor")
    finally:
        consumer.close()
        engine.dispose()


if __name__ == "__main__":
    main()
