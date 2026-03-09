#!/usr/bin/env python3
"""Populate icao_to_madb_pattern table.

Cette table fait le pont entre les codes ICAO OpenSky et les modèles MAdB.
Le problème : les noms de modèles diffèrent entre les deux sources.

  OpenSky  "t": "A21N"
      → icao_type_mapping : A21N → AIRBUS, A-321neo
      → icao_to_madb_pattern : A21N → pattern ^A321-[0-9]+N
      → madb_noise_ref : A321-251N, A321-252N, A321-253N...

Usage : python3 airplanes-data/import_icao_patterns.py
        (ou : make import-patterns)

Pour ajouter un nouveau type d'avion :
  1. Identifier le code ICAO (champ "t" dans le JSON OpenSky)
  2. Trouver les modèles correspondants dans madb_noise_ref
  3. Écrire un pattern regex PostgreSQL POSIX qui les capture
  4. Ajouter une ligne dans PATTERNS ci-dessous
"""

import os
import sys
import psycopg

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "noise_map"),
    "user": os.environ.get("DB_USER", "noiseuser"),
    "password": os.environ.get("DB_PASSWORD", "noisepass"),
}

# (icao_code, madb_model_pattern, madb_manufacturer_pattern, notes)
# madb_model_pattern   : regex POSIX PostgreSQL sur madb_noise_ref.aircraft_model
# madb_manufacturer_pattern : ILIKE pattern sur madb_noise_ref.manufacturer (None = pas de filtre)
PATTERNS = [

    # ── AIRBUS A318 ────────────────────────────────────────────────────────────
    ("A318", r"^A318-[0-9]+$",       "%Airbus%", "A318 toutes variantes"),

    # ── AIRBUS A319 ────────────────────────────────────────────────────────────
    ("A319", r"^A319-[0-9]+$",       "%Airbus%", "A319 classic (CFM/IAE)"),
    ("A19N", r"^A319-[0-9]+N",       "%Airbus%", "A319neo (LEAP/PW1100G)"),

    # ── AIRBUS A320 ────────────────────────────────────────────────────────────
    ("A320", r"^A320-[0-9]+$",       "%Airbus%", "A320 classic (CFM/IAE)"),
    ("A20N", r"^A320-[0-9]+N",       "%Airbus%", "A320neo (LEAP/PW1100G)"),

    # ── AIRBUS A321 ────────────────────────────────────────────────────────────
    ("A321", r"^A321-[0-9]+$",       "%Airbus%", "A321 classic (CFM/IAE)"),
    ("A21N", r"^A321-[0-9]+N",       "%Airbus%", "A321neo / XLR (LEAP/PW1100G)"),

    # ── AIRBUS A300-600 ────────────────────────────────────────────────────────
    # madb : "A300 B4-601", "A300 B4-605R", "A300 F4-622R"...
    ("A306", r"^A300 [BCF]4-6",      "%Airbus%", "A300-600 series"),

    # ── AIRBUS A330 ────────────────────────────────────────────────────────────
    # Naming madb : A330-XYZ où X = motorisation, Y = série (2→-200, 3→-300, 9→-900)
    ("A332", r"^A330-2",             "%Airbus%", "A330-200 (GE CF6)"),
    ("A333", r"^A330-3",             "%Airbus%", "A330-300 (PW/RR)"),
    ("A339", r"^A330-9",             "%Airbus%", "A330-900neo"),

    # ── AIRBUS A350 ────────────────────────────────────────────────────────────
    # madb : "A350-941" (900), "A350-1041" (1000)
    ("A359", r"^A350-9[0-9]",        "%Airbus%", "A350-900 XWB"),
    ("A35K", r"^A350-10",            "%Airbus%", "A350-1000 XWB"),

    # ── AIRBUS A380 ────────────────────────────────────────────────────────────
    ("A388", r"^A380-8",             "%Airbus%", "A380-800"),

    # ── A220 / CSeries ────────────────────────────────────────────────────────
    # madb : "BD-500-1A10" (CS100/A220-100), "BD-500-1A11" (CS300/A220-300)
    ("BCS1", r"^BD-500-1A10",        None,       "A220-100 / CSeries CS100"),
    ("BCS3", r"^BD-500-1A11",        None,       "A220-300 / CSeries CS300"),

    # ── BOEING 737 NG ─────────────────────────────────────────────────────────
    # madb nomme exactement : "737-600", "737-700", "737-800", "737-900", "737-900ER"
    # Note : icao_type_mapping B737 ne liste que BBJ/C-40, mais le pattern vise
    # directement madb pour le 737-700 commercial.
    ("B736", r"^737-600$",           "%Boeing%", "737-600"),
    ("B737", r"^737-700$",           "%Boeing%", "737-700"),
    ("B738", r"^737-800$",           "%Boeing%", "737-800"),
    ("B739", r"^737-900",            "%Boeing%", "737-900 / 737-900ER"),

    # ── BOEING 737 MAX ────────────────────────────────────────────────────────
    # madb : "737-8", "737-8200" (MAX 8) ; "737-9" (MAX 9)
    # Ces modèles matchent déjà via icao_type_mapping (exact), mais on les
    # inclut ici pour centraliser toute la logique de correspondance.
    ("B38M", r"^737-8",              "%Boeing%", "737 MAX 8 / 737-8"),
    ("B39M", r"^737-9$",             "%Boeing%", "737 MAX 9 / 737-9"),
    ("B3XM", r"^737-10$",            "%Boeing%", "737 MAX 10"),

    # ── BOEING 747 ────────────────────────────────────────────────────────────
    ("B741", r"^747-100$",           "%Boeing%", "747-100"),
    ("B742", r"^747-200",            "%Boeing%", "747-200 series"),
    ("B743", r"^747-300$",           "%Boeing%", "747-300"),
    ("B744", r"^747-400$",           "%Boeing%", "747-400"),
    ("B748", r"^747-8$",             "%Boeing%", "747-8 Intercontinental"),

    # ── BOEING 767 ────────────────────────────────────────────────────────────
    ("B763", r"^767-3",              "%Boeing%", "767-300 series"),

    # ── BOEING 777 ────────────────────────────────────────────────────────────
    ("B772", r"^777-200$",           "%Boeing%", "777-200"),
    ("B77L", r"^777-200LR$",         "%Boeing%", "777-200LR"),
    ("B773", r"^777-300$",           "%Boeing%", "777-300"),
    ("B77W", r"^777-300ER$",         "%Boeing%", "777-300ER"),

    # ── BOEING 787 ────────────────────────────────────────────────────────────
    # icao_type_mapping a "787-9 Dreamliner" mais madb n'a que "787-9"
    ("B788", r"^787-8$",             "%Boeing%", "787-8 Dreamliner"),
    ("B789", r"^787-9$",             "%Boeing%", "787-9 Dreamliner"),
    ("B78X", r"^787-10$",            "%Boeing%", "787-10 Dreamliner"),

    # ── ATR ───────────────────────────────────────────────────────────────────
    # madb utilise "ATR 42-XXX" et "ATR 72-XXX" (espace, pas de tiret)
    ("AT43", r"^ATR 42-3",           "%ATR%",    "ATR-42-300/320"),
    ("AT45", r"^ATR 42-5",           "%ATR%",    "ATR-42-500"),
    ("AT72", r"^ATR 72-(1|2)",       "%ATR%",    "ATR-72-100/200 series"),
    # ATR-72-500 et -600 utilisent la même désignation EASA : ATR 72-212A
    ("AT75", r"^ATR 72-212A$",       "%ATR%",    "ATR-72-500 (= ATR 72-212A)"),
    ("AT76", r"^ATR 72-212A$",       "%ATR%",    "ATR-72-600 (= ATR 72-212A)"),

    # ── EMBRAER ERJ-170/190 ───────────────────────────────────────────────────
    # madb : "ERJ 170-100 LR", "ERJ 170-100 STD" etc. (espace, suffixe variante)
    ("E170", r"^ERJ 170-100 ",       "%Embraer%", "ERJ-170-100 (E170)"),
    ("E75L", r"^ERJ 170-200 ",       "%Embraer%", "ERJ-170-200 long wing (E175)"),
    ("E190", r"^ERJ 190-100 ",       "%Embraer%", "ERJ-190-100 (E190)"),
    ("E195", r"^ERJ 190-200 ",       "%Embraer%", "ERJ-190-200 (E195)"),
    ("E290", r"^ERJ 190-300$",       "%Embraer%", "ERJ-190-300 (E190-E2)"),
    ("E295", r"^ERJ 190-400$",       "%Embraer%", "ERJ-190-400 (E195-E2)"),

    # ── DE HAVILLAND DHC-8 ────────────────────────────────────────────────────
    ("DH8A", r"^DHC-8-1",            None,        "DHC-8-100 Dash 8"),
    ("DH8B", r"^DHC-8-2",            None,        "DHC-8-200 Dash 8"),
    ("DH8C", r"^DHC-8-3",            None,        "DHC-8-300 Dash 8"),
    ("DH8D", r"^DHC-8-4",            None,        "DHC-8-400 Dash 8 Q400"),
    ("DHC6", r"^DHC-6",              None,        "DHC-6 Twin Otter"),

    # ── BOMBARDIER CHALLENGER 600/601/604/605 ─────────────────────────────────
    # madb : "CL-600-1A11" (Ch. 600), "CL-600-2A12" (601), "CL-600-2B16" (604/605)
    ("CL60",  r"^CL-600-(1A11|2A12|2B16)", None,        "Challenger 600/601/604/605"),

    # ── BOMBARDIER CHALLENGER 300/350 ─────────────────────────────────────────
    # madb : "BD-100-1A10" (Challenger 300/350)
    ("CL30",  r"^BD-100-1A10",             None,        "Challenger 300"),
    ("CL35",  r"^BD-100-1A10",             None,        "Challenger 350 (= Challenger 300 dans madb)"),

    # ── BOMBARDIER CRJ ────────────────────────────────────────────────────────
    # madb : "CL-600-2B19" (CRJ-200), "CL-600-2C10" (CRJ-700),
    #        "CL-600-2D24" (CRJ-900), "CL-600-2E25" (CRJ-1000)
    ("CRJ2",  r"^CL-600-2B19",             None,        "CRJ-100/200"),
    ("CRJ7",  r"^CL-600-2C10",             None,        "CRJ-700"),
    ("CRJ9",  r"^CL-600-2D24",             None,        "CRJ-900"),
    ("CRJX",  r"^CL-600-2E25",             None,        "CRJ-1000"),

    # ── BOMBARDIER GLOBAL ─────────────────────────────────────────────────────
    # madb : "BD-700-2A12" (Global 7500)
    ("GL7T",  r"^BD-700-2A12",             None,        "Global 7500"),

    # ── DASSAULT FALCON ───────────────────────────────────────────────────────
    ("FA6X",  r"^Falcon 6X",               None,        "Falcon 6X"),
    ("FA7X",  r"^Falcon 7X",               None,        "Falcon 7X"),
    # FA8X absent de madb, approximé par Falcon 7X
    ("FA8X",  r"^Falcon 7X",               None,        "Falcon 8X (approx. Falcon 7X dans madb)"),
    ("F2TH",  r"^Falcon 2000",             None,        "Falcon 2000 series"),

    # ── GULFSTREAM ────────────────────────────────────────────────────────────
    # madb : "G1159A" (GIV-SP), "G1159B" (G400)
    ("GLF4",  r"^G1159[AB]?",              None,        "Gulfstream IV / G400"),
    # madb : "GV" / "GV-SP" (Gulfstream V), "GVI" (G650), "GVII-G500/G600", "GVIII-G700/G800"
    ("GLF5",  r"^GV(-SP)?$",               None,        "Gulfstream V"),
    ("GLF6",  r"^GVI$",                    None,        "Gulfstream G650"),
    ("G500",  r"^GVII-G500$",              None,        "Gulfstream G500"),
    ("G600",  r"^GVII-G600$",              None,        "Gulfstream G600"),
    ("G700",  r"^GVIII-G700$",             None,        "Gulfstream G700"),

    # ── LEARJET ───────────────────────────────────────────────────────────────
    # madb : "Learjet Model 45" / "Learjet 45"
    ("LJ45",  r"^Learjet.*(45|46)",        None,        "Learjet 45/46"),

    # ── SAAB ──────────────────────────────────────────────────────────────────
    ("SB20",  r"^SAAB 2000",               None,        "SAAB 2000"),
    # madb : "SAAB SF340A" (avec préfixe SAAB)
    ("SF34",  r"^SAAB SF340",              None,        "SAAB SF340"),

    # ── EMBRAER ERJ-145 ───────────────────────────────────────────────────────
    # madb : "EMB-145" couvre ERJ-135/140/145
    ("E145",  r"^EMB-145",                 "%Embraer%", "ERJ-145 series"),

    # ── EMBRAER PHENOM / PRAETOR ──────────────────────────────────────────────
    # madb : "EMB-500" (Phenom 100), "EMB-505" (Phenom 300), "EMB-550" (Praetor)
    ("E35L",  r"^EMB-500",                 "%Embraer%", "Phenom 100E (EMB-500)"),
    ("E55P",  r"^EMB-505",                 "%Embraer%", "Phenom 300 (EMB-505)"),
    ("E550",  r"^EMB-550",                 "%Embraer%", "Praetor 500/600 (EMB-550)"),

    # ── PILATUS PC-24 ─────────────────────────────────────────────────────────
    ("PC24",  r"^PC-24",                   None,        "Pilatus PC-24"),

    # ── CESSNA CITATION ───────────────────────────────────────────────────────
    # madb : manufacturer = "Textron Aviation Inc." (pas "Cessna")
    # "525" (M2/CJ), "525A" (CJ2), "525B" (CJ3), "525C" (CJ4)
    # "510" (Mustang), "560" (Encore), "560XL" (XLS/XLS+)
    # "650" (III/VII), "680" / "680A" (Sovereign)
    # madb : "Cessna 510" (avec préfixe Cessna, contrairement aux autres)
    ("C510",  r"^Cessna 510",              "%Textron%",  "Citation Mustang (510)"),
    ("C525",  r"^525$",                    "%Textron%",  "Citation M2 / CJ (525)"),
    ("C25A",  r"^525A$",                   "%Textron%",  "Citation CJ2 (525A)"),
    ("C25B",  r"^525B$",                   "%Textron%",  "Citation CJ3 (525B)"),
    ("C25C",  r"^525C$",                   "%Textron%",  "Citation CJ4 (525C)"),
    ("C560",  r"^560$",                    "%Textron%",  "Citation Encore (560)"),
    ("C56X",  r"^560XL",                   "%Textron%",  "Citation XLS / XLS+ (560XL)"),
    ("C650",  r"^650$",                    "%Textron%",  "Citation III / VII (650)"),
    ("C68A",  r"^680A?$",                  "%Textron%",  "Citation Sovereign (680/680A)"),

    # ── PILATUS PC-12 ─────────────────────────────────────────────────────────
    ("PC12",  r"^PC-12",                   None,        "Pilatus PC-12"),

    # ── DAHER TBM ─────────────────────────────────────────────────────────────
    # madb : "TBM700" couvre TBM-700, TBM-850, TBM-900, TBM-930, TBM-940
    ("TBM7",  r"^TBM",                     None,        "TBM-700 series"),
    ("TBM8",  r"^TBM",                     None,        "TBM-850/900 series"),
    ("TBM9",  r"^TBM",                     None,        "TBM-930/940 series"),

    # ── BEECHCRAFT KING AIR / 1900 ────────────────────────────────────────────
    # madb : "B200" (King Air 200/250), "B300" (King Air 350), "1900" (1900C/D)
    ("BE20",  r"^B200",                    None,        "King Air 200/250"),
    ("B350",  r"^B300",                    None,        "King Air 350 (B300 dans madb)"),
    ("B190",  r"^1900",                    None,        "Beechcraft 1900C/D"),

    # ── SWEARINGEN / FAIRCHILD METRO ─────────────────────────────────────────
    # madb : "SA226" (Metro II/III), "SA227" (Metro 23)
    ("SW4",   r"^SA22[67]",                None,        "Swearingen/Fairchild Metro"),

    # ── PIAGGIO P.180 ─────────────────────────────────────────────────────────
    ("P180",  r"^P\.180",                  None,        "Piaggio P.180 Avanti"),

    # ── CESSNA PISTON ─────────────────────────────────────────────────────────
    # madb : "150", "152", "172", "172RG", "182", "182RG", etc.
    # manufacturer = "Textron Aviation Inc." (pas "Cessna")
    ("C150",  r"^150",                     "%Textron%", "Cessna 150"),
    ("C152",  r"^152",                     "%Textron%", "Cessna 152"),
    ("C172",  r"^172",                     "%Textron%", "Cessna 172 series"),
    ("C182",  r"^182",                     "%Textron%", "Cessna 182 series"),

    # ── PIPER ─────────────────────────────────────────────────────────────────
    # madb : "PA-28-140/150/160/180" (Cherokee), "PA-28R-200/201" (Arrow),
    #        "PA-28R-201T" (Arrow IV turbo), "PA-38-112" (Tomahawk)
    ("P28A",  r"^PA-28-[0-9]",            None,        "Piper PA-28 Cherokee series"),
    ("P28R",  r"^PA-28R-2[0-9][0-9]$",    None,        "Piper PA-28R Arrow"),
    ("P28S",  r"^PA-28R-201T",            None,        "Piper PA-28R Arrow IV Turbo"),
    ("PA38",  r"^PA-38",                  None,        "Piper PA-38 Tomahawk"),

    # ── CIRRUS ────────────────────────────────────────────────────────────────
    # madb : "SR20", "SR22", "SR22T"
    ("SR20",  r"^SR20$",                  None,        "Cirrus SR20"),
    ("SR22",  r"^SR22$",                  None,        "Cirrus SR22"),
    ("S22T",  r"^SR22T$",                 None,        "Cirrus SR22T"),

    # ── DIAMOND ───────────────────────────────────────────────────────────────
    # madb : "DA 40", "DA 42", "DA 62" (avec espace)
    ("DA40",  r"^DA 40",                  None,        "Diamond DA40"),
    ("DA42",  r"^DA 42",                  None,        "Diamond DA42"),
    ("DA62",  r"^DA 62",                  None,        "Diamond DA62"),
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS icao_to_madb_pattern (
    id                       SERIAL PRIMARY KEY,
    icao_code                VARCHAR(10)  NOT NULL,
    madb_model_pattern       VARCHAR(200) NOT NULL,
    madb_manufacturer_pattern VARCHAR(200),
    notes                    VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS idx_icao_to_madb_code
    ON icao_to_madb_pattern(icao_code);
"""

INSERT_SQL = """
INSERT INTO icao_to_madb_pattern
    (icao_code, madb_model_pattern, madb_manufacturer_pattern, notes)
VALUES (%s, %s, %s, %s)
"""


def main():
    print("Connexion à la base...", flush=True)
    conn = psycopg.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute("TRUNCATE icao_to_madb_pattern RESTART IDENTITY")
            cur.executemany(INSERT_SQL, PATTERNS)
            print(f"  {len(PATTERNS)} règles insérées", flush=True)

            # Validation : tester quelques codes clés
            print("\nValidation sur quelques codes :", flush=True)
            test_codes = ["A21N", "A20N", "A333", "AT76", "E190", "B789", "DH8D", "BCS1",
                         "CL60", "CRJ9", "GL7T", "FA6X", "GLF4", "LJ45", "E145",
                         "C525", "PC12", "TBM9", "BE20", "SR22", "DA42"]
            for code in test_codes:
                cur.execute("""
                    SELECT COUNT(DISTINCT n.aircraft_model)
                    FROM icao_to_madb_pattern p
                    JOIN madb_noise_ref n ON (
                        n.aircraft_model ~ p.madb_model_pattern
                        AND (p.madb_manufacturer_pattern IS NULL
                             OR n.manufacturer ILIKE p.madb_manufacturer_pattern)
                    )
                    WHERE p.icao_code = %s
                """, (code,))
                count = cur.fetchone()[0]
                status = "✓" if count > 0 else "✗ AUCUN MATCH"
                print(f"  {code:6s} → {count:3d} modèles madb  {status}", flush=True)

        conn.commit()
        print("\nImport terminé.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
