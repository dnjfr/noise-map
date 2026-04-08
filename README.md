# 🗺️ Carte du bruit en France - Données temps réel

Projet de visualisation en temps réel des niveaux de bruit aérien, routier et ferroviaire au-dessus de la France, utilisant Kafka, TimescaleDB et OpenSky Network.

## 📋 Architecture

```
OpenSky API → Producer (Python) → Kafka → Processor → TimescaleDB → API (FastAPI) → Frontend (Leaflet.js)
```

**Technologies utilisées** :
- **Kafka** : Streaming de données en temps réel
- **TimescaleDB** : Base de données PostgreSQL optimisée pour les séries temporelles
- **SQLAlchemy** : ORM Python pour interactions avec la base de données
- **psycopg3** : Driver PostgreSQL
- **FastAPI** : API REST
- **Leaflet.js** : Cartographie interactive

## 🚀 Installation rapide

### Prérequis
- Docker et Docker Compose installés
- Au moins 4 GB de RAM disponibles

### Structure des dossiers

```
noise-map/
├── docker-compose.yml
├── init-db.sql
├── producer/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── producer.py
├── processor/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── processor.py
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
└── frontend/
    ├── Dockerfile
    ├── index.html
    └── app.js
```

### Démarrage

1. **Cloner ou créer la structure de dossiers** avec tous les fichiers fournis

2. **Lancer l'infrastructure** :
```bash
docker-compose up -d
```

3. **Vérifier que tout fonctionne** :
```bash
# Logs du producer (données OpenSky)
docker logs -f aircraft-producer

# Logs du processor (calcul du bruit)
docker logs -f noise-processor

# Logs de l'API
docker logs -f noise-api
```

4. **Accèder à l'application** :
- Frontend : http://localhost:3000
- API : http://localhost:8000
- Documentation API : http://localhost:8000/docs

## 🛠️ Services

### Kafka (port 9092)
Gère le flux de données en temps réel des positions d'avions.

### TimescaleDB (port 5432)
Base de données optimisée pour les séries temporelles avec SQLAlchemy ORM.
- User: `noiseuser`
- Password: `noisepass`
- Database: `noise_map`
- Driver: `psycopg` (version 3)

### Producer
Récupère les données OpenSky toutes les 30 secondes pour la zone France et les envoie à Kafka.

### Processor
Consomme les données Kafka, calcule les niveaux de bruit et stocke dans TimescaleDB.

### API FastAPI
Expose les données via REST API.

### Frontend
Interface web avec carte interactive Leaflet.

## 📊 Endpoints API

- `GET /api/noise/current` - Niveaux de bruit actuels
- `GET /api/aircraft/current` - Positions actuelles des avions
- `GET /api/noise/history?grid_id=XX` - Historique d'une zone
- `GET /api/stats` - Statistiques globales

## 🎨 Fonctionnalités

- ✈️ Visualisation en temps réel des avions au-dessus de la France
- 🔊 Carte thermique du bruit avec code couleur
- 📈 Statistiques en direct (nombre d'avions, bruit moyen/max)
- 🕐 Mise à jour automatique toutes les 10 secondes
- 🗺️ Carte interactive (zoom, déplacement)
- 📍 Informations détaillées au clic (popup)

## 🔧 Configuration avancée

### Modifier l'intervalle de mise à jour OpenSky

Dans `docker-compose.yml`, section `aircraft-producer` :
```yaml
environment:
  OPENSKY_UPDATE_INTERVAL: 30  # secondes
```

### Changer la zone géographique

Par défaut, la France métropolitaine. Pour modifier, édite `FRANCE_BBOX` :
```yaml
# Format: lon_min,lat_min,lon_max,lat_max
FRANCE_BBOX: "-5.0,41.0,10.0,51.5"
```

### Ajuster la taille de la grille de bruit

Dans `processor/processor.py` :
```python
GRID_SIZE = 0.1  # 0.1° ≈ 10km
```

## 📦 Volumes Docker

Les données sont persistées dans des volumes Docker :
- `zookeeper-data` : Données Zookeeper
- `kafka-data` : Données Kafka
- `timescale-data` : Données TimescaleDB

Pour tout réinitialiser :
```bash
docker-compose down -v
```

## 🐛 Dépannage

### Les données ne s'affichent pas

1. Vérifier que tous les conteneurs sont up :
```bash
docker-compose ps
```

2. Vérifier les logs du producer :
```bash
docker logs aircraft-producer
```

Le résultat devrait être : `✈️ XX avions détectés au-dessus de la France`

3. Vérifier la base de données :
```bash
docker exec -it timescaledb psql -U noiseuser -d noise_map
SELECT COUNT(*) FROM aircraft_positions;
```

### Erreur de connexion Kafka

Kafka prend 30-40 secondes à démarrer. Attendre un peu puis :
```bash
docker-compose restart aircraft-producer noise-processor
```

### Erreur CORS dans le navigateur

Si vous accédez au frontend depuis un autre domaine que localhost, modifier le CORS dans `api/main.py`.

## 📈 Évolutions possibles

- [ ] Intégrer les capteurs de bruit réels des villes
- [ ] Prédiction des niveaux de bruit (ML)
- [ ] Historique long terme et analyses
- [ ] Alertes sur zones dépassant un seuil
- [ ] Support multi-pays
- [ ] Mode nuit/jour avec variation du bruit
- [ ] Export des données (CSV, PDF)

## 📝 Limites actuelles

- OpenSky Network API gratuite : limitée à 400 requêtes/jour (avec compte) ou 100/jour (anonyme)
- Le calcul du bruit est une estimation simplifiée
- Grille fixe de 10km (pourrait être dynamique selon le zoom)

## 🤝 Contribution

N'hésitez pas à améliorer ce projet ! Quelques idées :
- Optimiser l'algorithme de calcul du bruit
- Ajouter d'autres sources de données
- Améliorer l'UI/UX
- Ajouter des tests unitaires

## 📄 Licence

Projet à usage éducatif et personnel.

---

Créé avec ❤️ pour visualiser le bruit en temps réel