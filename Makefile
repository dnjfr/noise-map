.PHONY: help start stop restart logs clean clean-all status build build-frontend build-api build-aircraft-producer build-road-producer build-aircraft-processor build-road-processor build-railway-producer build-railway-processor logs-railway-producer logs-railway-processor import-madb import-icao import-patterns import-all refresh-madb-view import-rfn-lines import-shapes import-gtfs import-gtfs-static import-gtfs-temporal db-init

help:
	@echo "🗺️  Carte du Bruit - Commandes disponibles"
	@echo ""
	@echo "  make start          - Démarre tous les services"
	@echo "  make stop           - Arrête tous les services"
	@echo "  make restart        - Redémarre tous les services"
	@echo "  make logs           - Affiche les logs de tous les services"
	@echo "  make logs-aircraft-producer  - Affiche les logs du producer avions"
	@echo "  make logs-road-producer      - Affiche les logs du producer routier"
	@echo "  make logs-railway-producer     - Affiche les logs du producer trains"
	@echo "  make logs-aircraft-processor    - Affiche les logs du processor avions"
	@echo "  make logs-road-processor     - Affiche les logs du processor routier"
	@echo "  make logs-railway-processor    - Affiche les logs du processor trains"
	@echo "  make logs-kafka                - Affiche les logs de Kafka"
	@echo "  make logs-api                - Affiche les logs de l'API"
	@echo "  make status         - Statut des services"
	@echo "  make clean          - Arrête et supprime tout (volumes inclus)"
	@echo "  make build          - Rebuild toutes les images"
	@echo "  make build-frontend - Rebuild uniquement le frontend"
	@echo "  make build-api      - Rebuild uniquement l'API"
	@echo "  make build-aircraft-producer - Rebuild uniquement le producer avions"
	@echo "  make build-road-producer     - Rebuild uniquement le producer routier"
	@echo "  make build-railway-producer  - Rebuild uniquement le producer ferroviaire"
	@echo "  make build-aircraft-processor   - Rebuild uniquement le processor avions"
	@echo "  make build-road-processor    - Rebuild uniquement le processor routier"
	@echo "  make build-railway-processor - Rebuild uniquement le processor ferroviaire"
	@echo "  make db-shell       - Ouvre un shell PostgreSQL"
	@echo "  make test-api       - Test l'API"
	@echo ""

start:
	@echo "🚀 Démarrage de l'infrastructure..."
	docker compose up -d --remove-orphans
	@echo "✅ Services démarrés !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

stop:
	@echo "⏹️  Arrêt des services..."
	docker compose stop
	@echo "✅ Services arrêtés"

restart:
	@echo "🔄 Redémarrage..."
	docker compose down
	docker compose up -d
	@echo "✅ Services redémarrés"

logs:
	docker compose logs -f

logs-aircraft-producer:
	docker logs -f aircraft-producer

logs-aircraft-processor:
	docker logs -f aircraft-processor

logs-road-producer:
	docker compose logs -f road-producer

logs-road-processor:
	docker compose logs -f road-processor

logs-railway-producer:
	docker compose logs -f railway-producer

logs-railway-processor:
	docker compose logs -f railway-processor

logs-kafka:
	docker logs -f kafka

logs-api:
	docker logs -f noise-api

logs-frontend:
	docker logs -f noise-frontend

status:
	@echo "📊 Statut des services :"
	@docker compose ps

build:
	@echo "🔨 Rebuild des images..."
	docker compose build --no-cache
	@echo "✅ Images reconstruites"

build-frontend:
	@echo "🔨 Rebuild du frontend..."
	docker compose build --no-cache frontend
	docker compose up -d frontend
	@echo "✅ Frontend reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-api:
	@echo "🔨 Rebuild de l'API..."
	docker compose build --no-cache api
	docker compose up -d api
	@echo "✅ API reconstruite et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-aircraft-producer:
	@echo "🔨 Rebuild du producer avions..."
	docker compose build --no-cache aircraft-producer
	docker compose up -d aircraft-producer
	@echo "✅ Producer avions reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-road-producer:
	@echo "🔨 Rebuild du producer routier..."
	docker compose build --no-cache road-producer
	docker compose up -d road-producer
	@echo "✅ Producer routier reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-aircraft-processor:
	@echo "🔨 Rebuild du processor avions..."
	docker compose build --no-cache aircraft-processor
	docker compose up -d aircraft-processor
	@echo "✅ Processor avions reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-road-processor:
	@echo "🔨 Rebuild du processor routier..."
	docker compose build --no-cache road-processor
	docker compose up -d road-processor
	@echo "✅ Processor routier reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-railway-producer:
	@echo "🔨 Rebuild du producer ferroviaire..."
	docker compose build --no-cache railway-producer
	docker compose up -d railway-producer
	@echo "✅ Producer ferroviaire reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-railway-processor:
	@echo "🔨 Rebuild du processor ferroviaire..."
	docker compose build --no-cache railway-processor
	docker compose up -d railway-processor
	@echo "✅ Processor ferroviaire reconstruit et service redémarré !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

clean:
	@echo "Nettoyage (Kafka/Zookeeper reinitialises, DB preservee)..."
	docker compose down -v --remove-orphans
	@echo "Services et volumes Kafka supprimes. Les donnees DB (./data/timescaledb/) sont preservees."

clean-all:
	@echo "Nettoyage complet incluant les donnees DB..."
	docker compose down -v --remove-orphans
	trash data/timescaledb 2>/dev/null || true
	@echo "Tout supprime (DB incluse). Relancer make import-all apres make start."

db-shell:
	@echo "🐘 Connexion à PostgreSQL..."
	docker exec -it timescaledb psql -U noiseuser -d noise_map

db-consult:
	@echo "🐘 Démarrage de PostgreSQL et PGAdmin..."
	docker compose up -d timescaledb
	docker compose up -d pgadmin

db-start:
	@echo "🐘 Démarrage de PostgreSQL et PGAdmin..."
	docker compose up -d timescaledb

test-api:
	@echo "🧪 Test de l'API..."
	@echo ""
	@echo "Stats globales :"
	@curl -s http://localhost:8000/api/stats | python3 -m json.tool
	@echo ""
	@echo "Positions des avions :"
	@curl -s http://localhost:8000/api/aircraft/current | python3 -m json.tool | head -20

import-all:  ## Lance tous les imports de données de référence dans l'ordre
	$(MAKE) import-madb
	$(MAKE) import-icao
	$(MAKE) import-patterns
	$(MAKE) refresh-madb-view

refresh-madb-view:  ## Rafraîchit la vue matérialisée icao_to_madb_resolved (après import-all)
	docker compose exec timescaledb psql -U noiseuser -d noise_map -c "REFRESH MATERIALIZED VIEW icao_to_madb_resolved;"

import-icao:  ## Extrait le mapping ICAO → modèles depuis le PDF FAA JO 7360.1H
	python3 aircraft-data/import_icao_mapping.py

import-patterns:  ## Charge les règles de correspondance ICAO → madb
	python3 aircraft-data/import_icao_patterns.py

import-shapes:  ## Importe rail_shapes depuis gtfs-statique/shapes.txt (one-shot pfaedle, ~461 MB)
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --shapes

assign-shapes:  ## Calcule le mapping (route, first_stop, last_stop) → shape_id et l'écrit dans rail_route_shapes + rail_trips
	docker compose run --rm gtfs-updater python3 assign_shapes.py

import-gtfs:  ## Importe stops, routes, trips, stop_times (sans shapes)
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py

import-gtfs-static:  ## Importe uniquement stops, routes
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --static

import-gtfs-temporal:  ## Importe uniquement trips, stop_times (mise à jour quotidienne ~18h)
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --temporal

import-madb:  ## Charge les données MAdB dans TimescaleDB
	docker compose up -d timescaledb
	sleep 5
	docker compose exec timescaledb psql -U noiseuser -d noise_map -c "\i /docker-entrypoint-dbinit.d/db-init.sql" 2>/dev/null || true
	docker compose run --rm --no-deps -v $(PWD)/aircraft-data:/data \
		-e TIMESCALE_HOST=timescaledb \
		aircraft-processor python /data/import_madb.py

# --- Init DB ---

# Usage: make db-init
# Initialisation complète sur une nouvelle VM : démarrage DB + schéma + restore + shapes + GTFS
db-init:
	bash database-init/db-init.sh

# --- Backup / Restore ---

BACKUP_DIR := ./database-init/db-backup

# Usage: make db-backup
db-backup:
	@mkdir -p $(BACKUP_DIR)
	@echo "Backup des tables de référence statiques (noise_map)..."
	docker exec timescaledb pg_dump -U noiseuser -d noise_map --clean --if-exists \
		-t icao_type_mapping \
		-t madb_noise_ref \
		-t icao_noise_pattern \
		-t rail_route_shapes \
		| gzip > $(BACKUP_DIR)/noise_map_$$(date +%Y%m%d).sql.gz
	@echo "Backup sauvegardé: $(BACKUP_DIR)/noise_map_$$(date +%Y%m%d).sql.gz"

# Usage: make db-restore FILE=noise_map_20260320.sql.gz
db-restore:
	@test -n "$(FILE)" || (echo "Usage: make db-restore FILE=noise_map_20260320.sql.gz" && exit 1)
	@test -f $(BACKUP_DIR)/$(FILE) || (echo "Fichier introuvable: $(BACKUP_DIR)/$(FILE)" && exit 1)
	@echo "Restauration depuis $(BACKUP_DIR)/$(FILE)..."
	gunzip -c $(BACKUP_DIR)/$(FILE) | docker exec -i timescaledb psql -U noiseuser -d noise_map
	@echo "Restauration terminée."