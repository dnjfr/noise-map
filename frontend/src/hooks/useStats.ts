import { useState, useEffect, useCallback, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL
const UPDATE_INTERVAL = 5000

export interface Stats {
  aircraft_count: number
  aircraft_avg_noise_db: number
  aircraft_max_noise_db: number
  railway_train_count: number
  railway_avg_noise_db: number
  railway_max_noise_db: number
  road_segment_count: number
  road_avg_noise_db: number
  road_max_noise_db: number
}

export function useStats(): { stats: Stats | null; apiError: boolean } {
  const [stats, setStats] = useState<Stats | null>(null)
  const [apiError, setApiError] = useState(false)
  const consecutiveErrorsRef = useRef(0)

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/stats`)
      if (!res.ok) {
        consecutiveErrorsRef.current++
        if (consecutiveErrorsRef.current >= 2) setApiError(true)
        return
      }
      const data: Stats = await res.json()
      consecutiveErrorsRef.current = 0
      setApiError(false)
      setStats(prev => {
        if (
          prev != null &&
          data.aircraft_count === prev.aircraft_count &&
          data.aircraft_avg_noise_db === prev.aircraft_avg_noise_db &&
          data.aircraft_max_noise_db === prev.aircraft_max_noise_db &&
          data.road_segment_count === prev.road_segment_count &&
          data.road_avg_noise_db === prev.road_avg_noise_db &&
          data.road_max_noise_db === prev.road_max_noise_db &&
          data.railway_train_count === prev.railway_train_count &&
          data.railway_avg_noise_db === prev.railway_avg_noise_db &&
          data.railway_max_noise_db === prev.railway_max_noise_db
        ) return prev
        return data
      })
    } catch (error) {
      console.error('Erreur lors du chargement des statistiques:', error)
      consecutiveErrorsRef.current++
      if (consecutiveErrorsRef.current >= 2) setApiError(true)
    }
  }, [])

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchStats])

  return { stats, apiError }
}
