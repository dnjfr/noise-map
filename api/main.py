import os
import threading
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, TIMESTAMP, text, desc, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime, timedelta
from cachetools import TTLCache
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
    pool_size=10,
    max_overflow=20
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Cache in-process TTL=5s pour réduire la charge DB sur les endpoints chauds
_aircraft_cache: TTLCache = TTLCache(maxsize=20, ttl=5)
_aircraft_cache_lock = threading.Lock()
_noise_cache: TTLCache = TTLCache(maxsize=50, ttl=5)
_noise_cache_lock = threading.Lock()

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
    __tablename__ = "noise_levels"
    
    time = Column(TIMESTAMP(timezone=True), primary_key=True)
    latitude = Column(Float, primary_key=True, nullable=False)
    longitude = Column(Float, primary_key=True, nullable=False)
    noise_db = Column(Float, nullable=False)
    aircraft_count = Column(Integer)
    grid_id = Column(String(20))

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
            "stats": "/api/stats"
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
        
        # Niveau de bruit moyen et max
        noise_stats = db.query(
            func.avg(NoiseLevel.noise_db).label("avg_noise"),
            func.max(NoiseLevel.noise_db).label("max_noise")
        ).filter(
            NoiseLevel.time > two_minutes_ago
        ).first()
        
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
            "noisiest_zones": noisiest_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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