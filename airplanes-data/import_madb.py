#!/usr/bin/env python3
"""Import MAdB noise reference data into TimescaleDB."""

import csv
import os
import psycopg

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "noise_map"),
    "user": os.environ.get("DB_USER", "noiseuser"),
    "password": os.environ.get("DB_PASSWORD", "noisepass"),
}

HEADER_LINES = 6

FILES = [
    {
        "source": "jets",
        "path": "/data/MAdB_JETS_20260225_.csv",
        "noise_unit": "EPNdB",
        "cols": {
            "record": 1,
            "manufacturer": 6,
            "model": 7,
            "mtom": 12,
            "lateral": 25,
            "flyover": 28,
            "approach": 31,
            "overflight": None,
            "takeoff": None,
        },
    },
    {
        "source": "heavy_prop",
        "path": "/data/MAdB_Heavy_Prop_20260225_.csv",
        "noise_unit": "EPNdB",
        "cols": {
            "record": 1,
            "manufacturer": 6,
            "model": 7,
            "mtom": 11,
            "lateral": 29,
            "flyover": 32,
            "approach": 35,
            "overflight": None,
            "takeoff": None,
        },
    },
    {
        "source": "light_prop",
        "path": "/data/MAdB_Light_Prop_20260225_.csv",
        "noise_unit": "dBA",
        "cols": {
            "record": 1,
            "manufacturer": 6,
            "model": 7,
            "mtom": 11,
            "lateral": None,
            "flyover": None,
            "approach": None,
            "overflight": 32,
            "takeoff": 35,
        },
    },
]

INSERT_SQL = """
INSERT INTO madb_noise_ref (
    source, record_number, manufacturer, aircraft_model, mtom_kg,
    lateral_epndb, flyover_epndb, approach_epndb,
    overflight_dba, takeoff_dba, noise_unit
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (source, record_number) DO NOTHING
"""


def parse_float(value):
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace(",", ".").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value):
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace(" ", "").replace("\xa0", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def import_file(cursor, file_cfg):
    source = file_cfg["source"]
    path = file_cfg["path"]
    cols = file_cfg["cols"]
    noise_unit = file_cfg["noise_unit"]

    inserted = 0
    skipped = 0

    with open(path, encoding="latin-1") as f:
        for _ in range(HEADER_LINES):
            next(f)
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if not row or len(row) < 2:
                continue
            record = row[cols["record"]].strip() if cols["record"] < len(row) else None
            if not record:
                continue

            def get(col_key):
                idx = cols.get(col_key)
                if idx is None or idx >= len(row):
                    return None
                return row[idx]

            manufacturer = (get("manufacturer") or "").strip() or None
            model = (get("model") or "").strip() or None
            mtom_kg = parse_int(get("mtom"))
            lateral = parse_float(get("lateral"))
            flyover = parse_float(get("flyover"))
            approach = parse_float(get("approach"))
            overflight = parse_float(get("overflight"))
            takeoff = parse_float(get("takeoff"))

            cursor.execute(
                INSERT_SQL,
                (
                    source, record, manufacturer, model, mtom_kg,
                    lateral, flyover, approach, overflight, takeoff, noise_unit,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

    return inserted, skipped


def main():
    conn = psycopg.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for file_cfg in FILES:
                source = file_cfg["source"]
                print(f"Importing {source}...", flush=True)
                inserted, skipped = import_file(cur, file_cfg)
                print(f"  {source}: {inserted} insérés, {skipped} ignorés (doublons)", flush=True)
        conn.commit()
        print("Import terminé.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
