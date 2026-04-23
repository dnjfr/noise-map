import React, { useState } from 'react'
import type { Stats } from '../hooks/useStats'

interface Props {
  stats: Stats | null
}

/** Panneau de statistiques en 3 sections repliables (Aérien / Ferré / Routier).
 *  Affiche comptages et niveaux de bruit moyen/max depuis l'endpoint /api/stats. */
export default React.memo(function StatsPanel({ stats }: Props) {
  const hasStats = stats != null && typeof stats.aircraft_count === 'number'
  return (
    <div className="flex flex-col gap-1.5">
      <Section title="Aérien">
        <StatRow label="Avions détectés" value={hasStats ? String(stats.aircraft_count) : '—'} />
        <StatRow label="Bruit moyen" value={hasStats && stats.avg_noise_db ? `${stats.avg_noise_db.toFixed(1)} dB` : '— dB'} />
        <StatRow label="Bruit maximum" value={hasStats && stats.max_noise_db ? `${stats.max_noise_db.toFixed(1)} dB` : '— dB'} />
      </Section>
      <Section title="Ferré">
        <StatRow label="Trains détectés" value={hasStats ? String(stats.railway_train_count) : '—'} />
        <StatRow label="Bruit moyen" value={hasStats && stats.railway_avg_noise_db ? `${stats.railway_avg_noise_db.toFixed(1)} dB` : '— dB'} />
        <StatRow label="Bruit maximum" value={hasStats && stats.railway_max_noise_db ? `${stats.railway_max_noise_db.toFixed(1)} dB` : '— dB'} />
      </Section>
      <Section title="Routier">
        <StatRow label="Segments détectés" value={hasStats ? String(stats.road_segment_count) : '—'} />
        <StatRow label="Bruit moyen" value={hasStats && stats.road_avg_noise_db ? `${stats.road_avg_noise_db.toFixed(1)} dB` : '— dB'} />
        <StatRow label="Bruit maximum" value={hasStats && stats.road_max_noise_db ? `${stats.road_max_noise_db.toFixed(1)} dB` : '— dB'} />
      </Section>
    </div>
  )
})

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-lg shadow-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex justify-between items-center px-3 py-1.5 hover:bg-slate-800/60 transition-colors"
      >
        <span className="text-slate-200 text-xs font-semibold tracking-wide uppercase">{title}</span>
        <span className="text-slate-400 text-sm leading-none w-3 text-center">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-3 pb-1.5 border-t border-slate-700/50">
          {children}
        </div>
      )}
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-slate-700/40 last:border-0">
      <span className="text-slate-400 text-xs">{label}</span>
      <span className="text-sky-400 font-bold text-xs tabular-nums">{value}</span>
    </div>
  )
}
