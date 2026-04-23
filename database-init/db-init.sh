#!/usr/bin/env bash
# Initialisation complète de la base de données noise_map sur une nouvelle VM.
#
# Usage:
#   ./database-init/db-init.sh
#
# Prérequis :
#   - Docker disponible
#   - database-init/db-backup/ contient un fichier noise_map_*.sql.gz
#   - database-init/shapes.tar.xz présent
#
# Étapes :
#   1. Démarrage de TimescaleDB
#   2. Initialisation du schéma (db-init.sql)
#   3. Restauration des données de référence statiques (backup : icao, madb, rail_route_shapes)
#   4. Décompression de shapes.tar.xz → database-init/gtfs-statique/shapes.txt
#   5. Import des shapes dans rail_shapes (si table vide)
#   6. Calcul du mapping shape si rail_route_shapes est vide (make assign-shapes)
#   7. Téléchargement du GTFS SNCF + import trips/stop_times + application du mapping

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHAPES_ARCHIVE="$SCRIPT_DIR/shapes-import/shapes.tar.xz"
GTFS_DIR="$SCRIPT_DIR/gtfs-statique"
BACKUP_DIR="$SCRIPT_DIR/db-backup"
GTFS_URL="https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
GTFS_ZIP="/tmp/gtfs-sncf.zip"

TIMESCALE_HOST="${TIMESCALE_HOST:-timescaledb}"
TIMESCALE_USER="${TIMESCALE_USER:-noiseuser}"
TIMESCALE_NAME="${TIMESCALE_NAME:-noise_map}"

# --- Trouver le backup le plus récent ---
BACKUP_FILE=$(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)
if [[ -z "$BACKUP_FILE" ]]; then
  echo "Erreur : aucun fichier *.sql.gz trouvé dans $BACKUP_DIR" >&2
  exit 1
fi

echo "════════════════════════════════════════"
echo " Initialisation noise_map"
echo " Backup : $(basename "$BACKUP_FILE")"
echo "════════════════════════════════════════"

# ── 1. Démarrage TimescaleDB ───────────────
echo ""
echo "[1/6] Démarrage de TimescaleDB..."
docker compose up -d timescaledb

echo "      Attente du démarrage de la base..."
until docker exec "$TIMESCALE_HOST" pg_isready -U "$TIMESCALE_USER" -d "$TIMESCALE_NAME" -q 2>/dev/null; do
  sleep 10
done
echo "      TimescaleDB prête."

# ── 2. Schéma ──────────────────────────────
echo ""
echo "[2/6] Initialisation du schéma (db-init.sql)..."
for attempt in 1 2; do
  if docker exec -i "$TIMESCALE_HOST" psql -U "$TIMESCALE_USER" -d "$TIMESCALE_NAME" < "$SCRIPT_DIR/db-init.sql"; then
    break
  fi
  if [[ $attempt -eq 2 ]]; then
    echo "Erreur : initialisation du schéma échouée après 2 tentatives" >&2
    exit 1
  fi
  echo "      Tentative échouée, nouvelle tentative dans 10s..."
  sleep 10
done
echo "      Schéma initialisé."

# ── 3. Restore ─────────────────────────────
echo ""
echo "[3/6] Restauration du backup ($(basename "$BACKUP_FILE"))..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$TIMESCALE_HOST" psql -U "$TIMESCALE_USER" -d "$TIMESCALE_NAME"
echo "      Restauration terminée."

# ── 4. Décompression shapes ────────────────
echo ""
echo "[4/6] Décompression de shapes.tar.xz..."
mkdir -p "$GTFS_DIR"
cat "$SCRIPT_DIR"/shapes-import/shapes.tar.xz.part-* > "$SHAPES_ARCHIVE"
tar -xJf "$SHAPES_ARCHIVE" -C "$SCRIPT_DIR"
rm "$SHAPES_ARCHIVE"
echo "      shapes.txt extrait dans $GTFS_DIR"

# ── 5. Import shapes (si rail_shapes est vide) ────────────────────────────────
echo ""
echo "[5/7] Import des shapes dans rail_shapes..."
SHAPES_COUNT=$(docker exec "$TIMESCALE_HOST" psql -U "$TIMESCALE_USER" -d "$TIMESCALE_NAME" -tAc \
  "SELECT COUNT(*) FROM rail_shapes" 2>/dev/null || echo "0")
if [[ "$SHAPES_COUNT" -gt 0 ]]; then
  echo "      rail_shapes déjà remplie ($SHAPES_COUNT pts) — ignorée."
else
  docker compose run --rm \
    -v "$SCRIPT_DIR/gtfs-statique:/app/gtfs-statique:ro" \
    gtfs-updater python3 import-gtfs.py --shapes
  echo "      rail_shapes importée."
fi

# ── 6. GTFS SNCF ──────────────────────────────────────────────────────────────
echo ""
echo "[6/7] Téléchargement du GTFS SNCF..."
curl -fsSL -o "$GTFS_ZIP" "$GTFS_URL"
echo "      Extraction vers $GTFS_DIR..."
unzip -o "$GTFS_ZIP" -d "$GTFS_DIR" > /dev/null
rm -f "$GTFS_ZIP"
echo "      Import stops + routes + trips + stop_times..."
docker compose run --rm \
  -v "$SCRIPT_DIR/gtfs-statique:/app/gtfs-statique:ro" \
  gtfs-updater python3 import-gtfs.py
echo "      GTFS importé."

# ── 7. Calcul du mapping shape (si rail_route_shapes est vide) ────────────────
echo ""
echo "[7/7] Vérification du mapping shapes → trips..."
MAPPING_COUNT=$(docker exec "$TIMESCALE_HOST" psql -U "$TIMESCALE_USER" -d "$TIMESCALE_NAME" -tAc \
  "SELECT COUNT(*) FROM rail_route_shapes" 2>/dev/null || echo "0")
if [[ "$MAPPING_COUNT" -gt 0 ]]; then
  echo "      rail_route_shapes déjà remplie ($MAPPING_COUNT entrées) — skip."
else
  echo "      rail_route_shapes vide — calcul du mapping géométrique (1-2 min)..."
  docker compose run --rm gtfs-updater python3 assign-shapes.py
  echo "      Mapping calculé."
fi

echo ""
echo "════════════════════════════════════════"
echo " Initialisation terminée."
echo "════════════════════════════════════════"
