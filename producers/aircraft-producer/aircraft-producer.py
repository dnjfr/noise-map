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
ROTATION_DELAY = int(os.getenv("ROTATION_DELAY", "10"))  # secondes entre chaque zone en rotation

# 2 zones de 250 nm (463 km) couvrant la France métropolitaine + Corse
FRANCE_ZONES = [
    (46.923,  1.105,  250),   # Cléré-du-Bois (36700) — zone ouest/centre/nord
    (45.070,  6.030,  250),   # Allemond (38114)       — zone est/sud/Corse
]

# Polygone simplifié de la France métropolitaine (sens horaire, ~13 points)
# Exclut Suisse, nord Italie, NE Espagne, sud Angleterre
FRANCE_METRO_POLYGON = [
    (51.1,  2.6),   # Dunkerque
    (50.0,  6.2),   # frontière belgo-luxembourgeoise
    (49.5,  8.2),   # frontière allemande (Wissembourg)
    (47.6,  7.6),   # frontière suisse (Bâle)
    (46.4,  6.9),   # frontière suisse (Genève)
    (45.9,  6.9),   # frontière italo-suisse (Mont-Blanc)
    (43.8,  7.6),   # frontière italienne (Nice/Monaco)
    (43.3,  3.2),   # côte méditerranéenne (Cap Leucate)
    (42.4,  1.8),   # frontière espagnole (Pyrénées orientales)
    (43.4, -1.8),   # frontière espagnole (Hendaye)
    (47.5, -2.2),   # Bretagne sud
    (48.5, -4.8),   # Brest (pointe Finistère)
    (50.0, -1.8),   # Cherbourg
]

# Corse : bbox simple (la forme de l'île ne justifie pas un polygone)
CORSE_LAT_MIN, CORSE_LAT_MAX = 41.3, 43.1
CORSE_LON_MIN, CORSE_LON_MAX =  8.5,  9.6

CIVIL_CATEGORIES = {"A1", "A2", "A3", "A4", "A5"}


def _point_in_polygon(lat, lon, polygon):
    """Ray casting — retourne True si (lat, lon) est à l'intérieur du polygone."""
    inside = False
    j = len(polygon) - 1
    for i, (lat_i, lon_i) in enumerate(polygon):
        lat_j, lon_j = polygon[j]
        if ((lon_i > lon) != (lon_j > lon)) and \
           (lat < (lat_j - lat_i) * (lon - lon_i) / (lon_j - lon_i) + lat_i):
            inside = not inside
        j = i
    return inside


def is_in_france(lat, lon):
    """Retourne True si les coordonnées sont en France métropolitaine ou en Corse."""
    # Pré-filtre bbox global pour court-circuiter rapidement les points lointains
    if not (41.3 <= lat <= 51.1 and -5.1 <= lon <= 9.6):
        return False
    if _point_in_polygon(lat, lon, FRANCE_METRO_POLYGON):
        return True
    return CORSE_LAT_MIN <= lat <= CORSE_LAT_MAX and CORSE_LON_MIN <= lon <= CORSE_LON_MAX


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
    primary_url  = f"https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}"
    fallback_url = f"https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
    # fallback_url = f"https://api.adsb.one/v2/point/{lat}/{lon}/{radius}"
    
    for url in (primary_url, fallback_url):
        try:
            response = requests.get(url, timeout=15)
            if response.status_code in (429, 403):
                logger.warning(f"HTTP {response.status_code} zone ({lat}, {lon}) [{url}] — source ignorée")
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("ac", [])
        except Exception as e:
            logger.error(f"Erreur zone ({lat}, {lon}) [{url}]: {e}")
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
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        if not is_in_france(lat, lon):
            continue
        try:
            producer.send("aircraft-positions", value=parse_aircraft(ac))
            published += 1
        except Exception as e:
            logger.error(f"Erreur Kafka publish avion {ac.get('hex', '?')}: {e}")
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
    logger.info("Scan initial des 2 zones (2s entre chaque)...")
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
        # 1. Scan initial complet (2s entre chaque zone = 4s au total)
        initial_scan(producer)

        # 2. Rotation continue : une zone toutes les 10s (chaque zone rafraîchie toutes les 20s)
        logger.info(f"Rotation continue démarrée ({ROTATION_DELAY}s entre chaque zone)...")
        zone_index = 0
        while True:
            lat, lon, radius = FRANCE_ZONES[zone_index]
            aircraft_list = fetch_zone(lat, lon, radius)
            try:
                filter_and_publish(
                    producer,
                    aircraft_list,
                    f"Zone {zone_index + 1}/2 ({lat}, {lon}, r={radius}nm)"
                )
            except Exception as e:
                logger.error(f"Erreur Kafka publish, pause 60s: {e}")
                time.sleep(60)
                continue
            zone_index = (zone_index + 1) % len(FRANCE_ZONES)
            time.sleep(ROTATION_DELAY)

    except KeyboardInterrupt:
        logger.info("Arrêt du producer")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
