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
#   3. Restauration des données de référence (backup)
#   4. Décompression de shapes.tar.xz → database-init/gtfs-statique/shapes.txt
#   5. Import des shapes dans rail_shapes
#   6. Téléchargement du GTFS SNCF + import stops/routes/trips/stop_times

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHAPES_ARCHIVE="$SCRIPT_DIR/shapes-import/shapes.tar.xz"
GTFS_DIR="$SCRIPT_DIR/gtfs-statique"
BACKUP_DIR="$SCRIPT_DIR/db-backup"
GTFS_URL="https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
GTFS_ZIP="/tmp/gtfs-sncf.zip"

DB_CONTAINER="${DB_CONTAINER:-timescaledb}"
DB_USER="${DB_USER:-noiseuser}"
DB_NAME="${DB_NAME:-noise_map}"

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
until docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" -q 2>/dev/null; do
  sleep 2
done
echo "      TimescaleDB prête."

# ── 2. Schéma ──────────────────────────────
echo ""
echo "[2/6] Initialisation du schéma (db-init.sql)..."
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$SCRIPT_DIR/db-init.sql"
echo "      Schéma initialisé."

# ── 3. Restore ─────────────────────────────
echo ""
echo "[3/6] Restauration du backup ($(basename "$BACKUP_FILE"))..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
echo "      Restauration terminée."

# ── 4. Décompression shapes ────────────────
echo ""
echo "[4/6] Décompression de shapes.tar.xz..."
mkdir -p "$GTFS_DIR"
tar -xJf "$SHAPES_ARCHIVE" -C "$SCRIPT_DIR"
echo "      shapes.txt extrait dans $GTFS_DIR"

# ── 5. Import shapes ──────────────────────
echo ""
echo "[5/6] Import des shapes dans rail_shapes..."
docker compose run --rm \
  -v "$SCRIPT_DIR/gtfs-statique:/app/gtfs-statique:ro" \
  gtfs-updater python3 import-gtfs.py --shapes
echo "      rail_shapes importé."

# ── 6. GTFS SNCF ──────────────────────────
echo ""
echo "[6/6] Téléchargement du GTFS SNCF..."
curl -fsSL -o "$GTFS_ZIP" "$GTFS_URL"
echo "      Extraction vers $GTFS_DIR..."
unzip -o "$GTFS_ZIP" -d "$GTFS_DIR" > /dev/null
rm -f "$GTFS_ZIP"
echo "      Import stops / routes / trips / stop_times..."
docker compose run --rm \
  -v "$SCRIPT_DIR/gtfs-statique:/app/gtfs-statique:ro" \
  gtfs-updater python3 import-gtfs.py
echo "      GTFS importé."

echo ""
echo "════════════════════════════════════════"
echo " Initialisation terminée."
echo "════════════════════════════════════════"
