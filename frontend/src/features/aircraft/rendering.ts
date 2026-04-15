import type { MapRef } from 'react-map-gl/maplibre'
import type { Aircraft } from '../../hooks/useAircraftsData'
import { DB_LEVEL_COLOR_STOPS } from './constants'
import { calcGroundNoise, calcNoiseRadius, getNoiseReferenceDb, hexToRgb, interpolateColor } from './utils'

const LAT_REF = 46.6

/**
 * Dessine sur un canvas 2D les halos de bruit radial pour chaque avion.
 * @param canvasContext - Contexte canvas 2D pour le dessin
 * @param aircraftList - Liste des avions à afficher
 * @param posMap - Map des positions actuelles (icao24 -> [lat, lng])
 * @param map - Référence à la carte MapGL pour la projection
 * @param zoom - Niveau de zoom courant
 */
export function drawHalos(
  canvasContext: CanvasRenderingContext2D,
  aircraftMap: Map<string, Aircraft>,
  posMap: Map<string, [number, number]>,
  map: MapRef,
  zoom: number,
) {
  const pixelRatio = window.devicePixelRatio || 1
  const canvas = canvasContext.canvas
  // Auto-resize : synchronise le buffer avec la taille CSS réelle
  const canvasCssWidth = canvas.offsetWidth
  const canvasCssHeight = canvas.offsetHeight
  if (canvasCssWidth > 0 && canvasCssHeight > 0 && (canvas.width !== canvasCssWidth * pixelRatio || canvas.height !== canvasCssHeight * pixelRatio)) {
    canvas.width = canvasCssWidth * pixelRatio
    canvas.height = canvasCssHeight * pixelRatio
  }
  canvasContext.clearRect(0, 0, canvas.width, canvas.height)
  canvasContext.save()
  canvasContext.scale(pixelRatio, pixelRatio)

  const metersPerPixel = 156543.03 * Math.cos(LAT_REF * Math.PI / 180) / Math.pow(2, zoom)

  for (const aircraft of aircraftMap.values()) {
    const pos = posMap.get(aircraft.icao24)
    if (!pos) continue
    const [lat, lng] = pos
    if (!aircraft.velocity || aircraft.velocity === 0) continue

    const noiseReferenceDb = getNoiseReferenceDb(aircraft.aircraft_category)
    const altitudeMeters = aircraft.altitude ?? 1000
    const groundNoise = calcGroundNoise(noiseReferenceDb, altitudeMeters)
    if (groundNoise <= DB_LEVEL_COLOR_STOPS[0][0]) continue

    const point = map.project([lng, lat])
    const pointX = point.x
    const pointY = point.y
    if (!isFinite(pointX) || !isFinite(pointY)) continue

    // Rayon extérieur (51 dB, minimum 500m)
    let outerRadiusMeters = calcNoiseRadius(noiseReferenceDb, DB_LEVEL_COLOR_STOPS[0][0], altitudeMeters)
    outerRadiusMeters = outerRadiusMeters !== null ? Math.max(outerRadiusMeters, 500) : 500
    const outerRadiusPixels = outerRadiusMeters / metersPerPixel

    // Rayon intérieur (80 dB) — 0 si l'avion est trop haut
    const innerRadiusMeters = calcNoiseRadius(noiseReferenceDb, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0], altitudeMeters) ?? 0
    const innerRadiusPixels = Math.max(0, innerRadiusMeters / metersPerPixel)

    if (outerRadiusPixels < 2) continue

    const radialGradient = canvasContext.createRadialGradient(pointX, pointY, innerRadiusPixels, pointX, pointY, outerRadiusPixels)

    // t=0 → centre (couleur basée sur le groundNoise réel), t=1 → bord transparent
    const centerColor = interpolateColor(Math.min(groundNoise, DB_LEVEL_COLOR_STOPS[DB_LEVEL_COLOR_STOPS.length - 1][0]))
    const [centerRed, centerGreen, centerBlue] = hexToRgb(centerColor)
    radialGradient.addColorStop(0, `rgba(${centerRed},${centerGreen},${centerBlue},0.55)`)

    // Stops intermédiaires (70 dB et 60 dB) positionnés proportionnellement
    for (let i = DB_LEVEL_COLOR_STOPS.length - 2; i >= 1; i--) {
      const [thresholdDb, stopHexColor] = DB_LEVEL_COLOR_STOPS[i]
      const radiusMeters = calcNoiseRadius(noiseReferenceDb, thresholdDb, altitudeMeters)
      if (radiusMeters === null) continue
      const gradientStopPosition = (radiusMeters / metersPerPixel - innerRadiusPixels) / (outerRadiusPixels - innerRadiusPixels)
      if (gradientStopPosition <= 0 || gradientStopPosition >= 1) continue
      const [stopRed, stopGreen, stopBlue] = hexToRgb(stopHexColor)
      radialGradient.addColorStop(gradientStopPosition, `rgba(${stopRed},${stopGreen},${stopBlue},0.4)`)
    }

    // Bord extérieur transparent
    const [edgeRed, edgeGreen, edgeBlue] = hexToRgb(DB_LEVEL_COLOR_STOPS[0][1])
    radialGradient.addColorStop(1, `rgba(${edgeRed},${edgeGreen},${edgeBlue},0)`)

    canvasContext.fillStyle = radialGradient
    canvasContext.beginPath()
    canvasContext.arc(pointX, pointY, outerRadiusPixels, 0, 2 * Math.PI)
    canvasContext.fill()
  }

  canvasContext.restore()
}
