import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Map as MapGL, Source, Layer } from 'react-map-gl/maplibre'
import type { MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Aircraft } from '../hooks/useNoiseData'
import type { RoadSegment } from '../hooks/useRoadData'
import type { Train } from '../hooks/useRailwayData'
import { ANIMATION_DURATION, EARTH_RADIUS, FRAME_INTERVAL } from '../features/aircraft/constants'
import { TRAIN_SLIDE_DURATION } from '../features/railway/constants'
import type { AnimData } from '../features/aircraft/constants'
import type { TrainAnimData } from '../features/railway/constants'
import { projectOnPolyline, posAtDist, headingAtDist } from '../features/railway/polyline'
import { drawHalos } from '../features/aircraft/rendering'
import { drawRailwayHalos } from '../features/railway/rendering'
import AircraftMarker from '../features/aircraft/AircraftMarker'
import { railwayLineLayer } from '../features/railway/maplibre-layers'
import TrainMarker from '../features/railway/TrainMarker'
import { roadHaloOuter, roadHaloMid, roadHaloInner, roadCoreLayer } from '../features/road/maplibre-layers'
import { getRoadGeoJSON } from '../features/road/utils'

interface Props {
  aircraftData: Aircraft[]
  roadData: RoadSegment[]
  railwayData: Train[]
  railwayShapes: Map<string, [number, number, number][]>
  showAircraft: boolean
  showRoads: boolean
  showRailways: boolean
}

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_API
// Map dark-matter
// const MAP_STYLE = `https://api.maptiler.com/maps/019cbf29-a831-7ff4-b316-7788daaa3cf8/style.json?key=${MAPTILER_KEY}`
// Map winter
// const MAP_STYLE = `https://api.maptiler.com/maps/winter-v4/style.json?key=${MAPTILER_KEY}`
// Map winter custom
const MAP_STYLE = `https://api.maptiler.com/maps/019ce31a-bd4b-7f1b-973a-96f15b8cc90c/style.json?key=${MAPTILER_KEY}`

const MIN_ZOOM = 6
const MAX_ZOOM = 14
const LAT_REF = 46.6

/**
 * Composant principal de la carte. Gère la boucle RAF d'animation des positions, le canvas des halos, et la synchronisation des avions.
 * @param aircraftData - Liste des avions à afficher sur la carte
 * @returns Composant React avec carte interactive et halos de bruit
 */
export default React.memo(function NoiseMap({ aircraftData, roadData, railwayData, railwayShapes, showAircraft, showRoads, showRailways }: Props) {
  const mapRef = useRef<MapRef>(null)

  // Toutes les données "chaudes" en ref — jamais de setState dans la boucle RAF
  const positionsRef = useRef<Map<string, [number, number]>>(new Map())
  const aircraftRef = useRef<Map<string, Aircraft>>(new Map())
  const animDataRef = useRef<Map<string, AnimData>>(new Map())
  // [lat, lng, heading]
  const railwayPositionsRef = useRef<Map<string, [number, number, number]>>(new Map())
  const railwayDataRef = useRef<Map<string, Train>>(new Map())
  const railwayShapesRef = useRef<Map<string, [number, number, number][]>>(new Map())
  const railwayAnimDataRef = useRef<Map<string, TrainAnimData>>(new Map())

  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const railwayCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const canvasCtxRef = useRef<CanvasRenderingContext2D | null>(null)
  const railwayCanvasCtxRef = useRef<CanvasRenderingContext2D | null>(null)
  const zoomRef = useRef(6)
  const lastZoomStateRef = useRef(6)

  // State React pour les positions (throttlé à ~3fps)
  const [positions, setPositions] = useState<Map<string, [number, number]>>(new Map())
  const [railwayPositions, setRailwayPositions] = useState<Map<string, [number, number, number]>>(new Map())
  const [openPopupId, setOpenPopupId] = useState<string | null>(null)
  const [openTrainPopupId, setOpenTrainPopupId] = useState<string | null>(null)
  const [zoomState, setZoomState] = useState(6)

  const rafRef = useRef<number | null>(null)

  const roadGeoJSON = useMemo(() => getRoadGeoJSON(roadData), [roadData])

  // Convertir les shapes GTFS des trips actifs en GeoJSON pour affichage
  const railwayGeoJSON = useMemo(() => {
    if (railwayShapes.size === 0) return null
    const features: GeoJSON.Feature[] = []
    for (const [tripId, shape] of railwayShapes) {
      if (shape.length < 2) continue
      features.push({
        type: 'Feature',
        properties: { trip_id: tripId },
        geometry: {
          type: 'LineString',
          coordinates: shape.map(([lat, lon]) => [lon, lat]),
        },
      })
    }
    if (features.length === 0) return null
    return { type: 'FeatureCollection' as const, features }
  }, [railwayShapes])

  // Nettoyage du canvas avion à l'unmount
  useEffect(() => {
    return () => {
      canvasRef.current?.remove()
      railwayCanvasRef.current?.remove()
    }
  }, [])

  // Visibilité canvas avions
  useEffect(() => {
    if (canvasRef.current) canvasRef.current.style.display = showAircraft ? 'block' : 'none'
  }, [showAircraft])

  // Visibilité canvas trains
  useEffect(() => {
    if (railwayCanvasRef.current) railwayCanvasRef.current.style.display = showRailways ? 'block' : 'none'
  }, [showRailways])

  // Sync shapes ferroviaires depuis les props
  // Quand les shapes arrivent (chargement initial ou refresh 5 min), créer les animations
  // pour les trains déjà connus qui n'avaient pas encore de shape (race condition).
  useEffect(() => {
    railwayShapesRef.current = railwayShapes
    for (const [tripId, train] of railwayDataRef.current) {
      const shape = railwayShapes.get(tripId)
      if (!shape || shape.length < 2) continue
      // Ne pas écraser une animation shape déjà valide (Infinity = fallback heading, à remplacer)
      const existing = railwayAnimDataRef.current.get(tripId)
      if (existing && existing.maxDist !== Infinity && existing.maxDist > existing.minDist) continue
      const distTarget = projectOnPolyline(shape, [train.latitude, train.longitude])
      railwayAnimDataRef.current.set(tripId, {
        distFrom: distTarget,
        distTarget,
        speedMs: (train.speed_kmh ?? 0) / 3.6,
        startTime: performance.now(),
        maxDist: shape[shape.length - 1][2],
        minDist: shape[0][2],
        baseLat: train.latitude,
        baseLng: train.longitude,
      })
    }
  }, [railwayShapes])

  // Boucle RAF globale unique — met à jour toutes les positions, une seule fois par frame
  useEffect(() => {
    let lastFrameTime = 0
    let lastCircleTime = 0
    let lastReactUpdateTime = 0

    function loop(now: number) {
      rafRef.current = requestAnimationFrame(loop)

      if (now - lastFrameTime < FRAME_INTERVAL) return
      lastFrameTime = now

      let changed = false

      // --- Avions ---
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

      // --- Trains ---
      for (const [tripId, anim] of railwayAnimDataRef.current) {
        const train = railwayDataRef.current.get(tripId)
        if (!train) continue

        const shape = railwayShapesRef.current.get(tripId)
        const elapsedMs = now - anim.startTime

        if (shape && shape.length >= 2) {
          // Shape disponible → slide puis extrapolation
          let dist: number
          if (elapsedMs < TRAIN_SLIDE_DURATION) {
            // Phase slide : transition douce de distFrom vers distTarget
            const t = elapsedMs / TRAIN_SLIDE_DURATION
            dist = anim.distFrom + (anim.distTarget - anim.distFrom) * t
          } else {
            // Phase extrapolation : avance depuis distTarget par la vitesse
            const beyondSec = (elapsedMs - TRAIN_SLIDE_DURATION) / 1000
            dist = anim.distTarget + anim.speedMs * beyondSec
          }
          dist = Math.min(dist, anim.maxDist)
          const [lat, lng] = posAtDist(shape, dist)
          const hdg = headingAtDist(shape, dist)
          railwayPositionsRef.current.set(tripId, [lat, lng, hdg])
        } else {
          // Pas de shape → train immobile à sa position API (un train ne peut pas extrapoler en ligne droite)
          railwayPositionsRef.current.set(tripId, [anim.baseLat, anim.baseLng, train.heading ?? 0])
        }
        changed = true
      }

      // Halos canvas : throttlé à 5fps — toujours actif (redraw natif, pas de CSS transform)
      if (now - lastCircleTime >= 200) {
        lastCircleTime = now
        const map = mapRef.current
        const ctx = canvasCtxRef.current
        if (ctx && map) {
          drawHalos(ctx, aircraftRef.current, positionsRef.current, map, zoomRef.current)
        }
        // Halos trains
        const rCtx = railwayCanvasCtxRef.current
        if (rCtx && map) {
          drawRailwayHalos(rCtx, railwayDataRef.current, railwayPositionsRef.current, map, zoomRef.current)
        }
      }

      if (!changed) return

      // Markers React throttlés à ~3fps (333ms) — le canvas anime à 30fps via positionsRef
      if (now - lastReactUpdateTime >= 333) {
        lastReactUpdateTime = now
        setPositions(new Map(positionsRef.current))
        setRailwayPositions(new Map(railwayPositionsRef.current))
      }
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

  // Sync train positions from props
  useEffect(() => {
    const currentTrips = new Set(railwayData.map(t => t.trip_id))

    for (const tid of railwayDataRef.current.keys()) {
      if (!currentTrips.has(tid)) {
        railwayDataRef.current.delete(tid)
        railwayPositionsRef.current.delete(tid)
        railwayAnimDataRef.current.delete(tid)
      }
    }

    for (const train of railwayData) {
      railwayDataRef.current.set(train.trip_id, train)

      if (!railwayPositionsRef.current.has(train.trip_id)) {
        railwayPositionsRef.current.set(train.trip_id, [train.latitude, train.longitude, train.heading ?? 0])
      }

      const shape = railwayShapesRef.current.get(train.trip_id)
      const currentPos = railwayPositionsRef.current.get(train.trip_id)
      if (shape && shape.length >= 2) {
        // Projeter la position interpolée actuelle (pas la position API brute)
        let distFrom = 0
        if (currentPos) {
          distFrom = projectOnPolyline(shape, [currentPos[0], currentPos[1]])
        }
        // Projeter la position API pour la cible
        const distTarget = projectOnPolyline(shape, [train.latitude, train.longitude])
        // Train nouveau → pas de slide, apparition directe
        if (!currentPos) {
          distFrom = distTarget
        }
        railwayAnimDataRef.current.set(train.trip_id, {
          distFrom,
          distTarget,
          speedMs: (train.speed_kmh ?? 0) / 3.6,
          startTime: performance.now(),
          maxDist: shape[shape.length - 1][2],
          minDist: shape[0][2],
          baseLat: currentPos ? currentPos[0] : train.latitude,
          baseLng: currentPos ? currentPos[1] : train.longitude,
        })
      } else {
        // Pas de shape → train immobile à sa position API
        railwayAnimDataRef.current.set(train.trip_id, {
          distFrom: 0,
          distTarget: 0,
          speedMs: 0,
          startTime: performance.now(),
          maxDist: Infinity,
          minDist: 0,
          baseLat: train.latitude,
          baseLng: train.longitude,
        })
      }
    }
  }, [railwayData])

  /**
   * Crée et insère le canvas HTML des halos avion au-dessus du canvas WebGL de MapLibre.
   */
  function initCanvas() {
    const map = mapRef.current
    if (!map) return
    const container = (map as any).getCanvasContainer() as HTMLElement
    const webglCanvas = container.querySelector('.maplibregl-canvas') as HTMLElement

    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;'
    canvasRef.current = canvas
    canvasCtxRef.current = canvas.getContext('2d')
    if (webglCanvas) {
      webglCanvas.insertAdjacentElement('afterend', canvas)
    } else {
      container.appendChild(canvas)
    }

    const railwayCanvas = document.createElement('canvas')
    railwayCanvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;'
    railwayCanvasRef.current = railwayCanvas
    railwayCanvasCtxRef.current = railwayCanvas.getContext('2d')
    // Insérer après le canvas aircraft (pas après webgl) pour être au-dessus dans le DOM
    if (canvas) {
      canvas.insertAdjacentElement('afterend', railwayCanvas)
    } else if (webglCanvas) {
      webglCanvas.insertAdjacentElement('afterend', railwayCanvas)
    } else {
      container.appendChild(railwayCanvas)
    }

    redrawHalos()
  }

  /**
   * Redessine les halos de bruit sur le canvas en lisant l'état courant via les refs.
   */
  const redrawHalos = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const ctx = canvasCtxRef.current
    if (ctx) drawHalos(ctx, aircraftRef.current, positionsRef.current, map, zoomRef.current)
    const rCtx = railwayCanvasCtxRef.current
    if (rCtx) drawRailwayHalos(rCtx, railwayDataRef.current, railwayPositionsRef.current, map, zoomRef.current)
  }, [])

  const handleMove = useCallback((e: any) => {
    const newZoom = e.viewState.zoom
    zoomRef.current = newZoom
    if (Math.abs(newZoom - lastZoomStateRef.current) > 0.01) {
      lastZoomStateRef.current = newZoom
      setZoomState(newZoom)
    }
    redrawHalos()
  }, [redrawHalos])

  // Callbacks stables pour éviter les re-renders des AircraftMarker
  const handleMarkerClick = useCallback((icao: string) => setOpenPopupId(icao), [])
  const handlePopupClose = useCallback(() => setOpenPopupId(null), [])
  const handleTrainMarkerClick = useCallback((tripId: string) => setOpenTrainPopupId(tripId), [])
  const handleTrainPopupClose = useCallback(() => setOpenTrainPopupId(null), [])
  const handleMapMoveStart = useCallback(() => {
    setOpenPopupId(null)
    setOpenTrainPopupId(null)
  }, [])

  // Liste mémoïsée des markers (évite de recréer le tableau à chaque render)
  const markerList = useMemo(() => Array.from(positions.entries()), [positions])
  const trainMarkerList = useMemo(() => Array.from(railwayPositions.entries()), [railwayPositions])

  // Facteur zoom→taille mémoïsé — dépend uniquement du zoom, pas des positions (30fps)
  const zoomFactor = useMemo(() =>
    Math.max(0, Math.min(1, (zoomState - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM))),
  [zoomState])

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{ longitude: 1.888334, latitude: LAT_REF, zoom: 6 }}
      style={{ width: '100vw', height: '100vh' }}
      mapStyle={MAP_STYLE}
      minZoom={MIN_ZOOM}
      maxZoom={MAX_ZOOM}
      onLoad={initCanvas}
      onClick={handleMapMoveStart}
      onMoveStart={handleMapMoveStart}
      onMove={handleMove}
      onMoveEnd={redrawHalos}
    >
      {roadGeoJSON && showRoads && (
        <Source id="road-noise" type="geojson" data={roadGeoJSON}>
          <Layer {...roadHaloOuter} />
          <Layer {...roadHaloMid} />
          <Layer {...roadHaloInner} />
          <Layer {...roadCoreLayer} />
        </Source>
      )}

      {railwayGeoJSON && showRailways && (
        <Source id="railway-lines" type="geojson" data={railwayGeoJSON}>
          <Layer {...railwayLineLayer} />
        </Source>
      )}

      {showRailways && trainMarkerList.map(([tripId, pos]: [string, [number, number, number]]) => {
        const [lat, lng, heading] = pos
        const train = railwayDataRef.current.get(tripId)
        if (!train) return null
        return (
          <TrainMarker
            key={tripId}
            train={train}
            lat={lat}
            lng={lng}
            heading={heading}
            zoomFactor={zoomFactor}
            isOpen={openTrainPopupId === tripId}
            onClick={handleTrainMarkerClick}
            onClose={handleTrainPopupClose}
          />
        )
      })}

      {showAircraft && markerList.map(([icao, pos]: [string, [number, number]]) => {
        const [lat, lng] = pos
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