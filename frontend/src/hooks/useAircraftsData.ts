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

export interface Stats {
  aircraft_count: number
  avg_noise_db: number
  max_noise_db: number
  railway_train_count: number
  railway_avg_noise_db: number
  railway_max_noise_db: number
  road_segment_count: number
  road_avg_noise_db: number
  road_max_noise_db: number
}

interface AircraftsData {
  aircraftsData: Aircraft[]
  stats: Stats | null
}

interface AircraftsState extends AircraftsData {
  lastUpdate: Date | null
}

/**
 * Hook React exposant les positions des avions et les statistiques globales.
 * Poll /api/aircrafts/positions et /api/stats toutes les 3 secondes.
 * Évite les re-renders inutiles en comparant les comptages avant de mettre à jour l'état.
 *
 * @returns { aircraftsData, stats, lastUpdate }
 */
export function useAircraftsData(): AircraftsState {
  const [data, setData] = useState<AircraftsData>({
    aircraftsData: [],
    stats: null,
  })
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const prevRef = useRef<AircraftsData | null>(null)

  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const [aircraftRes, statsRes] = await Promise.all([
        isFirst ? perfFetch('aircraft', `http://${API_URL}:8000/api/aircrafts/positions`) : fetch(`http://${API_URL}:8000/api/aircrafts/positions`),
        isFirst ? perfFetch('stats', `http://${API_URL}:8000/api/stats`) : fetch(`http://${API_URL}:8000/api/stats`),
      ])
      const aircraftResult = isFirst ? await perfJson<any>('aircraft', aircraftRes) : await aircraftRes.json()
      const statsResult = isFirst ? await perfJson<any>('stats', statsRes) : await statsRes.json()
      if (isFirst) {
        perfDone('aircraft', aircraftResult.data?.length ?? 0, t0)
        perfDone('stats', '1', t0)
      }

      const newAircraftCount = aircraftResult.data?.length ?? 0
      const prevAircraftCount = prevRef.current?.aircraftsData.length ?? -1

      const prevStats = prevRef.current?.stats
      const statsUnchanged = prevStats != null &&
        statsResult.aircraft_count === prevStats.aircraft_count &&
        statsResult.avg_noise_db === prevStats.avg_noise_db &&
        statsResult.max_noise_db === prevStats.max_noise_db

      if (newAircraftCount === prevAircraftCount && statsUnchanged) {
        setLastUpdate(new Date())
        return
      }

      const newData: AircraftsData = {
        aircraftsData: aircraftResult.data || [],
        stats: statsResult,
      }
      prevRef.current = newData
      setData(newData)
      setLastUpdate(new Date())
    } catch (error) {
      console.error('Erreur lors du chargement des données avions:', error)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return useMemo(() => ({ ...data, lastUpdate }), [data, lastUpdate])
}
