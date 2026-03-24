import { useCallback, useEffect, useRef, useState } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const SHAPES_INTERVAL = 2 * 60 * 1000 // 2 min (aligné GTFS-RT Trip Updates)

type ShapePoints = [number, number, number][]

function parseShapes(json: Record<string, ShapePoints>): Map<string, ShapePoints> {
  return new Map(Object.entries(json))
}

export function useRailwayShapes() {
  const [shapesData, setShapesData] = useState<Map<string, ShapePoints>>(new Map())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchShapes = useCallback(async (detail: 'low' | 'high') => {
    const label = `railway-shapes-${detail}`
    const t0 = performance.now()
    try {
      const res = await perfFetch(label, `${API_URL}/api/railway/shapes?detail=${detail}`)
      if (!res.ok) return null
      const json: Record<string, ShapePoints> = await perfJson(label, res)
      const entries = Object.entries(json)
      const totalPoints = entries.reduce((sum, [, pts]) => sum + pts.length, 0)
      perfDone(label, `${entries.length} trips / ${totalPoints} points`, t0)
      return json
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    // Lancer low et high en parallèle — le premier arrivé s'affiche immédiatement
    const lowPromise = fetchShapes('low')
    const highPromise = fetchShapes('high')

    lowPromise.then(json => {
      if (!cancelled && json) setShapesData(parseShapes(json))
    })

    highPromise.then(json => {
      if (!cancelled && json) setShapesData(parseShapes(json))
    })

    // Rafraîchissement périodique en high
    intervalRef.current = setInterval(async () => {
      const json = await fetchShapes('high')
      if (!cancelled && json) setShapesData(parseShapes(json))
    }, SHAPES_INTERVAL)

    return () => {
      cancelled = true
      if (intervalRef.current !== null) clearInterval(intervalRef.current)
    }
  }, [fetchShapes])

  return { shapesData, refreshShapes: async () => {
    const json = await fetchShapes('high')
    if (json) setShapesData(parseShapes(json))
  }}
}
