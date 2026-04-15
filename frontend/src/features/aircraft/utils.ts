import type { Aircraft } from '../../hooks/useAircraftsData'
import { DB_LEVEL_COLOR_STOPS, NOISE_REFERENCE_DB_BY_CATEGORY } from './constants'

/**
 * Retourne le niveau de bruit de référence Lref en dB(A) pour une catégorie d'avion ICAO.
 * @param category - Catégorie ICAO (A1 à A5) ou null
 * @returns Niveau de bruit de référence en dB(A). Fallback 80 dB si catégorie inconnue
 */
export function getNoiseReferenceDb(category: string | null): number {
  return category ? (NOISE_REFERENCE_DB_BY_CATEGORY[category] ?? 80) : 80
}

/**
 * Calcule le niveau de bruit perçu au sol (dB(A)) depuis un avion à une altitude donnée.
 * @param noiseReferenceDb - Niveau de bruit de référence Lref en dB(A)
 * @param altitudeMeters - Altitude de l'avion en mètres
 * @returns Niveau de bruit au sol en dB(A). Formule : atténuation -20*log10(alt/300). Minimum 50m d'altitude
 */
export function calcGroundNoise(noiseReferenceDb: number, altitudeMeters: number): number {
  if (altitudeMeters <= 0) return noiseReferenceDb
  return noiseReferenceDb - 20 * Math.log10(Math.max(altitudeMeters, 50) / 300)
}

/**
 * Calcule le rayon horizontal en mètres à partir duquel le bruit descend sous un seuil donné.
 * @param noiseReferenceDb - Niveau de bruit de référence Lref en dB(A)
 * @param thresholdDb - Seuil de bruit en dB(A)
 * @param altitudeMeters - Altitude de l'avion en mètres
 * @returns Rayon horizontal en mètres, ou null si l'altitude est supérieure à la distance slant maximale
 */
export function calcNoiseRadius(noiseReferenceDb: number, thresholdDb: number, altitudeMeters: number): number | null {
  const slant = 300 * Math.pow(10, (noiseReferenceDb - thresholdDb) / 20)
  if (altitudeMeters >= slant) return null
  return Math.sqrt(slant * slant - altitudeMeters * altitudeMeters)
}

/**
 * Convertit une couleur hexadécimale en tuple RGB.
 * @param hex - Couleur en format hexadécimal (#RRGGBB)
 * @returns Tuple [R, G, B] avec valeurs 0-255
 */
export function hexToRgb(hex: string): [number, number, number] {
  const hexValue = parseInt(hex.slice(1), 16)
  return [(hexValue >> 16) & 255, (hexValue >> 8) & 255, hexValue & 255]
}

/**
 * Interpole une couleur CSS entre les stops de DB_LEVEL_COLOR_STOPS en fonction du niveau de bruit.
 * @param dbLevel - Niveau de bruit en dB(A)
 * @returns Couleur au format hexadécimal (#RRGGBB)
 */
export function interpolateColor(dbLevel: number): string {
  const stops = DB_LEVEL_COLOR_STOPS
  if (dbLevel <= stops[0][0]) return stops[0][1]
  if (dbLevel >= stops[stops.length - 1][0]) return stops[stops.length - 1][1]
  for (let i = 0; i < stops.length - 1; i++) {
    const [dbLevel0, hexColor0] = stops[i]
    const [dbLevel1, hexColor1] = stops[i + 1]
    if (dbLevel >= dbLevel0 && dbLevel <= dbLevel1) {
      const interpolationFactor = (dbLevel - dbLevel0) / (dbLevel1 - dbLevel0)
      const [red0, green0, blue0] = hexToRgb(hexColor0)
      const [red1, green1, blue1] = hexToRgb(hexColor1)
      const red = Math.round(red0 + interpolationFactor * (red1 - red0))
      const green = Math.round(green0 + interpolationFactor * (green1 - green0))
      const blue = Math.round(blue0 + interpolationFactor * (blue1 - blue0))
      return `#${[red, green, blue].map(v => v.toString(16).padStart(2, '0')).join('')}`
    }
  }
  return stops[stops.length - 1][1]
}

/**
 * Génère un SVG inline représentant la silhouette d'un avion.
 * @param size - Taille du SVG en pixels (width et height)
 * @returns String SVG de la silhouette d'avion
 */
export function getAircraftSvg(size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24">
  <rect x="10.5" y="2" width="3" height="16" rx="1.5" fill="#60a5fa"/>
  <polygon points="12,8 3,14 21,14" fill="#60a5fa"/>
  <polygon points="12,18 8,22 16,22" fill="#60a5fa"/>
</svg>`
}

/**
 * Génère le contenu HTML d'une popup d'info pour un avion.
 * @param aircraft - Données de l'avion (callsign, altitude, vitesse, ICAO, catégorie)
 * @returns String HTML contenant callsign, altitude, vitesse, bruit estimé, ICAO
 */
export function buildPopupContent(aircraft: Aircraft): string {
  const noiseReferenceDb = getNoiseReferenceDb(aircraft.aircraft_category)
  const altitudeMeters = aircraft.altitude
  const groundNoise = altitudeMeters && altitudeMeters > 0 ? calcGroundNoise(noiseReferenceDb, altitudeMeters).toFixed(0) : null
  return `
    <strong>${aircraft.callsign || aircraft.icao24}</strong><br />
    ${aircraft.aircraft_desc ? `<em style="color:#aaa">${aircraft.aircraft_desc}</em><br />` : ''}
    <strong>Altitude :</strong> ${altitudeMeters ? (altitudeMeters / 1000).toFixed(1) : 'N/A'} km<br />
    <strong>Vitesse :</strong> ${aircraft.velocity ? `${(aircraft.velocity * 3.6).toFixed(0)} km/h` : 'À l\'arrêt'}<br />
    ${groundNoise ? `<strong>Bruit estimé :</strong> ${groundNoise} dB<br />` : ''}
    <strong>ICAO24 :</strong> ${aircraft.icao24}
  `
}
