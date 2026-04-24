#!/usr/bin/env python3
"""Corrige les shapes dégradées (shp_3_*) depuis les données RFN et/ou des shapes DB existantes.

Shapes corrigées :
  shp_3_1001, shp_3_785  → Clermont-Ferrand ↔ Mende  (RFN 723000+722000 + shp_2_7951)
  shp_3_1043             → Paris-Est → Troyes          (RFN 001000)
  shp_3_1071             → Épinal → Nancy              (RFN 042000+070000)
  shp_3_1154, shp_3_951  → Lunéville → Nancy           (RFN 070000)
  shp_3_713, shp_3_1035  → Niederbronn ↔ Bitche        (RFN 159000)

Usage :
    python3 fix-shape-rfn.py                     # applique tous les correctifs
    python3 fix-shape-rfn.py --shape shp_3_XXXX  # corrige une shape spécifique
    python3 fix-shape-rfn.py --dry-run            # affiche sans modifier la DB
"""
import argparse
import csv
import json
import math
import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv(override=True)

CSV_PATH = "/app/lignes-rfn/formes-des-lignes-du-rfn.csv"
csv.field_size_limit(10_000_000)


# ─── Utilitaires géométriques ─────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111_000
    dlon = (lon2 - lon1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat**2 + dlon**2)


def nearest_idx(coords, lat, lon):
    best_d, best_i = float("inf"), 0
    for i, (clon, clat) in enumerate(coords):
        d = haversine_m(lat, lon, clat, clon)
        if d < best_d:
            best_d, best_i = d, i
    return best_i, best_d


def extract_section(coords, from_stop, to_stop, label=""):
    """Sous-liste de coords entre from_stop et to_stop (dans le bon sens)."""
    idx_from, d_from = nearest_idx(coords, *from_stop)
    idx_to,   d_to   = nearest_idx(coords, *to_stop)
    print(f"  {label}: [{idx_from}]({d_from:.0f}m) → [{idx_to}]({d_to:.0f}m)")
    if idx_from <= idx_to:
        return coords[idx_from : idx_to + 1]
    return list(reversed(coords[idx_to : idx_from + 1]))


def load_rfn_line(rfn_code: str) -> list[tuple[float, float]]:
    """Tous les points de la ligne RFN depuis le CSV → [(lon, lat), ...]."""
    coords = []
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row["CODE_LIGNE"] != rfn_code:
                continue
            geom = json.loads(row["Geo Shape"])
            coords.extend(geom["coordinates"])
    return coords


def load_db_shape(cur, shape_id: str) -> list[tuple[float, float]]:
    """Points d'une shape DB ordonnés par séquence → [(lon, lat), ...]."""
    cur.execute(
        "SELECT shape_pt_lon, shape_pt_lat FROM rail_shapes "
        "WHERE shape_id = %s ORDER BY shape_pt_sequence",
        (shape_id,),
    )
    return [(lon, lat) for lon, lat in cur.fetchall()]


def apply_fix(conn, shape_id: str, combined: list, dry_run: bool) -> None:
    """Remplace les points de shape_id en base par combined."""
    print(f"\n  Shape finale : {len(combined)} points")
    print(f"  Début : lat={combined[0][1]:.5f}, lon={combined[0][0]:.5f}")
    print(f"  Fin   : lat={combined[-1][1]:.5f}, lon={combined[-1][0]:.5f}")
    if dry_run:
        print("  [dry-run] Aucune modification en base.")
        return
    print(f"  Remplacement de {shape_id}...")
    with conn.cursor() as cur:
        with conn.transaction():
            cur.execute("DELETE FROM rail_shapes WHERE shape_id = %s", (shape_id,))
            rows = []
            cum_dist = 0.0
            prev = None
            for seq, (lon, lat) in enumerate(combined):
                if prev is not None:
                    cum_dist += haversine_m(prev[1], prev[0], lat, lon)
                rows.append((shape_id, lat, lon, seq + 1, cum_dist))
                prev = (lon, lat)
            cur.executemany(
                "INSERT INTO rail_shapes "
                "(shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence, shape_dist_traveled) "
                "VALUES (%s, %s, %s, %s, %s)",
                rows,
            )
        cur.execute("SELECT COUNT(*) FROM rail_shapes WHERE shape_id = %s", (shape_id,))
        print(f"  {cur.fetchone()[0]} points en base ✓")


# ─── Fonctions de correction ──────────────────────────────────────────────────

def fix_clermont_mende(conn, shape_id: str, dry_run: bool = False) -> None:
    """Clermont-Ferrand ↔ Mende via RFN 723000+722000 + shp_2_7951.

    Trois sections :
      1. RFN 723000 : Mende → jonction avec 722000
      2. RFN 722000 : jonction → Marvejols
      3. shp_2_7951 (IC 15941, tracé vérifié) : Marvejols → Clermont (inversé)
    """
    MENDE            = (44.522347, 3.501981)
    MARVEJOLS        = (44.544675, 3.281119)
    CLERMONT         = (45.778945, 3.100543)
    JUNCTION_723_722 = (44.498800, 3.248000)
    SOURCE_SHAPE     = "shp_2_7951"

    print(f"\n=== {shape_id} : Clermont-Ferrand ↔ Mende ===")

    print("Section 1 — RFN 723000 (Mende → jonction 722000)")
    coords_723 = load_rfn_line("723000")
    if not coords_723:
        print(f"ERREUR : ligne 723000 introuvable dans {CSV_PATH}", file=sys.stderr)
        return
    print(f"  {len(coords_723)} points chargés")
    sec1 = extract_section(coords_723, MENDE, JUNCTION_723_722, "723000")
    print(f"  → {len(sec1)} points retenus")

    print("Section 2 — RFN 722000 (jonction → Marvejols)")
    coords_722 = load_rfn_line("722000")
    if not coords_722:
        print(f"ERREUR : ligne 722000 introuvable dans {CSV_PATH}", file=sys.stderr)
        return
    print(f"  {len(coords_722)} points chargés")
    sec2 = extract_section(coords_722, JUNCTION_723_722, MARVEJOLS, "722000")
    print(f"  → {len(sec2)} points retenus")

    print(f"Section 3 — DB {SOURCE_SHAPE} (Marvejols → Clermont, inversé)")
    with conn.cursor() as cur:
        coords_db = load_db_shape(cur, SOURCE_SHAPE)
    if not coords_db:
        print(f"ERREUR : {SOURCE_SHAPE} introuvable en base", file=sys.stderr)
        return
    print(f"  {len(coords_db)} points chargés")
    sec3 = list(reversed(extract_section(coords_db, CLERMONT, MARVEJOLS, SOURCE_SHAPE)))
    print(f"  → {len(sec3)} points retenus (après inversion)")

    combined = sec1 + sec2[1:] + sec3[1:]
    apply_fix(conn, shape_id, combined, dry_run)


def fix_paris_troyes(conn, shape_id: str, dry_run: bool = False) -> None:
    """Paris-Est → Troyes via RFN 001000 (ligne Paris-Mulhouse conventionnelle)."""
    PARIS_EST = (48.876742, 2.358424)
    TROYES    = (48.296069, 4.065281)

    print(f"\n=== {shape_id} : Paris-Est → Troyes ===")
    coords = load_rfn_line("001000")
    if not coords:
        print("ERREUR : ligne 001000 introuvable", file=sys.stderr)
        return
    print(f"  {len(coords)} points chargés")
    section = extract_section(coords, PARIS_EST, TROYES, "001000")
    print(f"  → {len(section)} points retenus")
    apply_fix(conn, shape_id, section, dry_run)


def fix_epinal_nancy(conn, shape_id: str, dry_run: bool = False) -> None:
    """Épinal → Nancy via RFN 042000 (Épinal→jonction) + 070000 (jonction→Nancy).

    La jonction entre les deux lignes RFN se situe à ~249m d'écart
    près de Varangéville / Saint-Nicolas-de-Port (48.562°N, 6.391°E).
    """
    EPINAL   = (48.178005, 6.441787)
    NANCY    = (48.689857, 6.174579)
    JUNCTION = (48.56178,  6.39152)   # point de convergence 042000 ↔ 070000

    print(f"\n=== {shape_id} : Épinal → Nancy ===")

    print("Section 1 — RFN 042000 (Épinal → jonction)")
    coords_042 = load_rfn_line("042000")
    if not coords_042:
        print("ERREUR : ligne 042000 introuvable", file=sys.stderr)
        return
    print(f"  {len(coords_042)} points chargés")
    sec1 = extract_section(coords_042, EPINAL, JUNCTION, "042000")
    print(f"  → {len(sec1)} points retenus")

    print("Section 2 — RFN 070000 (jonction → Nancy)")
    coords_070 = load_rfn_line("070000")
    if not coords_070:
        print("ERREUR : ligne 070000 introuvable", file=sys.stderr)
        return
    print(f"  {len(coords_070)} points chargés")
    sec2 = extract_section(coords_070, JUNCTION, NANCY, "070000")
    print(f"  → {len(sec2)} points retenus")

    combined = sec1 + sec2[1:]
    apply_fix(conn, shape_id, combined, dry_run)


def fix_nancy_luneville(conn, shape_id: str, dry_run: bool = False) -> None:
    """Nancy ↔ Lunéville via RFN 070000 (ligne Paris-Strasbourg)."""
    NANCY     = (48.689857, 6.174579)
    LUNEVILLE = (48.587990, 6.496997)

    print(f"\n=== {shape_id} : Nancy ↔ Lunéville ===")
    coords = load_rfn_line("070000")
    if not coords:
        print("ERREUR : ligne 070000 introuvable", file=sys.stderr)
        return
    print(f"  {len(coords)} points chargés")
    section = extract_section(coords, LUNEVILLE, NANCY, "070000")
    print(f"  → {len(section)} points retenus")
    apply_fix(conn, shape_id, section, dry_run)


def fix_haguenau_bitche(conn, shape_id: str, dry_run: bool = False) -> None:
    """Niederbronn-les-Bains ↔ Bitche via RFN 159000."""
    NIEDERBRONN = (48.952385, 7.634090)
    BITCHE      = (49.048717, 7.432153)

    print(f"\n=== {shape_id} : Niederbronn ↔ Bitche ===")
    coords = load_rfn_line("159000")
    if not coords:
        print("ERREUR : ligne 159000 introuvable", file=sys.stderr)
        return
    print(f"  {len(coords)} points chargés")
    section = extract_section(coords, NIEDERBRONN, BITCHE, "159000")
    print(f"  → {len(section)} points retenus")
    apply_fix(conn, shape_id, section, dry_run)


# ─── Registre des correctifs ──────────────────────────────────────────────────

FIXES: dict[str, callable] = {
    "shp_3_1001": fix_clermont_mende,   # K150 Clermont-Mende
    "shp_3_785":  fix_clermont_mende,   # K150 variante direction inverse
    "shp_3_992":  fix_clermont_mende,   # K150 CTE 940xx (94002, 94004, etc.)
    "shp_3_1043": fix_paris_troyes,     # K4  Paris-Est → Troyes (143 trips)
    "shp_3_1071": fix_epinal_nancy,     # C43+ Épinal → Nancy (107 trips)
    "shp_3_1154": fix_nancy_luneville,  # C42+ Lunéville → Nancy (61 trips)
    "shp_3_951":  fix_nancy_luneville,  # C41  Lunéville → Nancy (27 trips)
    "shp_3_713":  fix_haguenau_bitche,  # P817 Bitche → Niederbronn (22 trips)
    "shp_3_1035": fix_haguenau_bitche,  # P817 Niederbronn → Bitche (21 trips)
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape", default=None,
                        help="Corriger uniquement cette shape_id (ex: shp_3_1043)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les informations sans modifier la base")
    args = parser.parse_args()

    if args.shape and args.shape not in FIXES:
        print(f"ERREUR : shape '{args.shape}' inconnue du registre.", file=sys.stderr)
        print(f"Shapes disponibles : {', '.join(FIXES)}", file=sys.stderr)
        sys.exit(1)

    conn_str = (
        f"host={os.environ['TIMESCALE_HOST']} "
        f"port={os.environ.get('TIMESCALE_PORT', 5432)} "
        f"dbname={os.environ['TIMESCALE_NAME']} "
        f"user={os.environ['TIMESCALE_USER']} "
        f"password={os.environ['TIMESCALE_PASSWORD']}"
    )

    targets = {args.shape: FIXES[args.shape]} if args.shape else FIXES

    errors = []
    with psycopg.connect(conn_str) as conn:
        for shape_id, fix_fn in targets.items():
            try:
                fix_fn(conn, shape_id, args.dry_run)
            except Exception as e:
                msg = f"ERREUR sur {shape_id}: {e}"
                print(msg, file=sys.stderr)
                errors.append(msg)

    print("\n════════════════════════════════════════")
    print(f" Corrections terminées — {len(targets) - len(errors)}/{len(targets)} réussies")
    if errors:
        for e in errors:
            print(f"  ✗ {e}")
    print("════════════════════════════════════════")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
