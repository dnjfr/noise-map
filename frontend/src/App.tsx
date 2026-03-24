import { useState, useEffect, useMemo } from 'react'
import NoiseMap from './components/Map'
import StatsPanel from './components/StatsPanel'
import Legend from './components/Legend'
import Header from './components/Header'
import LayerToggle from './components/LayerToggle'
import { useNoiseData } from './hooks/useNoiseData'
import { useRoadData } from './hooks/useRoadData'
import { useRailwayData } from './hooks/useRailwayData'
// useRailwayLines supprimé — les shapes GTFS suffisent pour le tracé
import { useRailwayShapes } from './hooks/useRailwayShapes'

const PAGE_OPEN = performance.now()
console.log(`%c[PERF] ══════ PAGE OUVERTE ══════`, 'color: #22d3ee; font-weight: bold; font-size: 14px')

export default function App() {
  const { stats, noiseData, aircraftData, lastUpdate } = useNoiseData()
  const { roadData } = useRoadData()
  const { railwayData } = useRailwayData()
  const { shapesData, refreshShapes } = useRailwayShapes()

  // Refresh shapes dès qu'un trip inconnu apparaît (évite les 5 min de fallback ligne droite)
  useEffect(() => {
    if (railwayData.length === 0) return
    const hasUnknown = railwayData.some(t => !shapesData.has(t.trip_id))
    if (hasUnknown) refreshShapes()
  }, [railwayData])

  // Ne passer que les trains dont la shape est disponible (évite les trains immobiles au chargement)
  const railwayDataWithShapes = useMemo(
    () => railwayData.filter(t => shapesData.has(t.trip_id) && (shapesData.get(t.trip_id)?.length ?? 0) >= 2),
    [railwayData, shapesData],
  )
  // Afficher la carte dès qu'au moins une source a répondu (évite 30s de blocage si une API est lente)
  const [loadingTimeout, setLoadingTimeout] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setLoadingTimeout(true), 5000)
    return () => clearTimeout(timer)
  }, [])
  const isLoading = lastUpdate === null && !loadingTimeout

  // Log fermeture page
  useEffect(() => {
    const onUnload = () => {
      console.log(`%c[PERF] ══════ PAGE FERMÉE (durée: ${((performance.now() - PAGE_OPEN) / 1000).toFixed(1)}s) ══════`, 'color: #f87171; font-weight: bold; font-size: 14px')
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])

  const [showAircraft, setShowAircraft] = useState(true)
  const [showRoads, setShowRoads] = useState(true)
  const [showRailways, setShowRailways] = useState(true)

  return (
    <div className="relative w-screen h-screen bg-slate-950">
      <NoiseMap aircraftData={aircraftData} roadData={roadData} railwayData={railwayDataWithShapes} railwayShapes={shapesData} showAircraft={showAircraft} showRoads={showRoads} showRailways={showRailways} />
      <div className="absolute top-4 right-4 z-[1000] flex flex-col gap-3 w-72">
        <Header lastUpdate={lastUpdate} />
        <StatsPanel stats={stats} roadData={roadData} />
      </div>
      <div className="absolute bottom-8 right-4 z-[1000]">
        <Legend />
      </div>
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000]">
        <LayerToggle
          showAircraft={showAircraft}
          showRoads={showRoads}
          showRailways={showRailways}
          onToggleAircraft={() => setShowAircraft(v => !v)}
          onToggleRoads={() => setShowRoads(v => !v)}
          onToggleRailways={() => setShowRailways(v => !v)}
        />
      </div>

      {isLoading && (
        <div className="absolute inset-0 z-[2000] flex flex-col items-center justify-center bg-slate-950/80 backdrop-blur-sm">
          <div className="w-14 h-14 rounded-full border-4 border-slate-600 border-t-blue-400 animate-spin mb-5" />
          <p className="text-slate-300 text-sm font-medium tracking-wide">Chargement des données...</p>
        </div>
      )}
    </div>
  )
}
