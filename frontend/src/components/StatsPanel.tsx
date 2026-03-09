import React from 'react'
import type { Stats } from '../hooks/useNoiseData'

interface Props {
  stats: Stats | null
}

export default React.memo(function StatsPanel({ stats }: Props) {
  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-4 shadow-2xl">
      <div className="space-y-0">
        <StatRow label="Avions détectés" value={stats ? String(stats.aircraft_count) : '—'} />
        <StatRow label="Bruit moyen" value={stats ? `${stats.avg_noise_db.toFixed(1)} dB` : '— dB'} />
        <StatRow label="Bruit maximum" value={stats ? `${stats.max_noise_db.toFixed(1)} dB` : '— dB'} />
      </div>
    </div>
  )
})

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2.5 border-b border-slate-700/50 last:border-0">
      <span className="text-slate-400 text-sm">{label}</span>
      <span className="text-sky-400 font-bold text-sm tabular-nums">{value}</span>
    </div>
  )
}
