#!/usr/bin/env python3
"""
assign_shapes.py — Associe chaque groupe de trips SNCF à une shape pfaedle
par correspondance géométrique multi-arrêts.

À lancer une seule fois après l'import des shapes (make import-shapes).
Le résultat est persisté dans rail_route_shapes, qui est inclus dans db-backup
et survivra aux mises à jour GTFS quotidiennes.

Lors de chaque import GTFS (import-gtfs.py --temporal), le mapping est appliqué
automatiquement sur les nouveaux trip_ids via un UPDATE SQL.

Usage :
    python3 assign_shapes.py
    make assign-shapes
"""

import os
import time
import logging
from math import radians, cos

import numpy as np
import psycopg
from dotenv import load_dotenv
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(override=True)

DB_CONFIG = {
    "host":     os.getenv("TIMESCALE_HOST"),
    "port":     os.getenv("TIMESCALE_PORT"),
    "dbname":   os.getenv("TIMESCALE_NAME"),
    "user":     os.getenv("TIMESCALE_USER"),
    "password": os.getenv("TIMESCALE_PASSWORD"),
}

# Points par shape conservés pour le scoring (downsampling en SQL)
SHAPE_SAMPLE_SIZE = 80
# Max arrêts échantillonnés par trip pour le scoring
MAX_STOPS_SAMPLE = 12
# Seuil de rejet : score > MAX_SCORE_KM → aucune shape assignée
MAX_SCORE_KM = 5.0
# Marge de filtrage bbox en degrés (~33 km à la latitude de la France)
BBOX_MARGIN_DEG = 0.3


def load_shapes(conn):
    """
    Charge les shapes sous-échantillonnées depuis rail_shapes.
    Retourne dict shape_id → np.array (N, 2) de (lat, lon) en float32.
    """
    logger.info("Chargement des shapes depuis rail_shapes (sous-échantillonnage SQL)...")
    rows = conn.execute("""
        SELECT shape_id, shape_pt_lat, shape_pt_lon
        FROM (
            SELECT shape_id, shape_pt_lat, shape_pt_lon,
                   ROW_NUMBER() OVER (PARTITION BY shape_id ORDER BY shape_pt_sequence) AS rn,
                   COUNT(*)     OVER (PARTITION BY shape_id)                            AS total
            FROM rail_shapes
        ) t
        WHERE rn = 1 OR rn = total
           OR MOD(rn, GREATEST(1, total / %s)) = 0
        ORDER BY shape_id, rn
    """, (SHAPE_SAMPLE_SIZE,)).fetchall()

    shapes: dict = {}
    for shape_id, lat, lon in rows:
        if shape_id not in shapes:
            shapes[shape_id] = []
        shapes[shape_id].append((lat, lon))

    shapes_np = {sid: np.array(pts, dtype=np.float32) for sid, pts in shapes.items()}
    logger.info(f"  {len(shapes_np)} shapes chargées ({len(rows):,} points après downsampling)")
    return shapes_np


def load_stops(conn):
    """Charge rail_stops → dict stop_id → (lat, lon)."""
    rows = conn.execute("SELECT stop_id, stop_lat, stop_lon FROM rail_stops").fetchall()
    stops = {stop_id: (float(lat), float(lon)) for stop_id, lat, lon in rows}
    logger.info(f"  {len(stops)} arrêts chargés")
    return stops


def load_trip_groups(conn, stops):
    """
    Groupe les trips par (route_id, first_stop_id, last_stop_id).

    Clé choisie plutôt que (route_id, direction_id) car :
    - direction_id peut être NULL dans les exports SNCF
    - les variantes partielles d'une même route (ex. Lyon→Paris vs Mâcon→Paris)
      produisent des entrées distinctes et reçoivent la shape la plus adaptée

    Retourne dict key → {"trip_id": str, "stops": np.array (N, 2)}
    """
    logger.info("Chargement et groupement des trips...")

    rows = conn.execute("""
        WITH first_stops AS (
            SELECT DISTINCT ON (trip_id) trip_id, stop_id
            FROM rail_stop_times
            ORDER BY trip_id, stop_sequence ASC
        ),
        last_stops AS (
            SELECT DISTINCT ON (trip_id) trip_id, stop_id
            FROM rail_stop_times
            ORDER BY trip_id, stop_sequence DESC
        )
        SELECT t.trip_id, t.route_id,
               f.stop_id AS first_stop,
               l.stop_id AS last_stop
        FROM rail_trips t
        JOIN first_stops f ON f.trip_id = t.trip_id
        JOIN last_stops  l ON l.trip_id = t.trip_id
    """).fetchall()

    logger.info(f"  {len(rows)} trips lus")

    # Un trip représentatif par groupe
    groups: dict = {}
    for trip_id, route_id, first_stop, last_stop in rows:
        key = (route_id, first_stop, last_stop)
        if key not in groups:
            groups[key] = trip_id

    logger.info(f"  {len(groups)} groupes distincts (route_id, first_stop, last_stop)")

    # Charger les stop_times des trips représentatifs
    rep_trip_ids = list(groups.values())
    rows_st = conn.execute(
        "SELECT trip_id, stop_id, stop_sequence FROM rail_stop_times "
        "WHERE trip_id = ANY(%s) ORDER BY trip_id, stop_sequence",
        (rep_trip_ids,),
    ).fetchall()

    trip_stops_map: dict = {}
    for trip_id, stop_id, _ in rows_st:
        if trip_id not in trip_stops_map:
            trip_stops_map[trip_id] = []
        trip_stops_map[trip_id].append(stop_id)

    group_data: dict = {}
    n_missing = 0
    for key, trip_id in groups.items():
        stop_ids = trip_stops_map.get(trip_id, [])
        coords = [stops[sid] for sid in stop_ids if sid in stops]
        if len(coords) >= 2:
            group_data[key] = {
                "trip_id": trip_id,
                "stops": np.array(coords, dtype=np.float32),
            }
        else:
            n_missing += 1

    if n_missing:
        logger.warning(f"  {n_missing} groupes ignorés (arrêts manquants en base)")
    logger.info(f"  {len(group_data)} groupes prêts pour le matching")
    return group_data


def precompute_shape_meta(shapes_np):
    """Précalcule les bboxes pour le filtrage spatial rapide."""
    return {
        sid: {
            "pts":     pts,
            "min_lat": float(pts[:, 0].min()),
            "max_lat": float(pts[:, 0].max()),
            "min_lon": float(pts[:, 1].min()),
            "max_lon": float(pts[:, 1].max()),
        }
        for sid, pts in shapes_np.items()
    }


def score_shape(stops_sample: np.ndarray, shape_pts: np.ndarray):
    """
    Calcule le score de correspondance entre les arrêts d'un trip et une shape.

    stops_sample : (K, 2) float32 — arrêts échantillonnés (lat, lon)
    shape_pts    : (M, 2) float32 — points de la shape (lat, lon)

    Retourne (score_km, direction_ok) :
    - score_km : distance moyenne en km de chaque arrêt au point shape le plus proche
    - direction_ok : True si le 1er arrêt pointe vers le début de la shape (pas inversée)
    """
    mean_lat_rad = radians(float(stops_sample[:, 0].mean()))
    scale = np.array([111.32, 111.32 * cos(mean_lat_rad)], dtype=np.float32)

    # (K, M) distances en km — approximation plate-carrée suffisante à l'échelle France
    diff = (stops_sample[:, np.newaxis, :] - shape_pts[np.newaxis, :, :]) * scale
    dists = np.sqrt((diff ** 2).sum(axis=2))

    min_dists = dists.min(axis=1)      # (K,) distance min de chaque arrêt à la shape
    score = float(min_dists.mean())

    # Vérification de direction : l'index du point le plus proche pour le 1er arrêt
    # doit être inférieur à celui du dernier arrêt (shape parcourue dans le bon sens)
    idx_first = int(dists[0].argmin())
    idx_last  = int(dists[-1].argmin())
    direction_ok = idx_first < idx_last

    return score, direction_ok


def match_groups(group_data, shapes_np):
    """
    Pour chaque groupe de trips, cherche la shape la mieux adaptée.

    Étapes par groupe :
      1. Filtrage bbox : seules les shapes couvrant géographiquement le 1er arrêt
         sont candidates (réduit généralement à <300 shapes sur 7258)
      2. Scoring multi-arrêts : distance moyenne stop→shape sur MAX_STOPS_SAMPLE arrêts
      3. Pénalité direction si la shape est parcourue à rebours
      4. Rejet si score > MAX_SCORE_KM (aucune shape adaptée trouvée)

    Retourne dict key → {"shape_id", "score", "trip_id"}.
    """
    logger.info("Matching des groupes aux shapes...")
    shape_meta = precompute_shape_meta(shapes_np)
    shape_list = list(shape_meta.items())

    results: dict = {}
    n_matched = 0
    n_skipped = 0

    for key, data in tqdm(group_data.items(), desc="Matching", unit="groupes"):
        stops_arr = data["stops"]
        trip_id   = data["trip_id"]

        # Sous-échantillonnage uniforme des arrêts
        n = len(stops_arr)
        if n > MAX_STOPS_SAMPLE:
            indices = np.linspace(0, n - 1, MAX_STOPS_SAMPLE, dtype=int)
            stops_sample = stops_arr[indices]
        else:
            stops_sample = stops_arr

        first_lat = float(stops_sample[0, 0])
        first_lon = float(stops_sample[0, 1])
        m = BBOX_MARGIN_DEG

        # Filtrage spatial : shape dont la bbox contient le 1er arrêt (± marge)
        candidates = [
            (sid, meta) for sid, meta in shape_list
            if (meta["min_lat"] - m) <= first_lat <= (meta["max_lat"] + m)
            and (meta["min_lon"] - m) <= first_lon <= (meta["max_lon"] + m)
        ]

        if not candidates:
            n_skipped += 1
            continue

        best_sid   = None
        best_score = float("inf")

        for sid, meta in candidates:
            score, direction_ok = score_shape(stops_sample, meta["pts"])
            # Pénalité légère pour mauvaise direction : on garde le candidat mais
            # on le défavorise face à un autre correctement orienté
            if not direction_ok:
                score += 1.5
            if score < best_score:
                best_score = score
                best_sid   = sid

        if best_sid and best_score < MAX_SCORE_KM:
            results[key] = {"shape_id": best_sid, "score": best_score, "trip_id": trip_id}
            n_matched += 1
        else:
            n_skipped += 1
            route_id, first_stop, last_stop = key
            logger.debug(
                f"  Rejeté ({route_id[:50]}, {first_stop}→{last_stop}) "
                f"score={best_score:.2f} km (seuil {MAX_SCORE_KM} km)"
            )

    logger.info(f"Matching terminé : {n_matched} groupes matchés, {n_skipped} sans shape")
    return results


def write_results(conn, results):
    """
    Écrit le mapping dans rail_route_shapes puis propage shape_id dans rail_trips.

    Les deux opérations sont dans une seule transaction pour garantir la cohérence.
    """
    rows = [
        (route_id, first_stop, last_stop, v["shape_id"], round(v["score"], 4))
        for (route_id, first_stop, last_stop), v in results.items()
    ]

    logger.info(f"Écriture de {len(rows)} entrées dans rail_route_shapes...")
    with conn.transaction():
        conn.execute("TRUNCATE rail_route_shapes")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rail_route_shapes "
                "  (route_id, first_stop, last_stop, shape_id, match_score) "
                "VALUES (%s, %s, %s, %s, %s)",
                rows,
            )

        logger.info("Propagation vers rail_trips.shape_id...")
        result = conn.execute("""
            UPDATE rail_trips t
            SET shape_id = subq.shape_id
            FROM (
                SELECT t2.trip_id, rrs.shape_id
                FROM rail_trips t2
                JOIN (
                    SELECT DISTINCT ON (trip_id) trip_id, stop_id AS first_stop
                    FROM rail_stop_times ORDER BY trip_id, stop_sequence ASC
                ) fst ON fst.trip_id = t2.trip_id
                JOIN (
                    SELECT DISTINCT ON (trip_id) trip_id, stop_id AS last_stop
                    FROM rail_stop_times ORDER BY trip_id, stop_sequence DESC
                ) lst ON lst.trip_id = t2.trip_id
                JOIN rail_route_shapes rrs
                    ON  rrs.route_id   = t2.route_id
                    AND rrs.first_stop = fst.first_stop
                    AND rrs.last_stop  = lst.last_stop
            ) subq
            WHERE t.trip_id = subq.trip_id
        """)
        logger.info(f"  {result.rowcount} trips mis à jour avec leur shape_id")


def main():
    t0 = time.time()
    logger.info("=== assign_shapes.py — matching géométrique trips → shapes ===")

    with psycopg.connect(**DB_CONFIG) as conn:
        shapes_np  = load_shapes(conn)
        stops      = load_stops(conn)
        group_data = load_trip_groups(conn, stops)
        results    = match_groups(group_data, shapes_np)
        write_results(conn, results)

    logger.info(f"Terminé en {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
