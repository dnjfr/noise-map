import { useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import LayerToggle from './components/LayerToggle'
import Legend from './components/Legend'
import { DEFAULT_STYLE_KEY, MAP_STYLES } from './components/Map'
import type { MapStyleKey } from './components/Map'
import NoiseMap from './components/Map'
import MapStyleToggle from './components/MapStyleToggle'
import StatsPanel from './components/StatsPanel'
import { useAircraftsData } from './hooks/useAircraftsData'
import { useRailwaysData } from './hooks/useRailwaysData'
import { useRoadsData } from './hooks/useRoadsData'
import { useRailwaysShapes } from './hooks/useRailwaysShapes'
import { useStats } from './hooks/useStats'

const DEBUG_PERF = true

const PAGE_OPEN = performance.now()
if (DEBUG_PERF) console.log(`%c[PERF] ══════ PAGE OUVERTE ══════`, 'color: #22d3ee; font-weight: bold; font-size: 14px')

export default function App() {
  const { aircraftsData, lastUpdate } = useAircraftsData()
  const stats = useStats()
  const { roadsData } = useRoadsData()
  const { railwaysData } = useRailwaysData()
  const { shapesData, refreshShapes } = useRailwaysShapes()

  // Refresh shapes dès qu'un trip inconnu apparaît (évite les 5 min de fallback ligne droite)
  useEffect(() => {
    if (railwaysData.length === 0) return
    const hasUnknown = railwaysData.some(t => !shapesData.has(t.trip_id))
    if (hasUnknown) refreshShapes()
  }, [railwaysData])

  // Ne passer que les trains dont la shape est disponible (évite les trains immobiles au chargement)
  const railwayDataWithShapes = useMemo(
    () => railwaysData.filter(t => shapesData.has(t.trip_id) && (shapesData.get(t.trip_id)?.length ?? 0) >= 2),
    [railwaysData, shapesData],
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
      if (DEBUG_PERF) console.log(`%c[PERF] ══════ PAGE FERMÉE (durée: ${((performance.now() - PAGE_OPEN) / 1000).toFixed(1)}s) ══════`, 'color: #f87171; font-weight: bold; font-size: 14px')
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])

  const [showAircraft, setShowAircraft] = useState(true)
  const [showRoads, setShowRoads] = useState(true)
  const [showRailways, setShowRailways] = useState(true)
  const [mapStyleKey, setMapStyleKey] = useState<MapStyleKey>(DEFAULT_STYLE_KEY)

  return (
    <div className="relative w-screen h-screen bg-slate-950">
      <NoiseMap aircraftsData={aircraftsData} roadsData={roadsData} railwaysData={railwayDataWithShapes} railwaysShapes={shapesData} showAircrafts={showAircraft} showRoads={showRoads} showRailways={showRailways} mapStyleKey={mapStyleKey} />
      <div className="absolute top-4 right-4 z-[1000] flex flex-col gap-3 w-72">
        <Header lastUpdate={lastUpdate} />
        <StatsPanel stats={stats} />
      </div>
      <div className="absolute bottom-8 right-4 z-[1000]">
        <Legend />
      </div>
      {Object.keys(MAP_STYLES).length >= 2 && (
        <div className="absolute bottom-4 left-4 z-[1000]">
          <MapStyleToggle currentStyle={mapStyleKey} onStyleChange={setMapStyleKey} />
        </div>
      )}
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
