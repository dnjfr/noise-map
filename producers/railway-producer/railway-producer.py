import os
import time
import json
import math
import logging
import requests
from datetime import datetime, timezone
from kafka import KafkaProducer
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TIMESCALE_HOST     = os.getenv("TIMESCALE_HOST")
TIMESCALE_PORT     = os.getenv("TIMESCALE_PORT")
TIMESCALE_NAME     = os.getenv("TIMESCALE_NAME")
TIMESCALE_USER     = os.getenv("TIMESCALE_USER")
TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD")
DATABASE_URL = f"postgresql+psycopg://{TIMESCALE_USER}:{TIMESCALE_PASSWORD}@{TIMESCALE_HOST}:{TIMESCALE_PORT}/{TIMESCALE_NAME}"

# SNCF GTFS-RT URL
GTFS_RT_URL = os.getenv("GTFS_RT_URL", "https://proxy.transport.data.gouv.fr/resource/sncf-gtfs-rt-trip-updates")

POLL_INTERVAL = 30  # 30 secondes
STOPS_RELOAD_HOURS = 24

# Cache léger des arrêts (petite table ~10k entrées, stable)
_stops_cache: dict = {}
_last_stops_load: float = 0.0


def create_kafka_producer():
    for attempt in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info("Connexion Kafka réussie")
            return producer
        except Exception as e:
            logger.warning(f"Tentative {attempt+1}/10 - Erreur Kafka: {e}")
            time.sleep(5)
    raise Exception("Impossible de se connecter à Kafka")


def create_db_engine():
    for attempt in range(10):
        try:
            engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connexion DB réussie")
            return engine
        except Exception as e:
            logger.warning(f"Tentative {attempt+1}/10 - Erreur DB: {e}")
            time.sleep(5)
    raise Exception("Impossible de se connecter à la DB")


# ─── GTFS Static ─────────────────────────────────────────────────────────────

def ensure_stops_cache(engine):
    """Charge/rafraîchit le cache des arrêts (petite table ~10k entrées, stable)."""
    global _stops_cache, _last_stops_load
    if _stops_cache and (time.monotonic() - _last_stops_load) < STOPS_RELOAD_HOURS * 3600:
        return True
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT stop_id, stop_name, stop_lat, stop_lon FROM rail_stops"
            )).fetchall()
        if not rows:
            logger.error("Table rail_stops vide — lancez 'make import-gtfs' avant de démarrer")
            return False
        _stops_cache = {stop_id: {"name": name, "lat": lat, "lon": lon} for stop_id, name, lat, lon in rows}
        _last_stops_load = time.monotonic()
        logger.info(f"Stops rechargés: {len(_stops_cache)}")
        return True
    except Exception as e:
        logger.error(f"Erreur chargement rail_stops: {e}")
        return False


def load_active_gtfs_data(engine, trip_ids: list):
    """Charge depuis la DB uniquement les données des trips actifs (trips, stop_times).

    Les shapes ne sont pas chargées ici : elles sont servies directement au frontend
    par l'API (/api/railways/shapes). Le producer utilise l'interpolation stop-to-stop
    (fallback) qui ne nécessite pas les géométries OSM.

    Retourne un dict gtfs_static partiel, ou None en cas d'erreur.
    """
    if not trip_ids:
        return None
    try:
        with engine.connect() as conn:
            # trips → {trip_id: {route_id, shape_id, trip_short_name}}
            rows = conn.execute(text(
                "SELECT trip_id, route_id, shape_id, trip_short_name FROM rail_trips WHERE trip_id = ANY(:ids)"
            ), {"ids": trip_ids}).fetchall()
            if not rows:
                logger.warning("Aucun trip actif trouvé dans rail_trips")
                return None
            trips = {
                trip_id: {"route_id": route_id or "", "shape_id": shape_id or "", "trip_short_name": name or ""}
                for trip_id, route_id, shape_id, name in rows
            }

            # stop_times → {trip_id: [{stop_id, arrival, departure, seq, dist}, ...]}
            rows = conn.execute(text(
                "SELECT trip_id, stop_id, arrival_time, departure_time, stop_sequence, shape_dist_traveled "
                "FROM rail_stop_times WHERE trip_id = ANY(:ids) ORDER BY trip_id, stop_sequence"
            ), {"ids": trip_ids}).fetchall()
            stop_times: dict = {}
            for trip_id, stop_id, arrival, departure, seq, dist in rows:
                if trip_id not in stop_times:
                    stop_times[trip_id] = []
                stop_times[trip_id].append({
                    "stop_id": stop_id,
                    "arrival": arrival or "",
                    "departure": departure or "",
                    "seq": seq,
                    "dist": dist or 0.0,
                })

        logger.info(f"Données actives chargées: {len(trips)} trips")
        return {"trips": trips, "stop_times": stop_times, "shapes": {}, "stops": _stops_cache}

    except Exception as e:
        logger.error(f"Erreur chargement données actives GTFS: {e}")
        return None


# ─── GTFS-RT ─────────────────────────────────────────────────────────────────

def parse_time_str(t_str):
    """Parse HH:MM:SS to seconds since midnight (handles >24h for overnight)."""
    try:
        parts = t_str.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        return None


def interpolate_position(trip_id, gtfs_static, now_utc, delay_seconds=0):
    """Interpolate train position along the shape or between stops."""
    trips = gtfs_static["trips"]
    stop_times_map = gtfs_static["stop_times"]
    stops = gtfs_static["stops"]
    shapes = gtfs_static["shapes"]

    trip_info = trips.get(trip_id)
    if not trip_info:
        return None

    st_list = stop_times_map.get(trip_id)
    if not st_list or len(st_list) < 2:
        return None

    # Current time as seconds since midnight, ajusté du retard réel.
    # On borne le retard à ±3h pour éviter un now_secs invalide si la donnée GTFS-RT est aberrante.
    clamped_delay = max(-10800, min(delay_seconds, 10800))
    now_secs = now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second - clamped_delay

    # Find current segment (between which two stops)
    prev_stop = None
    next_stop = None
    for i in range(len(st_list) - 1):
        dep_secs = parse_time_str(st_list[i].get("departure", ""))
        arr_secs = parse_time_str(st_list[i + 1].get("arrival", ""))
        if dep_secs is None or arr_secs is None:
            continue
        if dep_secs <= now_secs <= arr_secs:
            prev_stop = st_list[i]
            next_stop = st_list[i + 1]
            break

    if not prev_stop or not next_stop:
        return None

    dep_secs = parse_time_str(prev_stop["departure"])
    arr_secs = parse_time_str(next_stop["arrival"])
    if dep_secs is None or arr_secs is None or arr_secs <= dep_secs:
        return None

    progress = (now_secs - dep_secs) / (arr_secs - dep_secs)
    progress = max(0.0, min(1.0, progress))

    # Shape-based interpolation using shape_dist_traveled
    # d1/d2 = distances cumulées le long de la shape à l'arrêt précédent/suivant
    # target_dist = d1 + progress * (d2 - d1) → position exacte dans le segment
    shape_id = trip_info.get("shape_id", "")
    shape_coords = shapes.get(shape_id)  # [[lon, lat, dist], ...]
    d1 = prev_stop.get("dist", 0.0) or 0.0
    d2 = next_stop.get("dist", 0.0) or 0.0
    if shape_coords and len(shape_coords) >= 2 and d2 > d1:
        target_dist = d1 + progress * (d2 - d1)
        for j in range(len(shape_coords) - 1):
            da = shape_coords[j][2]
            db = shape_coords[j+1][2]
            if da <= target_dist <= db and db > da:
                frac = (target_dist - da) / (db - da)
                lon = shape_coords[j][0] + frac * (shape_coords[j+1][0] - shape_coords[j][0])
                lat = shape_coords[j][1] + frac * (shape_coords[j+1][1] - shape_coords[j][1])
                dlng = shape_coords[j+1][0] - shape_coords[j][0]
                dlat = shape_coords[j+1][1] - shape_coords[j][1]
                heading = math.degrees(math.atan2(dlng, dlat)) % 360
                next_stop_info = stops.get(next_stop["stop_id"], {})
                prev_stop_info = stops.get(prev_stop["stop_id"], {})
                return {
                    "latitude": lat,
                    "longitude": lon,
                    "heading": round(heading, 1),
                    "next_stop_name": next_stop_info.get("name", ""),
                    "prev_stop_name": prev_stop_info.get("name", ""),
                }

    # Fallback: linear interpolation between stops
    prev_stop_info = stops.get(prev_stop["stop_id"])
    next_stop_info = stops.get(next_stop["stop_id"])
    if not prev_stop_info or not next_stop_info:
        return None

    lat = prev_stop_info["lat"] + progress * (next_stop_info["lat"] - prev_stop_info["lat"])
    lon = prev_stop_info["lon"] + progress * (next_stop_info["lon"] - prev_stop_info["lon"])
    dlng = next_stop_info["lon"] - prev_stop_info["lon"]
    dlat = next_stop_info["lat"] - prev_stop_info["lat"]
    heading = math.degrees(math.atan2(dlng, dlat)) % 360

    prev_stop_info_fb = stops.get(prev_stop["stop_id"], {})
    return {
        "latitude": lat,
        "longitude": lon,
        "heading": round(heading, 1),
        "next_stop_name": next_stop_info.get("name", ""),
        "prev_stop_name": prev_stop_info_fb.get("name", ""),
    }


def fetch_gtfs_rt():
    """Fetch GTFS-RT TripUpdates from SNCF."""
    try:
        resp = requests.get(GTFS_RT_URL, timeout=30)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        return feed
    except Exception as e:
        logger.error(f"Erreur fetch GTFS-RT: {e}")
        return None


def estimate_speed(prev_stop, next_stop, stops):
    """Estimate speed in km/h based on distance between stops and schedule."""
    p = stops.get(prev_stop.get("stop_id"))
    n = stops.get(next_stop.get("stop_id"))
    if not p or not n:
        return 80.0  # default

    dep = parse_time_str(prev_stop.get("departure", ""))
    arr = parse_time_str(next_stop.get("arrival", ""))
    if not dep or not arr or arr <= dep:
        return 80.0

    dlat = math.radians(n["lat"] - p["lat"])
    dlon = math.radians(n["lon"] - p["lon"])
    a = math.sin(dlat/2)**2 + math.cos(math.radians(p["lat"])) * math.cos(math.radians(n["lat"])) * math.sin(dlon/2)**2
    dist_km = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    duration_h = (arr - dep) / 3600.0
    if duration_h <= 0:
        return 80.0
    return min(round(dist_km / duration_h, 1), 320.0)


def process_and_publish(producer, engine, feed):
    """Process GTFS-RT feed and publish train positions to Kafka."""
    now_utc = datetime.now(timezone.utc)
    published = 0

    active_trip_ids = []
    trip_delays = {}

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            tu = entity.trip_update
            trip_id = tu.trip.trip_id
            active_trip_ids.append(trip_id)

            # Get delay from last stop_time_update
            if tu.stop_time_update:
                last_stu = tu.stop_time_update[-1]
                if last_stu.arrival and last_stu.arrival.delay:
                    trip_delays[trip_id] = last_stu.arrival.delay
                elif last_stu.departure and last_stu.departure.delay:
                    trip_delays[trip_id] = last_stu.departure.delay

    if not active_trip_ids:
        logger.warning("Aucun trip actif dans le feed GTFS-RT")
        return 0

    # Chargement à la demande : uniquement les données des trips actifs
    gtfs_static = load_active_gtfs_data(engine, active_trip_ids)
    if not gtfs_static:
        return 0

    for trip_id in active_trip_ids:
        delay = trip_delays.get(trip_id, 0)
        pos = interpolate_position(trip_id, gtfs_static, now_utc, delay_seconds=delay)
        if not pos:
            continue

        trip_info = gtfs_static["trips"].get(trip_id, {})

        # Estimate speed (aussi ajusté du retard pour trouver le bon segment)
        st_list = gtfs_static["stop_times"].get(trip_id, [])
        speed = 80.0
        if len(st_list) >= 2:
            now_secs = now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second - delay
            for i in range(len(st_list) - 1):
                dep = parse_time_str(st_list[i].get("departure", ""))
                arr = parse_time_str(st_list[i+1].get("arrival", ""))
                if dep and arr and dep <= now_secs <= arr:
                    speed = estimate_speed(st_list[i], st_list[i+1], gtfs_static["stops"])
                    break

        message = {
            "timestamp": now_utc.isoformat(),
            "trip_id": trip_id,
            "train_number": trip_info.get("trip_short_name", ""),
            "route_id": trip_info.get("route_id", ""),
            "latitude": pos["latitude"],
            "longitude": pos["longitude"],
            "speed_kmh": speed,
            "heading": pos["heading"],
            "delay_seconds": delay,
            "next_stop_name": pos["next_stop_name"],
            "prev_stop_name": pos.get("prev_stop_name", ""),
        }

        producer.send("railway-positions", value=message)
        published += 1

    producer.flush()
    logger.info(f"Publié {published} positions de trains sur Kafka")
    return published


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("Démarrage du railway-producer GTFS-RT -> Kafka")
    time.sleep(10)

    engine = create_db_engine()
    producer = create_kafka_producer()

    if not ensure_stops_cache(engine):
        logger.error("Impossible de charger rail_stops. Arrêt.")
        return

    try:
        while True:
            # Rafraîchir le cache des arrêts si nécessaire (toutes les 24h)
            ensure_stops_cache(engine)

            feed = fetch_gtfs_rt()
            if feed:
                process_and_publish(producer, engine, feed)
            else:
                logger.warning("Pas de données GTFS-RT, retry dans 120s")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Arrêt du railway-producer")
    finally:
        producer.close()
        engine.dispose()


if __name__ == "__main__":
    main()
