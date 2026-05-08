-include .env

.PHONY: help \
        start stop restart status \
        logs logs-aircraft-producer logs-aircraft-processor \
        logs-road-producer logs-road-processor \
        logs-railway-producer logs-railway-processor \
        logs-kafka logs-api logs-frontend \
        build build-frontend build-api \
        build-aircraft-producer build-road-producer \
        build-aircraft-processor build-road-processor \
        build-railway-producer build-railway-processor \
        builder-clean \
        db-init db-shell db-consult db-start db-backup db-restore \
        import-all import-madb import-icao import-patterns refresh-madb-view \
        import-rfn-lines import-shapes assign-shapes \
        import-gtfs import-gtfs-static import-gtfs-temporal \
        clean clean-all \
        test-api

BACKUP_DIR := ./database-init/db-backup

# --- Help ---

help:
	@echo "🗺️  Carte du Bruit - Commandes disponibles"
	@echo ""
	@echo "  make start          - Démarre tous les services (sans pgadmin)"
	@echo "  make stop           - Arrête tous les services"
	@echo "  make restart        - Redémarre tous les services"
	@echo "  make logs           - Affiche les logs de tous les services"
	@echo "  make logs-aircraft-producer  - Affiche les logs du producer avions"
	@echo "  make logs-road-producer      - Affiche les logs du producer routier"
	@echo "  make logs-railway-producer   - Affiche les logs du producer trains"
	@echo "  make logs-aircraft-processor - Affiche les logs du processor avions"
	@echo "  make logs-road-processor     - Affiche les logs du processor routier"
	@echo "  make logs-railway-processor  - Affiche les logs du processor trains"
	@echo "  make logs-kafka              - Affiche les logs de Kafka"
	@echo "  make logs-api                - Affiche les logs de l'API"
	@echo "  make status         - Statut des services"
	@echo "  make build          - Rebuild toutes les images"
	@echo "  make build-frontend - Rebuild uniquement le frontend"
	@echo "  make build-api      - Rebuild uniquement l'API"
	@echo "  make build-aircraft-producer - Rebuild uniquement le producer avions"
	@echo "  make build-road-producer     - Rebuild uniquement le producer routier"
	@echo "  make build-railway-producer  - Rebuild uniquement le producer ferroviaire"
	@echo "  make build-aircraft-processor   - Rebuild uniquement le processor avions"
	@echo "  make build-road-processor    - Rebuild uniquement le processor routier"
	@echo "  make build-railway-processor - Rebuild uniquement le processor ferroviaire"
	@echo "  make db-init        - Initialisation complète de la base (nouvelle VM)"
	@echo "  make db-shell       - Ouvre un shell PostgreSQL"
	@echo "  make db-consult     - Démarre pgadmin (accès : http://localhost:5050)"
	@echo "  make db-backup      - Sauvegarde les tables de référence statiques"
	@echo "  make db-restore     - Restaure depuis FILE=noise_map_YYYYMMDD.sql.gz"
	@echo "  make import-all     - Lance tous les imports de données de référence"
	@echo "  make clean          - Arrête et supprime volumes Kafka (DB préservée)"
	@echo "  make clean-all      - Nettoyage complet incluant les données DB"
	@echo "  make test-api       - Test l'API"
	@echo ""

# --- Services ---

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

status:
	@echo "📊 Statut des services :"
	@docker compose ps

# --- Logs ---

logs:
	docker compose logs -f --tail=50

logs-aircraft-producer:
	docker logs -f --tail=50 aircraft-producer

logs-aircraft-processor:
	docker logs -f --tail=50 aircraft-processor

logs-road-producer:
	docker compose logs -f --tail=50 road-producer

logs-road-processor:
	docker compose logs -f --tail=50 road-processor

logs-railway-producer:
	docker compose logs -f --tail=50 railway-producer

logs-railway-processor:
	docker compose logs -f --tail=50 railway-processor

logs-kafka:
	docker logs -f --tail=50 kafka

logs-api:
	docker logs -f --tail=50 noise-api

logs-frontend:
	docker logs -f --tail=50 noise-frontend

# --- Build ---

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

builder-clean:
	@echo "Nettoyage des builds..."
	docker builder prune -a

# --- Base de données ---

db-init:
	bash database-init/db-init.sh

db-shell:
	@echo "🐘 Connexion à PostgreSQL..."
	docker exec -it timescaledb psql -U $(TIMESCALE_USER) -d $(TIMESCALE_NAME)

db-consult:
	@echo "🐘 Démarrage de PostgreSQL et pgadmin..."
	docker compose up -d timescaledb
	docker compose --profile admin up -d pgadmin
	@echo "✅ pgadmin disponible sur http://localhost:5050"

db-start:
	@echo "🐘 Démarrage de PostgreSQL..."
	docker compose up -d timescaledb

# --- Backup / Restore ---

db-backup:
	@mkdir -p $(BACKUP_DIR)
	@echo "Backup des tables de référence statiques ($(TIMESCALE_NAME))..."
	docker exec timescaledb pg_dump -U $(TIMESCALE_USER) -d $(TIMESCALE_NAME) --clean --if-exists \
		-t icao_type_mapping \
		-t madb_noise_ref \
		-t icao_noise_pattern \
		| gzip > $(BACKUP_DIR)/noise_map_$$(date +%Y%m%d).sql.gz
	@echo "Backup sauvegardé: $(BACKUP_DIR)/noise_map_$$(date +%Y%m%d).sql.gz"

db-restore:
	@test -n "$(FILE)" || (echo "Usage: make db-restore FILE=noise_map_20260320.sql.gz" && exit 1)
	@test -f $(BACKUP_DIR)/$(FILE) || (echo "Fichier introuvable: $(BACKUP_DIR)/$(FILE)" && exit 1)
	@echo "Restauration depuis $(BACKUP_DIR)/$(FILE)..."
	gunzip -c $(BACKUP_DIR)/$(FILE) | docker exec -i timescaledb psql -U $(TIMESCALE_USER) -d $(TIMESCALE_NAME)
	@echo "Restauration terminée."

# --- Import des données de référence ---

import-all:
	$(MAKE) import-madb
	$(MAKE) import-icao
	$(MAKE) import-patterns
	$(MAKE) refresh-madb-view

import-madb:
	docker compose up -d timescaledb
	sleep 5
	docker compose exec timescaledb psql -U $(TIMESCALE_USER) -d $(TIMESCALE_NAME) -c "\i /docker-entrypoint-dbinit.d/db-init.sql" 2>/dev/null || true
	docker compose run --rm --no-deps -v $(PWD)/aircraft-data:/data \
		-e TIMESCALE_HOST=timescaledb \
		aircraft-processor python /data/import_madb.py

import-icao:
	python3 aircraft-data/import_icao_mapping.py

import-patterns:
	python3 aircraft-data/import_icao_patterns.py

refresh-madb-view:
	docker compose exec timescaledb psql -U $(TIMESCALE_USER) -d $(TIMESCALE_NAME) -c "REFRESH MATERIALIZED VIEW icao_noise_resolved;"

import-rfn-lines:
	docker compose run --rm \
		-v $(PWD)/database-init/lignes-rfn:/app/lignes-rfn:ro \
		gtfs-updater python3 import-rfn-lines.py

import-shapes:
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --shapes

assign-shapes:
	docker compose run --rm gtfs-updater python3 assign_shapes.py

import-gtfs:
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py

import-gtfs-static:
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --static

import-gtfs-temporal:
	docker compose run --rm \
		-v $(PWD)/database-init/gtfs-statique:/app/gtfs-statique:ro \
		gtfs-updater python3 import-gtfs.py --temporal

# --- Nettoyage ---

clean:
	@echo "Nettoyage (Kafka/Zookeeper reinitialises, DB preservee)..."
	docker compose down -v --remove-orphans
	@echo "Services et volumes Kafka supprimes. Les donnees DB (./data/timescaledb/) sont preservees."

clean-all:
	@echo "Nettoyage complet incluant les donnees DB..."
	docker compose down -v --remove-orphans
	trash data/timescaledb 2>/dev/null || true
	@echo "Tout supprime (DB incluse). Relancer make import-all apres make start."

# --- Tests ---

test-api:
	@echo "🧪 Test de l'API..."
	@echo ""
	@echo "Stats globales :"
	@curl -s http://localhost:8000/api/stats | python3 -m json.tool
	@echo ""
	@echo "Positions des avions :"
	@curl -s http://localhost:8000/api/aircraft/current | python3 -m json.tool | head -20
