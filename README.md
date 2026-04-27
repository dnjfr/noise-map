# 🗺️ Carte du bruit en France - Données semi temps réel

Visualisation en quasi temps réel des niveaux de bruit aérien, routier et ferroviaire au-dessus de la France, via Kafka, TimescaleDB et plusieurs sources de données publiques.

## 📋 Idée d'origine

Le bruit est un fléau qui génère stress et fatigue. Mais se rend t'on vraiment compte du bruit qui nous entoure ?

Les cartes de bruit existantes reposent sur des modèles de propagation acoustique (NMPB, CNOSSOS-EU), alimentés par des données très précises (trafic, géométrie, topographie). Ce sont des snapshots statiques, basés sur des comptages périodiques. À ma connaissance, il n'existe pas de carte en temps réel - c'est de là qu'est né ce projet.

## 🌐 Démonstration

https://www.cartedubruit.com

## 📐 Architecture

<p align="center">
<img width="1000" src="/git-img/architecture/architecture.png"/>
</p>

Trois flux parallèles :
- **Aérien** (`aircraft-producer` / `aircraft-processor`) : positions ADS-B via adsb.one, calcul bruit en grille 0.1°
- **Routier** (`road-producer` / `road-processor`) : trafic TomTom par segments autoroutiers, calcul bruit routier
- **Ferroviaire** (`railway-producer` / `railway-processor`) : positions GTFS-RT SNCF, calcul bruit ferroviaire

**Stack technique** :
- **Kafka** (Confluent 7.5) : broker de streaming temps réel
- **TimescaleDB** : PostgreSQL optimisé séries temporelles
- **FastAPI** : API REST avec cache TTL in-process
- **Vite + Leaflet.js** : frontend cartographique interactif
- **pfaedle** : association des tracés géographiques aux trips ferroviaires (GTFS)

## 🚀 Installation

### Prérequis

- Docker et Docker Compose installés
- `make`, `xz` et `unzip` disponibles
- Au moins 6 Go de RAM disponibles
- Clés API : [MapTiler](https://www.maptiler.com/) et [TomTom](https://developer.tomtom.com/)

### Configurer MapTiler

Le frontend utilise [MapTiler](https://www.maptiler.com/) pour afficher le fond de carte. Les cartes custom sont liées à la clé API de leur créateur et ne peuvent être exportées sans un compte payant; chaque utilisateur doit créer sa propre carte et coller l'URL dans son `.env`.

#### Procédure complète pour créer une carte Maptiler
<details>
<summary>Afficher ⬇️</summary>
<br>

**1.** Créez votre compte Maptiler
<img width="1000" src="/git-img/maptiler/01-creation-compte.png"/>


**2.** Une fois votre compte créé, cliquez sur `NEW MAP`
<img width="1000" src="/git-img/maptiler/02-new-map.png"/>


**3.** Choisissez la carte que vous souhaitez utiliser
<img width="1000" src="/git-img/maptiler/03-map-selection.png"/>


**4a.** Une fois la carte choisie, cliquez sur `USE THIS MAP`, la carte est prête à être utilisée, passez à l'étape **8.**
<img width="1000" src="/git-img/maptiler/04-map-winter-light.png"/>


**4b.** Vous souhaitez peut être customiser la carte que vous souhaitez utiliser, par exemple ici, on veut utiliser la version sombre de la carte et changer les couleurs de fond, cliquez sur `CUSTOMIZE`
<img width="1000" src="/git-img/maptiler/05-map-winter-dark.png"/>


**5.** Changez les couleurs à votre gout puis cliquez sur `Save`
<img width="1000" src="/git-img/maptiler/06-modifier-couleurs.png"/>


**6.** Une nouvelle popup apparait, cliquez sur `Create and save`
<img width="1000" src="/git-img/maptiler/07-create-save.png"/>


**7.** A la différence d'une carte prête à l'emploi, vous devez également la rendre disponible dans votre application, cliquez sur `Publish`
<img width="1000" src="/git-img/maptiler/08-publish.png"/>


**8.** Votre carte est prête à être utilisée
<img width="1000" src="/git-img/maptiler/09-url.png"/>


</details>

Une fois votre carte créée, copiez l'URL du style dans votre `.env`.

Vous avez plusieurs possibilités :
- Utiliser une carte par défaut (claire ou sombre)
- Utiliser deux cartes (par exemple une carte sombre par défaut qui sera renseignée dans la variable `VITE_MAPTILER_DEFAULT_MAP` et une carte claire qu'il faudra renseigner dans la variable `VITE_MAPTILER_LIGHT_MAP`)
- Utiliser trois cartes (une grise qui sera la carte par défaut, une carte claire et une carte sombre)

Si vous n'utilisez qu'une ou deux cartes, vous pouvez supprimer ou laisser à vide la ou les variables non utilisées.

```dotenv
# Obligatoire - seule carte nécessaire pour que le frontend s'affiche
VITE_MAPTILER_DEFAULT_MAP=https://api.maptiler.com/maps/<your_map_id>/style.json?key=<your_api_key>

# Optionnel - si renseignées, un sélecteur de style apparaît sur la carte
# (2 cartes = 2 boutons, 3 cartes = 3 boutons)
VITE_MAPTILER_LIGHT_MAP=https://api.maptiler.com/maps/<your_light_map_id>/style.json?key=<your_api_key>
VITE_MAPTILER_DARK_MAP=https://api.maptiler.com/maps/<your_dark_map_id>/style.json?key=<your_api_key>
```

### Structure des dossiers

<details>
<summary>Afficher ⬇️</summary>
<br>

```
noise-map/
├── api/
│   ├── Dockerfile
│   ├── main.py                  # FastAPI - endpoints REST
│   └── requirements.txt
├── database-init/
│   ├── db-backup/
│   │   └── noise_map_YYYYMMDD.sql.gz   # Dump tables de référence statiques
│   ├── gtfs-statique/           # Fichiers GTFS SNCF (stops, routes, shapes…)
│   ├── shapes-import/
│   │   └── shapes.tar.xz        # Tracés ferroviaires générés par pfaedle
│   ├── db-init.sh               # Script d'initialisation complet
│   └── db-init.sql              # Schéma PostgreSQL
├── frontend/
│   ├── src/
│   │   ├── components/          # Composants React
│   │   ├── features/            # Logique métier par domaine
│   │   ├── hooks/               # Hooks React personnalisés
│   │   ├── lib/                 # Utilitaires
│   │   └── App.tsx
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   └── package.json
├── gtfs-updater/
│   ├── Dockerfile
│   ├── import-gtfs.py           # Import GTFS SNCF → rail_trips, rail_stop_times
│   ├── assign-shapes.py         # Matching géométrique trips → rail_shapes
│   ├── updater.py               # Scheduler quotidien (18h)
│   └── requirements.txt
├── processors/
│   ├── aircraft-processor/
│   │   ├── aircraft-processor.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── railway-processor/
│   │   ├── railway-processor.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── road-processor/
│       ├── road-processor.py
│       ├── Dockerfile
│       └── requirements.txt
├── producers/
│   ├── aircraft-producer/
│   │   ├── aircraft-producer.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── railway-producer/
│   │   ├── railway-producer.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── road-producer/
│       ├── road-producer.py
│       ├── Dockerfile
│       └── requirements.txt
├── data/
│   └── timescaledb/             # Données PostgreSQL persistées (hors git)
├── .env_example
├── docker-compose.yml
├── Makefile
└── README.md
```

</details>


### Démarrage

1. **Cloner le dépôt** et faire `cd noise-map`

2. **Créer le fichier `.env`** à partir du fichier exemple et renseigner votre clé API TomTom et la ou les carte(s) générée(s) via MapTiler :
```bash
cp .env_example .env
```

3. **Initialiser la base de données** (une seule fois, sur nouvelle machine) :
```bash
make db-init
```
Cette commande enchaîne automatiquement :
- Démarrage de TimescaleDB et création du schéma (`db-init.sql`)
- Restauration des données de référence statiques (bruit MADB/FAA, segments routiers, arrêts et lignes ferroviaires)
- Import des tracés ferroviaires depuis `shapes.tar.xz` (générés par pfaedle)
- Association des tracés aux trips (`assign-shapes.py`)
- Téléchargement du GTFS SNCF et import des horaires trains du jour

4. **Lancer l'infrastructure** :
```bash
make start
```

5. **Vérifier que tout fonctionne** :
```bash
make status

# Logs par service
make logs-aircraft-producer
make logs-railway-producer
make logs-road-producer
make logs-api
```

6. **Accéder à l'application en local** :
   - Frontend : http://localhost:3000
   - API : http://localhost:8000
   - Documentation API : http://localhost:8000/docs

## 🛠️ Services Docker

| Conteneur | Port hôte | Rôle |
|---|---|---|
| `zookeeper` | 2181 | Coordination Kafka |
| `kafka` | 9092 | Broker de streaming |
| `timescaledb` | 5433 | PostgreSQL + TimescaleDB |
| `noise-api` | 8000 | API REST FastAPI |
| `noise-frontend` | 3000 | Frontend Vite/Leaflet (nginx) |
| `aircraft-producer` | - | Positions ADS-B → Kafka |
| `aircraft-processor` | - | Kafka → bruit aérien → DB |
| `road-producer` | - | Trafic TomTom → Kafka |
| `road-processor` | - | Kafka → bruit routier → DB |
| `railway-producer` | - | GTFS-RT SNCF → Kafka |
| `railway-processor` | - | Kafka → bruit ferroviaire → DB |
| `gtfs-updater` | - | Import GTFS SNCF quotidien à 18h |

> TimescaleDB expose le port **5433** sur l'hôte, mais les conteneurs communiquent entre eux sur le port 5432.

## 🗄️ Base de données

### Tables hypertables (séries temporelles, rétention 7 jours)

| Table | Description |
|---|---|
| `aircraft_positions` | Positions brutes des avions |
| `aircraft_noise_levels` | Bruit aérien agrégé par cellule de grille |
| `railway_positions` | Positions des trains |
| `railway_noise_levels` | Bruit ferroviaire par cellule |
| `road_noise_levels` | Bruit routier par segment |

### Tables de référence statiques (importées une seule fois)

| Table | Description |
|---|---|
| `rail_stops` | Arrêts ferroviaires GTFS SNCF |
| `rail_routes` | Lignes ferroviaires GTFS SNCF |
| `rail_shapes` | Tracés géographiques des lignes (~461 Mo, générés par pfaedle) |
| `road_segments_ref` | Géométries OSM des segments autoroutiers |
| `madb_noise_ref` | Référentiel bruit MADB |
| `icao_type_mapping` | Correspondance types avions ICAO |
| `icao_noise_pattern` | Patrons de bruit par type d'avion |

### Tables rechargées quotidiennement

| Table | Description |
|---|---|
| `rail_trips` | Trajets du jour (GTFS SNCF) |
| `rail_stop_times` | Horaires aux arrêts |

## 📊 Endpoints API

| Méthode | Endpoint | Description | Cache |
|---|---|---|---|
| `GET` | `/api/aircrafts/positions` | Avions en vol (fenêtre 2 min) | 5 s |
| `GET` | `/api/roads/segments_noise` | Segments routiers ≥ 67 dB | 15 s |
| `GET` | `/api/railways/positions` | Trains actifs (fenêtre 5 min) | 10 s |
| `GET` | `/api/railways/shapes` | Tracés GTFS des trains actifs (gzip) | 2 min |
| `GET` | `/api/noise/history` | Historique bruit aérien par cellule (`?grid_id=XX`) | - |
| `GET` | `/api/stats` | Statistiques globales des 3 réseaux | - |

Le paramètre `?detail=low\|high` est disponible sur `/api/railways/shapes` pour adapter la résolution des tracés.

## 🎨 Fonctionnalités

- ✈️ Visualisation en temps réel des avions, trains et segments routiers bruyants
- 🔊 Carte thermique du bruit avec code couleur
- 🚆 Tracés des lignes ferroviaires avec correspondance géométrique multi-arrêts
- 📈 Statistiques en direct (nombre de véhicules, bruit moyen/max)
- 🗺️ Carte interactive (zoom, déplacement, popup au clic)
- 🔄 Mise à jour automatique selon les TTL par flux

## 🔧 Configuration avancée

### Zooms OpenStreetMap

Par défaut, le zoom minimum (le plus éloigné) de la carte est à `6` et le zoom maximum est à `10`. Pour les modifier, éditer dans le frontend `Map.txt` et faire un rebuild `make build-frontend` :
```python
MIN_ZOOM = 6
MAX_ZOOM = 10
```

### Fréquence de récupération des données via l'API TomTom
Par défaut, les données sont récupérées sur TomTom toutes les 5 minutes. Pour modifier la fréquence, éditer `POLL_INTERVAL` dans le `road-producer` :
```python
POLL_INTERVAL = 300
```

### Fréquence de récupération des données via GTFS-RT 
Par défaut, les données sont récupérées sur TomTom toutes les 30 secondes sachant que les données sont mises à jour toutes les 2 minutes pour les trains circulant dans les 60 prochaines minutes. Pour modifier la fréquence, éditer `POLL_INTERVAL` dans le `railway-producer` :
```python
POLL_INTERVAL = 30
```

### Logs de performance dans le navigateur

Le frontend affiche dans la console du navigateur des métriques de chargement (temps réseau, taille des réponses, temps de parsing JSON). Ces logs sont utiles pour diagnostiquer des lenteurs ou des problèmes de fetch.

Pour les activer ou les désactiver, modifier le flag `DEBUG_PERF` dans les deux fichiers suivants puis rebuilder le frontend (`make build-frontend`) :

- `frontend/src/hooks/perfLog.ts` — logs des hooks de données (avions, trains, routes, stats)
- `frontend/src/App.tsx` — logs d'ouverture et fermeture de page

```ts
// true  → logs visibles dans la console du navigateur
// false → logs silencés (le code reste en place)
const DEBUG_PERF = true
```

## 📦 Commandes Makefile

```bash
# Démarrage / arrêt
make start              # Lance tous les services
make stop               # Arrête les services
make status             # Statut des conteneurs

# Initialisation (nouvelle machine uniquement)
make db-init            # Schéma + restore + shapes + GTFS

# Rebuild d'un service
make build-api
make build-frontend
make build-aircraft-producer
make build-railway-producer
make build-road-producer

# Logs
make logs-api
make logs-kafka
make logs-aircraft-producer
make logs-railway-producer
make logs-road-producer

# Shell PostgreSQL
make db-shell

# Test rapide de l'API
make test-api

# Backup / restore des tables statiques
make db-backup
make db-restore FILE=noise_map_YYYYMMDD.sql.gz

# Import de données de référence (si reset Kafka)
make import-all         # madb + icao + patterns + refresh vue matérialisée

# Matching géométrique trips → shapes
make assign-shapes
```

## 🐛 Dépannage

### Les données ne s'affichent pas

1. Vérifier que tous les conteneurs sont actifs :
```bash
docker ps
```

2. Vérifier les logs du producer concerné :
```bash
make logs-aircraft-producer
make logs-railway-producer
make logs-road-producer
```

3. Vérifier les logs de Kafka :
```bash
make logs-kafka
```

4. Vérifier les logs de l'API :
```bash
make logs-api
```

5. Interroger directement la base :
```bash
make db-shell
# Puis dans psql :
SELECT COUNT(*) FROM aircraft_positions WHERE time > now() - interval '5 minutes';
SELECT COUNT(*) FROM railway_positions WHERE time > now() - interval '10 minutes';
```

### Kafka ne démarre pas

Kafka prend 30 à 40 secondes à être prêt. Les producers redémarrent automatiquement (`restart: unless-stopped`). En cas de problème persistant :
```bash
docker compose restart kafka
```

### Trains sans tracé sur la carte

Le matching shapes est effectué par `assign-shapes.py` au moment du `db-init`. Pour le relancer manuellement :
```bash
make assign-shapes
```

## 📈 Évolutions possibles

- [ ] Intégrer des capteurs de bruit réels (IoT, Bruitparif)
- [ ] Intégrer la météo
- [ ] Intégrer des données comme les revêtements pour les routes et les types de voies pour les lignes ferroviaires
- [ ] Prédiction des niveaux de bruit (ML)
- [ ] Historique long terme et analyses statistiques
- [ ] Alertes sur zones dépassant un seuil configurable
- [ ] Créer une heatmap des zones les plus bruyantes
- [ ] Support multi-pays
- [ ] Mode nuit/jour avec variation du bruit
- [ ] Export des données (CSV, GeoJSON)

## 📝 Limites actuelles

### Sources de données

- **ADS-B One** : agrégateur communautaire de récepteurs ADS-B, sans limite de requêtes connue, mais la couverture dépend de la densité des récepteurs bénévoles - zones rurales ou en altitude potentiellement sous-représentées.
- **TomTom** : couverture limitée aux tronçons autoroutiers et voies rapides (`motorway` / `trunk`). Les routes secondaires, départementales et urbaines ne sont pas incluses.
- **GTFS-RT SNCF de transport.data.gouv.fr** : données officielles SNCF, mises à jour quotidiennement à 18h. Les perturbations de dernière minute (suppression de train, changement de voie) peuvent ne pas être reflétées immédiatement.

### Modèles de bruit - ce qu'ils font et leurs limites

#### ✈️ Aérien - méthode NPD (ECAC Doc 29 / EASA MAdB)

Le calcul s'appuie sur les données de certification acoustique de la base **EASA MAdB** (Motor Aircraft Data Base), qui fournit pour chaque type ICAO un niveau de référence mesuré à 300 m à 160 nœuds.

La formule appliquée est :

```
L(dBA) = L_ref + ΔL_distance + ΔL_atmosphérique + ΔL_vitesse

ΔL_distance      = -20 · log10(altitude / 300)     - atténuation géométrique sphérique
ΔL_atmosphérique = -0.002 · altitude               - absorption de l'air (si altitude > 500 m)
ΔL_vitesse       =   3 · log10(v / 82 m/s)         - correction selon la vitesse réelle
```

La phase de vol (survol vs approche) est déduite du taux vertical. Pour les types sans données MAdB, un fallback par catégorie ICAO (A1–A5, de 65 à 85 dB de référence) est utilisé.

**Limites** : la distance horizontale entre l'avion et la cellule de grille est ignorée (simplification "avion à la verticale"). Le modèle ne prend pas en compte l'orientation de l'avion, la météo, ni le masquage par le relief.

#### 🚗 Routier - méthode NMPB-Routes-2008 (Sétra 2009)

Méthode normalisée française pour le bruit de trafic routier. Elle distingue deux catégories de véhicules (VL et PL) avec des proportions de poids lourds selon le type de route (10 % sur autoroute, 7 % sur voie rapide).

La puissance acoustique par type de véhicule est calculée en combinant deux termes :

```
L_r  = bruit de roulement  (VL : 55.4 + 20.1·log10(v/90),  PL : 63.4 + 20.0·log10(v/80))
L_m  = bruit moteur        (VL : formule par palier de vitesse, PL : 50.4 + 3·log10(v/80))
L_W  = addition énergétique(L_r, L_m)   - 10·log10(10^(L_r/10) + 10^(L_m/10))
```

La puissance totale de la source linéaire (débit × L_W) est ensuite propagée à 25 m selon un modèle de source cylindrique :

```
L(25m) = L_W/m - 10·log10(2·π·25)
```

**Limites** : propagation en champ libre sans réflexions ni absorption (pas de bâtiments, pas de merlons). La déclivité et le revêtement (supposé R2 standard) sont fixes. Le débit horaire TomTom est une instantanée, pas une moyenne journalière.

#### 🚆 Ferroviaire - méthode CRN/CNOSSOS-EU

Inspirée de la méthode CRN (Calcul de la propagation du bruit des infrastructures ferroviaires) et du cadre européen CNOSSOS, avec des niveaux de référence différenciés par type de train SNCF :

| Type | L_ref (dB) | v_ref (km/h) |
|---|---|---|
| TGV | 92 | 300 |
| IC (Intercités) | 82 | 200 |
| TER | 80 | 140 |
| FRET | 88 | 100 |

```
L(dBA) = L_ref + 30·log10(v / v_ref) + (-10·log10(d / 25))

correction vitesse    = 30·log10(v / v_ref)   - exposant 30 typique rail (vs 20 route)
atténuation distance  = -10·log10(d / 25)     - propagation cylindrique depuis la voie
```

**Limites** : le type de train est extrait du `trip_id` GTFS-RT - les trips non labellisés tombent sur le profil TER par défaut. La vitesse est issue de l'interpolation GTFS, pas d'une mesure réelle. Le modèle ne tient pas compte du type de voie (ballastée vs dalle béton), ni du matériel roulant précis.

## 💡 Cas d'usage

### Immobilier & urbanisme
- Évaluer l'impact sonore avant de lancer un projet de construction
- Identifier les zones à équiper en double vitrage ou murs anti-bruit
- Alimenter les dossiers réglementaires (directive européenne 2002/49/CE)

### Santé publique
- Croiser les zones d'exposition chronique avec des données de santé (hypertension, troubles du sommeil)
- Identifier les populations à risque selon leur localisation

### Transport & mobilité
- Optimiser les couloirs aériens en montrant les trajectoires les plus impactantes
- Prioriser les travaux d'isolation sur les tronçons ferroviaires bruyants la nuit
- Comparer l'impact de déviations routières avant construction

### Qualité de vie & grand public
- Proposer des itinéraires calmes pour le running ou la randonnée
- Recommander des hébergements calmes avec données objectives

### Recherche
- Constituer un dataset long terme pour détecter des couloirs de bruit
- Mesurer l'impact réel des réseaux vs les estimations statiques actuelles

## 📄 Licence

Projet à usage éducatif et personnel.

---

Créé avec ❤️ pour visualiser le bruit en semi temps réel
