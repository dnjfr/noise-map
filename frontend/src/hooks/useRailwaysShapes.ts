import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL
const SHAPES_INTERVAL = 2 * 60 * 1000 // 2 min (aligné GTFS-RT Trip Updates)

type ShapePoints = [number, number, number][]

function parseShapes(json: Record<string, ShapePoints>): Map<string, ShapePoints> {
  return new Map(Object.entries(json))
}

/**
 * Hook React exposant les shapes GTFS des trips actifs.
 * Au montage, charge low et high en parallèle (le premier arrivé s'affiche immédiatement).
 * Rafraîchissement automatique toutes les 2 minutes (aligné cache serveur TTL=2 min).
 * Expose refreshShapes() pour forcer un rechargement immédiat (ex : trip inconnu détecté).
 *
 * @returns { shapesData: Map<trip_id, ShapePoints[]>, refreshShapes }
 */
export function useRailwaysShapes() {
  const [shapesData, setShapesData] = useState<Map<string, ShapePoints>>(new Map())
  const [apiError, setApiError] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const consecutiveErrorsRef = useRef(0)

  const fetchShapes = useCallback(async (detail: 'low' | 'high') => {
    const label = `railway-shapes-${detail}`
    const t0 = performance.now()
    try {
      const res = await perfFetch(label, `${API_URL}/api/railways/shapes?detail=${detail}`)
      if (!res.ok) {
        if (detail === 'high') {
          consecutiveErrorsRef.current++
          if (consecutiveErrorsRef.current >= 2) setApiError(true)
        }
        return null
      }
      const json: Record<string, ShapePoints> = await perfJson(label, res)
      if (detail === 'high') {
        consecutiveErrorsRef.current = 0
        setApiError(false)
      }
      const entries = Object.entries(json)
      const totalPoints = entries.reduce((sum, [, pts]) => sum + pts.length, 0)
      perfDone(label, `${entries.length} trips / ${totalPoints} points`, t0)
      return json
    } catch {
      if (detail === 'high') {
        consecutiveErrorsRef.current++
        if (consecutiveErrorsRef.current >= 2) setApiError(true)
      }
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const highAppliedRef = { current: false }

    // Lancer low et high en parallèle — low s'affiche en premier, high écrase si disponible
    // highAppliedRef empêche low d'écraser high si high arrive avant low
    const lowPromise = fetchShapes('low')
    const highPromise = fetchShapes('high')

    lowPromise.then(json => {
      if (!cancelled && json && !highAppliedRef.current) setShapesData(parseShapes(json))
    })

    highPromise.then(json => {
      if (!cancelled && json) {
        highAppliedRef.current = true
        setShapesData(parseShapes(json))
      }
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

  const refreshShapes = useCallback(async () => {
    const json = await fetchShapes('high')
    if (json) setShapesData(parseShapes(json))
  }, [fetchShapes])

  return useMemo(() => ({ shapesData, refreshShapes, apiError }), [shapesData, refreshShapes, apiError])
}
