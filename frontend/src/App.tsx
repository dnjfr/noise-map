import { useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import InfoModal from './components/InfoModal'
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

const DEBUG_PERF = import.meta.env.VITE_DEBUG_PERF === 'true'

const PAGE_OPEN = performance.now()
if (DEBUG_PERF) console.log(`%c[PERF] ══════ PAGE OUVERTE ══════`, 'color: #22d3ee; font-weight: bold; font-size: 14px')

export default function App() {
  const { aircraftsData, lastUpdate, apiError: aircraftError } = useAircraftsData()
  const { stats, apiError: statsError } = useStats()
  const { roadsData, apiError: roadsError } = useRoadsData()
  const { railwaysData, apiError: railwaysError } = useRailwaysData()
  const { shapesData, refreshShapes, apiError: shapesError } = useRailwaysShapes()

  const hasApiError = aircraftError || statsError || roadsError || railwaysError || shapesError

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
  const [showInfo, setShowInfo] = useState(false)

  return (
    <div className="relative w-screen h-screen bg-slate-950">
      {hasApiError && (
        <div className="absolute top-0 left-0 right-0 z-[2000] bg-red-700/90 text-white text-sm text-center py-2 px-4 backdrop-blur-sm">
          API inaccessible — les données affichées peuvent ne plus être à jour
        </div>
      )}
      <NoiseMap aircraftsData={aircraftsData} roadsData={roadsData} railwaysData={railwayDataWithShapes} railwaysShapes={shapesData} showAircrafts={showAircraft} showRoads={showRoads} showRailways={showRailways} mapStyleKey={mapStyleKey} />
      <div className="absolute top-4 right-4 z-[1000] flex flex-col gap-3 w-72">
        <Header lastUpdate={lastUpdate} />
        <StatsPanel stats={stats} />
      </div>
      <div className="absolute bottom-8 right-4 z-[1000]">
        <Legend />
      </div>
      <div className="absolute bottom-4 right-[304px] z-[1000] flex flex-row gap-2">
        <button
          onClick={() => setShowInfo(true)}
          title="À propos"
          className="w-9 h-9 rounded-lg shadow-2xl border-2 border-slate-600 bg-slate-800/90 hover:border-slate-400 hover:scale-105 transition-all duration-200 cursor-pointer flex items-center justify-center text-slate-300 hover:text-white p-1.5"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
            <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18a8 8 0 110-16 8 8 0 010 16zm-1-9h2v6h-2v-6zm0-4h2v2h-2V5z" />
          </svg>
        </button>
        <a
          href="https://github.com/dnjfr/noise-map"
          target="_blank"
          rel="noopener noreferrer"
          title="GitHub"
          className="w-9 h-9 rounded-lg shadow-2xl border-2 border-slate-600 bg-slate-800/90 hover:border-slate-400 hover:scale-105 transition-all duration-200 flex items-center justify-center text-slate-300 hover:text-white p-1.5"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-full h-full">
            <path fillRule="evenodd" clipRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-.98.08-2.04 0 0 .67-.21 2.2 1.02.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-1.02 2.2-1.02.44 1.06.16 1.84.08 2.04.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
        </a>
      </div>
      {showInfo && <InfoModal onClose={() => setShowInfo(false)} />}
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
