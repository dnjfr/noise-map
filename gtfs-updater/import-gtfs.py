#!/usr/bin/env python3
"""Import GTFS SNCF dans TimescaleDB.

Usage:
    python3 import-gtfs.py                 # stops, routes, trips, stop_times (pas les shapes)
    python3 import-gtfs.py --shapes        # rail_shapes uniquement (one-shot, depuis shapes.txt pfaedle)
    python3 import-gtfs.py --static        # stops, routes uniquement
    python3 import-gtfs.py --temporal      # trips, stop_times (mise à jour quotidienne ~18h)
    python3 import-gtfs.py --force         # réimporte les tables statiques même si déjà remplies
    python3 import-gtfs.py --gtfs-dir /chemin/vers/gtfs/

Les shapes (rail_shapes) sont gérées séparément via --shapes car générées par pfaedle
depuis le PBF OSM — indépendantes du GTFS téléchargeable quotidiennement.

Les tables statiques (rail_stops, rail_routes) ne sont importées qu’une seule fois sauf --force.
Les tables temporelles (rail_trips, rail_stop_times) sont toujours tronquées puis rechargées.

Source GTFS : https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip
Info : https://transport.data.gouv.fr/datasets/horaires-sncf
"""
import argparse
import csv
import io
import os
import sys
import psycopg
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(override=True)

DEFAULT_GTFS_DIR = os.path.join(os.path.dirname(__file__), "gtfs-statique")

DB_CONFIG = {
    "host":     os.getenv("TIMESCALE_HOST"),
    "port":     os.getenv("TIMESCALE_PORT"),
    "dbname":   os.getenv("TIMESCALE_NAME"),
    "user":     os.getenv("TIMESCALE_USER"),
    "password": os.getenv("TIMESCALE_PASSWORD"),
}


def table_is_empty(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT NOT EXISTS (SELECT 1 FROM {table} LIMIT 1)")
        return cur.fetchone()[0]


def copy_csv(conn, table: str, columns: list[str], rows: list[list]) -> int:
    """Bulk-load rows into table via COPY. Returns number of rows loaded."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    buf.seek(0)

    cols = ", ".join(columns)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT CSV)") as copy:
            copy.write(buf.read())
    return len(rows)


def import_stops(conn, gtfs_dir: str) -> int:
    path = os.path.join(gtfs_dir, "stops.txt")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in tqdm(csv.DictReader(f), desc="    stops", unit=" arrêts"):
            rows.append([
                row["stop_id"],
                row["stop_name"],
                float(row["stop_lat"]),
                float(row["stop_lon"]),
                row.get("parent_station") or None,
                int(row["location_type"]) if row.get("location_type") else 0,
            ])
    return copy_csv(conn, "rail_stops",
                    ["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station", "location_type"],
                    rows)


def import_routes(conn, gtfs_dir: str) -> int:
    path = os.path.join(gtfs_dir, "routes.txt")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in tqdm(csv.DictReader(f), desc="    routes", unit=" routes"):
            rows.append([
                row["route_id"],
                row.get("route_short_name") or None,
                row.get("route_long_name") or None,
                int(row["route_type"]) if row.get("route_type") else None,
                row.get("route_color") or None,
                row.get("agency_id") or None,
            ])
    return copy_csv(conn, "rail_routes",
                    ["route_id", "route_short_name", "route_long_name", "route_type", "route_color", "agency_id"],
                    rows)


def import_shapes(conn, gtfs_dir: str) -> int:
    path = os.path.join(gtfs_dir, "shapes.txt")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in tqdm(csv.DictReader(f), desc="    shapes", unit=" pts"):
            rows.append([
                row["shape_id"],
                float(row["shape_pt_lat"]),
                float(row["shape_pt_lon"]),
                int(row["shape_pt_sequence"]),
                float(row["shape_dist_traveled"]) if row.get("shape_dist_traveled") else None,
            ])
    return copy_csv(conn, "rail_shapes",
                    ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"],
                    rows)


def import_trips(conn, gtfs_dir: str) -> int:
    path = os.path.join(gtfs_dir, "trips.txt")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in tqdm(csv.DictReader(f), desc="    trips", unit=" trajets"):
            rows.append([
                row["trip_id"],
                row["route_id"],
                row["service_id"],
                row.get("shape_id") or None,
                row.get("trip_short_name") or None,
                row.get("trip_headsign") or None,
                int(row["direction_id"]) if row.get("direction_id") else None,
            ])
    return copy_csv(conn, "rail_trips",
                    ["trip_id", "route_id", "service_id", "shape_id", "trip_short_name", "trip_headsign", "direction_id"],
                    rows)


def import_stop_times(conn, gtfs_dir: str) -> int:
    path = os.path.join(gtfs_dir, "stop_times.txt")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in tqdm(csv.DictReader(f), desc="    stop_times", unit=" horaires"):
            rows.append([
                row["trip_id"],
                row["stop_id"],
                int(row["stop_sequence"]),
                row.get("arrival_time") or None,
                row.get("departure_time") or None,
                float(row["shape_dist_traveled"]) if row.get("shape_dist_traveled") else None,
            ])
    return copy_csv(conn, "rail_stop_times",
                    ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time", "shape_dist_traveled"],
                    rows)


def main():
    parser = argparse.ArgumentParser(description="Import GTFS SNCF dans TimescaleDB")
    parser.add_argument("--gtfs-dir", default=DEFAULT_GTFS_DIR,
                        help="Répertoire contenant les fichiers GTFS extraits")
    parser.add_argument("--shapes",   action="store_true", help="Importer uniquement rail_shapes (one-shot pfaedle)")
    parser.add_argument("--static",   action="store_true", help="Importer uniquement les tables statiques (stops, routes)")
    parser.add_argument("--temporal", action="store_true", help="Importer uniquement les tables temporelles (trips, stop_times)")
    parser.add_argument("--force",    action="store_true", help="Réimporter les tables statiques même si déjà remplies")
    args = parser.parse_args()

    no_flag = not args.shapes and not args.static and not args.temporal
    do_shapes   = args.shapes
    do_static   = args.static  or no_flag
    do_temporal = args.temporal or no_flag

    gtfs_dir = args.gtfs_dir
    if not os.path.isdir(gtfs_dir):
        print(f"Erreur : répertoire GTFS introuvable : {gtfs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Connexion à la base de données...")
    with psycopg.connect(**DB_CONFIG) as conn:

        if do_shapes:
            print("\n── Shapes (pfaedle) ──")
            table, fn = "rail_shapes", import_shapes
            if not args.force and not table_is_empty(conn, table):
                print(f"  {table} : déjà remplie, ignorée (--force pour réimporter)")
            else:
                print(f"  {table} :", flush=True)
                with conn.transaction():
                    conn.execute(f"TRUNCATE {table} CASCADE")
                    n = fn(conn, gtfs_dir)
                print(f"  ✓ {n:,} lignes importées")

        if do_static:
            print("\n── Tables statiques ──")
            for table, fn in [
                ("rail_stops",  import_stops),
                ("rail_routes", import_routes),
            ]:
                if not args.force and not table_is_empty(conn, table):
                    print(f"  {table} : déjà remplie, ignorée (--force pour réimporter)")
                    continue
                print(f"  {table} :", flush=True)
                with conn.transaction():
                    conn.execute(f"TRUNCATE {table} CASCADE")
                    n = fn(conn, gtfs_dir)
                print(f"  ✓ {n:,} lignes importées")

        if do_temporal:
            print("\n── Tables temporelles ──")
            for table, fn in [
                ("rail_trips",      import_trips),
                ("rail_stop_times", import_stop_times),
            ]:
                print(f"  {table} :", flush=True)
                with conn.transaction():
                    conn.execute(f"TRUNCATE {table}")
                    n = fn(conn, gtfs_dir)
                print(f"  ✓ {n:,} lignes importées")

            # Appliquer le mapping shape depuis rail_route_shapes
            print("\n── Application du mapping shapes ──", flush=True)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM rail_route_shapes")
                mapping_count = cur.fetchone()[0]

            if mapping_count == 0:
                print("  ⚠ rail_route_shapes vide — lancez 'make assign-shapes' après import-shapes")
            else:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("""
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
                        n_updated = cur.rowcount
                print(f"  ✓ {n_updated:,} trips mis à jour avec leur shape_id")

    print("\nImport terminé.")


if __name__ == "__main__":
    main()
