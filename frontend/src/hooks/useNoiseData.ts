import { useState, useEffect, useCallback, useRef } from 'react'

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
}

interface NoiseState {
  noiseData: NoiseZone[]
  aircraftData: Aircraft[]
  stats: Stats | null
  lastUpdate: Date | null
}

/**
 * Hook React exposant les données de l'API (bruit, avions, statistiques).
 * Récupère les données toutes les 3 secondes et les expose via NoiseState.
 * @returns {NoiseState} Objet contenant noiseData, aircraftData, stats et lastUpdate
 */
export function useNoiseData() {
  const [state, setState] = useState<NoiseState>({
    noiseData: [],
    aircraftData: [],
    stats: null,
    lastUpdate: null,
  })

  const prevRef = useRef<NoiseState | null>(null)

  /**
   * Récupère les données de bruit, d'avions et de statistiques depuis l'API.
   * Compare avec l'état précédent pour éviter un setState inutile si les données n'ont pas changé.
   * En cas de changement, met à jour l'état ; sinon, met à jour uniquement lastUpdate.
   * @returns {Promise<void>}
   */
  const fetchData = useCallback(async () => {
    try {
      const [noiseRes, aircraftRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/api/noise/current?min_noise=40`),
        fetch(`${API_URL}/api/aircraft/current`),
        fetch(`${API_URL}/api/stats`),
      ])
      const noiseResult = await noiseRes.json()
      const aircraftResult = await aircraftRes.json()
      const statsResult = await statsRes.json()

      const newAircraftCount = aircraftResult.data?.length ?? 0
      const prevAircraftCount = prevRef.current?.aircraftData.length ?? -1
      const newNoiseCount = noiseResult.data?.length ?? 0
      const prevNoiseCount = prevRef.current?.noiseData.length ?? -1

      if (
        newAircraftCount === prevAircraftCount &&
        newNoiseCount === prevNoiseCount &&
        JSON.stringify(statsResult) === JSON.stringify(prevRef.current?.stats)
      ) {
        // Données identiques : mettre à jour uniquement l'horloge, sans recréer les arrays
        setState(prev => ({ ...prev, lastUpdate: new Date() }))
        return
      }

      const newState: NoiseState = {
        noiseData: noiseResult.data || [],
        aircraftData: aircraftResult.data || [],
        stats: statsResult,
        lastUpdate: new Date(),
      }
      prevRef.current = newState
      setState(newState)
    } catch (error) {
      console.error('Erreur lors du chargement des données:', error)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, UPDATE_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchData])

  return state
}
