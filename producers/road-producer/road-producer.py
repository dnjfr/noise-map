import os
import json
import time
import math
import logging
import hashlib
import requests
import mapbox_vector_tile
from shapely.geometry import shape
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from kafka import KafkaProducer
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

# ─── Config ──────────────────────────────────────────────────────────────────

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TIMESCALE_HOST     = os.getenv("TIMESCALE_HOST")
TIMESCALE_PORT     = os.getenv("TIMESCALE_PORT")
TIMESCALE_NAME     = os.getenv("TIMESCALE_NAME")
TIMESCALE_USER     = os.getenv("TIMESCALE_USER")
TIMESCALE_PASSWORD = quote_plus(os.getenv("TIMESCALE_PASSWORD"))
DATABASE_URL = f"postgresql+psycopg://{TIMESCALE_USER}:{TIMESCALE_PASSWORD}@{TIMESCALE_HOST}:{TIMESCALE_PORT}/{TIMESCALE_NAME}"

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

POLL_INTERVAL = 300  # 5 minutes


# Filtrage géographique : ne garder que les segments en France métropolitaine + Corse.
# Chaque tuple : (lon_min, lat_min, lon_max, lat_max)
_FRANCE_BBOXES = (
    # ── Côtes et frontières (petites boxes précises) ──────────────
    ( 1.5, 50.3,  2.5, 51.1),   # Côte nord Manche : Calais, Dunkerque, frontière belge
    ( 1.5, 49.5,  3.2, 50.8),   # Hauts-de-France / Lille - frontière belge ~50.7°N
    ( 3.2, 49.0,  4.0, 50.3),   # Picardie + Aisne - frontière belge ~50.0°N à 4°E
    ( 4.0, 48.8,  4.86, 50.0),  # Charleville Mezières - Chalon en Champagne
    ( 4.9, 48.8,  5.2, 49.7),   # Sedan
    ( 5.2, 48.8,  6.55, 49.5),  # Thionville - Metz
    (-1.7, 49.2, -1.32, 49.7),  # Côte normande : Cherbourg
    (-1.3, 49.0,  0.5, 49.3),   # Cotentin : Caen
    ( 0.0, 49.0,  1.3, 49.9),   # Normandie : Rouen, Evreux, Dieppe
    ( 4.0, 48.5, 6.41, 49.5),   # Lorraine + Ardennes - sous Belgique/Luxembourg
    ( 6.4, 48.5,  7.8, 49.2),   # Alsace - à l'ouest du Rhin ; Strasbourg inclus
    ( 6.4, 47.6,  7.7, 48.5),   # Alsace - Epinal, Mulhouse, Montbéliar, Belfort
    ( 5.5, 46.5,  6.3, 47.8),   # Doubs + Jura - clip frontière suisse
    ( 5.5, 45.5,  6.8, 46.13),  # Savoie : Annecy, Chambery
    ( 6.31, 46.1,  6.8, 46.4),  # Savoie : Thonon les Bains
    ( 5.8, 43.0, 6.86, 44.5),   # Hautes-Alpes + Alpes-de-Haute-Provence
    ( 6.86, 43.5, 7.49, 44.12), # Alpes-Maritimes - Cannes, Nice, Monaco
    ( 4.3, 43.0, 6.9, 44.15),   # Côte médit. Marseille–Var : Toulon, Marseille
    (-1.53, 43.0, 3.8, 43.49),  # Bande des Pyrénées - Pays Basque + Béarn : Hendaye, Ariège + PO
    ( 3.12, 43.5, 4.3, 44.1),   # Montpellier, Alès
    ( 1.79, 42.4, 3.17, 43.0),  # Perpignan
    ( 0.0, 43.4,  3.2, 44.2),   # Toulouse, Montauban, Millau
    (-1.9, 43.5, -0.5, 46.0),   # Côte atlantique Landes + Gironde : Bayonne
    (-2.5, 45.5, -0.2, 47.5),   # Côte atlantique Vendée + Charente : La Rochelle
    (-4.8, 48.0, -1.8, 48.7),   # Bretagne : Brest
    (-4.4, 47.8, -1.8, 48.0),   # Bretagne : Quimpert, Concarneau
    (-3.5, 47.6, -1.8, 47.8),   # Bretagne : Lorient, Vannes
    (-2.5, 47.2, -1.8, 47.6),   # Bretagne : Saint-Nazaire
    # ── Intérieur (grandes boxes, loin des frontières) ────────────
    (-2.0, 47.0,  3.5, 49.5),   # Normandie intérieure + Pays de Loire + IDF + Centre-Val de Loire
    ( 3.5, 47.0,  6.5, 49.0),   # Grand Est : Champagne + Lorraine intérieure + Bourgogne nord
    (-1.5, 44.5,  4.5, 47.0),   # Centre-France : Auvergne + Limousin + Berry + Bourgogne sud
    ( 4.0, 44.5,  5.8, 47.0),   # Rhône-Alpes intérieur : Lyon
    (-1.0, 43.5,  3.0, 45.5),   # Sud-Ouest intérieur : Lot + Aveyron + Cantal + Gers + Toulousain
    ( 3.0, 43.5,  6.5, 45.5),   # Midi intérieur : Ardèche + Gard + Vaucluse + Drôme + Provence
    # ── Corse ─────────────────────────────────────────────────────
    ( 8.5, 41.3,  9.6, 43.2),
)

def _is_in_france(lat: float, lon: float) -> bool:
    """True si (lat, lon) est dans au moins une bbox France."""
    return any(
        lo_min <= lon <= lo_max and la_min <= lat <= la_max
        for lo_min, la_min, lo_max, la_max in _FRANCE_BBOXES
    )


# road_type TomTom → config interne
# Valeurs exactes selon la doc TomTom (attention : "International road", "Major road", pas "International")
# Zoom 6 : motorway + trunk visibles, pas les routes secondaires
TOMTOM_ROAD_TYPE_CONFIG = {
    "Motorway":           {"nb_voies": 3, "highway_type": "motorway", "maxspeed": 130},
    "International road": {"nb_voies": 2, "highway_type": "trunk",    "maxspeed": 110},
    "Major road":         {"nb_voies": 2, "highway_type": "trunk",    "maxspeed": 110},
}


TOMTOM_ZOOM = 8
# 72 tuiles zoom 8 couvrant la France métropolitaine + Corse
# Obtenues en divisant chaque tuile zoom 7 en 4 tuiles zoom 8 (2x, 2y) / (2x+1, 2y) / (2x, 2y+1) / (2x+1, 2y+1)
# Géométrie 4× plus précise qu'au zoom 7 — élimine les routes "fantômes" causées par
# la simplification excessive des polylines au zoom 7.
# 72 req toutes les 5 minutes × 24h = 8 640 req/jour (quota TomTom free : 50k/jour)
TOMTOM_FRANCE_TILES = [
    # Rangée nord — ~49.0-51.0°N (Normandie, Paris-nord, Lille, Alsace-nord)
    (126, 86), (127, 86), (126, 87), (127, 87),  # ex (63,43)
    (128, 86), (129, 86), (128, 87), (129, 87),  # ex (64,43)
    (130, 86), (131, 86), (130, 87), (131, 87),  # ex (65,43)
    (132, 86), (133, 86), (132, 87), (133, 87),  # ex (66,43)
    # Rangée centre-nord — ~47.0-49.0°N (Bretagne, Paris, Bourgogne, Alsace)
    (124, 88), (125, 88), (124, 89), (125, 89),  # ex (62,44)
    (126, 88), (127, 88), (126, 89), (127, 89),  # ex (63,44)
    (128, 88), (129, 88), (128, 89), (129, 89),  # ex (64,44) — Paris tile
    (130, 88), (131, 88), (130, 89), (131, 89),  # ex (65,44)
    (132, 88), (133, 88), (132, 89), (133, 89),  # ex (66,44)
    # Rangée centre-sud — ~45.1-47.0°N (Loire, Auvergne, Lyon, Alpes)
    (126, 90), (127, 90), (126, 91), (127, 91),  # ex (63,45)
    (128, 90), (129, 90), (128, 91), (129, 91),  # ex (64,45)
    (130, 90), (131, 90), (130, 91), (131, 91),  # ex (65,45)
    (132, 90), (133, 90), (132, 91), (133, 91),  # ex (66,45)
    # Rangée sud — ~43.1-45.1°N (Bordeaux, Toulouse, Marseille, Nice)
    (126, 92), (127, 92), (126, 93), (127, 93),  # ex (63,46)
    (128, 92), (129, 92), (128, 93), (129, 93),  # ex (64,46)
    (130, 92), (131, 92), (130, 93), (131, 93),  # ex (65,46)
    (132, 92), (133, 92), (132, 93), (133, 93),  # ex (66,46)
    # Corse — ~41.0-43.1°N
    (134, 94), (135, 94), (134, 95), (135, 95),  # ex (67,47)
]
# Couverture villes clés vérifiée (zoom 8) :
# Brest(124-125,88-89) Nantes(126-127,88-89) Paris(128-129,88-89) Lille(130-131,86-87)
# Strasbourg(132-133,88-89) Lyon(130-131,90-91) Bordeaux(126-127,92-93)
# Toulouse(128-129,92-93) Marseille(130-131,92-93) Nice(132-133,92-93) Ajaccio(134-135,94-95)


# ─── Infra ───────────────────────────────────────────────────────────────────

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


# ─── Utilitaires tuiles XYZ ──────────────────────────────────────────────────

def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convertit coordonnées WGS84 → indices de tuile XYZ."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lat_lon_bounds(x: int, y: int, zoom: int) -> dict:
    """Retourne les bornes géographiques (WGS84) d'une tuile XYZ."""
    n = 2 ** zoom

    def tile_y_to_lat(ty):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))

    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = tile_y_to_lat(y)
    lat_min = tile_y_to_lat(y + 1)
    return {"lat_min": lat_min, "lat_max": lat_max,
            "lon_min": lon_min, "lon_max": lon_max}


# ─── Décodage Vector Tile via mapbox-vector-tile ─────────────────────────────
# Tags TomTom Traffic Flow (mode absolute) :
#   road_type       : "Motorway", "International road", "Major road", "Secondary road", ...
#   traffic_level   : double = vitesse réelle en km/h (mode ABSOLUTE, pas une scale 0-10)
#   left_hand_traffic, road_closure : bool

TOMTOM_TRAFFIC_BASE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/absolute"

# Projection Web Mercator (EPSG:3857) → WGS84 pour mapbox-vector-tile
EPSG3857_ORIGIN = 20037508.3428

def _merc_to_wgs84(x_merc: float, y_merc: float) -> tuple[float, float]:
    """Convertit mètres Web Mercator (EPSG:3857) → (lat, lon) WGS84."""
    lon = x_merc / EPSG3857_ORIGIN * 180.0
    lat = math.degrees(2 * math.atan(math.exp(y_merc / EPSG3857_ORIGIN * math.pi)) - math.pi / 2)
    return lat, lon


def decode_vector_tile(raw: bytes, tile_x: int, tile_y: int, zoom: int) -> list[dict]:
    """
    Décode un PBF TomTom Traffic Flow avec mapbox-vector-tile.
    Retourne une liste de features avec road_type, traffic_level et coords WGS84.
    """
    # mapbox_vector_tile retourne un dict de layers, chaque layer contient des features GeoJSON
    # Les coordonnées sont en pixels tuile (0-4095) — on demande la projection native
    try:
        tile_data = mapbox_vector_tile.decode(raw)
    except Exception as e:
        logger.error(f"[TomTom] Erreur décodage PBF: {e}")
        return []

    # Récupérer le layer Traffic flow (nom exact TomTom)
    layer = tile_data.get("Traffic flow") or tile_data.get("traffic_flow")
    if not layer:
        # Logger les layers disponibles pour debug
        logger.debug(f"[TomTom] Tile {tile_x}/{tile_y} vide (layers: {list(tile_data.keys())})")
        return []

    bounds = tile_to_lat_lon_bounds(tile_x, tile_y, zoom)
    # Buffer pour accepter les segments qui débordent légèrement de la tuile (carrefours, ponts)
    _lat_buf = (bounds["lat_max"] - bounds["lat_min"]) * 0.1
    _lon_buf = (bounds["lon_max"] - bounds["lon_min"]) * 0.1
    n = 2 ** zoom  # nombre de tuiles par axe à ce zoom
    features = []

    for feat in layer.get("features", []):
        geom_type = feat.get("geometry", {}).get("type", "")
        if geom_type not in ("LineString", "MultiLineString"):
            continue

        props = feat.get("properties", {})
        road_type     = props.get("road_type", "")
        traffic_level = props.get("traffic_level")   # 0 (fluide) → 10 (bloqué)
        road_closure  = props.get("road_closure", False)

        # Convertir les coordonnées pixel (0-4095) → WGS84
        # mapbox-vector-tile retourne les coords en unités tuile (extent=4096)
        coords_raw = feat["geometry"]["coordinates"]
        if geom_type == "LineString":
            lines = [coords_raw]
        else:
            lines = coords_raw
        for line in lines:
            coords_wgs84 = []
            for px, py in line:
                # mapbox-vector-tile retourne px/py en unités tuile (0-4095)
                # Y=0 est en HAUT dans MVT → py_flipped place 0 en bas
                # La longitude est linéaire en Mercator → interpolation directe OK
                # La latitude NE peut PAS être interpolée linéairement (projection Mercator)
                # → on utilise la formule Mercator inverse, identique à tile_to_lat_lon_bounds()
                lon = bounds["lon_min"] + (px / 4096.0) * (bounds["lon_max"] - bounds["lon_min"])
                ty_frac = tile_y + (4096 - py) / 4096.0  # position fractionnaire en coordonnées tuile globale
                lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty_frac / n))))
                # Ignorer les points aberrants en dehors des bornes de la tuile (avec buffer)
                if (lat < bounds["lat_min"] - _lat_buf or lat > bounds["lat_max"] + _lat_buf or
                        lon < bounds["lon_min"] - _lon_buf or lon > bounds["lon_max"] + _lon_buf):
                    continue
                coords_wgs84.append((lat, lon))

            if len(coords_wgs84) >= 2:
                features.append({
                    "road_type":     road_type,
                    "traffic_level": int(traffic_level) if traffic_level is not None else 0,
                    "road_closure":  road_closure,
                    "coords":        coords_wgs84,
                })

    logger.info(f"[TomTom] {len(features)} features décodées dans le layer 'Traffic flow'")
    return features


# ─── TomTom fetch + parse ────────────────────────────────────────────────────

def fetch_tomtom_tile(session: requests.Session, api_key: str, zoom: int, x: int, y: int) -> bytes | None:
    """Récupère une Vector Flow Tile TomTom en mode absolute (vitesse réelle km/h)."""
    url = (
        f"https://api.tomtom.com/traffic/map/4/tile/flow/absolute"
        f"/{zoom}/{x}/{y}.pbf?key={api_key}"
    )
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.error(f"[TomTom] Erreur fetch tile {zoom}/{x}/{y}: {e}")
        return None


def parse_tomtom_segments(features: list[dict]) -> dict:
    """
    Filtre les features motorway/trunk.
    traffic_level TomTom : 0 = fluide, 10 = complètement bloqué.
    On en déduit average_speed = freeflow * (1 - traffic_level/10).
    """
    segments = {}
    logged = False
    road_types_seen: set[str] = set()
    for feat in features:
        if feat.get("road_closure"):
            continue  # segment fermé, on skip

        road_types_seen.add(feat.get("road_type", "<vide>"))
        cfg = TOMTOM_ROAD_TYPE_CONFIG.get(feat["road_type"])
        if not cfg:
            continue

        coords = feat["coords"]
        if len(coords) < 2:
            continue

        lat0, lon0       = coords[0]
        lat_fin, lon_fin = coords[-1]

        lat_mid, lon_mid = coords[len(coords) // 2]
        if not (_is_in_france(lat0, lon0) and _is_in_france(lat_mid, lon_mid) and _is_in_france(lat_fin, lon_fin)):
            continue

        # DEBUG — valide que les coords sont bien en WGS84 après conversion
        if not logged:
            logger.info(f"[TomTom] DEBUG premier segment converti: lat0={lat0:.4f} lon0={lon0:.4f} lat_fin={lat_fin:.4f} lon_fin={lon_fin:.4f}")
            logged = True

        # Longueur Haversine en mètres
        longueur = 0
        for i in range(len(coords) - 1):
            dlat = math.radians(coords[i+1][0] - coords[i][0])
            dlon = math.radians(coords[i+1][1] - coords[i][1])
            a = (math.sin(dlat/2)**2
                 + math.cos(math.radians(coords[i][0]))
                 * math.cos(math.radians(coords[i+1][0]))
                 * math.sin(dlon/2)**2)
            longueur += int(6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

        code_pme = "tomtom_" + hashlib.md5(
            f"{lat0:.6f},{lon0:.6f},{lat_fin:.6f},{lon_fin:.6f}".encode()
        ).hexdigest()[:8]

        # En mode ABSOLUTE, traffic_level = vitesse réelle en km/h (pas une échelle 0-10)
        traffic_level    = feat.get("traffic_level", 0)
        current_speed    = float(traffic_level)                   # km/h directement
        free_flow_speed  = float(cfg["maxspeed"])
        average_speed    = round(min(current_speed, free_flow_speed), 1)
        # Congestion ratio : 0.0 (bloqué) → 1.0 (libre)
        congestion_ratio = current_speed / free_flow_speed if free_flow_speed > 0 else 1.0
        congestion_ratio = max(0.0, min(1.0, congestion_ratio))
        traffic_flow     = int(2000 * congestion_ratio)

        segments[code_pme] = {
            "axe":             feat["road_type"],
            "source":          "tomtom",
            "nb_voies":        cfg["nb_voies"],
            "longueur":        longueur,
            "sens_cardinal":   "",
            "lat_deb":         lat0,
            "lon_deb":         lon0,
            "lat_fin":         lat_fin,
            "lon_fin":         lon_fin,
            "geom_osm":        [[lat, lon] for lat, lon in coords],
            "highway_type":    cfg["highway_type"],
            "maxspeed":        cfg["maxspeed"],
            "average_speed":   average_speed,
            "free_flow_speed": free_flow_speed,
            "traffic_flow":    traffic_flow,
        }

    if not segments:
        logger.warning(f"[TomTom] 0 segments extraits. road_types reçus dans la tuile : {sorted(road_types_seen)}")

    return segments


# ─── Upsert DB  ────────────────────────────────────────

UPSERT_SQL = text("""
    INSERT INTO road_segments_ref (
        code_pme, axe, source, lat_deb, lon_deb, lat_fin, lon_fin, longueur,
        nb_voies, sens_cardinal, geom_osm, maxspeed, surface, bridge, tunnel, highway_type,
        average_speed, free_flow_speed, traffic_flow, fetched_at
    ) VALUES (
        :code_pme, :axe, :source, :lat_deb, :lon_deb, :lat_fin, :lon_fin, :longueur,
        :nb_voies, :sens_cardinal, :geom_osm, :maxspeed, NULL, FALSE, FALSE, :highway_type,
        :average_speed, :free_flow_speed, :traffic_flow, :fetched_at
    )
    ON CONFLICT (code_pme) DO UPDATE SET
        axe             = EXCLUDED.axe,
        source          = EXCLUDED.source,
        lat_deb         = EXCLUDED.lat_deb,
        lon_deb         = EXCLUDED.lon_deb,
        lat_fin         = EXCLUDED.lat_fin,
        lon_fin         = EXCLUDED.lon_fin,
        longueur        = EXCLUDED.longueur,
        nb_voies        = EXCLUDED.nb_voies,
        sens_cardinal   = EXCLUDED.sens_cardinal,
        geom_osm        = EXCLUDED.geom_osm,
        maxspeed        = EXCLUDED.maxspeed,
        highway_type    = EXCLUDED.highway_type,
        average_speed   = EXCLUDED.average_speed,
        free_flow_speed = EXCLUDED.free_flow_speed,
        traffic_flow    = EXCLUDED.traffic_flow,
        fetched_at      = EXCLUDED.fetched_at
""")


def upsert_segments(engine, segments: dict):
    fetched_at = datetime.now(timezone.utc)
    rows = [
        {
            "code_pme":        code_pme,
            "axe":             seg["axe"],
            "source":          seg["source"],
            "lat_deb":         seg["lat_deb"],
            "lon_deb":         seg["lon_deb"],
            "lat_fin":         seg["lat_fin"],
            "lon_fin":         seg["lon_fin"],
            "longueur":        seg["longueur"],
            "nb_voies":        seg["nb_voies"],
            "sens_cardinal":   seg["sens_cardinal"],
            "geom_osm":        json.dumps(seg["geom_osm"]),
            "maxspeed":        seg["maxspeed"],
            "highway_type":    seg["highway_type"],
            "average_speed":   seg["average_speed"],
            "free_flow_speed": seg["free_flow_speed"],
            "traffic_flow":    seg["traffic_flow"],
            "fetched_at":      fetched_at,
        }
        for code_pme, seg in segments.items()
    ]
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, rows)


def publish_segments(producer, segments: dict, timestamp: str, city_name: str):
    for code_pme, seg in segments.items():
        producer.send("road-segments", value={
            "timestamp":     timestamp,
            "code_pme":      code_pme,
            "axe":           seg["axe"],
            "city":          city_name,
            "lat_deb":       seg["lat_deb"],
            "lon_deb":       seg["lon_deb"],
            "lat_fin":       seg["lat_fin"],
            "lon_fin":       seg["lon_fin"],
            "geom_osm":      None,
            "longueur":      seg["longueur"],
            "nb_voies":      seg["nb_voies"],
            "maxspeed":      seg["maxspeed"],
            "surface":       None,
            "bridge":        False,
            "tunnel":        False,
            "highway_type":  seg["highway_type"],
            "traffic_flow":  seg["traffic_flow"],
            "average_speed": seg["average_speed"],
            "source":        seg["source"],
        })
    producer.flush()


# ─── TomTom ──────────────────────────────────────────────────────────────────

def _fetch_and_parse_tile(session, api_key, zoom, x, y):
    raw = fetch_tomtom_tile(session, api_key, zoom, x, y)
    if not raw:
        return x, y, {}
    features = decode_vector_tile(raw, x, y, zoom)
    if not features:
        return x, y, {}
    return x, y, parse_tomtom_segments(features)


def poll_tomtom_and_publish(producer, engine, api_key, timestamp):
    total = 0
    MAX_WORKERS = 10
    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_and_parse_tile, session, api_key, TOMTOM_ZOOM, x, y): (x, y)
                for x, y in TOMTOM_FRANCE_TILES
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                x, y = futures[future]
                try:
                    _, _, segments = future.result()
                except Exception as e:
                    logger.error(f"[TomTom] Erreur tuile ({x},{y}): {e}")
                    continue
                if segments:
                    upsert_segments(engine, segments)
                    publish_segments(producer, segments, timestamp, "France")
                    total += len(segments)
                    logger.info(f"[TomTom] {done}/{len(TOMTOM_FRANCE_TILES)} tuiles — {len(segments)} segments insérés ({x},{y})")

    if total == 0:
        logger.warning("[TomTom] Aucun segment extrait sur les 72 tuiles")
    else:
        logger.info(f"[TomTom] Total : {total} segments sur {len(TOMTOM_FRANCE_TILES)} tuiles zoom {TOMTOM_ZOOM}")
    return total


# ─── Main loop ───────────────────────────────────────────────────────────────

def main():
    logger.info(f"Démarrage du road-producer (TomTom {len(TOMTOM_FRANCE_TILES)} tuiles zoom {TOMTOM_ZOOM}, 1h polling)")
    time.sleep(10)

    engine   = create_db_engine()
    producer = create_kafka_producer()
    last_poll = None

    try:
        while True:
            now = time.monotonic()
            if last_poll is None or (now - last_poll) >= POLL_INTERVAL:
                timestamp = datetime.now(timezone.utc).isoformat()

                # TomTom — 1 tuile, 1 requête
                if TOMTOM_API_KEY:
                    poll_tomtom_and_publish(producer, engine, TOMTOM_API_KEY, timestamp)
                else:
                    logger.warning("TOMTOM_API non défini, flux TomTom ignoré")

                last_poll = now

            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Arrêt du road-producer")
    finally:
        producer.close()
        engine.dispose()


if __name__ == "__main__":
    main()