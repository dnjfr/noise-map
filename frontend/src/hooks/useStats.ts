import { useState, useEffect, useCallback } from 'react'

const API_URL = import.meta.env.VITE_API_URL
const UPDATE_INTERVAL = 5000

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

export function useStats(): Stats | null {
  const [stats, setStats] = useState<Stats | null>(null)

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`http://${API_URL}:8000/api/stats`)
      const data: Stats = await res.json()
      setStats(prev => {
        if (
          prev != null &&
          data.aircraft_count === prev.aircraft_count &&
          data.avg_noise_db === prev.avg_noise_db &&
          data.max_noise_db === prev.max_noise_db &&
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
    }
  }, [])

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchStats])

  return stats
}
