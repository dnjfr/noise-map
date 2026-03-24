import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const UPDATE_INTERVAL = 3000

export interface NoiseZone {
  latitude: number
  longitude: number
  noise_db: number
  aircraft_count: number
  grid_id: string
}

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
}

interface NoiseData {
  noiseData: NoiseZone[]
  aircraftData: Aircraft[]
  stats: Stats | null
}

interface NoiseState extends NoiseData {
  lastUpdate: Date | null
}

/**
 * Hook React exposant les données de l'API (bruit, avions, statistiques).
 * Récupère les données toutes les 3 secondes et les expose via NoiseState.
 * @returns {NoiseState} Objet contenant noiseData, aircraftData, stats et lastUpdate
 */
export function useNoiseData() {
  const [data, setData] = useState<NoiseData>({
    noiseData: [],
    aircraftData: [],
    stats: null,
  })
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const prevRef = useRef<NoiseData | null>(null)

  /**
   * Récupère les données de bruit, d'avions et de statistiques depuis l'API.
   * Compare avec l'état précédent pour éviter un setState inutile si les données n'ont pas changé.
   * En cas de changement, met à jour l'état ; sinon, met à jour uniquement lastUpdate.
   * @returns {Promise<void>}
   */
  const fetchCountRef = useRef(0)
  const fetchData = useCallback(async () => {
    const isFirst = fetchCountRef.current === 0
    fetchCountRef.current++
    const t0 = performance.now()
    try {
      const [noiseRes, aircraftRes, statsRes] = await Promise.all([
        isFirst ? perfFetch('noise', `${API_URL}/api/noise/current?min_noise=40`) : fetch(`${API_URL}/api/noise/current?min_noise=40`),
        isFirst ? perfFetch('aircraft', `${API_URL}/api/aircraft/current`) : fetch(`${API_URL}/api/aircraft/current`),
        isFirst ? perfFetch('stats', `${API_URL}/api/stats`) : fetch(`${API_URL}/api/stats`),
      ])
      const noiseResult = isFirst ? await perfJson<any>('noise', noiseRes) : await noiseRes.json()
      const aircraftResult = isFirst ? await perfJson<any>('aircraft', aircraftRes) : await aircraftRes.json()
      const statsResult = isFirst ? await perfJson<any>('stats', statsRes) : await statsRes.json()
      if (isFirst) {
        perfDone('noise', noiseResult.data?.length ?? 0, t0)
        perfDone('aircraft', aircraftResult.data?.length ?? 0, t0)
        perfDone('stats', '1', t0)
      }

      const newAircraftCount = aircraftResult.data?.length ?? 0
      const prevAircraftCount = prevRef.current?.aircraftData.length ?? -1
      const newNoiseCount = noiseResult.data?.length ?? 0
      const prevNoiseCount = prevRef.current?.noiseData.length ?? -1

      const prevStats = prevRef.current?.stats
      const statsUnchanged = prevStats != null &&
        statsResult.aircraft_count === prevStats.aircraft_count &&
        statsResult.avg_noise_db === prevStats.avg_noise_db &&
        statsResult.max_noise_db === prevStats.max_noise_db

      if (newAircraftCount === prevAircraftCount && newNoiseCount === prevNoiseCount && statsUnchanged) {
        // Données identiques : mettre à jour uniquement l'horloge, sans recréer les arrays
        setLastUpdate(new Date())
        return
      }

      const newData: NoiseData = {
        noiseData: noiseResult.data || [],
        aircraftData: aircraftResult.data || [],
        stats: statsResult,
      }
      prevRef.current = newData
      setData(newData)
      setLastUpdate(new Date())
    } catch (error) {
      console.error('Erreur lors du chargement des données:', error)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return useMemo(() => ({ ...data, lastUpdate }), [data, lastUpdate])
}
