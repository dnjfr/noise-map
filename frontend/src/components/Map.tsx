import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Map as MapGL, Marker, Popup } from 'react-map-gl/maplibre'
import type { MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Aircraft } from '../hooks/useNoiseData'

interface Props {
  noiseData: unknown[]
  aircraftData: Aircraft[]
}

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_API
const MAP_STYLE = `https://api.maptiler.com/maps/019cbf29-a831-7ff4-b316-7788daaa3cf8/style.json?key=${MAPTILER_KEY}`

const NOISE_REFERENCE_DB_BY_CATEGORY: Record<string, number> = {
  A1: 65, A2: 72, A3: 80, A4: 82, A5: 85,
}

const MIN_ZOOM = 6
const MAX_ZOOM = 13
const ICON_MIN = 6
const MAX_SIZE_BY_CATEGORY: Record<string, number> = {
  A1: 13, A2: 16, A3: 19, A4: 22, A5: 25,
}
const DEFAULT_MAX_SIZE = 17
const LAT_REF = 46.6

const DB_LEVEL_COLOR_STOPS: Array<[number, string]> = [
  [51, '#22c55e'],
  [60, '#eab308'],
  [70, '#f97316'],
  [80, '#dc2626'],
]

/**
 * Retourne le niveau de bruit de référence Lref en dB(A) pour une catégorie d'avion ICAO.
 * @param category - Catégorie ICAO (A1 à A5) ou null
 * @returns Niveau de bruit de référence en dB(A). Fallback 80 dB si catégorie inconnue
 */
function getNoiseReferenceDb(category: string | null): number {
  return category ? (NOISE_REFERENCE_DB_BY_CATEGORY[category] ?? 80) : 80
}

/**
 * Calcule le niveau de bruit perçu au sol (dB(A)) depuis un avion à une altitude donnée.
 * @param noiseReferenceDb - Niveau de bruit de référence Lref en dB(A)
 * @param altitudeMeters - Altitude de l'avion en mètres
 * @returns Niveau de bruit au sol en dB(A). Formule : atténuation -20*log10(alt/300). Minimum 50m d'altitude
 */
function calcGroundNoise(noiseReferenceDb: number, altitudeMeters: number): number {
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
function calcNoiseRadius(noiseReferenceDb: number, thresholdDb: number, altitudeMeters: number): number | null {
  const slant = 300 * Math.pow(10, (noiseReferenceDb - thresholdDb) / 20)
  if (altitudeMeters >= slant) return null
  return Math.sqrt(slant * slant - altitudeMeters * altitudeMeters)
}

/**
 * Convertit une couleur hexadécimale en tuple RGB.
 * @param hex - Couleur en format hexadécimal (#RRGGBB)
 * @returns Tuple [R, G, B] avec valeurs 0-255
 */
function hexToRgb(hex: string): [number, number, number] {
  const hexValue = parseInt(hex.slice(1), 16)
  return [(hexValue >> 16) & 255, (hexValue >> 8) & 255, hexValue & 255]
}

/**
 * Interpole une couleur CSS entre les stops de DB_LEVEL_COLOR_STOPS en fonction du niveau de bruit.
 * @param dbLevel - Niveau de bruit en dB(A)
 * @returns Couleur au format hexadécimal (#RRGGBB)
 */
function interpolateColor(dbLevel: number): string {
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
 * Dessine sur un canvas 2D les halos de bruit radial pour chaque avion.
 * @param canvasContext - Contexte canvas 2D pour le dessin
 * @param aircraftList - Liste des avions à afficher
 * @param posMap - Map des positions actuelles (icao24 -> [lat, lng])
 * @param map - Référence à la carte MapGL pour la projection
 * @param zoom - Niveau de zoom courant
 */
function drawHalos(
  canvasContext: CanvasRenderingContext2D,
  aircraftList: Aircraft[],
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

  for (const aircraft of aircraftList) {
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

/**
 * Génère le contenu HTML d'une popup d'info pour un avion.
 * @param aircraft - Données de l'avion (callsign, altitude, vitesse, ICAO, catégorie)
 * @returns String HTML contenant callsign, altitude, vitesse, bruit estimé, ICAO
 */
function buildPopupContent(aircraft: Aircraft): string {
  const noiseReferenceDb = getNoiseReferenceDb(aircraft.aircraft_category)
  const altitudeMeters = aircraft.altitude
  const groundNoise = altitudeMeters && altitudeMeters > 0 ? calcGroundNoise(noiseReferenceDb, altitudeMeters).toFixed(0) : null
  return `
    <strong>${aircraft.callsign || aircraft.icao24}</strong><br />
    ${aircraft.aircraft_desc ? `<em style="color:#aaa">${aircraft.aircraft_desc}</em><br />` : ''}
    <strong>Altitude :</strong> ${altitudeMeters ? (altitudeMeters / 1000).toFixed(1) : 'N/A'} km<br />
    <strong>Vitesse :</strong> ${aircraft.velocity ? (aircraft.velocity * 3.6).toFixed(0) : 'N/A'} km/h<br />
    ${groundNoise ? `<strong>Bruit estimé :</strong> ${groundNoise} dB<br />` : ''}
    <strong>ICAO24 :</strong> ${aircraft.icao24}
  `
}

/**
 * Génère un SVG inline représentant la silhouette d'un avion.
 * @param size - Taille du SVG en pixels (width et height)
 * @returns String SVG de la silhouette d'avion
 */
function getAircraftSvg(size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24">
  <rect x="10.5" y="2" width="3" height="16" rx="1.5" fill="#60a5fa"/>
  <polygon points="12,8 3,14 21,14" fill="#60a5fa"/>
  <polygon points="12,18 8,22 16,22" fill="#60a5fa"/>
</svg>`
}

const ANIMATION_DURATION = 3200
const EARTH_RADIUS = 6371000
const FRAME_INTERVAL = 1000 / 30

// Données d'animation par avion (purement ref, pas de state)
interface AnimData {
  fromLat: number; fromLng: number
  toLat: number; toLng: number
  startTime: number
}

// --- Composant marker memoized, défini hors de NoiseMap pour éviter les recréations ---

interface AircraftMarkerProps {
  icao: string
  lat: number
  lng: number
  aircraft: Aircraft
  zoomFactor: number
  isOpen: boolean
  onClick: (icao: string) => void
  onClose: () => void
}

/**
 * Affiche le marker d'un avion sur la carte avec rotation selon son cap.
 * Mémoïsé pour éviter les re-renders inutiles.
 * @param icao - Identifiant ICAO24 de l'avion
 * @param lat - Latitude du marker
 * @param lng - Longitude du marker
 * @param aircraft - Données de l'avion (heading, catégorie, etc.)
 * @param zoomFactor - Facteur de zoom pour adapter la taille du marker
 * @param isOpen - Indique si la popup d'info est ouverte
 * @param onClick - Callback au clic sur le marker
 * @param onClose - Callback à la fermeture de la popup
 */
const AircraftMarker = React.memo(function AircraftMarker({
  icao, lat, lng, aircraft, zoomFactor, isOpen, onClick, onClose,
}: AircraftMarkerProps) {
  const pixelSize = useMemo(() => {
    const maxSize = MAX_SIZE_BY_CATEGORY[aircraft.aircraft_category ?? ''] ?? DEFAULT_MAX_SIZE
    return Math.round(ICON_MIN + zoomFactor * (maxSize - ICON_MIN))
  }, [aircraft.aircraft_category, zoomFactor])

  const svgHtml = useMemo(() => ({ __html: getAircraftSvg(pixelSize) }), [pixelSize])

  const style = useMemo(() => ({
    transform: `rotate(${aircraft.heading ?? 0}deg)`,
    cursor: 'pointer' as const,
    width: pixelSize,
    height: pixelSize,
  }), [aircraft.heading, pixelSize])

  const handleClick = useCallback((e: { originalEvent: { stopPropagation(): void } }) => {
    e.originalEvent.stopPropagation()
    onClick(icao)
  }, [icao, onClick])

  return (
    <>
      <Marker latitude={lat} longitude={lng} anchor="center" onClick={handleClick}>
        <div style={style} dangerouslySetInnerHTML={svgHtml} />
      </Marker>
      {isOpen && (
        <Popup
          latitude={lat}
          longitude={lng}
          anchor="bottom"
          closeButton={true}
          closeOnClick={false}
          onClose={onClose}
        >
          <div
            style={{ fontSize: 13, lineHeight: 1.6 }}
            dangerouslySetInnerHTML={{ __html: buildPopupContent(aircraft) }}
          />
        </Popup>
      )}
    </>
  )
})

/**
 * Composant principal de la carte. Gère la boucle RAF d'animation des positions, le canvas des halos, et la synchronisation des avions.
 * @param aircraftData - Liste des avions à afficher sur la carte
 * @returns Composant React avec carte interactive et halos de bruit
 */
export default React.memo(function NoiseMap({ aircraftData }: Props) {
  const mapRef = useRef<MapRef>(null)

  // Toutes les données "chaudes" en ref — jamais de setState dans la boucle RAF
  const positionsRef = useRef<Map<string, [number, number]>>(new Map())
  const aircraftRef = useRef<Map<string, Aircraft>>(new Map())
  const animDataRef = useRef<Map<string, AnimData>>(new Map())

  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const zoomRef = useRef(6)

  // State React pour les positions (30fps)
  const [positions, setPositions] = useState<Map<string, [number, number]>>(new Map())
  const [openPopupId, setOpenPopupId] = useState<string | null>(null)

  const rafRef = useRef<number | null>(null)

  // Nettoyage du canvas à l'unmount
  useEffect(() => {
    return () => { canvasRef.current?.remove() }
  }, [])

  // Boucle RAF globale unique — met à jour toutes les positions, une seule fois par frame
  useEffect(() => {
    let lastFrameTime = 0
    let lastCircleTime = 0

    function loop(now: number) {
      rafRef.current = requestAnimationFrame(loop)

      if (now - lastFrameTime < FRAME_INTERVAL) return
      lastFrameTime = now

      let changed = false
      for (const [icao, anim] of animDataRef.current) {
        const aircraft = aircraftRef.current.get(icao)
        if (!aircraft) continue

        const elapsed = now - anim.startTime
        let lat: number, lng: number

        if (elapsed < ANIMATION_DURATION) {
          const animationProgress = elapsed / ANIMATION_DURATION
          lat = anim.fromLat + (anim.toLat - anim.fromLat) * animationProgress
          lng = anim.fromLng + (anim.toLng - anim.fromLng) * animationProgress
        } else {
          const secondsBeyond = (elapsed - ANIMATION_DURATION) / 1000
          const velocity = aircraft.velocity
          const heading = aircraft.heading
          if (velocity && velocity > 0 && heading != null) {
            const dist = velocity * secondsBeyond
            const headingRadians = (heading * Math.PI) / 180
            lat = anim.toLat + (dist * Math.cos(headingRadians)) / EARTH_RADIUS * (180 / Math.PI)
            lng = anim.toLng + (dist * Math.sin(headingRadians)) / (EARTH_RADIUS * Math.cos(anim.toLat * Math.PI / 180)) * (180 / Math.PI)
          } else {
            lat = anim.toLat
            lng = anim.toLng
          }
        }

        positionsRef.current.set(icao, [lat, lng])
        changed = true
      }

      // Halos canvas : throttlé à 5fps, indépendamment de changed (pan/zoom doit aussi redessiner)
      if (now - lastCircleTime >= 200) {
        lastCircleTime = now
        const canvas = canvasRef.current
        const map = mapRef.current
        if (canvas && map) {
          const canvasContext = canvas.getContext('2d')
          if (canvasContext) drawHalos(canvasContext, Array.from(aircraftRef.current.values()), positionsRef.current, map, zoomRef.current)
        }
      }

      if (!changed) return

      // Un seul setState par frame pour les markers React
      setPositions(new Map(positionsRef.current))
    }

    rafRef.current = requestAnimationFrame(loop)
    return () => { if (rafRef.current !== null) cancelAnimationFrame(rafRef.current) }
  }, [])

  // Synchronisation des avions depuis les props
  useEffect(() => {
    const currentIcaos = new Set(aircraftData.map(a => a.icao24))

    // Supprimer les avions disparus
    for (const icao of aircraftRef.current.keys()) {
      if (!currentIcaos.has(icao)) {
        aircraftRef.current.delete(icao)
        positionsRef.current.delete(icao)
        animDataRef.current.delete(icao)
      }
    }

    // Ajouter/mettre à jour
    for (const aircraft of aircraftData) {
      const prev = aircraftRef.current.get(aircraft.icao24)
      aircraftRef.current.set(aircraft.icao24, aircraft)

      if (!positionsRef.current.has(aircraft.icao24)) {
        positionsRef.current.set(aircraft.icao24, [aircraft.latitude, aircraft.longitude])
      }

      // Nouvelle position → nouvelle animation
      if (!prev || prev.latitude !== aircraft.latitude || prev.longitude !== aircraft.longitude) {
        const from = positionsRef.current.get(aircraft.icao24) ?? [aircraft.latitude, aircraft.longitude]
        animDataRef.current.set(aircraft.icao24, {
          fromLat: from[0], fromLng: from[1],
          toLat: aircraft.latitude, toLng: aircraft.longitude,
          startTime: performance.now(),
        })
      }
    }
  }, [aircraftData])

  /**
   * Crée et insère un canvas HTML au-dessus du canvas WebGL de MapLibre.
   * Lance un premier dessin des halos.
   */
  function initCanvas() {
    const map = mapRef.current
    if (!map) return
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;'
    canvasRef.current = canvas
    const container = (map as any).getCanvasContainer() as HTMLElement
    const webglCanvas = container.querySelector('.maplibregl-canvas') as HTMLElement
    if (webglCanvas) {
      webglCanvas.insertAdjacentElement('afterend', canvas)
    } else {
      container.appendChild(canvas)
    }
    redrawHalos()
  }

  /**
   * Redessine les halos de bruit sur le canvas en lisant l'état courant via les refs.
   */
  function redrawHalos() {
    const canvas = canvasRef.current
    const map = mapRef.current
    if (!canvas || !map) return
    const canvasContext = canvas.getContext('2d')
    if (canvasContext) drawHalos(canvasContext, Array.from(aircraftRef.current.values()), positionsRef.current, map, zoomRef.current)
  }

  // Callbacks stables pour éviter les re-renders des AircraftMarker
  const handleMarkerClick = useCallback((icao: string) => setOpenPopupId(icao), [])
  const handlePopupClose = useCallback(() => setOpenPopupId(null), [])
  const handleMapMoveStart = useCallback(() => setOpenPopupId(null), [])

  // Liste mémoïsée des markers (évite de recréer le tableau à chaque render)
  const markerList = useMemo(() => Array.from(positions.entries()), [positions])

  // Facteur zoom→taille mémoïsé (se recalcule quand positions change, au même rythme que le RAF)
  const zoomFactor = useMemo(() => {
    const z = zoomRef.current
    return Math.max(0, Math.min(1, (z - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)))
  }, [positions])

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{ longitude: 1.888334, latitude: 46.603354, zoom: 6 }}
      style={{ width: '100vw', height: '100vh' }}
      mapStyle={MAP_STYLE}
      minZoom={6}
      maxZoom={13}
      onLoad={initCanvas}
      onMoveStart={handleMapMoveStart}
      onMove={(e) => { zoomRef.current = e.viewState.zoom; redrawHalos() }}
    >
      {markerList.map(([icao, [lat, lng]]) => {
        const aircraft = aircraftRef.current.get(icao)
        if (!aircraft) return null
        return (
          <AircraftMarker
            key={icao}
            icao={icao}
            lat={lat}
            lng={lng}
            aircraft={aircraft}
            zoomFactor={zoomFactor}
            isOpen={openPopupId === icao}
            onClick={handleMarkerClick}
            onClose={handlePopupClose}
          />
        )
      })}
    </MapGL>
  )
})
