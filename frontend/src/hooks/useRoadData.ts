import { useState, useEffect, useCallback, useRef } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const FAST_INTERVAL = 3000   // 3s pendant le chargement initial
const SLOW_INTERVAL = 30000  // 30s une fois les données stables

export interface RoadSegment {
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
 * Hook React pour récupérer les données de bruit routier.
 * Polling /api/road/current toutes les 30s.
 * @returns { roadData, lastUpdate }
 */
export function useRoadData(): { roadData: RoadSegment[]; lastUpdate: Date | null } {
  const [roadData, setRoadData] = useState<RoadSegment[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const prevCountRef = useState(0)

  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const response = isFirst
        ? await perfFetch('road', `${API_URL}/api/road/current`)
        : await fetch(`${API_URL}/api/road/current`)
      if (!response.ok) return
      const result = isFirst
        ? await perfJson<any>('road', response)
        : await response.json()
      setRoadData(result.data || [])
      setLastUpdate(new Date())
      const count = (result.data || []).length
      if (isFirst) perfDone('road', count, t0)
      return count
    } catch (error) {
      console.error('Erreur chargement données routières:', error)
      return 0
    }
  }, [])

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval>
    let stableCount = 0

    const run = async () => {
      const count = await fetchData() ?? 0
      const prev = prevCountRef[0]

      if (count > 0 && count === prev) {
        stableCount++
      } else {
        stableCount = 0
      }
      prevCountRef[0] = count

      // Passer en mode lent après 3 polls consécutifs sans changement
      const nextInterval = stableCount >= 3 ? SLOW_INTERVAL : FAST_INTERVAL
      intervalId = setTimeout(run, nextInterval)
    }

    intervalId = setTimeout(run, 0)
    return () => clearTimeout(intervalId)
  }, [fetchData])

  return { roadData, lastUpdate }
}
