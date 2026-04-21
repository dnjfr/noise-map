# 🗺️ Carte du bruit en France - Données semi temps réel

Projet de visualisation en temps réel des niveaux de bruit aérien, routier et ferroviaire au-dessus de la France, utilisant Kafka, TimescaleDB et OpenSky Network.

## 📋 Idée d'origine
Le bruit est un fléau qui génère stress et fatigue. Mais est-ce qu’on se rend vraiment compte du bruit qui nous entoure ?

Les cartes de bruit existantes reposent sur des modèles de propagation acoustique (NMPB, CNOSSOS-EU), alimentés par des données très précises (trafic, géométrie, topographie). Mais ce sont des snapshots statiques, basés sur des comptages périodiques et à ma connaissance, il n’existe pas vraiment de carte en temps réel, c’est de là qu’est né ce projet.

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
- Docker, Docker Compose, XZ et Unzip installés
- Au moins 6 GB de RAM disponibles

### Structure des dossiers

```
noise-map/
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── data/
├── database-init/
│   ├── db-backup/
│   │   └── noise_map_YYYYmmdd.sql.gz
│   ├── shapes-import/
│   │   └── shapes.tar.xz
│   ├── db-init.sh
│   └── db-init.sql
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   └──  app.js
├── gtfs-updater/
│   ├── Dockerfile
│   ├── assign-shapes.py
│   ├── import-gtfs.py
│   └── updater.py
├── processors/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── processor.py
├── producers/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── producer.py
├── .env
├── docker-compose.yml
├── Makefile
└── README.md



```

### Démarrage

1. **Cloner le dépôt**

2. **Créer un fichier `.env`** à partir du fichier exemple et **renseigner vos clés API** `Maptiler` et `TomTom` :
```bash
cp .env_example .env
```

3. **Initialiser la base de données** (une seule fois sur une nouvelle machine) :
```bash
make db-init
```
Cette commande enchaîne automatiquement :
- Démarrage de TimescaleDB
- Création du schéma (`db-init.sql`)
- Restauration des données de référence (avions, ferroviaire hors tracés)
- Décompression de `shapes.tar.xz` et import des tracés ferroviaires
- Téléchargement du GTFS SNCF et import des horaires trains

4. **Lancer l'infrastructure** :
```bash
make start

5. **Vérifier que tout fonctionne** :
```bash
make status

# Logs par service
make logs-aircraft-producer
make logs-api
```

6. **Accéder à l'application** :
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

### GTFS Updater
Met à jour automatiquement les horaires ferroviaires (`rail_trips`, `rail_stop_times`) chaque jour à 18h en téléchargeant le GTFS SNCF. Le plan de transport théorique intègre les adaptations connues la veille à 17h (perturbations, mouvements sociaux).

> Les tracés géographiques (`rail_shapes`) sont statiques et ne sont pas re-téléchargés : ils ont été générés via pfaedle et importés lors de l'initialisation.

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

Par défaut, la France métropolitaine. Pour modifier, éditer `FRANCE_BBOX` :
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

## 🤝 Pistes d'améliorations
- Optimiser l'algorithme de calcul du bruit
- Améliorer le calcul de la propagation du bruit en tenant compte de la météo, du vent, des aménagements déjà mis en place, etc...
- Obtenir des données plus précises via des API payantes ou des données non publiques
- Ajouter d'autres sources de données comme les travaux
- Améliorer l'UI/UX
- Réduire le délai d'obtention des données pour un affichage quasi temps réel
- Ajouter des tests unitaires


## Exemples d'utilisation de la carte
Que faire des données ? Rien n'empêche de créer un dataset de toutes les données enregistrées sur une assez longue période pour créer ensuite des couloirs de bruits et identifier les zones les plus exogènes

### Immobilier & urbanisme
  - Promoteurs immobiliers : évaluer l'impact sonore avant de lancer un projet de construction
  - Collectivités locales : identifier les zones à équiper en double vitrage, murs anti-bruit, ouvégétalisation 
  - PLU / études d'impact : alimenter les dossiers réglementaires (la directive européenne 2002/49/CE impose déjà des cartes de bruit qui semblent être des snapshots statiques basés sur des comptages périodiques)

### Santé publique 
  - Épidémiologie : croiser les zones d'exposition chronique avec des données de santé (hypertension, troubles du sommeil), ce qui est un sujet de recherche actif à l'OMS
  - Médecins / mutuelles : identifier les populations à risque selon leur adresse
  - Maternités / pédiatres : exposition au bruit des nourrissons et enfants
  - Etablissements de soins / maisons de retraite : identifier les zons d'exposition au bruit

### Transport & mobilité
  - Optimisation des couloirs aériens : montrer à la DGAC ou aux aéroports quelles trajectoires sont les plus impactantes sur les zones habitées   
  - Horaires ferroviaires : identifier les tronçons bruyants la nuit pour prioriser les travaux d'isolation
  - Planification routière : comparer l'impact de déviations ou de nouvelles infrastructures avant construction

### Qualité de vie & usage grand public  
  - Applications de running / randonnée : proposer des itinéraires calmes
  - Parents : trouver des parcs ou zones de jeux loin du bruit
  - Tourisme : recommander des hébergements calmes avec données objectives plutôt que subjectives  

### Entreprises & RH
  - Choix d'implantation d'entreprise : bureaux dans des zones calmes pour le bien-être des salariés 

### Recherche & institutionnel
  - SNCF / RATP : mesurer l'impact réel de leurs réseaux vs les estimations statiques actuelles
  - Aéroports de Paris : suivi en temps réel des engagements de réduction du bruit 
  - Chercheurs en acoustique urbaine : dataset sur le long terme pour détecter des couloirs de bruits

## 📄 Licence

Projet à usage éducatif et personnel.

---

Créé avec ❤️ pour visualiser le bruit en semi temps réel