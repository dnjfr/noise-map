import os
import time
import json
import requests
from kafka import KafkaProducer
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ROTATION_DELAY = int(os.getenv("ROTATION_DELAY", "4"))  # secondes entre chaque zone en rotation

# 5 zones couvrant la France métropolitaine (lat, lon, rayon en nm)
# Conversions : 463 km = 250 nm | 100 km = 54 nm | 70 km = 38 nm | 60 km = 32 nm | 180 km = 97 nm
FRANCE_ZONES = [
    (46.923,  1.105,  250),   # Cléré-du-Bois (36700)     — 463 km, zone centrale
    (48.268,  6.981,   38),   # Sainte-Marguerite (88100)  — 70 km,  est
    (43.779,  6.340,   54),   # La Palud-sur-Verdon (04120)— 100 km, sud-est
    (42.771,  2.453,   32),   # Le Vivier (66730)          — 60 km,  Pyrénées
    (42.566,  8.757,   97),   # Calvi                      — 180 km, Corse
]

CIVIL_CATEGORIES = {"A1", "A2", "A3", "A4", "A5"}


def create_kafka_producer():
    """Crée et retourne un KafkaProducer connecté au broker défini dans KAFKA_BOOTSTRAP_SERVERS.

    Réessaie jusqu'à 10 fois avec 5s de délai si la connexion échoue.

    Args:
        None

    Returns:
        KafkaProducer configuré avec sérialisation JSON et acks="all"

    Raises:
        Exception: Si toutes les tentatives de connexion échouent.
    """
    max_retries = 10
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info("Connexion à Kafka réussie")
            return producer
        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/{max_retries} - Erreur Kafka: {e}")
            time.sleep(retry_delay)

    raise Exception("Impossible de se connecter à Kafka")


def fetch_zone(lat, lon, radius):
    """Interroge l'API adsb.one pour récupérer tous les avions dans un rayon donné.

    En cas de 429 (rate limit) sur adsb.one, bascule automatiquement sur airplanes.live
    (API identique). Retourne une liste vide si les deux sources échouent.

    Args:
        lat (float): Latitude du centre.
        lon (float): Longitude du centre.
        radius (int): Rayon en nautical miles.

    Returns:
        list: Liste de dicts représentant les avions (format adsb.one/airplanes.live).
    """
    primary_url  = f"https://api.adsb.one/v2/point/{lat}/{lon}/{radius}"
    fallback_url = f"https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}"
    
    for url in (primary_url, fallback_url):
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 429 and url == primary_url:
                logger.warning(f"429 adsb.one zone ({lat}, {lon}) — bascule sur airplanes.live")
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("ac", [])
        except Exception as e:
            logger.error(f"Erreur zone ({lat}, {lon}) [{url}]: {e}")
            if url == primary_url:
                continue
    return []


def filter_and_publish(producer, aircraft_list, label=""):
    """Filtre la liste d'avions pour ne garder que les avions civils (catégories A1-A5) avec des coordonnées valides, puis publie chacun sur le topic Kafka "aircraft-positions".

    Args:
        producer: KafkaProducer utilisé pour publier les messages.
        aircraft_list (list): Liste de dicts au format adsb.one.
        label (str, optional): Libellé pour le log. Défaut: "".

    Returns:
        int: Nombre d'avions publiés.
    """
    published = 0
    for ac in aircraft_list:
        if ac.get("category") not in CIVIL_CATEGORIES:
            continue
        if ac.get("lat") is None or ac.get("lon") is None:
            continue
        producer.send("aircraft-positions", value=parse_aircraft(ac))
        published += 1
    producer.flush()
    if label:
        logger.info(f"{label}: {published} avions publiés")
    return published


def initial_scan(producer):
    """Effectue un scan initial de toutes les zones FRANCE_ZONES avec 2s de délai entre chaque. Déduplique les avions vus dans plusieurs zones (garde celui avec la donnée la plus récente selon "seen"), puis publie le résultat complet.

    Args:
        producer: KafkaProducer à utiliser pour publier.

    Returns:
        None
    """
    logger.info("Scan initial des 6 zones (2s entre chaque)...")
    all_aircraft = {}

    for lat, lon, radius in FRANCE_ZONES:
        aircraft_list = fetch_zone(lat, lon, radius)
        logger.info(f"  Zone ({lat}, {lon}, r={radius}nm): {len(aircraft_list)} avions")

        for ac in aircraft_list:
            hex_id = ac.get("hex")
            if not hex_id:
                continue
            seen = ac.get("seen", 9999)
            if hex_id not in all_aircraft or seen < all_aircraft[hex_id].get("seen", 9999):
                all_aircraft[hex_id] = ac

        time.sleep(2)

    filter_and_publish(producer, list(all_aircraft.values()), "Scan initial")


def parse_aircraft(ac):
    """Convertit un dict d'avion au format adsb.one en dict normalisé avec unités SI, prêt à être publié sur Kafka.

    Args:
        ac (dict): Avion au format adsb.one (champs : hex, flight, lat, lon, alt_baro, gs, track, baro_rate, category, t, desc...).

    Returns:
        dict: Dict avec les champs : timestamp, icao24, callsign, latitude, longitude, altitude (m), velocity (m/s), heading (°), vertical_rate (m/s), on_ground, aircraft_type, aircraft_desc, aircraft_category.
    """
    alt_baro = ac.get("alt_baro")
    altitude_m = alt_baro / 3.28084 if isinstance(alt_baro, (int, float)) else None

    gs = ac.get("gs")
    velocity_ms = gs * 0.514444 if isinstance(gs, (int, float)) else None

    baro_rate = ac.get("baro_rate")
    vertical_rate_ms = baro_rate * 0.00508 if isinstance(baro_rate, (int, float)) else None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "icao24": ac.get("hex"),
        "callsign": ac.get("flight", "").strip() or None,
        "latitude": ac.get("lat"),
        "longitude": ac.get("lon"),
        "altitude": altitude_m,
        "velocity": velocity_ms,
        "heading": ac.get("track"),
        "vertical_rate": vertical_rate_ms,
        "on_ground": False,
        "aircraft_type": ac.get("t"),
        "aircraft_desc": ac.get("desc"),
        "aircraft_category": ac.get("category"),
    }


def main():
    """Point d'entrée du producer. Attend 10s au démarrage pour laisser Kafka initialiser, puis effectue un scan initial complet de toutes les zones et entre en rotation continue (une zone toutes les ROTATION_DELAY secondes).

    Args:
        None

    Returns:
        None
    """
    logger.info("Démarrage du producer adsb.one -> Kafka")
    logger.info(f"{len(FRANCE_ZONES)} zones, chaque zone rafraîchie toutes les {ROTATION_DELAY * len(FRANCE_ZONES)}s")

    time.sleep(10)

    producer = create_kafka_producer()

    try:
        # 1. Scan initial complet (2s entre chaque zone = 12s au total)
        initial_scan(producer)

        # 2. Rotation continue : une zone toutes les 4s (chaque zone rafraîchie toutes les 24s)
        logger.info(f"Rotation continue démarrée ({ROTATION_DELAY}s entre chaque zone)...")
        zone_index = 0
        while True:
            lat, lon, radius = FRANCE_ZONES[zone_index]
            aircraft_list = fetch_zone(lat, lon, radius)
            filter_and_publish(
                producer,
                aircraft_list,
                f"Zone {zone_index + 1}/6 ({lat}, {lon}, r={radius}nm)"
            )
            zone_index = (zone_index + 1) % len(FRANCE_ZONES)
            time.sleep(ROTATION_DELAY)

    except KeyboardInterrupt:
        logger.info("Arrêt du producer")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
