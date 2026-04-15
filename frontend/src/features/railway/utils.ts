import type { Train } from '../../hooks/useRailwaysData'
import { DEFAULT_RAILWAY_NOISE_REF, RAILWAY_NOISE_REF } from './constants'

/** Extrait le type de service depuis le trip_id SNCF (ex: "TER", "TGV", "IC") */
function extractServiceType(tripId: string): string {
  const m = tripId.match(/_[FR]:([A-Z]+):/)
  return m ? m[1] : ''
}

/** Extrait le numéro de train depuis trip_headsign ou le trip_id SNCF */
function getTrainNumber(train: Train): string {
  if (train.trip_headsign) return train.trip_headsign
  if (train.train_number) return train.train_number
  const m = train.trip_id.match(/OCESN(\d+)/)
  return m ? m[1] : train.trip_id.slice(0, 12)
}

/** Retourne L_ref et v_ref pour un train donné */
export function getRailwayNoiseRef(tripId: string): { lRef: number; vRef: number } {
  const svc = extractServiceType(tripId)
  return RAILWAY_NOISE_REF[svc] ?? DEFAULT_RAILWAY_NOISE_REF
}

/** Bruit au sol à une distance d (mètres) — propagation sphérique (20×log₁₀) */
export function calcRailwayGroundNoise(lRef: number, vRef: number, speedKmh: number, distanceM: number): number {
  const speed = Math.max(speedKmh || vRef * 0.5, 10)
  const speedCorrection = 30 * Math.log10(speed / vRef)
  const distAttenuation = -20 * Math.log10(Math.max(distanceM, 1) / 25)
  return lRef + speedCorrection + distAttenuation
}

/** Rayon horizontal (mètres) pour un seuil donné — propagation sphérique (20×log₁₀) */
export function calcRailwayNoiseRadius(lRef: number, vRef: number, speedKmh: number, thresholdDb: number): number {
  const speed = Math.max(speedKmh || vRef * 0.5, 10)
  const noiseAt25m = lRef + 30 * Math.log10(speed / vRef)
  if (noiseAt25m <= thresholdDb) return 0
  return 25 * Math.pow(10, (noiseAt25m - thresholdDb) / 20)
}

/**
 * Génère le contenu HTML de la popup MapLibre pour un train.
 * Affiche : type de service + numéro (ex: "TER 876542"), ligne, arrêts précédent/suivant,
 * vitesse, retard en minutes, et bruit estimé à 25m (omis si train à l'arrêt).
 * @param train - Données du train issues de useRailwaysData
 * @returns Chaîne HTML à injecter dans une Popup MapLibre
 */
export function buildRailwayPopupContent(train: Train): string {
  const delay = train.delay_seconds
  const delayStr = delay > 0 ? `+${Math.round(delay / 60)} min` : 'à l\'heure'
  const speed = train.speed_kmh ? `${Math.round(train.speed_kmh)} km/h` : 'À l\'arrêt'
  const serviceType = extractServiceType(train.trip_id)
  const trainNumber = getTrainNumber(train)
  const title = [serviceType, trainNumber].filter(Boolean).join(' ')

  const { lRef, vRef } = getRailwayNoiseRef(train.trip_id)
  const groundNoise = train.speed_kmh && train.speed_kmh > 0
    ? calcRailwayGroundNoise(lRef, vRef, train.speed_kmh, 25).toFixed(0)
    : null

  return `
    <div style="font-size:12px;line-height:1.6;min-width:180px">
      <div style="font-weight:700;font-size:14px;margin-bottom:6px">
        🚆 ${title}
      </div>
      ${train.route_long_name ? `<div style="color:#94a3b8;font-size:11px;margin-bottom:4px">${train.route_long_name}</div>` : ''}
      ${train.prev_stop_name ? `<div>◀ <em>${train.prev_stop_name}</em></div>` : ''}
      ${train.next_stop_name ? `<div>▶ <strong>${train.next_stop_name}</strong></div>` : ''}
      <div style="margin-top:4px">Vitesse : ${speed}</div>
      <div>Retard : ${delayStr}</div>
      ${groundNoise ? `<div><strong>Bruit estimé :</strong> ${groundNoise} dB (à 25m)</div>` : ''}
    </div>
  `
}
