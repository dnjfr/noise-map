import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL
const POLL_INTERVAL = 30000

export interface Train {
  trip_id: string
  train_number: string
  route_id: string
  latitude: number
  longitude: number
  speed_kmh: number
  heading: number
  delay_seconds: number
  next_stop_name: string
  prev_stop_name?: string
  time: string
  trip_headsign?: string
  route_short_name?: string
  route_long_name?: string
}

/**
 * Hook React exposant les positions temps-réel des trains (GTFS-RT).
 * Poll /api/railways/positions toutes les 30 secondes.
 *
 * @returns { railwaysData, lastUpdate }
 */
export function useRailwaysData(): { railwaysData: Train[]; lastUpdate: Date | null; apiError: boolean } {
  const [railwaysData, setRailwaysData] = useState<Train[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [apiError, setApiError] = useState(false)

  const consecutiveErrorsRef = useRef(0)
  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const response = isFirst
        ? await perfFetch('railway-current', `${API_URL}/api/railways/positions`)
        : await fetch(`${API_URL}/api/railways/positions`)
      if (!response.ok) {
        consecutiveErrorsRef.current++
        if (consecutiveErrorsRef.current >= 2) setApiError(true)
        return
      }
      const result = isFirst
        ? await perfJson<any>('railway-current', response)
        : await response.json()
      consecutiveErrorsRef.current = 0
      setApiError(false)
      setRailwaysData(result.data || [])
      setLastUpdate(new Date())
      if (isFirst) perfDone('railway-current', result.data?.length ?? 0, t0)
    } catch (error) {
      console.error('Erreur chargement données ferroviaires:', error)
      consecutiveErrorsRef.current++
      if (consecutiveErrorsRef.current >= 2) setApiError(true)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return useMemo(() => ({ railwaysData, lastUpdate, apiError }), [railwaysData, lastUpdate, apiError])
}
