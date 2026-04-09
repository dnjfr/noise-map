import os
import threading
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, TIMESTAMP, JSON, text, desc, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime, timedelta
from cachetools import TTLCache
from fastapi.responses import Response
import orjson
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

app = FastAPI(title="Noise Map API", version="1.0.0")

# CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration SQLAlchemy
TIMESCALE_USER = os.getenv("TIMESCALE_USER")
TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD")
TIMESCALE_HOST = os.getenv("TIMESCALE_HOST")
TIMESCALE_PORT = os.getenv("TIMESCALE_PORT")
TIMESCALE_NAME = os.getenv("TIMESCALE_NAME")

DATABASE_URL = f"postgresql+psycopg://{TIMESCALE_USER}:{TIMESCALE_PASSWORD}@{TIMESCALE_HOST}:{TIMESCALE_PORT}/{TIMESCALE_NAME}"

# Création du moteur et session
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Cache in-process TTL=5s pour réduire la charge DB sur les endpoints chauds
_aircraft_cache: TTLCache = TTLCache(maxsize=20, ttl=5)
_aircraft_cache_lock = threading.Lock()
_noise_cache: TTLCache = TTLCache(maxsize=50, ttl=5)
_noise_cache_lock = threading.Lock()
_road_cache: TTLCache = TTLCache(maxsize=10, ttl=15)
_road_cache_lock = threading.Lock()
_railway_cache: TTLCache = TTLCache(maxsize=10, ttl=10)
_railway_cache_lock = threading.Lock()
_railway_lines_cache: TTLCache = TTLCache(maxsize=1, ttl=1800)  # géométries statiques, 30 min
_railway_lines_cache_lock = threading.Lock()
_railway_shapes_cache: TTLCache = TTLCache(maxsize=2, ttl=120)  # shapes low/high, 2 min (aligné GTFS-RT)
_railway_shapes_cache_lock = threading.Lock()

# Définition des modèles
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

class NoiseLevel(Base):
    __tablename__ = "aircraft_noise_levels"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    latitude = Column(Float, primary_key=True, nullable=False)
    longitude = Column(Float, primary_key=True, nullable=False)
    noise_db = Column(Float, nullable=False)
    aircraft_count = Column(Integer)
    grid_id = Column(String(20))

class RoadNoiseLevel(Base):
    __tablename__ = "road_noise_levels"

    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    code_pme = Column(String(20), primary_key=True)
    noise_db = Column(Float)
    traffic_flow = Column(Integer)
    average_speed = Column(Float)

class RoadSegmentRef(Base):
    __tablename__ = "road_segments_ref"

    code_pme = Column(String(20), primary_key=True)
    axe = Column(String(20))
    source = Column(String(10))
    lat_deb = Column(Float)
    lon_deb = Column(Float)
    lat_fin = Column(Float)
    lon_fin = Column(Float)
    longueur = Column(Integer)
    nb_voies = Column(Integer)
    sens_cardinal = Column(String(20))
    geom_osm = Column(JSON)

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

class RailwayRouteRef(Base):
    __tablename__ = "railway_routes_ref"

    route_id = Column(String, primary_key=True)
    route_name = Column(String)
    shape_coords = Column(JSON)
    updated_at = Column(TIMESTAMP(timezone=True))

# Dépendance pour obtenir la session DB
def get_db():
    """Générateur de dépendance FastAPI (Depends).

    Ouvre une session SQLAlchemy, la yielde au handler, puis la ferme dans
    le bloc finally (même en cas d'exception).

    Yields:
        Session: Session SQLAlchemy active.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    """Endpoint racine de l'API.

    Retourne les informations de base (nom, version) et la liste des
    endpoints disponibles.

    Returns:
        dict: Dictionnaire contenant 'message', 'version' et 'endpoints'.
    """
    return {
        "message": "Noise Map API",
        "version": "1.0.0",
        "endpoints": {
            "current_noise": "/api/noise/current",
            "aircraft_positions": "/api/aircraft/current",
            "noise_history": "/api/noise/history",
            "stats": "/api/stats",
            "railway_positions": "/api/railway/current"
        }
    }

@app.get("/api/noise/current")
def get_current_noise(
    min_noise: Optional[float] = 40.0,
    limit: Optional[int] = 1000,
    db: Session = Depends(get_db)
):
    """Retourne les zones de bruit enregistrées dans les 2 dernières minutes.

    Filtrées par niveau minimum. Résultat mis en cache TTL=5s par couple
    (min_noise, limit) pour réduire la charge DB.

    Args:
        min_noise (float): Seuil minimum en dB(A), défaut 40.0.
        limit (int): Nombre maximum de zones retournées, défaut 1000.
        db (Session): Session SQLAlchemy injectée par Depends.

    Returns:
        dict: Dictionnaire avec 'count' (int), 'data' (list de zones),
            et 'timestamp' (ISO 8601).
    """
    cache_key = (min_noise, limit)
    with _noise_cache_lock:
        if cache_key in _noise_cache:
            return _noise_cache[cache_key]

    try:
        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

        results = db.query(NoiseLevel).filter(
            NoiseLevel.time > two_minutes_ago,
            NoiseLevel.noise_db >= min_noise
        ).order_by(desc(NoiseLevel.time)).limit(limit).all()

        data = [
            {
                "grid_id": r.grid_id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "noise_db": r.noise_db,
                "aircraft_count": r.aircraft_count,
                "time": r.time.isoformat()
            }
            for r in results
        ]

        result = {
            "count": len(data),
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        with _noise_cache_lock:
            _noise_cache[cache_key] = result
        return result

    except Exception as e:
        logger.error(f"Erreur API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/aircraft/current")
def get_current_aircraft(
    limit: Optional[int] = 500,
    db: Session = Depends(get_db)
):
    """Retourne la position la plus récente de chaque avion.

    Retourne les avions vus dans les 2 dernières minutes et non au sol
    (DISTINCT ON icao24). Résultat mis en cache TTL=5s.

    Args:
        limit (int): Nombre maximum d'avions retournés, défaut 500.
        db (Session): Session SQLAlchemy injectée par Depends.

    Returns:
        dict: Dictionnaire avec 'count' (int), 'data' (list d'avions avec
            icao24, callsign, latitude, longitude, altitude, velocity,
            heading, time, aircraft_type, aircraft_desc, aircraft_category),
            et 'timestamp' (ISO 8601).
    """
    cache_key = limit
    with _aircraft_cache_lock:
        if cache_key in _aircraft_cache:
            return _aircraft_cache[cache_key]

    try:
        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

        results = db.execute(text("""
            SELECT DISTINCT ON (icao24)
                icao24, callsign, latitude, longitude, altitude, velocity, heading, time,
                aircraft_type, aircraft_desc, aircraft_category
            FROM aircraft_positions
            WHERE time > :cutoff AND on_ground = false
            ORDER BY icao24, time DESC
        """), {"cutoff": two_minutes_ago}).fetchall()

        data = [
            {
                "icao24": r.icao24,
                "callsign": r.callsign,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude": r.altitude,
                "velocity": r.velocity,
                "heading": r.heading,
                "time": r.time.isoformat(),
                "aircraft_type": r.aircraft_type,
                "aircraft_desc": r.aircraft_desc,
                "aircraft_category": r.aircraft_category,
            }
            for r in results
        ]

        result = {
            "count": len(data),
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        with _aircraft_cache_lock:
            _aircraft_cache[cache_key] = result
        return result

    except Exception as e:
        logger.error(f"Erreur API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/noise/history")
def get_noise_history(
    grid_id: str,
    hours: Optional[int] = 1,
    db: Session = Depends(get_db)
):
    """Retourne la série temporelle du bruit pour une cellule de grille.

    Retourne les données sur la période demandée. Utile pour afficher
    l'évolution du bruit dans le temps pour une zone.

    Args:
        grid_id (str): Identifiant de grille au format "lat_lon"
            (ex: "48.80_2.30").
        hours (int): Nombre d'heures d'historique, défaut 1.
        db (Session): Session SQLAlchemy injectée par Depends.

    Returns:
        dict: Dictionnaire avec 'grid_id', 'count' (int), et 'data'
            (list de {time, noise_db, aircraft_count} triés chronologiquement).
    """
    try:
        time_ago = datetime.utcnow() - timedelta(hours=hours)
        
        results = db.query(NoiseLevel).filter(
            NoiseLevel.grid_id == grid_id,
            NoiseLevel.time > time_ago
        ).order_by(NoiseLevel.time.asc()).all()
        
        data = [
            {
                "time": r.time.isoformat(),
                "noise_db": r.noise_db,
                "aircraft_count": r.aircraft_count
            }
            for r in results
        ]
        
        return {
            "grid_id": grid_id,
            "count": len(data),
            "data": data
        }
    
    except Exception as e:
        logger.error(f"Erreur API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Retourne les statistiques globales de la carte.

    Nombre d'avions en vol (2 dernières minutes), bruit moyen et maximum
    (2 dernières minutes), et top 10 des zones les plus bruyantes
    (10 dernières minutes).

    Args:
        db (Session): Session SQLAlchemy injectée par Depends.

    Returns:
        dict: Dictionnaire avec 'aircraft_count', 'avg_noise_db',
            'max_noise_db', 'noisiest_zones' (list), et 'timestamp' (ISO 8601).
    """
    try:
        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        
        # Nombre total d'avions dans les 2 dernières minutes
        aircraft_count = db.query(func.count(func.distinct(AircraftPosition.icao24))).filter(
            AircraftPosition.time > two_minutes_ago,
            AircraftPosition.on_ground == False
        ).scalar()
        
        # Niveau de bruit moyen et max (aérien)
        noise_stats = db.query(
            func.avg(NoiseLevel.noise_db).label("avg_noise"),
            func.max(NoiseLevel.noise_db).label("max_noise")
        ).filter(
            NoiseLevel.time > two_minutes_ago
        ).first()

        # Bruit moyen et max ferroviaire + nombre de trains actifs
        railway_noise_stats = db.query(
            func.avg(RailwayNoiseLevel.noise_db).label("avg_noise"),
            func.max(RailwayNoiseLevel.noise_db).label("max_noise")
        ).filter(
            RailwayNoiseLevel.time > two_minutes_ago
        ).first()

        railway_train_count = db.query(func.count(func.distinct(RailwayPosition.trip_id))).filter(
            RailwayPosition.time > two_minutes_ago
        ).scalar()
        
        # Zones les plus bruyantes
        noisiest_zones = db.query(
            NoiseLevel.grid_id,
            NoiseLevel.latitude,
            NoiseLevel.longitude,
            func.avg(NoiseLevel.noise_db).label("avg_noise")
        ).filter(
            NoiseLevel.time > ten_minutes_ago
        ).group_by(
            NoiseLevel.grid_id,
            NoiseLevel.latitude,
            NoiseLevel.longitude
        ).order_by(
            desc("avg_noise")
        ).limit(10).all()
        
        noisiest_data = [
            {
                "grid_id": z.grid_id,
                "latitude": z.latitude,
                "longitude": z.longitude,
                "avg_noise": float(z.avg_noise)
            }
            for z in noisiest_zones
        ]
        
        return {
            "aircraft_count": aircraft_count or 0,
            "avg_noise_db": float(noise_stats.avg_noise) if noise_stats.avg_noise else 0.0,
            "max_noise_db": float(noise_stats.max_noise) if noise_stats.max_noise else 0.0,
            "railway_train_count": railway_train_count or 0,
            "railway_avg_noise_db": float(railway_noise_stats.avg_noise) if railway_noise_stats and railway_noise_stats.avg_noise else 0.0,
            "railway_max_noise_db": float(railway_noise_stats.max_noise) if railway_noise_stats and railway_noise_stats.max_noise else 0.0,
            "noisiest_zones": noisiest_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _simplify_geom(geom: list, max_pts: int = 20) -> list:
    if not geom or len(geom) <= max_pts:
        return geom
    step = max(1, len(geom) // max_pts)
    simplified = geom[::step]
    if simplified[-1] != geom[-1]:
        simplified.append(geom[-1])
    return simplified


@app.get("/api/road/current")
def get_current_road(db: Session = Depends(get_db)):
    """Retourne les segments routiers avec leur dernier niveau de bruit (< 10 min).

    Joint road_noise_levels (DISTINCT ON code_pme, ordre time DESC) avec
    road_segments_ref. Résultat mis en cache TTL=15s.

    Returns:
        dict: count, data (liste de segments avec noise_db, geom_osm, etc.), timestamp.
    """
    cache_key = "road_current"
    with _road_cache_lock:
        if cache_key in _road_cache:
            return _road_cache[cache_key]

    try:
        cutoff = datetime.utcnow() - timedelta(hours=3)

        rows = db.execute(text("""
            SELECT DISTINCT ON (n.code_pme)
                n.code_pme,
                n.noise_db,
                n.traffic_flow,
                n.average_speed,
                s.axe,
                s.lat_deb, s.lon_deb,
                s.lat_fin, s.lon_fin,
                s.geom_osm,
                s.nb_voies,
                n.time
            FROM road_noise_levels n
            JOIN road_segments_ref s ON s.code_pme = n.code_pme
            WHERE n.time > :cutoff
              AND n.noise_db >= 67
              AND s.fetched_at > NOW() - INTERVAL '25 hours'
              AND (
                s.highway_type IN ('motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link')
                OR (s.highway_type IS NULL AND (s.axe LIKE 'A%' OR s.axe LIKE 'N%'))
              )
            ORDER BY n.code_pme, n.time DESC
        """), {"cutoff": cutoff}).fetchall()

        data = [
            {
                "code_pme": r.code_pme,
                "axe": r.axe,
                "lat_deb": r.lat_deb,
                "lon_deb": r.lon_deb,
                "lat_fin": r.lat_fin,
                "lon_fin": r.lon_fin,
                "geom_osm": _simplify_geom(r.geom_osm),
                "noise_db": r.noise_db,
                "traffic_flow": r.traffic_flow,
                "average_speed": r.average_speed,
                "nb_voies": r.nb_voies,
            }
            for r in rows
        ]

        result = {
            "count": len(data),
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with _road_cache_lock:
            _road_cache[cache_key] = result
        return result

    except Exception as e:
        logger.error(f"Erreur API road: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/railway/current")
def get_current_railway(db: Session = Depends(get_db)):
    """Retourne les positions actuelles des trains avec leurs routes.

    Retourne le dernier enregistrement de chaque train dans les 5 dernières minutes.
    Joint railway_routes_ref pour inclure le tracé de la route (shape_coords).

    Returns:
        dict: count, data (liste de trains avec positions et tracés), timestamp.
    """
    cache_key = "railway_current"
    with _railway_cache_lock:
        if cache_key in _railway_cache:
            return _railway_cache[cache_key]

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=5)

        rows = db.execute(text("""
            SELECT DISTINCT ON (rp.trip_id)
                rp.trip_id, rp.train_number, rp.route_id,
                rp.latitude, rp.longitude, rp.speed_kmh, rp.heading,
                rp.delay_seconds, rp.next_stop_name, rp.prev_stop_name, rp.time,
                rt.trip_headsign,
                rr.route_short_name,
                rr.route_long_name
            FROM railway_positions rp
            LEFT JOIN rail_trips rt ON rt.trip_id = rp.trip_id
            LEFT JOIN rail_routes rr ON rr.route_id = rt.route_id
            WHERE rp.time > :cutoff
            ORDER BY rp.trip_id, rp.time DESC
        """), {"cutoff": cutoff}).fetchall()

        data = [
            {
                "trip_id": r.trip_id,
                "train_number": r.train_number,
                "route_id": r.route_id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "speed_kmh": r.speed_kmh,
                "heading": r.heading,
                "delay_seconds": r.delay_seconds,
                "next_stop_name": r.next_stop_name,
                "prev_stop_name": r.prev_stop_name,
                "time": r.time.isoformat(),
                "trip_headsign": r.trip_headsign,
                "route_short_name": r.route_short_name,
                "route_long_name": r.route_long_name,
            }
            for r in rows
        ]

        result = {
            "count": len(data),
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with _railway_cache_lock:
            _railway_cache[cache_key] = result
        return result

    except Exception as e:
        logger.error(f"Erreur API railway: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/railway/lines")
def get_railway_lines(db: Session = Depends(get_db)):
    """Retourne les géométries GTFS SNCF des lignes ferroviaires sous forme GeoJSON.

    Source : rail_shapes + rail_trips + rail_routes (GTFS SNCF).
    Une shape représentative par route, décimée (1 point sur 5). Mise en cache 1h.

    Returns:
        dict: GeoJSON FeatureCollection avec les LineStrings des voies ferrées.
    """
    cache_key = "railway_lines"
    with _railway_lines_cache_lock:
        if cache_key in _railway_lines_cache:
            return _railway_lines_cache[cache_key]

    try:
        rows = db.execute(text("""
            WITH route_shape AS (
                SELECT DISTINCT ON (route_id) route_id, shape_id
                FROM rail_trips
                WHERE shape_id IS NOT NULL
                ORDER BY route_id
            )
            SELECT
                rs.shape_id,
                rs.shape_pt_lat,
                rs.shape_pt_lon,
                rr.route_short_name,
                rr.route_type
            FROM route_shape rts
            JOIN rail_shapes rs ON rs.shape_id = rts.shape_id
            JOIN rail_routes rr ON rr.route_id = rts.route_id
            WHERE rr.route_type IN (0, 1, 2)
              AND MOD(rs.shape_pt_sequence - 1, 5) = 0
            ORDER BY rts.route_id, rs.shape_pt_sequence
        """)).fetchall()

        shapes: dict[str, list] = {}
        shape_props: dict[str, dict] = {}
        for r in rows:
            if r.shape_id not in shapes:
                shapes[r.shape_id] = []
                shape_props[r.shape_id] = {
                    "route_short_name": r.route_short_name,
                    "route_type": r.route_type,
                }
            shapes[r.shape_id].append([r.shape_pt_lon, r.shape_pt_lat])

        features = []
        for shape_id, coords in shapes.items():
            if len(coords) < 2:
                continue
            features.append({
                "type": "Feature",
                "properties": shape_props[shape_id],
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                }
            })

        result = {"type": "FeatureCollection", "features": features}
        with _railway_lines_cache_lock:
            _railway_lines_cache[cache_key] = result
        logger.info(f"railway/lines: {len(features)} lignes GTFS SNCF mises en cache")
        return result

    except Exception as e:
        logger.error(f"Erreur API railway/lines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/railway/shapes")
def get_railway_shapes(db: Session = Depends(get_db), detail: str = "high"):
    """Retourne les shapes GTFS des trips actifs (gzip, cache 2 min).

    Joint railway_positions (actifs 5 min) → rail_trips → rail_shapes.
    Retourne { trip_id: [[lat, lon, dist], ...] } pour tous les trips actifs.
    Décimation SQL : detail=low (1 point/5) ou detail=high (1 point/2).
    """
    keep_every = 5 if detail == "low" else 2
    cache_key = f"railway_shapes:{detail}"

    with _railway_shapes_cache_lock:
        if cache_key in _railway_shapes_cache:
            return Response(
                content=_railway_shapes_cache[cache_key],
                media_type="application/json",
                headers={"Content-Encoding": "gzip"},
            )

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=5)

        # Décimation côté SQL : on ne ramène que les points nécessaires
        # (1er point, dernier point, et 1 point tous les N)
        rows = db.execute(text("""
            SELECT f.trip_id, f.shape_pt_lat, f.shape_pt_lon,
                   f.shape_dist_traveled, f.shape_pt_sequence
            FROM (
                SELECT rp.trip_id, rs.shape_pt_lat, rs.shape_pt_lon,
                       rs.shape_dist_traveled, rs.shape_pt_sequence,
                       MAX(rs.shape_pt_sequence) OVER (PARTITION BY rp.trip_id) AS max_seq,
                       MIN(rs.shape_pt_sequence) OVER (PARTITION BY rp.trip_id) AS min_seq
                FROM (
                    SELECT DISTINCT ON (trip_id) trip_id
                    FROM railway_positions
                    WHERE time > :cutoff
                    ORDER BY trip_id, time DESC
                ) rp
                JOIN rail_trips rt ON rt.trip_id = rp.trip_id
                JOIN rail_shapes rs ON rs.shape_id = rt.shape_id
            ) f
            WHERE f.shape_pt_sequence = f.min_seq
               OR f.shape_pt_sequence = f.max_seq
               OR MOD(f.shape_pt_sequence, :keep_every) = 0
            ORDER BY f.trip_id, f.shape_pt_sequence
        """), {"cutoff": cutoff, "keep_every": keep_every}).fetchall()

        shapes: dict[str, list[list[float]]] = {}
        for r in rows:
            if r.trip_id not in shapes:
                shapes[r.trip_id] = []
            shapes[r.trip_id].append([r.shape_pt_lat, r.shape_pt_lon, r.shape_dist_traveled or 0.0])

        import gzip
        result_bytes = gzip.compress(orjson.dumps(shapes), compresslevel=1)
        with _railway_shapes_cache_lock:
            _railway_shapes_cache[cache_key] = result_bytes
        total_pts = sum(len(v) for v in shapes.values())
        logger.info(f"railway/shapes ({detail}): {len(shapes)} trips, {total_pts} pts, {len(result_bytes) / 1024 / 1024:.1f} MB gzip")
        return Response(
            content=result_bytes,
            media_type="application/json",
            headers={"Content-Encoding": "gzip"},
        )

    except Exception as e:
        logger.error(f"Erreur API railway/shapes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


## Warmup désactivé — avec 4 workers, chaque warmup charge ~200K pts en mémoire,
## ce qui cause des OOM en boucle. Le premier appel frontend peuplera le cache.
# @app.on_event("startup")
# def warmup_shapes_cache():
#     ...


@app.on_event("shutdown")
def shutdown_event():
    """Handler d'événement FastAPI déclenché à l'arrêt du serveur.

    Libère toutes les connexions du pool SQLAlchemy (engine.dispose())
    pour éviter les fuites de connexions.

    Returns:
        None
    """
    engine.dispose()
    logger.info("Connexions DB fermées")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)