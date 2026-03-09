import NoiseMap from './components/Map'
import StatsPanel from './components/StatsPanel'
import Legend from './components/Legend'
import Header from './components/Header'
import { useNoiseData } from './hooks/useNoiseData'

export default function App() {
  const { stats, noiseData, aircraftData, lastUpdate } = useNoiseData()
  const isLoading = lastUpdate === null

  return (
    <div className="relative w-screen h-screen bg-slate-950">
      <NoiseMap noiseData={noiseData} aircraftData={aircraftData} />
      <div className="absolute top-4 right-4 z-[1000] flex flex-col gap-3 w-72">
        <Header lastUpdate={lastUpdate} />
        <StatsPanel stats={stats} />
      </div>
      <div className="absolute bottom-8 right-4 z-[1000]">
        <Legend />
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
