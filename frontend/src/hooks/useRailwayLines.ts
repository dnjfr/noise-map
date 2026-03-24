import { useState, useEffect } from 'react'
import { perfFetch, perfJson, perfDone } from './perfLog'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export interface RailwayLinesGeoJSON {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    properties: { railway: string; is_high_speed: boolean }
    geometry: { type: 'LineString'; coordinates: [number, number][] }
  }>
}

export function useRailwayLines(): { linesGeoJSON: RailwayLinesGeoJSON | null } {
  const [linesGeoJSON, setLinesGeoJSON] = useState<RailwayLinesGeoJSON | null>(null)

  useEffect(() => {
    const t0 = performance.now()
    perfFetch('railway-lines', `${API_URL}/api/railway/lines`)
      .then(r => r.ok ? perfJson<any>('railway-lines', r) : null)
      .then(data => {
        if (data) {
          setLinesGeoJSON(data)
          perfDone('railway-lines', data.features?.length ?? 0, t0)
        }
      })
      .catch(err => console.error('Erreur chargement lignes ferroviaires:', err))
  }, [])  // Une seule fois au montage, données statiques

  return { linesGeoJSON }
}
