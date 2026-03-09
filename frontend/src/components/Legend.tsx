import React from 'react'

const items = [
  { color: '#22c55e', label: 'Négligeable (51–60 dB)' },
  { color: '#eab308', label: 'Perceptible (> 60 dB)' },
  { color: '#f97316', label: 'Gênant (≥ 70 dB)' },
  { color: '#ef4444', label: 'Dangereux (≥ 80 dB)' },
]

export default React.memo(function Legend() {
  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-4 shadow-2xl">
      <h3 className="text-sky-400 font-semibold text-sm mb-3">Niveau de bruit</h3>
      <div className="space-y-2">
        {items.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2.5">
            <div className="w-7 h-3.5 rounded-sm flex-shrink-0" style={{ backgroundColor: color }} />
            <span className="text-slate-300 text-xs">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
})
