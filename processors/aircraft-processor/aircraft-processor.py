import os
import time
import json
import math
from datetime import datetime
from kafka import KafkaConsumer
from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, TIMESTAMP, text
from sqlalchemy.orm import declarative_base, sessionmaker
from collections import defaultdict
from dotenv import load_dotenv
from urllib.parse import quote_plus
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


# Paramètres de la grille (France divisée en grilles de ~10km)
GRID_SIZE = 0.1  # degrés (~10km)

# Définition des modèles SQLAlchemy
Base = declarative_base()

class AircraftPosition(Base):
    __tablename__ = "aircraft_positions"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    icao24 = Column(String(10), primary_key=True, nullable=False)
    callsign = Column(String(10))
    latitude = Column(Float)
    longitude = Column(Float)
    altitude = Column(Float)
    velocity = Column(Float)
    heading = Column(Float)
    vertical_rate = Column(Float)
    on_ground = Column(Boolean)
    aircraft_type = Column(String(10))
    aircraft_desc = Column(String(100))
    aircraft_category = Column(String(5))

class AircraftNoiseLevel(Base):
    __tablename__ = "aircraft_noise_levels"
    
    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    latitude = Column(Float, primary_key=True, nullable=False)
    longitude = Column(Float, primary_key=True, nullable=False)
    noise_db = Column(Float, nullable=False)
    aircraft_count = Column(Integer)
    grid_id = Column(String(20))

def create_db_engine():
    """Crée et retourne un moteur SQLAlchemy connecté à TimescaleDB.

    Réessaie jusqu'à 10 fois avec 5s de délai (la DB peut mettre du temps
    à démarrer dans Docker).

    Args:
        Aucun.

    Returns:
        Engine: Engine SQLAlchemy prêt à l'emploi (pool_size=10,
            max_overflow=20, pool_pre_ping activé).

    Raises:
        Exception: Si toutes les tentatives échouent.
    """
    max_retries = 10
    retry_delay = 5
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
                echo=False
            )
            # Test de connexion
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connexion à TimescaleDB réussie via SQLAlchemy")
            return engine
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur DB: {e}")
            time.sleep(retry_delay)
    
    raise Exception("Impossible de se connecter à la base de données")

def create_kafka_consumer():
    """Crée et retourne un KafkaConsumer abonné au topic "aircraft-positions".

    Consumer group "noise-processor" avec offset reset à "latest".
    Réessaie jusqu'à 10 fois avec 5s de délai.

    Args:
        Aucun.

    Returns:
        KafkaConsumer: KafkaConsumer configuré avec désérialisation JSON
            automatique.

    Raises:
        Exception: Si toutes les tentatives échouent.
    """
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            consumer = KafkaConsumer(
                "aircraft-positions",
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="noise-processor"
            )
            logger.info("Connexion au consumer Kafka réussie")
            return consumer
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur Kafka: {e}")
            time.sleep(retry_delay)
    
    raise Exception("Impossible de se connecter à Kafka")

CATEGORY_REF_NOISE = {
    "A1": 65,
    "A2": 72,
    "A3": 80,
    "A4": 82,
    "A5": 85,
}

# Constantes NPD (ECAC Doc 29 / EASA MAdB)
D_NPD_REF = 300.0    # Distance de référence certification (m)
V_REF = 82.0         # Vitesse de référence : 160 nœuds en m/s
EPNdB_TO_dBA = -10.0 # Approximation EPNdB → dB(A) Lmax
ALPHA_ATM = 0.002    # Atténuation atmosphérique dB/m (Formule 4)

# Cache MAdB chargé au démarrage (ICAO type code → données de certification)
MADB_CACHE: dict = {}


def load_madb_lookup(engine) -> dict:
    """Charge en mémoire la vue matérialisée icao_noise_resolved.

    Cette vue contient les données de certification acoustique EASA MAdB
    pour chaque type ICAO. En cas d'échec (vue absente, import non fait),
    retourne un dict vide et active le mode fallback (calculate_noise_level).

    Args:
        engine: Engine SQLAlchemy vers TimescaleDB.

    Returns:
        dict: Dictionnaire keyed par code ICAO (ex: "A21N"), valeur = dict
            avec flyover_epndb, approach_epndb, overflight_dba, takeoff_dba,
            noise_unit. Retourne dict vide en cas d'erreur.
    """
    sql = text("""
        SELECT
            icao_code,
            flyover_epndb,
            approach_epndb,
            overflight_dba,
            takeoff_dba,
            noise_unit
        FROM icao_noise_resolved
    """)
    cache = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        for row in rows:
            if row.icao_code not in cache:  # garder la première entrée par code
                cache[row.icao_code] = {
                    "flyover_epndb": row.flyover_epndb,
                    "approach_epndb": row.approach_epndb,
                    "overflight_dba": row.overflight_dba,
                    "takeoff_dba": row.takeoff_dba,
                    "noise_unit": row.noise_unit,
                }
        if cache:
            logger.info(f"MADB cache loaded: {len(cache)} entries")
        else:
            logger.warning("MADB cache empty — fallback mode (run make import-all)")
    except Exception as e:
        logger.warning(f"Impossible de charger le cache MAdB: {e} — fallback mode")
    return cache


def calculate_noise_npd(altitude, velocity, vertical_rate, madb_ref) -> float | None:
    """Calcule le niveau de bruit en dB(A) selon la méthode NPD.

    Utilise la méthode Noise-Power-Distance basée sur les données de
    certification EASA MAdB. Implémente : Formule 3 (distance slant),
    Formule 4 (atténuation atmosphérique si altitude > 500m), Formule 6
    (correction vitesse). Retourne None si madb_ref est None, déclenchant
    le fallback.

    Args:
        altitude (float | None): Altitude en mètres.
        velocity (float | None): Vitesse en m/s.
        vertical_rate (float | None): Taux vertical en m/s (négatif = descente).
        madb_ref (dict | None): Données MAdB du type d'avion.

    Returns:
        float | None: Niveau de bruit en dB(A), minimum 30.0. Retourne None
            si madb_ref est None.
    """
    if madb_ref is None:
        return None

    # Sélection du niveau de référence selon la phase de vol
    if vertical_rate and vertical_rate < -3:   # descente → approche
        reference_epndb = madb_ref.get("approach_epndb") or madb_ref.get("flyover_epndb")
    else:                                       # croisière / survol
        reference_epndb = madb_ref.get("flyover_epndb") or madb_ref.get("approach_epndb")

    if reference_epndb is not None:
        reference_noise_db = reference_epndb + EPNdB_TO_dBA           # EPNdB → dB(A) approximatif
    else:
        # Avions légers : valeur directement en dBA
        reference_noise_db = madb_ref.get("overflight_dba") or madb_ref.get("takeoff_dba")
        if reference_noise_db is None:
            return None

    # Formule 3 : distance slant (d_horizontal ≈ 0 : avion directement au-dessus de la grille)
    if altitude is None or altitude <= 0:
        return None
    clamped_altitude_m = max(altitude, 100)
    slant_distance_m = clamped_altitude_m  # simplification : d_horizontal = 0 dans la cellule de grille
    distance_attenuation_db = -20 * math.log10(slant_distance_m / D_NPD_REF)

    # Formule 4 : atténuation atmosphérique (activée si altitude > 500 m)
    atmospheric_attenuation_db = 0.0
    if clamped_altitude_m > 500:
        atmospheric_attenuation_db = -ALPHA_ATM * slant_distance_m

    # Formule 6 : correction vitesse
    speed_correction_db = 0.0
    if velocity and velocity > 0:
        speed_correction_db = 3 * math.log10(velocity / V_REF)

    noise = reference_noise_db + distance_attenuation_db + atmospheric_attenuation_db + speed_correction_db
    return max(30.0, noise)


def calculate_noise_best(altitude, velocity, vertical_rate, aircraft_type, aircraft_category) -> float:
    """Sélectionne la meilleure méthode de calcul disponible.

    Essaie NPD (MAdB) si le type ICAO est dans le cache, sinon fallback sur
    la formule par catégorie. C'est la fonction principale à appeler pour
    calculer le bruit d'un avion.

    Args:
        altitude (float | None): Altitude en mètres.
        velocity (float | None): Vitesse en m/s.
        vertical_rate (float | None): Taux vertical en m/s.
        aircraft_type (str | None): Code ICAO type (ex: "A21N").
        aircraft_category (str | None): Catégorie ICAO (A1-A5).

    Returns:
        float: Niveau de bruit en dB(A).
    """
    madb_ref = MADB_CACHE.get(aircraft_type) if aircraft_type else None
    result = calculate_noise_npd(altitude, velocity, vertical_rate, madb_ref)
    if result is not None:
        return result
    return calculate_noise_level(altitude, velocity, aircraft_category)


def calculate_noise_level(altitude, velocity, aircraft_category=None):
    """Formule de fallback basée sur la catégorie ICAO.

    Utilise une référence de 80 dB à 300m avec atténuation de 6 dB par
    doublement de distance (-6 dB/octave). Ajustement vitesse ±3 dB
    normalisé autour de 250 m/s.

    Args:
        altitude (float | None): Altitude en mètres.
        velocity (float | None): Vitesse en m/s.
        aircraft_category (str | None): Catégorie ICAO (A1-A5), détermine le
            Lref de base.

    Returns:
        float: Niveau de bruit en dB(A), minimum 0.0.
    """
    if altitude is None or altitude <= 0:
        return 0

    category_reference_noise_db = CATEGORY_REF_NOISE.get(aircraft_category, 80)
    reference_altitude_m = 300

    noise_db = category_reference_noise_db - 6 * math.log2(max(altitude, 100) / reference_altitude_m)

    if velocity:
        normalized_velocity = min(velocity / 250, 1.5)
        noise_db += 3 * (normalized_velocity - 1)

    return max(0, noise_db)

def get_grid_id(lat, lon):
    """Convertit des coordonnées géographiques en identifiant de cellule.

    Convertit des coordonnées géographiques en identifiant de cellule de
    grille 0.1° (~10km). Arrondit lat/lon au multiple de GRID_SIZE le plus
    proche.

    Args:
        lat (float): Latitude.
        lon (float): Longitude.

    Returns:
        str: Identifiant de grille au format "lat_lon" (ex: "48.80_2.30").
    """
    grid_lat = round(lat / GRID_SIZE) * GRID_SIZE
    grid_lon = round(lon / GRID_SIZE) * GRID_SIZE
    return f"{grid_lat:.2f}_{grid_lon:.2f}"

def store_aircraft_position(session, data):
    """Crée un objet AircraftPosition depuis un dict Kafka.

    Crée un objet AircraftPosition depuis un dict Kafka et l'ajoute à la
    session SQLAlchemy (sans commit). Le timestamp est fixé à l'heure UTC
    courante.

    Args:
        session: Session SQLAlchemy active.
        data (dict): Message Kafka désérialisé contenant icao24, latitude,
            longitude, etc.

    Returns:
        None
    """
    position = AircraftPosition(
        time=datetime.utcnow(),
        icao24=data["icao24"],
        callsign=data.get("callsign"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        altitude=data.get("altitude"),
        velocity=data.get("velocity"),
        heading=data.get("heading"),
        vertical_rate=data.get("vertical_rate"),
        on_ground=data.get("on_ground", False),
        aircraft_type=data.get("aircraft_type"),
        aircraft_desc=data.get("aircraft_desc"),
        aircraft_category=data.get("aircraft_category"),
    )
    session.add(position)

def process_batch_and_calculate_noise(session, batch_data):
    """Traite un lot de messages Kafka et calcule le bruit.

    Traite un lot de messages Kafka : ignore les avions au sol, calcule le
    bruit de chaque avion (NPD ou fallback), agrège par cellule de grille
    (moyenne), et stocke un AircraftNoiseLevel par cellule dans la session SQLAlchemy.
    Les niveaux < 30 dB sont ignorés.

    Args:
        session: Session SQLAlchemy active.
        batch_data (list[dict]): Liste de messages Kafka désérialisés.

    Returns:
        None
    """
    grid_noise = defaultdict(lambda: {"total_noise": 0, "count": 0, "coords": None})
    
    for data in batch_data:
        lat = data["latitude"]
        lon = data["longitude"]
        alt = data.get("altitude", 0)
        vel = data.get("velocity", 0)
        
        if data.get("on_ground"):
            continue
        
        # Calculer le bruit
        noise = calculate_noise_best(
            alt,
            vel,
            data.get("vertical_rate"),
            data.get("aircraft_type"),
            data.get("aircraft_category"),
        )
        
        if noise < 30:  # Ignorer les bruits très faibles (fond sonore)
            continue
        
        # Agréger par grille
        grid_id = get_grid_id(lat, lon)
        grid_noise[grid_id]["total_noise"] += noise
        grid_noise[grid_id]["count"] += 1
        grid_noise[grid_id]["coords"] = (lat, lon)
    
    # Stocker les niveaux de bruit agrégés
    for grid_id, data in grid_noise.items():
        if data["count"] == 0:
            continue
        avg_noise = data["total_noise"] / data["count"]
        lat, lon = data["coords"]
        
        noise_level = AircraftNoiseLevel(
            time=datetime.utcnow(),
            latitude=lat,
            longitude=lon,
            noise_db=avg_noise,
            aircraft_count=data["count"],
            grid_id=grid_id
        )
        session.add(noise_level)

def main():
    """Point d'entrée du processor Kafka vers TimescaleDB.

    Point d'entrée du processor. Attend 15s au démarrage, se connecte à
    TimescaleDB et Kafka, charge le cache MAdB, puis consomme le topic
    "aircraft-positions" en boucle. Traite les positions par lots de 50 ou
    toutes les 30s. En cas d'erreur sur un lot, effectue un rollback et
    continue.

    Args:
        Aucun.

    Returns:
        None
    """
    logger.info("Démarrage du processor Kafka -> TimescaleDB")
    
    # Attendre que les services soient prêts
    time.sleep(15)
    
    engine = create_db_engine()
    Session = sessionmaker(bind=engine)

    global MADB_CACHE
    MADB_CACHE = load_madb_lookup(engine)

    batch = []
    batch_size = 50
    last_process_time = time.time()
    process_interval = 30  # Calculer le bruit toutes les 30 secondes

    try:
        while True:
            consumer = None
            try:
                consumer = create_kafka_consumer()
                for message in consumer:
                    data = message.value
                    batch.append(data)

                    # Traiter par lots
                    if len(batch) >= batch_size or (time.time() - last_process_time) > process_interval:
                        session = Session()

                        try:
                            # Stocker les positions
                            for item in batch:
                                store_aircraft_position(session, item)

                            # Calculer et stocker le bruit
                            process_batch_and_calculate_noise(session, batch)

                            session.commit()
                            logger.info(f"✅ Traité {len(batch)} positions - Bruit calculé")

                        except Exception as e:
                            session.rollback()
                            logger.error(f"Erreur lors du traitement: {e}")
                        finally:
                            session.close()

                        batch = []
                        last_process_time = time.time()

            except KeyboardInterrupt:
                logger.info("Arrêt du processor")
                break
            except Exception as e:
                logger.error(f"Erreur consumer Kafka, reconnexion dans 5s : {e}")
                batch = []
                time.sleep(5)
            finally:
                if consumer is not None:
                    try:
                        consumer.close()
                    except Exception:
                        pass
    finally:
        engine.dispose()

if __name__ == "__main__":
    main()