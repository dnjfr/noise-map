import { useState, useEffect, useCallback, useRef } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
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

export function useRailwayData(): { railwayData: Train[]; lastUpdate: Date | null } {
  const [railwayData, setRailwayData] = useState<Train[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const response = isFirst
        ? await perfFetch('railway-current', `${API_URL}/api/railway/current`)
        : await fetch(`${API_URL}/api/railway/current`)
      if (!response.ok) return
      const result = isFirst
        ? await perfJson<any>('railway-current', response)
        : await response.json()
      setRailwayData(result.data || [])
      setLastUpdate(new Date())
      if (isFirst) perfDone('railway-current', result.data?.length ?? 0, t0)
    } catch (error) {
      console.error('Erreur chargement données ferroviaires:', error)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return { railwayData, lastUpdate }
}
