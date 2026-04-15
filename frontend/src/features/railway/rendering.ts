import type { MapRef } from 'react-map-gl/maplibre'
import type { Train } from '../../hooks/useRailwaysData'
import { DB_LEVEL_COLOR_STOPS } from '../aircraft/constants'
import { hexToRgb, interpolateColor } from '../aircraft/utils'
import { calcRailwayGroundNoise, calcRailwayNoiseRadius, getRailwayNoiseRef } from './utils'

const LAT_REF = 46.6

/**
 * Dessine sur un canvas 2D les halos de bruit radial pour chaque train actif.
 * Gradient radial du centre (couleur bruit réel au sol) vers le bord extérieur (transparent).
 * Les stops intermédiaires (60 dB, 70 dB) sont positionnés proportionnellement à leur rayon physique.
 * Le rayon extérieur est calculé au seuil 51 dB avec un minimum de 5000m pour la visibilité aux bas zooms.
 * @param ctx - Contexte canvas 2D
 * @param trainsMap - Map des trains actifs (trip_id → Train)
 * @param posMap - Map des positions interpolées (trip_id → [lat, lng, dist_traveled])
 * @param map - Référence à la carte MapLibre pour la projection géo→pixel
 * @param zoom - Niveau de zoom courant (utilisé pour convertir mètres en pixels)
 */
export function drawRailwayHalos(
  ctx: CanvasRenderingContext2D,
  trainsMap: Map<string, Train>,
  posMap: Map<string, [number, number, number]>,
  map: MapRef,
  zoom: number,
) {
  const pixelRatio = window.devicePixelRatio || 1
  const canvas = ctx.canvas
  const cssW = canvas.offsetWidth
  const cssH = canvas.offsetHeight
  if (cssW > 0 && cssH > 0 && (canvas.width !== cssW * pixelRatio || canvas.height !== cssH * pixelRatio)) {
    canvas.width = cssW * pixelRatio
    canvas.height = cssH * pixelRatio
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.save()
  ctx.scale(pixelRatio, pixelRatio)

  const metersPerPixel = 156543.03 * Math.cos(LAT_REF * Math.PI / 180) / Math.pow(2, zoom)

  for (const train of trainsMap.values()) {
    const pos = posMap.get(train.trip_id)
    if (!pos) continue
    const [lat, lng] = pos

    const { lRef, vRef } = getRailwayNoiseRef(train.trip_id)
    const speedKmh = train.speed_kmh ?? 0

    const groundNoise = calcRailwayGroundNoise(lRef, vRef, speedKmh, 25)
    if (groundNoise <= DB_LEVEL_COLOR_STOPS[0][0]) continue

    const point = map.project([lng, lat])
    const px = point.x
    const py = point.y
    if (!isFinite(px) || !isFinite(py)) continue

    // Rayon extérieur (51 dB, minimum 5000m pour visibilité dès zoom 8)
    // Le rayon physique d'un TER à 100km/h est ~425m — trop petit aux zooms France/région
    let outerRadiusM = calcRailwayNoiseRadius(lRef, vRef, speedKmh, DB_LEVEL_COLOR_STOPS[0][0])
    outerRadiusM = Math.max(outerRadiusM, 5000)
    const outerRadiusPx = outerRadiusM / metersPerPixel

    // Rayon intérieur (80 dB)
    const innerRadiusM = calcRailwayNoiseRadius(lRef, vRef, speedKmh, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0])
    const innerRadiusPx = Math.max(0, innerRadiusM / metersPerPixel)

    if (outerRadiusPx < 2) continue

    const grad = ctx.createRadialGradient(px, py, innerRadiusPx, px, py, outerRadiusPx)

    // Centre : couleur basée sur le bruit réel au sol
    const centerColor = interpolateColor(Math.min(groundNoise, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0]))
    const [cr, cg, cb] = hexToRgb(centerColor)
    grad.addColorStop(0, `rgba(${cr},${cg},${cb},0.7)`)

    // Stops intermédiaires (70 dB, 60 dB)
    for (let i = DB_LEVEL_COLOR_STOPS.length - 2; i >= 1; i--) {
      const [thresholdDb, stopHex] = DB_LEVEL_COLOR_STOPS[i]
      const radiusM = calcRailwayNoiseRadius(lRef, vRef, speedKmh, thresholdDb)
      if (radiusM <= 0) continue
      const t = (radiusM / metersPerPixel - innerRadiusPx) / (outerRadiusPx - innerRadiusPx)
      if (t <= 0 || t >= 1) continue
      const [sr, sg, sb] = hexToRgb(stopHex)
      grad.addColorStop(t, `rgba(${sr},${sg},${sb},0.4)`)
    }

    // Bord extérieur transparent
    const [er, eg, eb] = hexToRgb(DB_LEVEL_COLOR_STOPS[0][1])
    grad.addColorStop(1, `rgba(${er},${eg},${eb},0)`)

    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(px, py, outerRadiusPx, 0, 2 * Math.PI)
    ctx.fill()
  }

  ctx.restore()
}
