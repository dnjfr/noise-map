import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL
const UPDATE_INTERVAL = 3000

export interface Aircraft {
  icao24: string
  callsign: string | null
  latitude: number
  longitude: number
  altitude: number | null
  velocity: number | null
  heading: number | null
  time: string
  aircraft_type: string | null
  aircraft_desc: string | null
  aircraft_category: string | null
}

interface AircraftsState {
  aircraftsData: Aircraft[]
  lastUpdate: Date | null
  apiError: boolean
}

/**
 * Hook React exposant les positions des avions.
 * Poll /api/aircrafts/positions toutes les 3 secondes.
 *
 * @returns { aircraftsData, lastUpdate }
 */
export function useAircraftsData(): AircraftsState {
  const [aircraftsData, setAircraftsData] = useState<Aircraft[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [apiError, setApiError] = useState(false)

  const prevCountRef = useRef<number>(-1)
  const consecutiveErrorsRef = useRef(0)

  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const res = isFirst
        ? await perfFetch('aircraft', `${API_URL}/api/aircrafts/positions`)
        : await fetch(`${API_URL}/api/aircrafts/positions`)
      const result = isFirst ? await perfJson<any>('aircraft', res) : await res.json()
      if (isFirst) perfDone('aircraft', result.data?.length ?? 0, t0)

      consecutiveErrorsRef.current = 0
      setApiError(false)

      const newCount = result.data?.length ?? 0
      if (newCount !== prevCountRef.current) {
        prevCountRef.current = newCount
        setAircraftsData(result.data || [])
      }
      setLastUpdate(new Date())
    } catch (error) {
      console.error('Erreur lors du chargement des données avions:', error)
      consecutiveErrorsRef.current++
      if (consecutiveErrorsRef.current >= 2) setApiError(true)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return useMemo(() => ({ aircraftsData, lastUpdate, apiError }), [aircraftsData, lastUpdate, apiError])
}
