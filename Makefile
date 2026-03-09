.PHONY: help start stop restart logs clean clean-all status build build-frontend build-api build-producer build-processor import-madb import-icao import-patterns import-all refresh-madb-view

help:
	@echo "🗺️  Carte du Bruit - Commandes disponibles"
	@echo ""
	@echo "  make start          - Démarre tous les services"
	@echo "  make stop           - Arrête tous les services"
	@echo "  make restart        - Redémarre tous les services"
	@echo "  make logs           - Affiche les logs de tous les services"
	@echo "  make logs-producer  - Affiche les logs du producer"
	@echo "  make logs-processor - Affiche les logs du processor"
	@echo "  make logs-api       - Affiche les logs de l'API"
	@echo "  make status         - Statut des services"
	@echo "  make clean          - Arrête et supprime tout (volumes inclus)"
	@echo "  make build          - Rebuild toutes les images"
	@echo "  make build-frontend - Rebuild uniquement le frontend"
	@echo "  make build-api      - Rebuild uniquement l'API"
	@echo "  make build-producer - Rebuild uniquement le producer"
	@echo "  make build-processor- Rebuild uniquement le processor"
	@echo "  make db-shell       - Ouvre un shell PostgreSQL"
	@echo "  make test-api       - Test l'API"
	@echo ""

start:
	@echo "🚀 Démarrage de l'infrastructure..."
	docker-compose up -d
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
	docker-compose down
	@echo "✅ Services arrêtés"

restart:
	@echo "🔄 Redémarrage..."
	docker-compose restart
	@echo "✅ Services redémarrés"

logs:
	docker-compose logs -f

logs-producer:
	docker logs -f aircraft-producer

logs-processor:
	docker logs -f noise-processor

logs-api:
	docker logs -f noise-api

status:
	@echo "📊 Statut des services :"
	@docker-compose ps

build:
	@echo "🔨 Rebuild des images..."
	docker-compose build --no-cache
	@echo "✅ Images reconstruites"

build-frontend:
	@echo "🔨 Rebuild du frontend..."
	docker-compose build --no-cache frontend
	docker-compose up -d
	@echo "✅ Frontend reconstruit et services démarrés !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-api:
	@echo "🔨 Rebuild de l'API..."
	docker-compose build --no-cache api
	docker-compose up -d
	@echo "✅ API reconstruite et services démarrés !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-producer:
	@echo "🔨 Rebuild du producer..."
	docker-compose build --no-cache aircraft-producer
	docker-compose up -d
	@echo "✅ Producer reconstruit et services démarrés !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

build-processor:
	@echo "🔨 Rebuild du processor..."
	docker-compose build --no-cache noise-processor
	docker-compose up -d
	@echo "✅ Processor reconstruit et services démarrés !"
	@echo ""
	@echo "📍 Accès :"
	@echo "  - Frontend : http://localhost:3000"
	@echo "  - API : http://localhost:8000"
	@echo "  - API Docs : http://localhost:8000/docs"
	@echo ""
	@echo "Attendre ~30s pour que les données s'affichent..."

clean:
	@echo "Nettoyage (Kafka/Zookeeper reinitialises, DB preservee)..."
	docker-compose down -v --remove-orphans
	@echo "Services et volumes Kafka supprimes. Les donnees DB (./data/timescaledb/) sont preservees."

clean-all:
	@echo "Nettoyage complet incluant les donnees DB..."
	docker-compose down -v --remove-orphans
	trash data/timescaledb 2>/dev/null || true
	@echo "Tout supprime (DB incluse). Relancer make import-all apres make start."

db-shell:
	@echo "🐘 Connexion à PostgreSQL..."
	docker exec -it timescaledb psql -U noiseuser -d noise_map

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
	docker-compose exec timescaledb psql -U noiseuser -d noise_map -c "REFRESH MATERIALIZED VIEW icao_to_madb_resolved;"

import-icao:  ## Extrait le mapping ICAO → modèles depuis le PDF FAA JO 7360.1H
	python3 airplanes-data/import_icao_mapping.py

import-patterns:  ## Charge les règles de correspondance ICAO → madb
	python3 airplanes-data/import_icao_patterns.py

import-madb:  ## Charge les données MAdB dans TimescaleDB
	docker-compose up -d timescaledb
	sleep 5
	docker-compose exec timescaledb psql -U noiseuser -d noise_map -c "\i /docker-entrypoint-initdb.d/init-db.sql" 2>/dev/null || true
	docker-compose run --rm --no-deps -v $(PWD)/airplanes-data:/data \
		-e DB_HOST=timescaledb \
		noise-processor python /data/import_madb.py