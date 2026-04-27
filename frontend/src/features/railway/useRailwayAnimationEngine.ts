import { useState, useEffect, useMemo, useRef } from 'react'
import type { Train } from '../../hooks/useRailwaysData'
import type { TrainAnimData } from './constants'
import { projectOnPolyline } from './polyline'

export function useRailwayAnimationEngine(
  railwaysData: Train[],
  railwaysShapes: Map<string, [number, number, number][]>,
  showRailways: boolean,
) {
  const railwayPositionsRef = useRef<Map<string, [number, number, number]>>(new Map())
  const railwayDataRef = useRef<Map<string, Train>>(new Map())
  const railwayShapesRef = useRef<Map<string, [number, number, number][]>>(new Map())
  const railwayAnimDataRef = useRef<Map<string, TrainAnimData>>(new Map())
  const railwayCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const railwayCanvasCtxRef = useRef<CanvasRenderingContext2D | null>(null)

  const [railwayPositions, setRailwayPositions] = useState<Map<string, [number, number, number]>>(new Map())

  useEffect(() => {
    return () => { railwayCanvasRef.current?.remove() }
  }, [])

  useEffect(() => {
    if (railwayCanvasRef.current) railwayCanvasRef.current.style.display = showRailways ? 'block' : 'none'
  }, [showRailways])

  // Sync shapes : crée les animations pour les trains déjà connus sans shape valide
  useEffect(() => {
    railwayShapesRef.current = railwaysShapes
    for (const [tripId, train] of railwayDataRef.current) {
      const shape = railwaysShapes.get(tripId)
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
  }, [railwaysShapes])

  useEffect(() => {
    const currentTrips = new Set(railwaysData.map(t => t.trip_id))

    for (const tid of railwayDataRef.current.keys()) {
      if (!currentTrips.has(tid)) {
        railwayDataRef.current.delete(tid)
        railwayPositionsRef.current.delete(tid)
        railwayAnimDataRef.current.delete(tid)
      }
    }

    for (const train of railwaysData) {
      railwayDataRef.current.set(train.trip_id, train)

      if (!railwayPositionsRef.current.has(train.trip_id)) {
        railwayPositionsRef.current.set(train.trip_id, [train.latitude, train.longitude, train.heading ?? 0])
      }

      const shape = railwayShapesRef.current.get(train.trip_id)
      const currentPos = railwayPositionsRef.current.get(train.trip_id)
      if (shape && shape.length >= 2) {
        // Projeter la position interpolée actuelle (pas la position API brute)
        let distFrom = 0
        if (currentPos) distFrom = projectOnPolyline(shape, [currentPos[0], currentPos[1]])
        const distTarget = projectOnPolyline(shape, [train.latitude, train.longitude])
        // Train nouveau → pas de slide, apparition directe
        if (!currentPos) distFrom = distTarget
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
          distFrom: 0, distTarget: 0, speedMs: 0,
          startTime: performance.now(),
          maxDist: Infinity, minDist: 0,
          baseLat: train.latitude, baseLng: train.longitude,
        })
      }
    }
  }, [railwaysData])

  const trainMarkerList = useMemo(() => Array.from(railwayPositions.entries()), [railwayPositions])

  function initCanvas(container: HTMLElement, insertAfter: HTMLElement | null) {
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;'
    railwayCanvasRef.current = canvas
    railwayCanvasCtxRef.current = canvas.getContext('2d')
    // Insérer après le canvas aircraft pour être au-dessus dans le DOM
    if (insertAfter) {
      insertAfter.insertAdjacentElement('afterend', canvas)
    } else {
      container.appendChild(canvas)
    }
  }

  return {
    railwayDataRef, railwayPositionsRef, railwayAnimDataRef, railwayShapesRef,
    railwayCanvasRef, railwayCanvasCtxRef,
    railwayPositions, setRailwayPositions, trainMarkerList,
    initCanvas,
  }
}
