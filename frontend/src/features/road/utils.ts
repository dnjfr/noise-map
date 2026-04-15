import type { RoadsSegment } from '../../hooks/useRoadsData'
import { CORRIDOR_MAX_HALF_WIDTH_PX, CORRIDOR_REF_DIST_M, ROAD_DB_LEVEL_COLOR_STOPS } from './constants'

export function hexToRgb(hex: string): [number, number, number] {
  const hexValue = parseInt(hex.slice(1), 16)
  return [(hexValue >> 16) & 255, (hexValue >> 8) & 255, hexValue & 255]
}

export function interpolateColor(hexA: string, hexB: string, t: number): string {
  const [r0, g0, b0] = hexToRgb(hexA)
  const [r1, g1, b1] = hexToRgb(hexB)
  const r = Math.round(r0 + t * (r1 - r0))
  const g = Math.round(g0 + t * (g1 - g0))
  const b = Math.round(b0 + t * (b1 - b0))
  return `#${[r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')}`
}

/**
 * Calcule la demi-largeur en pixels du corridor de bruit d'un segment routier.
 * Propagation sphérique depuis CORRIDOR_REF_DIST_M (25m) : 20×log₁₀(dist/25).
 * Plafonnée à CORRIDOR_MAX_HALF_WIDTH_PX pour éviter des corridors démesurés aux bas zooms.
 * @param noise_db - Niveau de bruit du segment en dB(A)
 * @param metersPerPixel - Échelle courante de la carte (mètres par pixel CSS)
 * @returns Demi-largeur du corridor en pixels CSS
 */
export function calcCorridorHalfWidthPx(noise_db: number, metersPerPixel: number): number {
  const halfWidthM = CORRIDOR_REF_DIST_M * Math.pow(10, (noise_db - 51) / 20)
  return Math.min(CORRIDOR_MAX_HALF_WIDTH_PX, halfWidthM / metersPerPixel)
}

/** Convertit roadData en GeoJSON FeatureCollection pour les layers MapLibre.
 * corridor_width_m = diamètre physique du corridor de bruit (source linéaire, -3dB/doublement). */
export function getRoadGeoJSON(roadData: RoadsSegment[]) {
  if (roadData.length === 0) return null
  return {
    type: 'FeatureCollection' as const,
    features: roadData.map(seg => ({
      type: 'Feature' as const,
      properties: {
        noise_db: seg.noise_db,
        corridor_width_m: Math.min(50 * Math.pow(10, (seg.noise_db - 51) / 10), 3000),
      },
      geometry: {
        type: 'LineString' as const,
        coordinates: seg.geom_osm
          ? seg.geom_osm.map(([lat, lon]: [number, number]) => [lon, lat])
          : [[seg.lon_deb, seg.lat_deb], [seg.lon_fin, seg.lat_fin]]
      }
    }))
  }
}

export function getRoadColor(noise_db: number): string {
  const stops = ROAD_DB_LEVEL_COLOR_STOPS
  if (noise_db <= stops[0][0]) return stops[0][1]
  if (noise_db >= stops[stops.length - 1][0]) return stops[stops.length - 1][1]
  for (let i = 0; i < stops.length - 1; i++) {
    const [db0, hex0] = stops[i]
    const [db1, hex1] = stops[i + 1]
    if (noise_db >= db0 && noise_db <= db1) {
      const t = (noise_db - db0) / (db1 - db0)
      const [r0, g0, b0] = hexToRgb(hex0)
      const [r1, g1, b1] = hexToRgb(hex1)
      const r = Math.round(r0 + t * (r1 - r0))
      const g = Math.round(g0 + t * (g1 - g0))
      const b = Math.round(b0 + t * (b1 - b0))
      return `#${[r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')}`
    }
  }
  return stops[stops.length - 1][1]
}
