import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL
const FAST_INTERVAL = 3000   // 3s pendant le chargement initial
const SLOW_INTERVAL = 30000  // 30s une fois les données stables

export interface RoadsSegment {
  code_pme: string
  axe: string
  lat_deb: number
  lon_deb: number
  lat_fin: number
  lon_fin: number
  geom_osm: [number, number][] | null
  noise_db: number
  traffic_flow: number
  average_speed: number
  nb_voies: number
}

/**
 * Hook React exposant les segments routiers avec leur niveau de bruit (HERE Traffic).
 * Polling adaptatif sur /api/roads/segments_noise : 3s pendant le chargement initial,
 * puis 30s une fois les données stabilisées (3 polls consécutifs sans changement de comptage).
 * @returns { roadsData, lastUpdate }
 */
export function useRoadsData(): { roadsData: RoadsSegment[]; lastUpdate: Date | null; apiError: boolean } {
  const [roadsData, setRoadsData] = useState<RoadsSegment[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [apiError, setApiError] = useState(false)
  const prevCountRef = useRef(0)

  const consecutiveErrorsRef = useRef(0)
  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const response = isFirst
        ? await perfFetch('road', `${API_URL}/api/roads/segments_noise`)
        : await fetch(`${API_URL}/api/roads/segments_noise`)
      if (!response.ok) {
        consecutiveErrorsRef.current++
        if (consecutiveErrorsRef.current >= 2) setApiError(true)
        return 0
      }
      const result = isFirst
        ? await perfJson<any>('road', response)
        : await response.json()
      consecutiveErrorsRef.current = 0
      setApiError(false)
      setRoadsData(result.data || [])
      setLastUpdate(new Date())
      const count = (result.data || []).length
      if (isFirst) perfDone('road', count, t0)
      return count
    } catch (error) {
      console.error('Erreur chargement données routières:', error)
      consecutiveErrorsRef.current++
      if (consecutiveErrorsRef.current >= 2) setApiError(true)
      return 0
    }
  }, [])

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval>
    let stableCount = 0

    const run = async () => {
      const count = await fetchData() ?? 0
      const prev = prevCountRef.current

      if (count > 0 && count === prev) {
        stableCount++
      } else {
        stableCount = 0
      }
      prevCountRef.current = count

      // Passer en mode lent après 3 polls consécutifs sans changement
      const nextInterval = stableCount >= 3 ? SLOW_INTERVAL : FAST_INTERVAL
      intervalId = setTimeout(run, nextInterval)
    }

    intervalId = setTimeout(run, 0)
    return () => clearTimeout(intervalId)
  }, [fetchData])

  return useMemo(() => ({ roadsData, lastUpdate, apiError }), [roadsData, lastUpdate, apiError])
}
