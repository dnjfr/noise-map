import os
import json
import math
import time
import logging
from datetime import datetime
from kafka import KafkaConsumer
from sqlalchemy import create_engine, Column, String, Float, Integer, TIMESTAMP, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

Base = declarative_base()


class RoadNoiseLevel(Base):
    __tablename__ = "road_noise_levels"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    code_pme = Column(String(20), primary_key=True)
    noise_db = Column(Float, nullable=False)
    traffic_flow = Column(Integer)
    average_speed = Column(Float)


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
                "road-segments",
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="road-processor",
            )
            logger.info("Connexion au consumer Kafka réussie")
            return consumer
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur Kafka: {e}")
            time.sleep(5)
    raise Exception("Impossible de se connecter à Kafka")


# 90 km/h : vitesse de référence autoroute/nationale hors agglomération (source : CERTU/Sétra,
#   guide NMPB-Routes-2008 §3.2 — vitesse nominale retenue pour les tronçons sans mesure GPS)
DEFAULT_SPEED_KMH = 90

# 500 veh/h : débit de référence pour trafic interurbain modéré sur 2×2 voies (source : Sétra 2009,
#   tableau 2 — seuil médian entre trafic faible <200 et chargé >1000 veh/h)
DEFAULT_FLOW_VEH_H = 500


def _energy_add(l1, l2):
    """Addition énergétique NMPB : 10·log(10^(L1/10) + 10^(L2/10))."""
    return 10 * math.log10(10 ** (l1 / 10) + 10 ** (l2 / 10))


def calculate_road_noise(flow_veh_h, speed_kmh, nb_voies=1, highway_type="trunk"):
    """Calcul bruit NMPB-Routes-2008 avec pondération VL/PL (Sétra 2009).

    Args:
        flow_veh_h: Débit total en véhicules/heure (None/0 accepté → DEFAULT_FLOW_VEH_H si speed dispo)
        speed_kmh: Vitesse moyenne VL en km/h (None accepté → DEFAULT_SPEED_KMH si flow dispo)
        nb_voies: Nombre de voies (conservé pour compatibilité, non utilisé dans NMPB)
        highway_type: Type de route ("motorway" ou "trunk")

    Returns:
        float: Niveau de bruit en dB(A), ou None si les deux métriques sont absentes
    """
    # Drop uniquement si les deux sont absentes (pas de données du tout)
    if (flow_veh_h is None or flow_veh_h <= 0) and (speed_kmh is None or speed_kmh <= 0):
        return None
    if flow_veh_h is None or flow_veh_h <= 0:
        flow_veh_h = DEFAULT_FLOW_VEH_H
    if speed_kmh is None or speed_kmh <= 0:
        speed_kmh = DEFAULT_SPEED_KMH

    # Pondération VL/PL selon type de route
    if highway_type == "motorway":
        ratio_pl = 0.10
        v_pl = 90.0
    else:  # trunk et autres
        ratio_pl = 0.07
        v_pl = 80.0

    q_vl = flow_veh_h * (1 - ratio_pl)
    q_pl = flow_veh_h * ratio_pl
    v_vl = max(speed_kmh, 20)
    v_pl = max(v_pl, 20)

    # Formules Lr (revêtement R2 — standard)
    lr_vl = 55.4 + 20.1 * math.log10(v_vl / 90)
    lr_pl = 63.4 + 20.0 * math.log10(v_pl / 80)

    # Formules Lm (allure stabilisée, déclivité 0%)
    if v_vl < 30:
        lm_vl = 36.7 - 10 * math.log10(v_vl / 90)
    elif v_vl < 110:
        lm_vl = 42.4 + 2 * math.log10(v_vl / 90)
    else:
        lm_vl = 40.7 + 21.3 * math.log10(v_vl / 90)

    if v_pl < 70:
        lm_pl = 49.6 - 10 * math.log10(v_pl / 80)
    else:
        lm_pl = 50.4 + 3 * math.log10(v_pl / 80)

    # Puissance par type de véhicule
    lw_vl = _energy_add(lr_vl, lm_vl)
    lw_pl = _energy_add(lr_pl, lm_pl)

    # Source totale L_W/m
    terme_vl = lw_vl + 10 * math.log10(q_vl) if q_vl > 0 else None
    terme_pl = lw_pl + 10 * math.log10(q_pl) if q_pl > 0 else None

    if terme_vl is not None and terme_pl is not None:
        l_source = _energy_add(terme_vl, terme_pl)
    elif terme_vl is not None:
        l_source = terme_vl
    elif terme_pl is not None:
        l_source = terme_pl
    else:
        return None

    # Propagation cylindrique à 25m (source linéaire) : L(r) = L_W/m - 10·log(2·π·r)
    l_25m = l_source - 10 * math.log10(2 * math.pi * 25)
    return round(max(30.0, l_25m), 1)


def process_batch(session, batch):
    """Traite un lot de messages Kafka et stocke les niveaux de bruit."""
    stored = 0
    dropped = 0
    for data in batch:
        flow = data.get("traffic_flow")
        speed = data.get("average_speed")
        nb_voies = data.get("nb_voies", 1) or 1
        highway_type = data.get("highway_type", "trunk")
        noise_db = calculate_road_noise(flow, speed, nb_voies, highway_type)
        if noise_db is None:
            dropped += 1
            continue
        noise_level = RoadNoiseLevel(
            time=datetime.utcnow(),
            code_pme=data["code_pme"],
            noise_db=noise_db,
            traffic_flow=flow,
            average_speed=speed,
        )
        session.add(noise_level)
        stored += 1
    if dropped:
        logger.warning(f"  {dropped} segments ignorés (flow ET speed absents simultanément)")
    return stored


def main():
    logger.info("Démarrage du road-processor Kafka -> TimescaleDB")
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
                    stored = process_batch(session, batch)
                    session.commit()
                    logger.info(f"Traité {len(batch)} messages - {stored} niveaux de bruit stockés")
                except Exception as e:
                    session.rollback()
                    logger.error(f"Erreur lors du traitement: {e}")
                finally:
                    session.close()

                batch = []
                last_process_time = time.time()

    except KeyboardInterrupt:
        logger.info("Arrêt du road-processor")
    finally:
        consumer.close()
        engine.dispose()


if __name__ == "__main__":
    main()
