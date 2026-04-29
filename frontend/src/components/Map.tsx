import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Map as MapGL, Source, Layer } from 'react-map-gl/maplibre'
import type { MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Aircraft } from '../hooks/useAircraftsData'
import type { RoadsSegment } from '../hooks/useRoadsData'
import type { Train } from '../hooks/useRailwaysData'
import { ANIMATION_DURATION, EARTH_RADIUS, FRAME_INTERVAL } from '../features/aircraft/constants'
import { TRAIN_SLIDE_DURATION, RAILWAY_LINE_COLORS } from '../features/railway/constants'
import { posAtDist, headingAtDist } from '../features/railway/polyline'
import { drawHalos } from '../features/aircraft/rendering'
import { drawRailwayHalos } from '../features/railway/rendering'
import AircraftMarker from '../features/aircraft/AircraftMarker'
import { getRailwayLineLayer } from '../features/railway/maplibre-layers'
import TrainMarker from '../features/railway/TrainMarker'
import { roadHaloOuter, roadHaloMid, roadHaloInner, roadCoreLayer } from '../features/road/maplibre-layers'
import { getRoadGeoJSON } from '../features/road/utils'
import { useAircraftAnimationEngine } from '../features/aircraft/useAircraftAnimationEngine'
import { useRailwayAnimationEngine } from '../features/railway/useRailwayAnimationEngine'

interface Props {
  aircraftsData: Aircraft[]
  roadsData: RoadsSegment[]
  railwaysData: Train[]
  railwaysShapes: Map<string, [number, number, number][]>
  showAircrafts: boolean
  showRoads: boolean
  showRailways: boolean
  mapStyleKey: MapStyleKey
}

const ALL_STYLES = {
  default: import.meta.env.VITE_MAPTILER_DEFAULT_MAP,
  light: import.meta.env.VITE_MAPTILER_LIGHT_MAP,
  dark: import.meta.env.VITE_MAPTILER_DARK_MAP,
} as const

export const MAP_STYLES = Object.fromEntries(
  Object.entries(ALL_STYLES).filter(([_, v]) => Boolean(v))
) as Partial<Record<'default' | 'light' | 'dark', string>>

export type MapStyleKey = 'default' | 'light' | 'dark'
export const DEFAULT_STYLE_KEY: MapStyleKey = (Object.keys(MAP_STYLES)[0] as MapStyleKey) ?? 'default'

const MIN_ZOOM = 6
const MAX_ZOOM = 11
const LAT_REF = 46.6

/**
 * Composant principal de la carte.
 * La boucle RAF est volontairement unifiée (un seul requestAnimationFrame pour avions + trains + canvas)
 * pour éviter deux passes de rendu par tick. Les systèmes d'animation sont encapsulés dans
 * useAircraftAnimationEngine et useRailwayAnimationEngine.
 */
export default React.memo(function NoiseMap({ aircraftsData, roadsData, railwaysData, railwaysShapes, showAircrafts, showRoads, showRailways, mapStyleKey }: Props) {
  const mapRef = useRef<MapRef>(null)
  const zoomRef = useRef(6)
  const lastZoomStateRef = useRef(6)
  const rafRef = useRef<number | null>(null)

  const [openPopupId, setOpenPopupId] = useState<string | null>(null)
  const [openTrainPopupId, setOpenTrainPopupId] = useState<string | null>(null)
  const [zoomState, setZoomState] = useState(6)

  const aircraft = useAircraftAnimationEngine(aircraftsData, showAircrafts)
  const railway = useRailwayAnimationEngine(railwaysData, railwaysShapes, showRailways)

  const roadGeoJSON = useMemo(() => getRoadGeoJSON(roadsData), [roadsData])
  const railwayLineLayer = useMemo(
    () => getRailwayLineLayer(RAILWAY_LINE_COLORS[mapStyleKey] ?? RAILWAY_LINE_COLORS.default),
    [mapStyleKey],
  )

  const railwayGeoJSON = useMemo(() => {
    if (railwaysShapes.size === 0) return null
    const features: GeoJSON.Feature[] = []
    for (const [tripId, shape] of railwaysShapes) {
      if (shape.length < 2) continue
      features.push({
        type: 'Feature',
        properties: { trip_id: tripId },
        geometry: { type: 'LineString', coordinates: shape.map(([lat, lon]) => [lon, lat]) },
      })
    }
    if (features.length === 0) return null
    return { type: 'FeatureCollection' as const, features }
  }, [railwaysShapes])

  // Boucle RAF globale unique — un seul tick pour avions + trains + canvas (pas de double rendu)
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
      for (const [icao, anim] of aircraft.animDataRef.current) {
        const ac = aircraft.aircraftRef.current.get(icao)
        if (!ac) continue

        const elapsed = now - anim.startTime
        let lat: number, lng: number

        if (elapsed < ANIMATION_DURATION) {
          const t = elapsed / ANIMATION_DURATION
          lat = anim.fromLat + (anim.toLat - anim.fromLat) * t
          lng = anim.fromLng + (anim.toLng - anim.fromLng) * t
        } else {
          const secondsBeyond = (elapsed - ANIMATION_DURATION) / 1000
          const velocity = ac.velocity
          const heading = ac.heading
          if (velocity && velocity > 0 && heading != null) {
            const dist = velocity * secondsBeyond
            const headingRad = (heading * Math.PI) / 180
            lat = anim.toLat + (dist * Math.cos(headingRad)) / EARTH_RADIUS * (180 / Math.PI)
            lng = anim.toLng + (dist * Math.sin(headingRad)) / (EARTH_RADIUS * Math.cos(anim.toLat * Math.PI / 180)) * (180 / Math.PI)
          } else {
            lat = anim.toLat
            lng = anim.toLng
          }
        }

        aircraft.positionsRef.current.set(icao, [lat, lng])
        changed = true
      }

      // --- Trains ---
      for (const [tripId, anim] of railway.railwayAnimDataRef.current) {
        const train = railway.railwayDataRef.current.get(tripId)
        if (!train) continue

        const shape = railway.railwayShapesRef.current.get(tripId)
        const elapsedMs = now - anim.startTime

        if (shape && shape.length >= 2) {
          // Shape disponible → slide puis extrapolation
          let dist: number
          if (elapsedMs < TRAIN_SLIDE_DURATION) {
            const t = elapsedMs / TRAIN_SLIDE_DURATION
            dist = anim.distFrom + (anim.distTarget - anim.distFrom) * t
          } else {
            const beyondSec = (elapsedMs - TRAIN_SLIDE_DURATION) / 1000
            dist = anim.distTarget + anim.speedMs * beyondSec
          }
          dist = Math.min(dist, anim.maxDist)
          const [lat, lng] = posAtDist(shape, dist)
          const hdg = headingAtDist(shape, dist)
          railway.railwayPositionsRef.current.set(tripId, [lat, lng, hdg])
        } else {
          // Pas de shape → train immobile à sa position API
          railway.railwayPositionsRef.current.set(tripId, [anim.baseLat, anim.baseLng, train.heading ?? 0])
        }
        changed = true
      }

      // Halos canvas throttlés à 5fps
      if (now - lastCircleTime >= 200) {
        lastCircleTime = now
        const map = mapRef.current
        const ctx = aircraft.canvasCtxRef.current
        if (ctx && map) drawHalos(ctx, aircraft.aircraftRef.current, aircraft.positionsRef.current, map, zoomRef.current)
        const rCtx = railway.railwayCanvasCtxRef.current
        if (rCtx && map) drawRailwayHalos(rCtx, railway.railwayDataRef.current, railway.railwayPositionsRef.current, map, zoomRef.current)
      }

      if (!changed) return

      // Markers React throttlés à ~3fps — le canvas anime à 30fps via les refs
      if (now - lastReactUpdateTime >= 333) {
        lastReactUpdateTime = now
        aircraft.setPositions(new Map(aircraft.positionsRef.current))
        railway.setRailwayPositions(new Map(railway.railwayPositionsRef.current))
      }
    }

    rafRef.current = requestAnimationFrame(loop)
    return () => { if (rafRef.current !== null) cancelAnimationFrame(rafRef.current) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function initCanvas() {
    const map = mapRef.current
    if (!map) return
    const container = (map as any).getCanvasContainer() as HTMLElement
    const webglCanvas = container.querySelector('.maplibregl-canvas') as HTMLElement
    aircraft.initCanvas(container, webglCanvas)
    railway.initCanvas(container, aircraft.canvasRef.current)
    redrawHalos()
  }

  const redrawHalos = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const ctx = aircraft.canvasCtxRef.current
    if (ctx) drawHalos(ctx, aircraft.aircraftRef.current, aircraft.positionsRef.current, map, zoomRef.current)
    const rCtx = railway.railwayCanvasCtxRef.current
    if (rCtx) drawRailwayHalos(rCtx, railway.railwayDataRef.current, railway.railwayPositionsRef.current, map, zoomRef.current)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleMove = useCallback((e: any) => {
    const newZoom = e.viewState.zoom
    zoomRef.current = newZoom
    if (Math.abs(newZoom - lastZoomStateRef.current) > 0.01) {
      lastZoomStateRef.current = newZoom
      setZoomState(newZoom)
    }
    redrawHalos()
  }, [redrawHalos])

  const handleMarkerClick = useCallback((icao: string) => setOpenPopupId(icao), [])
  const handlePopupClose = useCallback(() => setOpenPopupId(null), [])
  const handleTrainMarkerClick = useCallback((tripId: string) => setOpenTrainPopupId(tripId), [])
  const handleTrainPopupClose = useCallback(() => setOpenTrainPopupId(null), [])
  const handleMapMoveStart = useCallback(() => {
    setOpenPopupId(null)
    setOpenTrainPopupId(null)
  }, [])

  const zoomFactor = useMemo(() =>
    Math.max(0, Math.min(1, (zoomState - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM))),
  [zoomState])

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{ longitude: 1.888334, latitude: LAT_REF, zoom: 6 }}
      style={{ width: '100vw', height: '100vh' }}
      mapStyle={MAP_STYLES[mapStyleKey] as string}
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

      {showRailways && railway.trainMarkerList.map(([tripId, pos]: [string, [number, number, number]]) => {
        const [lat, lng, heading] = pos
        const train = railway.railwayDataRef.current.get(tripId)
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

      {showAircrafts && aircraft.markerList.map(([icao, pos]: [string, [number, number]]) => {
        const [lat, lng] = pos
        const ac = aircraft.aircraftRef.current.get(icao)
        if (!ac) return null
        return (
          <AircraftMarker
            key={icao}
            icao={icao}
            lat={lat}
            lng={lng}
            aircraft={ac}
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
