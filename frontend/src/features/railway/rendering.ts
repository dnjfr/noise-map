import type { MapRef } from 'react-map-gl/maplibre'
import type { Train } from '../../hooks/useRailwayData'
import { DB_LEVEL_COLOR_STOPS } from '../aircraft/constants'
import { hexToRgb, interpolateColor } from '../aircraft/utils'
import { getRailwayNoiseRef, calcRailwayGroundNoise, calcRailwayNoiseRadius } from './utils'

const LAT_REF = 46.6

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

    // Rayon extérieur (51 dB, minimum 500m)
    let outerRadiusM = calcRailwayNoiseRadius(lRef, vRef, speedKmh, DB_LEVEL_COLOR_STOPS[0][0])
    outerRadiusM = Math.max(outerRadiusM, 500)
    const outerRadiusPx = outerRadiusM / metersPerPixel

    // Rayon intérieur (80 dB)
    const innerRadiusM = calcRailwayNoiseRadius(lRef, vRef, speedKmh, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0])
    const innerRadiusPx = Math.max(0, innerRadiusM / metersPerPixel)

    if (outerRadiusPx < 2) continue

    const grad = ctx.createRadialGradient(px, py, innerRadiusPx, px, py, outerRadiusPx)

    // Centre : couleur basée sur le bruit réel au sol
    const centerColor = interpolateColor(Math.min(groundNoise, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0]))
    const [cr, cg, cb] = hexToRgb(centerColor)
    grad.addColorStop(0, `rgba(${cr},${cg},${cb},0.55)`)

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
