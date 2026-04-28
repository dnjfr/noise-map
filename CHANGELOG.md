
# Changelog

## [v1.2.4] - 2026-04-28
- Correction des CORS dans le fichier Nginx
- Modification de la gestion de mots de passe complexes dans l'API, les producers et les processeurs
- Modification de la zone aérienne pour couvrir la même zone en moins de requêtes
- Refonte de la légende
- Modification de l'architecture pour prendre en compte le nouveau découpage aérien
- Modification du READMME.md

## [v1.2.3] - 2026-04-27
- Correction Docker Compose 
- Amélioration du requirements.txt de l'API

## [v1.2.2] - 2026-04-27
- Modification API sur les cors 
- Modification Nginx

## [v1.2.1] - 2026-04-27
- Modification du README et de .gitignore

## [v1.2.0] - 2026-04-27
- Revue de code 
- Corrections de bugs et refactoring

## [v1.1.17] - 2026-04-24
- Enrichissement de certains shapes manquants à partir du fichier RFN
- Modification de l'emplacement du dossier provisoire gtfs-statique
- Modification de l'affichage des stats
- Réorganisation du Makefile
- Mise à jour du README.md

## [v1.1.16] - 2026-04-23
- Correction d'une dette technique sur les stats 
- Amélioration de la gestion des hypertables 
- Simplification du code SQL 
- Mise à jour de l'architecture du projet 
- Régénération des shapes avec pfaedle
- Optimisation mémoire sur l'assignation des shapes et sur l'API
- Mise à jour du README.md

## [v1.1.15] - 2026-04-22
- Mise à jour de l'architecture du projet

## [v1.1.14] - 2026-04-22
- Mise à jour de l'architecture du projet


## [v1.1.13] - 2026-04-21
- Modification des maps Maptiler dans le front
- Ajout d'un tutorial Maptiler dans le README.md 
- Correction des tracés de chemin de fer dans l'API


## [v1.1.12] - 2026-04-21
- Modification de l'utilisation mémoire de Kafka dans Docker Compose 
- Modification du README.md

## [v1.1.11] - 2026-04-21
- Suppression de la classe RoadSegmentRef dans l'API 
- Modification du README.md

## [v1.1.10] - 2026-04-21
- Modification du timer d'attente de démarrage de la base

## [v1.1.9] - 2026-04-21
- Renommage de fichier 
- Modification du README.md

## [v1.1.8] - 2026-04-21
- Refonte des imports GTFS pour associer les tracés de lignes de chemin de fer aux trajets

## [v1.1.7] - 2026-04-20
- Corrections sur l'initialisation de la base

## [v1.1.6] - 2026-04-20
- Uniformisation des variables d'environnement Timescaledb

## [v1.1.5] - 2026-04-20
- Correction de l'initialisation de la base 
- Changement de version Timescaledb

## [v1.1.4] - 2026-04-20
- Amélioration de l'initialisation de la base 
- Ajout de l'update gtfs 
- Optimisation mémoire

## [v1.1.3] - 2026-04-15
- Simplification de l'api 
- Amélioration du frontend 
- Renommage de variables 
- Documentation

## [v1.1.2] - 2026-04-09
- Correction du host dans les hooks 
- Ajout exemple .env 
- Update README.md


## [v1.1.1] - 2026-04-08
- Ajout du README.md 
- Ajout backup et restore db dans Makefile

## [v1.1.0] - 2026-03-24
- Ajout des réseaux routier et ferroviaire


## [v1.0.0] - 2026-03-09
- Initial commit