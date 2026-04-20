#!/usr/bin/env python3
"""Service de mise à jour quotidienne des données GTFS SNCF.

Télécharge le GTFS SNCF chaque jour à 18h et met à jour rail_trips et rail_stop_times.
Le plan de transport théorique intègre les adaptations connues la veille à 17h
(perturbations, mouvements sociaux), d'où la mise à jour à 18h.
"""
import os
import sys
import logging
import tempfile
import urllib.request
import zipfile
import subprocess
import schedule
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [gtfs-updater] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

GTFS_URL = "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
IMPORT_SCRIPT = os.path.join(os.path.dirname(__file__), "import-gtfs.py")


def update_gtfs():
    log.info("Démarrage de la mise à jour GTFS...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "gtfs.zip")

            log.info("Téléchargement depuis %s", GTFS_URL)
            urllib.request.urlretrieve(GTFS_URL, zip_path)

            log.info("Extraction dans %s", tmpdir)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmpdir)

            log.info("Import rail_trips + rail_stop_times...")
            subprocess.run(
                [sys.executable, IMPORT_SCRIPT, "--temporal", "--gtfs-dir", tmpdir],
                check=True,
            )

        log.info("Mise à jour terminée.")
    except Exception as e:
        log.error("Échec de la mise à jour : %s", e)


schedule.every().day.at("18:00").do(update_gtfs)

log.info("Démarré — mise à jour quotidienne programmée à 18h00.")
while True:
    schedule.run_pending()
    time.sleep(60)
